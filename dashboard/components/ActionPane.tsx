"use client";

import { useState } from "react";
import type { Agent, ScriptProfile, Video, Voice } from "@/lib/types";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { VoicePreviewButton } from "@/components/VoicePreviewButton";
import { shownVoice, topicVoicePayload, voiceConflict, voiceLabel, voiceMissing } from "@/lib/voices";
import { formatDateShort } from "@/lib/datetime";
import { scoreLabel } from "@/lib/utils";
import {
  AGENT_EFFORTS, type AgentPicks, agentChanged, agentLabel, agentOptions, agentPicksPayload,
  effectiveAgent, effortLabel, effortOptionLabel, initialEffort, isUsable, modelLabel,
  pickedAgent, resolvedModel, topicApprovalPayload,
} from "@/lib/agents";
import { styleOptions, videoStyleLabel } from "@/lib/visualStyles";

const STATUS_ACCENT: Partial<Record<string, string>> = {
  TOPIC_PROPOSED: "var(--amber)",
  SCRIPT_READY:   "var(--indigo)",
  VIDEO_READY:    "var(--green)",
};

const STATUS_LABEL: Partial<Record<string, string>> = {
  TOPIC_PROPOSED: "Topic Proposed",
  SCRIPT_READY:   "Script Ready",
  VIDEO_READY:    "Video Ready",
};

// The inbox's groups, in pipeline order. The API returns every status
// interleaved, oldest first; that order is kept inside each group.
const STATUS_ORDER = ["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"];

interface ActionPaneProps {
  videos: Video[];
  voices: Voice[];
  defaultVoiceId: string;
  /** READY script profiles only — a profile still building would be rejected
   *  by the PATCH, so offering it would present an invalid choice as valid. */
  scriptProfiles?: ScriptProfile[];
  /** Every agent row, uninstalled included — resolves each video's agent
   *  and the models its picker offers. undefined = not loaded (yet), which the
   *  picker reports as such rather than as "no agent installed". */
  agents?: Agent[];
  /** False when no OpenAI key is stored: the Illustrated style is then
   *  disabled in the picker. Defaults to true — the API refuses it anyway, so
   *  a page that never loads settings gets a clear error, not a wrong grey. */
  illustratedAvailable?: boolean;
  onAction: (videoId: string, action: string, video: Video, extra?: Record<string, unknown>) => void;
  /** `revise` opens the modal straight into its Request Revision dialog —
   *  the only place a human comment can be added. `picks` carries the row's
   *  agent choices into it, present only when the human touched one, so a
   *  choice made on the row is not dropped on the way to Revise. */
  onOpenModal: (video: Video, tab?: string, opts?: { revise?: boolean; picks?: AgentPicks }) => void;
}

function ActionMeta({ video, scriptProfiles = [], agents = [] }: {
  video: Video;
  scriptProfiles?: ScriptProfile[];
  agents?: Agent[];
}) {
  const agent = effectiveAgent(video, agents);
  const accent = STATUS_ACCENT[video.status] ?? "var(--amber)";
  const label = STATUS_LABEL[video.status] ?? video.status;
  const score = video.producibility_score;
  const { timeZone } = useTimeZone();
  const updatedStr = formatDateShort(video.updated_at, timeZone);
  return (
    // Sized to the picker captions (9px) with tighter tracking so status, score
    // and date share one line in the title column. Each piece is nowrap, so
    // when the column is too narrow the line breaks between pieces rather
    // than inside one ("TOPIC / PROPOSED", "OCT / 5").
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", columnGap: 8, rowGap: 2, fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--dim)" }}>
      <span style={{ width: 6, height: 6, background: accent, boxShadow: `0 0 5px ${accent}`, display: "inline-block", flexShrink: 0 }} />
      <span style={{ whiteSpace: "nowrap" }}>{label}</span>
      <span style={{ color: "var(--faint)" }}>·</span>
      <span style={{ color: "var(--ink-2)", whiteSpace: "nowrap" }}>Score {scoreLabel(score)} · {updatedStr}</span>
      {/* Read-only wherever a choice has no picker on this row — without
          this they would vanish from view entirely at exactly the checkpoints
          where knowing them matters. The topic group is live only at
          TOPIC_PROPOSED; the agent group also at SCRIPT_READY (TMDEV-110). */}
      {video.status !== "TOPIC_PROPOSED" && (
        <span data-testid={`choices-${video.id}`} style={{ color: "var(--dim)" }}>
          · {video.script_profile_id
              ? (scriptProfiles.find((p) => p.id === video.script_profile_id)?.name
                 ?? video.script_profile_id)
              : "generic style"}
          {video.status !== "SCRIPT_READY" && (
            <>
              {" · "}
              {agentLabel(video, agent)}
              {" · "}
              {modelLabel(video, agent)}
              {" · "}
              {effortLabel(video, agent)}
            </>
          )}
          {" · "}
          {videoStyleLabel(video)}
        </span>
      )}
    </div>
  );
}

// A caption above one inline picker. A wrapping <label> so the caption is the
// control's accessible name too; readOnly values (the agent) have no control to
// name, so they get a div.
function PickerField({ label, readOnly, children }: {
  label: string;
  readOnly?: boolean;
  children: React.ReactNode;
}) {
  const Wrapper = readOnly ? "div" : "label";
  return (
    <Wrapper style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--dim)" }}>
        {label}
      </span>
      {children}
    </Wrapper>
  );
}

function ActionButtons({ video, voices, defaultVoiceId, scriptProfiles = [], agents, illustratedAvailable = true, onAction, onOpenModal }: {
  video: Video;
  voices: Voice[];
  defaultVoiceId: string;
  scriptProfiles?: ScriptProfile[];
  agents?: Agent[];
  illustratedAvailable?: boolean;
  onAction: ActionPaneProps["onAction"];
  onOpenModal: ActionPaneProps["onOpenModal"];
}) {
  // null = untouched: the shown voice is recomputed every render, so it follows
  // /settings when that answers after this row mounted (see lib/voices.ts).
  const [pickedVoice, setPickedVoice] = useState<string | null>(null);
  const voice = shownVoice(pickedVoice, video, defaultVoiceId);
  // "" is a real choice, not an absence: it means the script-writing skill's
  // own generic style. So the picker shows whenever there is at least one
  // profile, and always carries the none option.
  const [selectedProfile, setSelectedProfile] = useState(video.script_profile_id ?? "");
  // Frozen after TOPIC_PROPOSED like the two above, so this select is the only
  // moment a human gets to choose the register.
  const [selectedStyle, setSelectedStyle] = useState(video.visual_style ?? "auto");
  // A dropdown of the video's own agent's models — the installer validated
  // that list against the real binary, and the API rejects anything outside
  // it. null = untouched, so the shown value tracks initialModel() until the
  // human picks, including when the agent list arrives after first render.
  const [pickedModel, setPickedModel] = useState<string | null>(null);
  // Same null-means-untouched trick as the model above. Greyed out with the
  // model while the agent is unusable (TMDEV-135, user decision): the levels
  // come from the CLI, but with no agent able to run the video a level records
  // nothing useful. What is NOT known without the agent is which level blank
  // resolves to, so untouched stays "" rather than guessing — see initialEffort.
  const [pickedEffort, setPickedEffort] = useState<string | null>(null);
  // Which agent does the next piece of work (TMDEV-110). Same null-means-
  // untouched trick: only a pick of a *different* agent is ever sent.
  const [pickedAgentId, setPickedAgentId] = useState<string | null>(null);
  const agentList = agents ?? [];
  const picks: AgentPicks = { agentId: pickedAgentId, model: pickedModel, effort: pickedEffort };
  // The agent the model list comes from — the picked one, else the video's.
  const agent = pickedAgent(video, agentList, pickedAgentId);
  // Read before the isUsable guard: in its false branch `agent` narrows away.
  const agentArchived = !!agent?.archived_at;
  const usable = isUsable(agent);
  // Why the agent pickers are greyed out, shown on hover only. A line of text
  // on the row took so much width that the buttons wrapped (TMDEV-135).
  const unusableReason = usable ? null
    : agentArchived ? "Agent uninstalled"
    : agents === undefined ? "Agent list not loaded" : "Agent not installed";
  const greyed = { opacity: 0.45, cursor: "not-allowed" } as const;
  const model = resolvedModel(video, agentList, picks);
  const effort = pickedEffort ?? initialEffort(video);
  const changed = agentChanged(video, agentList, pickedAgentId);
  const options = agentOptions(video, agentList);
  const touched = pickedAgentId !== null || pickedModel !== null || pickedEffort !== null;
  const reviseOpts = touched ? { revise: true, picks } : { revise: true };

  // Agent, Model and Effort: live at both checkpoints whose Approve hands the
  // video to an agent. VIDEO_READY has none — its Approve hands no work to an
  // agent, and its Revise happens in the modal, which has its own.
  const agentPickers = (
    <>
      <PickerField label="Agent" readOnly={options.length === 0}>
        {options.length === 0 ? (
          <span
            data-testid={`agent-name-${video.id}`}
            title={unusableReason ?? "Agent that runs this video"}
            style={{ fontFamily: "var(--mono)", fontSize: 11, padding: "7px 0", color: "var(--ink-2)", whiteSpace: "nowrap", ...(usable ? {} : greyed) }}
          >
            {agentLabel(video, effectiveAgent(video, agentList))}
          </span>
        ) : (
          <select
            data-testid={`agent-select-${video.id}`}
            value={pickedAgentId ?? effectiveAgent(video, agentList)?.id ?? video.agent_id ?? ""}
            onChange={(e) => { setPickedAgentId(e.target.value); setPickedModel(null); }}
            title="Agent that does this video's next piece of work"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              padding: "7px 8px",
              maxWidth: 160,
              background: "var(--panel)",
              color: "var(--ink)",
              border: "1px solid var(--border-2)",
            }}
          >
            {options.map((o) => (
              <option key={o.id} value={o.id} disabled={o.disabled}>{o.label}</option>
            ))}
          </select>
        )}
      </PickerField>
      <PickerField label="Model">
        <select
          data-testid={`model-input-${video.id}`}
          value={usable ? model : ""}
          disabled={!usable}
          onChange={(e) => setPickedModel(e.target.value)}
          title={unusableReason ?? "Agent model for this video"}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            padding: "7px 8px",
            maxWidth: 160,
            background: "var(--panel)",
            color: "var(--ink)",
            border: "1px solid var(--border-2)",
            ...(usable ? {} : greyed),
          }}
        >
          {usable
            ? agent.models.map((m, i) => (
                <option key={m} value={m}>{i === 0 ? `${m} (default)` : m}</option>
              ))
            : <option value="">—</option>}
        </select>
      </PickerField>
      <PickerField label="Effort">
        <select
          data-testid={`effort-input-${video.id}`}
          value={effort}
          disabled={!usable}
          onChange={(e) => setPickedEffort(e.target.value)}
          title={unusableReason ?? "Agent effort level for this video"}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            padding: "7px 8px",
            maxWidth: 120,
            background: "var(--panel)",
            color: "var(--ink)",
            border: "1px solid var(--border-2)",
            ...(usable ? {} : greyed),
          }}
        >
          <option value="">{effortOptionLabel(agent)}</option>
          {AGENT_EFFORTS.map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
      </PickerField>
      {/* A model belongs to one agent's list, so a new agent starts on its own
          default — said here, at the moment of the change, not discovered
          later from a video that ran on a model nobody picked. */}
      {changed && pickedModel === null && agent && (
        <span
          data-testid={`agent-reset-note-${video.id}`}
          style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--amber)", whiteSpace: "nowrap" }}
        >
          Model reset to {agent.name}&apos;s default
        </span>
      )}
    </>
  );
  // Voice: at TOPIC_PROPOSED (TMDEV-127), where a voice on another model is
  // chosen before the script is written for it, and at SCRIPT_READY. The API
  // lists no voice_conflicts at TOPIC_PROPOSED, so nothing is greyed out there.
  const voicePickers = voices.length > 0 && (
    <>
      <PickerField label="Voice">
        <select
          data-testid={`voice-select-${video.id}`}
          value={voice}
          onChange={(e) => setPickedVoice(e.target.value)}
          title={voiceConflict(video, voice) || undefined}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            padding: "7px 8px",
            background: "var(--panel)",
            color: "var(--ink)",
            border: "1px solid var(--border-2)",
            // A <select> is as wide as its longest option, and a disabled
            // voice's label carries its reason — capped so it cannot push
            // Approve off the row. The open list still shows it in full.
            maxWidth: 220,
          }}
        >
          {voiceMissing(voices, voice) && (
            <option value={voice} disabled>{voice ? `${voice} (not in roster)` : "No voice set"}</option>
          )}
          {/* A voice whose model cannot speak this script is shown but
              not pickable; the API would refuse it with a 409. */}
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
      {voiceConflict(video, voice) && (
        <div data-testid={`voice-conflict-${video.id}`} title={voiceConflict(video, voice)}
             style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--amber, #f59e0b)", maxWidth: 260 }}>
          This voice can&apos;t speak the script as written — pick another or request a revision.
        </div>
      )}
    </>
  );
  // Only a READY profile can be set; the full list is passed so an
  // already-selected one still resolves to a name in ActionMeta.
  const readyProfiles = scriptProfiles.filter((p) => p.status === "READY");
  // A curriculum video can arrive holding its domain's default profile, which
  // may have been deleted since (TMDEV-145). It is shown as unavailable rather
  // than reading as "No profile" while being sent, and the picker stays up
  // even with no READY profile left, so the human can clear it.
  const staleProfile = selectedProfile !== "" && !readyProfiles.some((p) => p.id === selectedProfile);
  // The list omits deleted profiles, so there is usually no name to show, and
  // the id is a UUID: say what it is instead.
  const staleName = scriptProfiles.find((p) => p.id === selectedProfile)?.name;
  if (video.status === "TOPIC_PROPOSED") {
    return (
      <>
        {(readyProfiles.length > 0 || selectedProfile !== "") && (
          <PickerField label="Script profile">
            <select
              data-testid={`profile-select-${video.id}`}
              value={selectedProfile}
              onChange={(e) => setSelectedProfile(e.target.value)}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                padding: "7px 8px",
                background: "var(--panel)",
                color: "var(--ink)",
                border: "1px solid var(--border-2)",
                // Profile names have no length limit, and a select is as wide
                // as its longest option; capped like the voice picker.
                maxWidth: 220,
              }}
            >
              <option value="">No profile (generic style)</option>
              {staleProfile && (
                <option value={selectedProfile}>
                  {staleName ? `${staleName} (unavailable)` : "Unavailable profile"}
                </option>
              )}
              {readyProfiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </PickerField>
        )}
        <PickerField label="Visual style">
          <select
            data-testid={`style-select-${video.id}`}
            value={selectedStyle}
            onChange={(e) => setSelectedStyle(e.target.value as typeof selectedStyle)}
            title="Visual register for this video"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              padding: "7px 8px",
              background: "var(--panel)",
              color: "var(--ink)",
              border: "1px solid var(--border-2)",
              // Sized by its longest option, the disabled "Illustrated (needs
              // an OpenAI key)", it was 257px and pushed Revise onto a second
              // line. Every selectable label fits in 150; the open list still
              // shows the disabled one in full.
              maxWidth: 150,
            }}
          >
            {styleOptions(illustratedAvailable).map((o) => (
              <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
            ))}
          </select>
        </PickerField>
        {voicePickers}
        {agentPickers}
        <button
          className="tm-btn"
          onClick={() => onAction(video.id, "approve-topic", video, {
            script_profile_id: selectedProfile, visual_style: selectedStyle,
            ...topicVoicePayload(pickedVoice),
            ...topicApprovalPayload(video, agentList, picks),
          })}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--green)",
            border: "1px solid rgba(101,210,122,0.32)",
            background: "rgba(101,210,122,0.06)",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget;
            el.style.background = "rgba(101,210,122,0.14)";
            el.style.borderColor = "var(--green)";
            el.style.boxShadow = "0 0 12px rgba(101,210,122,0.18)";
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget;
            el.style.background = "rgba(101,210,122,0.06)";
            el.style.borderColor = "rgba(101,210,122,0.32)";
            el.style.boxShadow = "none";
          }}
        >
          Approve
        </button>
        <button
          className="tm-btn"
          onClick={() => onAction(video.id, "reject-topic", video)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--ink-2)",
            border: "1px solid var(--border-2)",
            background: "transparent",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
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
        <button
          className="tm-btn"
          onClick={() => onOpenModal(video, undefined, reviseOpts)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--amber)",
            border: "1px solid rgba(245,166,35,0.32)",
            background: "rgba(245,166,35,0.06)",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
        >
          Revise
        </button>
      </>
    );
  }
  if (video.status === "SCRIPT_READY") {
    return (
      <>
        <button
          className="tm-btn"
          onClick={() => onOpenModal(video, "script")}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--ink-2)",
            border: "1px solid var(--border-2)",
            background: "transparent",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
        >
          Read
        </button>
        {voicePickers}
        {agentPickers}
        <button
          className="tm-btn"
          onClick={() => onAction(video.id, "approve-script", video, {
            // Always sent, picked or not: the API checks every voice_id against
            // the script, which is what catches a voice whose model was edited
            // in Settings after scripting.
            voice_id: voice, ...agentPicksPayload(video, agentList, picks),
          })}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--green)",
            border: "1px solid rgba(101,210,122,0.32)",
            background: "rgba(101,210,122,0.06)",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget;
            el.style.background = "rgba(101,210,122,0.14)";
            el.style.borderColor = "var(--green)";
            el.style.boxShadow = "0 0 12px rgba(101,210,122,0.18)";
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget;
            el.style.background = "rgba(101,210,122,0.06)";
            el.style.borderColor = "rgba(101,210,122,0.32)";
            el.style.boxShadow = "none";
          }}
        >
          Approve
        </button>
        <button
          className="tm-btn"
          onClick={() => onOpenModal(video, undefined, reviseOpts)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--amber)",
            border: "1px solid rgba(245,166,35,0.32)",
            background: "rgba(245,166,35,0.06)",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
        >
          Revise
        </button>
      </>
    );
  }
  if (video.status === "VIDEO_READY") {
    return (
      <>
        <button
          className="tm-btn"
          onClick={() => onOpenModal(video, "video")}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--ink-2)",
            border: "1px solid var(--border-2)",
            background: "transparent",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
        >
          Watch
        </button>
        <button
          className="tm-btn"
          onClick={() => onAction(video.id, "approve-video", video)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--green)",
            border: "1px solid rgba(101,210,122,0.32)",
            background: "rgba(101,210,122,0.06)",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget;
            el.style.background = "rgba(101,210,122,0.14)";
            el.style.borderColor = "var(--green)";
            el.style.boxShadow = "0 0 12px rgba(101,210,122,0.18)";
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget;
            el.style.background = "rgba(101,210,122,0.06)";
            el.style.borderColor = "rgba(101,210,122,0.32)";
            el.style.boxShadow = "none";
          }}
        >
          Approve
        </button>
        {/* Names the Video tab: a rendered video also has a script, and the
            modal's default tab prefers Script, so cancelling the dialog would
            otherwise leave the human on the script, not the video under review.
            A video without a file ignores the name and falls back safely. */}
        <button
          className="tm-btn"
          onClick={() => onOpenModal(video, "video", { revise: true })}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            padding: "8px 16px",
            color: "var(--amber)",
            border: "1px solid rgba(245,166,35,0.32)",
            background: "rgba(245,166,35,0.06)",
            cursor: "pointer",
            textTransform: "uppercase",
            minWidth: 92,
            transition: "all .12s",
          }}
        >
          Revise
        </button>
      </>
    );
  }
  return null;
}

export function ActionPane({ videos, voices, defaultVoiceId, scriptProfiles = [], agents, illustratedAvailable = true, onAction, onOpenModal }: ActionPaneProps) {
  const [flashing, setFlashing] = useState<Record<string, "approve" | "reject">>({});
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  // Statuses the human switched off. Stored as the excluded set, so every
  // status starts shown — including one this list has not seen yet.
  const [filteredOut, setFilteredOut] = useState<Set<string>>(new Set());

  function handleAction(videoId: string, action: string, video: Video, extra?: Record<string, unknown>) {
    const kind = action.includes("reject") ? "reject" : "approve";
    setFlashing((p) => ({ ...p, [videoId]: kind }));
    setTimeout(() => {
      setHidden((s) => new Set(s).add(videoId));
      setFlashing((p) => { const { [videoId]: _, ...rest } = p; return rest; });
    }, 550);
    if (extra !== undefined) onAction(videoId, action, video, extra);
    else onAction(videoId, action, video);
  }

  const visible = videos.filter((v) => !hidden.has(v.id));

  if (visible.length === 0) {
    return (
      <div data-testid="action-pane" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
        <div style={{ padding: "28px", textAlign: "center", fontFamily: "var(--mono)", color: "var(--dim)", letterSpacing: "0.2em", fontSize: 11 }}>
          ◆ INBOX ZERO — NO ACTIONS PENDING
        </div>
      </div>
    );
  }

  // A status the API might add later still gets a group, after the known
  // ones, rather than vanishing from the inbox.
  const statuses = [...STATUS_ORDER, ...new Set(visible.map((v) => v.status).filter((st) => !STATUS_ORDER.includes(st)))];
  const groups = statuses
    .map((status) => ({ status, rows: visible.filter((v) => v.status === status) }))
    .filter((g) => g.rows.length > 0);
  const shownGroups = groups.filter((g) => !filteredOut.has(g.status));

  function toggle(status: string) {
    setFilteredOut((s) => {
      const next = new Set(s);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }

  return (
    <div data-testid="action-pane" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
      {/* Status filter. Deliberately not remembered across reloads: a filter
          forgotten in a browser would hide videos waiting on a human. */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", padding: "12px 18px", borderBottom: "1px solid var(--border)" }}>
        {statuses.map((status) => {
          const count = visible.filter((v) => v.status === status).length;
          const on = !filteredOut.has(status);
          const accent = STATUS_ACCENT[status] ?? "var(--amber)";
          return (
            <button
              key={status}
              type="button"
              data-testid={`action-filter-${status}`}
              aria-pressed={on}
              onClick={() => toggle(status)}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11.5,
                letterSpacing: "0.04em",
                padding: "7px 14px",
                background: on ? "var(--amber-soft)" : "var(--panel)",
                border: `1px solid ${on ? "rgba(245,166,35,0.4)" : "var(--border)"}`,
                color: on ? "var(--amber)" : "var(--dim)",
                opacity: count === 0 ? 0.55 : 1,
                cursor: "pointer",
                transition: "all .12s",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span style={{ width: 6, height: 6, background: accent, display: "inline-block", flexShrink: 0 }} />
              {STATUS_LABEL[status] ?? status}
              <span style={{ opacity: 0.75, fontSize: 10 }}>{count}</span>
            </button>
          );
        })}
      </div>

      {shownGroups.length === 0 && (
        <div style={{ padding: "28px", textAlign: "center", fontFamily: "var(--mono)", color: "var(--dim)", letterSpacing: "0.2em", fontSize: 11 }}>
          ◆ NO ACTIONS MATCH THE FILTER
        </div>
      )}

      {shownGroups.map((group, gi) => (
        <div key={group.status}>
          <div
            data-testid={`action-group-${group.status}`}
            style={{
              display: "flex", alignItems: "center", gap: 10, padding: "10px 22px 10px 18px",
              borderTop: gi > 0 ? "1px solid var(--border)" : "none",
              borderBottom: "1px solid var(--border)",
              background: "rgba(255,255,255,0.015)",
              fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--dim)",
            }}
          >
            <span style={{ width: 6, height: 6, background: STATUS_ACCENT[group.status] ?? "var(--amber)", display: "inline-block", flexShrink: 0 }} />
            <span>{STATUS_LABEL[group.status] ?? group.status}</span>
            <span style={{ color: "var(--faint)" }}>·</span>
            <span style={{ color: "var(--ink-2)" }}>{group.rows.length}</span>
          </div>
          {group.rows.map((video, i) => {
            const accent = STATUS_ACCENT[video.status] ?? "var(--amber)";
            const flash = flashing[video.id];
            return (
              <div
                key={video.id}
                data-testid={`action-card-${video.id}`}
                className={flash === "approve" ? "tm-flash-ok" : flash === "reject" ? "tm-flash-no" : ""}
                style={{
                  display: "grid",
                  // The title keeps a floor and the controls take the rest, wrapping
                  // when they do not fit. With a plain `1fr auto` the controls took
                  // their full width, and a TOPIC_PROPOSED row (style, voice, agent,
                  // model, effort, three buttons) crushed the title to nothing and
                  // pushed Revise off-screen at 1280px (TMDEV-127).
                  gridTemplateColumns: "4px minmax(220px, 1fr) minmax(0, auto)",
                  alignItems: "center",
                  gap: 18,
                  padding: "18px 22px 18px 18px",
                  borderBottom: i < group.rows.length - 1 ? "1px solid var(--border)" : "none",
                  transition: "background .12s",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.012)"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = ""; }}
              >
                {/* Color bar */}
                <div style={{ width: 2, height: 36, background: accent, boxShadow: `0 0 6px color-mix(in oklab, ${accent} 50%, transparent)` }} />

                {/* Info */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                  <div
                    onClick={() => onOpenModal(video)}
                    style={{ fontFamily: "var(--sans)", fontWeight: 600, fontSize: 14, color: "var(--ink)", letterSpacing: "-0.005em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: "pointer" }}
                    title="Click to open"
                  >
                    {video.title || video.topic}
                  </div>
                  <ActionMeta video={video} scriptProfiles={scriptProfiles} agents={agents} />
                </div>

                {/* Buttons */}
                {/* flex-end, not center: the pickers carry a caption above them, so
                    centring would float every button halfway up a caption. */}
                <div style={{ display: "flex", alignItems: "flex-end", gap: 8, flexWrap: "wrap", justifyContent: "flex-end", rowGap: 10 }}>
                  <ActionButtons video={video} voices={voices} defaultVoiceId={defaultVoiceId} scriptProfiles={scriptProfiles} agents={agents} illustratedAvailable={illustratedAvailable} onAction={handleAction} onOpenModal={onOpenModal} />
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
