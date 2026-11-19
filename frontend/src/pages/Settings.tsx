import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage, type SettingsModel, type SmtpSettings } from "../api/client";
import { EmailFrame } from "../components/EmailFrame";
import { btn, btnPrimary, card, ErrorBox, input, Loading, pageTitle } from "../components/ui";
import { useMe } from "../lib/useAuth";

const MAX_SIGNATURE = 500;

function SettingsForm({ saved, readOnly }: { saved: SettingsModel; readOnly: boolean }) {
  const qc = useQueryClient();
  const [dryRun, setDryRun] = useState(saved.dry_run);
  const save = useMutation({
    mutationFn: api.saveSettings,
    onSuccess: (s) => { qc.setQueryData(["settings"], s); qc.invalidateQueries({ queryKey: ["settings", "email-sample"] }); },
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (saved.dry_run && !dryRun && !confirm("Turn DRY_RUN off? The next run will email real vendors.")) return;
    const text = (k: string) => String(f.get(k) ?? "").trim();
    save.mutate({
      dry_run: dryRun, send_time: text("send_time"), signature: text("signature"), email_subject: text("email_subject"), email_intro: text("email_intro"),
      email_outro: text("email_outro"), email_closing: text("email_closing"), email_company: text("email_company"),
    });
  }

  return (
    <form className="mt-4 grid max-w-xl gap-4" onSubmit={submit} onChange={() => save.reset()}>
      {readOnly && <p className="text-sm text-slate-500">Only admins can change settings.</p>}
      <fieldset disabled={readOnly} className={`rounded-2xl border-2 p-4 transition-colors duration-300 ${dryRun ? "border-sky-200 bg-sky-50/80" : "border-rose-400 bg-rose-50"}`}>
        <legend className="px-1 font-semibold">Dry run</legend>
        <label className="flex items-center gap-2 text-base font-medium">
          <input type="checkbox" name="dry_run" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="h-5 w-5" aria-describedby="dry-run-note" />
          DRY_RUN: preview only, send nothing
        </label>
        <p id="dry-run-note" className={`mt-2 text-sm ${dryRun ? "text-indigo-800" : "font-semibold text-rose-800"}`}>
          {dryRun
            ? "On: emails are logged as Dry run in the history, nothing goes to vendors."
            : "Warning: DRY_RUN is off. Every due email goes to the vendor's real address on the next run."}
        </p>
      </fieldset>

      <div className="grid gap-1">
        <label htmlFor="send_time" className="font-medium">Daily send time (IST)</label>
        <input id="send_time" name="send_time" type="time" required disabled={readOnly} defaultValue={saved.send_time} className={`${input} w-36`} />
      </div>

      <fieldset disabled={readOnly} className="grid gap-3 rounded-2xl border border-slate-200 p-4">
        <legend className="px-1 font-semibold">Email wording</legend>
        {([
          ["email_subject", "Subject", "{vendor} and {company} are filled in for each email", true],
          ["email_intro", "Opening line", "Under “Dear vendor,”. Leave empty to skip", false],
          ["email_outro", "Line after the table", "Leave empty to skip", false],
          ["email_closing", "Closing", "For example: Yours faithfully, / Regards,", true],
          ["email_company", "Company name", "Bold, last line of the email", true],
        ] as const).map(([k, label, note, req]) => (
          <div key={k} className="grid gap-1">
            <label htmlFor={k} className="text-sm font-medium">{label}</label>
            <input id={k} name={k} required={req} defaultValue={saved[k]} className={input} />
            <span className="text-xs text-slate-500">{note}</span>
          </div>
        ))}
        <div className="grid gap-1">
          <label htmlFor="signature" className="text-sm font-medium">Signature (name, designation, phone…)</label>
          <textarea id="signature" name="signature" required rows={3} maxLength={MAX_SIGNATURE} defaultValue={saved.signature} className={input}
            title="Signature can't be empty" />
          <span className="text-xs text-slate-500">One line each; they appear under the closing.</span>
        </div>
      </fieldset>

      {/* Hiding admin controls is comfort only: the server refuses them for non-admins */}
      {!readOnly && <div className="flex items-center gap-3">
        <button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save settings"}</button>
        <p role="status" className="text-sm text-emerald-700">{save.isSuccess && "Saved."}</p>
      </div>}
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
    <section className={`${card} mt-8 max-w-xl p-5`} aria-labelledby="actions-h">
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
      {run.isError && <p role="alert" className="mt-1 text-sm text-rose-700">Run now: {errorMessage(run.error)}</p>}
      {rebuild.isError && <p role="alert" className="mt-1 text-sm text-rose-700">Rebuild: {errorMessage(rebuild.error)}</p>}
    </section>
  );
}

/** Read-only: the mail server is set in the server's .env (SMTP_*). The test button checks it works. */
function SmtpInfo({ s }: { s: SmtpSettings }) {
  const test = useMutation({ mutationFn: api.testSmtp });
  const rows: [string, string][] = [
    ["Server", s.host ? `${s.host}:${s.port}${s.starttls ? " (STARTTLS)" : ""}` : "Not set"],
    ["Username", s.user || "Not set"],
    ["Password", s.password_set ? "Set" : "Not set"],
    ["From", s.from_email ? `${s.from_name} <${s.from_email}>` : "Not set"],
  ];
  return (
    <section className={`${card} mt-8 max-w-xl p-5`} aria-labelledby="smtp-h">
      <h2 id="smtp-h" className="font-semibold">Email server (SMTP)</h2>
      <p className="mt-1 text-sm text-slate-500">Set in the server's <code>.env</code> (<code>SMTP_*</code>); change it there and restart. Admins only.</p>
      <dl className="mt-4 grid grid-cols-[7rem_1fr] gap-x-4 gap-y-2 text-sm">
        {rows.map(([k, v]) => <div key={k} className="contents"><dt className="font-medium">{k}</dt><dd className="break-all text-slate-700">{v}</dd></div>)}
      </dl>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" className={btn} disabled={test.isPending} onClick={() => test.mutate()} title="Sends a test email to you">
          {test.isPending ? "Sending…" : "Send test email"}
        </button>
        <p role="status" className="text-sm text-emerald-700">{test.data && `Test email sent to ${test.data.sent_to}.`}</p>
      </div>
      {test.isError && <ErrorBox error={test.error} />}
    </section>
  );
}

function EmailServer() {
  const q = useQuery({ queryKey: ["smtp"], queryFn: api.smtpSettings });
  if (q.isPending) return <Loading what="Loading email server settings" />;
  if (q.isError) return <div className="mt-8 max-w-xl"><ErrorBox error={q.error} /></div>;
  return <SmtpInfo s={q.data} />;
}

/** The real template with made-up rows. SettingsForm refetches it on save, so a new signature shows. */
function EmailSample() {
  const q = useQuery({ queryKey: ["settings", "email-sample"], queryFn: api.emailSample });
  return (
    <section className={`${card} mt-8 max-w-3xl p-5`} aria-labelledby="sample-h">
      <h2 id="sample-h" className="font-semibold">Email format</h2>
      <p className="mt-1 mb-4 text-sm text-slate-500">What vendors receive. The rows here are made up; real emails list that vendor's paid invoices.</p>
      {q.isPending && <Loading what="Loading sample email" />}
      {q.isError && <ErrorBox error={q.error} />}
      {q.data && <EmailFrame subject={q.data.subject} to="vendor@example.com" html={q.data.html} />}
    </section>
  );
}

export default function Settings() {
  const q = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const isAdmin = useMe().data?.is_admin ?? false;
  return (
    <section>
      <h1 className={pageTitle}>Settings</h1>
      <p className="mt-1 text-slate-500">A value set in the server environment wins; saving it here is refused.</p>
      {q.isPending && <Loading what="Loading settings" />}
      {q.isError && <div className="mt-4"><ErrorBox error={q.error} /></div>}
      {q.data && <><SettingsForm saved={q.data} readOnly={!isAdmin} /><EmailSample />{isAdmin && <><EmailServer /><Actions dryRun={q.data.dry_run} /></>}</>}
    </section>
  );
}
