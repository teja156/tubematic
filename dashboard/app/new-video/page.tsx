"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Agent, Project, ScriptProfile, Video, VisualStyle, Voice } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { VoicePreviewButton } from "@/components/VoicePreviewButton";
import { AGENT_EFFORTS, effortOptionLabel, isUsable } from "@/lib/agents";
import { illustratedAvailable, styleOptions } from "@/lib/visualStyles";
import { voiceLabel } from "@/lib/voices";

// The fixed domain every submission here is filed into. Keep in sync:
// renderer/api/pipeline.py MANUAL_PROJECT_ID.
const MANUAL_PROJECT_ID = "manual";

// Submitting a video by hand, without an agent harness (TMDEV-118). Every
// video made here goes into the one "Manual Videos" domain, unscored — there
// is no agent at submit time to match a domain or score the topic, and
// submitting it is itself the approval. See POST /videos/manual.

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

// Keep in sync: renderer/api/pipeline.py's VIDEO_TITLE_MAX_LEN.
const TITLE_MAX = 70;

const mono = { fontFamily: "var(--mono)" } as const;

const inputStyle = {
  ...mono, fontSize: 12, width: "100%", padding: "8px 10px",
  background: "var(--panel)", border: "1px solid var(--border-2)", color: "var(--ink)",
} as const;

const selectStyle = {
  ...mono, fontSize: 11, padding: "7px 8px", width: "100%",
  background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--border-2)",
} as const;

/** A captioned control. A <label>, so the caption is the control's accessible
 *  name — the same shape as ActionPane's PickerField. The note sits outside
 *  the label, or it would become part of that name. */
function Field({ label, note, children }: { label: string; note?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{
          ...mono, fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--dim)",
        }}>
          {label}
        </span>
        {children}
      </label>
      {note && <span style={{ ...mono, fontSize: 10, color: "var(--mute)" }}>{note}</span>}
    </div>
  );
}

export default function NewVideoPage() {
  // undefined until /agents answers, and left so if it never does.
  const [agents, setAgents] = useState<Agent[] | undefined>(undefined);
  const [agentsFailed, setAgentsFailed] = useState(false);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [installVoiceId, setInstallVoiceId] = useState("");
  // The manual domain's own default voice, which the API seeds a submission
  // with when no voice is picked (TMDEV-121). "" until the domain has one —
  // it only exists after the first manual video.
  const [manualVoiceId, setManualVoiceId] = useState("");
  const [canIllustrate, setCanIllustrate] = useState(true);
  const [profiles, setProfiles] = useState<ScriptProfile[]>([]);

  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  // "" is Automatic: no agent_id is sent and the API deals one by weight.
  const [agentId, setAgentId] = useState("");
  // null = untouched, the idiom every per-video picker uses.
  const [model, setModel] = useState<string | null>(null);
  const [effort, setEffort] = useState("");
  const [profileId, setProfileId] = useState("");
  const [style, setStyle] = useState<VisualStyle>("auto");
  const [voiceId, setVoiceId] = useState("");
  const [approve, setApprove] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Pick<Video, "id" | "title" | "status"> | null>(null);

  // One-shot, not polled — the same reasoning as PipelineClient: these change
  // on other pages, and a stale list only lasts until the next page load.
  useEffect(() => {
    apiFetch("/agents")
      .then((r) => r.json())
      .then((data: Agent[]) => {
        if (Array.isArray(data)) setAgents(data);
        else setAgentsFailed(true);
      })
      .catch(() => setAgentsFailed(true));
    apiFetch("/settings")
      .then((r) => r.json())
      .then((s) => {
        setVoices(s.elevenlabs_voices ?? []);
        setInstallVoiceId(s.elevenlabs_voice_id ?? "");
        setCanIllustrate(illustratedAvailable(s));
      })
      .catch(() => {});
    apiFetch("/projects")
      .then((r) => r.json())
      .then((rows: Project[]) => {
        const manual = Array.isArray(rows) ? rows.find((p) => p.id === MANUAL_PROJECT_ID) : undefined;
        setManualVoiceId(manual?.default_voice_id ?? "");
      })
      .catch(() => {});
    apiFetch("/script-profiles")
      .then((r) => r.json())
      .then((data: ScriptProfile[]) => setProfiles(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const liveAgents = (agents ?? []).filter((a) => !a.archived_at);
  const picked = liveAgents.find((a) => a.id === agentId) ?? null;
  // Under Automatic the agent is not known until the API deals it, so the
  // model stays "" (its default). A picked agent's model is pinned, as
  // approving a topic pins it, so the row records which model made the video.
  const resolvedModel = isUsable(picked)
    ? (model !== null && picked.models.includes(model) ? model : picked.models[0])
    : "";
  const readyProfiles = profiles.filter((p) => p.status === "READY");
  // What "Default" resolves to: the manual domain's voice while it is still in
  // the roster (the API skips a stale one the same way), else the install's.
  const defaultVoiceId = voices.some((v) => v.voice_id === manualVoiceId)
    ? manualVoiceId : installVoiceId;
  const defaultVoiceName = voices.find((v) => v.voice_id === defaultVoiceId)?.name;

  // Code points, not UTF-16 units: the API counts with Python's len(), so an
  // emoji is one character there and two in .length — which would disable
  // submit for a title the API accepts.
  const titleLen = Array.from(title.trim()).length;
  const canSubmit = titleLen > 0 && titleLen <= TITLE_MAX && topic.trim() !== "" && !submitting;

  const agentNote = agentsFailed
    ? "Agent list not loaded — the video will be dealt an agent automatically."
    : agents !== undefined && liveAgents.length === 0
      ? "No agents installed. Install one on the host with onboard.py --install-agent."
      : undefined;

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    setCreated(null);
    const body: Record<string, unknown> = {
      title: title.trim(),
      topic: topic.trim(),
      approve,
      ...(agentId ? { agent_id: agentId } : {}),
      agent_model: resolvedModel,
      agent_effort: effort,
      script_profile_id: profileId,
      visual_style: style,
      voice_id: voiceId,
    };
    try {
      const r = await apiFetch("/videos/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(data?.error ?? "Could not submit the video.");
        return;
      }
      setCreated({ id: data.id, title: data.title, status: data.status });
      // The pickers are kept: someone submitting several videos in a row
      // usually wants the same agent and style for each.
      setTitle("");
      setTopic("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit the video.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <SectionLabel label="New Video" />

      <div style={{ maxWidth: 820, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ ...mono, fontSize: 11, color: "var(--dim)", lineHeight: 1.6 }}>
          Submit a video yourself. It is filed under the <b>Manual Videos</b> domain and is not
          scored — you asked for it, so it needs no rubric to get in.
        </div>

        <Field label="Title" note={`${titleLen}/${TITLE_MAX} — the short name shown on cards`}>
          <input
            data-testid="new-video-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="How DNS resolves a name"
            style={{ ...inputStyle, borderColor: titleLen > TITLE_MAX ? "var(--red)" : "var(--border-2)" }}
          />
        </Field>

        <Field label="Topic" note="The full brief the agent writes the script from">
          <textarea
            data-testid="new-video-topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            rows={6}
            placeholder="What the video is about, the angle, and anything it must cover"
            style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }}
          />
        </Field>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
          <Field label="Agent" note={agentNote}>
            <select
              data-testid="new-video-agent"
              value={agentId}
              disabled={liveAgents.length === 0}
              onChange={(e) => { setAgentId(e.target.value); setModel(null); }}
              style={selectStyle}
            >
              <option value="">Automatic (dealt by weight)</option>
              {liveAgents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </Field>

          <Field label="Model">
            <select
              data-testid="new-video-model"
              value={resolvedModel}
              disabled={!isUsable(picked)}
              onChange={(e) => setModel(e.target.value)}
              style={selectStyle}
            >
              {isUsable(picked)
                ? picked.models.map((m, i) => (
                    <option key={m} value={m}>{i === 0 ? `${m} (default)` : m}</option>
                  ))
                : <option value="">Agent default</option>}
            </select>
          </Field>

          <Field label="Effort">
            <select
              data-testid="new-video-effort"
              value={effort}
              onChange={(e) => setEffort(e.target.value)}
              style={selectStyle}
            >
              <option value="">{effortOptionLabel(picked)}</option>
              {AGENT_EFFORTS.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </Field>

          <Field label="Script profile">
            <select
              data-testid="new-video-profile"
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              style={selectStyle}
            >
              <option value="">No profile (generic style)</option>
              {readyProfiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>

          <Field label="Visual style">
            <select
              data-testid="new-video-style"
              value={style}
              onChange={(e) => setStyle(e.target.value as VisualStyle)}
              style={selectStyle}
            >
              {styleOptions(canIllustrate).map((o) => (
                <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
              ))}
            </select>
          </Field>

          <div style={{ display: "flex", gap: 6, alignItems: "flex-end" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Field label="Voice">
                <select
                  data-testid="new-video-voice"
                  value={voiceId}
                  onChange={(e) => setVoiceId(e.target.value)}
                  style={selectStyle}
                >
                  <option value="">{defaultVoiceName ? `Default (${defaultVoiceName})` : "Default"}</option>
                  {voices.map((v) => <option key={v.voice_id} value={v.voice_id}>{voiceLabel(v)}</option>)}
                </select>
              </Field>
            </div>
            <VoicePreviewButton voiceId={voiceId || defaultVoiceId} disabled={!(voiceId || defaultVoiceId)} />
          </div>
        </div>

        <label style={{ ...mono, fontSize: 12, color: "var(--ink)", display: "flex", gap: 8, alignItems: "flex-start", cursor: "pointer" }}>
          <input
            type="checkbox"
            data-testid="new-video-approve"
            checked={approve}
            onChange={(e) => setApprove(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span>
            Automatically approve topic
            <span style={{ display: "block", fontSize: 10, color: "var(--mute)", marginTop: 2 }}>
              {approve
                ? "Lands at TOPIC_APPROVED — the agent starts scripting on its next poll."
                : "Lands at TOPIC_PROPOSED — approve it on the Pipeline page first."}
            </span>
          </span>
        </label>

        {error && (
          <div data-testid="new-video-error" style={{ ...mono, fontSize: 11, color: "var(--red)" }}>
            {error}
          </div>
        )}
        {created && (
          <div data-testid="new-video-success" style={{ ...mono, fontSize: 11, color: "var(--green)" }}>
            Submitted “{created.title}” at {created.status}.{" "}
            <Link href="/" style={{ color: "var(--amber)" }}>Open the Pipeline →</Link>
          </div>
        )}

        <button
          data-testid="new-video-submit"
          onClick={submit}
          disabled={!canSubmit}
          style={{
            ...mono, fontSize: 11, padding: "9px 14px", alignSelf: "flex-start",
            cursor: canSubmit ? "pointer" : "not-allowed",
            background: "transparent", border: "1px solid var(--amber)", color: "var(--amber)",
            textTransform: "uppercase", letterSpacing: "0.1em",
            opacity: canSubmit ? 1 : 0.5,
          }}
        >
          {submitting ? "Submitting…" : "Submit video"}
        </button>
      </div>
    </>
  );
}
