import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { ApiError, api, downloadUrl, type VendorListStatus, type VendorPreview, type VendorRow } from "../api/client";
import { formatDateTime } from "../lib/format";
import { Badge, DownloadLink, ErrorBox, Loading, Modal, Spinner, btn, btnPrimary, card, focusRing, input, sectionTitle, td, th } from "./ui";

export const VENDOR_LIST_KEY = ["vendor-list"] as const;
export const useVendorListStatus = () => useQuery({ queryKey: VENDOR_LIST_KEY, queryFn: api.vendorListStatus });

const MAX_MB = 20; // mirrors the server's MAX_UPLOAD_MB default; the server still enforces it
const PAGE = 50;
const SHOWN = 200; // rows listed per diff category in the preview

const FileIcon = ({ className = "" }: { className?: string }) => (
  <svg aria-hidden viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 11a4 4 0 100-8 4 4 0 000 8zM21 21v-2a4 4 0 00-3-3.87M17 3.13a4 4 0 010 7.75" />
  </svg>
);

// ---------------------------------------------------------------------------------------------------------------------
// The status card on the Upload page

export function VendorListCard() {
  const status = useVendorListStatus();
  const [open, setOpen] = useState<null | "edit" | "reupload" | "history">(null);
  const [notice, setNotice] = useState("");
  const close = (message?: string) => { setOpen(null); if (message) setNotice(message); };
  const s = status.data;

  return (
    <section aria-labelledby="vendor-list-title" className={`${card} animate-fade-up p-5`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-700"><FileIcon className="h-5 w-5" /></span>
          <div>
            <h2 id="vendor-list-title" className={sectionTitle}>Vendors list</h2>
            <p className="text-xs text-slate-500">Stored once and used for every run, by every user.</p>
          </div>
        </div>
        {s && <Badge label={s.exists ? "Already uploaded" : "Not uploaded yet"} tone={s.exists ? "green" : "amber"} />}
      </div>

      {status.isPending && <Loading what="Loading the vendors list" />}
      {status.isError && <div className="mt-4"><ErrorBox error={status.error} /></div>}

      {s && s.exists && (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
            {([
              ["File name", s.file_name ?? ""], ["Last updated", formatDateTime(s.updated_at)],
              ["Updated by", s.updated_by ?? ""], ["Total vendors", s.total.toLocaleString("en-IN")],
            ] as const).map(([k, v]) => (
              <div key={k} className="min-w-0 rounded-xl bg-slate-50 px-3 py-2">
                <dt className="text-xs text-slate-500">{k}</dt>
                <dd className="truncate font-medium text-slate-900" title={v}>{v}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button type="button" className={btn} onClick={() => setOpen("edit")}>View / Edit</button>
            <button type="button" className={btn} onClick={() => setOpen("reupload")}>Re-upload</button>
            <button type="button" className={`${focusRing} rounded-md px-2 py-1 text-sm text-indigo-700 hover:underline`} onClick={() => setOpen("history")}>
              Version history <span className="tabular-nums text-slate-500">(v{s.version})</span>
            </button>
          </div>
        </>
      )}

      {s && !s.exists && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="font-medium text-amber-900">No vendors list yet</p>
          <p className="mt-1 text-sm text-amber-900/80">
            Upload your vendors list (Party Name and Email id) once. Until it is there, a reconciliation run can't start.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button type="button" className={btnPrimary} onClick={() => setOpen("reupload")}>Upload vendors list</button>
            <DownloadLink href={downloadUrl.sample("vendors")}>Sample format</DownloadLink>
          </div>
        </div>
      )}

      {notice && (
        <p role="status" className="mt-3 flex animate-fade-in items-center justify-between gap-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200">
          {notice}
          <button type="button" aria-label="Dismiss" className={`${focusRing} rounded px-1 text-emerald-700 hover:text-emerald-900`} onClick={() => setNotice("")}>✕</button>
        </p>
      )}

      {open === "edit" && <EditModal onClose={close} />}
      {open === "reupload" && <ReuploadModal status={s} onClose={close} />}
      {open === "history" && <HistoryModal onClose={() => close()} />}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------------------
// View / Edit

type Row = { k: number; id: number | null; party_name: string; email: string; deleted?: boolean };
type RowErrors = { party_name?: string; email?: string };
const ADDRESS = /^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/;
const plain = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

/** The same rules the server enforces (it has the last word): a name, valid email address(es), no name twice. */
function validate(rows: Row[]): Map<number, RowErrors> {
  const errors = new Map<number, RowErrors>();
  const seen = new Map<string, number>();
  rows.forEach((r, i) => {
    if (r.deleted) return;
    const e: RowErrors = {};
    if (!plain(r.party_name)) e.party_name = "Party Name can't be empty";
    else if (seen.has(plain(r.party_name))) e.party_name = `Listed twice (also row ${seen.get(plain(r.party_name))! + 1})`;
    else seen.set(plain(r.party_name), i);
    const parts = r.email.split(/[;,]/).map((p) => p.trim()).filter(Boolean);
    if (!parts.length) e.email = "Email id is empty";
    else if (!parts.every((p) => ADDRESS.test(p))) e.email = "Not a valid email address";
    if (e.party_name || e.email) errors.set(r.k, e);
  });
  return errors;
}

function EditModal({ onClose }: { onClose: (message?: string) => void }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: [...VENDOR_LIST_KEY, "vendors"], queryFn: api.vendorList, staleTime: 0, gcTime: 0 });
  const dirty = useRef(false); // set by the editor; Esc and the Close button ask before throwing edits away
  return (
    <Modal title="Vendors list: view / edit" onClose={() => onClose()} guard={() => !dirty.current || confirm("Discard your unsaved changes?")}>
      {list.isPending && <Loading what="Loading the vendors" />}
      {list.isError && <ErrorBox error={list.error} />}
      {list.data && <Editor key={list.dataUpdatedAt} version={list.data.version} vendors={list.data.vendors} onClose={onClose} dirtyRef={dirty}
        reload={() => qc.invalidateQueries({ queryKey: [...VENDOR_LIST_KEY, "vendors"] })} />}
    </Modal>
  );
}

function Editor({ version, vendors, onClose, reload, dirtyRef }: { version: number; vendors: VendorRow[]; onClose: (message?: string) => void; reload: () => void; dirtyRef: { current: boolean } }) {
  const qc = useQueryClient();
  const nextKey = useRef(vendors.length);
  const original = useMemo(() => new Map(vendors.map((v) => [v.id, v])), [vendors]);
  const [rows, setRows] = useState<Row[]>(() => vendors.map((v, k) => ({ k, id: v.id, party_name: v.party_name, email: v.email ?? "" })));
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [attempted, setAttempted] = useState(false);
  const [serverErrors, setServerErrors] = useState<Map<number, RowErrors>>(new Map());
  const errors = useMemo(() => validate(rows), [rows]);

  const touched = (r: Row) => {
    if (r.id === null) return !r.deleted; // added
    const o = original.get(r.id);
    return !!o && (r.deleted || o.party_name !== r.party_name || (o.email ?? "") !== r.email);
  };
  const added = rows.filter((r) => r.id === null && !r.deleted).length;
  const removed = rows.filter((r) => r.id !== null && r.deleted).length;
  const edited = rows.filter((r) => r.id !== null && !r.deleted && touched(r)).length;
  const dirty = added + removed + edited > 0;
  dirtyRef.current = dirty;

  const save = useMutation({
    mutationFn: (kept: Row[]) => api.saveVendorList(version, kept.map(({ id, party_name, email }) => ({ id, party_name, email }))),
    onSuccess: (out) => {
      qc.invalidateQueries();
      const q = out.requeued ? ` ${out.requeued} earlier exception${out.requeued > 1 ? "s were" : " was"} queued for email.` : "";
      onClose(`Vendors list saved (version ${out.status.version}, ${out.status.total.toLocaleString("en-IN")} vendors).${q}`);
    },
    onError: (err, kept) => {
      // 422: row-level messages; "row" is the position in what was sent
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
        const m = new Map<number, RowErrors>();
        for (const d of err.detail as { row: number; field?: "party_name" | "email"; message: string }[]) {
          const k = kept[d.row]?.k;
          if (k !== undefined) m.set(k, { ...m.get(k), [d.field ?? "party_name"]: d.message });
        }
        setServerErrors(m);
      }
    },
  });
  const conflict = save.error instanceof ApiError && save.error.status === 409;

  const update = (k: number, patch: Partial<Row>) => {
    save.reset(); setServerErrors(new Map());
    setRows((rs) => rs.map((r) => (r.k === k ? { ...r, ...patch } : r)));
  };
  const addRow = () => {
    save.reset();
    setQuery(""); setPage(0);
    setRows((rs) => [{ k: nextKey.current++, id: null, party_name: "", email: "" }, ...rs]);
  };
  const submit = () => {
    setAttempted(true);
    if (errors.size) { const first = rows.findIndex((r) => errors.has(r.k)); setQuery(""); setPage(Math.floor(first / PAGE)); return; }
    save.mutate(rows.filter((r) => !r.deleted));
  };

  const q = query.trim().toLowerCase();
  const visible = rows.filter((r) => !q || r.party_name.toLowerCase().includes(q) || r.email.toLowerCase().includes(q));
  const pages = Math.max(1, Math.ceil(visible.length / PAGE));
  const shown = visible.slice(Math.min(page, pages - 1) * PAGE, (Math.min(page, pages - 1) + 1) * PAGE);
  const from = visible.length ? Math.min(page, pages - 1) * PAGE + 1 : 0;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <input type="search" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} placeholder="Search Party Name or Email id"
          aria-label="Search vendors" className={`${input} w-full sm:w-72`} />
        <button type="button" className={btn} onClick={addRow}>+ Add vendor</button>
        <span className="ml-auto text-sm text-slate-500" aria-live="polite">
          {rows.filter((r) => !r.deleted).length.toLocaleString("en-IN")} vendors
          {dirty && <> · <span className="text-indigo-700">{[added && `${added} added`, edited && `${edited} edited`, removed && `${removed} removed`].filter(Boolean).join(", ")}</span></>}
        </span>
      </div>

      <div className="mt-3 overflow-x-auto rounded-xl ring-1 ring-slate-200">
        <table className="w-full min-w-[40rem] border-collapse text-sm">
          <thead><tr><th className={`${th} w-12`}>#</th><th className={th}>Party Name</th><th className={th}>Email id</th><th className={`${th} w-24`}><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {shown.map((r) => {
              const err = { ...(attempted ? errors.get(r.k) : undefined), ...serverErrors.get(r.k) };
              const idx = rows.indexOf(r);
              return (
                <tr key={r.k} className={r.deleted ? "bg-rose-50/60" : touched(r) ? "bg-indigo-50/40" : ""}>
                  <td className={`${td} tabular-nums text-slate-500`}>{idx + 1}</td>
                  <td className={td}>
                    <input aria-label={`Party Name, row ${idx + 1}`} value={r.party_name} disabled={r.deleted} aria-invalid={!!err.party_name}
                      onChange={(e) => update(r.k, { party_name: e.target.value })}
                      className={`${input} w-full ${r.deleted ? "line-through" : ""} ${err.party_name ? "border-rose-400" : ""}`} />
                    {err.party_name && <p className="mt-1 text-xs text-rose-700">{err.party_name}</p>}
                  </td>
                  <td className={td}>
                    <input aria-label={`Email id, row ${idx + 1}`} value={r.email} disabled={r.deleted} aria-invalid={!!err.email} inputMode="email"
                      onChange={(e) => update(r.k, { email: e.target.value })}
                      className={`${input} w-full ${r.deleted ? "line-through" : ""} ${err.email ? "border-rose-400" : ""}`} />
                    {err.email && <p className="mt-1 text-xs text-rose-700">{err.email}</p>}
                  </td>
                  <td className={`${td} text-right`}>
                    {r.deleted
                      ? <button type="button" className={`${btn} px-2.5 py-1 text-xs`} onClick={() => update(r.k, { deleted: false })}>Undo</button>
                      : <button type="button" aria-label={`Delete ${r.party_name || `row ${idx + 1}`}`} className={`${btn} px-2.5 py-1 text-xs text-rose-700 hover:border-rose-300 hover:bg-rose-50`}
                          onClick={() => (r.id === null ? setRows((rs) => rs.filter((x) => x.k !== r.k)) : update(r.k, { deleted: true }))}>Delete</button>}
                  </td>
                </tr>
              );
            })}
            {!shown.length && <tr><td colSpan={4} className={`${td} py-8 text-center text-slate-500`}>{q ? "No vendor matches the search." : "No vendors."}</td></tr>}
          </tbody>
        </table>
      </div>

      {visible.length > PAGE && (
        <nav aria-label="Pages" className="flex items-center justify-between gap-3 pt-3 text-sm text-slate-500">
          <span>Showing <b className="font-mono tabular-nums text-slate-800">{from}–{Math.min(from + PAGE - 1, visible.length)}</b> of {visible.length.toLocaleString("en-IN")}</span>
          <span className="flex gap-2">
            <button type="button" className={btn} disabled={page === 0} onClick={() => setPage(page - 1)}>← Previous</button>
            <button type="button" className={btn} disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next →</button>
          </span>
        </nav>
      )}

      <div className="mt-4 space-y-3">
        {attempted && errors.size > 0 && <p role="alert" className="text-sm text-rose-700">Fix the {errors.size} highlighted row{errors.size > 1 ? "s" : ""} before saving.</p>}
        {save.isError && !serverErrors.size && <ErrorBox error={save.error} />}
        {save.isError && serverErrors.size > 0 && <p role="alert" className="text-sm text-rose-700">The server found problems in {serverErrors.size} row{serverErrors.size > 1 ? "s" : ""}; they are marked above. Nothing was saved.</p>}
        {conflict && (
          <button type="button" className={btn} onClick={() => { if (!dirty || confirm("Reload the latest list? Your unsaved changes here will be lost.")) reload(); }}>
            Reload the latest list
          </button>
        )}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button type="button" className={btn} onClick={() => { if (!dirty || confirm("Discard your unsaved changes?")) { dirtyRef.current = false; onClose(); } }}>Cancel</button>
          <button type="button" className={btnPrimary} disabled={!dirty || save.isPending || conflict} onClick={submit}>
            {save.isPending ? <><Spinner />Saving…</> : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------------
// Re-upload with preview and confirmation

function checkFile(f: File): string | null {
  if (!/\.(xlsx|xls)$/i.test(f.name)) return "Only .xlsx or .xls files are accepted";
  if (f.size > MAX_MB * 1024 * 1024) return `File is over ${MAX_MB} MB`;
  return null;
}

function ReuploadModal({ status, onClose }: { status: VendorListStatus | undefined; onClose: (message?: string) => void }) {
  const qc = useQueryClient();
  const first = !status?.exists;
  const [file, setFile] = useState<File>();
  const [problem, setProblem] = useState<string>();
  const [password, setPassword] = useState("");
  const [locked, setLocked] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [over, setOver] = useState(false);

  const preview = useMutation({
    mutationFn: (f: File) => api.previewVendorList(f, password || undefined),
    onError: (err) => setLocked(err instanceof ApiError && Array.isArray(err.detail) && err.detail.some((d) => d.password_required)),
    onSuccess: () => setLocked(false),
  });
  const replace = useMutation({
    mutationFn: (p: VendorPreview) => api.replaceVendorList(file!, p.base_version, password || undefined),
    onSuccess: (out) => {
      qc.invalidateQueries();
      const q = out.requeued ? ` ${out.requeued} earlier exception${out.requeued > 1 ? "s were" : " was"} queued for email.` : "";
      onClose(`${first ? "Vendors list uploaded" : "Vendors list replaced"} (version ${out.status.version}, ${out.status.total.toLocaleString("en-IN")} vendors).${q}`);
    },
  });

  const pick = (f: File | undefined) => {
    preview.reset(); replace.reset(); setConfirming(false); setLocked(false);
    const bad = f ? checkFile(f) : null;
    setProblem(bad ?? undefined);
    setFile(f && !bad ? f : undefined);
    if (f && !bad) preview.mutate(f);
  };
  const p = preview.data;
  const changes = p ? p.new.length + p.removed.length + p.changed.length : 0;
  const conflict = replace.error instanceof ApiError && replace.error.status === 409;

  return (
    <Modal title={first ? "Upload vendors list" : "Re-upload vendors list"} onClose={() => onClose()}>
      <label htmlFor="vendor-file" onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); }}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 border-dashed p-6 text-center transition has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-indigo-200 ${
          over ? "border-indigo-500 bg-indigo-50" : file ? "border-emerald-300 border-solid bg-emerald-50/60" : "border-slate-300 hover:border-indigo-300 hover:bg-slate-50"}`}>
        <input id="vendor-file" type="file" accept=".xlsx,.xls" className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
        <span className="font-semibold text-slate-900">{file ? file.name : "Choose the vendors Excel file"}</span>
        <span className="text-xs text-slate-500">{file ? `${(file.size / 1024).toFixed(0)} KB · click to choose another` : `Drag it here, or click to browse. .xlsx or .xls, up to ${MAX_MB} MB. Columns: Party Name (or Vendor Name), Email id.`}</span>
      </label>
      <div className="mt-2 text-xs"><DownloadLink href={downloadUrl.sample("vendors")}>Sample format</DownloadLink></div>
      {problem && <p role="alert" className="mt-3 text-sm text-rose-700">{problem}</p>}

      {locked && file && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="grow sm:max-w-xs">
            <label htmlFor="vendor-pw" className="text-xs font-medium text-slate-500">Password for {file.name}</label>
            <input id="vendor-pw" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} className={`${input} mt-1 w-full`} />
          </div>
          <button type="button" className={btn} disabled={!password || preview.isPending} onClick={() => preview.mutate(file)}>Open file</button>
        </div>
      )}

      {preview.isPending && <Loading what="Reading the file" />}
      {preview.isError && !locked && (
        <div className="mt-3">
          <ErrorBox error={preview.error} />
          <p className="mt-2 text-sm text-slate-500">{first ? "Nothing was saved." : "The current vendors list was not changed."}</p>
        </div>
      )}
      {preview.isError && locked && <div className="mt-3"><ErrorBox error={preview.error} /></div>}

      {p && (
        <div className="mt-5 animate-fade-up">
          <h3 className="font-semibold text-slate-900">What this file changes</h3>
          <p className="text-sm text-slate-500">
            {p.file_name} has {p.total.toLocaleString("en-IN")} vendors{status?.exists ? `; the stored list has ${status.total.toLocaleString("en-IN")}` : ""}. Nothing is saved until you confirm.
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([["New", p.new.length, "text-emerald-800 bg-emerald-50"], ["Removed", p.removed.length, p.removed.length ? "text-rose-800 bg-rose-50" : "bg-slate-50"],
              ["Changed", p.changed.length, p.changed.length ? "text-amber-900 bg-amber-50" : "bg-slate-50"], ["Unchanged", p.unchanged, "bg-slate-50"]] as const).map(([k, v, tone]) => (
              <div key={k} className={`rounded-xl px-3 py-2 ${v || k === "Unchanged" ? tone : "bg-slate-50"}`}>
                <dt className="text-xs text-slate-500">{k}</dt>
                <dd className="font-mono text-lg font-semibold tabular-nums text-slate-900">{v.toLocaleString("en-IN")}</dd>
              </div>
            ))}
          </dl>

          <DiffList title="New vendors" rows={p.new.map((v) => [v.party_name, v.email ?? ""])} />
          <DiffList title="Removed vendors (no longer matched or emailed)" rows={p.removed.map((v) => [v.party_name, v.email ?? ""])} />
          <DiffList title="Changed vendors" head={["Party Name", "Old email", "New email"]}
            rows={p.changed.map((c) => [c.party_name === c.old_party_name ? c.party_name : `${c.old_party_name} → ${c.party_name}`, c.old_email ?? "", c.new_email ?? ""])} />
          {p.issues.length > 0 && (
            <details className="mt-3 text-sm">
              <summary className={`cursor-pointer ${focusRing}`}>{p.issues.length} row{p.issues.length > 1 ? "s" : ""} to check in the file</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600">
                {p.issues.slice(0, 50).map((i, n) => <li key={n}>{i.sheet} row {i.row}: {i.message} <span className="text-slate-400">({i.rejected ? "skipped" : "kept, email flagged"})</span></li>)}
              </ul>
              {p.issues.length > 50 && <p className="mt-1 text-slate-500">…and {p.issues.length - 50} more.</p>}
            </details>
          )}

          {!changes && !first && <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">This file is the same as the stored list. There is nothing to replace.</p>}

          {confirming ? (
            <div role="alertdialog" aria-label="Confirm replacing the vendors list" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4">
              <p className="font-medium text-amber-950">{first ? "Save this as the vendors list?" : "Replace the stored vendors list?"}</p>
              <p className="mt-1 text-sm text-amber-950/80">
                {first
                  ? `${p.total.toLocaleString("en-IN")} vendors will be stored and used for every run by every user.`
                  : <>The list changes for every user and every future run: {p.new.length} added, {p.removed.length} removed, {p.changed.length} updated.
                    Removed vendors stop being matched or emailed. This is recorded in the version history.</>}
              </p>
              {replace.isError && <div className="mt-3"><ErrorBox error={replace.error} /></div>}
              <div className="mt-3 flex flex-wrap justify-end gap-2">
                {conflict
                  ? <button type="button" className={btn} onClick={() => { setConfirming(false); replace.reset(); file && preview.mutate(file); }}>Review again</button>
                  : <>
                    <button type="button" className={btn} disabled={replace.isPending} onClick={() => setConfirming(false)}>Back</button>
                    <button type="button" className={btnPrimary} disabled={replace.isPending} onClick={() => replace.mutate(p)}>
                      {replace.isPending ? <><Spinner />Saving…</> : first ? "Yes, save the list" : "Yes, replace the list"}
                    </button></>}
              </div>
            </div>
          ) : (
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button type="button" className={btn} onClick={() => onClose()}>Cancel</button>
              <button type="button" className={btnPrimary} disabled={!first && !changes} onClick={() => setConfirming(true)}>
                {first ? "Save as vendors list…" : "Replace list…"}
              </button>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function DiffList({ title, rows, head = ["Party Name", "Email id"] }: { title: string; rows: string[][]; head?: string[] }) {
  if (!rows.length) return null;
  return (
    <details className="mt-3 text-sm" open={rows.length <= 5}>
      <summary className={`cursor-pointer font-medium text-slate-800 ${focusRing}`}>{title} ({rows.length.toLocaleString("en-IN")})</summary>
      <div className="mt-2 max-h-56 overflow-auto rounded-xl ring-1 ring-slate-200">
        <table className="w-full border-collapse text-sm">
          <thead><tr>{head.map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
          <tbody>{rows.slice(0, SHOWN).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={td}>{c}</td>)}</tr>)}</tbody>
        </table>
      </div>
      {rows.length > SHOWN && <p className="mt-1 text-slate-500">…and {(rows.length - SHOWN).toLocaleString("en-IN")} more.</p>}
    </details>
  );
}

// ---------------------------------------------------------------------------------------------------------------------
// Version history

const ACTION: Record<string, string> = { UPLOAD: "Uploaded file", EDIT: "Edited in the app", EMAIL_FIX: "Email fixed" };

function HistoryModal({ onClose }: { onClose: () => void }) {
  const history = useQuery({ queryKey: [...VENDOR_LIST_KEY, "history"], queryFn: api.vendorListHistory, staleTime: 0 });
  return (
    <Modal title="Vendors list: version history" onClose={onClose}>
      {history.isPending && <Loading what="Loading the history" />}
      {history.isError && <ErrorBox error={history.error} />}
      {history.data && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <thead><tr><th className={th}>Version</th><th className={th}>When</th><th className={th}>User</th><th className={th}>Action</th><th className={th}>Details</th></tr></thead>
            <tbody>
              {history.data.map((h) => (
                <tr key={h.id}>
                  <td className={`${td} font-mono tabular-nums`}>v{h.version}</td>
                  <td className={`${td} whitespace-nowrap`}>{formatDateTime(h.logged_at)}</td>
                  <td className={td}>{h.user}</td>
                  <td className={`${td} whitespace-nowrap`}>{ACTION[h.action] ?? h.action}</td>
                  <td className={td}>
                    {h.file_name && <span className="block truncate text-slate-900" title={h.file_name}>{h.file_name}</span>}
                    <span className="text-slate-500">
                      {[h.added && `${h.added} added`, h.removed && `${h.removed} removed`, h.changed && `${h.changed} changed`].filter(Boolean).join(", ") || "no vendor changes"}
                      {` · ${h.vendor_count.toLocaleString("en-IN")} vendors`}
                    </span>
                    {h.details && (h.details.added?.length || h.details.removed?.length || h.details.changed?.length) ? (
                      <details className="mt-1">
                        <summary className={`cursor-pointer text-xs text-indigo-700 ${focusRing}`}>Names</summary>
                        <div className="mt-1 text-xs text-slate-600">
                          {(["added", "removed", "changed"] as const).map((k) => h.details?.[k]?.length ? <p key={k}><b className="capitalize">{k}:</b> {h.details[k]!.slice(0, 30).join("; ")}{h.details[k]!.length > 30 ? `; …and ${h.details[k]!.length - 30} more` : ""}</p> : null)}
                        </div>
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))}
              {!history.data.length && <tr><td colSpan={5} className={`${td} py-8 text-center text-slate-500`}>No changes recorded yet.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
