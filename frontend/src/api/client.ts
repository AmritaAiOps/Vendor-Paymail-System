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

type Query = Record<string, string | number | undefined>;

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const qs = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
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
  return res.status === 204 ? (undefined as T) : res.json();
}

const get = <T>(p: string, q?: Query) => request<T>("GET", p, undefined, q);
const send = <T>(m: string, p: string, b?: unknown) => request<T>(m, p, b);

// --- types (short forms from CONTRACT.md; exact types live in backend/app/schemas.py) ---
export type ResultOut = {
  id: number; batch_id: number; vendor_name: string; invoice_no: string; utr: string;
  invoice_value: string; payment_date: string | null; amount_paid: string | null;
  tds_amount: string | null; invoice_deduction: string | null; reason: string | null;
  status: string; exception_type: string | null;
};
export type RowIssue = { sheet: string; row: number; message: string; rejected: boolean };
export type FileReport = { file_name: string; rows_read: number; rows_kept: number; rows_skipped: number; rows_rejected: number; issues: RowIssue[] };
export type BatchOut = { id: number; uploaded_at: string; consolidated_file: string; bank_file: string; gdn_file: string; tds_file: string; vendors_file: string; status: string; error_message: string | null };
export type BatchSummary = { batch: BatchOut; counts: Record<string, number>; files: Record<string, FileReport> };
export type QueueItemOut = { id: number; vendor_id: number; vendor_name: string; to_email: string; send_on_date: string; status: string; sent_at: string | null; subject: string; invoice_count: number };
export type EmailPreview = { subject: string; html: string; text: string };
export type HistoryOut = Record<string, unknown> & { id: number };
export type VendorOut = { id: number; party_name: string; email: string; is_email_valid: boolean };
export type SettingsModel = { dry_run: boolean; send_time: string };
export type RunNowOut = { sent: number; failed: number; dry_run: number; not_sent: number };

export const api = {
  health: () => get<{ status: string }>("/health"),
  uploadBatch: (form: FormData) => send<BatchOut>("POST", "/batches", form),
  batchSummary: (id: number) => get<BatchSummary>(`/batches/${id}/summary`),
  reconcile: (id: number) => send<BatchSummary>("POST", `/batches/${id}/reconcile`),
  batchResults: (id: number) => get<ResultOut[]>(`/batches/${id}/results`),
  runNow: () => send<RunNowOut>("POST", "/scheduler/run-now"),
  emailQueue: (q?: { batch_id?: number; status?: string }) => get<QueueItemOut[]>("/email-queue", q),
  emailPreview: (id: number) => get<EmailPreview>(`/email-queue/${id}/preview`),
  emailHistory: () => get<HistoryOut[]>("/email-history"),
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
