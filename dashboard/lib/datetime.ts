// Pure timestamp formatters. `timeZone` is always an explicit parameter (never
// read from context here) so every function is unit-testable with zero React
// setup, and so a caller can never accidentally format in the browser's zone.
//
// The DB deliberately stores UTC (see docs/data-formats.md) — these formatters
// convert to host-local for display only. See TimeZoneProvider for where the
// host's IANA zone name comes from.

const NO_VALUE = "—";

/** Accepts a bare "YYYY-MM-DDTHH:MM:SS" (no zone designator) as UTC, matching
 * every backend _now() implementation. Returns null on anything unparseable. */
function parseIso(iso: string): Date | null {
  if (!iso) return null;
  const normalized = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(iso) ? `${iso}Z` : iso;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function isValidTimeZone(tz: string | null | undefined): boolean {
  if (!tz) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

export function formatDate(iso: string, timeZone: string): string {
  const d = parseIso(iso);
  if (!d) return NO_VALUE;
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone, month: "short", day: "numeric", year: "numeric",
    }).format(d);
  } catch {
    return NO_VALUE;
  }
}

export function formatDateShort(iso: string, timeZone: string): string {
  const d = parseIso(iso);
  if (!d) return NO_VALUE;
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone, month: "short", day: "numeric",
    }).format(d);
  } catch {
    return NO_VALUE;
  }
}

export function formatDateTime(iso: string, timeZone: string): string {
  const d = parseIso(iso);
  if (!d) return NO_VALUE;
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone, month: "short", day: "numeric", year: "numeric",
      hour: "numeric", minute: "2-digit",
    }).format(d);
  } catch {
    return NO_VALUE;
  }
}

export function formatClock(d: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(d);
  } catch {
    return NO_VALUE;
  }
}

/** Relative "Xh"/"Xd" — pure epoch subtraction, timezone-independent by design.
 * `now` is a parameter (not Date.now()) so this stays deterministic in tests
 * without faking Date, matching the repo's vitest convention. */
export function formatRelative(iso: string, now: number): string {
  const d = parseIso(iso);
  if (!d) return NO_VALUE;
  const diff = now - d.getTime();
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 24) return `${Math.max(hours, 0)}h`;
  return `${Math.floor(hours / 24)}d`;
}

/** A scheduled post's time, shown in the zone it was chosen in — which may
 * differ from the host's, so the zone is always named: "Thu, Oct 1, 2026,
 * 9:00 AM GMT+5:30 · Asia/Kolkata". */
export function formatScheduled(iso: string, timeZone: string): string {
  const d = parseIso(iso);
  if (!d || !isValidTimeZone(timeZone)) return NO_VALUE;
  const when = new Intl.DateTimeFormat("en-US", {
    timeZone, weekday: "short", month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }).format(d);
  return `${when} · ${timeZone}`;
}

/** The wall-clock date ("YYYY-MM-DD") and time ("HH:MM") at `at` in
 * `timeZone` — the shapes `<input type="date">` and `<input type="time">`
 * take. Used for the schedule presets and the date picker's minimum; the API,
 * not this, converts a picked wall time back to UTC. */
export function wallClock(timeZone: string, at: Date): { date: string; time: string } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(at).map((p) => [p.type, p.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

/** "YYYY-MM-DD" plus `days`, as calendar arithmetic — no zone is involved. */
export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}
