const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Takes the contract's money string ("545060.00"). Number() is display-only: never do arithmetic on it.
// null/empty stays empty: the contract says "doesn't apply" is blank, never 0.
export function formatMoney(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return inr.format(Number(v));
}

// ISO datetime -> "05-Aug-26 14:30" (text slice, no timezone shift). Date-only input gives just the date.
export function formatDateTime(iso: string | null | undefined): string {
  const t = /T(\d{2}:\d{2})/.exec(iso ?? "");
  return t ? `${formatDate(iso)} ${t[1]}` : formatDate(iso);
}

// ISO "YYYY-MM-DD" (or datetime) -> "05-Aug-26". Sliced as text so timezones can't shift the day.
export function formatDate(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  return m ? `${m[3]}-${MONTHS[Number(m[2]) - 1]}-${m[1].slice(2)}` : "";
}
