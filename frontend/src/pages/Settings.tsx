import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage, type SettingsModel } from "../api/client";
import { ErrorBox, Loading, StubTag, btn, btnPrimary, input } from "../components/ui";

const MAX_SIGNATURE = 500;

function SettingsForm({ saved }: { saved: SettingsModel }) {
  const qc = useQueryClient();
  const [dryRun, setDryRun] = useState(saved.dry_run);
  const save = useMutation({
    mutationFn: api.saveSettings,
    onSuccess: (s) => qc.setQueryData(["settings"], s),
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (saved.dry_run && !dryRun && !confirm("Turn DRY_RUN off? The next run will email real vendors.")) return;
    save.mutate({ dry_run: dryRun, send_time: String(f.get("send_time")), signature: String(f.get("signature")).trim() });
  }

  return (
    <form className="mt-4 grid max-w-xl gap-4" onSubmit={submit} onChange={() => save.reset()}>
      <fieldset className={`rounded-lg border-2 p-3 ${dryRun ? "border-blue-300 bg-blue-50" : "border-red-500 bg-red-50"}`}>
        <legend className="px-1 font-semibold">Dry run</legend>
        <label className="flex items-center gap-2 text-base font-medium">
          <input type="checkbox" name="dry_run" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="h-5 w-5" aria-describedby="dry-run-note" />
          DRY_RUN: preview only, send nothing
        </label>
        <p id="dry-run-note" className={`mt-2 text-sm ${dryRun ? "text-blue-900" : "font-semibold text-red-900"}`}>
          {dryRun
            ? "On: emails are logged as Dry run in the history, nothing goes to vendors."
            : "Warning: DRY_RUN is off. Every due email goes to the vendor's real address on the next run."}
        </p>
      </fieldset>

      <div className="grid gap-1">
        <label htmlFor="send_time" className="font-medium">Daily send time (IST)</label>
        <input id="send_time" name="send_time" type="time" required defaultValue={saved.send_time} className={`${input} w-36`} />
      </div>

      <div className="grid gap-1">
        <label htmlFor="signature" className="font-medium">Signature under the email table</label>
        <input id="signature" name="signature" required maxLength={MAX_SIGNATURE} defaultValue={saved.signature} className={input}
          pattern=".*\S.*" title="Signature can't be empty" />
      </div>

      <div className="flex items-center gap-3">
        <button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save settings"}</button>
        <p role="status" className="text-sm text-green-800">{save.isSuccess && "Saved."}</p>
      </div>
      {save.isError && <ErrorBox error={save.error} />}
    </form>
  );
}

function Actions({ dryRun }: { dryRun: boolean }) {
  const qc = useQueryClient();
  const refresh = () => ["queue", "history"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const run = useMutation({ mutationFn: api.runNow, onSuccess: refresh });
  const rebuild = useMutation({ mutationFn: api.rebuildHistoryXlsx });
  return (
    <section className="mt-8 max-w-xl rounded-lg border border-slate-200 bg-white p-3" aria-labelledby="actions-h">
      <h2 id="actions-h" className="font-semibold">Actions</h2>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button className={btn} disabled={run.isPending}
          onClick={() => (dryRun || confirm("DRY_RUN is off: this emails real vendors now. Continue?")) && run.mutate()}>
          {run.isPending ? "Running…" : "Run now"}
        </button>
        <button className={btn} disabled={rebuild.isPending} onClick={() => rebuild.mutate()}>
          {rebuild.isPending ? "Rebuilding…" : "Rebuild history file"}
        </button>
      </div>
      <p role="status" className="mt-2 text-sm">
        {run.data && `Run finished: ${run.data.sent} sent, ${run.data.failed} failed, ${run.data.dry_run} dry run, ${run.data.not_sent} not sent.`}
        {run.data && rebuild.data && " "}
        {rebuild.data && `History file rebuilt with ${rebuild.data.rows.toLocaleString("en-IN")} rows.`}
      </p>
      {run.isError && <p role="alert" className="mt-1 text-sm text-red-800">Run now: {errorMessage(run.error)}</p>}
      {rebuild.isError && <p role="alert" className="mt-1 text-sm text-red-800">Rebuild: {errorMessage(rebuild.error)}</p>}
    </section>
  );
}

export default function Settings() {
  const q = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return (
    <section>
      <h1 className="text-xl font-semibold">Settings<StubTag path="/settings" /></h1>
      <p className="mt-1 text-slate-600">A value set in the server environment wins; saving it here is refused.</p>
      {q.isPending && <Loading what="Loading settings" />}
      {q.isError && <div className="mt-4"><ErrorBox error={q.error} /></div>}
      {q.data && <><SettingsForm saved={q.data} /><Actions dryRun={q.data.dry_run} /></>}
    </section>
  );
}
