import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, downloadUrl, type HistoryFilters, type HistoryOut, type HistoryStatus } from "../api/client";
import { EmailFrame } from "../components/EmailFrame";
import { DownloadLink, Empty, ErrorBox, HISTORY_BADGE, Loading, Modal, Pager, StatusBadge, StubTag, btn, btnPrimary, input, num, td, th } from "../components/ui";
import { formatDate, formatDateTime, formatMoney } from "../lib/format";

const PAGE = 25;
const WHY: Record<string, string> = {
  UTR_NOT_FOUND: "The UTR was not found in the bank statement debits.",
  VENDOR_NOT_FOUND: "The vendor was not found in the vendors list.",
  INVALID_EMAIL: "The vendor's email address is invalid.",
  REASON_MISSING: "The invoice has a deduction but the GDN report gives no reason. It is waiting for manual review.",
  BOUNCED: "The bank returned this payment (NEFT return), so no email was sent.",
  AMOUNT_MISMATCH: "TDS and GDN debit notes do not explain the shortfall, or the invoice was overpaid. It is waiting for manual review.",
};
// A Not sent row links to the page that holds the item behind it, filtered to that UTR (or invoice).
const IN_REVIEW = new Set(["REASON_MISSING", "AMOUNT_MISMATCH"]);
function itemLink(h: HistoryOut): string | null {
  const find = h.utr || h.invoice_no;
  if (h.status !== "NOT_SENT" || !h.not_sent_reason || !find) return null;
  return `${IN_REVIEW.has(h.not_sent_reason) ? "/manual-review" : "/exceptions"}?q=${encodeURIComponent(find)}`;
}
const bounced = (h: HistoryOut) => h.not_sent_reason === "BOUNCED";

function Detail({ row, onClose }: { row: HistoryOut; onClose: () => void }) {
  const fresh = useQuery({ queryKey: ["history-item", row.id], queryFn: () => api.emailHistoryItem(row.id), initialData: row });
  const h = fresh.data;
  const hasEmail = h.status !== "NOT_SENT" && h.email_queue_id !== null;
  const mail = useQuery({ queryKey: ["preview", h.email_queue_id], queryFn: () => api.emailPreview(h.email_queue_id!), enabled: hasEmail });
  const facts: [string, string | null][] = [
    ["Logged at", formatDateTime(h.logged_at)], ["Vendor", h.vendor_name], ["To", h.to_email], ["Invoice", h.invoice_no], ["UTR", h.utr],
    ["Sent at", formatDateTime(h.sent_at)], ["Scheduled for", formatDate(h.scheduled_send_date)],
  ];
  return (
    <Modal title={`${h.vendor_name} · ${h.invoice_no ?? "no invoice"}`} onClose={onClose}>
      <p className="mb-3"><StatusBadge map={HISTORY_BADGE} value={h.status} /></p>
      <dl className="mb-4 grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
        {facts.filter(([, v]) => v).map(([k, v]) => <div key={k} className="contents"><dt className="text-slate-600">{k}</dt><dd>{v}</dd></div>)}
      </dl>
      {h.status === "NOT_SENT" && (
        <div role="note" className={`rounded border p-3 ${bounced(h) ? "border-amber-400 bg-amber-50" : "border-slate-300 bg-slate-50"}`}>
          <h3 className="font-medium">Why no email was sent</h3>
          <p className="mt-1">{WHY[h.not_sent_reason ?? ""] ?? h.not_sent_reason ?? "No reason was recorded."}</p>
          {itemLink(h) && <p className="mt-2"><Link className="underline" to={itemLink(h)!}>Open the {IN_REVIEW.has(h.not_sent_reason ?? "") ? "manual review" : "exception"} item</Link></p>}
        </div>
      )}
      {h.status === "FAILED" && h.error_message && <p role="alert" className="mb-3 rounded border border-red-300 bg-red-50 p-3 text-red-900">Send error: {h.error_message}</p>}
      {h.status === "DRY_RUN" && <p className="mb-3 text-sm text-slate-700">Dry run: this is the email that would be sent. Nothing left the server.</p>}
      {hasEmail && (<>
        <h3 className="mb-2 font-medium">{h.status === "SENT" ? "Email as sent" : "Email"}</h3>
        {mail.isPending && <Loading what="Loading the email" />}
        {mail.isError && <ErrorBox error={mail.error} />}
        {mail.data && <EmailFrame subject={mail.data.subject} to={h.to_email} html={mail.data.html} />}
      </>)}
      {h.status !== "NOT_SENT" && !hasEmail && <Empty>This row has no linked email.</Empty>}
    </Modal>
  );
}

export default function EmailHistory() {
  const [filters, setFilters] = useState<HistoryFilters>({});
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<HistoryOut | null>(null);
  const q = useQuery({ queryKey: ["history", filters, offset], queryFn: () => api.emailHistory(filters, PAGE, offset), placeholderData: (p) => p });
  const counts = q.data?.counts ?? {};
  const all = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);
  const apply = (f: HistoryFilters) => { setFilters(f); setOffset(0); };

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Email History<StubTag path="/email-history" /></h1>
        <div className="flex flex-wrap gap-2">
          {Object.values(filters).some(Boolean) && <DownloadLink href={downloadUrl.historyExport(filters)}>Export filtered view</DownloadLink>}
          <DownloadLink href={downloadUrl.historyExport()}>Download history (Excel)</DownloadLink>
        </div>
      </div>
      <p className="mt-1 text-slate-600">Every email the app sent or did not send, newest first.</p>

      <form className="mt-4 flex flex-wrap items-end gap-3" aria-label="Filter history" key={JSON.stringify(filters) === "{}" ? "clear" : "set"}
        onSubmit={(e) => {
          e.preventDefault();
          const d = new FormData(e.currentTarget);
          const val = (k: string) => (String(d.get(k) ?? "").trim() || undefined);
          apply({ date_from: val("date_from"), date_to: val("date_to"), vendor: val("vendor"), q: val("q"), status: filters.status });
        }}>
        <label className="text-sm">From<br /><input name="date_from" type="date" className={input} defaultValue={filters.date_from} /></label>
        <label className="text-sm">To<br /><input name="date_to" type="date" className={input} defaultValue={filters.date_to} /></label>
        <label className="text-sm">Vendor<br /><input name="vendor" className={input} defaultValue={filters.vendor} /></label>
        <label className="text-sm">UTR or invoice no<br /><input name="q" className={input} defaultValue={filters.q} /></label>
        <button className={btnPrimary}>Apply</button>
        <button type="button" className={btn} onClick={() => apply({})}>Clear</button>
      </form>

      <div role="group" aria-label="Filter by status" className="mt-4 flex flex-wrap gap-2 text-sm">
        <button className={`${btn} ${!filters.status ? "border-blue-700 font-semibold" : ""}`} aria-pressed={!filters.status} onClick={() => apply({ ...filters, status: undefined })}>
          All <span className="tabular-nums">({all.toLocaleString("en-IN")})</span></button>
        {(Object.keys(HISTORY_BADGE) as HistoryStatus[]).map((s) => (
          <button key={s} className={`${btn} ${filters.status === s ? "border-blue-700 font-semibold" : ""}`} aria-pressed={filters.status === s} onClick={() => apply({ ...filters, status: s })}>
            {HISTORY_BADGE[s][0]} <span className="tabular-nums">({(counts[s] ?? 0).toLocaleString("en-IN")})</span></button>
        ))}
      </div>

      {q.isPending && <Loading what="Loading history" />}
      {q.isError && <div className="mt-4"><ErrorBox error={q.error} /></div>}
      {q.data && (q.data.rows.length === 0 ? <div className="mt-4"><Empty>{all === 0 && !filters.status ? "No emails have been sent or blocked yet." : "No history matches these filters."}</Empty></div> : (
        <>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">Email history, {q.data.total} rows</caption>
              <thead><tr>
                {["Logged at", "Vendor", "To", "Subject", "Invoice no", "UTR", "Payment date"].map((c) => <th key={c} className={th}>{c}</th>)}
                {["Amount paid", "TDS amount", "Invoice deduction"].map((c) => <th key={c} className={`${th} ${num}`}>{c}</th>)}
                {["Reason", "Status", "Not sent reason", "Sent at"].map((c) => <th key={c} className={th}>{c}</th>)}
                <th className={th}><span className="sr-only">Details</span></th>
              </tr></thead>
              <tbody>
                {q.data.rows.map((h) => (
                  <tr key={h.id} className={`cursor-pointer hover:bg-slate-50 ${bounced(h) ? "bg-amber-50" : ""}`} onClick={() => setOpen(h)}>
                    <td className={`${td} whitespace-nowrap`}>{formatDateTime(h.logged_at)}</td><td className={td}>{h.vendor_name}</td><td className={td}>{h.to_email}</td>
                    <td className={td}>{h.subject}</td><td className={td}>{h.invoice_no}</td><td className={`${td} font-mono text-xs`}>{h.utr}</td>
                    <td className={`${td} whitespace-nowrap`}>{formatDate(h.payment_date)}</td>
                    <td className={`${td} ${num}`}>{formatMoney(h.amount_paid)}</td><td className={`${td} ${num}`}>{formatMoney(h.tds_amount)}</td>
                    <td className={`${td} ${num}`}>{formatMoney(h.invoice_deduction)}</td><td className={td}>{h.reason}</td>
                    <td className={td}><StatusBadge map={HISTORY_BADGE} value={h.status} /></td>
                    <td className={td}>{h.not_sent_reason && (() => {
                      const text = h.not_sent_reason.replaceAll("_", " ").toLowerCase(), to = itemLink(h);
                      return to
                        ? <Link to={to} className={`underline ${bounced(h) ? "font-semibold" : ""}`} onClick={(e) => e.stopPropagation()}>{text}</Link>
                        : <span className={bounced(h) ? "font-semibold" : ""}>{text}</span>;
                    })()}</td>
                    <td className={`${td} whitespace-nowrap`}>{formatDateTime(h.sent_at)}</td>
                    <td className={td}><button className={btn} onClick={(e) => { e.stopPropagation(); setOpen(h); }}>View<span className="sr-only"> {h.invoice_no ?? h.vendor_name}</span></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager offset={offset} limit={PAGE} total={q.data.total} onChange={setOffset} />
        </>
      ))}
      {open && <Detail row={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
