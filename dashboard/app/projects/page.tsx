"use client";

import { useEffect, useMemo, useState } from "react";
import type { Agent, Project, Video, VideoStatus, Voice } from "@/lib/types";
import { VideoModal } from "@/components/VideoModal";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDate } from "@/lib/datetime";
import { patchVideo } from "@/lib/videoStatus";
import { illustratedAvailable } from "@/lib/visualStyles";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const STATUS_ACCENT: Record<VideoStatus, string> = {
  TOPIC_PROPOSED:     "var(--dim)",
  TOPIC_APPROVED:     "var(--cyan)",
  TOPIC_REJECTED:     "var(--red)",
  SCRIPT_READY:       "var(--amber)",
  VOICING:            "var(--amber)",
  VOICE_READY:        "var(--green)",
  RENDER_QUEUED:      "var(--green)",
  RENDERING:          "var(--green)",
  VIDEO_READY:        "var(--amber)",
  VIDEO_APPROVED:     "var(--cyan)",
  REVISION_REQUESTED: "var(--red)",
  SCHEDULED:          "var(--cyan)",
  PUBLISHING:         "var(--blue)",
  PUBLISHED:          "var(--green)",
  FAILED:             "var(--red)",
};

export default function ProjectsPage() {
  const { timeZone } = useTimeZone();
  const [projects, setProjects]             = useState<Project[]>([]);
  const [videos, setVideos]                 = useState<Video[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedVideo, setSelectedVideo]   = useState<Video | null>(null);
  const [initialTab, setInitialTab]         = useState<string>("overview");
  const [agents, setAgents]                 = useState<Agent[] | undefined>(undefined);
  const [canIllustrate, setCanIllustrate]   = useState(true);
  const [publishingEnabled, setPublishingEnabled] = useState(false);
  const [voices, setVoices]                 = useState<Voice[]>([]);
  const [defaultVoiceId, setDefaultVoiceId] = useState("");

  useEffect(() => {
    function load() {
      Promise.all([
        apiFetch("/projects").then((r) => r.json()),
        apiFetch("/videos").then((r) => r.json()),
      ])
        .then(([projs, vids]: [Project[], Video[]]) => {
          setProjects(Array.isArray(projs) ? projs : []);
          setVideos(Array.isArray(vids) ? vids : []);
        })
        .catch(() => {});
    }
    load();
    const id = setInterval(load, 5_000);
    return () => clearInterval(id);
  }, []);

  // The modal's agent picker (TMDEV-110). Same fetch as PipelineClient's, and
  // uninstalled agents included for the same reason: a video pinned to one
  // still needs its name resolved. Not polled — agents change only when the
  // host-side installer runs. Left undefined until it answers, and on failure:
  // the modal then shows the agent instead of offering it, and sends nothing
  // for an untouched picker, so a slow or failed fetch can never move a video.
  useEffect(() => {
    apiFetch("/agents")
      .then((r) => r.json())
      .then((data: Agent[]) => setAgents(Array.isArray(data) ? data : undefined))
      .catch(() => {});
  }, []);

  // The modal's style picker disables Illustrated when no OpenAI key is
  // stored. Stays true until /settings answers, and on failure: the API
  // refuses the style itself, so that only costs a clearer error. The same
  // answer carries the voice roster for the modal's voice pickers (TMDEV-127);
  // until it arrives, or if it fails, the modal shows none and sends none.
  useEffect(() => {
    apiFetch("/settings")
      .then((r) => r.json())
      .then((s) => {
        setCanIllustrate(illustratedAvailable(s));
        setVoices(s.elevenlabs_voices ?? []);
        setDefaultVoiceId(s.elevenlabs_voice_id ?? "");
        // Whether the modal offers Publish…, Retry publishing and Cancel
        // schedule. Off until this answers, and on failure.
        setPublishingEnabled(!!s.publishing_enabled);
      })
      .catch(() => {});
  }, []);

  const videoCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const v of videos) {
      if (v.project_id) c[v.project_id] = (c[v.project_id] || 0) + 1;
    }
    return c;
  }, [videos]);

  const projectVideos = useMemo(() => {
    if (!selectedProject) return [];
    return videos.filter((v) => v.project_id === selectedProject.id);
  }, [videos, selectedProject]);

  // `extra` carries the topic card's frozen-at-approval picks (script profile,
  // agent model, visual style) in the SAME PATCH as the status change. Dropping
  // it is not a cosmetic loss: every one of those fields is rejected once the
  // video leaves TOPIC_PROPOSED, so a silently discarded pick cannot be
  // corrected afterwards — the modal shows a picker and the choice never
  // arrives. PipelineClient spreads it the same way.
  const handleAction = async (
    videoId: string,
    action: string,
    video: Video,
    extra?: Record<string, unknown>,
  ) => {
    const statusMap: Partial<Record<string, VideoStatus>> = {
      "approve-topic":  "TOPIC_APPROVED",
      "reject-topic":   "TOPIC_REJECTED",
      "revise-topic":   "REVISION_REQUESTED",
      "approve-script": "VOICING",
      "revise-script":  "REVISION_REQUESTED",
      "approve-video":  "VIDEO_APPROVED",
      "revise-video":   "REVISION_REQUESTED",
    };
    const newStatus = statusMap[action];
    if (!newStatus) return;

    // A refusal is reported, not swallowed: the modal has already closed, and
    // with a picked agent in `extra` there is one more way to be refused — it
    // may have been uninstalled since this page fetched the list.
    try {
      await patchVideo(videoId, { status: newStatus, onlyIfCurrentStatus: video.status, ...extra });
    } catch (e) {
      alert(e instanceof Error ? e.message : "Action failed");
    }

    apiFetch("/videos")
      .then((r) => r.json())
      .then((data: Video[]) => {
        if (Array.isArray(data)) setVideos(data);
      })
      .catch(() => {});
  };

  return (
    <>
      <SectionLabel label="Projects" count={`${projects.length} project${projects.length !== 1 ? "s" : ""}`} />

      {projects.length === 0 ? (
        <div style={{
          fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.24em",
          color: "var(--mute)", textTransform: "uppercase", padding: "24px 0",
        }}>
          — No projects yet —
        </div>
      ) : (
        <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
          {/* Left: project list. minWidth: 0 is what makes the 340px basis
              hold: without it a flex item grows to its min-content width, and
              a nowrap description's min-content is the whole sentence — which
              crushes the video pane on the right. */}
          <div style={{ flex: "0 0 340px", minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
            {projects.map((project) => {
              const isSelected = selectedProject?.id === project.id;
              const count = videoCounts[project.id] ?? 0;
              const isPaused = project.status === "paused";

              return (
                <div
                  key={project.id}
                  data-testid={`project-row-${project.id}`}
                  onClick={() => setSelectedProject(project)}
                  style={{
                    padding: "12px 14px",
                    background: isSelected ? "var(--panel)" : "transparent",
                    border: `1px solid ${isSelected ? "var(--border-2)" : "var(--border)"}`,
                    cursor: "pointer",
                    transition: "all .12s",
                    opacity: isPaused ? 0.6 : 1,
                    boxShadow: isSelected ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.borderColor = "var(--border-2)";
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.borderColor = "var(--border)";
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <span style={{
                      fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, minWidth: 0, overflowWrap: "anywhere",
                      color: isSelected ? "var(--amber)" : "var(--ink)",
                    }}>
                      {project.name}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {/* Pause exists only on curriculum seeds, so on any
                          other domain this badge would describe a state
                          nothing can change. */}
                      {project.is_curriculum_seed === 1 && (
                        <span data-testid={`project-status-${project.id}`} style={{
                          fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.12em",
                          padding: "2px 6px",
                          border: `1px solid ${isPaused ? "var(--red)" : "var(--green)"}`,
                          color: isPaused ? "var(--red)" : "var(--green)",
                          textTransform: "uppercase",
                        }}>
                          {isPaused ? "paused" : "active"}
                        </span>
                      )}
                      {/* Any domain can reach its topic cap, seed or not. */}
                      {project.expired === true && (
                        <span data-testid={`project-expired-${project.id}`}
                          title="This domain holds as many topics as its cap allows; raise the cap on the Topics page"
                          style={{
                            fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.12em",
                            padding: "2px 6px", border: "1px solid var(--red)", color: "var(--red)",
                            textTransform: "uppercase",
                          }}>
                          expired
                        </span>
                      )}
                      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)" }}>
                        {count}v
                      </span>
                    </div>
                  </div>
                  {project.description && (
                    <div style={{
                      fontFamily: "var(--mono)", fontSize: 10, color: "var(--dim)",
                      marginTop: 4, lineHeight: 1.5,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                      {project.description}
                    </div>
                  )}
                  {project.is_curriculum_seed === 1 && (
                    <div style={{ marginTop: 4 }}>
                      <span style={{
                        fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.1em",
                        color: "var(--indigo)", border: "1px solid var(--indigo)",
                        padding: "1px 5px", textTransform: "uppercase",
                      }}>
                        seed
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Right: selected project videos */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {!selectedProject ? (
              <div style={{
                fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.24em",
                color: "var(--mute)", textTransform: "uppercase", padding: "24px 0",
              }}>
                — Select a project to view its videos —
              </div>
            ) : projectVideos.length === 0 ? (
              <div style={{
                fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.24em",
                color: "var(--mute)", textTransform: "uppercase", padding: "24px 0",
              }}>
                — No videos in this project —
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {projectVideos.map((video) => {
                  const accent = STATUS_ACCENT[video.status] ?? "var(--dim)";
                  const dateStr = formatDate(video.created_at, timeZone);

                  return (
                    <div
                      key={video.id}
                      data-testid={`project-video-${video.id}`}
                      onClick={() => setSelectedVideo(video)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        padding: "10px 14px",
                        background: "var(--panel)",
                        border: "1px solid var(--border)",
                        cursor: "pointer",
                        transition: "border-color .12s",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--border-2)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink)",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>
                          {video.title || video.topic}
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                          <span style={{
                            fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.1em",
                            color: "var(--mute)", textTransform: "uppercase",
                          }}>
                            {video.strategy}
                          </span>
                          <span style={{ color: "var(--border)", fontSize: 10 }}>·</span>
                          <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--mute)" }}>
                            {dateStr}
                          </span>
                        </div>
                      </div>
                      <span style={{
                        fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.1em",
                        padding: "2px 7px",
                        border: `1px solid ${accent}`,
                        color: accent,
                        textTransform: "uppercase",
                        flexShrink: 0,
                      }}>
                        {video.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      <VideoModal
        video={selectedVideo}
        initialTab={initialTab}
        agents={agents}
        voices={voices}
        defaultVoiceId={defaultVoiceId}
        illustratedAvailable={canIllustrate}
        publishingEnabled={publishingEnabled}
        onClose={() => { setSelectedVideo(null); setInitialTab("overview"); }}
        onAction={(id, action, video, extra) => handleAction(id, action, video, extra)}
      />
    </>
  );
}
