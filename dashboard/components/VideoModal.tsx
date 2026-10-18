"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Agent, LogRecord, LogsResponse, ScriptProfile, Video, VideoPublication, Voice } from "@/lib/types";
import { isScored, videoStreamUrl } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";
import { ReviseDialog } from "@/components/ReviseDialog";
import { PublishDialog } from "@/components/PublishDialog";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { VoicePreviewButton } from "@/components/VoicePreviewButton";
import { shownVoice, topicVoicePayload, voiceConflict, voiceLabel, voiceMissing } from "@/lib/voices";
import { LogList } from "@/components/LogList";
import { CostBreakdown } from "@/components/CostBreakdown";
import { formatDateTime, formatScheduled } from "@/lib/datetime";
import { canDelete, canRetryPublish, isAgentStuck, retryAgent } from "@/lib/videoStatus";
import { platformLabel } from "@/lib/platforms";
import {
  AGENT_EFFORTS, type AgentPicks, agentChanged, agentLabel, agentOptions, agentPicksPayload,
  effectiveAgent, effortLabel, effortOptionLabel, initialEffort, isUsable, modelLabel,
  pickedAgent, resolvedModel, topicApprovalPayload,
} from "@/lib/agents";
import { styleOptions, videoStyleLabel } from "@/lib/visualStyles";

interface VideoModalProps {
  video: Video | null;
  initialTab?: string;
  /** Open straight into the Request Revision dialog. Set by the Pipeline
   *  page's Revise buttons: that dialog is the only way a human comment is
   *  added, so a Revise click should land in it rather than one click short. */
  openRevise?: boolean;
  /** Agent choices already made on the Pipeline inbox row, handed over by its
   *  Revise button so they are not dropped on the way into the dialog. Seeds
   *  the pickers when the modal opens; absent means untouched. */
  initialPicks?: AgentPicks;
  // Optional: the Library page doesn't fetch the voice roster and renders this
  // modal without a picker — it only lists videos past both voice checkpoints.
  // PipelineClient and the Projects page (TMDEV-127) pass these.
  voices?: Voice[];
  defaultVoiceId?: string;
  /** READY script profiles only — a profile still building would be rejected
   *  by the PATCH, so offering it would present an invalid choice as valid. */
  scriptProfiles?: ScriptProfile[];
  /** Every agent row, uninstalled included — resolves the video's agent and
   *  the models and agents its pickers offer. undefined = not loaded (Archive
   *  omits it; the other pages until GET /agents answers): the read-only rows
   *  fall back to generic wording, the agent is shown rather than offered, and
   *  the picker says the list is not loaded rather than claiming no agent is
   *  installed. */
  agents?: Agent[];
  /** settings.publishing_enabled (TMDEV-83). False hides the publish
   *  affordance and makes VIDEO_APPROVED read as terminal. A UI filter only —
   *  PUBLISHING/PUBLISHED stay in VideoStatus and still render everywhere.
   *  Defaults false so a page that does not fetch settings (Library,
   *  Projects) simply does not offer publishing. */
  publishingEnabled?: boolean;
  /** False when no OpenAI key is stored: Illustrated is disabled in the style
   *  picker. Defaults true, unlike publishingEnabled — the API refuses the
   *  style without a key anyway, so the safe default is to let it say so. */
  illustratedAvailable?: boolean;
  onClose: () => void;
  onAction: (videoId: string, action: string, video: Video, extra?: Record<string, unknown>) => void;
}

// Reduces a segment's voice text to the authored, on-screen word text, so
// authors see clean display text rather than markup. Mirrors
// _strip_non_spoken in mcp/server.py:
//   - <phoneme alphabet="..." ph="...">word</phoneme> -> the wrapped word
//   - <respell as="...">word</respell> -> the wrapped (authored) word, not
//     the "as" respelling — same "display keeps the authored word" contract
//     <phoneme> already has (TMDEV-26 follow-up)
//   - <ipa ph="...">word</ipa> -> the wrapped word, never the IPA (TMDEV-123)
//   - <break time="0.6s" /> and [pause] / [short pause] / [long pause] -> gone
function stripVoiceMarkup(text: string): string {
  return text
    .replace(/<phoneme\b[^>]*>([\s\S]*?)<\/phoneme>/gi, "$1")
    .replace(/<respell\b[^>]*>([\s\S]*?)<\/respell>/gi, "$1")
    .replace(/<ipa\b[^>]*>([\s\S]*?)<\/ipa>/gi, "$1")
    .replace(/<break\b[^>]*>/gi, " ")
    .replace(/\[\s*(?:short\s+|long\s+)?pause\s*\]/gi, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9,
          textTransform: "uppercase",
          letterSpacing: "0.14em",
          color: "var(--dim)",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.4 }}>
        {value}
      </div>
    </div>
  );
}

// A caption above one action-block picker. A wrapping <label> so the caption
// is the control's accessible name too, not just text that happens to sit near
// it; readOnly values (the agent) have no control to name, so they get a div.
function PickerField({ label, readOnly, children }: {
  label: string;
  readOnly?: boolean;
  children: React.ReactNode;
}) {
  const Wrapper = readOnly ? "div" : "label";
  return (
    <Wrapper style={{ display: "block", flex: 1, minWidth: 0 }}>
      <span
        style={{
          display: "block",
          fontFamily: "var(--mono)",
          fontSize: 9,
          textTransform: "uppercase",
          letterSpacing: "0.14em",
          color: "var(--dim)",
          marginBottom: 4,
        }}
      >
        {label}
      </span>
      {children}
    </Wrapper>
  );
}

function ActionBtn({
  onClick,
  variant,
  children,
  fullWidth,
  disabled,
}: {
  onClick: () => void;
  variant: "primary" | "amber" | "ghost" | "danger";
  children: React.ReactNode;
  fullWidth?: boolean;
  disabled?: boolean;
}) {
  const styles: Record<string, string> = {
    primary:
      "bg-[#1de8a8]/10 hover:bg-[#1de8a8]/20 text-[#1de8a8] border border-[#1de8a8]/25 hover:border-[#1de8a8]/50",
    amber:
      "bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/25 hover:border-amber-500/50",
    ghost:
      "bg-[#131325] hover:bg-[#1a1a2e] text-[#9a9ab8] hover:text-[#f0f0ff] border border-[#2a2a42]",
    danger:
      "bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/25 hover:border-red-500/50",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-4 py-2 text-sm font-medium transition-all duration-150 disabled:opacity-50 ${styles[variant]} ${fullWidth ? "w-full" : ""}`}
    >
      {children}
    </button>
  );
}

function MdContent({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => (
          <p style={{ margin: "0 0 0.75em", lineHeight: 1.65, color: "var(--ink)", fontSize: 13 }}>
            {children}
          </p>
        ),
        strong: ({ children }) => (
          <strong style={{ color: "var(--ink)", fontWeight: 600 }}>{children}</strong>
        ),
        em: ({ children }) => (
          <em style={{ color: "var(--dim)", fontStyle: "italic" }}>{children}</em>
        ),
        code: ({ children, className }) => {
          const isBlock = className?.includes("language-");
          return isBlock ? (
            <code
              style={{
                display: "block",
                background: "var(--panel-2)",
                border: "1px solid var(--border-2)",
                padding: "10px 14px",
                fontFamily: "var(--mono)",
                fontSize: 12,
                color: "var(--green)",
                lineHeight: 1.6,
                overflowX: "auto",
                marginBottom: "0.75em",
              }}
            >
              {children}
            </code>
          ) : (
            <code
              style={{
                background: "var(--panel-2)",
                border: "1px solid var(--border-2)",
                padding: "1px 5px",
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--green)",
              }}
            >
              {children}
            </code>
          );
        },
        pre: ({ children }) => (
          <pre style={{ margin: "0 0 0.75em", background: "none" }}>{children}</pre>
        ),
        ul: ({ children }) => (
          <ul style={{ margin: "0 0 0.75em", paddingLeft: 18, color: "var(--ink)", fontSize: 13 }}>
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol style={{ margin: "0 0 0.75em", paddingLeft: 18, color: "var(--ink)", fontSize: 13 }}>
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li style={{ marginBottom: 2, lineHeight: 1.55 }}>{children}</li>
        ),
        h1: ({ children }) => (
          <h1 style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", margin: "0 0 0.5em", borderBottom: "1px solid var(--border)", paddingBottom: 4 }}>
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", margin: "0.75em 0 0.4em", textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "var(--mono)" }}>
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 style={{ fontSize: 12, fontWeight: 600, color: "var(--dim)", margin: "0.5em 0 0.3em" }}>
            {children}
          </h3>
        ),
        blockquote: ({ children }) => (
          <blockquote
            style={{
              borderLeft: "3px solid var(--amber)",
              paddingLeft: 12,
              margin: "0 0 0.75em",
              color: "var(--dim)",
              fontStyle: "italic",
            }}
          >
            {children}
          </blockquote>
        ),
        hr: () => (
          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "0.75em 0" }} />
        ),
        a: ({ children, href }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--amber)", textDecoration: "underline", textDecorationColor: "rgba(245,166,35,0.4)" }}
          >
            {children}
          </a>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

// How much of the AI review the modal shows before "Read more". The review is
// stored and served uncapped (VQA-7 removed the must-fix limit, so a defective
// video can produce a long one), and a wall of markdown buries the rest of the
// panel.
const REVIEW_PREVIEW_CHARS = 700;

function isClipped(feedback: string | null | undefined): boolean {
  return (feedback?.length ?? 0) > REVIEW_PREVIEW_CHARS;
}

function clipReview(feedback: string | null | undefined): string {
  const text = feedback ?? "";
  if (!isClipped(text)) return text;
  // Cut at a paragraph break, not any newline. A single finding spans several
  // lines in _format_feedback's output ("- **type** @ time", an indented
  // description, then "Suggested fix:"), so cutting at "\n" can leave a bullet
  // with its body lopped off; "\n\n" matches the format's real boundaries.
  const slice = text.slice(0, REVIEW_PREVIEW_CHARS);
  const lastBreak = slice.lastIndexOf("\n\n");
  return (lastBreak > REVIEW_PREVIEW_CHARS / 2 ? slice.slice(0, lastBreak) : slice).trimEnd() + "\n\n…";
}

const reviewToggleStyle: CSSProperties = {
  marginTop: 8,
  fontFamily: "var(--mono)",
  fontSize: 10,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  padding: "5px 12px",
  border: "1px solid var(--border)",
  background: "var(--panel)",
  color: "var(--ink)",
  cursor: "pointer",
};

export function VideoModal({ video: seed, initialTab, openRevise = false, initialPicks, voices = [], defaultVoiceId = "", scriptProfiles = [], agents, publishingEnabled = false, illustratedAvailable = true, onClose, onAction }: VideoModalProps) {
  const { timeZone, label: tzLabel } = useTimeZone();
  const [video, setVideo] = useState<Video | null>(null);
  const [reviseOpen, setReviseOpen] = useState(false);
  // null = untouched, like the agent picks below; the shown voice is derived
  // (see lib/voices.ts), so it follows the roster even when that answers late.
  const [pickedVoice, setPickedVoice] = useState<string | null>(null);
  // "" is a real choice, not an absence: it means the script-writing skill's
  // own generic style. So the picker shows whenever there is at least one
  // profile, and always carries the none option.
  const [selectedProfile, setSelectedProfile] = useState("");
  // Frozen after TOPIC_PROPOSED alongside the profile and the model.
  const [selectedStyle, setSelectedStyle] = useState<Video["visual_style"]>("auto");
  // A dropdown of the video's own agent's models (the API rejects anything
  // else). null = untouched, so the shown value tracks initialModel() until
  // the human picks — including when the agent list arrives after first paint.
  const [pickedModel, setPickedModel] = useState<string | null>(null);
  // Same null-means-untouched trick as the model above, and never disabled:
  // the levels are fixed by the CLI rather than read off the agent's row, so
  // there is always a valid list to offer even on Projects and Library, which
  // never fetch /agents at all. What is NOT known without the agent is which
  // level blank resolves to, so untouched stays "" — see initialEffort.
  const [pickedEffort, setPickedEffort] = useState<string | null>(null);
  // Which agent does the next piece of work (TMDEV-110). null = untouched;
  // only a pick of a *different* agent is ever sent.
  const [pickedAgentId, setPickedAgentId] = useState<string | null>(null);
  // Resolved by id rather than looked up in the scriptProfiles prop: the
  // Library and Projects pages render this modal without that prop at all, and
  // GET /script-profiles/<id> also resolves an *archived* profile, which the
  // list endpoint deliberately omits. Falls back to the raw id so a deleted
  // profile shows something traceable instead of a blank row.
  const [profileName, setProfileName] = useState("");
  const [reviewExpanded, setReviewExpanded] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");
  const [cancellingSchedule, setCancellingSchedule] = useState(false);
  const [cancelScheduleError, setCancelScheduleError] = useState("");
  const [retryingAgent, setRetryingAgent] = useState(false);
  const [retryAgentError, setRetryAgentError] = useState("");
  // Where this video actually went (TMDEV-83). Replaces videos.youtube_url as
  // the read path — one TEXT column cannot hold four platform URLs.
  const [publications, setPublications] = useState<VideoPublication[]>([]);
  const [logs, setLogs] = useState<LogRecord[]>([]);

  const seedId = seed ? seed.id : null;

  function refreshVideo(id: string) {
    fetch(`/api/proxy/videos/${id}`)
      .then((r) => r.json())
      .then((full: Video) => setVideo(full))
      .catch(() => {});
  }

  function refreshLogs(id: string) {
    // No service filter: one video's trail spans the renderer that rendered it,
    // the MCP tools that voiced and staged it, and the API calls that moved it
    // between statuses.
    fetch(`/api/proxy/logs?video_id=${encodeURIComponent(id)}&limit=200`)
      .then((r) => r.json())
      .then((data: Partial<LogsResponse>) =>
        setLogs(Array.isArray(data.records) ? data.records : []))
      .catch(() => setLogs([]));
  }

  function refreshPublications(id: string) {
    fetch(`/api/proxy/videos/${id}/publications`)
      .then((r) => r.json())
      .then((rows: VideoPublication[]) => setPublications(Array.isArray(rows) ? rows : []))
      .catch(() => {});
  }

  useEffect(() => {
    if (!seed) { setVideo(null); return; }
    setVideo(seed);
    setPickedVoice(null);
    setSelectedProfile(seed.script_profile_id ?? "");
    setSelectedStyle(seed.visual_style ?? "auto");
    // Seeded from the inbox row's picks when its Revise opened this modal,
    // otherwise cleared: this modal stays mounted between videos, and a pick
    // left over from the last one would be sent for this one.
    setPickedAgentId(initialPicks?.agentId ?? null);
    setPickedModel(initialPicks?.model ?? null);
    setPickedEffort(initialPicks?.effort ?? null);
    setProfileName("");
    // Collapse again for a different video — otherwise opening a long review,
    // closing, and opening another shows the second one pre-expanded.
    setReviewExpanded(false);
    setPublishOpen(false);
    setRetryError("");
    setCancelScheduleError("");
    setReviseOpen(openRevise);
    setPublications([]);
    // Cleared before refetching, like publications above — otherwise opening a
    // second video briefly shows the first one's records.
    setLogs([]);
    refreshVideo(seed.id);
    refreshPublications(seed.id);
    refreshLogs(seed.id);
  }, [seedId]);

  const profileId = video?.script_profile_id ?? "";
  useEffect(() => {
    if (!profileId) { setProfileName(""); return; }
    let cancelled = false;
    fetch(`/api/proxy/script-profiles/${profileId}`)
      .then((r) => r.json())
      .then((p: ScriptProfile) => {
        if (cancelled) return;
        setProfileName(p?.name ? (p.archived ? `${p.name} (deleted)` : p.name) : profileId);
      })
      .catch(() => { if (!cancelled) setProfileName(profileId); });
    return () => { cancelled = true; };
  }, [profileId]);

  // Only a READY profile can actually be set on a video, but the full list is
  // passed so an already-selected one still resolves to a name below.
  const readyProfiles = scriptProfiles.filter((p) => p.status === "READY");
  // A curriculum video can arrive holding its domain's default profile, which
  // may have been deleted since (TMDEV-145). Shown by name (profileName marks a
  // deleted one) rather than reading as "No profile" while being sent; the
  // picker stays up even with no READY profile left, so it can be cleared.
  const staleProfile = selectedProfile !== "" && !readyProfiles.some((p) => p.id === selectedProfile);

  if (!video) return null;

  // undefined = the list was never fetched here, which is not the same as
  // "no agent installed".
  const agentsLoaded = agents !== undefined;
  const agentList = agents ?? [];
  const picks: AgentPicks = { agentId: pickedAgentId, model: pickedModel, effort: pickedEffort };
  // The agent the model list comes from — the picked one, else the video's.
  const agent = pickedAgent(video, agentList, pickedAgentId);
  // The video's own agent, for the read-only rows.
  const videoAgent = effectiveAgent(video, agentList);
  // Read before the isUsable guard: in its false branch `agent` narrows away.
  const agentArchived = !!agent?.archived_at;
  const agentUsable = isUsable(agent);
  const model = resolvedModel(video, agentList, picks);
  const effort = pickedEffort ?? initialEffort(video);
  const changed = agentChanged(video, agentList, pickedAgentId);
  const options = agentOptions(video, agentList);
  // The agent group reopens at every human checkpoint (TMDEV-110); between
  // them an agent or the renderer holds the video and it is read-only.
  const atCheckpoint = video.status === "TOPIC_PROPOSED" || video.status === "SCRIPT_READY"
    || video.status === "VIDEO_READY";

  const handleReviseSubmit = async (feedback: string) => {
    await fetch(`/api/proxy/videos/${video.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: "human", content: feedback }),
    });
    const action = video.status === "TOPIC_PROPOSED" ? "revise-topic"
      : video.status === "SCRIPT_READY" ? "revise-script"
      : video.status === "VIDEO_READY" ? "revise-video"
      : null;
    if (action) {
      // A revision is the next piece of agent work, so it goes to the picked
      // agent. An untouched picker keeps the exact three-argument call.
      const extra = agentPicksPayload(video, agentList, picks);
      if (Object.keys(extra).length > 0) onAction(video.id, action, video, extra);
      else onAction(video.id, action, video);
    }
    onClose();
  };

  const voice = shownVoice(pickedVoice, video, defaultVoiceId);
  // At TOPIC_PROPOSED (TMDEV-127) and SCRIPT_READY. The API lists no
  // voice_conflicts at TOPIC_PROPOSED — the script is written after approval,
  // for whichever voice is picked — so nothing is greyed out there.
  const voicePickers = voices.length > 0 && (
    <>
      <div className="flex items-end gap-2">
        <PickerField label="Voice">
          <select
            data-testid="video-modal-voice-select"
            value={voice}
            onChange={(e) => setPickedVoice(e.target.value)}
            className="w-full rounded border border-[#2a2a42] bg-[#131325] px-3 py-2 text-sm text-[#f0f0ff]"
          >
            {voiceMissing(voices, voice) && (
              <option value={voice} disabled>{voice ? `${voice} (not in roster)` : "No voice set"}</option>
            )}
            {/* A voice whose model cannot speak this script is
                shown but not pickable; the API would refuse it. */}
            {voices.map((v) => (
              <option key={v.voice_id} value={v.voice_id}
                      disabled={!!voiceConflict(video, v.voice_id)}
                      title={voiceConflict(video, v.voice_id) || undefined}>
                {voiceLabel(v)}{voiceConflict(video, v.voice_id) ? " — can't voice this script" : ""}
              </option>
            ))}
          </select>
        </PickerField>
        <VoicePreviewButton voiceId={voice} disabled={voiceMissing(voices, voice)} />
      </div>
      {voiceConflict(video, voice) && (
        <p data-testid="video-modal-voice-conflict" className="text-xs text-amber-400">
          This voice can&apos;t speak the script as written:{" "}
          {voiceConflict(video, voice)}
        </p>
      )}
    </>
  );

  const agentPickers = (
    <>
      <PickerField label="Agent" readOnly={options.length === 0}>
        {options.length === 0 ? (
          <div
            data-testid="video-modal-agent-name"
            style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-2)" }}
          >
            {agentLabel(video, videoAgent)}
          </div>
        ) : (
          <select
            data-testid="video-modal-agent-select"
            value={pickedAgentId ?? videoAgent?.id ?? video.agent_id ?? ""}
            onChange={(e) => { setPickedAgentId(e.target.value); setPickedModel(null); }}
            title="Agent that does this video's next piece of work"
            className="w-full rounded border border-[#2a2a42] bg-[#131325] px-3 py-2 text-sm text-[#f0f0ff]"
          >
            {options.map((o) => (
              <option key={o.id} value={o.id} disabled={o.disabled}>{o.label}</option>
            ))}
          </select>
        )}
      </PickerField>
      <PickerField label="Model">
        <select
          data-testid="video-modal-model-input"
          value={agentUsable ? model : ""}
          disabled={!agentUsable}
          onChange={(e) => setPickedModel(e.target.value)}
          title="Agent model for this video"
          className="w-full rounded border border-[#2a2a42] bg-[#131325] px-3 py-2 text-sm text-[#f0f0ff]"
        >
          {agentUsable
            ? agent.models.map((m, i) => (
                <option key={m} value={m}>{i === 0 ? `${m} (default)` : m}</option>
              ))
            : <option value="">—</option>}
        </select>
      </PickerField>
      <PickerField label="Effort">
        <select
          data-testid="video-modal-effort-input"
          value={effort}
          onChange={(e) => setPickedEffort(e.target.value)}
          title="Agent effort level for this video"
          className="w-full rounded border border-[#2a2a42] bg-[#131325] px-3 py-2 text-sm text-[#f0f0ff]"
        >
          <option value="">{effortOptionLabel(agent)}</option>
          {AGENT_EFFORTS.map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
      </PickerField>
      {/* A model belongs to one agent's list, so a new agent starts on its own
          default — said at the moment of the change. */}
      {changed && pickedModel === null && agent && (
        <div
          data-testid="video-modal-agent-reset-note"
          style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--amber)" }}
        >
          Model reset to {agent.name}&apos;s default
        </div>
      )}
      {!agentUsable && (
        <div
          data-testid="video-modal-model-hint"
          style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--amber)" }}
        >
          {agentArchived
            ? "This video's agent is uninstalled — no model can be chosen."
            : !agentsLoaded
              ? video.status === "TOPIC_PROPOSED"
                ? "Agent list not loaded here — the agent's default model will be used."
                : "Agent list not loaded here — the agent and model stay as they are."
              : "This video's agent is not installed — no model can be chosen."}
        </div>
      )}
    </>
  );

  const leftTabs = (["topic", "script", "video", "publications", "comments", "logs"] as const)
    .filter((tab) => {
      if (tab === "script") return !!video.script;
      if (tab === "video") return !!video.video_path;
      // Only once the video has actually been published somewhere — an empty
      // tab on every unpublished video is pure noise.
      if (tab === "publications") return publications.length > 0;
      return true;
    });
  // Topic leads the tab strip because it reads first, but it must not steal the
  // default from a video that has a script or a render — those are what a human
  // opens the modal for. It becomes the default only before either exists, which
  // is exactly the TOPIC_PROPOSED checkpoint where the brief is the thing being
  // judged. (Previously that case landed on Comments, which showed nothing.)
  const defaultLeftTab = video.script ? "script" : video.video_path ? "video" : "topic";

  const commentCount = video.comments?.length ?? 0;
  // Live posts drive every "open it" affordance now. videos.youtube_url is
  // deliberately still on the row and still writable — it is retired as a read
  // path, not dropped.
  const livePosts = publications.filter((p) => p.status === "PUBLISHED" && p.post_url);
  // An archived video is frozen server-side (every PATCH 409s), so none of the
  // status actions are offered — only its live-post links survive.
  const archived = !!video.archived_at;
  // Exactly when {voicePickers} renders below; the read-only voice rows show
  // everywhere else, like the agent rows (TMDEV-147).
  const voicePickerShown = !archived && voices.length > 0
    && (video.status === "TOPIC_PROPOSED" || video.status === "SCRIPT_READY");
  const deletable = canDelete(video);
  const retryable = publishingEnabled && canRetryPublish(video, publications.length);
  const stuck = isAgentStuck(video);

  // Retry agent (TMDEV-129): clears the stuck flag so the scheduled agent
  // picks the video up again on its next pass. The status is left alone.
  const handleRetryAgent = async () => {
    if (retryingAgent) return;
    setRetryingAgent(true);
    setRetryAgentError("");
    try {
      await retryAgent(video.id);
      refreshVideo(video.id);
    } catch (e) {
      setRetryAgentError(e instanceof Error ? e.message : "Retry agent failed.");
    } finally {
      setRetryingAgent(false);
    }
  };

  // Retry publishing (TMDEV-97). The server checks postforme first: a live post
  // is adopted and settles in place; only when nothing is live does the video
  // go back to VIDEO_APPROVED, and then the normal Publish dialog opens.
  const handleRetryPublish = async () => {
    if (retrying) return;
    setRetrying(true);
    setRetryError("");
    try {
      const res = await fetch(`/api/proxy/videos/${video.id}/publish/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setRetryError(body.error ?? "Retry publishing failed.");
        return;
      }
      refreshVideo(video.id);
      refreshPublications(video.id);
      if (body.outcome === "republish") setPublishOpen(true);
    } catch {
      setRetryError("Retry publishing failed.");
    } finally {
      setRetrying(false);
    }
  };

  // Cancel schedule (TMDEV-133). postforme deletes the post first and the
  // video follows; there is no reschedule — cancel, then schedule again.
  const handleCancelSchedule = async () => {
    if (cancellingSchedule) return;
    if (!window.confirm("Cancel this scheduled post? Nothing will be posted, and the video goes back to Video Approved.")) return;
    setCancellingSchedule(true);
    setCancelScheduleError("");
    try {
      const res = await fetch(`/api/proxy/videos/${video.id}/schedule/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setCancelScheduleError(body.error ?? "Cancelling the schedule failed.");
      }
      refreshVideo(video.id);
      refreshPublications(video.id);
    } catch {
      setCancelScheduleError("Cancelling the schedule failed.");
    } finally {
      setCancellingSchedule(false);
    }
  };

  return (
    <>
      <Dialog open={!!seed} onOpenChange={(v) => !v && onClose()}>
        <DialogContent
          data-testid="video-modal"
          className="flex flex-col overflow-hidden border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff] p-0"
          style={{ width: "95vw", maxWidth: 1280, height: "88vh", maxHeight: "88vh" }}
        >
          {/* Header */}
          <DialogHeader
            style={{
              flexShrink: 0,
              padding: "18px 28px 14px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <DialogTitle
              style={{
                fontSize: 16,
                fontWeight: 600,
                color: "var(--ink)",
                lineHeight: 1.35,
                fontFamily: "var(--sans)",
                marginBottom: 8,
              }}
            >
              {video.title || video.topic}
            </DialogTitle>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <StatusBadge status={video.status} />
              {video.archived_at && (
                <span
                  data-testid="archived-badge"
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9,
                    color: "var(--red)",
                    textTransform: "uppercase",
                    letterSpacing: "0.14em",
                  }}
                >
                  Archived {formatDateTime(video.archived_at, timeZone)} {tzLabel}
                </span>
              )}
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 9,
                  color: "var(--dim)",
                  textTransform: "uppercase",
                  letterSpacing: "0.14em",
                }}
              >
                v{video.video_version}
              </span>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 9,
                  color: "var(--mute)",
                  textTransform: "uppercase",
                  letterSpacing: "0.14em",
                }}
              >
                {video.id}
              </span>
            </div>
          </DialogHeader>

          {/* Two-column body */}
          <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

            {/* ── LEFT: tabbed content ── */}
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
                borderRight: "1px solid var(--border)",
              }}
            >
              <Tabs
                defaultValue={initialTab && leftTabs.includes(initialTab as typeof leftTabs[number]) ? initialTab : defaultLeftTab}
                className="flex flex-1 flex-col overflow-hidden"
              >
                <TabsList
                  style={{
                    flexShrink: 0,
                    background: "var(--bg)",
                    borderBottom: "1px solid var(--border)",
                    borderRadius: 0,
                    padding: "0 20px",
                    height: 40,
                    gap: 4,
                    justifyContent: "flex-start",
                  }}
                >
                  {leftTabs.map((tab) => {
                    const label =
                      tab === "comments" && commentCount > 0
                        ? `Comments (${commentCount})`
                        : tab === "publications"
                          ? "Publishing Results"
                          : tab.charAt(0).toUpperCase() + tab.slice(1);
                    return (
                      <TabsTrigger
                        key={tab}
                        value={tab}
                        className="rounded-none border-b-2 border-transparent px-3 h-10 text-xs font-medium
                                   text-[#9a9ab8] hover:text-[#f0f0ff] transition-colors
                                   data-[state=active]:border-amber-400 data-[state=active]:text-[#f0f0ff]
                                   data-[state=active]:bg-transparent"
                      >
                        {label}
                      </TabsTrigger>
                    );
                  })}
                </TabsList>

                {/* Topic — the full descriptive brief. The header shows only the
                    short display name, so this is where the whole text lives. */}
                <TabsContent value="topic" className="mt-0 flex-1 overflow-y-auto" style={{ padding: "24px 28px" }}>
                  <p
                    data-testid="video-topic-body"
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: 13,
                      lineHeight: 1.8,
                      color: "var(--ink)",
                      fontFamily: "var(--sans)",
                      margin: 0,
                    }}
                  >
                    {video.topic}
                  </p>
                </TabsContent>

                {/* Script */}
                {video.script && (
                  <TabsContent value="script" className="mt-0 flex-1 overflow-y-auto" style={{ padding: "24px 28px" }}>
                    {video.script_segments && video.script_segments.length > 0 ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                        {video.script_segments.map((seg, i) => (
                          <div
                            key={seg.id}
                            data-testid={`script-segment-${seg.id}`}
                            style={{
                              padding: "16px 0",
                              borderBottom:
                                i < video.script_segments!.length - 1 ? "1px solid var(--border)" : "none",
                            }}
                          >
                            <p
                              style={{
                                margin: "0 0 8px",
                                whiteSpace: "pre-wrap",
                                fontSize: 13,
                                lineHeight: 1.8,
                                color: "var(--ink)",
                                fontFamily: "var(--sans)",
                              }}
                            >
                              {stripVoiceMarkup(seg.voice)}
                            </p>
                            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                              <span
                                style={{
                                  flexShrink: 0,
                                  fontFamily: "var(--mono)",
                                  fontSize: 9,
                                  textTransform: "uppercase",
                                  letterSpacing: "0.14em",
                                  color: "var(--amber)",
                                  paddingTop: 2,
                                }}
                              >
                                Visual
                              </span>
                              <span
                                style={{
                                  fontSize: 12,
                                  lineHeight: 1.55,
                                  color: "var(--dim)",
                                  fontStyle: "italic",
                                }}
                              >
                                {seg.visual || "—"}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <pre
                        style={{
                          whiteSpace: "pre-wrap",
                          fontSize: 13,
                          lineHeight: 1.8,
                          color: "var(--ink)",
                          fontFamily: "var(--sans)",
                          margin: 0,
                        }}
                      >
                        {video.script}
                      </pre>
                    )}
                  </TabsContent>
                )}

                {/* Video */}
                {video.video_path && (
                  <TabsContent value="video" className="mt-0 flex-1 overflow-y-auto" style={{ padding: "24px 28px" }}>
                    <video
                      src={videoStreamUrl(video)}
                      controls
                      style={{
                        width: "100%",
                        maxHeight: "calc(88vh - 180px)",
                        border: "1px solid var(--border)",
                        display: "block",
                      }}
                    />
                  </TabsContent>
                )}

                {/* Always present, unlike Publishing Results: a per-video log
                    is most useful exactly when nothing else on this video
                    worked, so gating it on success would hide it when needed. */}
                  <TabsContent value="logs" className="mt-0 flex-1 overflow-y-auto"
                               style={{ padding: "24px 28px" }}>
                    <LogList
                      records={logs}
                      testId="video-log-list"
                      emptyLabel={
                        "No log records for this video. Records only exist for work done since "
                        + "structured logging was deployed, so an older video will be empty."
                      }
                    />
                  </TabsContent>

                {/* Analytics — where this video went, and how it is doing.
                    Figures are worker-captured snapshots, never a live read. */}
                {publications.length > 0 && (
                  <TabsContent value="publications" className="mt-0 flex-1 overflow-y-auto"
                               style={{ padding: "24px 28px" }}>
                    {publications.map((pub) => (
                      <div
                        key={pub.id}
                        data-testid={`publication-${pub.id}`}
                        style={{
                          border: "1px solid var(--border)", background: "var(--panel)",
                          padding: "12px 14px", marginBottom: 10,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span style={{ fontFamily: "var(--mono)", fontSize: 11,
                                         color: "var(--ink)" }}>
                            {pub.platform ? platformLabel(pub.platform) : "unknown"}
                          </span>
                          <span
                            style={{
                              fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.12em",
                              color: pub.status === "PUBLISHED" ? "var(--green)"
                                   : pub.status === "FAILED" ? "var(--red)" : "var(--amber)",
                            }}
                          >
                            {/* A target of a scheduled post is not pending in
                                any sense a human would act on — it is waiting
                                for its time. */}
                            {pub.status === "PENDING" && video.status === "SCHEDULED"
                              ? "SCHEDULED" : pub.status}
                          </span>
                        </div>
                        {pub.post_url && (
                          /* The URL itself, not a "View post" label — it is the
                             thing you copy, paste and check, and seeing it also
                             confirms which account it actually landed on. */
                          <a
                            href={pub.post_url}
                            target="_blank"
                            rel="noreferrer"
                            data-testid={`publication-url-${pub.id}`}
                            style={{ fontFamily: "var(--mono)", fontSize: 10.5,
                                     color: "var(--blue)", marginTop: 8,
                                     display: "block", wordBreak: "break-all" }}
                          >
                            {pub.post_url}
                          </a>
                        )}
                        {pub.error && (
                          <p
                            data-testid={`publication-error-${pub.id}`}
                            style={{ fontFamily: "var(--mono)", fontSize: 10,
                                     color: "var(--amber)", marginTop: 8 }}
                          >
                            {pub.error}
                          </p>
                        )}
                      </div>
                    ))}
                    <p style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)",
                                marginTop: 14 }}>
                      View counts and other figures live on the Analytics page — this tab is where
                      the video went and whether it got there.
                    </p>
                  </TabsContent>
                )}

                {/* Comments */}
                <TabsContent
                  value="comments"
                  className="mt-0"
                  style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}
                >
                  {/* Thread */}
                  <div style={{ flex: 1, overflowY: "auto", padding: "20px 28px" }}>
                    {(!video.comments || video.comments.length === 0) && (
                      <p style={{ fontSize: 13, color: "var(--dim)" }}>No comments yet.</p>
                    )}
                    {video.comments?.map((c) => (
                      <div
                        key={c.id}
                        style={{
                          display: "flex",
                          gap: 14,
                          marginBottom: 20,
                          padding: "14px 16px",
                          background: c.author === "human" ? "rgba(100,120,255,0.04)" : "rgba(245,166,35,0.04)",
                          border: `1px solid ${c.author === "human" ? "rgba(100,120,255,0.12)" : "rgba(245,166,35,0.12)"}`,
                        }}
                      >
                        {/* Avatar / label */}
                        <div style={{ flexShrink: 0, paddingTop: 2 }}>
                          <div
                            style={{
                              width: 28,
                              height: 28,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              background: c.author === "human" ? "rgba(100,120,255,0.15)" : "rgba(245,166,35,0.15)",
                              border: `1px solid ${c.author === "human" ? "rgba(100,120,255,0.3)" : "rgba(245,166,35,0.3)"}`,
                              fontFamily: "var(--mono)",
                              fontSize: 9,
                              letterSpacing: "0.1em",
                              color: c.author === "human" ? "var(--blue)" : "var(--amber)",
                              textTransform: "uppercase",
                            }}
                          >
                            {c.author === "human" ? "YOU" : "AI"}
                          </div>
                        </div>

                        {/* Content */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontFamily: "var(--mono)",
                              fontSize: 9,
                              textTransform: "uppercase",
                              letterSpacing: "0.12em",
                              color: c.author === "human" ? "var(--blue)" : "var(--amber)",
                              marginBottom: 6,
                            }}
                          >
                            {c.author === "human" ? "You" : "Agent"}
                          </div>
                          <div style={{ fontSize: 13 }}>
                            <MdContent>{c.content}</MdContent>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Read-only by design: a human comment is only ever added
                      through Request Revision, which exists only at the three
                      checkpoints and moves the video to REVISION_REQUESTED in
                      the same step. A free-form box here let a note land at any
                      status with nothing acting on it. */}
                  <p
                    data-testid="comments-readonly-note"
                    style={{
                      flexShrink: 0,
                      margin: 0,
                      borderTop: "1px solid var(--border)",
                      padding: "12px 28px",
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      letterSpacing: "0.06em",
                      color: "var(--mute)",
                    }}
                  >
                    Comments are added by the agent, or by you through Request Revision.
                  </p>
                </TabsContent>
              </Tabs>
            </div>

            {/* ── RIGHT: sidebar ── */}
            <div
              style={{
                width: 300,
                flexShrink: 0,
                overflowY: "auto",
                display: "flex",
                flexDirection: "column",
                background: "var(--panel)",
              }}
            >
              {/* Actions */}
              {((!archived && (
                video.status === "TOPIC_PROPOSED" ||
                video.status === "SCRIPT_READY" ||
                video.status === "VIDEO_READY" ||
                ((video.status === "VIDEO_APPROVED" || video.status === "SCHEDULED") && publishingEnabled))) ||
                deletable || stuck) && (
                <div
                  data-testid="video-modal-actions"
                  style={{
                    padding: "18px 20px 14px",
                    borderBottom: "1px solid var(--border)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      textTransform: "uppercase",
                      letterSpacing: "0.14em",
                      color: "var(--dim)",
                      marginBottom: 4,
                    }}
                  >
                    Actions
                  </div>
                  {stuck && (
                    <>
                      <p
                        data-testid="agent-stuck-banner"
                        className="font-mono text-[11px] text-amber-400"
                      >
                        The scheduled agent ran {video.agent_no_progress_count ?? 0} sessions in a
                        row without moving this video forward, so it has stopped picking it up.
                        The comments and poll.log say what the sessions did.
                      </p>
                      <ActionBtn
                        fullWidth
                        variant="primary"
                        disabled={retryingAgent}
                        onClick={handleRetryAgent}
                      >
                        {retryingAgent ? "Retrying…" : "Retry agent"}
                      </ActionBtn>
                      {retryAgentError && (
                        <p
                          data-testid="retry-agent-error"
                          className="font-mono text-[11px] text-amber-400"
                        >
                          {retryAgentError}
                        </p>
                      )}
                    </>
                  )}
                  {!archived && video.status === "TOPIC_PROPOSED" && (
                    <>
                      <PickerField label="Visual style">
                        <select
                          data-testid="video-modal-style-select"
                          value={selectedStyle}
                          onChange={(e) =>
                            setSelectedStyle(e.target.value as Video["visual_style"])}
                          title="Visual register for this video"
                          className="w-full rounded border border-[#2a2a42] bg-[#131325] px-3 py-2 text-sm text-[#f0f0ff]"
                        >
                          {styleOptions(illustratedAvailable).map((o) => (
                            <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
                          ))}
                        </select>
                      </PickerField>
                      {(readyProfiles.length > 0 || selectedProfile !== "") && (
                        <PickerField label="Script profile">
                          <select
                            data-testid="video-modal-profile-select"
                            value={selectedProfile}
                            onChange={(e) => setSelectedProfile(e.target.value)}
                            className="w-full rounded border border-[#2a2a42] bg-[#131325] px-3 py-2 text-sm text-[#f0f0ff]"
                          >
                            <option value="">No profile (generic style)</option>
                            {staleProfile && (
                              <option value={selectedProfile}>{profileName || selectedProfile}</option>
                            )}
                            {readyProfiles.map((p) => (
                              <option key={p.id} value={p.id}>{p.name}</option>
                            ))}
                          </select>
                        </PickerField>
                      )}
                      {voicePickers}
                      {agentPickers}
                      <ActionBtn fullWidth variant="primary" onClick={() => { onAction(video.id, "approve-topic", video, { script_profile_id: selectedProfile, visual_style: selectedStyle, ...topicVoicePayload(pickedVoice), ...topicApprovalPayload(video, agentList, picks) }); onClose(); }}>
                        Approve Topic
                      </ActionBtn>
                      <ActionBtn fullWidth variant="danger" onClick={() => { onAction(video.id, "reject-topic", video); onClose(); }}>
                        Reject Topic
                      </ActionBtn>
                      <ActionBtn fullWidth variant="amber" onClick={() => setReviseOpen(true)}>
                        Request Revision
                      </ActionBtn>
                    </>
                  )}
                  {!archived && video.status === "SCRIPT_READY" && (
                    <>
                      {voicePickers}
                      {agentPickers}
                      <ActionBtn fullWidth variant="primary" onClick={() => { onAction(video.id, "approve-script", video, { voice_id: voice, ...agentPicksPayload(video, agentList, picks) }); onClose(); }}>
                        Approve Script
                      </ActionBtn>
                      <ActionBtn fullWidth variant="amber" onClick={() => setReviseOpen(true)}>
                        Request Revision
                      </ActionBtn>
                    </>
                  )}
                  {!archived && video.status === "VIDEO_READY" && (
                    <>
                      {/* Only Request Revision uses these — approving the
                          video hands no work to an agent. */}
                      {agentPickers}
                      <ActionBtn fullWidth variant="primary" onClick={() => { onAction(video.id, "approve-video", video); onClose(); }}>
                        Approve Video
                      </ActionBtn>
                      <ActionBtn fullWidth variant="amber" onClick={() => setReviseOpen(true)}>
                        Request Revision
                      </ActionBtn>
                    </>
                  )}
                  {!archived && video.status === "VIDEO_APPROVED" && publishingEnabled && (
                    <ActionBtn fullWidth variant="primary" onClick={() => setPublishOpen(true)}>
                      Publish…
                    </ActionBtn>
                  )}
                  {!archived && video.status === "SCHEDULED" && publishingEnabled && (
                    <>
                      <ActionBtn
                        fullWidth
                        variant="amber"
                        disabled={cancellingSchedule}
                        onClick={handleCancelSchedule}
                      >
                        {cancellingSchedule ? "Cancelling…" : "Cancel schedule"}
                      </ActionBtn>
                      {cancelScheduleError && (
                        <p
                          data-testid="cancel-schedule-error"
                          className="font-mono text-[11px] text-amber-400"
                        >
                          {cancelScheduleError}
                        </p>
                      )}
                    </>
                  )}
                  {retryable && (
                    <>
                      <ActionBtn
                        fullWidth
                        variant="primary"
                        disabled={retrying}
                        onClick={handleRetryPublish}
                      >
                        {retrying ? "Checking postforme…" : "Retry publishing"}
                      </ActionBtn>
                      {retryError && (
                        <p
                          data-testid="retry-publish-error"
                          className="font-mono text-[11px] text-amber-400"
                        >
                          {retryError}
                        </p>
                      )}
                    </>
                  )}
                  {deletable && (
                    <ActionBtn fullWidth variant="danger" onClick={() => setDeleteOpen(true)}>
                      Delete Video
                    </ActionBtn>
                  )}
                </div>
              )}

              {/* Scheduled for — shown wherever the modal opens, not only where
                  publishing controls are offered: when a post goes out is the
                  one thing a SCHEDULED video exists to say. */}
              {video.status === "SCHEDULED" && video.scheduled_at && (
                <div
                  data-testid="video-modal-scheduled-for"
                  style={{
                    padding: "18px 20px 14px",
                    borderBottom: "1px solid var(--border)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      textTransform: "uppercase",
                      letterSpacing: "0.14em",
                      color: "var(--dim)",
                    }}
                  >
                    Scheduled for
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "#38bdf8", lineHeight: 1.5 }}>
                    {formatScheduled(video.scheduled_at, video.scheduled_timezone || timeZone)}
                  </div>
                  {video.scheduled_timezone && video.scheduled_timezone !== timeZone && (
                    <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--dim)" }}>
                      {formatDateTime(video.scheduled_at, timeZone)} {tzLabel}
                    </div>
                  )}
                </div>
              )}

              {/* Published to — one link per live post. Deliberately not under
                  Actions: opening a post changes nothing about the video, and on
                  an archived video it used to be the only thing under that
                  heading, which read as if it did something. */}
              {livePosts.length > 0 && (
                <div
                  data-testid="video-modal-published-to"
                  style={{
                    padding: "18px 20px 14px",
                    borderBottom: "1px solid var(--border)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      textTransform: "uppercase",
                      letterSpacing: "0.14em",
                      color: "var(--dim)",
                      marginBottom: 4,
                    }}
                  >
                    Published to
                  </div>
                  {livePosts.map((pub) => (
                    <ActionBtn
                      key={pub.id}
                      fullWidth
                      variant="ghost"
                      onClick={() => window.open(pub.post_url, "_blank")}
                    >
                      {platformLabel(pub.platform)} →
                    </ActionBtn>
                  ))}
                </div>
              )}

              {/* Details */}
              <div style={{ padding: "14px 20px" }}>
                <MetaRow label="Strategy" value={<span style={{ textTransform: "capitalize" }}>{video.strategy}</span>} />
                <MetaRow
                  label="Producibility"
                  value={
                    <span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 15, color: "var(--amber)" }}>
                        {isScored(video.producibility_score) ? video.producibility_score : "—"}
                      </span>
                      {isScored(video.producibility_score) && (
                        <span style={{ color: "var(--dim)", fontSize: 12 }}> / 10</span>
                      )}
                    </span>
                  }
                />
                {video.status !== "TOPIC_PROPOSED" && (
                  <>
                    <MetaRow
                      label="Script profile"
                      value={video.script_profile_id
                        ? (profileName || video.script_profile_id)
                        : <span style={{ color: "var(--dim)" }}>None — generic style</span>}
                    />
                    {/* The agent group has live pickers at every checkpoint
                        of a non-archived video, so it is read-only here only
                        where no picker is shown. */}
                    {(archived || !atCheckpoint) && (
                      <>
                        <MetaRow label="Agent" value={agentLabel(video, videoAgent)} />
                        <MetaRow
                          label="Agent model"
                          value={video.agent_model
                            ? video.agent_model
                            : <span style={{ color: "var(--dim)" }}>{modelLabel(video, videoAgent)}</span>}
                        />
                        <MetaRow
                          label="Agent effort"
                          value={video.agent_effort
                            ? video.agent_effort
                            : <span style={{ color: "var(--dim)" }}>{effortLabel(video, videoAgent)}</span>}
                        />
                      </>
                    )}
                    <MetaRow label="Visual style" value={videoStyleLabel(video)} />
                  </>
                )}
                {/* voice_info comes with the single-video fetch, not the list
                    row the modal opens on, so the rows appear once it lands. */}
                {!voicePickerShown && video.voice_info && (
                  <>
                    <MetaRow
                      label="Voice"
                      value={video.voice_info.name
                        ? video.voice_info.name
                        : video.voice_info.voice_id
                          ? <span>{video.voice_info.voice_id} <span style={{ color: "var(--dim)" }}>(not in roster)</span></span>
                          : <span style={{ color: "var(--dim)" }}>None set</span>}
                    />
                    <MetaRow
                      label="Voice model"
                      value={!video.voice_info.model_id
                        ? <span style={{ color: "var(--dim)" }}>—</span>
                        : video.voice_info.model_voiced
                          ? video.voice_info.model_id
                          : <span>{video.voice_info.model_id} <span style={{ color: "var(--dim)" }}>(current setting)</span></span>}
                    />
                  </>
                )}
                <MetaRow label="Created" value={`${formatDateTime(video.created_at, timeZone)} ${tzLabel}`} />
                <MetaRow label="Updated" value={`${formatDateTime(video.updated_at, timeZone)} ${tzLabel}`} />
              </div>

              {/* Cost */}
              <CostBreakdown videoId={video.id} refreshKey={video.updated_at} />

              {/* AI Review Feedback */}
              {video.gemini_feedback && (
                <div
                  style={{
                    borderTop: "1px solid var(--border)",
                    padding: "14px 20px",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      textTransform: "uppercase",
                      letterSpacing: "0.14em",
                      color: "var(--dim)",
                      marginBottom: 8,
                    }}
                  >
                    AI Review Feedback
                  </div>
                  <div style={{ fontSize: 12 }}>
                    <MdContent>
                      {reviewExpanded
                        ? video.gemini_feedback
                        : clipReview(video.gemini_feedback)}
                    </MdContent>
                  </div>
                  {!reviewExpanded &&
                    (isClipped(video.gemini_feedback) || video.gemini_feedback_truncated) && (
                      <button
                        data-testid="review-read-more"
                        onClick={() => {
                          setReviewExpanded(true);
                          // Usually a no-op: the modal refetches the full record
                          // on open, so the whole review is already in hand. This
                          // only does work when the clipped seed row from a list
                          // payload is still in place because that refresh has
                          // not landed yet.
                          if (video.gemini_feedback_truncated) refreshVideo(video.id);
                        }}
                        style={reviewToggleStyle}
                      >
                        Read more
                      </button>
                    )}
                  {reviewExpanded && (
                    <button
                      data-testid="review-read-less"
                      onClick={() => setReviewExpanded(false)}
                      style={reviewToggleStyle}
                    >
                      Show less
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
          {/* Rendered inside this dialog's content so Base UI treats it as a
              nested child dialog, not a sibling. As a sibling it only worked
              when opened later from the sidebar button; opened together with
              the modal (openRevise, the Quick Actions Revise button) each modal
              marked the other aria-hidden, hiding both from assistive tech.
              It still portals to <body>, so the layout is unchanged. */}
          <ReviseDialog
            open={reviseOpen}
            title={video.title || video.topic}
            onClose={() => setReviseOpen(false)}
            onSubmit={handleReviseSubmit}
          />
        </DialogContent>
      </Dialog>

      {video && (
        <PublishDialog
          open={publishOpen}
          videoId={video.id}
          videoTitle={video.title || video.topic}
          onClose={() => setPublishOpen(false)}
          onPublished={() => {
            refreshVideo(video.id);
            refreshPublications(video.id);
          }}
        />
      )}

      {/* One meaning of "delete" everywhere (TMDEV-84): the files go, the
          record stays, archived. Same operation as the retention sweep. */}
      <Dialog open={deleteOpen} onOpenChange={(v) => !v && setDeleteOpen(false)}>
        <DialogContent
          data-testid="delete-dialog"
          className="border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff]"
          style={{ maxWidth: 440 }}
        >
          <DialogHeader>
            <DialogTitle style={{ fontSize: 15, fontWeight: 600 }}>Delete this video?</DialogTitle>
          </DialogHeader>
          <p style={{ fontSize: 13, lineHeight: 1.6, color: "var(--dim)", margin: 0 }}>
            The rendered video and its working files (audio, images, scene config) are
            deleted and cannot be recovered. The record — topic, script, comments,
            publication links and analytics — is kept in the Archive.
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
            <ActionBtn variant="ghost" onClick={() => setDeleteOpen(false)}>Cancel</ActionBtn>
            <ActionBtn
              variant="danger"
              onClick={() => { onAction(video.id, "delete", video); setDeleteOpen(false); onClose(); }}
            >
              Delete
            </ActionBtn>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
