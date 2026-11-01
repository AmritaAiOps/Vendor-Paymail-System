import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { UPLOAD_FIELDS, api, errorMessage, type FileReport, type UploadField } from "../api/client";
import { Empty, ErrorBox, Loading, StubTag, btnPrimary, focusRing, td, th, num } from "../components/ui";
import { setLastBatch } from "../lib/lastBatch";

const ZONES: { field: UploadField; label: string }[] = [
  { field: "consolidated", label: "Consolidated Report" },
  { field: "bank", label: "Bank Statement" },
  { field: "gdn", label: "GDN Report" },
  { field: "tds", label: "TDS Excel" },
  { field: "vendors", label: "Vendors List" },
];
const MAX_MB = 20; // shortcut: mirrors the server's MAX_UPLOAD_MB default; the server still enforces it, revisit if that setting changes

function check(f: File): string | null {
  if (!/\.(xlsx|xls)$/i.test(f.name)) return "Only .xlsx or .xls files are accepted";
  if (f.size > MAX_MB * 1024 * 1024) return `File is over ${MAX_MB} MB`;
  return null;
}

function Zone({ field, label, file, error, onPick }: { field: UploadField; label: string; file?: File; error?: string; onPick: (f: File | undefined) => void }) {
  const [over, setOver] = useState(false);
  const id = `file-${field}`;
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onPick(e.dataTransfer.files[0]); }}
      className={`rounded-lg border-2 border-dashed p-4 ${over ? "border-blue-600 bg-blue-50" : "border-slate-300 bg-white"}`}
    >
      <label htmlFor={id} className="block font-medium">{label}</label>
      <p className="mb-2 text-xs text-slate-600">Drop a file here or choose one (.xlsx, .xls)</p>
      <input id={id} type="file" accept=".xlsx,.xls" aria-describedby={`${id}-msg`} className={`block w-full text-sm ${focusRing}`}
        onChange={(e) => onPick(e.target.files?.[0])} />
      <p id={`${id}-msg`} aria-live="polite" className={`mt-2 text-sm ${error ? "text-red-800" : "text-slate-700"}`}>
        {error ?? (file ? `${file.name} (${(file.size / 1024).toFixed(0)} KB)` : "")}
      </p>
    </div>
  );
}

const FILE_LABEL: Record<string, string> = Object.fromEntries(ZONES.map((z) => [z.field, z.label]));

function FileSummary({ name, report }: { name: string; report: FileReport }) {
  const shown = report.issues.slice(0, 50);
  return (
    <section className="rounded border border-slate-200 bg-white p-3">
      <h3 className="font-medium">{FILE_LABEL[name] ?? name} <span className="font-normal text-slate-600">· {report.file_name}</span></h3>
      <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {([["Read", report.rows_read], ["Kept", report.rows_kept], ["Skipped", report.rows_skipped], ["Rejected", report.rows_rejected]] as const).map(([k, v]) => (
          <div key={k} className="flex gap-1"><dt className="text-slate-600">{k}</dt><dd className={`font-semibold tabular-nums ${k === "Rejected" && v > 0 ? "text-red-800" : ""}`}>{v.toLocaleString("en-IN")}</dd></div>
        ))}
      </dl>
      {report.issues.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className={`cursor-pointer ${focusRing}`}>{report.issues.length} row issue{report.issues.length > 1 ? "s" : ""}</summary>
          <table className="mt-2 w-full border-collapse text-sm">
            <thead><tr><th className={th}>Sheet</th><th className={`${th} ${num}`}>Row</th><th className={th}>Outcome</th><th className={th}>Message</th></tr></thead>
            <tbody>
              {shown.map((i, n) => (
                <tr key={n}><td className={td}>{i.sheet}</td><td className={`${td} ${num}`}>{i.row}</td>
                  <td className={td}>{i.rejected ? "Rejected" : "Kept, check"}</td><td className={td}>{i.message}</td></tr>
              ))}
            </tbody>
          </table>
          {report.issues.length > shown.length && <p className="mt-1 text-slate-600">…and {report.issues.length - shown.length} more.</p>}
        </details>
      )}
    </section>
  );
}

export default function Upload() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<Partial<Record<UploadField, File>>>({});
  const [errors, setErrors] = useState<Partial<Record<UploadField, string>>>({});
  const [progress, setProgress] = useState<number | null>(null);

  const pick = (field: UploadField, f: File | undefined) => {
    const problem = f ? check(f) : null;
    setErrors((e) => ({ ...e, [field]: problem ?? undefined }));
    setFiles((s) => ({ ...s, [field]: f && !problem ? f : undefined }));
  };
  const ready = UPLOAD_FIELDS.every((f) => files[f]);

  const up = useMutation({
    mutationFn: () => api.uploadBatch(files as Record<UploadField, File>, setProgress),
    onMutate: () => setProgress(0),
    onSuccess: (b) => setLastBatch(b.id),
  });
  const batchId = up.data?.id;
  const summary = useQuery({ queryKey: ["summary", batchId], queryFn: () => api.batchSummary(batchId!), enabled: batchId !== undefined });
  const run = useMutation({
    mutationFn: () => api.reconcile(batchId!),
    onSuccess: () => navigate(`/batch-results/${batchId}`),
  });

  return (
    <section>
      <h1 className="text-xl font-semibold">Upload<StubTag path="/batches" /></h1>
      <p className="mt-1 text-slate-600">Add the five Excel files for one reconciliation run.</p>
      <form className="mt-4" onSubmit={(e) => { e.preventDefault(); up.mutate(); }}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ZONES.map((z) => <Zone key={z.field} {...z} file={files[z.field]} error={errors[z.field]} onPick={(f) => pick(z.field, f)} />)}
        </div>
        <div className="mt-4 flex items-center gap-4">
          <button type="submit" className={btnPrimary} disabled={!ready || up.isPending}>{up.isPending ? "Uploading…" : "Upload files"}</button>
          {up.isPending && progress !== null && (
            <label className="flex items-center gap-2 text-sm">Upload progress
              <progress value={progress} max={100} className="w-48" /> <span className="tabular-nums">{progress}%</span></label>
          )}
          {!ready && !up.isPending && <span className="text-sm text-slate-600">Choose all five files to continue.</span>}
        </div>
      </form>

      {up.isError && <div className="mt-4"><ErrorBox error={up.error} /></div>}

      {batchId !== undefined && (
        <div className="mt-6">
          <h2 className="text-lg font-semibold">Validation summary <span className="font-normal text-slate-600">· batch {batchId}<StubTag path={`/batches/${batchId}/summary`} /></span></h2>
          {summary.isPending && <Loading what="Reading the validation report" />}
          {summary.isError && <ErrorBox error={summary.error} />}
          {summary.data && (Object.keys(summary.data.files).length === 0
            ? <Empty>No file report was returned.</Empty>
            : <div className="mt-2 grid gap-3">{ZONES.map((z) => summary.data.files[z.field] && <FileSummary key={z.field} name={z.field} report={summary.data.files[z.field]} />)}</div>)}
          <div className="mt-4 flex items-center gap-3">
            <button className={btnPrimary} onClick={() => run.mutate()} disabled={run.isPending || summary.isPending}>
              {run.isPending ? "Reconciling…" : "Run reconciliation"}
            </button>
            {run.isError && <span role="alert" className="text-sm text-red-800">{errorMessage(run.error)}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
