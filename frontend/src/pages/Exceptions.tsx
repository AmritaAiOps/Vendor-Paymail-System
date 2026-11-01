import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, downloadUrl, type ExceptionType, type ResultOut } from "../api/client";
import { ResultsTable, matchesQuery } from "../components/ResultsTable";
import { DownloadLink, Empty, ErrorBox, Loading, StubTag, btn } from "../components/ui";

// Order and wording of the groups. BOUNCED is highlighted wherever it appears, with the text label as well as colour.
const GROUPS: { type: ExceptionType; title: string; hint: string }[] = [
  { type: "UTR_NOT_FOUND", title: "UTR not found", hint: "The UTR is not among the bank statement debits. Check the UTR in the Consolidated Report." },
  { type: "VENDOR_NOT_FOUND", title: "Vendor not found", hint: "The vendor is not in the Vendors List. Add them to the list and upload again." },
  { type: "INVALID_EMAIL", title: "Invalid email", hint: "The vendor's email address in the Vendors List is not valid." },
  { type: "BOUNCED", title: "Payment bounced", hint: "The bank returned the payment (NEFT return). No email is sent." },
];

export default function Exceptions() {
  const [params, setParams] = useSearchParams();
  const find = params.get("q") ?? "";
  const q = useQuery({ queryKey: ["exceptions"], queryFn: api.exceptions });
  const rows = (q.data ?? []).filter((r) => matchesQuery(r, find));
  const byType = (t: string) => rows.filter((r) => r.exception_type === t);
  const known = new Set<string>(GROUPS.map((g) => g.type));
  const other = rows.filter((r: ResultOut) => !known.has(r.exception_type ?? ""));

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Exceptions<StubTag path="/exceptions" /></h1>
        <DownloadLink href={downloadUrl.exceptionsExport()}>Download exceptions (Excel)</DownloadLink>
      </div>
      <p className="mt-1 text-slate-600">Payments that got no email, grouped by cause.</p>
      {find && (
        <p className="mt-3 text-sm">Showing items matching <strong>{find}</strong>. <button className={btn} onClick={() => setParams({})}>Show all</button></p>
      )}

      {q.isPending && <Loading what="Loading exceptions" />}
      {q.isError && <div className="mt-4"><ErrorBox error={q.error} /></div>}
      {q.data && (rows.length === 0
        ? <div className="mt-4"><Empty>{find ? "No open exception matches. It may already be resolved." : "No exceptions. Every payment has an email."}</Empty></div>
        : <>
          {GROUPS.map((g) => byType(g.type).length > 0 && (
            <section key={g.type} className={`mt-6 rounded-lg border p-3 ${g.type === "BOUNCED" ? "border-amber-400 bg-amber-50" : "border-slate-200 bg-white"}`}>
              <h2 className="text-lg font-semibold">{g.title} <span className="font-normal text-slate-600">({byType(g.type).length})</span></h2>
              <p className="mb-2 text-sm text-slate-700">{g.hint}</p>
              <ResultsTable rows={byType(g.type)} caption={`${g.title}: ${byType(g.type).length} rows`} />
            </section>
          ))}
          {other.length > 0 && (
            <section className="mt-6 rounded-lg border border-slate-200 bg-white p-3">
              <h2 className="text-lg font-semibold">Other <span className="font-normal text-slate-600">({other.length})</span></h2>
              <ResultsTable rows={other} caption="Other exceptions" extraHeader="Type" extra={(r) => r.exception_type} />
            </section>
          )}
        </>)}
    </section>
  );
}
