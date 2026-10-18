"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Agent, ScriptProfile, Stats, Video, Voice } from "@/lib/types";
import { SummaryStrip } from "@/components/SummaryStrip";
import { ActionPane } from "@/components/ActionPane";
import { KanbanBoard } from "@/components/KanbanBoard";
import { VideoModal } from "@/components/VideoModal";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatClock } from "@/lib/datetime";
import { deleteVideo, patchVideo } from "@/lib/videoStatus";
import { illustratedAvailable } from "@/lib/visualStyles";
import type { AgentPicks } from "@/lib/agents";

const POLL_MS = 5_000;

const NO_CACHE: RequestInit = { cache: "no-store" };


export function PipelineClient() {
  const { timeZone, label: tzLabel } = useTimeZone();
  const [stats, setStats] = useState<Stats>({});
  const [videos, setVideos] = useState<Video[]>([]);
  const [actionable, setActionable] = useState<Video[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const [initialTab, setInitialTab] = useState("overview");
  const [openRevise, setOpenRevise] = useState(false);
  // Agent choices an inbox row's Revise hands to the modal (TMDEV-110).
  const [initialPicks, setInitialPicks] = useState<AgentPicks | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [defaultVoiceId, setDefaultVoiceId] = useState("");
  const [scriptProfiles, setScriptProfiles] = useState<ScriptProfile[]>([]);
  // undefined until /agents answers (and if it fails), so the pickers say the
  // list is not loaded instead of claiming no agent is installed.
  const [agents, setAgents] = useState<Agent[] | undefined>(undefined);
  const [publishingEnabled, setPublishingEnabled] = useState(false);
  const [canIllustrate, setCanIllustrate] = useState(true);
  const [autoPilot, setAutoPilot] = useState(false);
  // null on the server and on first client render, so SSR and the initial CSR
  // pass match exactly ("Updated —"); the clock only starts ticking once
  // mounted client-side, in the timezone the API reports.
  const [now, setNow] = useState<Date | null>(null);

  // Tracks the latest fetch sequence to discard out-of-order responses.
  const fetchSeqRef = useRef(0);

  const fetchAll = useCallback(async () => {
    const seq = ++fetchSeqRef.current;
    try {
      const [statsRes, videosRes, actionableRes] = await Promise.all([
        fetch("/api/proxy/stats", NO_CACHE),
        fetch("/api/proxy/videos", NO_CACHE),
        fetch("/api/proxy/videos/actionable", NO_CACHE),
      ]);
      // Discard this response if a newer fetch already completed.
      if (seq !== fetchSeqRef.current) return;

      const [statsData, videosData, actionableData] = await Promise.all([
        statsRes.json(),
        videosRes.json(),
        actionableRes.json(),
      ]);
      if (seq !== fetchSeqRef.current) return;

      setStats(Array.isArray(videosData) ? statsData : {});
      setVideos(Array.isArray(videosData) ? videosData : []);
      setActionable(Array.isArray(actionableData) ? actionableData : []);
      setError(null);
    } catch {
      if (seq !== fetchSeqRef.current) return;
      setError("Failed to reach pipeline API");
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  // Voice roster for the topic and script pickers — fetched once, not polled: the
  // Settings page is the place that changes it, and a stale roster here just
  // means a newly-added voice appears after the next full page load.
  useEffect(() => {
    fetch("/api/proxy/settings", NO_CACHE)
      .then((r) => r.json())
      .then((s) => {
        setVoices(s.elevenlabs_voices ?? []);
        setDefaultVoiceId(s.elevenlabs_voice_id ?? "");
        setPublishingEnabled(!!s.publishing_enabled);
        setCanIllustrate(illustratedAvailable(s));
        setAutoPilot(!!s.auto_pilot_enabled);
      })
      .catch(() => {});
  }, []);

  // The whole non-archived list, not just READY: the picker filters to READY
  // itself, but a video that already carries a profile needs its name resolved
  // for the read-only display, and that profile may since have stopped being
  // offered. Not polled, same reasoning as the voice roster — the Profiles page
  // is where they change, and a newly-built one shows up on the next page load.
  useEffect(() => {
    fetch("/api/proxy/script-profiles", NO_CACHE)
      .then((r) => r.json())
      .then((data: ScriptProfile[]) => setScriptProfiles(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  // Uninstalled agents included: a video pinned to one still needs its name
  // resolved, and the pickers disable themselves for it. Not polled — agents
  // change only when the host-side installer runs.
  useEffect(() => {
    fetch("/api/proxy/agents", NO_CACHE)
      .then((r) => r.json())
      .then((data: Agent[]) => setAgents(Array.isArray(data) ? data : undefined))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1_000);
    return () => clearInterval(id);
  }, []);

  const handleAction = useCallback(
    async (videoId: string, action: string, video: Video, extra?: Record<string, unknown>) => {
      try {
        if (action === "approve-topic") {
          // script_profile_id (from extra, the picker's selection) travels in
          // the same atomic PATCH as the status change, exactly like voice_id
          // on approve-script below.
          await patchVideo(videoId, { status: "TOPIC_APPROVED", onlyIfCurrentStatus: "TOPIC_PROPOSED", ...extra });
        } else if (action === "reject-topic") {
          await patchVideo(videoId, { status: "TOPIC_REJECTED", onlyIfCurrentStatus: "TOPIC_PROPOSED" });
        } else if (action === "revise-topic") {
          // Every revise carries the modal's agent picks (TMDEV-110): the
          // revision is the next piece of agent work, and the agent group is
          // checked against the status before this PATCH moves it.
          await patchVideo(videoId, { status: "REVISION_REQUESTED", onlyIfCurrentStatus: "TOPIC_PROPOSED", ...extra });
        } else if (action === "approve-script") {
          // voice_id (from extra, the picker's selection) travels in the same
          // atomic PATCH as the status change — see renderer/api/pipeline.py's
          // patch_video, which guards both under one WHERE status = ? clause.
          await patchVideo(videoId, { status: "VOICING", onlyIfCurrentStatus: "SCRIPT_READY", ...extra });
        } else if (action === "revise-script") {
          await patchVideo(videoId, { status: "REVISION_REQUESTED", onlyIfCurrentStatus: "SCRIPT_READY", ...extra });
        } else if (action === "approve-video") {
          // Named for what it does. It used to be called "publish" and was
          // never a publish — it approves a video, and real publishing
          // (TMDEV-83) now sits at the status this moves it to.
          await patchVideo(videoId, { status: "VIDEO_APPROVED", onlyIfCurrentStatus: "VIDEO_READY" });
        } else if (action === "revise-video") {
          await patchVideo(videoId, { status: "REVISION_REQUESTED", onlyIfCurrentStatus: "VIDEO_READY", ...extra });
        } else if (action === "delete") {
          await deleteVideo(videoId);
        }
        await fetchAll();
      } catch (e) {
        alert(e instanceof Error ? e.message : "Action failed");
      }
    },
    [fetchAll],
  );

  const handleOpenModal = useCallback((
    video: Video, tab?: string, opts?: { revise?: boolean; picks?: AgentPicks },
  ) => {
    setSelectedVideo(video);
    setInitialTab(tab ?? "overview");
    setOpenRevise(!!opts?.revise);
    setInitialPicks(opts?.picks);
  }, []);

  const timeStr = now ? `${formatClock(now, timeZone)} ${tzLabel}` : "—";

  return (
    <>
      {error && (
        <div style={{
          marginBottom: 20,
          border: "1px solid rgba(255,107,107,0.2)",
          background: "rgba(255,107,107,0.05)",
          padding: "12px 16px",
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--red)",
          letterSpacing: "0.06em",
        }}>
          {error}
        </div>
      )}

      <SectionLabel label="Overview" count={`Updated ${timeStr}`} />
      <SummaryStrip stats={stats} />

      <SectionLabel label="Quick Actions" count="Requires Input" />
      {autoPilot && (
        <div
          data-testid="auto-pilot-notice"
          style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--amber)",
                   border: "1px solid var(--amber)", padding: "6px 10px", marginBottom: 10 }}
        >
          AUTO PILOT IS ON — videos in its projects are approved and posted with no human
          review. Change it in Settings → Auto Pilot.
        </div>
      )}
      <ActionPane videos={actionable} voices={voices} defaultVoiceId={defaultVoiceId} scriptProfiles={scriptProfiles} agents={agents} illustratedAvailable={canIllustrate} onAction={handleAction} onOpenModal={handleOpenModal} />

      <SectionLabel label="Pipeline — Kanban" count={`${Object.values(stats).reduce((a, b) => a + b, 0)} Items`} />
      <KanbanBoard videos={videos} onAction={handleAction} onOpenModal={handleOpenModal} />

      <VideoModal
        video={selectedVideo}
        initialTab={initialTab}
        openRevise={openRevise}
        initialPicks={initialPicks}
        voices={voices}
        defaultVoiceId={defaultVoiceId}
        scriptProfiles={scriptProfiles}
        agents={agents}
        publishingEnabled={publishingEnabled}
        illustratedAvailable={canIllustrate}
        onClose={() => setSelectedVideo(null)}
        onAction={handleAction}
      />
    </>
  );
}
