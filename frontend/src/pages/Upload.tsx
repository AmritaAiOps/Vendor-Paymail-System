import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, UPLOAD_FIELDS, api, downloadUrl, errorMessage, type FileReport, type UploadField } from "../api/client";
import { DownloadLink, Empty, ErrorBox, Loading, Spinner, btn, btnPrimary, card, focusRing, num, pageTitle, sectionTitle, td, th } from "../components/ui";
import { setLastBatch } from "../lib/lastBatch";

const ZONES: { field: UploadField; label: string }[] = [
  { field: "consolidated", label: "Consolidated Report" },
  { field: "bank", label: "Bank Statement" },
  { field: "gdn", label: "GDN Report" },
  { field: "tds", label: "TDS Excel" },
  { field: "vendors", label: "Vendors List" },
];
// fallback when the headers can't be read; a file matching neither is added to its own card by hand
const BULK_HINTS: [UploadField, RegExp][] = [
  ["consolidated", /consolidat/i], ["bank", /bank/i], ["gdn", /gdn/i], ["tds", /tds/i], ["vendors", /vendor/i],
];
const MAX_MB = 20; // shortcut: mirrors the server's MAX_UPLOAD_MB default; the server still enforces it, revisit if that setting changes

function check(f: File): string | null {
  if (!/\.(xlsx|xls)$/i.test(f.name)) return "Only .xlsx or .xls files are accepted";
  if (f.size > MAX_MB * 1024 * 1024) return `File is over ${MAX_MB} MB`;
  return null;
}

const FileIcon = ({ className = "" }: { className?: string }) => (
  <svg aria-hidden viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" />
  </svg>
);

function Zone({ field, label, file, error, onPick }: { field: UploadField; label: string; file?: File; error?: string; onPick: (f: File | undefined) => void }) {
  const [over, setOver] = useState(false);
  const id = `file-${field}`;
  const state = over ? "border-indigo-500 bg-indigo-50 scale-[1.02] shadow-lg shadow-indigo-500/10"
    : error ? "border-rose-300 bg-rose-50"
    : file ? "border-emerald-300 border-solid bg-emerald-50/60"
    : "border-slate-300 bg-white/70 hover:border-indigo-300 hover:bg-white hover:shadow-md";
  return (
    // The whole card is the file picker's label: click anywhere, or drop a file on it
    <label htmlFor={id}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onPick(e.dataTransfer.files[0]); }}
      className={`group relative flex flex-1 cursor-pointer flex-col gap-3 rounded-2xl border-2 border-dashed p-5 transition duration-200 has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-indigo-200 ${state}`}
    >
      <input id={id} type="file" accept=".xlsx,.xls" aria-describedby={`${id}-msg`} className="sr-only"
        onChange={(e) => { onPick(e.target.files?.[0]); e.target.value = ""; }} />
      <div className="flex items-center gap-3">
        <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl transition duration-200 ${
          file ? "bg-emerald-500 text-white " : "bg-indigo-50 text-indigo-700 group-hover:scale-110 group-hover:bg-indigo-100"}`}>
          {file
            ? <svg aria-hidden viewBox="0 0 20 20" className="h-5 w-5 animate-pop" fill="currentColor"><path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 111.4-1.4L8 12.58l7.3-7.3a1 1 0 011.4 0z" clipRule="evenodd" /></svg>
            : <FileIcon className="h-5 w-5" />}
        </span>
        <span className="min-w-0">
          <span className="block font-semibold text-slate-900">{label}</span>
          <span className="block text-xs text-slate-500">{over ? "Drop it here" : "Drag a file here, or click to browse"}</span>
        </span>
      </div>
      <p id={`${id}-msg`} aria-live="polite" className="min-h-9 text-sm">
        {error ? <span className="text-rose-700">{error}</span>
          : file ? (
            <span className="flex animate-fade-in items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-emerald-200">
              <span className="min-w-0 truncate font-medium text-slate-700" title={file.name}>{file.name}</span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="text-xs tabular-nums text-slate-500">{(file.size / 1024).toFixed(0)} KB</span>
                <button type="button" aria-label={`Remove ${file.name}`} onClick={(e) => { e.preventDefault(); onPick(undefined); }}
                  className={`grid h-6 w-6 place-items-center rounded-full text-slate-500 transition hover:bg-rose-50 hover:text-rose-700 ${focusRing}`}>✕</button>
              </span>
            </span>)
          : <span className="text-xs text-slate-500">.xlsx or .xls, up to {MAX_MB} MB</span>}
      </p>
    </label>
  );
}

const FILE_LABEL: Record<string, string> = Object.fromEntries(ZONES.map((z) => [z.field, z.label]));

function FileSummary({ name, report }: { name: string; report: FileReport }) {
  const shown = report.issues.slice(0, 50);
  return (
    <section className={`${card} animate-fade-up p-4`}>
      <h3 className="flex flex-wrap items-center gap-2 font-semibold">
        <FileIcon className="h-4 w-4 text-indigo-600" />{FILE_LABEL[name] ?? name}
        <span className="truncate text-sm font-normal text-slate-500">{report.file_name}</span>
      </h3>
      <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {([["Read", report.rows_read], ["Kept", report.rows_kept], ["Skipped", report.rows_skipped], ["Rejected", report.rows_rejected]] as const).map(([k, v]) => (
          <div key={k} className={`rounded-xl px-3 py-2 ${k === "Rejected" && v > 0 ? "bg-rose-50 text-rose-800" : "bg-slate-50"}`}>
            <dt className="text-xs text-slate-500">{k}</dt>
            <dd className="font-mono text-lg font-semibold tabular-nums text-slate-900">{v.toLocaleString("en-IN")}</dd>
          </div>
        ))}
      </dl>
      {report.issues.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className={`cursor-pointer ${focusRing}`}>{report.issues.length} row issue{report.issues.length > 1 ? "s" : ""}</summary>
          <table className="mt-2 w-full border-collapse overflow-hidden rounded-xl text-sm ring-1 ring-slate-200">
            <thead><tr><th className={th}>Sheet</th><th className={`${th} ${num}`}>Row</th><th className={th}>Outcome</th><th className={th}>Message</th></tr></thead>
            <tbody>
              {shown.map((i, n) => (
                <tr key={n}><td className={td}>{i.sheet}</td><td className={`${td} ${num}`}>{i.row}</td>
                  <td className={td}>{i.rejected ? "Rejected" : "Kept, check"}</td><td className={td}>{i.message}</td></tr>
              ))}
            </tbody>
          </table>
          {report.issues.length > shown.length && <p className="mt-1 text-slate-500">…and {report.issues.length - shown.length} more.</p>}
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
  // Files the server said are password-protected (422 with password_required); each gets its own password box
  const [locked, setLocked] = useState<Partial<Record<UploadField, boolean>>>({});
  const [passwords, setPasswords] = useState<Partial<Record<UploadField, string>>>({});

  const pick = (field: UploadField, f: File | undefined) => {
    up.reset(); // a changed file set is a new batch; the old one stays on the server unreconciled
    const problem = f ? check(f) : null;
    setErrors((e) => ({ ...e, [field]: problem ?? undefined }));
    setFiles((s) => ({ ...s, [field]: f && !problem ? f : undefined }));
  };
  // Several files at once: each goes to the card its name points at (e.g. "Bank Statement.xlsx" -> Bank Statement)
  const [bulkNote, setBulkNote] = useState("");
  const pickMany = async (list: FileList | File[]) => {
    const unknown: string[] = [];
    const all = Array.from(list);
    // the server reads the column headers; the file name is the fallback (protected files, or no server answer)
    const byHeaders = await api.detectFiles(all).catch(() => ({} as Record<string, UploadField | null>));
    for (const f of all) {
      const field = byHeaders[f.name] ?? BULK_HINTS.find(([, re]) => re.test(f.name))?.[0];
      if (field) pick(field, f); else unknown.push(f.name);
    }
    setBulkNote(unknown.length ? `Couldn't tell which card these belong to, add them to their card: ${unknown.join(", ")}` : "");
  };
  const ready = UPLOAD_FIELDS.every((f) => files[f]);
  const qc = useQueryClient();

  const up = useMutation({
    mutationFn: () => api.uploadBatch(files as Record<UploadField, File>, passwords, setProgress),
    onMutate: () => setProgress(0),
    onSuccess: (b) => setLastBatch(b.id),
    onError: (err) => {
      if (!(err instanceof ApiError) || !Array.isArray(err.detail)) return;
      const need = err.detail.filter((d) => d.password_required).map((d) => [d.file, true]);
      if (need.length) setLocked((l) => ({ ...l, ...Object.fromEntries(need) }));
    },
  });
  const batchId = up.data?.id;
  const summary = useQuery({ queryKey: ["summary", batchId], queryFn: () => api.batchSummary(batchId!), enabled: batchId !== undefined });
  const run = useMutation({
    mutationFn: () => api.reconcile(batchId!),
    // Reconciling changes every list (results, queue, exceptions, review), so drop all cached data
    onSuccess: () => qc.invalidateQueries().then(() => navigate("/results")),
  });

  const [round, setRound] = useState(0); // remounts the file inputs so Reset really empties them
  const reset = () => {
    setFiles({}); setErrors({}); setLocked({}); setPasswords({}); setProgress(null); up.reset(); run.reset(); setRound((r) => r + 1);
  };
  // 409 from the server: the same rows were uploaded before; its message names that batch
  const duplicateOf = up.error instanceof ApiError && up.error.status === 409 ? /batch (\d+)/.exec(errorMessage(up.error))?.[1] : undefined;

  const readyCount = UPLOAD_FIELDS.filter((f) => files[f]).length;
  const step = batchId === undefined ? 1 : 2;

  return (
    <section>
      <h1 className={pageTitle}>Upload</h1>
      <p className="mt-1 text-slate-500">Add the five Excel files for one reconciliation run.</p>

      <ol className="mt-6 flex flex-wrap items-center gap-2 text-sm" aria-label="Steps">
        {["Add files", "Check the files", "Reconcile"].map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <span aria-current={i + 1 === step ? "step" : undefined}
              className={`flex items-center gap-2 rounded-full px-3 py-1 font-medium transition ${
                i + 1 < step ? "bg-emerald-50 text-emerald-700" : i + 1 === step ? "bg-indigo-600 text-white shadow-[0_1px_12px_rgba(99,102,241,0.25)]" : "bg-slate-50 text-slate-500 ring-1 ring-slate-200"}`}>
              <span className="tabular-nums">{i + 1 < step ? "✓" : i + 1}</span>{label}
            </span>
            {i < 2 && <span aria-hidden className="h-px w-6 bg-slate-200" />}
          </li>
        ))}
      </ol>

      <form key={round} className="mt-6" onSubmit={(e) => { e.preventDefault(); up.mutate(); }}>
        <label htmlFor="file-all"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); pickMany(e.dataTransfer.files); }}
          className="mb-4 flex cursor-pointer flex-col items-center gap-1 rounded-2xl border-2 border-dashed border-indigo-300 bg-indigo-50/50 p-6 text-center transition hover:bg-indigo-50 has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-indigo-200">
          <input id="file-all" type="file" multiple accept=".xlsx,.xls" className="sr-only"
            onChange={(e) => { pickMany(e.target.files ?? []); e.target.value = ""; }} />
          <span className="font-semibold text-slate-900">Select or drop all five files at once</span>
          <span className="text-xs text-slate-500">Each file goes to its card by its column headers, or by its name (consolidated, bank, GDN, TDS, vendors)</span>
          {bulkNote && <span role="alert" className="mt-1 text-sm text-rose-700">{bulkNote}</span>}
        </label>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ZONES.map((z, i) => (
            <div key={z.field} className="flex animate-fade-up flex-col" style={{ animationDelay: `${i * 60}ms` }}>
              <Zone {...z} file={files[z.field]} error={errors[z.field]} onPick={(f) => pick(z.field, f)} />
              <div className="mt-1 px-1 text-xs"><DownloadLink href={downloadUrl.sample(z.field)}>Sample format</DownloadLink></div>
              {locked[z.field] && (
                // Outside the Zone: that card is the file picker's label, so a click inside it would open the picker
                <div className="mt-2 animate-fade-in">
                  <label htmlFor={`pw-${z.field}`} className="text-xs font-medium text-slate-500">Password for the {z.label}</label>
                  <input id={`pw-${z.field}`} type="password" autoComplete="off" required value={passwords[z.field] ?? ""}
                    onChange={(e) => { up.reset(); setPasswords((p) => ({ ...p, [z.field]: e.target.value })); }}
                    className={`mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm ${focusRing}`}
                    placeholder="This file is password-protected" />
                </div>
              )}
            </div>
          ))}
          <div className={`${card} flex animate-fade-up flex-col justify-between gap-4 p-5 sm:col-span-2 lg:col-span-1`} style={{ animationDelay: "300ms" }}>
            <div>
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-semibold text-slate-900">Files ready</span>
                <span className="tabular-nums text-slate-500">{readyCount} of {UPLOAD_FIELDS.length}</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400 transition-all duration-500 ease-out"
                  style={{ width: `${(readyCount / UPLOAD_FIELDS.length) * 100}%` }} />
              </div>
            </div>
            {up.isPending && progress !== null ? (
              <div role="progressbar" aria-label="Upload progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} className="text-sm">
                <div className="flex justify-between text-slate-500"><span className="flex items-center gap-2"><Spinner className="h-3.5 w-3.5 text-indigo-600" />Uploading</span><span className="tabular-nums">{progress}%</span></div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-indigo-500 transition-all duration-300" style={{ width: `${progress}%` }} />
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">{ready ? "All set. Upload to check the files." : "Choose all five files to continue."}</p>
            )}
            <div className="flex gap-2">
              <button type="submit" className={`${btnPrimary} flex-1 py-2.5`} disabled={!ready || up.isPending || up.isSuccess}>
                {up.isPending ? <><Spinner />Uploading…</> : up.isSuccess ? "Uploaded ✓" : "Upload files"}
              </button>
              <button type="button" className={`${btn} py-2.5`} onClick={reset} disabled={up.isPending || run.isPending || (readyCount === 0 && !up.isSuccess && !up.isError)}
                title="Clear the chosen files and start a new upload">
                Reset
              </button>
            </div>
          </div>
        </div>
      </form>

      {up.isError && (
        <div className="mt-4">
          <ErrorBox error={up.error} />
          {duplicateOf && <Link to="/results" className={`${btn} mt-2`}>Open results →</Link>}
        </div>
      )}

      {batchId !== undefined && (
        <div className="mt-10 animate-fade-up">
          <h2 className={sectionTitle}>Validation summary <span className="font-normal text-slate-500">· batch {batchId}</span></h2>
          {summary.isPending && <Loading what="Reading the validation report" />}
          {summary.isError && <ErrorBox error={summary.error} />}
          {summary.data && (Object.keys(summary.data.files).length === 0
            ? <Empty>No file report was returned.</Empty>
            : <div className="mt-3 grid gap-3 lg:grid-cols-2">{ZONES.map((z) => summary.data.files[z.field] && <FileSummary key={z.field} name={z.field} report={summary.data.files[z.field]} />)}</div>)}
          <div className="mt-6 flex items-center gap-3">
            <button className={`${btnPrimary} px-5 py-2.5`} onClick={() => run.mutate()} disabled={run.isPending || summary.isPending}>
              {run.isPending ? <><Spinner />Reconciling…</> : "Run reconciliation →"}
            </button>
            {run.isError && <span role="alert" className="text-sm text-rose-700">{errorMessage(run.error)}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
