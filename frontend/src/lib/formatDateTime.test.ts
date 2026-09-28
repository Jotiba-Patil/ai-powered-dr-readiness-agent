import { describe, expect, it } from "vitest";
import { formatDateTime } from "./labels";

// Same cases as backend/tests/unit/test_timefmt.py, so both sides print identical text.
const CASES: [string, string, string][] = [
  ["2026-09-28T06:00:00Z", "UTC", "28 Sep 2026, 06:00 UTC"],
  ["2026-09-28T06:00:00Z", "Asia/Kolkata", "28 Sep 2026, 11:30 UTC+05:30"],
  ["2026-09-28T06:00:00Z", "America/New_York", "28 Sep 2026, 02:00 UTC-04:00"],
  ["2026-01-05T23:30:00Z", "Europe/Berlin", "6 Jan 2026, 00:30 UTC+01:00"],
  ["2026-03-01T04:45:00Z", "Asia/Kathmandu", "1 Mar 2026, 10:30 UTC+05:45"],
];

describe("formatDateTime", () => {
  it.each(CASES)("%s in %s", (iso, timeZone, text) => {
    expect(formatDateTime(iso, { timeZone })).toBe(text);
  });

  it("uses the browser's zone by default (UTC in tests) and can show seconds", () => {
    expect(formatDateTime("2026-09-28T06:00:05Z")).toBe("28 Sep 2026, 06:00 UTC");
    expect(formatDateTime("2026-09-28T06:00:05Z", { seconds: true })).toBe(
      "28 Sep 2026, 06:00:05 UTC",
    );
    expect(formatDateTime("2026-09-28T06:00:00+02:00", { timeZone: "UTC" })).toBe(
      "28 Sep 2026, 04:00 UTC",
    );
  });

  it("leaves anything that is not a date as it is", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
  });
});
