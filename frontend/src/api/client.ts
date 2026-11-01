// The only module that talks to the backend. Paths are exactly those in docs/CONTRACT.md (b).
// Money is a string in JSON (never float); keep it a string until display.
const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

let authToken: string | null = null;
export const setAuthToken = (t: string | null) => { authToken = t; };

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
  }
}

/** Human text for any ApiError: a string, FastAPI's [{msg}] list, or the upload's [{file, message}] list. */
export function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Something went wrong";
  if (Array.isArray(err.detail)) {
    return err.detail.map((d) => (d.file ? `${d.file}: ${d.message}` : d.msg ?? d.message ?? JSON.stringify(d))).join("; ");
  }
  return err.message;
}

// Paths whose last response carried X-Stub: true (canned data from Person A's stubs). Dev screens show a tag.
const stubPaths = new Set<string>();
const noteStub = (path: string, header: string | null) => { header === "true" ? stubPaths.add(path) : stubPaths.delete(path); };
export const isStub = (path: string) => stubPaths.has(path);

type Query = Record<string, string | number | undefined>;

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<{ data: T; res: Response }> {
  const qs = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)));
  const headers: Record<string, string> = {};
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs.size ? `?${qs}` : ""}`, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the server");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, data?.detail ?? res.statusText);
  }
  noteStub(path, res.headers.get("X-Stub"));
  return { data: res.status === 204 ? (undefined as T) : await res.json(), res };
}

const get = async <T>(p: string, q?: Query) => (await request<T>("GET", p, undefined, q)).data;
const send = async <T>(m: string, p: string, b?: unknown) => (await request<T>(m, p, b)).data;

// fetch has no upload progress, so the batch upload uses XMLHttpRequest.
function upload<T>(path: string, form: FormData, onProgress: (pct: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}${path}`);
    if (authToken) xhr.setRequestHeader("Authorization", `Bearer ${authToken}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(new ApiError(0, "Cannot reach the server"));
    xhr.onload = () => {
      let data: any = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* non-JSON error body */ }
      if (xhr.status >= 200 && xhr.status < 300) { noteStub(path, xhr.getResponseHeader("X-Stub")); resolve(data as T); }
      else reject(new ApiError(xhr.status, data?.detail ?? xhr.statusText));
    };
    xhr.send(form);
  });
}

// --- types (short forms from CONTRACT.md; exact types live in backend/app/schemas.py) ---
export type ResultStatus = "PAID_IN_FULL" | "TDS_ONLY" | "DEDUCTION" | "EXCEPTION" | "MANUAL_REVIEW";
export type QueueStatus = "PENDING" | "SENDING" | "SENT" | "FAILED" | "SKIPPED";
export type HistoryStatus = "SENT" | "FAILED" | "DRY_RUN" | "NOT_SENT";
export type ResultOut = {
  id: number; batch_id: number; vendor_name: string; invoice_no: string; utr: string | null;
  invoice_value: string; payment_date: string | null; amount_paid: string | null;
  tds_amount: string | null; invoice_deduction: string | null; reason: string | null;
  status: ResultStatus; exception_type: string | null;
};
export type RowIssue = { sheet: string; row: number; message: string; rejected: boolean };
export type FileReport = { file_name: string; rows_read: number; rows_kept: number; rows_skipped: number; rows_rejected: number; issues: RowIssue[] };
export type BatchOut = { id: number; uploaded_at: string; consolidated_file: string; bank_file: string; gdn_file: string; tds_file: string; vendors_file: string; status: string; error_message: string | null };
export type BatchSummary = { batch: BatchOut; counts: Record<ResultStatus, number>; files: Record<string, FileReport> };
export type QueueItemOut = { id: number; vendor_id: number; vendor_name: string; to_email: string | null; send_on_date: string; status: QueueStatus; sent_at: string | null; subject: string | null; invoice_count: number };
export type EmailPreview = { subject: string; html: string; text: string };
export type HistoryOut = {
  id: number; logged_at: string; batch_id: number | null; vendor_name: string; to_email: string | null; subject: string | null;
  invoice_no: string | null; utr: string | null; invoice_amount: string | null; payment_date: string | null;
  amount_paid: string | null; tds_amount: string | null; invoice_deduction: string | null; reason: string | null;
  status: HistoryStatus; not_sent_reason: string | null; scheduled_send_date: string | null; sent_at: string | null;
  error_message: string | null; email_queue_id: number | null;
};
export type HistoryFilters = { date_from?: string; date_to?: string; vendor?: string; status?: HistoryStatus; q?: string };
export type VendorOut = { id: number; party_name: string; email: string; is_email_valid: boolean };
export type SettingsModel = { dry_run: boolean; send_time: string };
export type RunNowOut = { sent: number; failed: number; dry_run: number; not_sent: number };

export const UPLOAD_FIELDS = ["consolidated", "bank", "gdn", "tds", "vendors"] as const;
export type UploadField = (typeof UPLOAD_FIELDS)[number];

export const api = {
  health: () => get<{ status: string }>("/health"),
  uploadBatch: (files: Record<UploadField, File>, onProgress: (pct: number) => void) => {
    const form = new FormData();
    UPLOAD_FIELDS.forEach((f) => form.append(f, files[f]));
    return upload<BatchOut>("/batches", form, onProgress);
  },
  batchSummary: (id: number) => get<BatchSummary>(`/batches/${id}/summary`),
  reconcile: (id: number) => send<BatchSummary>("POST", `/batches/${id}/reconcile`),
  /** One page; total comes from X-Total-Count (null while the endpoint is a stub that doesn't send it). */
  batchResultsPage: async (id: number, limit: number, offset: number) => {
    const { data, res } = await request<ResultOut[]>("GET", `/batches/${id}/results`, undefined, { limit, offset });
    const total = res.headers.get("X-Total-Count");
    return { rows: data, total: total === null ? null : Number(total) };
  },
  runNow: () => send<RunNowOut>("POST", "/scheduler/run-now"),
  emailQueue: (q?: { batch_id?: number; status?: QueueStatus }) => get<QueueItemOut[]>("/email-queue", q),
  emailPreview: (id: number) => get<EmailPreview>(`/email-queue/${id}/preview`),
  /** Newest first. counts = per status for the date/vendor/search filters (not the status filter). */
  emailHistory: async (f: HistoryFilters, limit: number, offset: number) => {
    const { data, res } = await request<HistoryOut[]>("GET", "/email-history", undefined, { ...f, limit, offset });
    const counts = JSON.parse(res.headers.get("X-Status-Counts") ?? "{}") as Partial<Record<HistoryStatus, number>>;
    return { rows: data, total: Number(res.headers.get("X-Total-Count") ?? data.length), counts };
  },
  emailHistoryItem: (id: number) => get<HistoryOut>(`/email-history/${id}`),
  rebuildHistoryXlsx: () => send<{ rows: number }>("POST", "/email-history/rebuild-xlsx"),
  exceptions: () => get<ResultOut[]>("/exceptions"),
  manualReview: () => get<ResultOut[]>("/manual-review"),
  setReason: (resultId: number, reason: string) => send<ResultOut>("PUT", `/manual-review/${resultId}/reason`, { reason }),
  gdnUpload: (form: FormData) => send<{ rows_read: number; requeued: number }>("POST", "/manual-review/gdn-upload", form),
  setVendorEmail: (id: number, email: string) => send<VendorOut>("PUT", `/vendors/${id}/email`, { email }),
  settings: () => get<SettingsModel>("/settings"),
  saveSettings: (s: SettingsModel) => send<SettingsModel>("PUT", "/settings", s),
};

// Excel downloads are plain links (the browser handles the file); paths per contract.
export const downloadUrl = {
  proforma: (batchId: number) => `${BASE}/batches/${batchId}/proforma.xlsx`,
  report: (batchId: number) => `${BASE}/batches/${batchId}/report.xlsx`,
  historyExport: () => `${BASE}/email-history/export.xlsx`,
  exceptionsExport: () => `${BASE}/exceptions/export.xlsx`,
};
