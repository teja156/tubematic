import { describe, expect, it } from "vitest";
import {
  formatClock,
  formatDate,
  formatDateShort,
  formatDateTime,
  formatRelative,
  isValidTimeZone,
  addDays,
  formatScheduled,
  wallClock,
} from "@/lib/datetime";

describe("formatDate", () => {
  it("formats in the given IANA timezone, not the host's (canary)", () => {
    // Test runner host is pinned to UTC (vitest.config.ts). This is the same
    // instant as midnight UTC, which crosses to the previous local day in
    // America/New_York — proves the explicit timeZone argument is honored,
    // catching the whole class of date-boundary bugs (incl. the old
    // scripts/status.py [:10] raw-slice bug).
    expect(formatDate("2026-01-01T00:00:00Z", "America/New_York")).toBe("Dec 31, 2025");
  });

  it("formats correctly on the UTC baseline", () => {
    expect(formatDate("2026-01-01T00:00:00Z", "UTC")).toBe("Jan 1, 2026");
  });

  it("returns em dash for unparseable input", () => {
    expect(formatDate("garbage", "UTC")).toBe("—");
    expect(formatDate("", "UTC")).toBe("—");
  });

  it("returns em dash for an invalid timezone rather than throwing", () => {
    expect(formatDate("2026-01-01T00:00:00Z", "Not/A Zone")).toBe("—");
  });
});

describe("formatDateShort / formatDateTime", () => {
  it("formatDateShort omits the year", () => {
    expect(formatDateShort("2026-01-01T00:00:00Z", "UTC")).toBe("Jan 1");
  });

  it("formatDateTime includes a time component", () => {
    expect(formatDateTime("2026-01-01T13:00:00Z", "UTC")).toContain("1:00");
  });

  it("DST spring-forward: an IANA zone name tracks the offset change, a fixed offset would not", () => {
    // 2026-03-08 is the US DST transition (2am -> 3am local in America/New_York).
    expect(formatDateTime("2026-03-08T06:59:00Z", "America/New_York")).toContain("1:59");
    expect(formatDateTime("2026-03-08T07:01:00Z", "America/New_York")).toContain("3:01");
  });
});

describe("parseIso (via formatDate) — legacy Z-less rows", () => {
  it("treats a bare 'YYYY-MM-DDTHH:MM:SS' (no zone designator) as UTC", () => {
    expect(formatDate("2026-01-01T00:00:00", "UTC")).toBe("Jan 1, 2026");
  });
});

describe("formatClock", () => {
  it("formats HH:MM:SS in 24h in the given zone", () => {
    const d = new Date("2026-01-01T13:05:09Z");
    expect(formatClock(d, "UTC")).toBe("13:05:09");
  });
});

describe("formatRelative", () => {
  it("is deterministic given an explicit `now` — no Date faking required", () => {
    const created = "2026-01-01T00:00:00Z";
    const threeHoursLater = new Date("2026-01-01T03:00:00Z").getTime();
    const twoDaysLater = new Date("2026-01-03T00:00:00Z").getTime();
    expect(formatRelative(created, threeHoursLater)).toBe("3h");
    expect(formatRelative(created, twoDaysLater)).toBe("2d");
  });

  it("returns em dash for unparseable input", () => {
    expect(formatRelative("garbage", Date.now())).toBe("—");
  });
});

describe("isValidTimeZone", () => {
  it("accepts a real IANA name", () => {
    expect(isValidTimeZone("America/New_York")).toBe(true);
    expect(isValidTimeZone("UTC")).toBe(true);
  });

  it("rejects a human label — the guard that keeps a label out of the Intl call", () => {
    expect(isValidTimeZone("EDT (UTC-04:00)")).toBe(false);
  });

  it("rejects null/undefined/empty", () => {
    expect(isValidTimeZone(null)).toBe(false);
    expect(isValidTimeZone(undefined)).toBe(false);
    expect(isValidTimeZone("")).toBe(false);
  });
});

describe("scheduling helpers", () => {
  it("formatScheduled names the zone the time was chosen in", () => {
    const out = formatScheduled("2026-10-01T03:30:00Z", "Asia/Kolkata");
    expect(out).toContain("Oct 1, 2026");
    expect(out).toContain("9:00 AM");
    expect(out).toContain("GMT+5:30");
    expect(out.endsWith("· Asia/Kolkata")).toBe(true);
  });

  it("formatScheduled shows nothing for a missing time or a bad zone", () => {
    expect(formatScheduled("", "UTC")).toBe("—");
    expect(formatScheduled("2026-10-01T03:30:00Z", "Not/AZone")).toBe("—");
  });

  it("wallClock reads the date and time in the given zone", () => {
    const at = new Date("2026-09-28T20:45:00Z");
    expect(wallClock("UTC", at)).toEqual({ date: "2026-09-28", time: "20:45" });
    // Already tomorrow in Kolkata — the date input's minimum must follow the zone.
    expect(wallClock("Asia/Kolkata", at)).toEqual({ date: "2026-09-29", time: "02:15" });
  });

  it("wallClock gives 00, never 24, at midnight", () => {
    expect(wallClock("UTC", new Date("2026-09-28T00:05:00Z")).time).toBe("00:05");
  });

  it("addDays crosses month and year ends", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
});
