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
    save.mutate({ dry_run: dryRun, send_time: String(f.get("send_time")), signature: String(f.get("signature")).trim() });
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

      <div className="grid gap-1">
        <label htmlFor="signature" className="font-medium">Signature under the email table</label>
        <input id="signature" name="signature" required disabled={readOnly} maxLength={MAX_SIGNATURE} defaultValue={saved.signature} className={input}
          pattern=".*\S.*" title="Signature can't be empty" />
      </div>

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

const FIELD_ENV: Record<string, string> = {
  host: "SMTP_HOST", port: "SMTP_PORT", user: "SMTP_USER", password: "SMTP_PASSWORD",
  from_email: "SMTP_FROM", from_name: "SMTP_FROM_NAME", starttls: "SMTP_STARTTLS",
};

function SmtpForm({ saved }: { saved: SmtpSettings }) {
  const qc = useQueryClient();
  const [starttls, setStarttls] = useState(saved.starttls);
  const save = useMutation({ mutationFn: api.saveSmtpSettings, onSuccess: (s) => qc.setQueryData(["smtp"], s) });
  const test = useMutation({ mutationFn: api.testSmtp });
  const locked = (f: string) => saved.locked.includes(f);
  const hint = (f: string) => locked(f) && <span className="text-xs text-slate-500">Set by {FIELD_ENV[f]} on the server</span>;

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const text = (k: string) => String(f.get(k) ?? "").trim();
    save.mutate({
      host: text("host"), port: Number(f.get("port")), user: text("user"), password: String(f.get("password") ?? ""),
      from_email: text("from_email"), from_name: text("from_name"), starttls,
    });
  }

  const field = (name: keyof SmtpSettings, label: string, props: Record<string, unknown> = {}) => (
    <div className="grid gap-1">
      <label htmlFor={`smtp-${name}`} className="font-medium">{label}</label>
      <input id={`smtp-${name}`} name={name} disabled={locked(name)} defaultValue={String(saved[name] ?? "")} className={input} {...props} />
      {hint(name)}
    </div>
  );

  return (
    <section className={`${card} mt-8 max-w-xl p-5`} aria-labelledby="smtp-h">
      <h2 id="smtp-h" className="font-semibold">Email server (SMTP)</h2>
      <p className="mt-1 text-sm text-slate-500">The mail account the payment advice emails are sent from. Admins only.</p>
      <form className="mt-4 grid gap-4" onSubmit={submit} onChange={() => { save.reset(); test.reset(); }}>
        <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
          {field("host", "Server", { placeholder: "smtp.gmail.com", autoComplete: "off" })}
          {field("port", "Port", { type: "number", min: 1, max: 65535, required: true })}
        </div>
        {field("user", "Username", { autoComplete: "off" })}
        <div className="grid gap-1">
          <label htmlFor="smtp-password" className="font-medium">Password</label>
          <input id="smtp-password" name="password" type="password" autoComplete="new-password" disabled={locked("password")} className={input}
            placeholder={saved.password_set ? "Saved. Leave blank to keep it" : "App password or account password"} />
          {hint("password")}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {field("from_email", "From address", { type: "email", placeholder: "payments@company.com" })}
          {field("from_name", "From name")}
        </div>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={starttls} disabled={locked("starttls")} onChange={(e) => setStarttls(e.target.checked)} className="h-4 w-4" />
          Use STARTTLS (port 587; turn off only if your provider says so)
          {hint("starttls")}
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save email server"}</button>
          <button type="button" className={btn} disabled={test.isPending || save.isPending} onClick={() => test.mutate()}
            title="Sends a test email to you with the saved settings">
            {test.isPending ? "Sending…" : "Send test email"}
          </button>
          <p role="status" className="text-sm text-emerald-700">
            {save.isSuccess && "Saved."} {test.data && `Test email sent to ${test.data.sent_to}.`}
          </p>
        </div>
        {save.isError && <ErrorBox error={save.error} />}
        {test.isError && <ErrorBox error={test.error} />}
      </form>
    </section>
  );
}

function EmailServer() {
  const q = useQuery({ queryKey: ["smtp"], queryFn: api.smtpSettings });
  if (q.isPending) return <Loading what="Loading email server settings" />;
  if (q.isError) return <div className="mt-8 max-w-xl"><ErrorBox error={q.error} /></div>;
  return <SmtpForm saved={q.data} />;
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
