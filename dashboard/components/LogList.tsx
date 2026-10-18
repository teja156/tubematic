"use client";

import { useTimeZone } from "@/components/TimeZoneProvider";
import type { LogRecord } from "@/lib/types";

/** Rendering for a list of log records, shared by the Logs page and the
 * per-video tab in VideoModal so the two cannot drift apart visually. */

const mono = { fontFamily: "var(--mono)" } as const;

// Records store UTC (the `ts` field is written as ...Z), and the whole app
// formats in the host's zone at display time — see TimeZoneProvider.
const LEVEL_COLOR: Record<string, string> = {
  debug: "var(--dim)",
  info: "var(--mute)",
  warning: "var(--amber)",
  error: "var(--red, #e5484d)",
  critical: "var(--red, #e5484d)",
};

function formatTs(ts: string, timeZone: string) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  }).format(d);
}

export function LogList({
  records,
  emptyLabel = "No log records match these filters.",
  testId = "log-list",
}: {
  records: LogRecord[];
  emptyLabel?: string;
  testId?: string;
}) {
  const { timeZone } = useTimeZone();

  if (records.length === 0) {
    return (
      <p data-testid={`${testId}-empty`} style={{ ...mono, fontSize: 11, color: "var(--dim)" }}>
        {emptyLabel}
      </p>
    );
  }

  return (
    <div data-testid={testId} style={{ border: "1px solid var(--border)", background: "var(--panel)" }}>
      {records.map((r, i) => (
        <div
          key={`${r.ts}-${i}`}
          data-testid="log-row"
          data-level={r.level}
          data-service={r.service}
          style={{
            ...mono, fontSize: 11, display: "flex", gap: 12, padding: "6px 10px",
            borderTop: i === 0 ? "none" : "1px solid var(--border)", alignItems: "baseline",
          }}
        >
          <span style={{ color: "var(--dim)", whiteSpace: "nowrap" }}>
            {formatTs(r.ts, timeZone)}
          </span>
          <span
            style={{
              color: LEVEL_COLOR[r.level] ?? "var(--mute)",
              textTransform: "uppercase", letterSpacing: "0.08em",
              width: 62, flexShrink: 0,
            }}
          >
            {r.level}
          </span>
          <span style={{ color: "var(--mute)", width: 70, flexShrink: 0 }}>{r.service}</span>
          {/* pre-wrap: a record's message can carry an embedded traceback, and
              collapsing that to one line makes the useful ones unreadable. */}
          <span style={{ color: "var(--fg, inherit)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {r.message}
          </span>
        </div>
      ))}
    </div>
  );
}
