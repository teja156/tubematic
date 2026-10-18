"use client";

import { accountLabel, platformLabel, type AccountName } from "@/lib/platforms";

// The Analytics page's graphs (TMDEV-113): views per platform, per account,
// and views gained per month. Plain bars, no charting library — three
// single-series charts do not need one, and plain elements test in happy-dom.
//
// The platform and account graphs are summed here from the rows the page
// already holds, rather than from the API's `by_platform`: that aggregate
// folds an unreported count into 0, and a graph must not draw "not reported"
// as "nobody watched".

export type MonthViews = { month: string; views: number };

type Row = { social_account_id: string; platform: string; views: number | null };

type Props = {
  publications: Row[];
  byMonth: MonthViews[];
  timeZone?: string;
  names: Record<string, AccountName>;
  platform: string;
  account: string;
  onPlatform: (platform: string) => void;
  onAccount: (id: string) => void;
};

const mono = { fontFamily: "var(--mono)" } as const;

const EMPTY = "No views reported yet";

type Bar = { key: string; label: string; views: number | null };

/** Sum per key. A key stays null until one of its rows reports a count. */
function sumBy(rows: Row[], keyOf: (r: Row) => string, labelOf: (r: Row) => string): Bar[] {
  const bars = new Map<string, Bar>();
  for (const r of rows) {
    const key = keyOf(r);
    const bar = bars.get(key) ?? { key, label: labelOf(r), views: null };
    if (r.views !== null && r.views !== undefined) bar.views = (bar.views ?? 0) + r.views;
    bars.set(key, bar);
  }
  // Highest first, unreported last; Array.sort is stable for ties.
  return [...bars.values()].sort((a, b) =>
    a.views === null ? (b.views === null ? 0 : 1) : b.views === null ? -1 : b.views - a.views);
}

function Card({ title, testId, children }: {
  title: string; testId: string; children: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      style={{ border: "1px solid var(--border)", background: "var(--panel)", padding: "14px 16px" }}
    >
      <h3 style={{ ...mono, fontSize: 9, color: "var(--mute)", letterSpacing: "0.16em",
                   textTransform: "uppercase", fontWeight: 400, margin: "0 0 12px" }}>
        {title}
      </h3>
      {children}
    </section>
  );
}

function Empty() {
  return <p style={{ ...mono, fontSize: 11, color: "var(--dim)", margin: 0 }}>{EMPTY}</p>;
}

/** Horizontal bars; each is a button that toggles the filter it names. */
function BarList({ bars, kind, selected, onSelect }: {
  bars: Bar[]; kind: string; selected: string; onSelect: (key: string) => void;
}) {
  if (bars.length === 0) return <Empty />;
  const max = Math.max(0, ...bars.map((b) => b.views ?? 0));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {bars.map((b) => {
        const on = b.key === selected;
        const value = b.views === null ? "—" : b.views.toLocaleString();
        return (
          <button
            key={b.key}
            type="button"
            className="chart-bar"
            data-testid={`bar-${kind}-${b.key}`}
            data-key={b.key}
            aria-pressed={on}
            title={`${b.label}: ${b.views === null ? "not reported" : `${value} views`}`
              + ` — click to ${on ? "clear the filter" : "filter to it"}`}
            onClick={() => onSelect(on ? "" : b.key)}
            // The label gets a line of its own: beside the bar, the column is
            // too narrow for "<account id> (<Platform>)" and cut the platform off.
            style={{
              ...mono, fontSize: 11, textAlign: "left", cursor: "pointer",
              display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto",
              alignItems: "center", columnGap: 10, rowGap: 4, padding: "6px 6px",
              background: on ? "var(--panel-2)" : "transparent",
              border: "1px solid", borderColor: on ? "var(--border-hot)" : "transparent",
              color: on ? "var(--ink)" : "var(--ink-2)", fontWeight: on ? 700 : 400,
            }}
          >
            <span style={{ gridColumn: "1 / -1", overflow: "hidden", textOverflow: "ellipsis",
                           whiteSpace: "nowrap" }}>
              {b.label}
            </span>
            <span style={{ height: 10 }}>
              {b.views !== null && (
                <span
                  data-testid="bar-fill"
                  className="chart-fill"
                  style={{
                    display: "block", height: "100%", borderRadius: "0 4px 4px 0",
                    width: `${max > 0 ? Math.round((b.views / max) * 100) : 0}%`,
                    background: on ? "var(--amber)" : "var(--blue)",
                  }}
                />
              )}
            </span>
            <span style={{ color: b.views === null ? "var(--mute)" : "inherit" }}>{value}</span>
          </button>
        );
      })}
    </div>
  );
}

function monthName(month: string, style: "short" | "long") {
  const [y, m] = month.split("-").map(Number);
  // Pinned to UTC: "2026-09" is a label, not an instant, and must not shift.
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-US", {
    month: style, ...(style === "long" ? { year: "numeric" } : {}), timeZone: "UTC",
  });
}

/** One column per month. A month where views fell keeps its negative figure
 *  in the label and draws no height — there is no bar below the baseline. */
function MonthColumns({ months }: { months: MonthViews[] }) {
  if (months.length === 0) return <Empty />;
  const max = Math.max(0, ...months.map((m) => m.views));
  return (
    <div>
      <div style={{ ...mono, fontSize: 9, color: "var(--mute)", marginBottom: 4 }}>
        {max.toLocaleString()}
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 120,
                    borderBottom: "1px solid var(--border-2)", borderTop: "1px solid var(--border)" }}>
        {months.map((m) => (
          <div
            key={m.month}
            tabIndex={0}
            className="chart-bar"
            data-testid={`month-${m.month}`}
            title={`${monthName(m.month, "long")}: ${m.views.toLocaleString()} views gained`}
            style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end",
                     justifyContent: "center" }}
          >
            <div
              data-testid="month-fill"
              className="chart-fill"
              style={{
                width: "100%", maxWidth: 24, borderRadius: "4px 4px 0 0", background: "var(--blue)",
                height: `${max > 0 && m.views > 0 ? Math.round((m.views / max) * 100) : 0}%`,
              }}
            />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
        {months.map((m) => (
          <div key={m.month} style={{ ...mono, flex: 1, fontSize: 9, color: "var(--mute)",
                                       textAlign: "center", overflow: "hidden" }}>
            {monthName(m.month, "short")}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AnalyticsCharts({
  publications, byMonth, timeZone, names, platform, account, onPlatform, onAccount,
}: Props) {
  const byPlatform = sumBy(publications, (r) => r.platform, (r) => platformLabel(r.platform));
  const byAccount = sumBy(publications, (r) => r.social_account_id,
                          (r) => accountLabel(r.social_account_id, r.platform, names));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Card title="Views per platform" testId="chart-platform">
        <BarList bars={byPlatform} kind="platform" selected={platform} onSelect={onPlatform} />
      </Card>
      <Card title="Views per account" testId="chart-account">
        <BarList bars={byAccount} kind="account" selected={account} onSelect={onAccount} />
      </Card>
      <Card title="Views gained per month" testId="chart-month">
        <MonthColumns months={byMonth} />
        <p style={{ ...mono, fontSize: 10, color: "var(--mute)", margin: "10px 0 0" }}>
          Months in {timeZone || "UTC"}. A post&apos;s views from before it was first read
          count in the month it was first read.
        </p>
      </Card>
    </div>
  );
}
