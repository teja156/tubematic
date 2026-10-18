"use client";

import { useEffect, useMemo, useState } from "react";
import type { Agent, Video, VideoStatus, Strategy } from "@/lib/types";
import { VideoModal } from "@/components/VideoModal";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDate, formatScheduled } from "@/lib/datetime";
import { scoreLabel } from "@/lib/utils";
import { deleteVideo, patchVideo } from "@/lib/videoStatus";

const LIBRARY_STATES: Array<{ status: VideoStatus; label: string; accent: string }> = [
  { status: "VIDEO_READY",    label: "Ready",      accent: "var(--amber)" },
  { status: "VIDEO_APPROVED", label: "Approved",   accent: "var(--cyan)" },
  { status: "SCHEDULED",      label: "Scheduled",  accent: "var(--cyan)" },
  { status: "PUBLISHING",     label: "Publishing", accent: "var(--blue)" },
  { status: "PUBLISHED",      label: "Published",  accent: "var(--green)" },
];

const STRATEGIES = ["All Strategies", "Curriculum", "Trending", "Mining"];
const SORTS = ["Newest First", "Oldest First", "Highest Score", "Lowest Score"];

function parseDur(d: string): number {
  const [m, s] = d.split(":").map(Number);
  return (m || 0) * 60 + (s || 0);
}

function VideoCard({ video, accent, onClick }: { video: Video; accent: string; onClick: () => void }) {
  const isPublished = video.status === "PUBLISHED";
  const isPublishing = video.status === "PUBLISHING";
  const isApproved = video.status === "VIDEO_APPROVED";
  const isReady = video.status === "VIDEO_READY";

  const stateLabel = LIBRARY_STATES.find((s) => s.status === video.status)?.label ?? video.status;
  const { timeZone } = useTimeZone();
  const dateStr = formatDate(video.created_at, timeZone);

  return (
    <article
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        cursor: "pointer",
        transition: "all .15s",
        display: "flex",
        flexDirection: "column",
      }}
      onClick={onClick}
      onMouseEnter={(e) => {
        const el = e.currentTarget;
        el.style.borderColor = "var(--border-hot)";
        el.style.transform = "translateY(-2px)";
        el.style.boxShadow = "0 8px 20px rgba(0,0,0,0.4)";
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget;
        el.style.borderColor = "var(--border)";
        el.style.transform = "none";
        el.style.boxShadow = "none";
      }}
    >
      {/* Thumbnail */}
      <div
        style={{
          position: "relative",
          aspectRatio: "16 / 9",
          background: `repeating-linear-gradient(45deg, rgba(255,255,255,0.02) 0 10px, transparent 10px 20px), linear-gradient(135deg, color-mix(in oklab, ${accent} 40%, #0a0d14), #0a0d14)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        {/* Status tag top-left */}
        <div
          style={{
            position: "absolute",
            top: 8,
            left: 8,
            fontFamily: "var(--mono)",
            fontSize: 9,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            padding: "3px 7px",
            background: "rgba(0,0,0,0.7)",
            color: accent,
            border: `1px solid ${accent}`,
            display: "flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          <span
            style={{
              width: 5,
              height: 5,
              background: accent,
              boxShadow: `0 0 4px ${accent}`,
              animation: "tm-pulse 2s ease-in-out infinite",
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          {stateLabel}
        </div>

        {/* Score badge top-right (in place of resolution) */}
        <div
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            fontFamily: "var(--mono)",
            fontSize: 9,
            letterSpacing: "0.16em",
            color: "var(--ink-2)",
            opacity: 0.7,
          }}
        >
          {scoreLabel(video.producibility_score)}
        </div>

        {/* Play button center */}
        <div
          className="vid-play-btn"
          style={{
            width: 44,
            height: 44,
            borderRadius: "50%",
            background: "rgba(0,0,0,0.55)",
            border: `1px solid ${accent}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "all .15s",
          }}
        >
          <div
            style={{
              width: 0,
              height: 0,
              borderLeft: `11px solid ${accent}`,
              borderTop: "7px solid transparent",
              borderBottom: "7px solid transparent",
              marginLeft: 3,
              transition: "border-color .15s",
            }}
          />
        </div>

        {/* Published marker. Since TMDEV-83 a video can be live on several
            platforms at once, so the card says "published" and the modal's
            Analytics tab carries the per-platform links. */}
        {video.status === "PUBLISHED" && (
          <div
            style={{
              position: "absolute",
              bottom: 8,
              right: 8,
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              background: "rgba(0,0,0,0.75)",
              color: "var(--ink)",
              padding: "2px 6px",
              letterSpacing: "0.04em",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            ▶ LIVE
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: "12px 14px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
        {/* Title */}
        <div
          style={{
            fontFamily: "var(--sans)",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--ink)",
            letterSpacing: "-0.005em",
            lineHeight: 1.3,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical" as const,
            overflow: "hidden",
            minHeight: 36,
          } as React.CSSProperties}
        >
          {video.title || video.topic}
        </div>

        {/* Meta */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--dim)", flexWrap: "wrap" }}>
          <span>{video.strategy}</span>
          <span style={{ color: "var(--faint)" }}>·</span>
          <span>{dateStr}</span>
        </div>
        {video.status === "SCHEDULED" && video.scheduled_at && (
          <div
            data-testid={`library-scheduled-at-${video.id}`}
            style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--cyan)" }}
          >
            ⏱ {formatScheduled(video.scheduled_at, video.scheduled_timezone || timeZone)}
          </div>
        )}

        {/* Stats row */}
        <div style={{ display: "flex", gap: 14, fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--dim)", letterSpacing: "0.02em", borderTop: "1px dashed var(--border-2)", paddingTop: 8, marginTop: 2 }}>
          {isPublished && (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ color: "var(--mute)", letterSpacing: "0.16em", textTransform: "uppercase", fontSize: 9 }}>Score</span>
                <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>{scoreLabel(video.producibility_score)}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ color: "var(--mute)", letterSpacing: "0.16em", textTransform: "uppercase", fontSize: 9 }}>Status</span>
                <span style={{ color: "var(--green)", fontWeight: 700 }}>LIVE</span>
              </div>

            </>
          )}
          {isReady && (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ color: "var(--mute)", letterSpacing: "0.16em", textTransform: "uppercase", fontSize: 9 }}>Score</span>
                <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>{scoreLabel(video.producibility_score)}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ color: "var(--mute)", letterSpacing: "0.16em", textTransform: "uppercase", fontSize: 9 }}>Status</span>
                <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>AWAITING</span>
              </div>
            </>
          )}
          {isApproved && (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ color: "var(--mute)", letterSpacing: "0.16em", textTransform: "uppercase", fontSize: 9 }}>Queue</span>
              <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>SCHEDULED</span>
            </div>
          )}
          {isPublishing && (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ color: "var(--mute)", letterSpacing: "0.16em", textTransform: "uppercase", fontSize: 9 }}>Upload</span>
              <span style={{ color: "var(--blue)", fontWeight: 700 }}>IN PROGRESS</span>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

export default function LibraryPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const [activeState, setActiveState] = useState<VideoStatus>("VIDEO_READY");
  const [strategy, setStrategy] = useState("All Strategies");
  const [sort, setSort] = useState("Newest First");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<Agent[] | undefined>(undefined);
  const [publishingEnabled, setPublishingEnabled] = useState(false);

  useEffect(() => {
    function load() {
      fetch("/api/proxy/videos", { cache: "no-store" })
        .then((r) => r.json())
        .then((data: Video[]) => {
          if (!Array.isArray(data)) return;
          setVideos(data.filter((v) => LIBRARY_STATES.some((s) => s.status === v.status)));
          setLoading(false);
        })
        .catch(() => setLoading(false));
    }
    load();
    const id = setInterval(load, 5_000);
    return () => clearInterval(id);
  }, []);

  // The modal's agent picker (TMDEV-110): a VIDEO_READY revision can go to a
  // different agent. Same fetch as PipelineClient's; not polled, since agents
  // change only when the host-side installer runs. undefined until it answers
  // and on failure — the modal then sends nothing for an untouched picker.
  useEffect(() => {
    fetch("/api/proxy/agents", { cache: "no-store" })
      .then((r) => r.json())
      .then((data: Agent[]) => setAgents(Array.isArray(data) ? data : undefined))
      .catch(() => {});
  }, []);

  // Whether the modal offers Publish…, Retry publishing and Cancel schedule —
  // the actions for the very videos this page lists. Off until /settings
  // answers, and on failure: the API refuses a publish while it is disabled
  // anyway, so the button would only lead to that refusal.
  useEffect(() => {
    fetch("/api/proxy/settings", { cache: "no-store" })
      .then((r) => r.json())
      .then((s) => setPublishingEnabled(!!s?.publishing_enabled))
      .catch(() => {});
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of LIBRARY_STATES) c[s.status] = videos.filter((v) => v.status === s.status).length;
    return c;
  }, [videos]);

  const filtered = useMemo(() => {
    let list = videos.filter((v) => v.status === activeState);
    if (strategy !== "All Strategies") list = list.filter((v) => v.strategy.toLowerCase() === strategy.toLowerCase());
    if (query) {
      const q = query.toLowerCase();
      // Match both fields — after the title/topic split, searching only one
      // makes a video unfindable by words that live in the other.
      list = list.filter(
        (v) => v.topic.toLowerCase().includes(q) || (v.title ?? "").toLowerCase().includes(q),
      );
    }
    list = [...list];
    switch (sort) {
      case "Oldest First":   list.reverse(); break;
      case "Highest Score":  list.sort((a, b) => b.producibility_score - a.producibility_score); break;
      case "Lowest Score":   list.sort((a, b) => a.producibility_score - b.producibility_score); break;
      default: break;
    }
    return list;
  }, [videos, activeState, strategy, sort, query]);

  const activeAccent = LIBRARY_STATES.find((s) => s.status === activeState)?.accent ?? "var(--amber)";
  const activeLabel = LIBRARY_STATES.find((s) => s.status === activeState)?.label ?? activeState;

  const handleAction = async (videoId: string, action: string, extra?: Record<string, unknown>) => {
    if (action === "delete") {
      try {
        await deleteVideo(videoId);
      } catch (e) {
        alert(e instanceof Error ? e.message : "Delete failed");
      }
    } else if (action === "approve-video" || action === "revise-video") {
      // revise-video used to fall through to the bare return below, so Request
      // Revision posted the comment and never moved the video. `extra` is the
      // modal's agent picks: the revision goes to whichever agent the human
      // chose. A refusal is reported — the modal has already closed, so
      // without this the human would believe the action went through.
      try {
        await patchVideo(videoId, action === "approve-video"
          ? { status: "VIDEO_APPROVED", onlyIfCurrentStatus: "VIDEO_READY" }
          : { status: "REVISION_REQUESTED", onlyIfCurrentStatus: "VIDEO_READY", ...extra });
      } catch (e) {
        alert(e instanceof Error ? e.message : "Action failed");
      }
    } else {
      return;
    }
    fetch("/api/proxy/videos")
      .then((r) => r.json())
      .then((data: Video[]) => setVideos(data.filter((v) => LIBRARY_STATES.some((s) => s.status === v.status))));
  };

  return (
    <>
      <SectionLabel label="Video Library" count={`${videos.length} Total`} />

      {/* Filter row */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 24 }}>
        {/* State pills */}
        <div style={{ display: "flex", gap: 4 }}>
          {LIBRARY_STATES.map((s) => {
            const isActive = activeState === s.status;
            return (
              <button
                key={s.status}
                onClick={() => setActiveState(s.status)}
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11.5,
                  letterSpacing: "0.04em",
                  padding: "7px 14px",
                  background: isActive ? "var(--amber-soft)" : "var(--panel)",
                  border: `1px solid ${isActive ? "rgba(245,166,35,0.4)" : "var(--border)"}`,
                  color: isActive ? "var(--amber)" : "var(--dim)",
                  cursor: "pointer",
                  transition: "all .12s",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                {s.label}
                <span style={{ opacity: 0.75, fontSize: 10 }}>{counts[s.status] ?? 0}</span>
              </button>
            );
          })}
        </div>

        {/* Separator */}
        <div style={{ width: 1, height: 20, background: "var(--border-2)", flexShrink: 0 }} />

        {/* Strategy select */}
        <select
          data-testid="strategy-select"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            padding: "7px 28px 7px 12px",
            // The chevron fill is --dim, hardcoded because a data: URL cannot
            // read var(). Keep in sync with globals.css (both selects here).
            background: `var(--panel) url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6"><path d="M0 0l5 6 5-6z" fill="%23939cae"/></svg>') no-repeat right 10px center`,
            border: "1px solid var(--border)",
            color: "var(--ink-2)",
            cursor: "pointer",
            appearance: "none" as const,
            letterSpacing: "0.02em",
          }}
        >
          {STRATEGIES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        {/* Sort select */}
        <select
          data-testid="sort-select"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            padding: "7px 28px 7px 12px",
            background: `var(--panel) url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6"><path d="M0 0l5 6 5-6z" fill="%23939cae"/></svg>') no-repeat right 10px center`,
            border: "1px solid var(--border)",
            color: "var(--ink-2)",
            cursor: "pointer",
            appearance: "none" as const,
            letterSpacing: "0.02em",
          }}
        >
          {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        {/* Search */}
        <input
          data-testid="search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="> search titles…"
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            background: "var(--panel)",
            border: "1px solid var(--border)",
            color: "var(--ink)",
            padding: "7px 12px",
            minWidth: 240,
            letterSpacing: "0.02em",
            outline: "none",
          }}
          onFocus={(e) => { e.currentTarget.style.borderColor = "var(--amber)"; }}
          onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
        />

        {/* Count */}
        <div style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.16em", color: "var(--dim)", textTransform: "uppercase" }}>
          <strong style={{ color: "var(--ink)", fontWeight: 700 }}>{filtered.length}</strong>&nbsp;&nbsp;videos
        </div>
      </div>

      {/* Grid or empty state */}
      {loading ? (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.28em", color: "var(--mute)", textTransform: "uppercase", padding: "40px 0" }}>
          LOADING…
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ background: "var(--panel)", border: "1px solid var(--border)", padding: "60px 40px", textAlign: "center" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.28em", color: "var(--mute)", marginBottom: 10 }}>
            ◇ NO VIDEOS YET
          </div>
          <div style={{ fontFamily: "var(--sans)", color: "var(--ink-2)", fontSize: 14 }}>
            Nothing in <strong style={{ color: "var(--amber)" }}>{activeLabel.toUpperCase()}</strong> matches your filters.
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}>
          {filtered.map((video) => (
            <VideoCard
              key={video.id}
              video={video}
              accent={activeAccent}
              onClick={() => setSelectedVideo(video)}
            />
          ))}
        </div>
      )}

      <VideoModal
        video={selectedVideo}
        agents={agents}
        publishingEnabled={publishingEnabled}
        onClose={() => setSelectedVideo(null)}
        onAction={(id, action, _video, extra) => handleAction(id, action, extra)}
      />
    </>
  );
}
