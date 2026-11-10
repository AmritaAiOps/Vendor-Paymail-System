const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Takes the contract's money string ("545060.00"). Number() is display-only: never do arithmetic on it.
// null/empty stays empty: the contract says "doesn't apply" is blank, never 0.
export function formatMoney(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return inr.format(Number(v));
}

// ISO datetime -> "05-Aug-26 14:30". The backend stores every timestamp in IST, so the clock time is shown as is.
export function formatDateTime(iso: string | null | undefined): string {
  const t = /T(\d{2}:\d{2})/.exec(iso ?? "");
  return t ? `${formatDate(iso)} ${t[1]}` : formatDate(iso);
}

/** "in 1 day 4 hrs", "in 3 hrs", "in 25 min"; "due now" once the time has passed. Days and hours only, minutes when under an hour. */
export function timeRemaining(targetMs: number, nowMs: number = Date.now()): string {
  const diff = targetMs - nowMs;
  if (diff <= 0) return "due now";
  const days = Math.floor(diff / 86_400_000);
  const hrs = Math.floor((diff % 86_400_000) / 3_600_000);
  if (days > 0) return `in ${days} day${days > 1 ? "s" : ""}${hrs ? ` ${hrs} hr${hrs > 1 ? "s" : ""}` : ""}`;
  if (hrs > 0) return `in ${hrs} hr${hrs > 1 ? "s" : ""}`;
  return `in ${Math.max(1, Math.ceil(diff / 60_000))} min`;
}

// ISO "YYYY-MM-DD" (or datetime) -> "05-Aug-26". Sliced as text so timezones can't shift the day.
export function formatDate(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  return m ? `${m[3]}-${MONTHS[Number(m[2]) - 1]}-${m[1].slice(2)}` : "";
}
