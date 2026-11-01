import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadUrl, type ResultOut, type ResultStatus } from "../api/client";
import { DownloadLink, Empty, ErrorBox, Loading, Pager, RESULT_BADGE, StatusBadge, StubTag, btn, input, num, td, th, focusRing } from "../components/ui";
import { formatDate, formatMoney } from "../lib/format";
import { getLastBatch, setLastBatch } from "../lib/lastBatch";

const PAGE = 25;
const FETCH = 500; // the endpoint's max page size

// shortcut: fetches every row and sorts/filters in the browser (fine to a few thousand rows);
// move to server-side paging once a batch can hold far more than ~10,000 rows
async function fetchAll(id: number): Promise<ResultOut[]> {
  const out: ResultOut[] = [];
  for (;;) {
    const { rows, total } = await api.batchResultsPage(id, FETCH, out.length);
    out.push(...rows);
    if (total === null || rows.length === 0 || out.length >= total) return out;
  }
}

type Key = "vendor_name" | "invoice_no" | "invoice_value" | "utr" | "payment_date" | "amount_paid" | "tds_amount" | "invoice_deduction" | "reason" | "status";
const COLS: { key: Key; label: string; money?: boolean }[] = [
  { key: "vendor_name", label: "Vendor" }, { key: "invoice_no", label: "Invoice" }, { key: "invoice_value", label: "Invoice amount", money: true },
  { key: "utr", label: "UTR" }, { key: "payment_date", label: "Payment date" }, { key: "amount_paid", label: "Paid", money: true },
  { key: "tds_amount", label: "TDS amount", money: true }, { key: "invoice_deduction", label: "Invoice deduction", money: true },
  { key: "reason", label: "Reason" }, { key: "status", label: "Status" },
];
// Send date is not here: ResultOut has no such field, and the contract says nobody else computes it.

function compare(a: ResultOut, b: ResultOut, key: Key, money?: boolean) {
  const x = a[key], y = b[key];
  if (x === null || x === "") return y === null || y === "" ? 0 : 1; // blanks last
  if (y === null || y === "") return -1;
  return money ? Number(x) - Number(y) : String(x).localeCompare(String(y)); // Number() only orders rows, nothing is summed
}

function BatchPicker({ id }: { id?: number }) {
  const navigate = useNavigate();
  return (
    <form className="flex items-end gap-2" onSubmit={(e) => {
      e.preventDefault();
      const v = Number(new FormData(e.currentTarget).get("batch"));
      if (Number.isInteger(v) && v > 0) navigate(`/batch-results/${v}`);
    }}>
      <label className="text-sm">Batch number<br />
        <input name="batch" type="number" min={1} defaultValue={id} key={id} className={`${input} w-28`} /></label>
      <button className={btn}>Open</button>
    </form>
  );
}

export default function BatchResults() {
  const params = useParams();
  const id = params.id ? Number(params.id) : getLastBatch() ?? undefined;
  const valid = id !== undefined && Number.isInteger(id) && id > 0;
  useEffect(() => { if (valid) setLastBatch(id); }, [valid, id]);

  const summary = useQuery({ queryKey: ["summary", id], queryFn: () => api.batchSummary(id!), enabled: valid });
  const results = useQuery({ queryKey: ["results", id], queryFn: () => fetchAll(id!), enabled: valid });

  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "vendor_name", dir: 1 });
  const [status, setStatus] = useState<ResultStatus | "">("");
  const [vendor, setVendor] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  const rows = useMemo(() => {
    const col = COLS.find((c) => c.key === sort.key)!;
    const v = vendor.toLowerCase(), s = search.toLowerCase();
    return (results.data ?? [])
      .filter((r) => (!status || r.status === status) && (!v || r.vendor_name.toLowerCase().includes(v))
        && (!s || r.invoice_no.toLowerCase().includes(s) || (r.utr ?? "").toLowerCase().includes(s)))
      .sort((a, b) => sort.dir * compare(a, b, sort.key, col.money));
  }, [results.data, sort, status, vendor, search]);

  const counts = summary.data?.counts;
  // matched = fully explained by the bank (paid in full or TDS only); deduction rows are shown separately
  const cards: [string, number | undefined][] = counts ? [
    ["Total", Object.values(counts).reduce((a, b) => a + b, 0)],
    ["Matched", counts.PAID_IN_FULL + counts.TDS_ONLY],
    ["With deduction", counts.DEDUCTION],
    ["Exceptions", counts.EXCEPTION],
    ["Manual review", counts.MANUAL_REVIEW],
  ] : [];
  const change = <T,>(set: (v: T) => void) => (v: T) => { set(v); setOffset(0); };

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-xl font-semibold">Batch results{valid && ` · batch ${id}`}<StubTag path={`/batches/${id}/results`} /></h1>
        <BatchPicker id={valid ? id : undefined} />
      </div>

      {!valid && <div className="mt-4"><Empty>No batch yet. <Link to="/upload" className="underline">Upload files</Link> or enter a batch number above.</Empty></div>}

      {valid && (<>
        <div className="mt-4 flex flex-wrap gap-2">
          <DownloadLink href={downloadUrl.proforma(id)}>Download proforma (Excel)</DownloadLink>
          <DownloadLink href={downloadUrl.report(id)}>Download reconciliation report (Excel)</DownloadLink>
          <DownloadLink href={downloadUrl.historyExport()}>Download history (Excel)</DownloadLink>
        </div>

        {summary.isError && <div className="mt-4"><ErrorBox error={summary.error} /></div>}
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5" aria-label="Summary">
          {summary.isPending ? <li className="col-span-full"><Loading what="Loading summary" /></li> : cards.map(([label, n]) => (
            <li key={label} className="rounded border border-slate-200 bg-white p-3">
              <div className="text-xs uppercase tracking-wide text-slate-600">{label}</div>
              <div className="text-2xl font-semibold tabular-nums">{n?.toLocaleString("en-IN")}</div>
            </li>
          ))}
        </ul>

        <form className="mt-6 flex flex-wrap items-end gap-3" onSubmit={(e) => e.preventDefault()} aria-label="Filter results">
          <label className="text-sm">Vendor<br /><input className={input} value={vendor} onChange={(e) => change(setVendor)(e.target.value)} /></label>
          <label className="text-sm">Invoice or UTR<br /><input className={input} value={search} onChange={(e) => change(setSearch)(e.target.value)} /></label>
          <label className="text-sm">Status<br />
            <select className={input} value={status} onChange={(e) => change(setStatus)(e.target.value as ResultStatus | "")}>
              <option value="">All</option>
              {Object.entries(RESULT_BADGE).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
            </select></label>
          <button type="button" className={btn} onClick={() => { setVendor(""); setSearch(""); setStatus(""); setOffset(0); }}>Clear</button>
        </form>

        {results.isPending && <Loading what="Loading results" />}
        {results.isError && <ErrorBox error={results.error} />}
        {results.data && (rows.length === 0 ? <div className="mt-4"><Empty>{results.data.length === 0 ? "This batch has no results yet. Run reconciliation first." : "No rows match these filters."}</Empty></div> : (
          <>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">Reconciliation results, {rows.length} rows</caption>
                <thead><tr>
                  {COLS.map((c) => (
                    <th key={c.key} scope="col" className={`${th} ${c.money ? num : ""}`}
                      aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                      <button className={`font-semibold uppercase ${focusRing}`} onClick={() => { setSort((s) => ({ key: c.key, dir: s.key === c.key && s.dir === 1 ? -1 : 1 })); setOffset(0); }}>
                        {c.label}{sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                      </button>
                    </th>
                  ))}
                </tr></thead>
                <tbody>
                  {rows.slice(offset, offset + PAGE).map((r) => (
                    <tr key={r.id}>
                      <td className={td}>{r.vendor_name}</td><td className={td}>{r.invoice_no}</td>
                      <td className={`${td} ${num}`}>{formatMoney(r.invoice_value)}</td><td className={`${td} font-mono text-xs`}>{r.utr}</td>
                      <td className={td}>{formatDate(r.payment_date)}</td><td className={`${td} ${num}`}>{formatMoney(r.amount_paid)}</td>
                      <td className={`${td} ${num}`}>{formatMoney(r.tds_amount)}</td><td className={`${td} ${num}`}>{formatMoney(r.invoice_deduction)}</td>
                      <td className={td}>{r.reason}</td>
                      <td className={td}><StatusBadge map={RESULT_BADGE} value={r.status} />{r.exception_type && <div className="mt-1 text-xs text-slate-700">{r.exception_type.replaceAll("_", " ").toLowerCase()}</div>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager offset={offset} limit={PAGE} total={rows.length} onChange={setOffset} />
          </>
        ))}
      </>)}
    </section>
  );
}
