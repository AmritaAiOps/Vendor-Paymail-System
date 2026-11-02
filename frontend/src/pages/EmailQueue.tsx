import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorMessage, type QueueItemOut, type QueueStatus } from "../api/client";
import { EmailFrame } from "../components/EmailFrame";
import { btn, btnPrimary, card, Empty, ErrorBox, input, Loading, Modal, num, pageTitle, QUEUE_BADGE, Spinner, StatusBadge, td, th } from "../components/ui";
import { useMe } from "../lib/useAuth";
import { formatDate, formatDateTime } from "../lib/format";

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

export default function EmailQueue() {
  const isAdmin = useMe().data?.is_admin ?? false;
  const drafts = useQuery({ queryKey: ["queue", "DRAFT", undefined], queryFn: () => api.emailQueue({ status: "DRAFT" }) });
  const [status, setStatus] = useState<QueueStatus | "">("");
  const [batch, setBatch] = useState("");
  const [open, setOpen] = useState<QueueItemOut | null>(null);
  const batchId = Number(batch) > 0 ? Number(batch) : undefined;
  const q = useQuery({
    queryKey: ["queue", status, batchId],
    queryFn: () => api.emailQueue({ status: status || undefined, batch_id: batchId }),
  });

  // one table body per send date; each row is one vendor's email for that day
  const groups = new Map<string, QueueItemOut[]>();
  [...(q.data ?? [])].sort((a, b) => a.send_on_date.localeCompare(b.send_on_date) || a.vendor_name.localeCompare(b.vendor_name))
    .forEach((i) => groups.set(i.send_on_date, [...(groups.get(i.send_on_date) ?? []), i]));

  return (
    <section>
      <h1 className={pageTitle}>Email queue</h1>
      <p className="mt-1 text-slate-500">One email per vendor per send date. Select a row to see the email.</p>
      {isAdmin && <div className="mt-4"><SendAll drafts={drafts.data?.length ?? 0} /></div>}
      <form className={`${card} mt-4 flex flex-wrap items-end gap-3 p-4 text-slate-500`} onSubmit={(e) => e.preventDefault()} aria-label="Filter the queue">
        <label className="text-sm">Status<br />
          <select className={input} value={status} onChange={(e) => setStatus(e.target.value as QueueStatus | "")}>
            <option value="">All</option>
            {Object.entries(QUEUE_BADGE).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
          </select></label>
        <label className="text-sm">Batch number<br /><input type="number" min={1} className={`${input} w-28`} value={batch} onChange={(e) => setBatch(e.target.value)} /></label>
      </form>

      {q.isPending && <Loading what="Loading the queue" />}
      {q.isError && <ErrorBox error={q.error} />}
      {q.data && (q.data.length === 0 ? <div className="mt-4"><Empty>Nothing in the queue{status || batchId ? " for these filters" : " yet"}.</Empty></div> : (
        <div className={`${card} mt-4 animate-fade-up overflow-x-auto`}>
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Emails grouped by send date</caption>
            <thead><tr><th className={th}>Vendor</th><th className={th}>To</th><th className={`${th} ${num}`}>Invoices</th><th className={th}>Status</th><th className={th}>Sent at</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
            {[...groups].map(([date, items]) => (
              <tbody key={date}>
                <tr><th colSpan={6} scope="colgroup" className="bg-slate-100 px-3 py-1.5 text-left font-mono text-xs font-medium text-indigo-700">Send on {formatDate(date)}</th></tr>
                {items.map((i) => (
                  <tr key={i.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(i)}>
                    <td className={td}>{i.vendor_name}</td><td className={td}>{i.to_email}</td>
                    <td className={`${td} ${num}`}>{i.invoice_count}</td>
                    <td className={td}><StatusBadge map={QUEUE_BADGE} value={i.status} /></td>
                    <td className={td}>{formatDateTime(i.sent_at)}</td>
                    <td className={td}><button className={btn} onClick={(e) => { e.stopPropagation(); setOpen(i); }}>Preview<span className="sr-only"> email to {i.vendor_name}</span></button></td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      ))}
      {open && <Preview item={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
