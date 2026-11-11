"use client";

// Watch figures by group (TMDEV-212): seconds watched, share of the video
// watched and stayed to watch, for one account at a time, grouped each way
// the API returns (visual style, script profile, domain, script length,
// formula and opening). Lives on the Analytics page's Watch time tab.
//
// One account at a time because a platform counts a view and a watched second
// its own way and every account has its own audience. The API picks the
// account with the most posts when none is named, so the tab opens on
// something worth reading.

import { useEffect, useState } from "react";
import type { WatchGroup, WatchMeasure, WatchTime } from "@/lib/types";
import { formatShare, formatWatchSeconds } from "@/lib/format";
import { accountLabel, platformLabel, type AccountName } from "@/lib/platforms";

const mono = { fontFamily: "var(--mono)" } as const;

const control = {
  ...mono, fontSize: 11, background: "var(--panel)", color: "var(--ink)",
  border: "1px solid var(--border)", padding: "6px 10px",
} as const;

const cell = { padding: "9px 18px 9px 0" } as const;

const MEASURES = [
  { key: "avg_watch_secs", label: "Watched", format: formatWatchSeconds },
  { key: "watched_pct", label: "% watched", format: formatShare },
  { key: "stayed_pct", label: "Stayed", format: formatShare },
] as const;

function Figure({ measure, format, videos, minGroup, testId }: {
  measure: WatchMeasure; format: (v: number | null) => string; videos: number;
  minGroup: number; testId: string;
}) {
  // Fewer reporting videos than the group has: say how many, since the
  // figure speaks for those alone. Under the threshold it is as hard to read
  // as a small group, and says so in words, since colour alone is easy to miss.
  const partial = measure.n > 0 && measure.n !== videos;
  const thin = partial && measure.n < minGroup;
  return (
    <td data-testid={testId} style={{ ...cell, color: thin ? "var(--dim)" : "var(--ink)" }}>
      {format(measure.median)}
      {partial && (
        <span style={{ color: "var(--mute)", fontSize: 10 }}>
          {" "}({measure.n} of {videos}{thin ? ", too few" : ""})
        </span>
      )}
    </td>
  );
}

export function WatchTimePanel({ names }: { names: Record<string, AccountName> }) {
  const [data, setData] = useState<WatchTime | null>(null);
  const [account, setAccount] = useState("");
  const [dimension, setDimension] = useState("visual_style");
  const [error, setError] = useState("");

  useEffect(() => {
    let stale = false;
    const query = account ? `?social_account_id=${encodeURIComponent(account)}` : "";
    fetch(`/api/proxy/analytics/watch-time${query}`, { cache: "no-store" })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (stale) return;
        if (!r.ok || !body || !Array.isArray(body.dimensions)) {
          setError(body?.error ?? "Could not load watch figures.");
          return;
        }
        setError("");
        setData(body as WatchTime);
      })
      .catch(() => { if (!stale) setError("Could not reach the pipeline API."); });
    return () => { stale = true; };
  }, [account]);

  // The table shows an account's figures only while it is the account the
  // select names. Between a pick and its answer, and after a pick that failed,
  // the last answer belongs to another account and is not drawn.
  const shown = data && (!account || data.social_account_id === account) ? data : null;
  const minGroup = data?.min_group ?? 20;
  const groups: WatchGroup[] =
    shown?.dimensions.find((d) => d.id === dimension)?.groups ?? [];
  const nothingReported = groups.length > 0
    && groups.every((g) => MEASURES.every((m) => g[m.key].n === 0));

  return (
    <div data-testid="watch-time" style={{ maxWidth: 980 }}>
      {error && (
        <div data-testid="watch-time-error"
             style={{ ...mono, fontSize: 11, color: "var(--amber)", border: "1px solid var(--border)",
                      background: "var(--panel)", padding: "12px 14px", marginBottom: 20,
                      maxWidth: 640 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
                    marginBottom: 20 }}>
        <label style={{ ...mono, fontSize: 10, color: "var(--mute)", display: "flex",
                        gap: 8, alignItems: "center" }}>
          <span>ACCOUNT</span>
          <select data-testid="watch-account" value={account || data?.social_account_id || ""}
                  onChange={(e) => { setError(""); setAccount(e.target.value); }} style={control}>
            {(data?.accounts ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {accountLabel(a.id, a.platform, names)}, {a.videos} video{a.videos === 1 ? "" : "s"}
              </option>
            ))}
          </select>
        </label>
        <label style={{ ...mono, fontSize: 10, color: "var(--mute)", display: "flex",
                        gap: 8, alignItems: "center" }}>
          <span>GROUP BY</span>
          <select data-testid="watch-group-by" value={dimension}
                  onChange={(e) => setDimension(e.target.value)} style={control}>
            {(data?.dimensions ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.label}</option>
            ))}
          </select>
        </label>
      </div>

      {data && data.accounts.length === 0 && (
        <p data-testid="watch-time-empty" style={{ ...mono, fontSize: 11, color: "var(--dim)" }}>
          Nothing published yet.
        </p>
      )}

      {groups.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ ...mono, fontSize: 11, borderCollapse: "collapse", minWidth: 560,
                          width: "100%" }}>
            <thead>
              <tr style={{ color: "var(--mute)", textAlign: "left" }}>
                {["Group", "Videos", ...MEASURES.map((m) => m.label), ""].map((h, i) => (
                  <th key={i} style={{ padding: "8px 18px 8px 0", fontWeight: 400, fontSize: 9,
                                       textTransform: "uppercase", letterSpacing: "0.12em",
                                       boxShadow: "inset 0 -1px 0 var(--border)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                const small = g.videos < minGroup;
                return (
                  <tr key={g.key} data-testid={`watch-group-${g.key}`}
                      style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ ...cell, color: small ? "var(--dim)" : "var(--ink)", maxWidth: 320 }}>
                      {g.label}
                    </td>
                    <td style={{ ...cell, color: "var(--dim)" }}>{g.videos}</td>
                    {MEASURES.map((m) => (
                      <Figure key={m.key} measure={g[m.key]} format={m.format} videos={g.videos}
                              minGroup={minGroup} testId={`watch-${m.key}-${g.key}`} />
                    ))}
                    <td style={{ ...cell, paddingRight: 0 }}>
                      {small && (
                        <span data-testid={`watch-small-${g.key}`}
                              title={`Fewer than ${minGroup} videos: one unusual video can move this figure.`}
                              style={{ fontSize: 9, letterSpacing: "0.12em", color: "var(--amber)",
                                       whiteSpace: "nowrap" }}>
                          TOO FEW
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {nothingReported && shown && (
        <p data-testid="watch-time-unreported"
           style={{ ...mono, fontSize: 11, color: "var(--dim)", marginTop: 16, maxWidth: 640 }}>
          {platformLabel(shown.platform)} has reported no watch figures for these posts.
        </p>
      )}

      {data && data.accounts.length > 0 && (
        <p style={{ ...mono, fontSize: 10, color: "var(--mute)", marginTop: 18, maxWidth: 640,
                    lineHeight: 1.6 }}>
          Each figure is the median across the group&apos;s videos, read from every post&apos;s
          latest snapshot. Watched is the average length of a view, % watched is that as a share
          of the video, and Stayed is the share of views that kept watching. A dash means the
          platform did not report it. Groups under {minGroup} videos are marked TOO FEW, because
          one unusual video can move their figure. Compare groups inside one account only:
          platforms count views and watch time differently.
        </p>
      )}
    </div>
  );
}
