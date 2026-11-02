import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, downloadUrl, errorMessage, type ExceptionType, type ResultOut } from "../api/client";
import { ResultsTable, matchesQuery } from "../components/ResultsTable";
import { btn, btnPrimary, card, DownloadLink, Empty, ErrorBox, input, Loading, pageTitle, sectionTitle, Spinner } from "../components/ui";

// Order and wording of the groups. BOUNCED is highlighted wherever it appears, with the text label as well as colour.
const GROUPS: { type: ExceptionType; title: string; hint: string }[] = [
  { type: "UTR_NOT_FOUND", title: "UTR not found", hint: "The UTR is not among the bank statement debits. Check the UTR in the Consolidated Report." },
  { type: "VENDOR_NOT_FOUND", title: "Vendor not found", hint: "The vendor is not in the Vendors List. Add them to the list and upload all five files again, then reconcile: the new batch replaces these rows." },
  { type: "INVALID_EMAIL", title: "Invalid email", hint: "The vendor's email address in the Vendors List is not valid. Type the right address and save: the held payments go to the email queue." },
  { type: "BOUNCED", title: "Payment bounced", hint: "The bank returned the payment (NEFT return). No email is sent." },
];

/** Saves the vendor's address; the server then queues this vendor's exceptions that now pass. */
function FixEmail({ vendorId }: { vendorId: number }) {
  const [email, setEmail] = useState("");
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.setVendorEmail(vendorId, email.trim()),
    onSuccess: () => ["exceptions", "queue", "history", "summary", "results"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
  return (
    <form className="flex min-w-72 flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <input type="text" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@vendor.com, other@vendor.com"
        aria-label="Correct email address" className={`${input} flex-1 py-1.5`} />
      <button className={`${btnPrimary} py-1.5`} disabled={save.isPending || !email.trim()}>{save.isPending ? <Spinner /> : "Save"}</button>
      {save.isError && <span role="alert" className="w-full text-xs text-rose-700">{errorMessage(save.error)}</span>}
    </form>
  );
}

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
        <h1 className={pageTitle}>Exceptions</h1>
        <DownloadLink href={downloadUrl.exceptionsExport()}>Download exceptions (Excel)</DownloadLink>
      </div>
      <p className="mt-1 text-slate-500">Payments that got no email, grouped by cause.</p>
      {find && (
        <p className="mt-3 text-sm">Showing items matching <strong>{find}</strong>. <button className={btn} onClick={() => setParams({})}>Show all</button></p>
      )}

      {q.isPending && <Loading what="Loading exceptions" />}
      {q.isError && <div className="mt-4"><ErrorBox error={q.error} /></div>}
      {q.data && (rows.length === 0
        ? <div className="mt-4"><Empty>{find ? "No open exception matches. It may already be resolved." : "No exceptions. Every payment has an email."}</Empty></div>
        : <>
          {GROUPS.map((g) => byType(g.type).length > 0 && (
            <section key={g.type} className={`mt-6 animate-fade-up rounded-xl border p-4 ${g.type === "BOUNCED" ? "border-amber-300 bg-amber-50/80" : "border-slate-200 bg-white shadow-sm"}`}>
              <h2 className={sectionTitle}>{g.title} <span className="font-normal text-slate-500">({byType(g.type).length})</span></h2>
              <p className="mb-2 text-sm text-slate-700">{g.hint}</p>
              {g.type === "INVALID_EMAIL"
                ? <ResultsTable rows={byType(g.type)} caption={`${g.title}: ${byType(g.type).length} rows`} extraHeader="Fix email"
                    extra={(r) => r.vendor_id !== null && byType(g.type).find((x) => x.vendor_id === r.vendor_id) === r
                      ? <FixEmail vendorId={r.vendor_id} /> : <span className="text-xs text-slate-500">Same vendor as above</span>} />
                : <ResultsTable rows={byType(g.type)} caption={`${g.title}: ${byType(g.type).length} rows`} />}
            </section>
          ))}
          {other.length > 0 && (
            <section className={`${card} mt-6 animate-fade-up p-4`}>
              <h2 className={sectionTitle}>Other <span className="font-normal text-slate-500">({other.length})</span></h2>
              <ResultsTable rows={other} caption="Other exceptions" extraHeader="Type" extra={(r) => r.exception_type} />
            </section>
          )}
        </>)}
    </section>
  );
}
