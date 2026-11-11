"use client";

// How one post is doing, from its latest snapshot (TMDEV-212): the four
// counts and the watch figures. Shown in the video window's Analytics tab.
//
// A figure the platform did not report reads "not reported", never 0. TikTok
// reports counts only, Instagram no stayed-to-watch, YouTube no reach or
// saves, so every post has some.

import type { VideoPublication } from "@/lib/types";
import { formatDateTime } from "@/lib/datetime";
import { formatShare, formatWatchSeconds } from "@/lib/format";

const NOT_REPORTED = "not reported";

function count(value: number | null | undefined): string {
  return value === null || value === undefined ? NOT_REPORTED : value.toLocaleString();
}

function watch(text: string): string {
  return text === "—" ? NOT_REPORTED : text;
}

export function PublicationFigures({ pub, timeZone, tzLabel }: {
  pub: VideoPublication; timeZone: string; tzLabel: string;
}) {
  // An API from before these fields sends none of them: show nothing rather
  // than a card of "not reported".
  if (pub.status !== "PUBLISHED" || pub.fetched_at === undefined) return null;

  if (!pub.fetched_at) {
    return (
      <p data-testid={`publication-figures-${pub.id}`}
         style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", marginTop: 10 }}>
        No figures read yet. The worker reads them every hour.
      </p>
    );
  }

  const figures: [string, string][] = [
    ["Views", count(pub.views)],
    ["Likes", count(pub.likes)],
    ["Comments", count(pub.comments)],
    ["Shares", count(pub.shares)],
    ["Watched", watch(formatWatchSeconds(pub.avg_watch_secs))],
    ["% watched", watch(formatShare(pub.watched_pct))],
    ["Stayed", watch(formatShare(pub.stayed_pct))],
    ["Reach", count(pub.reach)],
    ["Saves", count(pub.saves)],
  ];

  return (
    <div data-testid={`publication-figures-${pub.id}`} style={{ marginTop: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))",
                    gap: "10px 14px" }}>
        {figures.map(([label, value]) => (
          <div key={label} data-testid={`figure-${pub.id}-${label}`}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--mute)",
                          letterSpacing: "0.14em", textTransform: "uppercase" }}>
              {label}
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11.5,
                          color: value === NOT_REPORTED ? "var(--mute)" : "var(--ink)" }}>
              {value}
            </div>
          </div>
        ))}
      </div>
      <p style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", marginTop: 10 }}>
        Read {formatDateTime(pub.fetched_at, timeZone)} {tzLabel}
      </p>
    </div>
  );
}
