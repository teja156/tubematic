"use client";

import { useEffect, useState } from "react";
import type { Agent, GpuStatus, Mascot, Project, ProjectStatus, ScriptProfile, Voice } from "@/lib/types";
import { AGENT_EFFORTS, effortOptionLabel } from "@/lib/agents";
import {
  NO_DOMAIN_DEFAULTS, domainAgent, domainAgentOptions, domainChips, domainDefaults,
  domainModelOptions, type DomainDefaultValues, type DomainLists,
} from "@/lib/domains";
import { mascotGate, mascotGateNote, mascotOptions } from "@/lib/mascots";
import { voiceLabel } from "@/lib/voices";
import { illustratedAvailable, styleOptions } from "@/lib/visualStyles";
import { codePoints } from "@/lib/utils";
import { SectionLabel } from "@/components/SectionLabel";
import { MiningSources } from "@/components/MiningSources";
import { useVisualStyles } from "@/components/VisualStylesProvider";

const ALL_MODES: Array<{ key: string; label: string; accent: string; desc: string }> = [
  { key: "curriculum", label: "Curriculum",  accent: "var(--indigo)", desc: "Enumerate sub-topics from seed domains" },
  { key: "trending",   label: "Trending",    accent: "var(--cyan)",   desc: "Scan configured trending sources" },
  { key: "mining",     label: "Mining",      accent: "var(--green)",  desc: "Spin-offs from YouTube videos via Gemini" },
];

// ── helpers ───────────────────────────────────────────────────────────────────

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

// ── Domain pickers ────────────────────────────────────────────────────────────

// Every picker fills its field. A select is as wide as its longest option
// (profile names are user-supplied with no length limit), so one sized by its
// content pushed the controls after it off-screen; the open list still shows
// every option in full.
const pickerStyle = {
  fontFamily: "var(--mono)",
  fontSize: 11,
  padding: "6px 8px",
  width: "100%",
  minWidth: 0,
  background: "var(--bg)",
  color: "var(--ink)",
  border: "1px solid var(--border-2)",
} as const;

const captionStyle = {
  fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.14em",
  textTransform: "uppercase", color: "var(--dim)",
} as const;

const noteStyle = {
  fontFamily: "var(--mono)", fontSize: 10, lineHeight: 1.5, color: "var(--dim)",
} as const;

function DomainVoiceSelect({ testId, value, voices, onChange }: {
  testId: string; value: string; voices: Voice[]; onChange: (next: string) => void;
}) {
  const stale = value !== "" && !voices.some((v) => v.voice_id === value);
  return (
    <select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title="Voice every new video in this domain starts with"
      style={pickerStyle}
    >
      <option value="">Install default voice</option>
      {stale && <option value={value}>{value} (removed)</option>}
      {voices.map((v) => <option key={v.voice_id} value={v.voice_id}>{voiceLabel(v)}</option>)}
    </select>
  );
}

// "" inherits the install's default mascot, "none" pins no mascot even when the
// install has one. Gated on the GPU like the per-video picker: the mascots are
// disabled (saying why) unless it is working, and fail closed while the status
// loads; the non-mascot choices and a held value stay selectable, so an
// unrelated edit re-sends the stored default untouched.
function DomainMascotSelect({ testId, value, mascots, gpu, onChange }: {
  testId: string; value: string; mascots: DomainLists["mascots"]; gpu: GpuStatus | null;
  onChange: (next: string) => void;
}) {
  const note = mascotGateNote(mascotGate(gpu));
  return (
    <select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title={note || "Experimental: the mascot this domain's new videos start with"}
      style={pickerStyle}
    >
      {mascotOptions(mascots, gpu, value, [
        { value: "", label: "Use install default" },
        { value: "none", label: "None" },
      ]).map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>)}
    </select>
  );
}

function DomainProfileSelect({ testId, value, profiles, onChange }: {
  testId: string; value: string; profiles: ScriptProfile[]; onChange: (next: string) => void;
}) {
  // Only a READY profile can be picked. One held but no longer offered
  // (deleted, or the list failed to load) stays visible rather than silently
  // reading as "No profile" — the API seeds nothing for it. The list omits
  // deleted profiles, so there is usually no name to show, and the id is a
  // UUID: say what it is instead.
  const ready = profiles.filter((p) => p.status === "READY");
  const stale = value !== "" && !ready.some((p) => p.id === value);
  const staleName = profiles.find((p) => p.id === value)?.name;
  return (
    <select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title="Script profile this domain's curriculum videos start with"
      style={pickerStyle}
    >
      <option value="">No profile</option>
      {stale && <option value={value}>{staleName ? `${staleName} (unavailable)` : "Unavailable profile"}</option>}
      {ready.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );
}

// ── Topic cap ───────────────────────────────────────────────────────────────

// Bounds on a domain's topic_cap (TMDEV-153). Keep in sync with
// renderer/api/pipeline.py's and mcp/server.py's TOPIC_CAP_MIN/MAX.
const MIN_TOPIC_CAP = 25;
const MAX_TOPIC_CAP = 750;

// The longest description a domain may be given (TMDEV-170), in code points.
// Keep in sync with renderer/api/pipeline.py's and mcp/server.py's
// PROJECT_DESCRIPTION_MAX_CHARS. Every domain's description rides on every
// research run, so the server refuses anything longer.
const MAX_DOMAIN_DESCRIPTION_CHARS = 2000;

// Commits on blur or Enter, like Settings' number fields, so typing "300" is
// one save rather than three. An entry outside the bounds reverts.
function DomainCapInput({ testId, value, onCommit }: {
  testId: string; value: number; onCommit: (next: number) => void;
}) {
  const [local, setLocal] = useState(String(value));
  useEffect(() => { setLocal(String(value)); }, [value]);
  function commit() {
    const n = Number(local);
    if (Number.isInteger(n) && n >= MIN_TOPIC_CAP && n <= MAX_TOPIC_CAP) {
      if (n !== value) onCommit(n);
    } else {
      setLocal(String(value));
    }
  }
  return (
    <input
      data-testid={testId}
      // Named on the input itself: its <label> also holds the count beside it.
      aria-label="Topic cap"
      type="number"
      min={MIN_TOPIC_CAP}
      max={MAX_TOPIC_CAP}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
      title={`How many topics this domain may ever hold (${MIN_TOPIC_CAP}–${MAX_TOPIC_CAP})`}
      style={{ ...pickerStyle, width: 64 }}
    />
  );
}

// A captioned picker. The <label> also names its control for screen readers.
function DomainField({ label, flex, children }: {
  label: string; flex?: string; children: React.ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0, flex }}>
      <span style={captionStyle}>{label}</span>
      {children}
    </label>
  );
}

// A group of related defaults with the one sentence that says which videos
// they reach. The seven defaults do not all apply to the same videos (the
// style and profile start curriculum videos only), and a bare row of pickers
// gave no place to say so.
function DomainGroup({ title, accent, note, flex = "1 1 220px", children }: {
  title: string; accent?: boolean; note: string; flex?: string; children: React.ReactNode;
}) {
  return (
    <div style={{ flex, minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", color: accent ? "var(--amber)" : "var(--ink-2)" }}>
        {title}
      </div>
      {children}
      <div style={noteStyle}>{note}</div>
    </div>
  );
}

type DefaultControl = "style" | "voice" | "profile" | "mascot" | "agent" | "agent-model" | "agent-effort";

// The Look, Narration and Agent groups: the same controls on a domain's row,
// where each change is saved at once, and in the add-domain form. One
// component so the two cannot drift apart. It renders the groups as siblings;
// the caller supplies the wrapping row and, on a domain's row, the topic cap.
function DomainDefaults({ values, onChange, testId, lists, canIllustrate, gpu }: {
  values: DomainDefaultValues;
  onChange: (patch: Partial<DomainDefaultValues>) => void;
  /** Per domain on a row (`domain-voice-<id>`), fixed in the form. */
  testId: (control: DefaultControl) => string;
  lists: DomainLists;
  canIllustrate: boolean;
  gpu: GpuStatus | null;
}) {
  const agent = domainAgent(lists.agents, values.default_agent_id);
  return (
    <>
      <DomainGroup title="Look"
                   note="The style starts this domain's curriculum videos. The mascot starts every new video.">
        <div style={{ display: "flex", gap: 8 }}>
          <DomainField label="Visual style" flex="1.2 1 0">
            <select
              data-testid={testId("style")}
              value={values.default_visual_style}
              onChange={(e) => onChange({ default_visual_style: e.target.value })}
              title="Register this domain's curriculum videos start in"
              style={pickerStyle}
            >
              <option value="">No style</option>
              {styleOptions(lists.styles, canIllustrate, gpu, values.default_visual_style).map((o) => (
                <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
              ))}
            </select>
          </DomainField>
          <DomainField label="Mascot (exp.)" flex="1 1 0">
            <DomainMascotSelect testId={testId("mascot")} value={values.default_mascot_id}
                                mascots={lists.mascots} gpu={gpu}
                                onChange={(next) => onChange({ default_mascot_id: next })} />
          </DomainField>
        </div>
      </DomainGroup>

      <DomainGroup title="Narration"
                   note="The voice starts every new video. The profile starts curriculum videos.">
        <div style={{ display: "flex", gap: 8 }}>
          <DomainField label="Default voice" flex="1 1 0">
            <DomainVoiceSelect testId={testId("voice")} value={values.default_voice_id}
                               voices={lists.voices}
                               onChange={(next) => onChange({ default_voice_id: next })} />
          </DomainField>
          <DomainField label="Script profile" flex="1 1 0">
            <DomainProfileSelect testId={testId("profile")} value={values.default_script_profile_id}
                                 profiles={lists.profiles}
                                 onChange={(next) => onChange({ default_script_profile_id: next })} />
          </DomainField>
        </div>
      </DomainGroup>

      <DomainGroup title="Agent" accent flex="1.4 1 300px"
                   note="New videos in this domain start on this agent. Automatic deals one by weight. You can still change it on each video.">
        <div style={{ display: "flex", gap: 8 }}>
          <DomainField label="Agent" flex="1.3 1 0">
            <select
              data-testid={testId("agent")}
              value={values.default_agent_id}
              // The model goes with the agent: the stored one belongs to the
              // other agent's list, and the API would refuse the pair.
              onChange={(e) => onChange({ default_agent_id: e.target.value, default_agent_model: "" })}
              title="Agent every new video in this domain starts on"
              style={pickerStyle}
            >
              {domainAgentOptions(lists.agents, values.default_agent_id).map((o) => (
                <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
              ))}
            </select>
          </DomainField>
          <DomainField label="Model" flex="1.3 1 0">
            <select
              data-testid={testId("agent-model")}
              value={values.default_agent_model}
              disabled={!agent}
              onChange={(e) => onChange({ default_agent_model: e.target.value })}
              title={agent ? "Model those videos start on" : "Pick an agent to choose one of its models"}
              style={{ ...pickerStyle, opacity: agent ? 1 : 0.5 }}
            >
              {domainModelOptions(agent, values.default_agent_model).map((o) => (
                <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
              ))}
            </select>
          </DomainField>
          <DomainField label="Effort" flex="1 1 0">
            <select
              data-testid={testId("agent-effort")}
              value={values.default_agent_effort}
              onChange={(e) => onChange({ default_agent_effort: e.target.value })}
              title="Effort level those videos start on"
              style={pickerStyle}
            >
              <option value="">{effortOptionLabel(agent)}</option>
              {AGENT_EFFORTS.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </DomainField>
        </div>
      </DomainGroup>
    </>
  );
}

// ── Domain row ────────────────────────────────────────────────────────────────

const badgeStyle = {
  fontFamily: "var(--mono)", fontSize: 9.5, letterSpacing: "0.16em",
  textTransform: "uppercase", padding: "3px 8px", flexShrink: 0,
} as const;

// One line per domain: what it is, what it overrides, how full it is, and its
// status. The defaults themselves sit in a panel under the line, opened by
// "Edit defaults". Seven pickers and a cap on the line itself left no room
// for the name, and nowhere to say which videos each default applies to.
function DomainRow({ project, videoCounts, onToggle, onSave, lists, canIllustrate, gpu }: {
  project: Project;
  videoCounts: Record<string, number>;
  onToggle: (id: string, next: ProjectStatus) => void;
  onSave: (id: string, patch: Partial<Project>) => void;
  lists: DomainLists;
  canIllustrate: boolean;
  gpu: GpuStatus | null;
}) {
  // Each row keeps its own state, so two domains can be open side by side.
  const [open, setOpen] = useState(false);
  const isPaused = project.status === "paused";
  const isExpired = project.expired === true;
  const isSeed = project.is_curriculum_seed === 1;
  const count = videoCounts[project.id] ?? 0;
  const values = domainDefaults(project);
  const chips = domainChips(values, lists);
  const panelId = `domain-panel-${project.id}`;

  return (
    <div
      data-testid={`domain-row-${project.id}`}
      style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
    >
      <div
        data-testid={`domain-summary-${project.id}`}
        style={{
          display: "flex",
          alignItems: "center",
          // Wraps rather than overlaps on a narrow screen: the name and chips
          // keep their basis and the counts and buttons drop under them.
          flexWrap: "wrap",
          gap: 12,
          padding: "10px 16px",
          opacity: isPaused || isExpired ? 0.55 : 1,
          transition: "opacity .15s",
        }}
      >
        <div
          aria-hidden="true"
          title={isSeed ? "Curriculum seed domain" : "Not a curriculum seed"}
          style={{
            width: 7,
            height: 7,
            background: isSeed ? "var(--indigo)" : "var(--border-2)",
            boxShadow: isSeed ? "0 0 6px var(--indigo)" : undefined,
            flexShrink: 0,
          }}
        />

        {/* Name, description and what the domain overrides. The 300px basis
            is what the line wraps on. */}
        <div style={{ flex: "1 1 300px", minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 0 }}>
            <span data-testid={`domain-name-${project.id}`} style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 600, color: "var(--ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flexShrink: 0, maxWidth: "100%" }}>
              {project.name}
            </span>
            {project.description && (
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--dim)", letterSpacing: "0.06em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
                {project.description}
              </span>
            )}
          </div>
          <div data-testid={`domain-chips-${project.id}`} style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {chips.map((c) => (
              <span key={c.key} data-testid={`domain-chip-${c.key}-${project.id}`} style={{ fontFamily: "var(--mono)", fontSize: 10, padding: "2px 7px", background: "var(--panel-2)", border: "1px solid var(--border-2)", color: "var(--ink)", whiteSpace: "nowrap", maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis" }}>
                <span style={{ color: "var(--dim)", letterSpacing: "0.1em", textTransform: "uppercase", fontSize: 9, marginRight: 6 }}>{c.label}</span>
                {c.value}
              </span>
            ))}
            {chips.length === 0 && (
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--dim)" }}>
                Install defaults for everything
              </span>
            )}
          </div>
        </div>

        {/* The topic count is the domain's whole history, archived and
            rejected topics included, which is why it can read higher than the
            video count under it. */}
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--dim)", textAlign: "right", lineHeight: 1.5, flexShrink: 0 }}>
          <div data-testid={`domain-topics-${project.id}`} style={{ whiteSpace: "nowrap" }}>
            <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>{project.topic_count ?? 0}</span>
            {` / ${project.topic_cap ?? 100} topics`}
          </div>
          <div style={{ whiteSpace: "nowrap" }}>
            <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>{count}</span>
            {` video${count !== 1 ? "s" : ""}`}
          </div>
        </div>

        {/* Expired: the domain holds as many topics as its cap allows, so
            research files nothing more here until the cap is raised. Any domain
            can expire, seed or not. */}
        {isExpired && (
          <div
            data-testid={`domain-expired-${project.id}`}
            title="This domain holds as many topics as its cap allows. Research files nothing more here until you raise the cap; manual submissions still go through."
            style={{ ...badgeStyle, background: "rgba(255,107,107,0.06)", border: "1px solid rgba(255,107,107,0.3)", color: "var(--red)" }}
          >
            EXPIRED
          </div>
        )}

        {/* Pause is a curriculum-seed control: a seed is where its topics come
            FROM, so pausing it stops generation at the root. Any other domain
            only receives topics researched elsewhere, so a pause there could
            not stop them, and the API refuses one. Hence no badge or toggle. */}
        {isSeed && (
          <>
            {/* ACTIVE beside EXPIRED read as a contradiction, so an expired
                seed shows only EXPIRED; a pause still shows, since resuming
                would not re-open the domain until the cap is raised. */}
            {(isPaused || !isExpired) && <div
              data-testid={`domain-status-${project.id}`}
              style={{
                ...badgeStyle,
                background: isPaused ? "rgba(255,255,255,0.04)" : "rgba(101,210,122,0.06)",
                border: `1px solid ${isPaused ? "var(--border-2)" : "rgba(101,210,122,0.24)"}`,
                color: isPaused ? "var(--dim)" : "var(--green)",
              }}
            >
              {isPaused ? "PAUSED" : "ACTIVE"}
            </div>}

            <button
              data-testid={`toggle-domain-${project.id}`}
              onClick={() => onToggle(project.id, isPaused ? "active" : "paused")}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                padding: "6px 14px",
                background: "transparent",
                border: "1px solid var(--border-2)",
                color: isPaused ? "var(--green)" : "var(--dim)",
                cursor: "pointer",
                transition: "all .12s",
                flexShrink: 0,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = isPaused ? "rgba(101,210,122,0.4)" : "rgba(255,107,107,0.4)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-2)"; }}
            >
              {isPaused ? "Resume topic generation" : "Pause topic generation"}
            </button>
          </>
        )}

        <button
          type="button"
          data-testid={`domain-edit-${project.id}`}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            padding: "6px 12px",
            // Wide enough for the longer label, so the buttons before it do
            // not shift when the row opens.
            minWidth: 124,
            background: "var(--amber-soft)",
            border: "1px solid var(--amber-glow)",
            color: "var(--amber)",
            cursor: "pointer",
            flexShrink: 0,
          }}
        >
          {open ? "Close" : "Edit defaults"}
        </button>
      </div>

      {/* Rendered only while open: seven selects per domain, times every
          domain, is a lot of DOM for controls nobody is looking at. */}
      {open && (
        <div
          id={panelId}
          data-testid={panelId}
          style={{ display: "flex", flexWrap: "wrap", gap: "20px 28px", padding: "16px 16px 18px 35px", borderTop: "1px solid var(--border)", background: "var(--panel-2)" }}
        >
          <DomainDefaults
            values={values}
            onChange={(patch) => onSave(project.id, patch as Partial<Project>)}
            testId={(control) => `domain-${control}-${project.id}`}
            lists={lists}
            canIllustrate={canIllustrate}
            gpu={gpu}
          />
          {/* Topic cap (TMDEV-153): research deduplicates against every topic
              ever filed here, archived ones included, so the domain may only
              ever hold so many. */}
          <DomainGroup title="Limits" flex="0 1 190px"
                       note={`How many topics this domain may ever hold (${MIN_TOPIC_CAP} to ${MAX_TOPIC_CAP}).`}>
            <DomainField label="Topic cap">
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <DomainCapInput
                  testId={`domain-cap-${project.id}`}
                  value={project.topic_cap ?? 100}
                  onCommit={(next) => onSave(project.id, { topic_cap: next })}
                />
                <span data-testid={`domain-topic-count-${project.id}`} style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--dim)", whiteSpace: "nowrap" }}>
                  {project.topic_count ?? 0} filed
                </span>
              </span>
            </DomainField>
          </DomainGroup>
        </div>
      )}
    </div>
  );
}

// ── Add domain form ───────────────────────────────────────────────────────────

function AddDomainForm({ onAdded, lists, canIllustrate, gpu }: {
  onAdded: () => void; lists: DomainLists; canIllustrate: boolean; gpu: GpuStatus | null;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSeed, setIsSeed] = useState(true);
  // "" is a real choice in each default, not an absence: no style preference
  // is not the same as pinning every video to "auto".
  const [defaults, setDefaults] = useState<DomainDefaultValues>(NO_DOMAIN_DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
      const r = await apiFetch("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: slug, name: name.trim(), description: description.trim(), is_curriculum_seed: isSeed, status: "active", ...defaults }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setError(body.error ?? "Failed to create domain");
        return;
      }
      setName("");
      setDescription("");
      setIsSeed(true);
      setDefaults(NO_DOMAIN_DEFAULTS);
      onAdded();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      data-testid="add-domain-form"
      onSubmit={handleSubmit}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: "16px",
        background: "var(--panel)",
        border: "1px solid var(--border)",
      }}
    >
      <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--dim)", marginBottom: 2 }}>
        ＋ Add Domain
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <input
          data-testid="domain-name-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Domain name (e.g. Python Internals)"
          required
          style={{
            flex: 2,
            minWidth: 200,
            fontFamily: "var(--mono)",
            fontSize: 12,
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--ink)",
            padding: "8px 12px",
            outline: "none",
          }}
          onFocus={(e) => { e.currentTarget.style.borderColor = "var(--indigo)"; }}
          onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
        />
      </div>

      {/* Its own row: a scope statement wants paragraphs, and a tall box beside
          the one-line name made the row ragged. */}
      <div>
        <textarea
          data-testid="domain-description-input"
          value={description}
          rows={3}
          onChange={(e) => {
            const chars = codePoints(e.target.value);
            setDescription(chars.length > MAX_DOMAIN_DESCRIPTION_CHARS
              ? chars.slice(0, MAX_DOMAIN_DESCRIPTION_CHARS).join("")
              : e.target.value);
          }}
          placeholder="Description / scope (optional)"
          style={{
            width: "100%",
            boxSizing: "border-box",
            resize: "vertical",
            lineHeight: 1.5,
            fontFamily: "var(--mono)",
            fontSize: 12,
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--ink)",
            padding: "8px 12px",
            outline: "none",
          }}
          onFocus={(e) => { e.currentTarget.style.borderColor = "var(--indigo)"; }}
          onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
        />
        <div
          data-testid="domain-description-count"
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10.5,
            textAlign: "right",
            marginTop: 4,
            color: codePoints(description).length >= MAX_DOMAIN_DESCRIPTION_CHARS * 0.9
              ? "var(--amber)" : "var(--mute)",
          }}
        >
          {codePoints(description).length} / {MAX_DOMAIN_DESCRIPTION_CHARS}
        </div>
      </div>

      {/* The same groups a domain's row opens, so what you choose here is
          what you find there. All optional. */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "16px 28px", padding: "12px 0", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
        <DomainDefaults
          values={defaults}
          onChange={(patch) => setDefaults((d) => ({ ...d, ...patch }))}
          testId={(control) => `domain-${control}-select`}
          lists={lists}
          canIllustrate={canIllustrate}
          gpu={gpu}
        />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
        <label
          data-testid="curriculum-seed-checkbox-label"
          style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em", color: "var(--ink-2)" }}
        >
          <input
            data-testid="curriculum-seed-checkbox"
            type="checkbox"
            checked={isSeed}
            onChange={(e) => setIsSeed(e.target.checked)}
            style={{ accentColor: "var(--indigo)", width: 14, height: 14 }}
          />
          Curriculum seed (scheduled runs will enumerate this domain)
        </label>

        <button
          data-testid="add-domain-submit"
          type="submit"
          disabled={busy || !name.trim()}
          style={{
            marginLeft: "auto",
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            padding: "8px 20px",
            background: "rgba(101,100,255,0.08)",
            border: "1px solid rgba(101,100,255,0.32)",
            color: "var(--indigo)",
            cursor: busy || !name.trim() ? "not-allowed" : "pointer",
            opacity: busy || !name.trim() ? 0.5 : 1,
            transition: "all .12s",
          }}
        >
          {busy ? "Adding…" : "Add Domain"}
        </button>
      </div>

      {error && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--red)", letterSpacing: "0.08em" }}>
          ✕ {error}
        </div>
      )}
    </form>
  );
}

// ── Mode toggles ──────────────────────────────────────────────────────────────

// Shown on hover over the greyed-out mining toggle. The API leaves mining out
// of the active strategies while no Gemini key is stored, and refuses turning
// it on (TMDEV-165).
const MINING_UNAVAILABLE = "Needs a Gemini API key — add it under Settings → API Keys";

function ModeToggles({
  active,
  miningAvailable,
  onChange,
}: {
  active: string[];
  miningAvailable: boolean;
  onChange: (next: string[]) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {ALL_MODES.map((mode) => {
        const isOn = active.includes(mode.key);
        const usable = mode.key !== "mining" || miningAvailable;
        return (
          <button
            key={mode.key}
            data-testid={`mode-toggle-${mode.key}`}
            disabled={!usable}
            onClick={() => {
              const next = isOn ? active.filter((m) => m !== mode.key) : [...active, mode.key];
              onChange(next);
            }}
            title={usable ? mode.desc : MINING_UNAVAILABLE}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11.5,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              padding: "8px 16px",
              background: isOn ? `color-mix(in oklab, ${mode.accent} 10%, transparent)` : "var(--panel)",
              border: `1px solid ${isOn ? `color-mix(in oklab, ${mode.accent} 40%, transparent)` : "var(--border)"}`,
              color: isOn ? mode.accent : "var(--dim)",
              cursor: usable ? "pointer" : "not-allowed",
              opacity: usable ? 1 : 0.45,
              transition: "all .12s",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                background: isOn ? mode.accent : "var(--border-2)",
                boxShadow: isOn ? `0 0 5px ${mode.accent}` : undefined,
                flexShrink: 0,
              }}
            />
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

// What an alert calls the field a refused save was about, when the API gave
// no reason of its own.
const SAVED_FIELD: Record<string, string> = {
  default_visual_style: "style",
  default_voice_id: "default voice",
  default_script_profile_id: "script profile",
  default_mascot_id: "mascot",
  default_agent_id: "agent",
  default_agent_model: "agent's model",
  default_agent_effort: "agent's effort",
  topic_cap: "topic cap",
};


export default function TopicsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [videoCounts, setVideoCounts] = useState<Record<string, number>>({});
  const [activeStrategies, setActiveStrategies] = useState<string[]>(["curriculum", "trending", "mining"]);
  const [miningUrls, setMiningUrls] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingModes, setSavingModes] = useState(false);
  const [modesError, setModesError] = useState<string | null>(null);
  // Assumed until /research/strategies answers, so a slow load never shows the
  // toggle greyed out on an install that has the key.
  const [miningAvailable, setMiningAvailable] = useState(true);
  const [savingMining, setSavingMining] = useState(false);
  const [miningError, setMiningError] = useState<string | null>(null);
  // Illustrated is disabled as a domain default when no OpenAI key is stored.
  // Fetched apart from loadAll so a failed settings read changes nothing but
  // this: the API refuses the style itself, so true is the safe fallback.
  const [canIllustrate, setCanIllustrate] = useState(true);
  const [gpu, setGpu] = useState<GpuStatus | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [profiles, setProfiles] = useState<ScriptProfile[]>([]);
  const [mascots, setMascots] = useState<Mascot[]>([]);
  // undefined until GET /agents answers, and for good if it fails: a domain's
  // agent then shows by its id, and only Automatic can be picked.
  const [agents, setAgents] = useState<Agent[] | undefined>(undefined);
  const visualStyles = useVisualStyles();
  const lists: DomainLists = { styles: visualStyles, voices, profiles, mascots, agents };

  async function loadAll() {
    const [projRes, vidRes, stratRes, miningRes] = await Promise.all([
      apiFetch("/projects"),
      apiFetch("/videos"),
      apiFetch("/research/strategies"),
      apiFetch("/research/mining-sources"),
    ]);
    if (projRes.ok) {
      const p: Project[] = await projRes.json();
      setProjects(p);
    }
    if (vidRes.ok) {
      const vids: Array<{ project_id: string | null }> = await vidRes.json();
      const counts: Record<string, number> = {};
      for (const v of vids) {
        if (v.project_id) counts[v.project_id] = (counts[v.project_id] ?? 0) + 1;
      }
      setVideoCounts(counts);
    }
    if (stratRes.ok) {
      const s: { strategies: string[]; mining_available?: boolean } = await stratRes.json();
      setActiveStrategies(s.strategies);
      setMiningAvailable(s.mining_available !== false);
    }
    if (miningRes.ok) {
      const m: { youtube_urls: string[] } = await miningRes.json();
      setMiningUrls(m.youtube_urls);
    }
    setLoading(false);
  }

  useEffect(() => { loadAll(); }, []);

  useEffect(() => {
    apiFetch("/settings")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => {
        if (!s) return;
        setCanIllustrate(illustratedAvailable(s));
        setVoices(Array.isArray(s.elevenlabs_voices) ? s.elevenlabs_voices : []);
      })
      .catch(() => {});
    apiFetch("/render/gpu")
      .then((r) => (r.ok ? r.json() : null))
      .then((g) => setGpu(g && typeof g.status === "string" ? (g as GpuStatus) : null))
      .catch(() => {});
  }, []);

  // Apart from loadAll for the same reason as settings: a failed read leaves
  // only the profile pickers empty, and a held default still shows.
  useEffect(() => {
    apiFetch("/script-profiles")
      .then((r) => (r.ok ? r.json() : null))
      .then((rows) => { if (Array.isArray(rows)) setProfiles(rows); })
      .catch(() => {});
    apiFetch("/mascots")
      .then((r) => (r.ok ? r.json() : null))
      .then((rows) => { if (Array.isArray(rows)) setMascots(rows); })
      .catch(() => {});
    apiFetch("/agents")
      .then((r) => (r.ok ? r.json() : null))
      .then((rows) => { if (Array.isArray(rows)) setAgents(rows); })
      .catch(() => {});
  }, []);

  async function handleToggleDomain(id: string, next: ProjectStatus) {
    const r = await apiFetch(`/projects/${id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    // A refusal is reported, not shown as success: only a curriculum seed can
    // be paused, and the row may have stopped being one since this page loaded.
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      alert(body.error ?? "Could not change this domain's status");
      return;
    }
    setProjects((prev) => prev.map((p) => p.id === id ? { ...p, status: next } : p));
  }

  async function saveDomain(id: string, patch: Partial<Project>) {
    const project = projects.find((p) => p.id === id);
    if (!project) return;
    const next = { ...project, ...patch };
    // POST /projects is an upsert, and its ON CONFLICT clause overwrites every
    // column it is given — so the unchanged fields have to be sent back or
    // they are blanked. That is why this re-sends every editable field rather
    // than posting the one that changed; a field missing here is a field any
    // other edit silently clears. domainDefaults is the list of defaults: an
    // omitted default_mascot_id would reset to "use the install default", an
    // omitted default_agent_id to Automatic.
    const r = await apiFetch("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: next.id,
        name: next.name,
        description: next.description,
        is_curriculum_seed: next.is_curriculum_seed === 1,
        status: next.status,
        ...domainDefaults(next),
        topic_cap: next.topic_cap,
      }),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      alert(body.error ?? `Could not change this domain's ${SAVED_FIELD[Object.keys(patch)[0]] ?? "settings"}`);
      return;
    }
    // The saved row carries the topic count and expiry as they are now. The
    // count loaded with the page can be stale (research may have filed since),
    // so expiry is never worked out here from the new cap. The id check keeps
    // a response that is not a project row from being merged in.
    const saved = await r.json().catch(() => null);
    const fresh = saved && saved.id === id ? (saved as Project) : {};
    setProjects((prev) => prev.map((p) => p.id === id ? { ...p, ...patch, ...fresh } : p));
  }

  async function handleModeChange(next: string[]) {
    setSavingModes(true);
    setModesError(null);
    const res = await apiFetch("/research/strategies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategies: next }),
    });
    if (res.ok) {
      setActiveStrategies(next);
    } else {
      // Nothing was stored, so the toggles keep showing what is in effect.
      const body = await res.json().catch(() => ({}));
      setModesError(typeof body.error === "string" && body.error
        ? body.error
        : "Failed to save research modes — changes were not persisted.");
    }
    setSavingModes(false);
  }

  async function handleMiningUrlsChange(next: string[]) {
    const prev = miningUrls;
    setMiningUrls(next);
    setSavingMining(true);
    setMiningError(null);
    const res = await apiFetch("/research/mining-sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ youtube_urls: next }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setMiningUrls(prev);
      // The API's 400 names the entries it refused; say that, not just "failed".
      setMiningError(typeof body.error === "string" && body.error
        ? body.error
        : "Failed to save mining sources — changes were not persisted.");
    } else if (Array.isArray(body.youtube_urls)) {
      // The list as stored: canonical and deduplicated by the API.
      setMiningUrls(body.youtube_urls);
    }
    setSavingMining(false);
  }

  const seedDomains = projects.filter((p) => p.is_curriculum_seed === 1);
  const otherDomains = projects.filter((p) => p.is_curriculum_seed !== 1);

  return (
    <>
      <SectionLabel label="Topics & Modes" count={`${projects.length} domains`} />

      {/* Research Modes */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--mute)", marginBottom: 10 }}>
          Research Modes{savingModes ? " — saving…" : ""}
        </div>
        <ModeToggles active={activeStrategies} miningAvailable={miningAvailable}
                     onChange={handleModeChange} />
        {modesError && (
          <div data-testid="mode-error" style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--red)", letterSpacing: "0.04em" }}>
            {modesError}
          </div>
        )}
        <div style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.04em" }}>
          Active modes run on the next scheduled research cycle.
          {!miningAvailable && " Mining is off: it needs a Gemini API key."}
        </div>
      </section>

      {/* Mining Sources */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--mute)", marginBottom: 10 }}>
          Mining Sources
        </div>
        <MiningSources
          urls={miningUrls}
          saving={savingMining}
          error={miningError}
          onChange={handleMiningUrlsChange}
        />
      </section>

      {/* Add domain */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--mute)", marginBottom: 10 }}>
          Curriculum Seed Domains
        </div>
        <AddDomainForm onAdded={loadAll} lists={lists} canIllustrate={canIllustrate} gpu={gpu} />
      </section>

      {/* Seed domains list */}
      {loading ? (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.28em", color: "var(--mute)", textTransform: "uppercase", padding: "20px 0" }}>
          LOADING…
        </div>
      ) : seedDomains.length === 0 ? (
        <div style={{ background: "var(--panel)", border: "1px solid var(--border)", padding: "32px", textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.24em", color: "var(--mute)", marginBottom: 6 }}>◇ NO SEED DOMAINS YET</div>
          <div style={{ fontFamily: "var(--sans)", fontSize: 13, color: "var(--ink-2)" }}>
            Add a domain above to let curriculum mode enumerate sub-topics automatically.
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 24 }}>
          {seedDomains.map((p) => (
            <DomainRow key={p.id} project={p} videoCounts={videoCounts} onToggle={handleToggleDomain} onSave={saveDomain} lists={lists} canIllustrate={canIllustrate} gpu={gpu} />
          ))}
        </div>
      )}

      {/* Other domains */}
      {otherDomains.length > 0 && (
        <section>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--mute)", marginBottom: 10 }}>
            Other Domains (trending / mining / manual)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {otherDomains.map((p) => (
              <DomainRow key={p.id} project={p} videoCounts={videoCounts} onToggle={handleToggleDomain} onSave={saveDomain} lists={lists} canIllustrate={canIllustrate} gpu={gpu} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
