"use client";

import type { Video, VideoStatus } from "@/lib/types";
import { KanbanColumn } from "@/components/KanbanColumn";
import { KanbanCard } from "@/components/KanbanCard";

// `extraStatuses` folds a transient status into an adjacent column's video
// list without giving it a column of its own — used for RENDER_QUEUED, which
// shares the "Rendering" column's in-progress bucket (it's worker-owned and
// typically only sits there for one poll interval).
const MAIN_COLUMNS: Array<{ status: VideoStatus; label: string; accent: string; extraStatuses?: VideoStatus[] }> = [
  { status: "TOPIC_PROPOSED",   label: "Topic Proposed",  accent: "#f5a623" },
  { status: "TOPIC_APPROVED",   label: "Topic Approved",  accent: "#5fa3ff" },
  { status: "SCRIPT_READY",     label: "Script Ready",    accent: "#818cf8" },
  { status: "VOICING",          label: "Voicing",         accent: "#f48fb1" },
  { status: "VOICE_READY",      label: "Voice Ready",     accent: "#818cf8" },
  { status: "RENDERING",        label: "Rendering",       accent: "#e879c8", extraStatuses: ["RENDER_QUEUED"] },
  { status: "VIDEO_READY",      label: "Video Ready",     accent: "#ff9966" },
  { status: "VIDEO_APPROVED",   label: "Video Approved",  accent: "#ff6b6b" },
  { status: "SCHEDULED",        label: "Scheduled",       accent: "#38bdf8" },
  { status: "PUBLISHING",       label: "Publishing",      accent: "#4ade80" },
  { status: "PUBLISHED",        label: "Published",       accent: "#65d27a" },
];

const SIDE_COLUMNS: Array<{ status: VideoStatus; label: string; accent: string; extraStatuses?: VideoStatus[] }> = [
  { status: "TOPIC_REJECTED",     label: "Rejected",           accent: "#ff6b6b" },
  { status: "REVISION_REQUESTED", label: "Revision Requested", accent: "#ff9966" },
  { status: "FAILED",             label: "Failed",             accent: "#ff3b3b" },
];

interface KanbanBoardProps {
  videos: Video[];
  onAction: (videoId: string, action: string, video: Video) => void;
  onOpenModal: (video: Video, tab?: string) => void;
}

export function KanbanBoard({ videos, onAction, onOpenModal }: KanbanBoardProps) {
  const byStatus = (status: VideoStatus, extraStatuses?: VideoStatus[]) =>
    videos.filter((v) => v.status === status || extraStatuses?.includes(v.status));

  return (
    <div
      className="kanban-scroll"
      style={{
        overflowX: "auto",
        overflowY: "hidden",
        paddingBottom: 16,
        margin: "0 calc(-1 * var(--gutter))",
        paddingLeft: "var(--gutter)",
        paddingRight: "var(--gutter)",
      }}
    >
      <div
        style={{
          display: "grid",
          gridAutoFlow: "column",
          gridAutoColumns: 256,
          gap: 14,
          minHeight: 540,
        }}
      >
        {[...MAIN_COLUMNS, ...SIDE_COLUMNS].map(({ status, label, accent, extraStatuses }) => (
          <KanbanColumn
            key={status}
            status={status}
            label={label}
            accent={accent}
            videos={byStatus(status, extraStatuses)}
            onAction={onAction}
            onOpenModal={onOpenModal}
          />
        ))}
      </div>
    </div>
  );
}
