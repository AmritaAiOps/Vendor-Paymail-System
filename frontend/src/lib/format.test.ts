import { expect, test } from "vitest";
import { formatDate, formatDateTime, formatMoney, timeRemaining } from "./format";

test("datetime keeps the (IST) clock time", () => {
  expect(formatDateTime("2025-09-15T10:05:33")).toBe("15-Sep-25 10:05");
  expect(formatDateTime("2025-09-15")).toBe("15-Sep-25");
  expect(formatDateTime(null)).toBe("");
});

test("Indian grouping", () => {
  expect(formatMoney(545060)).toBe("5,45,060.00");
  expect(formatMoney("196000")).toBe("1,96,000.00");
});

test("time remaining reads like a person would say it", () => {
  const now = Date.parse("2026-11-10T10:00:00+05:30");
  const at = (ms: number) => timeRemaining(now + ms, now);
  const H = 3_600_000;
  expect(at(28 * H)).toBe("in 1 day 4 hrs");
  expect(at(48 * H)).toBe("in 2 days");
  expect(at(3 * H + 20 * 60_000)).toBe("in 3 hrs");
  expect(at(H)).toBe("in 1 hr");
  expect(at(25 * 60_000)).toBe("in 25 min");
  expect(at(5_000)).toBe("in 1 min");
  expect(at(0)).toBe("due now");
  expect(at(-H)).toBe("due now");
});

test("blank stays blank, dates are dd-mmm-yy", () => {
  expect(formatMoney(null)).toBe("");
  expect(formatDate("2026-08-05")).toBe("05-Aug-26");
});
