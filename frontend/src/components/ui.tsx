import { useEffect, useRef, useState, type ReactNode } from "react";
import { download, errorMessage } from "../api/client";

export const focusRing = "outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 focus-visible:ring-offset-0";
const press = "transition duration-150 hover:-translate-y-px active:translate-y-0 active:scale-[.98] disabled:pointer-events-none disabled:opacity-50";
export const btn = `inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 ${press} ${focusRing}`;
export const btnPrimary = `inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-indigo-600/25 hover:bg-indigo-500 ${press} ${focusRing}`;
export const input = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 disabled:bg-slate-50 disabled:text-slate-500";
/** White panel used for every grouped block on a page. */
export const card = "rounded-xl border border-slate-200 bg-white shadow-sm";
export const pageTitle = "font-display text-2xl font-semibold tracking-tight text-slate-900";
export const sectionTitle = "font-display text-lg font-semibold tracking-tight text-slate-900";

const tones = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 [--dot:var(--color-emerald-500)]",
  red: "bg-rose-50 text-rose-700 ring-rose-600/20 [--dot:var(--color-rose-500)]",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/25 [--dot:var(--color-amber-500)]",
  blue: "bg-indigo-50 text-indigo-700 ring-indigo-600/20 [--dot:var(--color-indigo-500)]",
  slate: "bg-slate-100 text-slate-700 ring-slate-500/20 [--dot:var(--color-slate-400)]",
};

/** Always carries its text, so meaning never depends on colour alone. */
export function Badge({ label, tone }: { label: string; tone: keyof typeof tones }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[var(--dot)]" />{label}
    </span>
  );
}

export const RESULT_BADGE = {
  PAID_IN_FULL: ["Paid in full", "green"], TDS_ONLY: ["TDS only", "blue"], DEDUCTION: ["Deduction", "amber"],
  EXCEPTION: ["Exception", "red"], MANUAL_REVIEW: ["Manual review", "amber"],
} as const;
export const QUEUE_BADGE = {
  DRAFT: ["Draft", "slate"], PENDING: ["Scheduled", "blue"], SENDING: ["Sending", "blue"], SENT: ["Sent", "green"], FAILED: ["Failed", "red"], SKIPPED: ["Skipped", "amber"],
} as const;
export const HISTORY_BADGE = {
  SENT: ["Sent", "green"], FAILED: ["Failed", "red"], DRY_RUN: ["Dry run", "blue"], NOT_SENT: ["Not sent", "amber"],
} as const;

export function StatusBadge({ map, value }: { map: Record<string, readonly [string, keyof typeof tones]>; value: string }) {
  const [label, tone] = map[value] ?? [value, "slate" as const];
  return <Badge label={label} tone={tone} />;
}

/** The app mark: the Amrita square logo. */
export const Logo = ({ className = "h-9 w-9" }: { className?: string }) => (
  <img src="/amrita-mark.png" alt="" aria-hidden className={`rounded-xl object-cover ${className}`} />
);

export const Spinner = ({ className = "h-4 w-4" }: { className?: string }) => (
  <span aria-hidden className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent ${className}`} />
);

export const Loading = ({ what = "Loading" }: { what?: string }) => (
  <div role="status" className="flex animate-fade-in items-center gap-3 py-8 text-slate-500">
    <Spinner className="h-5 w-5 text-indigo-600" /><span>{what}…</span>
  </div>
);

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="flex animate-fade-in flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white/60 px-6 py-14 text-center text-sm text-slate-500">
    <svg aria-hidden viewBox="0 0 24 24" className="h-8 w-8 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 13h4l2 3h6l2-3h4M5 13l2-8h10l2 8v6H5z" strokeLinejoin="round" />
    </svg>
    <p>{children}</p>
  </div>
);

export const ErrorBox = ({ error }: { error: unknown }) => (
  <p role="alert" className="flex animate-fade-up items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
    <svg aria-hidden viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9 6a1 1 0 112 0v4a1 1 0 11-2 0V6zm1 8.5a1.25 1.25 0 100-2.5 1.25 1.25 0 000 2.5z" clipRule="evenodd" />
    </svg>
    <span>{errorMessage(error)}</span>
  </p>
);

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
  if (total === 0) return null;
  const to = Math.min(offset + limit, total);
  return (
    <nav aria-label="Pages" className="flex items-center justify-between gap-3 py-3 text-sm text-slate-500">
      <span aria-live="polite">Showing <b className="font-mono font-semibold tabular-nums text-slate-800">{offset + 1}–{to}</b> of {total.toLocaleString("en-IN")}</span>
      <span className="flex gap-2">
        <button className={btn} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>← Previous</button>
        <button className={btn} disabled={to >= total} onClick={() => onChange(offset + limit)}>Next →</button>
      </span>
    </nav>
  );
}

export function DownloadLink({ href, children }: { href: string; children: ReactNode }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const click = () => {
    setBusy(true); setError(null);
    download(href).catch(setError).finally(() => setBusy(false));
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" className={btn} disabled={busy} onClick={click}>
        {busy ? <Spinner /> : (
          <svg aria-hidden viewBox="0 0 20 20" className="h-4 w-4 text-indigo-600" fill="currentColor">
            <path d="M10 3a1 1 0 011 1v7.59l2.3-2.3a1 1 0 111.4 1.42l-4 4a1 1 0 01-1.4 0l-4-4a1 1 0 111.4-1.42l2.3 2.3V4a1 1 0 011-1zM4 15a1 1 0 011 1v1h10v-1a1 1 0 112 0v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2a1 1 0 011-1z" />
          </svg>
        )}
        {children}
      </button>
      {error !== null && <span role="alert" className="text-sm text-rose-700">{errorMessage(error)}</span>}
    </span>
  );
}

/** Native <dialog>: Esc closes, focus is trapped and restored by the browser. */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="modal-title"
      className="m-auto w-[min(56rem,95vw)] overflow-hidden rounded-xl border border-slate-200 bg-white p-0 text-slate-700 shadow-2xl backdrop:bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-5 py-3">
        <h2 id="modal-title" className={sectionTitle}>{title}</h2>
        <button className={btn} onClick={() => ref.current?.close()}>Close</button>
      </div>
      <div className="max-h-[75vh] overflow-auto p-5">{children}</div>
    </dialog>
  );
}

/** A table inside a card, scrolling sideways on small screens. */
export const TableCard = ({ children, className = "" }: { children: ReactNode; className?: string }) => (
  <div className={`${card} animate-fade-up overflow-x-auto ${className}`}>{children}</div>
);

export const th = "border-b border-slate-200 bg-slate-50 px-3 py-2.5 text-left text-xs font-medium text-slate-500";
export const td = "border-b border-slate-200 px-3 py-3 align-top text-slate-700";
export const num = "text-right font-mono tabular-nums";
