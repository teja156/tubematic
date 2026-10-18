"use client";

import { useEffect, useState } from "react";
import type { Agent, Settings, PipelineStatus, RetentionBacklog, Voice } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { AutoPilotPanel } from "@/components/AutoPilotPanel";
import { CostsPanel } from "@/components/CostsPanel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToastStack, useToasts } from "@/components/Toast";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { VoicePreviewButton } from "@/components/VoicePreviewButton";
import { formatDate, formatDateTime, formatRelative } from "@/lib/datetime";
import { AGENT_EFFORTS } from "@/lib/agents";
import { codePoints } from "@/lib/utils";

const STATUS_POLL_MS = 30_000;

// Max named voices in the roster (TMDEV-51). Keep in sync with
// renderer/api/pipeline.py, mcp/server.py and onboard/config.py.
const MAX_VOICES = 5;

// The model sets below are copies of tubematic_core/voice_models.py, pinned by
// renderer/api/tests/test_pipeline.py's cross-copy test. Each roster voice
// carries its own model (TMDEV-121); these only drive the per-voice picker
// and its pronunciation notes.
// eleven_v3 is deliberately absent (TMDEV-26) — it applies no text
// normalization, so phoneme tags break the caption timeline.
// eleven_english_v1 was removed (TMDEV-122): ElevenLabs no longer has it.
const PHONEME_COMPATIBLE_MODELS = ["eleven_turbo_v2", "eleven_flash_v2"];

// Models that take inline IPA through <ipa> tags (TMDEV-123).
const IPA_COMPATIBLE_MODELS = ["eleven_v3"];

// The current (non-deprecated) ElevenLabs model catalog — every model here
// is always usable, since pronunciation (the lexicon + inline <respell>
// tags) is plain text substitution with no model restriction. Models in
// PHONEME_COMPATIBLE_MODELS additionally support exact <phoneme> tags.
// eleven_multilingual_v2 first/default, per onboard.py DEFAULT_DICTIONARY_MODEL.
const DICTIONARY_COMPATIBLE_MODELS = [
  "eleven_multilingual_v2",
  "eleven_v3",
  "eleven_flash_v2_5",
  "eleven_turbo_v2_5",
  "eleven_flash_v2",
  "eleven_turbo_v2",
];

// The image-model catalog; OpenAI is the only image provider (TMDEV-165).
// Keep in sync with renderer/api/pipeline.py, mcp/server.py and
// onboard/config.py. Every model must support transparent backgrounds:
// character_model is chosen from this same list (TMDEV-148).
const OPENAI_IMAGE_MODELS = ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"];

// Gemini models usable for the AI review (VQA-7) — video-understanding text
// models, distinct from the image catalog above. Keep in sync with
// renderer/api/pipeline.py and onboard/config.py.
const AI_REVIEW_MODELS = [
  "gemini-2.5-flash",
  "gemini-3.5-flash",
  "gemini-3.6-flash",
];
// Gemini's documented valid range for videoMetadata.fps is (0, 24].
const MAX_AI_REVIEW_FPS = 24;
// VQA-7: "default AI review loop to 1 and max to 2".
const MAX_AI_REVIEW_LOOPS = 2;
// Keep in sync with renderer/api/pipeline.py and onboard/config.py. 0 would
// mean "delete the file a service is writing right now".
const MIN_LOG_RETENTION_DAYS = 1;
const MAX_LOG_RETENTION_DAYS = 365;
// Keep in sync with renderer/api/pipeline.py and onboard/config.py. Unlike log
// retention, 0 is valid: it turns the video retention sweep off.
const MIN_RETENTION_DAYS = 0;
const MAX_RETENTION_DAYS = 365;
// Keep in sync with renderer/api/pipeline.py's MAX_USER_PREFERENCES_CHARS. The
// text rides on every agent run, so the server rejects anything longer.
const MAX_USER_PREFERENCES_CHARS = 6000;
// Keep in sync with renderer/api/pipeline.py's MAX_CONCURRENT_AGENT_SESSIONS.
const MAX_CONCURRENT_AGENT_SESSIONS = 10;

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

// ── Trending sources editor ───────────────────────────────────────────────────
// Keep in sync with onboard.py SUPPORTED_TRENDING_SOURCES and
// agent_files/skills/tubematic-topic-research/SKILL.md (Trending section).
const SUPPORTED_TRENDING_SOURCES = ["GitHub Trending", "Hacker News", "Lobsters", "Dev.to"];

function TrendingSourcesEditor({
  sources,
  onSave,
  saving,
}: {
  sources: string[];
  onSave: (next: string[]) => void;
  saving: boolean;
}) {
  function handleToggle(src: string) {
    const next = sources.includes(src)
      ? sources.filter((s) => s !== src)
      : [...sources, src];
    onSave(next);
  }

  return (
    <div data-testid="trending-sources-editor" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {SUPPORTED_TRENDING_SOURCES.map((src) => {
        const slug = src.toLowerCase().replace(/[^a-z0-9]+/g, "-");
        const checked = sources.includes(src);
        return (
          <label
            key={src}
            data-testid={`trending-source-checkbox-${slug}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.6 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={saving}
              onChange={() => handleToggle(src)}
              style={{ accentColor: "var(--green, #4ade80)", width: 14, height: 14 }}
            />
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-2)" }}>
              {src}
            </span>
          </label>
        );
      })}
    </div>
  );
}

// ── Number input with save on blur/Enter ──────────────────────────────────────

function NumInput({
  value,
  min,
  max,
  testId,
  onCommit,
}: {
  value: number;
  min: number;
  max: number;
  testId: string;
  onCommit: (n: number) => void;
}) {
  const [local, setLocal] = useState(String(value));

  // keep in sync when parent state changes
  useEffect(() => { setLocal(String(value)); }, [value]);

  function commit() {
    const n = parseInt(local, 10);
    if (!isNaN(n) && n >= min && n <= max) onCommit(n);
    else setLocal(String(value)); // revert invalid
  }

  return (
    <input
      data-testid={testId}
      type="number"
      min={min}
      max={max}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
      style={{
        width: 80,
        background: "var(--input-bg, var(--panel))",
        border: "1px solid var(--border)",
        color: "var(--ink)",
        fontFamily: "var(--mono)",
        fontSize: 12,
        padding: "6px 10px",
        outline: "none",
      }}
    />
  );
}

// ── Secret input (TMDEV-73) ───────────────────────────────────────────────────
// API keys live in the settings table. The server returns only a mask, so the
// value shown here is never a usable key. Committing the unchanged mask is a
// no-op server-side, which is what makes it safe to render it as the field's
// value at all; clearing the field stores "" and removes the key.

function SecretInput({
  value,
  testId,
  onCommit,
}: {
  value: string;
  testId: string;
  onCommit: (v: string) => void;
}) {
  const [local, setLocal] = useState(value);
  const [focused, setFocused] = useState(false);

  useEffect(() => { setLocal(value); }, [value]);

  function commit() {
    setFocused(false);
    if (local !== value) onCommit(local.trim());
  }

  return (
    <input
      data-testid={testId}
      // Only mask while unfocused: the stored value is already a mask, and
      // hiding what the user is actively typing makes a mistyped key
      // undebuggable without helping anyone.
      type={focused ? "text" : "password"}
      value={local}
      placeholder="not set"
      autoComplete="off"
      spellCheck={false}
      onFocus={() => setFocused(true)}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      style={{
        width: 220,
        background: "var(--input-bg, var(--panel))",
        border: "1px solid var(--border)",
        color: "var(--ink)",
        fontFamily: "var(--mono)",
        fontSize: 12,
        padding: "6px 10px",
        outline: "none",
      }}
    />
  );
}

// ── Row helper ────────────────────────────────────────────────────────────────

function Row({ label, note, children }: { label: string; note?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-2)" }}>{label}</div>
        {note && <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", marginTop: 3, letterSpacing: "0.02em" }}>{note}</div>}
      </div>
      {children}
    </div>
  );
}

/** Binary units, so the figure matches `du -h` on the host. */
function formatBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${units[i]}`;
}

function backlogText(b: RetentionBacklog): string {
  if (b.failed.count + b.rejected.count === 0) return "No failed or rejected videos to sweep.";
  return `${b.failed.count} failed and ${b.rejected.count} rejected videos are holding `
    + `${formatBytes(b.failed.bytes + b.rejected.bytes)}.`;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
// One entry per settings group. `fields` is load-bearing, not documentation:
// it scopes both what a tab's Save button sends and what counts as unsaved on
// that tab, so the two can never drift apart.
//
// Pipeline Control is deliberately absent — pause/resume is an operational
// action against a different endpoint, and burying it behind a tab and a Save
// button would make stopping the scheduler a three-click operation. It stays
// pinned above the tabs and still applies immediately.

const TABS = [
  { key: "ai-review", label: "AI Review",
    fields: ["gemini_review_enabled", "ai_review_model", "ai_review_fps", "ai_review_max_loops"] },
  { key: "research", label: "Research",
    fields: ["max_curriculum_per_run", "max_trending_per_run", "max_mining_per_run",
             "research_pending_cap", "max_research_runs_per_day", "trending_sources"] },
  { key: "voice", label: "Voice",
    fields: ["elevenlabs_voices", "elevenlabs_voice_id"] },
  { key: "images", label: "Images",
    fields: ["image_model", "character_model"] },
  { key: "rendering", label: "Rendering",
    fields: ["render_timeout_secs", "max_render_retries", "watermark_enabled"] },
  { key: "logs", label: "Logs", fields: ["log_retention_days"] },
  { key: "retention", label: "Retention", fields: ["retention_days", "unpublished_retention_days"] },
  { key: "api-keys", label: "API Keys",
    fields: ["elevenlabs_api_key", "gemini_api_key", "openai_api_key", "youtube_transcript_api_key",
             "postforme_api_key"] },
  { key: "publishing", label: "Publishing",
    fields: ["publishing_enabled"] },
  { key: "notifications", label: "Notifications",
    fields: ["discord_webhook_url", "notify_topic_proposed", "notify_script_ready",
             "notify_video_ready", "dashboard_base_url"] },
  // The research readouts are read-only; the two agent-session fields
  // (TMDEV-129) are the only settings here.
  { key: "scheduling", label: "Scheduling",
    fields: ["max_concurrent_agent_sessions", "agent_session_timeout_secs"] },
  // No settings fields either — agents live in their own table and save
  // through /agents, so they sit outside the Save/dirty machinery entirely.
  { key: "agents", label: "Agents", fields: [] },
  { key: "preferences", label: "Preferences", fields: ["user_preferences"] },
  // Model prices live in their own table and save through /prices, like the
  // Agents tab — outside the Save/dirty machinery.
  { key: "costs", label: "Costs", fields: [] },
  // Auto Pilot saves its whole configuration through /autopilot as one
  // document — outside the Save/dirty machinery, like Agents and Costs.
  { key: "auto-pilot", label: "Auto Pilot", fields: [] },
] as const satisfies ReadonlyArray<{ key: string; label: string; fields: readonly (keyof Settings)[] }>;

type TabKey = (typeof TABS)[number]["key"];

// ── Page ──────────────────────────────────────────────────────────────────────

// At module scope on purpose. Declared inside SettingsPage, it got a fresh
// function identity on every render, so React treated it as a different
// component type and remounted it -- replacing the <button> DOM node. Blurring
// a NumInput commits into `draft`, which re-renders the parent, so clicking
// SAVE straight from a focused number field swapped the button out between
// mousedown and mouseup and the browser never synthesized a `click` at all:
// the first click on SAVE silently did nothing.
function SaveBar({
  tabKey,
  count,
  saving,
  onSave,
}: {
  tabKey: TabKey;
  count: number;
  saving: boolean;
  onSave: (tabKey: TabKey) => void;
}) {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: 14,
        marginTop: 22, paddingTop: 16, borderTop: "1px solid var(--border)",
      }}
    >
      <button
        data-testid={`save-${tabKey}`}
        disabled={!count || saving}
        onClick={() => onSave(tabKey)}
        style={{
          fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700,
          letterSpacing: "0.06em", padding: "7px 20px",
          border: `1px solid ${count ? "var(--amber)" : "var(--border)"}`,
          background: count ? "rgba(245,158,11,0.10)" : "var(--panel)",
          color: count ? "var(--amber)" : "var(--mute)",
          cursor: count && !saving ? "pointer" : "not-allowed",
          transition: "all .15s",
        }}
      >
        {saving ? "SAVING…" : "SAVE"}
      </button>
      <span
        data-testid={`dirty-${tabKey}`}
        style={{
          fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.04em",
          color: count ? "var(--amber)" : "var(--mute)",
        }}
      >
        {count ? `${count} unsaved change${count === 1 ? "" : "s"}` : "No changes"}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { timeZone, label: tzLabel } = useTimeZone();
  const [s, setS] = useState<Settings | null>(null);
  const [backlog, setBacklog] = useState<RetentionBacklog | null>(null);
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [saving, setSaving] = useState(false);
  // Edits live here until Save; `s` stays exactly what the server last returned,
  // so cancelling is just dropping the draft and every field has an unambiguous
  // saved value to compare against.
  const [draft, setDraft] = useState<Partial<Settings>>({});
  const [tab, setTab] = useState<TabKey>(TABS[0].key);
  const { toasts, push, dismiss } = useToasts();

  async function load() {
    const r = await apiFetch("/settings");
    if (r.ok) setS(await r.json());
  }

  async function loadBacklog() {
    // Best effort, like loadStatus: without it the field still works, the
    // page just cannot say how much the opt-in would free.
    try {
      const r = await apiFetch("/retention/backlog");
      if (!r.ok) return;
      const body = await r.json();
      if (body?.failed && body?.rejected) setBacklog(body);
    } catch { /* leave the line out */ }
  }

  async function loadStatus() {
    const r = await apiFetch("/pipeline/status");
    if (r.ok) setStatus(await r.json());
    // Degrade silently on failure — the research-window readout falls back to
    // placeholders; it must never block the rest of the Settings page.
  }

  useEffect(() => {
    load();
    loadStatus();
    loadBacklog();
    const id = setInterval(loadStatus, STATUS_POLL_MS);
    return () => clearInterval(id);
  }, []);

  /** Stage an edit. Nothing reaches the API until the tab's Save is clicked. */
  function edit(partial: Partial<Settings>) {
    setDraft((d) => ({ ...d, ...partial }));
  }

  /** The value to render: the staged edit if there is one, else the saved value.
   *  `in` rather than a truthiness check — "" is a legitimate staged value for a
   *  cleared API key. */
  function val<K extends keyof Settings>(key: K): Settings[K] {
    return (key in draft ? draft[key] : s![key]) as Settings[K];
  }

  function dirtyFields(tabKey: TabKey): (keyof Settings)[] {
    const def = TABS.find((t) => t.key === tabKey)!;
    return def.fields.filter((f) => f in draft);
  }

  async function saveTab(tabKey: TabKey) {
    const fields = dirtyFields(tabKey);
    if (!fields.length) return;
    // Scoped to this tab rather than sending `draft` wholesale. Today the two
    // are always identical, because requestTab discards a tab's edits when you
    // leave it — so the draft never holds another tab's fields, and no test can
    // distinguish them (a mutation to `partial = draft` passes the suite).
    // Kept anyway: it makes Save correct on its own terms rather than by
    // depending on that discard behaviour staying exactly as it is.
    const partial = Object.fromEntries(fields.map((f) => [f, draft[f]]));
    setSaving(true);
    try {
      const r = await apiFetch("/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(partial),
      });
      if (r.ok) {
        setS(await r.json());
        // Clear only this tab's fields — another tab may hold edits the user
        // has not saved yet, and dropping those silently is the bug the
        // per-tab confirm exists to prevent.
        setDraft((d) => {
          const next = { ...d };
          fields.forEach((f) => delete next[f]);
          return next;
        });
        push("success", `Saved ${fields.length} setting${fields.length === 1 ? "" : "s"}.`);
      } else {
        // Previously a non-ok response was discarded and the page kept
        // rendering stale state, so a rejected value looked like it applied.
        let detail = `HTTP ${r.status}`;
        try {
          const body = await r.json();
          if (body?.error) detail = body.error;
        } catch { /* non-JSON error body — the status is all we have */ }
        push("error", `Save failed — ${detail}`);
      }
      loadStatus();
    } catch (e) {
      push("error", `Save failed — ${e instanceof Error ? e.message : "unreachable"}`);
    } finally {
      setSaving(false);
    }
  }

  function requestTab(next: string) {
    if (next === tab) return;
    if (dirtyFields(tab).length &&
        !window.confirm("Discard unsaved changes on this tab?")) {
      return;
    }
    // Leaving a tab drops its edits, so the discard the user just confirmed
    // actually happens rather than lurking until some later Save.
    const leaving = dirtyFields(tab);
    if (leaving.length) {
      setDraft((d) => {
        const nextDraft = { ...d };
        leaving.forEach((f) => delete nextDraft[f]);
        return nextDraft;
      });
    }
    setTab(next as TabKey);
  }

  async function setPaused(paused: boolean) {
    setSaving(true);
    try {
      const r = await apiFetch("/pipeline/pause", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paused }),
      });
      if (r.ok) setS((p) => p ? { ...p, pipeline_paused: paused } : p);
    } finally {
      setSaving(false);
    }
  }

  if (!s) return (
    <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.28em", color: "var(--mute)", textTransform: "uppercase", padding: "40px 0" }}>
      LOADING…
    </div>
  );

  const inputStyle = {
    background: "var(--input-bg, var(--panel))",
    border: "1px solid var(--border)",
    color: "var(--ink)",
    fontFamily: "var(--mono)",
    fontSize: 12,
    padding: "6px 10px",
    outline: "none",
  };

  return (
    <>
      <SectionLabel label="Settings" count={saving ? "Saving…" : undefined} />

      {/* ── Section 1: Pipeline Control ── */}
      <SectionLabel label="Pipeline Control" />
      <Row label="Pipeline state" note="Pausing stops the scheduler from advancing new videos.">
        <button
          data-testid="toggle-pipeline-pause"
          onClick={() => setPaused(!s.pipeline_paused)}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.06em",
            padding: "7px 16px",
            border: `1px solid ${s.pipeline_paused ? "var(--red)" : "var(--border-2)"}`,
            background: s.pipeline_paused ? "rgba(239,68,68,0.12)" : "var(--panel)",
            color: s.pipeline_paused ? "var(--red)" : "var(--green)",
            cursor: "pointer",
            transition: "all .15s",
            whiteSpace: "nowrap",
          }}
        >
          {s.pipeline_paused ? "■ PAUSED — click to resume" : "▶ Running — click to pause"}
        </button>
      </Row>

      <Tabs value={tab} onValueChange={requestTab}>
        <TabsList
          style={{
            background: "var(--bg)",
            borderBottom: "1px solid var(--border)",
            borderRadius: 0,
            padding: 0,
            // Wraps rather than scrolls: at ~1024px the tabs outgrow the
            // content column, and body clips horizontal overflow, so a
            // single non-wrapping row would hide the last tabs entirely.
            height: "auto",
            minHeight: 38,
            flexWrap: "wrap",
            maxWidth: "100%",
            gap: 4,
            justifyContent: "flex-start",
            marginTop: 24,
          }}
        >
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key} data-testid={`tab-${t.key}`}>
              {t.label}
              {/* A dot on the tab itself, so unsaved work on a tab you are not
                  looking at is still visible. */}
              {dirtyFields(t.key).length > 0 && (
                <span
                  data-testid={`tab-dirty-${t.key}`}
                  aria-label="unsaved changes"
                  style={{ color: "var(--amber)", marginLeft: 6 }}
                >
                  ●
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="ai-review">
      {/* ── Section 2: AI Review ── */}
      <div data-testid="section-ai-review">
        <SectionLabel label="AI Review" count="Experimental" />
        <Row label="Gemini review" note="Off by default. Sends each rendered video to Gemini to look for defects, and back for revision if it finds any (needs the Gemini key). If the review itself fails, the video still goes to your review as if it had passed — so check its comments to see whether a review ran.">
          {/* Experimental (TMDEV-165): named beside the switch, not only in
              the heading, because this is where review is turned on. */}
          <span
            data-testid="ai-review-experimental"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              padding: "3px 8px",
              border: "1px solid color-mix(in oklab, var(--amber) 40%, transparent)",
              background: "color-mix(in oklab, var(--amber) 10%, transparent)",
              color: "var(--amber)",
              whiteSpace: "nowrap",
            }}
          >
            Experimental
          </span>
          <button
            data-testid="toggle-gemini-review"
            onClick={() => edit({ gemini_review_enabled: !val("gemini_review_enabled") })}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.06em",
              padding: "7px 16px",
              border: `1px solid ${val("gemini_review_enabled") ? "var(--green)" : "var(--border)"}`,
              background: val("gemini_review_enabled") ? "rgba(74,222,128,0.1)" : "var(--panel)",
              color: val("gemini_review_enabled") ? "var(--green)" : "var(--mute)",
              cursor: "pointer",
              transition: "all .15s",
            }}
          >
            {val("gemini_review_enabled") ? "ON" : "OFF"}
          </button>
        </Row>
        <Row label="Review model" note="Which Gemini model reviews each rendered video. The 3.x models cost about 1.4x gemini-2.5-flash per video reviewed — far less than their 5x headline token price, since they tokenise video ~3.7x more cheaply.">
          <select
            data-testid="select-ai-review-model"
            value={AI_REVIEW_MODELS.includes(val("ai_review_model")) ? val("ai_review_model") : AI_REVIEW_MODELS[0]}
            onChange={(e) => edit({ ai_review_model: e.target.value })}
            style={inputStyle}
          >
            {AI_REVIEW_MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </Row>
        <Row label="Sampling rate" note="Frames per second Gemini samples from the video. Its default of 1 is too coarse to see motion defects in a 30fps render. Cost scales linearly with this; videos too long for the chosen rate are sampled lower automatically rather than failing.">
          <NumInput
            value={val("ai_review_fps")}
            min={1}
            max={MAX_AI_REVIEW_FPS}
            testId="input-ai-review-fps"
            onCommit={(n) => edit({ ai_review_fps: n })}
          />
        </Row>
        <Row label="Max review rounds" note="How many times the review can send a video back for revision before it is accepted regardless of findings.">
          <NumInput
            value={val("ai_review_max_loops")}
            min={1}
            max={MAX_AI_REVIEW_LOOPS}
            testId="input-ai-review-max-loops"
            onCommit={(n) => edit({ ai_review_max_loops: n })}
          />
        </Row>
      </div>
          <SaveBar tabKey="ai-review" count={dirtyFields("ai-review").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="research">
      {/* ── Section 3: Per-Run Topic Limits ── */}
      <SectionLabel label="Per-Run Topic Limits" />
      <Row label="Curriculum topics per run">
        <NumInput
          value={val("max_curriculum_per_run")}
          min={0}
          max={50}
          testId="input-max-curriculum-per-run"
          onCommit={(n) => edit({ max_curriculum_per_run: n })}
        />
      </Row>
      <Row label="Trending topics per run">
        <NumInput
          value={val("max_trending_per_run")}
          min={0}
          max={50}
          testId="input-max-trending-per-run"
          onCommit={(n) => edit({ max_trending_per_run: n })}
        />
      </Row>
      <Row label="Mining topics per run">
        <NumInput
          value={val("max_mining_per_run")}
          min={0}
          max={50}
          testId="input-max-mining-per-run"
          onCommit={(n) => edit({ max_mining_per_run: n })}
        />
      </Row>
      <Row
        label="Research pending cap"
        note="Skip research entirely when this many or more topics are already queued."
      >
        <NumInput
          value={val("research_pending_cap")}
          min={0}
          max={50}
          testId="input-research-pending-cap"
          onCommit={(n) => edit({ research_pending_cap: n })}
        />
      </Row>
      <Row
        label="Max research runs per day"
        note="Rolling 24h cap on research agent sessions, independent of the pending-topic queue. 0 disables research entirely."
      >
        <NumInput
          value={val("max_research_runs_per_day")}
          min={0}
          max={50}
          testId="input-max-research-runs-per-day"
          onCommit={(n) => edit({ max_research_runs_per_day: n })}
        />
      </Row>

      {/* ── Section 4: Trending Sources ── */}
      <SectionLabel label="Trending Sources" />
      <div style={{ marginBottom: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.04em" }}>
        Sources the agent scans when generating trending topics.
      </div>
      <TrendingSourcesEditor
        sources={val("trending_sources")}
        onSave={(next) => edit({ trending_sources: next })}
        saving={false}
      />
          <SaveBar tabKey="research" count={dirtyFields("research").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="voice">
      {/* ── Section 5: Voice & Pronunciation ── */}
      <SectionLabel label="Voice & Pronunciation" />
      <div style={{ marginBottom: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.04em" }}>
        Named ElevenLabs voices available for TTS (up to {MAX_VOICES}), each with the model it
        speaks with. Mark one as the default — used whenever a video doesn&apos;t have its own voice
        picked.
      </div>
      <VoicesEditor
        voices={val("elevenlabs_voices")}
        defaultVoiceId={val("elevenlabs_voice_id")}
        onSave={(voices, defaultVoiceId) => edit({ elevenlabs_voices: voices, elevenlabs_voice_id: defaultVoiceId })}
        saving={false}
        inputStyle={inputStyle}
      />
      <div data-testid="voice-model-legend" style={{ marginBottom: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.04em", lineHeight: 1.6 }}>
        {/* Pronunciation is not a separate setting (TMDEV-26): the term
            lexicon and inline <respell> tags work on every model. A voice's
            model only adds exact control on top, detected automatically. */}
        Every model takes the pronunciation lexicon and &lt;respell&gt; tags.{" "}
        {PHONEME_COMPATIBLE_MODELS.join("/")} also take exact &lt;phoneme&gt; tags;{" "}
        {IPA_COMPATIBLE_MODELS.join("/")} exact IPA. A script is written for its voice&apos;s model,
        so changing a voice&apos;s model can stop scripts already written for it from being approved
        with it — request a revision on those.
      </div>
          <SaveBar tabKey="voice" count={dirtyFields("voice").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="images">
      {/* ── Image generation ── */}
      <SectionLabel label="Image Generation" />
      <Row
        label="Image model"
        note="The OpenAI model that draws scene images (the generate_image MCP tool). OpenAI grants model access per project, so the OpenAI key's project must have access to the model chosen here."
      >
        <select
          data-testid="select-image-model"
          value={val("image_model")}
          onChange={(e) => edit({ image_model: e.target.value })}
          style={inputStyle}
        >
          {OPENAI_IMAGE_MODELS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </Row>
      <Row
        label="Character model"
        note="Draws the Illustrated style's transparent characters (the generate_character MCP tool). OpenAI grants model access per project, so the OpenAI key's project must have access to the model chosen here."
      >
        <select
          data-testid="select-character-model"
          value={val("character_model")}
          onChange={(e) => edit({ character_model: e.target.value })}
          style={inputStyle}
        >
          {OPENAI_IMAGE_MODELS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </Row>
          <SaveBar tabKey="images" count={dirtyFields("images").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="rendering">
      {/* ── Rendering ── */}
      <SectionLabel label="Rendering" />
      <Row
        label="Render timeout"
        note="How long a single render attempt may run before the worker kills it and retries. Shown in minutes; stored as render_timeout_secs — same key onboard.py's wizard writes."
      >
        <NumInput
          value={Math.round(val("render_timeout_secs") / 60)}
          min={1}
          max={120}
          testId="input-render-timeout-mins"
          onCommit={(mins) => edit({ render_timeout_secs: mins * 60 })}
        />
      </Row>
      <Row
        label="Max render retries"
        note="How many times a crashed or timed-out render is retried before the video is marked FAILED. Stored as max_render_retries (formerly max_feedback_loops). It used to cap the AI review loop too; that now has its own setting on the AI Review tab."
      >
        <NumInput
          value={val("max_render_retries")}
          min={0}
          max={10}
          testId="input-max-render-retries"
          onCommit={(n) => edit({ max_render_retries: n })}
        />
      </Row>
      <Row
        label="Watermark"
        note={'Burn the "Made with tubematic.ai" mark into the top-right corner of every rendered video. Applies to renders that start after saving; videos already rendered are not changed.'}
      >
        <button
          data-testid="toggle-watermark"
          onClick={() => edit({ watermark_enabled: !val("watermark_enabled") })}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.06em",
            padding: "7px 16px",
            border: `1px solid ${val("watermark_enabled") ? "var(--green)" : "var(--border)"}`,
            background: val("watermark_enabled") ? "rgba(74,222,128,0.1)" : "var(--panel)",
            color: val("watermark_enabled") ? "var(--green)" : "var(--mute)",
            cursor: "pointer",
            transition: "all .15s",
          }}
        >
          {val("watermark_enabled") ? "ON" : "OFF"}
        </button>
      </Row>
          <SaveBar tabKey="rendering" count={dirtyFields("rendering").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="logs">
      {/* ── Logs ── */}
      <SectionLabel label="Logs" />
      <Row
        label="Keep logs for"
        note="Days of structured logs to keep before they are deleted. Each service prunes its own files when it starts and once a day after that, so a change here applies at the next pass rather than immediately — unlike every other setting on this page. Browse them on the Logs page."
      >
        <NumInput
          value={val("log_retention_days")}
          min={MIN_LOG_RETENTION_DAYS}
          max={MAX_LOG_RETENTION_DAYS}
          testId="input-log-retention-days"
          onCommit={(n) => edit({ log_retention_days: n })}
        />
      </Row>
          <SaveBar tabKey="logs" count={dirtyFields("logs").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="retention">
      {/* ── Video retention ── */}
      <SectionLabel label="Video retention" />
      <Row
        label="Delete published videos after"
        note="Days after a video is published before its rendered file and working files (audio, images) are deleted to free disk. The record, its publication links and analytics stay, in the Archive. This setting deletes only published videos. 0 keeps them forever. The render worker checks once an hour."
      >
        <NumInput
          value={val("retention_days")}
          min={MIN_RETENTION_DAYS}
          max={MAX_RETENTION_DAYS}
          testId="input-retention-days"
          onCommit={(n) => edit({ retention_days: n })}
        />
      </Row>
      <Row
        label="Delete failed and rejected videos after"
        note="Days after a failed or rejected video last changed before its rendered file and working files are deleted and it moves to the Archive. A failed video can no longer be retried once it is archived. 0, the default, keeps them forever. Checked with the setting above, once an hour."
      >
        <NumInput
          value={val("unpublished_retention_days")}
          min={MIN_RETENTION_DAYS}
          max={MAX_RETENTION_DAYS}
          testId="input-unpublished-retention-days"
          onCommit={(n) => edit({ unpublished_retention_days: n })}
        />
      </Row>
      {backlog && (
        <div
          data-testid="retention-backlog"
          style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--dim)", padding: "10px 0" }}
        >
          {backlogText(backlog)}
        </div>
      )}
          <SaveBar tabKey="retention" count={dirtyFields("retention").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="api-keys">
      {/* ── API keys (TMDEV-73) ── */}
      <SectionLabel label="API Keys" />
      {([
        ["elevenlabs_api_key", "ElevenLabs", "Voice generation. Required to voice a video."],
        ["gemini_api_key", "Gemini", "Optional — topic mining and AI review. Without it, both are off."],
        ["openai_api_key", "OpenAI", "Required — scene images and the Illustrated style's characters. Without it, no scene image can be generated and Illustrated cannot be chosen."],
        ["youtube_transcript_api_key", "youtube-transcript.io", "Optional — fetches the transcripts a Script Profile is built from. Topic mining does not use it."],
        ["postforme_api_key", "postforme.dev", "Publishing to social platforms. The most powerful key here — it can post to every account connected to that postforme project."],
      ] as const).map(([key, label, note]) => (
        <Row
          key={key}
          label={label}
          note={`${note} ${val(key) ? "Stored — type to replace, or clear the field to remove it." : "Not set."}`}
        >
          <SecretInput
            value={val(key)}
            testId={`input-${key.replace(/_/g, "-")}`}
            onCommit={(v) => edit({ [key]: v } as Partial<Settings>)}
          />
        </Row>
      ))}
          <SaveBar tabKey="api-keys" count={dirtyFields("api-keys").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="publishing">
      {/* ── Publishing (TMDEV-83) ── */}
      <div data-testid="section-publishing">
        <SectionLabel label="Publishing" />
        <Row
          label="Publishing"
          note="Publish approved videos to YouTube, Instagram, TikTok and Facebook via postforme.dev. Every publish is something you click and confirm, unless a project is on Auto Pilot (its own tab), which posts unattended. Needs the postforme.dev key on the API Keys tab."
        >
          <button
            data-testid="toggle-publishing"
            onClick={() => edit({ publishing_enabled: !val("publishing_enabled") })}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.06em",
              padding: "7px 16px",
              border: `1px solid ${val("publishing_enabled") ? "var(--green)" : "var(--border)"}`,
              background: val("publishing_enabled") ? "rgba(74,222,128,0.1)" : "var(--panel)",
              color: val("publishing_enabled") ? "var(--green)" : "var(--mute)",
              cursor: "pointer",
              transition: "all .15s",
            }}
          >
            {val("publishing_enabled") ? "ON" : "OFF"}
          </button>
        </Row>
        <p style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--mute)", marginTop: 10 }}>
          Pick which connected accounts Tubematic may post to on the Socials page.
        </p>
      </div>
          <SaveBar tabKey="publishing" count={dirtyFields("publishing").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="notifications">
      {/* ── Notifications (TMDEV-5) ── */}
      <div data-testid="section-notifications">
        <SectionLabel label="Discord" />
        <Row
          label="Webhook URL"
          note={
            "Create one in the Discord channel's Integrations → Webhooks, then paste it here. " +
            (val("discord_webhook_url")
              ? "Stored — type to replace, or clear the field to turn notifications off."
              : "Not set — nothing is sent until this is filled in.") +
            " Saving checks the webhook still exists; it does not send a message."
          }
        >
          <SecretInput
            value={val("discord_webhook_url")}
            testId="input-discord-webhook-url"
            onCommit={(v) => edit({ discord_webhook_url: v })}
          />
        </Row>
        <Row
          label="Dashboard URL"
          note="Used to link back from a notification, e.g. http://192.168.1.20:3000. Leave blank for messages with no links — this container cannot know what address you reach it by."
        >
          <input
            data-testid="input-dashboard-base-url"
            type="text"
            value={val("dashboard_base_url")}
            placeholder="not set"
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => edit({ dashboard_base_url: e.target.value })}
            style={{ ...inputStyle, width: 220 }}
          />
        </Row>

        <SectionLabel label="Send a message when…" />
        {([
          ["notify_topic_proposed", "Topics are proposed",
           "One bundled message per research run, not one per topic."],
          ["notify_script_ready", "A script is ready",
           "The checkpoint before ElevenLabs charges for voicing."],
          ["notify_video_ready", "A video is ready",
           "A finished render waiting for your sign-off."],
        ] as const).map(([key, label, note]) => (
          <Row key={key} label={label} note={note}>
            <button
              data-testid={`toggle-${key.replace(/_/g, "-")}`}
              onClick={() => edit({ [key]: !val(key) } as Partial<Settings>)}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.06em",
                padding: "7px 16px",
                border: `1px solid ${val(key) ? "var(--green)" : "var(--border)"}`,
                background: val(key) ? "rgba(74,222,128,0.1)" : "var(--panel)",
                color: val(key) ? "var(--green)" : "var(--mute)",
                cursor: "pointer",
                transition: "all .15s",
              }}
            >
              {val(key) ? "ON" : "OFF"}
            </button>
          </Row>
        ))}
        <p style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--mute)", marginTop: 10 }}>
          Notifications are sent by the render worker, so they arrive within a
          minute or so of the event — or once the current render finishes.
        </p>
      </div>
          <SaveBar tabKey="notifications" count={dirtyFields("notifications").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="scheduling">
      {/* ── Section 6: Scheduling ── */}
      <SectionLabel label="Scheduling" />
      <Row label="Research runs used" note="Rolling 24h window — a slot frees 24h after each run, not at a fixed reset time.">
        <span data-testid="research-runs-used" style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink)" }}>
          {status ? `${status.research_runs_today} / ${status.max_research_runs_per_day}` : "—"}
        </span>
      </Row>
      <Row label="Next research slot frees">
        <span data-testid="research-window-resets" style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink)" }}>
          {!status
            ? "—"
            : !status.research_window_resets_at || status.research_runs_today < status.max_research_runs_per_day
              ? "slots available now"
              : formatDateTime(status.research_window_resets_at, timeZone)}
        </span>
      </Row>
      <Row label="Last research run">
        <span data-testid="last-research-at" style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink)" }}>
          {!status
            ? "—"
            : !status.last_research_at
              ? "never"
              : `${formatDateTime(status.last_research_at, timeZone)} (${formatRelative(status.last_research_at, Date.now())} ago)`}
        </span>
      </Row>
      <SectionLabel label="Agent sessions" />
      <Row
        label="Concurrent sessions"
        note="How many videos the scheduled agent works on at once, one session each. Research and script profiles run beside them, outside this limit. Each session is a paid agent run: set 1 on a tight budget."
      >
        <NumInput
          value={val("max_concurrent_agent_sessions")}
          min={1}
          max={MAX_CONCURRENT_AGENT_SESSIONS}
          testId="input-max-concurrent-agent-sessions"
          onCommit={(n) => edit({ max_concurrent_agent_sessions: n })}
        />
      </Row>
      <Row
        label="Session timeout"
        note="How long one agent session may run before it is stopped, retries included. Shown in minutes; stored as agent_session_timeout_secs."
      >
        <NumInput
          value={Math.round(val("agent_session_timeout_secs") / 60)}
          min={1}
          max={600}
          testId="input-agent-session-timeout-mins"
          onCommit={(mins) => edit({ agent_session_timeout_secs: mins * 60 })}
        />
      </Row>
          <SaveBar tabKey="scheduling" count={dirtyFields("scheduling").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="agents">
          <AgentsPanel inputStyle={inputStyle} />
        </TabsContent>

        <TabsContent value="preferences">
      {/* ── User preferences ── */}
      <SectionLabel label="Preferences" />
      <p style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--mute)", margin: "8px 0 10px", lineHeight: 1.6 }}>
        Your standing preferences for every video, sent to the agent on every run and labelled as
        yours. Write them for any stage (topics, scripts, voice, visuals); each run applies only the
        parts that fit what it is doing. They cannot override a human checkpoint.
      </p>
      <textarea
        data-testid="input-user-preferences"
        value={(val("user_preferences") ?? "")}
        rows={14}
        placeholder={"e.g.\nTopics: favour Linux internals; skip crypto.\nScripts: calm tone, no jokes, UK spelling.\nVisuals: prefer diagrams over stock-style photos."}
        spellCheck={false}
        onChange={(e) => {
          const chars = codePoints(e.target.value);
          edit({
            user_preferences: chars.length > MAX_USER_PREFERENCES_CHARS
              ? chars.slice(0, MAX_USER_PREFERENCES_CHARS).join("")
              : e.target.value,
          });
        }}
        style={{ ...inputStyle, width: "100%", boxSizing: "border-box", resize: "vertical", lineHeight: 1.5 }}
      />
      <div
        data-testid="user-preferences-count"
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10.5,
          textAlign: "right",
          marginTop: 4,
          color: codePoints(val("user_preferences") ?? "").length >= MAX_USER_PREFERENCES_CHARS * 0.9
            ? "var(--amber)" : "var(--mute)",
        }}
      >
        {codePoints(val("user_preferences") ?? "").length} / {MAX_USER_PREFERENCES_CHARS}
      </div>
          <SaveBar tabKey="preferences" count={dirtyFields("preferences").length} saving={saving} onSave={saveTab} />
        </TabsContent>

        <TabsContent value="costs">
          <CostsPanel inputStyle={inputStyle} />
        </TabsContent>

        <TabsContent value="auto-pilot">
          <AutoPilotPanel inputStyle={inputStyle} />
        </TabsContent>
      </Tabs>

      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--dim)",
          background: "var(--panel)",
          border: "1px solid var(--border)",
          padding: "12px 16px",
          letterSpacing: "0.02em",
          lineHeight: 1.7,
        }}
      >
        Poll interval is configured during onboarding. To change it, re-run:{" "}
        <code style={{ color: "var(--amber)", fontSize: 10 }}>python onboard.py --step cron</code>
        <br />
        All displayed timestamps use the host's timezone: <span data-testid="settings-tz" style={{ color: "var(--amber)" }}>{tzLabel}</span>.
      </div>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </>
  );
}

// ── Voices roster editor (TMDEV-51) ───────────────────────────────────────────

// What a model adds on top of the lexicon and <respell>, which every model takes.
function modelNote(model: string): string {
  if (IPA_COMPATIBLE_MODELS.includes(model)) return "Supports exact IPA via <ipa> tags.";
  if (PHONEME_COMPATIBLE_MODELS.includes(model)) return "Supports exact <phoneme> tags.";
  return "Pronunciation via the lexicon and <respell> tags only.";
}

function VoiceRow({
  index,
  voice,
  isDefault,
  onCommit,
  onSetDefault,
  onRemove,
  inputStyle,
}: {
  index: number;
  voice: Voice;
  isDefault: boolean;
  onCommit: (patch: Partial<Voice>) => void;
  onSetDefault: () => void;
  onRemove: () => void;
  inputStyle: React.CSSProperties;
}) {
  const [name, setName] = useState(voice.name);
  const [voiceId, setVoiceId] = useState(voice.voice_id);

  useEffect(() => { setName(voice.name); }, [voice.name]);
  useEffect(() => { setVoiceId(voice.voice_id); }, [voice.voice_id]);

  return (
    <div data-testid={`voice-row-${index}`} style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <input
        data-testid={`voice-name-${index}`}
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={() => {
          if (name.trim() && name !== voice.name) onCommit({ name: name.trim() });
          else setName(voice.name);
        }}
        style={{ ...inputStyle, width: 140 }}
      />
      <input
        data-testid={`voice-id-${index}`}
        type="text"
        value={voiceId}
        placeholder="voice id"
        onChange={(e) => setVoiceId(e.target.value)}
        onBlur={() => {
          if (voiceId.trim() && voiceId !== voice.voice_id) onCommit({ voice_id: voiceId.trim() });
          else setVoiceId(voice.voice_id);
        }}
        style={{ ...inputStyle, width: 180 }}
      />
      <select
        data-testid={`voice-model-${index}`}
        value={voice.model_id}
        onChange={(e) => onCommit({ model_id: e.target.value })}
        title={modelNote(voice.model_id)}
        style={{ ...inputStyle, width: 190 }}
      >
        {DICTIONARY_COMPATIBLE_MODELS.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>
      <label
        data-testid={`voice-default-${index}`}
        style={{ display: "flex", alignItems: "center", gap: 4, fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-2)", cursor: "pointer" }}
      >
        <input type="radio" checked={isDefault} onChange={onSetDefault} />
        default
      </label>
      <VoicePreviewButton voiceId={voice.voice_id} modelId={voice.model_id} />
      <button
        data-testid={`voice-remove-${index}`}
        onClick={onRemove}
        style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--mute)", background: "transparent", border: "1px solid var(--border)", padding: "4px 10px", cursor: "pointer" }}
      >
        Remove
      </button>
    </div>
  );
}

function VoicesEditor({
  voices,
  defaultVoiceId,
  onSave,
  saving,
  inputStyle,
}: {
  voices: Voice[];
  defaultVoiceId: string;
  onSave: (voices: Voice[], defaultVoiceId: string) => void;
  saving: boolean;
  inputStyle: React.CSSProperties;
}) {
  const [newName, setNewName] = useState("");
  const [newId, setNewId] = useState("");
  const [newModel, setNewModel] = useState(DICTIONARY_COMPATIBLE_MODELS[0]);

  function commitRow(index: number, patch: Partial<Voice>) {
    onSave(voices.map((v, i) => (i === index ? { ...v, ...patch } : v)), defaultVoiceId);
  }

  function removeRow(index: number) {
    const removedId = voices[index].voice_id;
    onSave(
      voices.filter((_, i) => i !== index),
      defaultVoiceId === removedId ? "" : defaultVoiceId,
    );
  }

  function addVoice() {
    if (!newName.trim() || !newId.trim() || voices.length >= MAX_VOICES) return;
    onSave([...voices, { name: newName.trim(), voice_id: newId.trim(), model_id: newModel }],
           defaultVoiceId);
    setNewName("");
    setNewId("");
  }

  return (
    <div data-testid="voices-editor" style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 10 }}>
      {voices.map((v, i) => (
        <VoiceRow
          key={i}
          index={i}
          voice={v}
          isDefault={v.voice_id === defaultVoiceId}
          onCommit={(patch) => commitRow(i, patch)}
          onSetDefault={() => onSave(voices, v.voice_id)}
          onRemove={() => removeRow(i)}
          inputStyle={inputStyle}
        />
      ))}
      {voices.length < MAX_VOICES ? (
        <div data-testid="voice-add-row" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            data-testid="voice-add-name"
            type="text"
            placeholder="name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ ...inputStyle, width: 140 }}
          />
          <input
            data-testid="voice-add-id"
            type="text"
            placeholder="voice id"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            style={{ ...inputStyle, width: 180 }}
          />
          <select
            data-testid="voice-add-model"
            value={newModel}
            onChange={(e) => setNewModel(e.target.value)}
            title={modelNote(newModel)}
            style={{ ...inputStyle, width: 190 }}
          >
            {DICTIONARY_COMPATIBLE_MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button
            data-testid="voice-add"
            onClick={addVoice}
            disabled={saving || !newName.trim() || !newId.trim()}
            style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--green)", background: "rgba(101,210,122,0.06)", border: "1px solid rgba(101,210,122,0.32)", padding: "4px 12px", cursor: "pointer" }}
          >
            Add
          </button>
        </div>
      ) : (
        <div data-testid="voice-cap-note" style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)" }}>
          Maximum of {MAX_VOICES} voices reached.
        </div>
      )}
    </div>
  );
}

// ── Agents ────────────────────────────────────────────────────────────────────
// Rows are written only by the host-side installer, which validates each
// agent's model list against the real binary. This container has no agent
// binary, so the model list is read-only here, and installing or uninstalling
// an agent is host-side too. Only the default agent, the weight and which of
// the agent's models is its default are editable, each saved immediately on its
// own endpoint rather than through the tab Save machinery above.

// Keep in sync with the weight bounds PATCH /agents enforces (renderer/api/).
const MAX_AGENT_WEIGHT = 100;
//  More than one agent is installable, so these name none of them: a command
//  that said `claude` would be the wrong instruction on an install running
//  Codex or OpenCode, and following it would not touch that install at all.
const INSTALL_AGENT_CMD = "python onboard.py --install-agent <agent>";
const UNINSTALL_AGENT_CMD = "python onboard.py --uninstall-agent <agent>";

async function errorDetail(r: Response): Promise<string> {
  try {
    const body = await r.json();
    if (body?.error) return body.error;
  } catch { /* non-JSON error body — the status is all we have */ }
  return `HTTP ${r.status}`;
}

function AgentWeight({
  agent,
  disabled,
  inputStyle,
  onSave,
}: {
  agent: Agent;
  disabled: boolean;
  inputStyle: React.CSSProperties;
  onSave: (n: number) => void;
}) {
  const [local, setLocal] = useState(String(agent.weight));
  useEffect(() => { setLocal(String(agent.weight)); }, [agent.weight]);
  const n = Number(local);
  const valid = /^\d+$/.test(local.trim()) && n <= MAX_AGENT_WEIGHT;
  const changed = valid && n !== agent.weight;
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-2)" }}>weight</span>
      <input
        data-testid={`agent-weight-${agent.id}`}
        type="number"
        min={0}
        max={MAX_AGENT_WEIGHT}
        value={local}
        disabled={disabled}
        onChange={(e) => setLocal(e.target.value)}
        style={{ ...inputStyle, width: 70 }}
      />
      <button
        data-testid={`agent-weight-save-${agent.id}`}
        disabled={disabled || !changed}
        onClick={() => onSave(n)}
        style={{
          fontFamily: "var(--mono)", fontSize: 11, padding: "4px 10px",
          color: changed && !disabled ? "var(--amber)" : "var(--mute)",
          background: "transparent",
          border: `1px solid ${changed && !disabled ? "var(--amber)" : "var(--border)"}`,
          cursor: changed && !disabled ? "pointer" : "not-allowed",
        }}
      >
        Save
      </button>
    </span>
  );
}

function AgentsPanel({ inputStyle }: { inputStyle: React.CSSProperties }) {
  const { timeZone } = useTimeZone();
  // null until the first load resolves, so the empty state never flashes up
  // before the list arrives.
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const r = await apiFetch("/agents");
      if (!r.ok) { setLoadError(await errorDetail(r)); setAgents([]); return; }
      const data = await r.json();
      setAgents(Array.isArray(data) ? data : []);
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "unreachable");
      setAgents([]);
    }
  }

  useEffect(() => { load(); }, []);

  async function mutate(id: string, init: RequestInit) {
    setBusy(id);
    setErrors((e) => ({ ...e, [id]: "" }));
    try {
      const r = await apiFetch(`/agents/${id}`, init);
      if (!r.ok) {
        const detail = await errorDetail(r);
        setErrors((e) => ({ ...e, [id]: detail }));
        return;
      }
      // Reload rather than splice in the returned row: making one agent the
      // default clears is_default on whichever agent held it before.
      await load();
    } catch (e) {
      setErrors((prev) => ({ ...prev, [id]: e instanceof Error ? e.message : "unreachable" }));
    } finally {
      setBusy(null);
    }
  }

  function patch(
    id: string,
    body: { is_default: true } | { weight: number } | { default_model: string }
      | { effort: string },
  ) {
    return mutate(id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  const mono = { fontFamily: "var(--mono)" } as const;
  const note = { ...mono, fontSize: 10, color: "var(--mute)", letterSpacing: "0.02em", marginBottom: 6 } as const;

  return (
    <div data-testid="section-agents">
      <SectionLabel label="Agents" />
      <div data-testid="agents-weight-hint" style={note}>
        Weights are exact shares: new videos are dealt from a shuffled deck, so weights 3 and 1
        mean exactly 3 and 1 of every 4 new videos, in random order. A weight of 0 gets none.
      </div>
      <div data-testid="agents-models-note" style={note}>
        Models are added or removed by re-running{" "}
        <code style={{ color: "var(--amber)" }}>{INSTALL_AGENT_CMD}</code>{" "}
        on the host; the default model and the effort level can be picked here.
      </div>
      <div data-testid="agents-effort-hint" style={note}>
        Effort is how hard an agent thinks on each run. A video can override it at the topic
        checkpoint; everything else uses the level set here.
      </div>
      <div data-testid="agents-uninstall-note" style={{ ...note, marginBottom: 12 }}>
        An agent is uninstalled on the host with{" "}
        <code style={{ color: "var(--amber)" }}>{UNINSTALL_AGENT_CMD}</code>.
      </div>

      {loadError && (
        <div data-testid="agents-error" style={{ ...mono, fontSize: 11, color: "var(--red)", marginBottom: 10 }}>
          Could not load agents — {loadError}
        </div>
      )}

      {agents === null ? (
        <div style={{ ...mono, fontSize: 11, color: "var(--mute)" }}>Loading…</div>
      ) : agents.length === 0 && !loadError ? (
        <div data-testid="agents-empty" style={{ ...mono, fontSize: 12, color: "var(--ink-2)", padding: "12px 0" }}>
          No agent installed. Run{" "}
          <code style={{ color: "var(--amber)" }}>{INSTALL_AGENT_CMD}</code>{" "}
          on the host.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {agents.map((a) => {
            const archived = !!a.archived_at;
            const disabled = archived || busy !== null;
            return (
              <div
                key={a.id}
                data-testid={`agent-row-${a.id}`}
                style={{ border: "1px solid var(--border)", padding: "12px 14px", opacity: archived ? 0.6 : 1 }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ ...mono, fontSize: 13, fontWeight: 700, color: "var(--ink)" }}>{a.name}</span>
                  <span style={{ ...mono, fontSize: 10, color: "var(--dim)" }}>{a.id}</span>
                  {archived && (
                    <span
                      data-testid={`agent-archived-${a.id}`}
                      style={{
                        ...mono, fontSize: 9, letterSpacing: "0.12em", padding: "2px 6px",
                        border: "1px solid var(--dim)", color: "var(--dim)", textTransform: "uppercase",
                      }}
                    >
                      uninstalled
                    </span>
                  )}
                </div>

                <div style={{ ...mono, fontSize: 10.5, color: "var(--dim)", marginTop: 6, lineHeight: 1.7 }}>
                  <div>binary: <span style={{ color: "var(--ink-2)" }}>{a.binary}</span></div>
                  <div>workspace: <span style={{ color: "var(--ink-2)" }}>{a.run_path}</span></div>
                  <div>install scope: <span style={{ color: "var(--ink-2)" }}>{a.install_scope}</span></div>
                  <div>verified: <span style={{ color: "var(--ink-2)" }}>{a.verified_at ? formatDate(a.verified_at, timeZone) : "—"}</span></div>
                </div>

                <div data-testid={`agent-models-${a.id}`} style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {a.models.map((m, i) => (
                    <span
                      key={m}
                      style={{
                        ...mono, fontSize: 10.5, padding: "2px 8px",
                        border: `1px solid ${i === 0 ? "var(--green)" : "var(--border-2)"}`,
                        color: i === 0 ? "var(--green)" : "var(--ink-2)",
                      }}
                    >
                      {m}
                      {i === 0 && <span data-testid={`agent-model-default-${a.id}`}> · default</span>}
                    </span>
                  ))}
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
                  <label
                    data-testid={`agent-default-${a.id}`}
                    style={{ display: "flex", alignItems: "center", gap: 4, ...mono, fontSize: 11, color: "var(--ink-2)", cursor: disabled ? "not-allowed" : "pointer" }}
                  >
                    <input
                      type="radio"
                      name="default-agent"
                      checked={a.is_default}
                      disabled={disabled}
                      onChange={() => patch(a.id, { is_default: true })}
                    />
                    Default agent
                  </label>
                  <AgentWeight
                    agent={a}
                    disabled={disabled}
                    inputStyle={inputStyle}
                    onSave={(n) => patch(a.id, { weight: n })}
                  />
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ ...mono, fontSize: 11, color: "var(--ink-2)" }}>default model</span>
                    {/* Controlled by models[0]: the API moves the pick to the
                        front, and the reload that follows re-renders from it. */}
                    <select
                      data-testid={`agent-default-model-${a.id}`}
                      value={a.models[0] ?? ""}
                      disabled={disabled || a.models.length === 0}
                      onChange={(e) => patch(a.id, { default_model: e.target.value })}
                      style={{ ...inputStyle, width: "auto" }}
                    >
                      {a.models.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ ...mono, fontSize: 11, color: "var(--ink-2)" }}>effort</span>
                    {/* Not gated on a.models like the picker above: the levels
                        come from the CLI, not from what this install probed,
                        so an agent with no usable model list still has one. */}
                    <select
                      data-testid={`agent-effort-${a.id}`}
                      value={a.effort}
                      disabled={disabled}
                      onChange={(e) => patch(a.id, { effort: e.target.value })}
                      style={{ ...inputStyle, width: "auto" }}
                    >
                      {AGENT_EFFORTS.map((e) => <option key={e} value={e}>{e}</option>)}
                    </select>
                  </span>
                </div>

                {errors[a.id] && (
                  <div data-testid={`agent-error-${a.id}`} style={{ ...mono, fontSize: 10.5, color: "var(--red)", marginTop: 8 }}>
                    {errors[a.id]}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
