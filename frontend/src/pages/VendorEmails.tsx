import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadUrl, errorMessage, type QueueItemOut, type QueueStatus, type ResultFilters, type ResultOut, type ResultStatus } from "../api/client";
import { EmailFrame } from "../components/EmailFrame";
import { btn, btnPrimary, card, DownloadLink, Empty, ErrorBox, input, Loading, Modal, Pager, pageTitle, QUEUE_BADGE, RESULT_BADGE, Spinner, StatusBadge } from "../components/ui";
import { useMe } from "../lib/useAuth";
import { formatDate, formatDateTime, formatMoney } from "../lib/format";

function Preview({ item, onClose }: { item: QueueItemOut; onClose: () => void }) {
  const q = useQuery({ queryKey: ["preview", item.id], queryFn: () => api.emailPreview(item.id) });
  return (
    <Modal title={`Email to ${item.vendor_name}`} onClose={onClose}>
      {q.isPending && <Loading what="Rendering the email" />}
      {q.isError && <ErrorBox error={q.error} />}
      {q.data && <EmailFrame subject={q.data.subject} to={item.to_email} html={q.data.html} />}
    </Modal>
  );
}

/** Stage 2: schedules every draft; the daily job then sends each on its T+2 date. Admin only. */
function SendAll({ drafts }: { drafts: number }) {
  const qc = useQueryClient();
  const run = useMutation({ mutationFn: api.scheduleAll, onSuccess: () => qc.invalidateQueries({ queryKey: ["queue"] }) });
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button className={btnPrimary} disabled={run.isPending || drafts === 0}
        onClick={() => confirm(`Schedule ${drafts} draft email(s)? Each goes out on its send date (T+2); any past that date go on the next daily run.`) && run.mutate()}>
        {run.isPending ? <><Spinner />Scheduling…</> : `Send all${drafts ? ` (${drafts})` : ""}`}
      </button>
      <span role="status" className="text-sm text-slate-500">
        {run.data ? `${run.data.scheduled} email(s) scheduled.` : "Drafts are not sent until you choose Send all."}
      </span>
      {run.isError && <span role="alert" className="text-sm text-rose-700">{errorMessage(run.error)}</span>}
    </div>
  );
}

/** Sends one email at once, ignoring its T+2 date. Admin only. */
function SendNow({ item, dryRun }: { item: QueueItemOut; dryRun: boolean }) {
  const qc = useQueryClient();
  const run = useMutation({ mutationFn: () => api.sendNow(item.id), onSuccess: () => qc.invalidateQueries() });
  return (
    <>
      <button className={btnPrimary} disabled={run.isPending}
        onClick={() => confirm(dryRun ? "Dry run is on: the email is logged, not sent. Continue?" : `Send the email to ${item.vendor_name} (${item.to_email ?? "no address"}) now, ahead of its send date?`) && run.mutate()}>
        {run.isPending ? <><Spinner />Sending…</> : <>Send now<span className="sr-only"> to {item.vendor_name}</span></>}
      </button>
      {run.isError && <span role="alert" className="text-xs text-rose-700">{errorMessage(run.error)}</span>}
    </>
  );
}

/** Runs the daily job now. "Send due" = send date today or earlier; "Send all now" ignores the T+2 date (for testing). Admin only. */
function SendDue({ dryRun }: { dryRun: boolean }) {
  const qc = useQueryClient();
  const run = useMutation({ mutationFn: (ignoreDate: boolean) => api.runNow(ignoreDate), onSuccess: () => qc.invalidateQueries() });
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button className={btn} disabled={run.isPending}
        onClick={() => confirm(dryRun ? "Dry run is on: emails are logged, not sent. Continue?" : "Send every email due today or earlier to the vendors now?") && run.mutate(false)}>
        {run.isPending ? <><Spinner />Sending…</> : "Send due emails now"}
      </button>
      <button className={btnPrimary} disabled={run.isPending}
        onClick={() => confirm(dryRun ? "Dry run is on: emails are logged, not sent. Continue?" : "Send EVERY scheduled email now, even those not due until a later date? Check TEST_RECIPIENT if this is a test.") && run.mutate(true)}>
        Send all scheduled now
      </button>
      <span role="status" className="text-sm text-slate-500">
        {run.data ? `${run.data.sent} sent, ${run.data.dry_run} dry run, ${run.data.failed} failed, ${run.data.not_sent} not sent.` : dryRun ? "Dry run is on: nothing is really sent." : ""}
      </span>
      {run.isError && <span role="alert" className="text-sm text-rose-700">{errorMessage(run.error)}</span>}
    </div>
  );
}

const PAGE = 10; // vendors per page
const FETCH = 500; // the results endpoint's max page size

// shortcut: fetches every result row and groups in the browser (fine to a few thousand rows);
// move to server-side paging once results can hold far more than ~10,000 rows
async function fetchAll(f: ResultFilters): Promise<ResultOut[]> {
  const out: ResultOut[] = [];
  for (;;) {
    const { rows, total } = await api.resultsPage(f, FETCH, out.length);
    out.push(...rows);
    if (rows.length === 0 || out.length >= total) return out;
  }
}

type Group = { key: string; vendor: string; email: QueueItemOut | null; rows: ResultOut[] };

// compact, left-aligned cells so the table fits the page without side scrolling
const cell = "border-b border-slate-200 px-2 py-2 text-left align-top text-slate-700 break-words";
const head = "border-b border-slate-200 bg-slate-50 px-2 py-2 text-left text-xs font-medium text-slate-500";
const mono = "font-mono tabular-nums";

/** One block per vendor: its email (to, send date, status, preview) with the invoices that email covers. */
export default function VendorEmails() {
  const isAdmin = useMe().data?.is_admin ?? false;
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const drafts = useQuery({ queryKey: ["queue", "DRAFT", undefined], queryFn: () => api.emailQueue({ status: "DRAFT" }) });
  const [queueStatus, setQueueStatus] = useState<QueueStatus | "">("");
  const [status, setStatus] = useState<ResultStatus | "">("");
  const [vendor, setVendor] = useState("");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<QueueItemOut | null>(null);
  const filters: ResultFilters = { status: status || undefined, vendor, q: search, date_from: dateFrom, date_to: dateTo };
  const results = useQuery({ queryKey: ["results", filters], queryFn: () => fetchAll(filters) });
  const queue = useQuery({ queryKey: ["queue", queueStatus, undefined], queryFn: () => api.emailQueue({ status: queueStatus || undefined }) });

  const change = <T,>(set: (v: T) => void) => (v: T) => { set(v); setOffset(0); };
  const filtered = !!(vendor || search || status || dateFrom || dateTo || queueStatus);

  // a result belongs to the email with the same vendor and send date; the rest (exceptions, not yet queued) group by vendor name
  const groups: Group[] = [];
  if (results.data && queue.data) {
    const byKey = new Map<string, Group>();
    const emails = new Map(queue.data.map((e) => [`${e.vendor_id}|${e.send_on_date}`, e]));
    for (const r of results.data) {
      const e = r.vendor_id && r.send_on_date ? emails.get(`${r.vendor_id}|${r.send_on_date}`) ?? null : null;
      if (queueStatus && !e) continue; // filtering by email status hides rows without an email
      const key = e ? `q${e.id}` : `v${r.vendor_name}`;
      if (!byKey.has(key)) byKey.set(key, { key, vendor: r.vendor_name, email: e, rows: [] });
      byKey.get(key)!.rows.push(r);
    }
    groups.push(...byKey.values());
    groups.sort((a, b) => (a.email?.send_on_date ?? "9").localeCompare(b.email?.send_on_date ?? "9") || a.vendor.localeCompare(b.vendor));
  }
  const rows = results.data ?? [];
  const count = (...st: ResultStatus[]) => rows.filter((r) => st.includes(r.status)).length;
  const cards: [string, number][] = [
    ["Vendors", groups.length], ["Invoices", groups.reduce((n, g) => n + g.rows.length, 0)], ["With deduction", count("DEDUCTION")],
    ["Exceptions", count("EXCEPTION")], ["Manual review", count("MANUAL_REVIEW")],
  ];
  const ready = results.data && queue.data;

  return (
    <section>
      <h1 className={pageTitle}>Vendor emails</h1>
      <p className="mt-1 text-slate-500">Each vendor with the email going to them and the invoices it covers. Emails are scheduled to go out on their send date (T+2); use Send now to send one at once. The latest upload's result is shown when an invoice appears more than once.</p>
      {isAdmin && <div className="mt-3 space-y-3">{!!drafts.data?.length && <SendAll drafts={drafts.data.length} />}<SendDue dryRun={settings.data?.dry_run ?? true} /></div>}
      <div className="mt-3 flex flex-wrap gap-2">
        <DownloadLink href={downloadUrl.results(filters)}>Download these results (Excel)</DownloadLink>
        <DownloadLink href={downloadUrl.historyExport()}>Download history (Excel)</DownloadLink>
      </div>

      <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5" aria-label="Summary">
        {cards.map(([label, n]) => (
          <li key={label} className={`${card} p-3`}>
            <div className="text-xs text-slate-500">{label}</div>
            <div className="mt-1 font-mono text-xl font-semibold tabular-nums text-slate-900">{ready ? n.toLocaleString("en-IN") : "–"}</div>
          </li>
        ))}
      </ul>

      <form className={`${card} mt-4 flex flex-wrap items-end gap-3 p-3 text-slate-500`} onSubmit={(e) => e.preventDefault()} aria-label="Filter vendors">
        <label className="text-sm">Vendor<br /><input className={input} value={vendor} onChange={(e) => change(setVendor)(e.target.value)} /></label>
        <label className="text-sm">Invoice or UTR<br /><input className={input} value={search} onChange={(e) => change(setSearch)(e.target.value)} /></label>
        <label className="text-sm">Invoice status<br />
          <select className={input} value={status} onChange={(e) => change(setStatus)(e.target.value as ResultStatus | "")}>
            <option value="">All</option>
            {Object.entries(RESULT_BADGE).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
          </select></label>
        <label className="text-sm">Email status<br />
          <select className={input} value={queueStatus} onChange={(e) => change(setQueueStatus)(e.target.value as QueueStatus | "")}>
            <option value="">All</option>
            {Object.entries(QUEUE_BADGE).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
          </select></label>
        <label className="text-sm">Paid from<br /><input type="date" className={input} value={dateFrom} onChange={(e) => change(setDateFrom)(e.target.value)} /></label>
        <label className="text-sm">Paid to<br /><input type="date" className={input} value={dateTo} onChange={(e) => change(setDateTo)(e.target.value)} /></label>
        <button type="button" className={btn} onClick={() => { setVendor(""); setSearch(""); setStatus(""); setQueueStatus(""); setDateFrom(""); setDateTo(""); setOffset(0); }}>Clear</button>
      </form>

      {!ready && !results.isError && !queue.isError && <Loading what="Loading vendors" />}
      {results.isError && <ErrorBox error={results.error} />}
      {queue.isError && <ErrorBox error={queue.error} />}
      {ready && (groups.length === 0 ? <div className="mt-4"><Empty>{filtered ? "No vendors match these filters." : <>No results yet. <Link to="/upload" className="font-medium text-indigo-600 underline-offset-2 hover:underline">Upload files</Link> to get started.</>}</Empty></div> : (
        <>
          <div className="mt-4 space-y-3">
            {groups.slice(offset, offset + PAGE).map((g) => (
              <article key={g.key} className={`${card} animate-fade-up overflow-hidden`} aria-label={g.vendor}>
                <header className="flex flex-wrap items-center justify-between gap-2 bg-slate-100 px-3 py-2">
                  <div>
                    <h2 className="font-display text-sm font-semibold text-slate-900">{g.vendor}</h2>
                    <p className="text-xs text-slate-500">
                      {g.email ? <>To {g.email.to_email ?? "no email address"} · send on {formatDate(g.email.send_on_date)}{g.email.sent_at && <> · sent {formatDateTime(g.email.sent_at)}</>}</> : "No email queued"}
                    </p>
                  </div>
                  {g.email && (
                    <div className="flex items-center gap-3">
                      <StatusBadge map={QUEUE_BADGE} value={g.email.status} />
                      {isAdmin && (g.email.status === "PENDING" || g.email.status === "DRAFT") && <SendNow item={g.email} dryRun={settings.data?.dry_run ?? true} />}
                      <button className={btn} onClick={() => setOpen(g.email)}>Preview<span className="sr-only"> email to {g.vendor}</span></button>
                    </div>
                  )}
                </header>
                <table className="w-full table-fixed border-collapse text-sm">
                  <caption className="sr-only">Invoices for {g.vendor}</caption>
                  <thead><tr>
                    <th className={`${head} w-[14%]`}>Invoice</th><th className={`${head} w-[11%]`}>Invoice amount</th><th className={`${head} w-[15%]`}>UTR</th>
                    <th className={`${head} w-[10%]`}>Payment date</th><th className={`${head} w-[11%]`}>Paid</th><th className={`${head} w-[10%]`}>TDS</th>
                    <th className={`${head} w-[16%]`}>Credit note / deduction</th><th className={`${head} w-[13%]`}>Status</th>
                  </tr></thead>
                  <tbody>
                    {g.rows.map((r) => (
                      <tr key={r.id}>
                        <td className={cell}>{r.invoice_no}</td><td className={`${cell} ${mono}`}>{formatMoney(r.invoice_value)}</td>
                        <td className={`${cell} font-mono text-xs`}>{r.utr}</td><td className={cell}>{formatDate(r.payment_date)}</td>
                        <td className={`${cell} ${mono}`}>{formatMoney(r.amount_paid)}</td><td className={`${cell} ${mono}`}>{formatMoney(r.tds_amount)}</td>
                        <td className={cell}><span className={mono}>{formatMoney(r.invoice_deduction)}</span>{r.reason && <div className="text-xs text-slate-500">{r.reason}</div>}</td>
                        <td className={cell}><StatusBadge map={RESULT_BADGE} value={r.status} />{r.exception_type && <div className="mt-1 text-xs text-slate-700">{r.exception_type.replaceAll("_", " ").toLowerCase()}</div>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            ))}
          </div>
          <Pager offset={offset} limit={PAGE} total={groups.length} onChange={setOffset} />
        </>
      ))}
      {open && <Preview item={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
