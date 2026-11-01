import { expect, test } from "vitest";
import { formatDate, formatMoney } from "./format";

test("Indian grouping", () => {
  expect(formatMoney(545060)).toBe("5,45,060.00");
  expect(formatMoney("196000")).toBe("1,96,000.00");
});

test("blank stays blank, dates are dd-mmm-yy", () => {
  expect(formatMoney(null)).toBe("");
  expect(formatDate("2026-08-05")).toBe("05-Aug-26");
});
