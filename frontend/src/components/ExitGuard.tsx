import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type PendingSummary, type SendAllOut } from "../api/client";
import { formatDateTime, timeRemaining } from "../lib/format";
import { Badge, ErrorBox, Modal, Spinner, btn, btnPrimary, card, focusRing, td, th } from "./ui";

export const PENDING_KEY = ["pending-summary"] as const;

/** Scheduled (T+2) emails not yet sent, plus the missing-UTR count. Refreshed every minute while the app is open. */
export const usePendingSummary = () =>
  useQuery({ queryKey: PENDING_KEY, queryFn: api.pendingSummary, refetchInterval: 60_000, staleTime: 15_000 });

type Reason = "logout" | "close";
type Guard = { requestSignOut: () => void };
const GuardContext = createContext<Guard>({ requestSignOut: () => {} });
export const useExitGuard = () => useContext(GuardContext);

/** What the pending set looks like: "Keep as scheduled" is remembered for this exact set, so closing the tab afterwards
 *  isn't nagged again, but newly scheduled mails ask again. */
const signature = (s: PendingSummary) => s.items.map((i) => i.id).join(",");

/**
 * Wraps the signed-in app. Before the user leaves (sign out, or closing / reloading / leaving the tab) it checks for
 * scheduled mails that haven't gone out, and shows what they are.
 * - Sign out goes through requestSignOut(): a fresh check, then the modal if anything is pending.
 * - Closing the tab: browsers only allow their own generic "Leave site?" prompt, and only from a synchronous
 *   `beforeunload` handler, so it uses the last summary the app fetched. If the user answers "Stay", the page is still
 *   alive a moment later, and the in-app modal opens with the details.
 * Idle sign-out (useAuth) has nobody to ask, so it signs out as before.
 */
export function ExitGuardProvider({ isAdmin, signOut, children }: { isAdmin: boolean; signOut: () => void; children: ReactNode }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState<Reason | null>(null);
  const [summary, setSummary] = useState<PendingSummary>();
  const kept = useRef<string | null>(null);

  const open = useCallback((r: Reason, s: PendingSummary) => { setSummary(s); setReason(r); }, []);

  const requestSignOut = useCallback(() => {
    qc.fetchQuery({ queryKey: PENDING_KEY, queryFn: api.pendingSummary, staleTime: 0 })
      .then((s) => (s.total > 0 ? open("logout", s) : signOut()))
      .catch(signOut); // can't tell (offline): the user asked to sign out, so do it
  }, [qc, open, signOut]);

  useEffect(() => {
    let timer: number | undefined;
    const onUnload = (e: BeforeUnloadEvent) => {
      const s = qc.getQueryData<PendingSummary>(PENDING_KEY);
      if (!s || s.total === 0 || signature(s) === kept.current) return;
      e.preventDefault();
      e.returnValue = ""; // the browser shows its own text; custom text is not allowed
      window.clearTimeout(timer);
      timer = window.setTimeout(() => open("close", s), 300); // only runs if the user chose to stay
    };
    window.addEventListener("beforeunload", onUnload);
    return () => { window.removeEventListener("beforeunload", onUnload); window.clearTimeout(timer); };
  }, [qc, open]);

  const value = useMemo(() => ({ requestSignOut }), [requestSignOut]);
  return (
    <GuardContext.Provider value={value}>
      {children}
      {reason && summary && (
        <PendingMailsModal key={reason} reason={reason} initial={summary} isAdmin={isAdmin}
          onKeep={() => { kept.current = signature(summary); }}
          onSignOut={signOut} onClose={() => setReason(null)} />
      )}
    </GuardContext.Provider>
  );
}

// ---------------------------------------------------------------------------------------------------------------------

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;

function PendingMailsModal({ reason, initial, isAdmin, onKeep, onSignOut, onClose }: {
  reason: Reason; initial: PendingSummary; isAdmin: boolean; onKeep: () => void; onSignOut: () => void; onClose: () => void;
}) {
  const qc = useQueryClient();
  // the list keeps updating while the modal is open (a daily run or another user may send some meanwhile)
  const live = usePendingSummary();
  const s = live.data ?? initial;
  const [step, setStep] = useState<"list" | "confirm" | "done">("list");
  const [withFlagged, setWithFlagged] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 30_000); return () => window.clearInterval(t); }, []);

  const flagged = s.items.filter((i) => i.missing_utr_count > 0);
  const send = useMutation({
    mutationFn: () => api.sendAllNow(s.items.map((i) => i.id), withFlagged),
    onSuccess: () => { qc.invalidateQueries(); setStep("done"); },
  });
  const sent: SendAllOut | undefined = send.data;
  const leaving = reason === "logout";
  const keepAndGo = () => { onKeep(); onClose(); if (leaving) onSignOut(); };

  return (
    <Modal title={step === "confirm" ? "Send scheduled mails now?" : step === "done" ? "Mails sent" : "Scheduled mails are still pending"}
      onClose={() => { onClose(); }}>
      {step === "list" && (
        <>
          <p className="text-slate-600">
            {leaving ? "Before you sign out: " : "Before you close the app: "}
            <b className="text-slate-900">{plural(s.total, "mail")}</b> {s.total === 1 ? "is" : "are"} scheduled but not sent yet.
            The daily job sends them on their T+2 date, but only while the server is running, so you decide now.
          </p>

          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <div className="rounded-xl bg-indigo-50 px-3 py-2"><dt className="text-xs text-slate-500">Pending scheduled mails</dt><dd className="font-mono text-lg font-semibold tabular-nums text-slate-900">{s.total}</dd></div>
            <div className={`rounded-xl px-3 py-2 ${flagged.length ? "bg-amber-50" : "bg-slate-50"}`}>
              <dt className="text-xs text-slate-500">With missing UTRs</dt>
              <dd className="font-mono text-lg font-semibold tabular-nums text-slate-900">{flagged.length}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 px-3 py-2"><dt className="text-xs text-slate-500">Next send</dt><dd className="truncate font-medium text-slate-900">{s.items[0] ? timeRemaining(Date.parse(s.items[0].scheduled_at), now) : ""}</dd></div>
          </dl>

          <div className="mt-4 max-h-72 overflow-auto rounded-xl ring-1 ring-slate-200">
            <table className="w-full min-w-[34rem] border-collapse text-sm">
              <thead className="sticky top-0"><tr>
                <th className={th}>Vendor</th><th className={`${th} text-right`}>Invoices</th><th className={th}>Scheduled send</th><th className={th}>Time remaining</th><th className={th}>UTR</th>
              </tr></thead>
              <tbody>
                {s.items.map((i) => (
                  <tr key={i.id} className={i.missing_utr_count ? "bg-amber-50/50" : ""}>
                    <td className={`${td} font-medium text-slate-900`}>{i.vendor_name}</td>
                    <td className={`${td} text-right tabular-nums`}>{i.invoice_count}</td>
                    <td className={`${td} whitespace-nowrap`}>{formatDateTime(i.scheduled_at)}</td>
                    <td className={`${td} whitespace-nowrap`}>{timeRemaining(Date.parse(i.scheduled_at), now)}</td>
                    <td className={td}>{i.missing_utr_count ? <Badge label={`${plural(i.missing_utr_count, "invoice")} missing UTR`} tone="amber" /> : <span className="text-slate-400">OK</span>}</td>
                  </tr>
                ))}
                {!s.items.length && <tr><td colSpan={5} className={`${td} py-6 text-center text-slate-500`}>Nothing is pending any more.</td></tr>}
              </tbody>
            </table>
          </div>

          {flagged.length > 0 && (
            <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">
              <b>{plural(flagged.length, "mail")}</b> belong{flagged.length === 1 ? "s" : ""} to vendors with invoices that have no UTR. Those invoices are not in the emails.
              Sending now holds these mails unless you choose to include them. <Link to="/exceptions" onClick={onClose} className="font-medium underline">Review exceptions</Link>
            </p>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
            <button type="button" className={`${focusRing} mr-auto rounded-md px-2 py-1 text-sm text-slate-600 hover:underline`} onClick={onClose}>
              {leaving ? "Stay in the app" : "Back to the app"}
            </button>
            <button type="button" className={btn} onClick={keepAndGo}>Keep as scheduled (T+2)</button>
            <button type="button" className={btnPrimary} disabled={!isAdmin || !s.total} onClick={() => setStep("confirm")}
              title={isAdmin ? undefined : "Only admins can send mails now"}>Send now</button>
          </div>
          {!isAdmin && <p className="mt-2 text-right text-xs text-slate-500">Only admins can send mails now. “Keep as scheduled” leaves them for the daily job.</p>}
        </>
      )}

      {step === "confirm" && (
        <>
          <p className="text-slate-700">
            This sends the mails to the vendors <b>right now</b>, instead of on their T+2 dates. It can't be undone.
          </p>
          {flagged.length > 0 ? (
            <fieldset className="mt-4 space-y-2">
              <legend className="text-sm font-medium text-slate-900">{plural(flagged.length, "mail")} flagged with missing UTRs</legend>
              {([
                [false, `Hold the ${flagged.length} flagged and send the other ${s.total - flagged.length}`, "The flagged mails stay scheduled until the UTRs are fixed. Recommended."],
                [true, `Send all ${s.total}, including the flagged`, "The emails contain only the invoices that have a UTR."],
              ] as const).map(([v, label, note]) => (
                <label key={String(v)} className={`flex cursor-pointer gap-3 rounded-xl border p-3 text-sm ${withFlagged === v ? "border-indigo-400 bg-indigo-50" : "border-slate-200 hover:bg-slate-50"}`}>
                  <input type="radio" name="flagged" checked={withFlagged === v} onChange={() => setWithFlagged(v)} className="mt-1" />
                  <span><span className="block font-medium text-slate-900">{label}</span><span className="text-slate-500">{note}</span></span>
                </label>
              ))}
            </fieldset>
          ) : (
            <p className="mt-3 text-sm text-slate-600">{plural(s.total, "mail")} will be sent.</p>
          )}
          {send.isError && <div className="mt-3"><ErrorBox error={send.error} /></div>}
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className={btn} disabled={send.isPending} onClick={() => { send.reset(); setStep("list"); }}>Back</button>
            <button type="button" className={btnPrimary} disabled={send.isPending} onClick={() => send.mutate()}>
              {send.isPending ? <><Spinner />Sending…</> : `Yes, send ${withFlagged || !flagged.length ? s.total : s.total - flagged.length} now`}
            </button>
          </div>
        </>
      )}

      {step === "done" && sent && (
        <>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([["Sent", sent.sent, "bg-emerald-50"], ["Held (missing UTR)", sent.held, sent.held ? "bg-amber-50" : "bg-slate-50"],
              ["Failed", sent.failed + sent.not_sent, sent.failed + sent.not_sent ? "bg-rose-50" : "bg-slate-50"], ["Dry run", sent.dry_run, "bg-slate-50"]] as const).map(([k, v, tone]) => (
              <div key={k} className={`rounded-xl px-3 py-2 ${tone}`}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-mono text-lg font-semibold tabular-nums text-slate-900">{v}</dd></div>
            ))}
          </dl>
          {sent.dry_run > 0 && <p className="mt-3 text-sm text-slate-600">Dry run is on in Settings: those mails were logged, not emailed, and stay scheduled.</p>}
          {sent.held > 0 && <p className="mt-3 text-sm text-slate-600">The held mails stay scheduled. Fix the missing UTRs (Exceptions) and they go out on their date.</p>}
          {sent.already_done > 0 && <p className="mt-3 text-sm text-slate-600">{plural(sent.already_done, "mail")} had already been sent by someone else.</p>}
          <div className="mt-5 flex justify-end gap-2">
            {leaving
              ? <button type="button" className={btnPrimary} onClick={() => { onClose(); onSignOut(); }}>Sign out</button>
              : <button type="button" className={btnPrimary} onClick={onClose}>Done</button>}
          </div>
        </>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------------------------------------------------
// Missing-UTR notification

const DISMISSED = "utrNoticeDismissed";
const stored = () => { try { return Number(sessionStorage.getItem(DISMISSED)) || 0; } catch { return 0; } };

/** A banner under the header while invoices have no UTR. It comes back if the number grows after being dismissed. */
export function MissingUtrNotice() {
  const { data } = usePendingSummary();
  const [dismissed, setDismissed] = useState(stored);
  const n = data?.missing_utr_invoices ?? 0;
  if (n === 0 || n <= dismissed) return null;
  const mails = data!.missing_utr_mails;
  const dismiss = () => { setDismissed(n); try { sessionStorage.setItem(DISMISSED, String(n)); } catch { /* storage blocked: it just comes back on reload */ } };
  return (
    <div role="status" className={`${card} mx-auto mt-3 flex max-w-[110rem] animate-fade-in flex-wrap items-center gap-x-3 gap-y-1 border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-950`}>
      <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-amber-600" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0" /></svg>
      <span className="min-w-0 flex-1">
        <b>{plural(n, "invoice")} {n === 1 ? "has" : "have"} no UTR</b>, so no mail can be sent for {n === 1 ? "it" : "them"}.
        {mails > 0 && <> {plural(mails, "scheduled mail")} belong{mails === 1 ? "s" : ""} to vendors with this problem; those mails are flagged and held if you send now.</>}
      </span>
      <Link to="/exceptions" className={`${focusRing} rounded font-medium underline`}>Review exceptions</Link>
      <button type="button" aria-label="Dismiss notification" onClick={dismiss} className={`${focusRing} rounded px-1.5 text-amber-700 hover:text-amber-900`}>✕</button>
    </div>
  );
}
