"use client";

import { useState } from "react";
import type { Video, VideoStatus } from "@/lib/types";
import { KanbanCard } from "@/components/KanbanCard";

interface KanbanColumnProps {
  status: VideoStatus;
  label: string;
  accent: string;
  videos: Video[];
  onAction: (videoId: string, action: string, video: Video) => void;
  onOpenModal: (video: Video, tab?: string) => void;
}

export function KanbanColumn({ status, label, accent, videos, onAction, onOpenModal }: KanbanColumnProps) {
  const [active, setActive] = useState(false);

  return (
    <div
      data-testid={`kanban-col-${status}`}
      style={{
        background: "var(--panel)",
        border: `1px solid ${active ? accent : "var(--border)"}`,
        display: "flex",
        flexDirection: "column",
        minHeight: 540,
        width: 256,
        flexShrink: 0,
        position: "relative",
        transition: "border-color .12s",
        boxShadow: active
          ? `0 0 0 1px color-mix(in oklab, ${accent} 28%, transparent), 0 0 30px color-mix(in oklab, ${accent} 14%, transparent)`
          : "none",
      }}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 14px 12px",
          borderBottom: "1px dashed var(--border-2)",
          position: "relative",
        }}
      >
        {/* Colored accent underline */}
        <div
          style={{
            position: "absolute",
            left: 14,
            right: 14,
            bottom: -1,
            height: 1,
            background: accent,
            opacity: 0.22,
          }}
        />
        <h3
          style={{
            margin: 0,
            fontFamily: "var(--mono)",
            fontSize: 12.5,
            fontWeight: 700,
            color: accent,
            letterSpacing: "0.02em",
            textTransform: "capitalize",
          }}
        >
          {label}
        </h3>
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: "0.04em",
            padding: "2px 8px",
            background: `color-mix(in oklab, ${accent} 18%, transparent)`,
            color: accent,
            border: `1px solid color-mix(in oklab, ${accent} 40%, transparent)`,
            minWidth: 24,
            textAlign: "center",
          }}
        >
          {videos.length}
        </span>
      </div>

      {/* Body */}
      <div
        style={{
          padding: 12,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          flex: 1,
          overflowY: "auto",
        }}
      >
        {videos.length === 0 ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              letterSpacing: "0.28em",
              color: "var(--mute)",
            }}
          >
            — EMPTY —
          </div>
        ) : (
          videos.map((video) => (
            <KanbanCard
              key={video.id}
              video={video}
              accent={accent}
              onAction={onAction}
              onOpenModal={onOpenModal}
            />
          ))
        )}
      </div>
    </div>
  );
}
