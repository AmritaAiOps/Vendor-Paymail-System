// The contract has no "list batches" endpoint, so the screens remember the batch you last uploaded or opened.
const KEY = "lastBatchId";

export function getLastBatch(): number | null {
  try {
    const v = Number(localStorage.getItem(KEY));
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

export function setLastBatch(id: number) {
  try { localStorage.setItem(KEY, String(id)); } catch { /* private mode: just don't remember */ }
}
