import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorMessage, type ResultOut } from "../api/client";
import { ResultsTable, matchesQuery } from "../components/ResultsTable";
import { Empty, ErrorBox, Loading, StubTag, btn, btnPrimary, input } from "../components/ui";

const MAX_REASON = 500;
const WHY: Record<string, string> = { REASON_MISSING: "Reason missing", AMOUNT_MISMATCH: "Amount mismatch" };

function useRefreshAfterChange() {
  const qc = useQueryClient();
  return () => ["manual-review", "queue", "exceptions", "history"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

function ReasonForm({ row }: { row: ResultOut }) {
  const [text, setText] = useState("");
  const refresh = useRefreshAfterChange();
  const save = useMutation({ mutationFn: () => api.setReason(row.id, text.trim()), onSuccess: refresh });
  const id = `reason-${row.id}`;
  return (
    <form className="flex min-w-72 flex-col gap-1" onSubmit={(e) => { e.preventDefault(); if (text.trim()) save.mutate(); }}>
      <label htmlFor={id} className="sr-only">Reason for invoice {row.invoice_no}</label>
      <div className="flex gap-2">
        <input id={id} className={`${input} flex-1`} value={text} maxLength={MAX_REASON} placeholder="Reason for the deduction"
          onChange={(e) => setText(e.target.value)} aria-describedby={`${id}-msg`} />
        <button className={btnPrimary} disabled={!text.trim() || save.isPending}>{save.isPending ? "Saving…" : "Save"}</button>
      </div>
      <p id={`${id}-msg`} role={save.isError ? "alert" : undefined} className="text-xs text-red-800">{save.isError ? errorMessage(save.error) : ""}</p>
    </form>
  );
}

function GdnUpload() {
  const [file, setFile] = useState<File>();
  const refresh = useRefreshAfterChange();
  const up = useMutation({ mutationFn: () => api.gdnUpload(file!), onSuccess: refresh });
  return (
    <form className="mt-4 rounded-lg border border-slate-200 bg-white p-3" onSubmit={(e) => { e.preventDefault(); if (file) up.mutate(); }}>
      <h2 className="font-medium">Upload an updated GDN report</h2>
      <p className="mb-2 text-sm text-slate-600">Matching items get the report's narration as their reason and move to the email queue.</p>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="gdn-file" className="text-sm">GDN file (.xlsx, .xls)</label>
        <input id="gdn-file" type="file" accept=".xlsx,.xls" className="text-sm" onChange={(e) => { setFile(e.target.files?.[0]); up.reset(); }} />
        <button className={btn} disabled={!file || up.isPending}>{up.isPending ? "Reading…" : "Upload and apply"}</button>
      </div>
      <p role="status" className="mt-2 text-sm">
        {up.data && `Read ${up.data.rows_read.toLocaleString("en-IN")} GDN rows. ${up.data.requeued} item${up.data.requeued === 1 ? "" : "s"} moved to the email queue.`}
      </p>
      {up.isError && <p role="alert" className="mt-2 text-sm text-red-800">{errorMessage(up.error)}</p>}
    </form>
  );
}

export default function ManualReview() {
  const [params, setParams] = useSearchParams();
  const find = params.get("q") ?? "";
  const q = useQuery({ queryKey: ["manual-review"], queryFn: api.manualReview });
  const rows = (q.data ?? []).filter((r) => matchesQuery(r, find));

  return (
    <section>
      <h1 className="text-xl font-semibold">Manual review<StubTag path="/manual-review" /></h1>
      <p className="mt-1 text-slate-600">Deductions with no reason. Type a reason, or upload an updated GDN report. Saved items go straight to the email queue.</p>
      <GdnUpload />
      {find && <p className="mt-3 text-sm">Showing items matching <strong>{find}</strong>. <button className={btn} onClick={() => setParams({})}>Show all</button></p>}

      {q.isPending && <Loading what="Loading items" />}
      {q.isError && <div className="mt-4"><ErrorBox error={q.error} /></div>}
      {q.data && (rows.length === 0
        ? <div className="mt-4"><Empty>{find ? "No item in review matches. It may already be resolved." : "Nothing waiting for review."}</Empty></div>
        : <div className="mt-4"><ResultsTable rows={rows} caption={`Manual review: ${rows.length} items`} extraHeader="Why / reason"
          extra={(r) => (<>
            <p className="mb-1 text-xs font-semibold uppercase text-amber-900">{WHY[r.exception_type ?? ""] ?? r.exception_type}</p>
            <ReasonForm row={r} />
          </>)} /></div>)}
    </section>
  );
}
