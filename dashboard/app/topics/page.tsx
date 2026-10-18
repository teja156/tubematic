"use client";

import { useEffect, useState } from "react";
import type { Project, ProjectStatus, ScriptProfile, Voice } from "@/lib/types";
import { voiceLabel } from "@/lib/voices";
import { illustratedAvailable, styleLabel, styleOptions } from "@/lib/visualStyles";
import { codePoints } from "@/lib/utils";
import { SectionLabel } from "@/components/SectionLabel";
import { MiningSources } from "@/components/MiningSources";

const ALL_MODES: Array<{ key: string; label: string; accent: string; desc: string }> = [
  { key: "curriculum", label: "Curriculum",  accent: "var(--indigo)", desc: "Enumerate sub-topics from seed domains" },
  { key: "trending",   label: "Trending",    accent: "var(--cyan)",   desc: "Scan configured trending sources" },
  { key: "mining",     label: "Mining",      accent: "var(--green)",  desc: "Spin-offs from YouTube videos via Gemini" },
];

// ── helpers ───────────────────────────────────────────────────────────────────

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

// ── Default voice picker ──────────────────────────────────────────────────────

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
      style={{
        fontFamily: "var(--mono)",
        fontSize: 10.5,
        padding: "5px 6px",
        background: "var(--bg)",
        color: "var(--ink-2)",
        border: "1px solid var(--border-2)",
        flexShrink: 0,
      }}
    >
      <option value="">Install default voice</option>
      {stale && <option value={value}>{value} (removed)</option>}
      {voices.map((v) => <option key={v.voice_id} value={v.voice_id}>{voiceLabel(v)}</option>)}
    </select>
  );
}

// ── Default script profile picker ─────────────────────────────────────────────

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
      style={{
        fontFamily: "var(--mono)",
        fontSize: 10.5,
        padding: "5px 6px",
        background: "var(--bg)",
        color: "var(--ink-2)",
        border: "1px solid var(--border-2)",
        flexShrink: 0,
        // Profile names are user-supplied with no length limit, and a select is
        // as wide as its longest option: unbounded, one long name pushed the
        // controls after it off-screen. The open list still shows it in full.
        maxWidth: 220,
      }}
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
      style={{
        fontFamily: "var(--mono)",
        fontSize: 10.5,
        padding: "4px 6px",
        width: 52,
        background: "var(--bg)",
        color: "var(--ink-2)",
        border: "1px solid var(--border-2)",
      }}
    />
  );
}

// A small caption above each per-domain picker. Three unlabelled dropdowns in a
// row read as one control; the <label> also names its select for screen readers.
// The fixed width matters: a select is as wide as its longest option (243px for
// the style picker's "needs an OpenAI key" one), and three at that width
// crushed a seed row's domain name to ~70px at 1280px. The select stretches to
// the field, and its open list still shows every option in full. 150px, not
// 170, is what lets a seed row keep its pause button on one line at 1280px
// alongside the topic cap. A field without a width sizes to its content.
function DomainField({ label, width, children }: {
  label: string; width?: number; children: React.ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 3, flexShrink: 0, width }}>
      <span style={{ fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--mute)" }}>
        {label}
      </span>
      {children}
    </label>
  );
}

// ── Domain row ────────────────────────────────────────────────────────────────

function DomainRow({
  project,
  videoCounts,
  onToggle,
  onStyleChange,
  onVoiceChange,
  onProfileChange,
  onCapChange,
  canIllustrate,
  voices,
  profiles,
}: {
  project: Project;
  videoCounts: Record<string, number>;
  onToggle: (id: string, next: ProjectStatus) => void;
  onStyleChange: (id: string, next: string) => void;
  onVoiceChange: (id: string, next: string) => void;
  onProfileChange: (id: string, next: string) => void;
  onCapChange: (id: string, next: number) => void;
  canIllustrate: boolean;
  voices: Voice[];
  profiles: ScriptProfile[];
}) {
  const isPaused = project.status === "paused";
  const isExpired = project.expired === true;
  const accent = project.is_curriculum_seed ? "var(--indigo)" : "var(--dim)";
  const count = videoCounts[project.id] ?? 0;

  return (
    <div
      data-testid={`domain-row-${project.id}`}
      style={{
        display: "flex",
        alignItems: "center",
        // Wraps rather than overlaps on a narrow screen: a seed row carries
        // three pickers, a count, a badge and the pause button, and without
        // wrapping the name shrank to nothing under them at 1024px.
        flexWrap: "wrap",
        gap: 16,
        padding: "12px 16px",
        background: "var(--panel)",
        border: "1px solid var(--border)",
        opacity: isPaused || isExpired ? 0.55 : 1,
        transition: "opacity .15s",
      }}
    >
      {/* Seed indicator */}
      <div
        title={project.is_curriculum_seed ? "Curriculum seed domain" : "Not a curriculum seed"}
        style={{
          width: 7,
          height: 7,
          background: project.is_curriculum_seed ? accent : "var(--border-2)",
          boxShadow: project.is_curriculum_seed ? `0 0 6px ${accent}` : undefined,
          flexShrink: 0,
        }}
      />

      {/* Name + description. The 160px basis is what the row wraps on. */}
      <div style={{ flex: "1 1 160px", minWidth: 160 }}>
        <div style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>
          {project.name}
        </div>
        {project.description && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.06em", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {project.description}
          </div>
        )}
      </div>

      {/* Default visual style. There is no project edit form anywhere in the
          dashboard, so without this a domain created before the register
          existed could never be pinned to one. POST /projects is the upsert
          path, so this needs no new endpoint. */}
      <DomainField label="Visual style" width={150}>
        <select
          data-testid={`domain-style-${project.id}`}
          value={project.default_visual_style ?? ""}
          onChange={(e) => onStyleChange(project.id, e.target.value)}
          title="Register this domain's curriculum videos start in"
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10.5,
            padding: "5px 6px",
            background: "var(--bg)",
            color: "var(--ink-2)",
            border: "1px solid var(--border-2)",
            flexShrink: 0,
          }}
        >
          <option value="">No style</option>
          {styleOptions(canIllustrate).map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
          ))}
        </select>
      </DomainField>

      {/* Default voice (TMDEV-121): every new video filed into this domain,
          whatever its sourcing mode, starts with it. A voice since removed
          from the roster stays visible as "(removed)" rather than silently
          reading as the install default — the API seeds nothing for it. */}
      <DomainField label="Default voice" width={150}>
        <DomainVoiceSelect
          testId={`domain-voice-${project.id}`}
          value={project.default_voice_id ?? ""}
          voices={voices}
          onChange={(next) => onVoiceChange(project.id, next)}
        />
      </DomainField>

      {/* Default script profile: seeds this domain's curriculum videos only,
          like the visual style. A human can still pick another at the topic. */}
      <DomainField label="Script profile" width={150}>
        <DomainProfileSelect
          testId={`domain-profile-${project.id}`}
          value={project.default_script_profile_id ?? ""}
          profiles={profiles}
          onChange={(next) => onProfileChange(project.id, next)}
        />
      </DomainField>

      {/* Topic cap (TMDEV-153): research deduplicates against every topic
          ever filed here, archived ones included, so the domain may only ever
          hold so many. The count beside it is that whole history, which is
          why it can read higher than the video count after it. */}
      <DomainField label="Topic cap">
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <DomainCapInput
            testId={`domain-cap-${project.id}`}
            value={project.topic_cap ?? 100}
            onCommit={(next) => onCapChange(project.id, next)}
          />
          <span data-testid={`domain-topic-count-${project.id}`} style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", whiteSpace: "nowrap" }}>
            {project.topic_count ?? 0} filed
          </span>
        </span>
      </DomainField>

      {/* Video count */}
      <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.12em", color: "var(--dim)", textTransform: "uppercase", textAlign: "right", flexShrink: 0 }}>
        <span style={{ color: "var(--ink-2)", fontWeight: 700 }}>{count}</span>
        <span style={{ marginLeft: 4, color: "var(--mute)" }}>video{count !== 1 ? "s" : ""}</span>
      </div>

      {/* Expired: the domain holds as many topics as its cap allows, so
          research files nothing more here until the cap is raised. Any domain
          can expire, seed or not. */}
      {isExpired && (
        <div
          data-testid={`domain-expired-${project.id}`}
          title="This domain holds as many topics as its cap allows. Research files nothing more here until you raise the cap; manual submissions still go through."
          style={{
            fontFamily: "var(--mono)",
            fontSize: 9.5,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            padding: "3px 8px",
            background: "rgba(255,107,107,0.06)",
            border: "1px solid rgba(255,107,107,0.3)",
            color: "var(--red)",
            flexShrink: 0,
          }}
        >
          EXPIRED
        </div>
      )}

      {/* Pause is a curriculum-seed control: a seed is where its topics come
          FROM, so pausing it stops generation at the root. Any other domain
          only receives topics researched elsewhere, so a pause there could
          not stop them, and the API refuses one. Hence no badge or toggle. */}
      {project.is_curriculum_seed === 1 && (
        <>
          {/* Status badge. ACTIVE beside EXPIRED read as a contradiction, so
              an expired seed shows only EXPIRED; a pause still shows, since
              resuming would not re-open the domain until the cap is raised. */}
          {(isPaused || !isExpired) && <div
            data-testid={`domain-status-${project.id}`}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              padding: "3px 8px",
              background: isPaused ? "rgba(255,255,255,0.04)" : "rgba(101,210,122,0.06)",
              border: `1px solid ${isPaused ? "var(--border-2)" : "rgba(101,210,122,0.24)"}`,
              color: isPaused ? "var(--dim)" : "var(--green)",
              flexShrink: 0,
            }}
          >
            {isPaused ? "PAUSED" : "ACTIVE"}
          </div>}

          {/* Toggle button */}
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
    </div>
  );
}

// ── Add domain form ───────────────────────────────────────────────────────────

function AddDomainForm({ onAdded, canIllustrate, voices, profiles }: {
  onAdded: () => void; canIllustrate: boolean; voices: Voice[]; profiles: ScriptProfile[];
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSeed, setIsSeed] = useState(true);
  // "" is a real choice, not an absence: it means the domain has no
  // preference, which is not the same as pinning every video to "auto".
  const [defaultStyle, setDefaultStyle] = useState("");
  const [defaultVoice, setDefaultVoice] = useState("");
  const [defaultProfile, setDefaultProfile] = useState("");
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
        body: JSON.stringify({ id: slug, name: name.trim(), description: description.trim(), is_curriculum_seed: isSeed, status: "active", default_visual_style: defaultStyle, default_voice_id: defaultVoice, default_script_profile_id: defaultProfile }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setError(body.error ?? "Failed to create domain");
        return;
      }
      setName("");
      setDescription("");
      setIsSeed(true);
      setDefaultStyle("");
      setDefaultVoice("");
      setDefaultProfile("");
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

        <label
          data-testid="domain-style-label"
          style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em", color: "var(--ink-2)" }}
        >
          Visual style
          <select
            data-testid="domain-style-select"
            value={defaultStyle}
            onChange={(e) => setDefaultStyle(e.target.value)}
            title="Register this domain's curriculum videos start in"
            style={{ fontFamily: "var(--mono)", fontSize: 11, padding: "6px 8px", background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--border-2)" }}
          >
            <option value="">No preference</option>
            {styleOptions(canIllustrate).map((o) => (
              <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
            ))}
          </select>
        </label>

        <label
          data-testid="domain-voice-label"
          style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em", color: "var(--ink-2)" }}
        >
          Default voice
          <DomainVoiceSelect testId="domain-voice-select" value={defaultVoice}
                             voices={voices} onChange={setDefaultVoice} />
        </label>

        <label
          data-testid="domain-profile-label"
          style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em", color: "var(--ink-2)" }}
        >
          Script profile
          <DomainProfileSelect testId="domain-profile-select" value={defaultProfile}
                               profiles={profiles} onChange={setDefaultProfile} />
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
  const [voices, setVoices] = useState<Voice[]>([]);
  const [profiles, setProfiles] = useState<ScriptProfile[]>([]);

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
  }, []);

  // Apart from loadAll for the same reason as settings: a failed read leaves
  // only the profile pickers empty, and a held default still shows.
  useEffect(() => {
    apiFetch("/script-profiles")
      .then((r) => (r.ok ? r.json() : null))
      .then((rows) => { if (Array.isArray(rows)) setProfiles(rows); })
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

  async function saveDomain(id: string, patch: Partial<Project>, what: string) {
    const project = projects.find((p) => p.id === id);
    if (!project) return;
    const next = { ...project, ...patch };
    // POST /projects is an upsert, and its ON CONFLICT clause overwrites every
    // column it is given — so the unchanged fields have to be sent back or
    // they are blanked. That is why this re-sends every editable field rather
    // than posting the one that changed; a field missing here is a field any
    // other edit silently clears.
    const r = await apiFetch("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: next.id,
        name: next.name,
        description: next.description,
        is_curriculum_seed: next.is_curriculum_seed === 1,
        status: next.status,
        default_visual_style: next.default_visual_style ?? "",
        default_voice_id: next.default_voice_id ?? "",
        default_script_profile_id: next.default_script_profile_id ?? "",
        topic_cap: next.topic_cap,
      }),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      alert(body.error ?? `Could not change this domain's ${what}`);
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

  function handleDomainStyle(id: string, next: string) {
    return saveDomain(id, { default_visual_style: next as Project["default_visual_style"] }, "style");
  }

  function handleDomainVoice(id: string, next: string) {
    return saveDomain(id, { default_voice_id: next }, "default voice");
  }

  function handleDomainProfile(id: string, next: string) {
    return saveDomain(id, { default_script_profile_id: next }, "script profile");
  }

  // Expiry comes back with the saved row, against the count as it is now.
  function handleDomainCap(id: string, next: number) {
    return saveDomain(id, { topic_cap: next }, "topic cap");
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
        <AddDomainForm onAdded={loadAll} canIllustrate={canIllustrate} voices={voices} profiles={profiles} />
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
            <DomainRow key={p.id} project={p} videoCounts={videoCounts} onToggle={handleToggleDomain} onStyleChange={handleDomainStyle} onVoiceChange={handleDomainVoice} onProfileChange={handleDomainProfile} onCapChange={handleDomainCap} canIllustrate={canIllustrate} voices={voices} profiles={profiles} />
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
              <DomainRow key={p.id} project={p} videoCounts={videoCounts} onToggle={handleToggleDomain} onStyleChange={handleDomainStyle} onVoiceChange={handleDomainVoice} onProfileChange={handleDomainProfile} onCapChange={handleDomainCap} canIllustrate={canIllustrate} voices={voices} profiles={profiles} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
