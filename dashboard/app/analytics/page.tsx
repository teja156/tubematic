"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { VideoPublication } from "@/lib/types";
import { AnalyticsCharts, type MonthViews } from "@/components/AnalyticsCharts";
import { SectionLabel } from "@/components/SectionLabel";
import { SpendCard } from "@/components/SpendCard";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate } from "@/lib/datetime";
import { accountLabel, platformLabel, type AccountName } from "@/lib/platforms";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

type Metrics = {
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
};

type AnalyticsRow = VideoPublication & Metrics & { title: string; fetched_at: string | null };

type Analytics = {
  totals: Metrics & { videos: number; publications: number };
  by_platform: Record<string, Metrics>;
  publications: AnalyticsRow[];
  // Optional: an API from before the graphs answers without them.
  by_month?: MonthViews[];
  timezone?: string;
};

/** Rows rendered at a time; more are added as the table's own box scrolls. */
const PAGE = 50;

const mono = { fontFamily: "var(--mono)" } as const;

const control = {
  ...mono, fontSize: 11, background: "var(--panel)", color: "var(--ink)",
  border: "1px solid var(--border)", padding: "6px 10px",
} as const;

type SortKey = "newest" | keyof Metrics;

const SORTS: { key: SortKey; label: string }[] = [
  { key: "newest", label: "Newest first" },
  { key: "views", label: "Most views" },
  { key: "likes", label: "Most likes" },
  { key: "comments", label: "Most comments" },
  { key: "shares", label: "Most shares" },
];

/** Highest first, and an unreported metric below a real 0 — "not reported"
 *  is not a smaller number. Array.sort is stable, so ties keep the API's
 *  newest-first order. */
function sortRows(rows: AnalyticsRow[], key: SortKey): AnalyticsRow[] {
  if (key === "newest") return rows;
  return [...rows].sort((a, b) => {
    const x = a[key], y = b[key];
    if (x === null || x === undefined) return y === null || y === undefined ? 0 : 1;
    if (y === null || y === undefined) return -1;
    return y - x;
  });
}

/** A metric that was never reported reads "—", never 0: "not reported" and
 *  "reported as zero" are different claims, and showing 0 for the first
 *  invents a datapoint. */
function metric(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : value.toLocaleString();
}

export default function AnalyticsPage() {
  const { timeZone } = useTimeZone();
  const [data, setData] = useState<Analytics | null>(null);
  const [platform, setPlatform] = useState("");
  const [account, setAccount] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [names, setNames] = useState<Record<string, AccountName>>({});
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  // Separate from `error` on purpose: load() clears `error` on success, and it
  // runs immediately after a refresh — so a partial-failure warning written
  // into `error` would be wiped by the very reload that follows it.
  const [refreshNote, setRefreshNote] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (platform) params.set("platform", platform);
    if (account) params.set("social_account_id", account);
    const query = params.toString();
    apiFetch(`/analytics${query ? `?${query}` : ""}`)
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) {
          setError(body?.error ?? "Could not load analytics.");
          return;
        }
        setError("");
        setData(body as Analytics);
      })
      .catch(() => setError("Could not reach the pipeline API."));
  }, [platform, account]);

  // Capture a snapshot now rather than waiting for the worker's hourly pass,
  // then re-read. Bounded by the per-account walk on the server: one feed call
  // per account however many videos have been published.
  //
  // Freshness still has a ceiling we do not control — this re-reads postforme's
  // view, and postforme polls the platforms on its own cadence.
  const refresh = useCallback(async () => {
    setRefreshing(true);
    setRefreshNote("");
    try {
      const r = await apiFetch("/analytics/refresh", { method: "POST" });
      const body = await r.json().catch(() => null);
      if (!r.ok) {
        setError(body?.error ?? "Could not refresh.");
        return;
      }
      // A 200 does not mean every account was read: the endpoint reports how
      // many feeds failed, and ignoring that count makes a refresh that
      // captured nothing look identical to one that worked.
      const failed = body?.errors ?? 0;
      const captured = body?.snapshots ?? 0;
      setRefreshNote(failed
        ? `${failed} account(s) unreachable — ${captured} snapshot(s) captured. `
          + "Some figures below may be stale."
        : "");
      load();
    } catch {
      setError("Could not reach the pipeline API.");
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  useEffect(() => {
    load();
  }, [load]);

  // Names for the account filter. `feeds=0` skips the per-account feed probe
  // the Socials page needs and this page does not. Any failure is silent:
  // the filter falls back to ids, which is what it showed before.
  useEffect(() => {
    apiFetch("/publishing/accounts?feeds=0")
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !Array.isArray(body)) return;
        const map: Record<string, AccountName> = {};
        for (const a of body) {
          if (a && typeof a.id === "string") {
            map[a.id] = { username: a.username || "", platform: a.platform || "" };
          }
        }
        setNames(map);
      })
      .catch(() => {});
  }, []);

  // Filter options come from the data itself rather than a second request —
  // an account with no published post has nothing to filter to anyway.
  const platforms = Object.keys(data?.by_platform ?? {});
  const accounts = new Map<string, string>();
  for (const p of data?.publications ?? []) {
    if (!accounts.has(p.social_account_id)) accounts.set(p.social_account_id, p.platform);
  }
  const rows = sortRows(data?.publications ?? [], sort);

  // The list grows without bound, so it renders a page at a time and adds one
  // when a sentinel row at the end of the table's own scroll box comes into
  // view. Every row is still loaded — the totals and graphs need them all —
  // so this bounds the DOM, not the payload. Without IntersectionObserver
  // nothing could ask for more, so everything renders.
  const [visible, setVisible] = useState(PAGE);
  const scrollBox = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLTableRowElement>(null);
  const lazy = typeof IntersectionObserver !== "undefined";
  const shown = lazy ? rows.slice(0, visible) : rows;
  const hasMore = shown.length < rows.length;

  useEffect(() => {
    setVisible(PAGE);
    scrollBox.current?.scrollTo?.({ top: 0 });
  }, [platform, account, sort, data]);

  // Re-armed after every page: a fresh observer reports at once if the
  // sentinel is still in view, which keeps a tall box filling up.
  useEffect(() => {
    const el = sentinel.current;
    if (!lazy || !hasMore || !el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setVisible((v) => v + PAGE);
    }, { root: scrollBox.current, rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [lazy, hasMore, visible]);

  return (
    <>
      <SectionLabel
        label="Analytics"
        count={`${data?.totals.videos ?? 0} Published`}
      />

      <Tabs defaultValue="videos">
        <TabsList
          style={{
            background: "var(--bg)", borderBottom: "1px solid var(--border)", borderRadius: 0,
            padding: 0, height: "auto", minHeight: 38, gap: 4, justifyContent: "flex-start",
            marginBottom: 20,
          }}
        >
          <TabsTrigger value="videos" data-testid="tab-videos">Videos</TabsTrigger>
          <TabsTrigger value="spend" data-testid="tab-spend">Spend</TabsTrigger>
        </TabsList>

        <TabsContent value="videos">
          {/* Graphs on the right beside everything else; below 1100px they
              drop in after the filters, which scope them too (globals.css). */}
          <div className="analytics-layout">
            <div style={{ gridArea: "head" }}>
              {error && (
                <div
                  data-testid="analytics-error"
                  style={{
                    ...mono, fontSize: 11, color: "var(--amber)", border: "1px solid var(--border)",
                    background: "var(--panel)", padding: "12px 14px", marginBottom: 20, maxWidth: 640,
                  }}
                >
                  {error}
                </div>
              )}

              {/* Totals */}
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 24 }}>
                {(["views", "likes", "comments", "shares"] as const).map((key) => (
                  <div
                    key={key}
                    data-testid={`total-${key}`}
                    style={{
                      border: "1px solid var(--border)", background: "var(--panel)",
                      padding: "12px 18px", minWidth: 110,
                    }}
                  >
                    <div style={{ ...mono, fontSize: 9, color: "var(--mute)", letterSpacing: "0.16em",
                                  textTransform: "uppercase" }}>
                      {key}
                    </div>
                    <div style={{ ...mono, fontSize: 20, color: "var(--ink)", fontWeight: 700 }}>
                      {metric(data?.totals[key])}
                    </div>
                  </div>
                ))}
              </div>

              {/* Filters */}
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
                            marginBottom: 20 }}>
                <select
                  data-testid="filter-platform"
                  value={platform}
                  onChange={(e) => setPlatform(e.target.value)}
                  style={control}
                >
                  <option value="">All platforms</option>
                  {platforms.map((p) => (
                    <option key={p} value={p}>{platformLabel(p)}</option>
                  ))}
                </select>
                <select
                  data-testid="filter-account"
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                  style={control}
                >
                  <option value="">All accounts</option>
                  {Array.from(accounts, ([id, plat]) => (
                    <option key={id} value={id}>{accountLabel(id, plat, names)}</option>
                  ))}
                </select>
                <select
                  aria-label="Sort by"
                  data-testid="sort-by"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortKey)}
                  style={control}
                >
                  {SORTS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                </select>
              </div>
            </div>

            <aside style={{ gridArea: "charts" }}>
              <AnalyticsCharts
                publications={data?.publications ?? []}
                byMonth={data?.by_month ?? []}
                timeZone={data?.timezone}
                names={names}
                platform={platform}
                account={account}
                onPlatform={setPlatform}
                onAccount={setAccount}
              />
            </aside>

            <div style={{ gridArea: "list", minWidth: 0 }}>
              {data && data.publications.length === 0 && (
                <p data-testid="analytics-empty" style={{ ...mono, fontSize: 11, color: "var(--dim)" }}>
                  Nothing published yet.
                </p>
              )}

              {/* The table scrolls inside its own box, both ways, so a long list
                  never drags the page (and the graphs) along with it. */}
              <div
                ref={scrollBox}
                data-testid="analytics-scroll"
                style={{ overflow: "auto", maxHeight: "min(70vh, 720px)" }}
              >
                <table style={{ ...mono, fontSize: 11, borderCollapse: "collapse", minWidth: 720,
                                width: "100%" }}>
                  <thead>
                    <tr style={{ color: "var(--mute)", textAlign: "left" }}>
                      {["Video", "Platform", "Views", "Likes", "Comments", "Shares", "Updated"].map((h) => (
                        <th key={h} style={{ padding: "8px 14px 8px 0", fontWeight: 400,
                                             textTransform: "uppercase", letterSpacing: "0.12em",
                                             fontSize: 9, position: "sticky", top: 0,
                                             background: "var(--bg)",
                                             boxShadow: "inset 0 -1px 0 var(--border)" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((row) => (
                      <tr key={row.id} data-testid={`analytics-row-${row.id}`}
                          style={{ borderTop: "1px solid var(--border)" }}>
                        <td style={{ padding: "9px 14px 9px 0", color: "var(--ink)", maxWidth: 320 }}>
                          {row.post_url ? (
                            <a href={row.post_url} target="_blank" rel="noreferrer"
                               style={{ color: "var(--blue)", textDecoration: "none" }}>
                              {row.title}
                            </a>
                          ) : row.title}
                        </td>
                        <td style={{ padding: "9px 14px 9px 0", color: "var(--dim)" }}>
                          {platformLabel(row.platform)}
                        </td>
                        <td style={{ padding: "9px 14px 9px 0" }}>{metric(row.views)}</td>
                        <td style={{ padding: "9px 14px 9px 0" }}>{metric(row.likes)}</td>
                        <td style={{ padding: "9px 14px 9px 0" }}>{metric(row.comments)}</td>
                        <td style={{ padding: "9px 14px 9px 0" }}>{metric(row.shares)}</td>
                        <td style={{ padding: "9px 14px 9px 0", color: "var(--mute)" }}>
                          {row.fetched_at ? formatDate(row.fetched_at, timeZone) : "not polled yet"}
                        </td>
                      </tr>
                    ))}
                    {hasMore && (
                      <tr ref={sentinel} data-testid="analytics-more">
                        <td colSpan={7} style={{ padding: "12px 0", color: "var(--mute)" }}>
                          Showing {shown.length} of {rows.length} — scroll for more
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {refreshNote && (
                <p data-testid="analytics-refresh-note"
                   style={{ ...mono, fontSize: 11, color: "var(--amber)", marginTop: 16, maxWidth: 640 }}>
                  {refreshNote}
                </p>
              )}

              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 18 }}>
                <button
                  type="button"
                  data-testid="refresh-analytics"
                  onClick={refresh}
                  disabled={refreshing}
                  style={{
                    ...mono, fontSize: 11, color: "var(--blue)", background: "var(--panel)",
                    border: "1px solid var(--border)", padding: "9px 14px",
                    cursor: refreshing ? "default" : "pointer", opacity: refreshing ? 0.5 : 1,
                  }}
                >
                  {refreshing ? "Refreshing…" : "Refresh metrics"}
                </button>
              </div>
              <p style={{ ...mono, fontSize: 10, color: "var(--mute)", marginTop: 10, maxWidth: 640 }}>
                Figures are snapshots, not live reads — the render worker captures one hourly. Refreshing
                takes a snapshot now, though how fresh the numbers are still depends on how often
                postforme itself reads each platform.
              </p>
            </div>
          </div>
        </TabsContent>

        {/* Mounted only while open, so the spend summary (and its ElevenLabs
            pool call) is fetched when someone looks at it, not on every visit. */}
        <TabsContent value="spend">
          <SpendCard />
        </TabsContent>
      </Tabs>
    </>
  );
}
