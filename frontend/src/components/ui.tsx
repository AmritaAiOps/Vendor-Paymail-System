import { useEffect, useRef, type ReactNode } from "react";
import { errorMessage, isStub } from "../api/client";

export const focusRing = "outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-1";
export const btn = `rounded border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 ${focusRing}`;
export const btnPrimary = `rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50 ${focusRing}`;
export const input = `rounded border border-slate-300 bg-white px-2 py-1.5 text-sm ${focusRing}`;

const tones = {
  green: "bg-green-100 text-green-900 border-green-300",
  red: "bg-red-100 text-red-900 border-red-300",
  amber: "bg-amber-100 text-amber-900 border-amber-300",
  blue: "bg-blue-100 text-blue-900 border-blue-300",
  slate: "bg-slate-100 text-slate-800 border-slate-300",
};

/** Always carries its text, so meaning never depends on colour alone. */
export function Badge({ label, tone }: { label: string; tone: keyof typeof tones }) {
  return <span className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{label}</span>;
}

export const RESULT_BADGE = {
  PAID_IN_FULL: ["Paid in full", "green"], TDS_ONLY: ["TDS only", "blue"], DEDUCTION: ["Deduction", "amber"],
  EXCEPTION: ["Exception", "red"], MANUAL_REVIEW: ["Manual review", "amber"],
} as const;
export const QUEUE_BADGE = {
  PENDING: ["Pending", "slate"], SENDING: ["Sending", "blue"], SENT: ["Sent", "green"], FAILED: ["Failed", "red"], SKIPPED: ["Skipped", "amber"],
} as const;
export const HISTORY_BADGE = {
  SENT: ["Sent", "green"], FAILED: ["Failed", "red"], DRY_RUN: ["Dry run", "blue"], NOT_SENT: ["Not sent", "amber"],
} as const;

export function StatusBadge({ map, value }: { map: Record<string, readonly [string, keyof typeof tones]>; value: string }) {
  const [label, tone] = map[value] ?? [value, "slate" as const];
  return <Badge label={label} tone={tone} />;
}

export const Loading = ({ what = "Loading" }: { what?: string }) => <p role="status" className="py-6 text-slate-600">{what}…</p>;
export const Empty = ({ children }: { children: ReactNode }) => <p className="rounded border border-dashed border-slate-300 py-8 text-center text-slate-600">{children}</p>;
export const ErrorBox = ({ error }: { error: unknown }) => (
  <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-red-900">{errorMessage(error)}</p>
);

/** Dev only: marks a screen whose last response for `path` came from a stub (X-Stub: true). */
export function StubTag({ path }: { path: string }) {
  return import.meta.env.DEV && isStub(path)
    ? <span title="This response came from a stub with canned data" className="ml-2 rounded border border-dashed border-purple-400 px-1.5 py-0.5 text-xs font-normal text-purple-800">stub data</span>
    : null;
}

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
  if (total === 0) return null;
  const to = Math.min(offset + limit, total);
  return (
    <nav aria-label="Pages" className="flex items-center gap-3 py-3 text-sm">
      <button className={btn} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <span aria-live="polite">{offset + 1}–{to} of {total.toLocaleString("en-IN")}</span>
      <button className={btn} disabled={to >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </nav>
  );
}

export function DownloadLink({ href, children }: { href: string; children: ReactNode }) {
  return <a href={href} download className={`inline-block ${btn}`}>{children}</a>;
}

/** Native <dialog>: Esc closes, focus is trapped and restored by the browser. */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="modal-title" className="m-auto w-[min(56rem,95vw)] rounded-lg p-0 backdrop:bg-black/40">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 id="modal-title" className="text-lg font-semibold">{title}</h2>
        <button className={btn} onClick={() => ref.current?.close()}>Close</button>
      </div>
      <div className="max-h-[75vh] overflow-auto p-4">{children}</div>
    </dialog>
  );
}

export const th = "border-b border-slate-300 bg-slate-100 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-700";
export const td = "border-b border-slate-200 px-3 py-2 align-top";
export const num = "text-right tabular-nums";
