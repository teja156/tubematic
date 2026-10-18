"use client";

import type { Stats, VideoStatus } from "@/lib/types";

const CARDS: Array<{
  label: string;
  sub: string;
  id: string;
  statuses: VideoStatus[];
  accent: string;
  spark: string;
}> = [
  {
    id: "01",
    label: "Topics Awaiting",
    sub: "Need your review",
    statuses: ["TOPIC_PROPOSED"],
    accent: "var(--amber)",
    spark: "▁▂▃▅▇",
  },
  {
    id: "02",
    label: "Scripts Ready",
    sub: "Pending approval",
    statuses: ["SCRIPT_READY"],
    accent: "var(--indigo)",
    spark: "▂▃▂▃▅",
  },
  {
    id: "03",
    label: "Videos Ready",
    sub: "Ready to publish",
    statuses: ["VIDEO_READY"],
    accent: "var(--green)",
    spark: "▃▅▇▆▇",
  },
  {
    id: "04",
    label: "In Pipeline",
    sub: "Processing now",
    statuses: [
      "TOPIC_APPROVED",
      "VOICING",
      "VOICE_READY",
      "RENDER_QUEUED",
      "RENDERING",
      "VIDEO_APPROVED",
      "SCHEDULED",
      "PUBLISHING",
    ],
    accent: "var(--blue)",
    spark: "▇▇▆▇▇",
  },
  {
    id: "05",
    label: "Published",
    sub: "Live on the channel",
    statuses: ["PUBLISHED"],
    accent: "var(--mint)",
    spark: "▅▆▇▇█",
  },
  {
    id: "06",
    label: "Failed",
    sub: "Unrecoverable failures",
    statuses: ["FAILED"],
    accent: "var(--red)",
    spark: "▁▁▂▁▁",
  },
];

interface SummaryStripProps {
  stats: Stats;
}

export function SummaryStrip({ stats }: SummaryStripProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(0, 1fr))", gap: 14 }}>
      {CARDS.map(({ id, label, sub, statuses, accent, spark }) => {
        const count = statuses.reduce((sum, s) => sum + (stats[s] ?? 0), 0);
        return (
          <div
            key={id}
            data-testid={`summary-tile-${id}`}
            style={{
              position: "relative",
              background: "var(--panel)",
              border: "1px solid var(--border)",
              padding: "18px 18px 16px",
              minHeight: 116,
              overflow: "hidden",
              cursor: "pointer",
              transition: "border-color .15s, background .15s",
            }}
            className="stat-card"
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--border-hot)";
              (e.currentTarget as HTMLElement).style.background = "var(--panel-2)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--border)";
              (e.currentTarget as HTMLElement).style.background = "var(--panel)";
            }}
          >
            {/* Corner ticks */}
            <div
              style={{
                position: "absolute",
                top: 6,
                left: 6,
                width: 8,
                height: 8,
                borderTop: "1px solid var(--mute)",
                borderLeft: "1px solid var(--mute)",
              }}
            />
            <div
              style={{
                position: "absolute",
                bottom: 6,
                right: 6,
                width: 8,
                height: 8,
                borderBottom: "1px solid var(--mute)",
                borderRight: "1px solid var(--mute)",
              }}
            />

            {/* Spark */}
            <div
              style={{
                position: "absolute",
                right: 10,
                top: 12,
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "0.16em",
                color: accent,
                opacity: 0.7,
              }}
            >
              {spark}
            </div>

            {/* Big number */}
            <div
              data-testid={`tile-count-${id}`}
              style={{
                fontFamily: "var(--display)",
                fontSize: 56,
                lineHeight: 0.9,
                fontWeight: 400,
                color: accent,
                textShadow: `0 0 12px color-mix(in oklab, ${accent} 35%, transparent)`,
                letterSpacing: "-0.01em",
              }}
            >
              {count}
            </div>

            {/* Title */}
            <div
              style={{
                marginTop: 12,
                fontFamily: "var(--mono)",
                fontSize: 13,
                fontWeight: 700,
                letterSpacing: "0.02em",
                color: "var(--ink)",
              }}
            >
              {label}
            </div>

            {/* Subtitle */}
            <div
              style={{
                marginTop: 4,
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--dim)",
                letterSpacing: "0.02em",
              }}
            >
              {sub}
            </div>

            {/* ID stamp */}
            <div
              style={{
                position: "absolute",
                bottom: 8,
                left: 18,
                fontFamily: "var(--mono)",
                fontSize: 9,
                letterSpacing: "0.18em",
                color: "var(--mute)",
                textTransform: "uppercase",
              }}
            >
              // {id}
            </div>
          </div>
        );
      })}
    </div>
  );
}
