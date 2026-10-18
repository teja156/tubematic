"use client";

import type { Video, VideoStatus } from "@/lib/types";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDateTime, formatRelative, formatScheduled } from "@/lib/datetime";
import { isScored } from "@/lib/utils";

const STATUS_ACCENT: Record<VideoStatus, string> = {
  TOPIC_PROPOSED:           "#f5a623",
  TOPIC_APPROVED:           "#5fa3ff",
  TOPIC_REJECTED:           "#ff6b6b",
  SCRIPT_READY:             "#818cf8",
  VOICING:                  "#f48fb1",
  VOICE_READY:              "#818cf8",
  RENDER_QUEUED:            "#e879c8",
  RENDERING:                "#e879c8",
  VIDEO_READY:              "#ff9966",
  VIDEO_APPROVED:           "#ff6b6b",
  REVISION_REQUESTED:       "#ff9966",
  SCHEDULED:                "#38bdf8",
  PUBLISHING:               "#4ade80",
  PUBLISHED:                "#65d27a",
  FAILED:                   "#ff3b3b",
};

const STRATEGY_LABEL: Record<string, string> = {
  curriculum: "CURRICULUM",
  trending:   "TRENDING",
  mining:     "MINING",
  manual:     "MANUAL",
};

interface KanbanCardProps {
  video: Video;
  accent: string;
  onAction: (videoId: string, action: string, video: Video) => void;
  onOpenModal: (video: Video, tab?: string) => void;
}

export function KanbanCard({ video, accent, onAction, onOpenModal }: KanbanCardProps) {
  const showProgress = video.status === "VOICING" || video.status === "VOICE_READY" || video.status === "RENDER_QUEUED" || video.status === "RENDERING";
  const showThumb = video.status === "VIDEO_READY" || video.status === "VIDEO_APPROVED" || video.status === "SCHEDULED" || video.status === "PUBLISHING" || video.status === "PUBLISHED";
  const isProposed = video.status === "TOPIC_PROPOSED";
  const isScriptReady = video.status === "SCRIPT_READY";
  const isVideoReady = video.status === "VIDEO_READY";

  const { timeZone } = useTimeZone();
  const createdAgo = formatRelative(video.created_at, Date.now());
  const createdAgoTitle = formatDateTime(video.created_at, timeZone);

  return (
    <div
      data-testid={`kanban-card-${video.id}`}
      style={{
        background: "var(--panel-2)",
        border: "1px solid var(--border-2)",
        padding: 12,
        cursor: "grab",
        transition: "all .15s",
        position: "relative",
      }}
      onClick={() => onOpenModal(video)}
      onMouseEnter={(e) => {
        const el = e.currentTarget;
        el.style.borderColor = accent;
        el.style.transform = "translateY(-1px)";
        el.style.boxShadow = "0 4px 12px rgba(0,0,0,0.4)";
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget;
        el.style.borderColor = "var(--border-2)";
        el.style.transform = "none";
        el.style.boxShadow = "none";
      }}
    >
      {/* Optional thumbnail strip */}
      {showThumb && (
        <div
          style={{
            position: "relative",
            margin: "-12px -12px 10px",
            height: 96,
            background: `repeating-linear-gradient(45deg, rgba(255,255,255,0.02) 0 8px, transparent 8px 16px), linear-gradient(135deg, color-mix(in oklab, ${accent} 28%, #0a0d14), #0a0d14)`,
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* CSS play triangle */}
          <div
            style={{
              width: 0,
              height: 0,
              borderLeft: `14px solid color-mix(in oklab, ${accent} 70%, white)`,
              borderTop: "9px solid transparent",
              borderBottom: "9px solid transparent",
              filter: `drop-shadow(0 0 8px color-mix(in oklab, ${accent} 50%, transparent))`,
            }}
          />
          {video.status === "PUBLISHING" && (
            <div style={{ position: "absolute", bottom: 6, right: 8, fontFamily: "var(--mono)", fontSize: 10, background: "rgba(0,0,0,0.7)", color: "var(--ink)", padding: "1px 5px", letterSpacing: "0.04em" }}>
              UPLOADING
            </div>
          )}
          {video.status === "PUBLISHED" && (
            <div style={{ position: "absolute", bottom: 6, right: 8, fontFamily: "var(--mono)", fontSize: 10, background: "rgba(0,0,0,0.7)", color: "var(--ink)", padding: "1px 5px", letterSpacing: "0.04em" }}>
              ▶ LIVE
            </div>
          )}
        </div>
      )}

      {/* Header: dot + score */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ width: 7, height: 7, background: accent, boxShadow: `0 0 5px ${accent}`, display: "inline-block", flexShrink: 0 }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 10.5, fontWeight: 700, color: "var(--ink-2)" }}>
          {isScored(video.producibility_score)
            ? <>{video.producibility_score}<span style={{ color: "var(--mute)" }}>/10</span></>
            : "—"}
        </span>
      </div>

      {/* Title — the short display name, falling back to the full topic for
          rows written before the two carried different text. Clamped to two
          lines either way, so a long topic can never turn the card into a wall
          of text; the full text is on hover and in the modal's Topic tab. */}
      <div
        title={video.topic}
        style={{ fontFamily: "var(--sans)", fontSize: 13.5, fontWeight: 600, color: "var(--ink)", lineHeight: 1.3, letterSpacing: "-0.005em", marginBottom: 8, textWrap: "pretty", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" } as React.CSSProperties}
      >
        {video.title || video.topic}
      </div>

      {/* When a scheduled post goes out, in the zone it was picked in. */}
      {video.status === "SCHEDULED" && video.scheduled_at && (
        <div
          data-testid={`scheduled-at-${video.id}`}
          style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: STATUS_ACCENT.SCHEDULED, lineHeight: 1.4, marginBottom: 8 }}
        >
          ⏱ {formatScheduled(video.scheduled_at, video.scheduled_timezone || timeZone)}
        </div>
      )}

      {/* Meta */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--mono)", fontSize: 9.5, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--dim)" }}>
        {video.strategy && (
          <span style={{ padding: "1px 5px", border: "1px solid var(--border-2)", background: "rgba(255,255,255,0.02)", color: "var(--ink-2)" }}>
            {STRATEGY_LABEL[video.strategy] ?? video.strategy}
          </span>
        )}
        {video.status === "PUBLISHED" && (
          <span style={{ color: "var(--green)" }}>LIVE</span>
        )}
        {video.agent_stuck_at && !video.archived_at && (
          <span
            data-testid={`kanban-card-stuck-${video.id}`}
            title="The scheduled agent stopped retrying this video. Open it to retry."
            style={{ color: "var(--amber)" }}
          >
            STUCK
          </span>
        )}
        <span style={{ marginLeft: "auto", opacity: 0.6 }} title={createdAgoTitle}>{createdAgo}</span>
      </div>

      {/* Progress bar */}
      {showProgress && (
        <div style={{ marginTop: 10, height: 4, background: "rgba(255,255,255,0.04)", position: "relative", overflow: "hidden" }}>
          <div
            style={{
              height: "100%",
              width: "50%",
              background: accent,
              boxShadow: `0 0 5px ${accent}`,
              position: "relative",
            }}
          >
            <div
              style={{
                content: "",
                position: "absolute",
                inset: 0,
                background: "repeating-linear-gradient(45deg, transparent 0, transparent 3px, rgba(0,0,0,0.18) 3px, rgba(0,0,0,0.18) 6px)",
              }}
            />
          </div>
        </div>
      )}

      {/* Action buttons (proposed only) */}
      {isProposed && (
        <div style={{ display: "flex", gap: 6, marginTop: 10 }} onClick={(e) => e.stopPropagation()}>
          <button
            className="tm-btn"
            onClick={() => onAction(video.id, "approve-topic", video)}
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.06em",
              padding: "6px 8px",
              color: "var(--green)",
              border: "1px solid rgba(101,210,122,0.32)",
              background: "rgba(101,210,122,0.06)",
              cursor: "pointer",
              textTransform: "uppercase",
              transition: "all .12s",
            }}
          >
            Approve
          </button>
          <button
            className="tm-btn"
            onClick={() => onAction(video.id, "reject-topic", video)}
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.06em",
              padding: "6px 8px",
              color: "var(--ink-2)",
              border: "1px solid var(--border-2)",
              background: "transparent",
              cursor: "pointer",
              textTransform: "uppercase",
              transition: "all .12s",
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget;
              el.style.color = "var(--red)";
              el.style.borderColor = "rgba(255,107,107,0.42)";
              el.style.background = "rgba(255,107,107,0.06)";
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget;
              el.style.color = "var(--ink-2)";
              el.style.borderColor = "var(--border-2)";
              el.style.background = "transparent";
            }}
          >
            Reject
          </button>
        </div>
      )}

      {/* Script ready buttons */}
      {isScriptReady && (
        <div style={{ display: "flex", gap: 6, marginTop: 10 }} onClick={(e) => e.stopPropagation()}>
          <button
            className="tm-btn"
            onClick={() => onOpenModal(video, "script")}
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.06em",
              padding: "6px 8px",
              color: "var(--ink-2)",
              border: "1px solid var(--border-2)",
              background: "transparent",
              cursor: "pointer",
              textTransform: "uppercase",
              transition: "all .12s",
            }}
          >
            Read
          </button>
          <button
            className="tm-btn"
            onClick={() => onAction(video.id, "approve-script", video)}
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.06em",
              padding: "6px 8px",
              color: "var(--green)",
              border: "1px solid rgba(101,210,122,0.32)",
              background: "rgba(101,210,122,0.06)",
              cursor: "pointer",
              textTransform: "uppercase",
              transition: "all .12s",
            }}
          >
            Approve
          </button>
        </div>
      )}

      {/* Video ready buttons */}
      {isVideoReady && (
        <div style={{ display: "flex", gap: 6, marginTop: 10 }} onClick={(e) => e.stopPropagation()}>
          <button
            className="tm-btn"
            onClick={() => onOpenModal(video, "video")}
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.06em",
              padding: "6px 8px",
              color: "var(--ink-2)",
              border: "1px solid var(--border-2)",
              background: "transparent",
              cursor: "pointer",
              textTransform: "uppercase",
              transition: "all .12s",
            }}
          >
            Watch
          </button>
          <button
            className="tm-btn"
            onClick={() => onAction(video.id, "approve-video", video)}
            style={{
              flex: 1,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.06em",
              padding: "6px 8px",
              color: "var(--green)",
              border: "1px solid rgba(101,210,122,0.32)",
              background: "rgba(101,210,122,0.06)",
              cursor: "pointer",
              textTransform: "uppercase",
              transition: "all .12s",
            }}
          >
            Approve
          </button>
        </div>
      )}
    </div>
  );
}

export { STATUS_ACCENT };
