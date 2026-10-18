import type { VideoStatus } from "@/lib/types";

const STATUS_CONFIG: Record<VideoStatus, { label: string; color: string }> = {
  TOPIC_PROPOSED:          { label: "Topic Proposed",      color: "#f5a623" },
  TOPIC_APPROVED:          { label: "Topic Approved",      color: "#5fa3ff" },
  TOPIC_REJECTED:          { label: "Topic Rejected",      color: "#ff6b6b" },
  SCRIPT_READY:            { label: "Script Ready",        color: "#818cf8" },
  VOICING:                 { label: "Voicing",             color: "#f48fb1" },
  VOICE_READY:             { label: "Voice Ready",         color: "#818cf8" },
  RENDER_QUEUED:           { label: "Render Queued",       color: "#e879c8" },
  RENDERING:               { label: "Rendering",           color: "#e879c8" },
  VIDEO_READY:             { label: "Video Ready",         color: "#ff9966" },
  VIDEO_APPROVED:          { label: "Video Approved",      color: "#ff6b6b" },
  REVISION_REQUESTED:      { label: "Revision Requested",  color: "#ff9966" },
  SCHEDULED:               { label: "Scheduled",           color: "#38bdf8" },
  PUBLISHING:              { label: "Publishing",          color: "#4ade80" },
  PUBLISHED:               { label: "Published",           color: "#65d27a" },
  FAILED:                  { label: "Failed",              color: "#ff3b3b" },
};

export function StatusBadge({ status }: { status: VideoStatus }) {
  const config = STATUS_CONFIG[status] ?? { label: status, color: "#939cae" /* Keep in sync: --dim in globals.css */ };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: config.color, boxShadow: `0 0 4px ${config.color}`, flexShrink: 0, display: "inline-block" }} />
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.14em", lineHeight: 1, color: config.color }}>
        {config.label}
      </span>
    </span>
  );
}
