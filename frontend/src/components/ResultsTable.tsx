import type { ReactNode } from "react";
import type { ResultOut } from "../api/client";
import { formatDate, formatMoney } from "../lib/format";
import { num, td, th } from "./ui";

/** The plain results table shared by Exceptions and Manual review. `extra` adds one trailing column. */
export function ResultsTable({ rows, caption, extraHeader, extra }: {
  rows: ResultOut[]; caption: string; extraHeader?: string; extra?: (r: ResultOut) => ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead><tr>
          <th className={th}>Vendor</th><th className={th}>Invoice</th><th className={`${th} ${num}`}>Invoice amount</th>
          <th className={th}>UTR</th><th className={th}>Payment date</th><th className={`${th} ${num}`}>Paid</th>
          <th className={`${th} ${num}`}>TDS amount</th><th className={`${th} ${num}`}>Invoice deduction</th><th className={th}>Batch</th>
          {extraHeader && <th className={th}>{extraHeader}</th>}
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className={td}>{r.vendor_name}</td><td className={td}>{r.invoice_no}</td>
              <td className={`${td} ${num}`}>{formatMoney(r.invoice_value)}</td><td className={`${td} font-mono text-xs`}>{r.utr}</td>
              <td className={td}>{formatDate(r.payment_date)}</td><td className={`${td} ${num}`}>{formatMoney(r.amount_paid)}</td>
              <td className={`${td} ${num}`}>{formatMoney(r.tds_amount)}</td><td className={`${td} ${num}`}>{formatMoney(r.invoice_deduction)}</td>
              <td className={td}>{r.batch_id}</td>
              {extra && <td className={td}>{extra(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** ?q=… on Exceptions and Manual review: the Email History links use it to land on one item. */
export const matchesQuery = (r: ResultOut, q: string) =>
  !q || r.invoice_no.toLowerCase().includes(q.toLowerCase()) || (r.utr ?? "").toLowerCase().includes(q.toLowerCase());
