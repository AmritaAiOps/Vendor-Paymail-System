import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type QueueItemOut, type QueueStatus } from "../api/client";
import { EmailFrame } from "../components/EmailFrame";
import { Empty, ErrorBox, Loading, Modal, QUEUE_BADGE, StatusBadge, StubTag, btn, input, num, td, th } from "../components/ui";
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

export default function EmailQueue() {
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
      <h1 className="text-xl font-semibold">Email queue<StubTag path="/email-queue" /></h1>
      <p className="mt-1 text-slate-600">One email per vendor per send date. Select a row to see the email.</p>
      <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={(e) => e.preventDefault()} aria-label="Filter the queue">
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
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Emails grouped by send date</caption>
            <thead><tr><th className={th}>Vendor</th><th className={th}>To</th><th className={`${th} ${num}`}>Invoices</th><th className={th}>Status</th><th className={th}>Sent at</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
            {[...groups].map(([date, items]) => (
              <tbody key={date}>
                <tr><th colSpan={6} scope="colgroup" className="bg-slate-200 px-3 py-1.5 text-left text-sm font-semibold">Send on {formatDate(date)}</th></tr>
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
