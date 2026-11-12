"use client";

import { useEffect, useRef, useState } from "react";
import type { Agent, GpuStatus, Mascot, Settings, PipelineStatus, RetentionBacklog, Voice } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { AutoPilotPanel } from "@/components/AutoPilotPanel";
import { RenderersPanel } from "@/components/RenderersPanel";
import { CostsPanel } from "@/components/CostsPanel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToastStack, useToasts } from "@/components/Toast";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SaveStatus, SavesSummaryLine } from "@/components/SaveStatus";
import {
  responseError, SavesProvider, useSaveStatus, useSerialQueue, type SaveState,
} from "@/lib/saveStatus";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { VoicePreviewButton } from "@/components/VoicePreviewButton";
import { formatDate, formatDateTime, formatRelative } from "@/lib/datetime";
import { AGENT_EFFORTS } from "@/lib/agents";
import { mascotGate, mascotGateNote, mascotOptions } from "@/lib/mascots";
import { codePoints } from "@/lib/utils";
import { formatBytes } from "@/lib/format";

const STATUS_POLL_MS = 30_000;
// Longer than the Discord webhook check a save can include (5 s).
const SAVE_TIMEOUT_MS = 30_000;

// Max named voices in the roster (TMDEV-51). Keep in sync with
// renderer/api/pipeline.py, mcp/server.py and onboard/config.py.
const MAX_VOICES = 10;

// The model sets below are copies of tubematic_core/voice_models.py, pinned by
// renderer/api/tests/test_pipeline.py's cross-copy test. Each roster voice
// carries its own model (TMDEV-121); these only drive the per-voice picker
// and its pronunciation notes.
// eleven_v3 and eleven_v4 are deliberately absent (TMDEV-26) — they apply no
// text normalization, so phoneme tags break the caption timeline.
// eleven_english_v1 was removed (TMDEV-122): ElevenLabs no longer has it.
const PHONEME_COMPATIBLE_MODELS = ["eleven_turbo_v2", "eleven_flash_v2"];

// Models that take inline IPA through <ipa> tags (TMDEV-123, TMDEV-172).
const IPA_COMPATIBLE_MODELS = ["eleven_v3", "eleven_v4"];

// The current (non-deprecated) ElevenLabs model catalog — every model here
// is always usable, since pronunciation (the lexicon + inline <respell>
// tags) is plain text substitution with no model restriction. Models in
// PHONEME_COMPATIBLE_MODELS additionally support exact <phoneme> tags.
// eleven_multilingual_v2 first/default, per onboard.py DEFAULT_DICTIONARY_MODEL.
const DICTIONARY_COMPATIBLE_MODELS = [
  "eleven_multilingual_v2",
  "eleven_v3",
  "eleven_v4",
  "eleven_flash_v2_5",
  "eleven_turbo_v2_5",
  "eleven_flash_v2",
  "eleven_turbo_v2",
];

// Models that honour a voice's speed (TMDEV-216, probed): eleven_v3 and
// eleven_v4 ignore it, so the API refuses a speed there and the picker is
// disabled. Keep in sync with tubematic_core/voice_models.py SPEED_MODELS.
const SPEED_MODELS = [
  "eleven_multilingual_v2",
  "eleven_flash_v2_5",
  "eleven_turbo_v2_5",
  "eleven_flash_v2",
  "eleven_turbo_v2",
];

// 0.70 to 1.20 in steps of 0.05: ElevenLabs' range, on the step the API takes.
const SPEED_OPTIONS = Array.from({ length: 11 }, (_, i) => Math.round((0.7 + i * 0.05) * 100) / 100);

// A roster entry as the API stores it: no speed at 1.0, and none on a model
// that ignores it.
function withSpeed(voice: Voice): Voice {
  const { speed, ...rest } = voice;
  return speed !== undefined && speed !== 1 && SPEED_MODELS.includes(voice.model_id)
    ? { ...rest, speed } : rest;
}

function SpeedSelect({ testId, model, speed, onChange, inputStyle }: {
  testId: string;
  model: string;
  speed: number;
  onChange: (speed: number) => void;
  inputStyle: React.CSSProperties;
}) {
  const allowed = SPEED_MODELS.includes(model);
  return (
    <select
      data-testid={testId}
      aria-label="Speed"
      value={allowed ? speed.toFixed(2) : "1.00"}
      disabled={!allowed}
      onChange={(e) => onChange(Number(e.target.value))}
      title={allowed ? "How fast this voice speaks. 1.00 is ElevenLabs' normal pace."
                     : `${model} ignores speed, so it stays at 1.00.`}
      style={{ ...inputStyle, width: 82 }}
    >
      {SPEED_OPTIONS.map((v) => (
        <option key={v} value={v.toFixed(2)}>{v.toFixed(2)}x</option>
      ))}
    </select>
  );
}

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
// Keeps what was typed when it is out of range or the API refuses it, so it can
// be corrected; the stored value stays in force meanwhile.

function fieldBorder(status: SaveState | undefined): string {
  return status?.state === "error" ? "var(--red)" : "var(--border)";
}

/** What a field compares an edit with: the value on its way to the API, or
 *  else the stored one. Comparing with the stored value alone would drop an
 *  edit back to it made while another save was on its way, and would send an
 *  Enter followed by a blur twice. */
function useBaseline<T>(value: T, status?: SaveState) {
  const sent = useRef<{ v: T } | null>(null);
  // In flight until the stored value is the one sent last, or the field's
  // saves are over (saved, refused). An answer to an older save in between
  // changes nothing here.
  useEffect(() => { if (sent.current && Object.is(sent.current.v, value)) sent.current = null; }, [value]);
  useEffect(() => { if (status?.state !== "saving") sent.current = null; }, [status?.state]);
  return {
    current: () => (sent.current ? sent.current.v : value),
    mark: (v: T) => { sent.current = { v }; },
    inFlight: () => sent.current !== null,
  };
}

/** Commits a text field. Typed back to the stored value: nothing to send, and
 *  a refusal shown for it no longer applies. A value whose refusal is on
 *  screen is not sent again by a mere focus and blur (for the Discord webhook
 *  that would run its check again each time); Enter or an edit sends it. */
function commitText(
  v: string,
  baseline: { current: () => string; mark: (v: string) => void },
  lastSent: { current: string | null },
  status: SaveState | undefined,
  onCommit: (v: string) => void,
  onSame?: () => void,
  force = false,
) {
  if (v === baseline.current()) {
    onSame?.();
    return;
  }
  // Enter always sends: a value that failed because the API could not be
  // reached has to be sendable again without retyping it.
  if (!force && status?.state === "error" && v === lastSent.current) return;
  baseline.mark(v);
  lastSent.current = v;
  onCommit(v);
}

/** Whether a field may show the stored value now: not while you have typed
 *  something not yet committed, not while a save of it is on its way (an
 *  older answer would put an older value in the box), and not while a refusal
 *  is shown (what you typed stays, to be corrected). */
function mayFollow(dirty: boolean, inFlight: boolean, status?: SaveState): boolean {
  return !dirty && !inFlight && status?.state !== "error";
}

function NumInput({
  value,
  min,
  max,
  testId,
  status,
  onCommit,
  onInvalid,
  onSame,
}: {
  value: number;
  min: number;
  max: number;
  testId: string;
  status?: SaveState;
  onCommit: (n: number) => void;
  onInvalid?: (message: string) => void;
  onSame?: () => void;
}) {
  const [local, setLocal] = useState(String(value));
  const baseline = useBaseline(value, status);
  const dirty = useRef(false);

  useEffect(() => {
    if (mayFollow(dirty.current, baseline.inFlight(), status)) setLocal(String(value));
  }, [value, status?.state]);

  function commit() {
    const text = local.trim();
    const n = Number(text);
    if (!/^-?\d+$/.test(text) || n < min || n > max) {
      if (onInvalid) onInvalid(`must be a whole number from ${min} to ${max}`);
      else setLocal(String(value)); // revert invalid
      return;
    }
    dirty.current = false;
    if (n === baseline.current()) {
      onSame?.();
      return;
    }
    baseline.mark(n);
    onCommit(n);
  }

  return (
    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <SaveStatus status={status} testId={`status-${testId}`} id={`status-${testId}`} />
      <input
        data-testid={testId}
        type="number"
        min={min}
        max={max}
        value={local}
        aria-invalid={status?.state === "error"}
        aria-describedby={`status-${testId}`}
        onChange={(e) => { dirty.current = true; setLocal(e.target.value); }}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
        style={{
          width: 80,
          background: "var(--input-bg, var(--panel))",
          border: `1px solid ${fieldBorder(status)}`,
          color: "var(--ink)",
          fontFamily: "var(--mono)",
          fontSize: 12,
          padding: "6px 10px",
          outline: "none",
        }}
      />
    </span>
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
  status,
  onCommit,
  onSame,
}: {
  value: string;
  testId: string;
  status?: SaveState;
  onCommit: (v: string) => void;
  onSame?: () => void;
}) {
  const [local, setLocal] = useState(value);
  const [focused, setFocused] = useState(false);
  const baseline = useBaseline(value, status);
  const dirty = useRef(false);
  const lastSent = useRef<string | null>(null);

  useEffect(() => {
    if (mayFollow(dirty.current, baseline.inFlight(), status)) setLocal(value);
  }, [value, status?.state]);

  function commit(force = false) {
    setFocused(false);
    dirty.current = false;
    commitText(local.trim(), baseline, lastSent, status, onCommit, onSame, force);
  }

  return (
    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <SaveStatus status={status} testId={`status-${testId}`} id={`status-${testId}`} />
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
        aria-invalid={status?.state === "error"}
        aria-describedby={`status-${testId}`}
        onFocus={() => setFocused(true)}
        onChange={(e) => { dirty.current = true; lastSent.current = null; setLocal(e.target.value); }}
        onBlur={() => commit()}
        onKeyDown={(e) => { if (e.key === "Enter") { commit(true); (e.target as HTMLInputElement).blur(); } }}
        style={{
          width: 220,
          background: "var(--input-bg, var(--panel))",
          border: `1px solid ${fieldBorder(status)}`,
          color: "var(--ink)",
          fontFamily: "var(--mono)",
          fontSize: 12,
          padding: "6px 10px",
          outline: "none",
        }}
      />
    </span>
  );
}

// ── Plain text input with save on blur/Enter ──────────────────────────────────

function TextInput({
  value,
  testId,
  status,
  onCommit,
  onSame,
}: {
  value: string;
  testId: string;
  status?: SaveState;
  onCommit: (v: string) => void;
  onSame?: () => void;
}) {
  const [local, setLocal] = useState(value);
  const baseline = useBaseline(value, status);
  const dirty = useRef(false);
  const lastSent = useRef<string | null>(null);

  useEffect(() => {
    if (mayFollow(dirty.current, baseline.inFlight(), status)) setLocal(value);
  }, [value, status?.state]);

  function commit(force = false) {
    dirty.current = false;
    commitText(local.trim(), baseline, lastSent, status, onCommit, onSame, force);
  }

  return (
    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <SaveStatus status={status} testId={`status-${testId}`} id={`status-${testId}`} />
      <input
        data-testid={testId}
        type="text"
        value={local}
        placeholder="not set"
        autoComplete="off"
        spellCheck={false}
        aria-invalid={status?.state === "error"}
        aria-describedby={`status-${testId}`}
        onChange={(e) => { dirty.current = true; lastSent.current = null; setLocal(e.target.value); }}
        onBlur={() => commit()}
        onKeyDown={(e) => { if (e.key === "Enter") { commit(true); (e.target as HTMLInputElement).blur(); } }}
        style={{
          width: 220,
          background: "var(--input-bg, var(--panel))",
          border: `1px solid ${fieldBorder(status)}`,
          color: "var(--ink)",
          fontFamily: "var(--mono)",
          fontSize: 12,
          padding: "6px 10px",
          outline: "none",
        }}
      />
    </span>
  );
}

// ── Preferences text: saves a second after typing stops, and on blur ──────────

const PREFERENCES_SAVE_DELAY_MS = 1000;

function PreferencesEditor({
  value,
  status,
  inputStyle,
  onWaiting,
  onSame,
  onSave,
}: {
  value: string;
  status?: SaveState;
  inputStyle: React.CSSProperties;
  onWaiting: () => void;
  onSame: () => void;
  onSave: (text: string) => void;
}) {
  const [local, setLocal] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Text typed since the last save was sent. While there is some, the answer
  // to an earlier save must not replace what is in the box.
  const unsent = useRef(false);
  const latest = useRef(value);
  const save = useRef(onSave);
  save.current = onSave;
  const baseline = useBaseline(value, status);

  // The API stores the text trimmed. An answer that is only the box's text
  // trimmed leaves the box alone, or a trailing space or line break you just
  // typed would vanish under the cursor.
  useEffect(() => {
    if (!unsent.current && !baseline.inFlight() && status?.state !== "error"
        && value !== latest.current.trim()) {
      setLocal(value);
      latest.current = value;
    }
  }, [value, status?.state]);

  // An earlier save answering while newer text waits for its second must not
  // read as all saved: the field goes back to waiting (and the page keeps its
  // leave-page prompt). A refusal still shows as it is.
  useEffect(() => {
    if (status?.state === "saved" && unsent.current) onWaiting();
  }, [status?.state]);

  function flush() {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (!unsent.current) return;
    unsent.current = false;
    baseline.mark(latest.current);
    save.current(latest.current);
  }

  // Leaving the tab or the page sends what is still waiting.
  useEffect(() => () => flush(), []);

  return (
    <>
      <textarea
        data-testid="input-user-preferences"
        value={local}
        rows={14}
        placeholder={"e.g.\nTopics: favour Linux internals; skip crypto.\nScripts: calm tone, no jokes, UK spelling.\nVisuals: prefer diagrams over stock-style photos."}
        spellCheck={false}
        aria-invalid={status?.state === "error"}
        aria-describedby="status-input-user-preferences"
        onChange={(e) => {
          const chars = codePoints(e.target.value);
          const next = chars.length > MAX_USER_PREFERENCES_CHARS
            ? chars.slice(0, MAX_USER_PREFERENCES_CHARS).join("")
            : e.target.value;
          setLocal(next);
          latest.current = next;
          unsent.current = next !== baseline.current();
          if (timer.current) clearTimeout(timer.current);
          timer.current = null;
          if (unsent.current) {
            onWaiting();
            timer.current = setTimeout(flush, PREFERENCES_SAVE_DELAY_MS);
          } else if (!baseline.inFlight()) {
            // Typed back to what is stored: nothing left to send. With a save
            // still on its way, its outcome is what shows.
            onSame();
          }
        }}
        onBlur={flush}
        style={{
          ...inputStyle, width: "100%", boxSizing: "border-box", resize: "vertical", lineHeight: 1.5,
          border: `1px solid ${fieldBorder(status)}`,
        }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 4 }}>
        <SaveStatus status={status} testId="status-input-user-preferences" id="status-input-user-preferences" />
        <div
          data-testid="user-preferences-count"
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10.5,
            color: codePoints(local).length >= MAX_USER_PREFERENCES_CHARS * 0.9
              ? "var(--amber)" : "var(--mute)",
          }}
        >
          {codePoints(local).length} / {MAX_USER_PREFERENCES_CHARS}
        </div>
      </div>
    </>
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

function backlogText(b: RetentionBacklog): string {
  if (b.failed.count + b.rejected.count === 0) return "No failed or rejected videos to sweep.";
  return `${b.failed.count} failed and ${b.rejected.count} rejected videos are holding `
    + `${formatBytes(b.failed.bytes + b.rejected.bytes)}.`;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
// One entry per settings group. Every change on every tab is saved the moment
// it is made (TMDEV-218), so a tab carries no list of fields and nothing is
// ever left unsaved when you switch tabs.
//
// Pipeline Control is deliberately absent — pause/resume is an operational
// action against a different endpoint, and burying it behind a tab would make
// stopping the scheduler a two-click operation. It stays pinned above the tabs.

const TABS = [
  { key: "ai-review", label: "AI Review" },
  { key: "research", label: "Research" },
  { key: "voice", label: "Voice" },
  { key: "images", label: "Images" },
  { key: "rendering", label: "Rendering" },
  { key: "logs", label: "Logs" },
  { key: "retention", label: "Retention" },
  { key: "api-keys", label: "API Keys" },
  { key: "publishing", label: "Publishing" },
  { key: "notifications", label: "Notifications" },
  // The research readouts are read-only; the two agent-session fields
  // (TMDEV-129) are the only settings here.
  { key: "scheduling", label: "Scheduling" },
  // Agents live in their own table and save through /agents.
  { key: "agents", label: "Agents" },
  { key: "preferences", label: "Preferences" },
  // Model prices live in their own table and save through /prices.
  { key: "costs", label: "Costs" },
  // Auto Pilot saves its whole configuration through /autopilot as one
  // document.
  { key: "auto-pilot", label: "Auto Pilot" },
] as const satisfies ReadonlyArray<{ key: string; label: string }>;

type TabKey = (typeof TABS)[number]["key"];

// ── Page ──────────────────────────────────────────────────────────────────────

// The page-wide save status lives in a provider, so the page body sits one
// level down: everything that saves reports to it from below.
export default function SettingsPage() {
  return (
    <SavesProvider>
      <SettingsBody />
    </SavesProvider>
  );
}

function SettingsBody() {
  const { timeZone, label: tzLabel } = useTimeZone();
  const [s, setS] = useState<Settings | null>(null);
  const [backlog, setBacklog] = useState<RetentionBacklog | null>(null);
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  // Switches and pickers show their new value while it is on its way; a
  // refused change drops out of here and the stored value shows again.
  const [optimistic, setOptimistic] = useState<Partial<Settings>>({});
  const [confirmPublishing, setConfirmPublishing] = useState(false);
  // Whether Auto Pilot is on, read when the Publishing confirmation opens;
  // null until then, or if the read fails (the loaded settings then decide).
  const [autoPilotOn, setAutoPilotOn] = useState<boolean | null>(null);
  const statuses = useSaveStatus();
  const enqueue = useSerialQueue();
  const [tab, setTab] = useState<TabKey>(TABS[0].key);
  const { toasts, push, dismiss } = useToasts();
  const [mascots, setMascots] = useState<Mascot[]>([]);
  const [gpu, setGpu] = useState<GpuStatus | null>(null);

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
    // /settings?tab=rendering lands on that tab (the Mascots page links here).
    const wanted = new URLSearchParams(window.location.search).get("tab");
    const found = TABS.find((t) => t.key === wanted);
    if (found) setTab(found.key);
    // Best effort; the picker only needs the pickable ones.
    apiFetch("/mascots").then((r) => r.json())
      .then((rows) => setMascots(Array.isArray(rows) ? rows : []))
      .catch(() => {});
    apiFetch("/render/gpu").then((r) => (r.ok ? r.json() : null))
      .then((g) => setGpu(g && typeof g.status === "string" ? (g as GpuStatus) : null))
      .catch(() => {});
    const id = setInterval(loadStatus, STATUS_POLL_MS);
    return () => clearInterval(id);
  }, []);

  /** The value to render: one on its way to the API, else the stored value.
   *  `in` rather than a truthiness check — false and "" are real values. */
  function val<K extends keyof Settings>(key: K): Settings[K] {
    return (key in optimistic ? optimistic[key] : s![key]) as Settings[K];
  }

  /** Saves one change and shows its outcome beside the field named by
   *  `statusKey`. Every save goes through one queue: POST /settings answers
   *  with the whole settings object, so an answer that arrived after a newer
   *  one would put the older values back on screen. */
  function save(
    partial: Partial<Settings>,
    statusKey: string,
    opts: { optimistic?: boolean; label?: string } = {},
  ): Promise<boolean> {
    const keys = Object.keys(partial) as (keyof Settings)[];
    if (opts.optimistic) setOptimistic((o) => ({ ...o, ...partial }));
    // Only this save's own value leaves: a newer change to the same key, made
    // while this one was on its way, stays on screen.
    const settle = () => setOptimistic((o) => {
      const next = { ...o };
      keys.forEach((k) => { if (next[k] === partial[k]) delete next[k]; });
      return next;
    });
    return statuses.run(statusKey, () => enqueue(async () => {
      // A hung request would hold every later change behind it in the queue.
      const r = await apiFetch("/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(partial),
        signal: AbortSignal.timeout(SAVE_TIMEOUT_MS),
      }).catch(() => null);
      if (!r?.ok) {
        settle();
        return responseError(r);
      }
      const body = await r.json().catch(() => null);
      if (body && typeof body === "object" && !Array.isArray(body)) setS(body as Settings);
      settle();
      loadStatus();
      return null;
    }), opts.label);
  }

  // The newest `val`, for an Undo clicked after later changes.
  const valRef = useRef(val);
  valRef.current = val;

  /** Props for a NumInput bound to one settings key. */
  function numField<K extends keyof Settings>(
    key: K,
    toStored: (n: number) => Settings[K] = (n) => n as Settings[K],
  ) {
    return {
      status: statuses.get(key),
      onCommit: (n: number) => { void save({ [key]: toStored(n) } as Partial<Settings>, key); },
      onInvalid: (message: string) => statuses.fail(key, message),
      // Typed back to what is stored: a refusal no longer applies. A save
      // still on its way keeps its status.
      onSame: () => clearError(key),
    };
  }

  function clearError(key: string) {
    if (statuses.get(key)?.state === "error") statuses.clear(key);
  }

  /** A switch or picker: saved on change, shown at once, snapped back if refused. */
  function choose<K extends keyof Settings>(key: K, value: Settings[K]) {
    void save({ [key]: value } as Partial<Settings>, key, { optimistic: true });
  }

  function togglePublishing() {
    // Turning publishing on lets approved videos be posted (and, with Auto
    // Pilot on, scheduled unattended), so it is confirmed first. Off saves at once.
    if (val("publishing_enabled")) {
      choose("publishing_enabled", false);
      return;
    }
    setConfirmPublishing(true);
    // Auto Pilot saves through its own route, so the settings loaded with the
    // page can be out of date about it; the dialog's warning reads it fresh.
    setAutoPilotOn(null);
    apiFetch("/autopilot")
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => setAutoPilotOn(b && typeof b.enabled === "boolean" ? b.enabled : null))
      .catch(() => {});
  }

  function saveVoices(voices: Voice[], defaultVoiceId: string, removed?: RemovedVoice): Promise<boolean> {
    // The roster and the default go together: a default that is not in the
    // roster reads back as "" (TMDEV-51), so splitting them could blank it.
    return save(
      { elevenlabs_voices: voices, elevenlabs_voice_id: defaultVoiceId },
      "voices",
      { optimistic: true },
    ).then((ok) => {
      if (ok && removed !== undefined) {
        push("success", `Removed voice "${removed.voice.name}".`, {
          label: "Undo",
          onClick: () => { void restoreVoice(removed); },
        });
      }
      return ok;
    });
  }

  /** Puts one removed voice back into the roster as it is now, so a change
   *  made after the removal is kept. It is the default again only if nothing
   *  else became the default meanwhile. */
  function restoreVoice(removed: RemovedVoice) {
    const roster = valRef.current("elevenlabs_voices");
    if (roster.some((v) => v.voice_id === removed.voice.voice_id)) return;
    if (roster.length >= MAX_VOICES) {
      push("error", `No room to put "${removed.voice.name}" back: the roster holds ${MAX_VOICES} voices.`);
      return;
    }
    const next = [...roster];
    next.splice(Math.min(removed.index, next.length), 0, removed.voice);
    const current = valRef.current("elevenlabs_voice_id");
    saveVoices(next, removed.wasDefault && !current ? removed.voice.voice_id : current);
  }

  function changeTab(next: string) {
    // A refused change shows beside its field; once the field is gone from the
    // screen the stored value is what shows when it comes back.
    statuses.clearAll();
    setTab(next as TabKey);
  }

  async function setPaused(paused: boolean) {
    await statuses.run("pipeline_paused", async () => {
      const r = await apiFetch("/pipeline/pause", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paused }),
      }).catch(() => null);
      if (!r?.ok) return responseError(r);
      setS((p) => p ? { ...p, pipeline_paused: paused } : p);
      return null;
    });
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
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <SectionLabel label="Settings" />
        </div>
        <SavesSummaryLine />
      </div>

      {/* ── Section 1: Pipeline Control ── */}
      <SectionLabel label="Pipeline Control" />
      <Row label="Pipeline state" note="Pausing stops the scheduler from advancing new videos.">
        <SaveStatus status={statuses.get("pipeline_paused")} testId="status-pipeline-paused" />
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

      <Tabs value={tab} onValueChange={changeTab}>
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
          <SaveStatus status={statuses.get("gemini_review_enabled")} testId="status-toggle-gemini-review" />
          <button
            data-testid="toggle-gemini-review"
            onClick={() => choose("gemini_review_enabled", !val("gemini_review_enabled"))}
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
          <SaveStatus status={statuses.get("ai_review_model")} testId="status-select-ai-review-model" />
          <select
            data-testid="select-ai-review-model"
            value={AI_REVIEW_MODELS.includes(val("ai_review_model")) ? val("ai_review_model") : AI_REVIEW_MODELS[0]}
            onChange={(e) => choose("ai_review_model", e.target.value)}
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
            {...numField("ai_review_fps")}
          />
        </Row>
        <Row label="Max review rounds" note="How many times the review can send a video back for revision before it is accepted regardless of findings.">
          <NumInput
            value={val("ai_review_max_loops")}
            min={1}
            max={MAX_AI_REVIEW_LOOPS}
            testId="input-ai-review-max-loops"
            {...numField("ai_review_max_loops")}
          />
        </Row>
      </div>
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
          {...numField("max_curriculum_per_run")}
        />
      </Row>
      <Row label="Trending topics per run">
        <NumInput
          value={val("max_trending_per_run")}
          min={0}
          max={50}
          testId="input-max-trending-per-run"
          {...numField("max_trending_per_run")}
        />
      </Row>
      <Row label="Mining topics per run">
        <NumInput
          value={val("max_mining_per_run")}
          min={0}
          max={50}
          testId="input-max-mining-per-run"
          {...numField("max_mining_per_run")}
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
          {...numField("research_pending_cap")}
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
          {...numField("max_research_runs_per_day")}
        />
      </Row>

      {/* ── Section 4: Trending Sources ── */}
      <SectionLabel label="Trending Sources" />
      <div style={{ marginBottom: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.04em" }}>
        Sources the agent scans when generating trending topics.
      </div>
      <TrendingSourcesEditor
        sources={val("trending_sources")}
        onSave={(next) => choose("trending_sources", next)}
        saving={false}
      />
      <SaveStatus status={statuses.get("trending_sources")} testId="status-trending-sources" />
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
        onSave={saveVoices}
        saving={false}
        inputStyle={inputStyle}
      />
      <SaveStatus status={statuses.get("voices")} testId="status-voices" />
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
        </TabsContent>

        <TabsContent value="images">
      {/* ── Image generation ── */}
      <SectionLabel label="Image Generation" />
      <Row
        label="Image model"
        note="The OpenAI model that draws scene images (the generate_image MCP tool). OpenAI grants model access per project, so the OpenAI key's project must have access to the model chosen here."
      >
        <SaveStatus status={statuses.get("image_model")} testId="status-select-image-model" />
        <select
          data-testid="select-image-model"
          value={val("image_model")}
          onChange={(e) => choose("image_model", e.target.value)}
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
        <SaveStatus status={statuses.get("character_model")} testId="status-select-character-model" />
        <select
          data-testid="select-character-model"
          value={val("character_model")}
          onChange={(e) => choose("character_model", e.target.value)}
          style={inputStyle}
        >
          {OPENAI_IMAGE_MODELS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </Row>
        </TabsContent>

        <TabsContent value="rendering">
      {/* ── Rendering ── */}
      <SectionLabel label="Rendering" />
      <Row
        label="Render stall timeout"
        note="How long the render's progress counter may stand still before the renderer kills the render and retries — the check that catches a hung browser in minutes rather than hours. Shown in minutes; stored as render_stall_timeout_secs."
      >
        <NumInput
          value={Math.round(val("render_stall_timeout_secs") / 60)}
          min={1}
          max={120}
          testId="input-render-stall-timeout-mins"
          {...numField("render_stall_timeout_secs", (mins) => mins * 60)}
        />
      </Row>
      <Row
        label="Render timeout"
        note="The ceiling on one render attempt, whatever its progress, before the renderer kills it and retries. Only a render that keeps advancing but pathologically slowly reaches it; raise it on a slow CPU rendering over-length videos. Shown in minutes; stored as render_timeout_secs — same key onboard.py's wizard writes."
      >
        <NumInput
          value={Math.round(val("render_timeout_secs") / 60)}
          min={1}
          max={600}
          testId="input-render-timeout-mins"
          {...numField("render_timeout_secs", (mins) => mins * 60)}
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
          {...numField("max_render_retries")}
        />
      </Row>
      <Row
        label="Watermark"
        note={'Burn the "Made with tubematic.ai" mark into the top-right corner of every rendered video. Applies to renders that start after saving; videos already rendered are not changed.'}
      >
        <SaveStatus status={statuses.get("watermark_enabled")} testId="status-toggle-watermark" />
        <button
          data-testid="toggle-watermark"
          onClick={() => choose("watermark_enabled", !val("watermark_enabled"))}
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
      <Row
        label="Default mascot (experimental)"
        note="The mascot new videos start with, unless their domain has its own. Off by default. A video only gets one while the GPU is working, and never on Cartoon 3D. Draw and approve mascots on the Profiles tab."
      >
        <SaveStatus status={statuses.get("default_mascot_id")} testId="status-select-default-mascot" />
        <select
          data-testid="select-default-mascot"
          title={mascotGateNote(mascotGate(gpu)) || undefined}
          value={val("default_mascot_id") ?? ""}
          onChange={(e) => choose("default_mascot_id", e.target.value)}
          style={{
            fontFamily: "var(--mono)", fontSize: 11, padding: "7px 8px", maxWidth: 260,
            background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--border-2)",
          }}
        >
          {mascotOptions(mascots, gpu, val("default_mascot_id") ?? "").map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
          ))}
        </select>
      </Row>
          <RenderersPanel />
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
          {...numField("log_retention_days")}
        />
      </Row>
        </TabsContent>

        <TabsContent value="retention">
      {/* ── Video retention ── */}
      <SectionLabel label="Video retention" />
      <Row
        label="Delete published videos after"
        note="Days after a video is published before its rendered file and working files (audio, images) are deleted to free disk. The record, its publication links and analytics stay, in the Archive. This setting deletes only published videos. 0 keeps them forever. The worker checks once an hour."
      >
        <NumInput
          value={val("retention_days")}
          min={MIN_RETENTION_DAYS}
          max={MAX_RETENTION_DAYS}
          testId="input-retention-days"
          {...numField("retention_days")}
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
          {...numField("unpublished_retention_days")}
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
            status={statuses.get(key)}
            onCommit={(v) => { void save({ [key]: v } as Partial<Settings>, key); }}
            onSame={() => clearError(key)}
          />
        </Row>
      ))}
        </TabsContent>

        <TabsContent value="publishing">
      {/* ── Publishing (TMDEV-83) ── */}
      <div data-testid="section-publishing">
        <SectionLabel label="Publishing" />
        <Row
          label="Publishing"
          note="Publish approved videos to YouTube, Instagram, TikTok and Facebook via postforme.dev. Every publish is something you click and confirm, unless a project is on Auto Pilot (its own tab), which posts unattended. Needs the postforme.dev key on the API Keys tab."
        >
          <SaveStatus status={statuses.get("publishing_enabled")} testId="status-toggle-publishing" />
          <button
            data-testid="toggle-publishing"
            onClick={togglePublishing}
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
            status={statuses.get("discord_webhook_url")}
            onSame={() => clearError("discord_webhook_url")}
            onCommit={(v) => {
              void save({ discord_webhook_url: v }, "discord_webhook_url",
                        { label: v ? "Checking the webhook…" : undefined });
            }}
          />
        </Row>
        <Row
          label="Dashboard URL"
          note="Used to link back from a notification, e.g. http://192.168.1.20:3000. Leave blank for messages with no links — this container cannot know what address you reach it by."
        >
          <TextInput
            value={val("dashboard_base_url")}
            testId="input-dashboard-base-url"
            status={statuses.get("dashboard_base_url")}
            onCommit={(v) => { void save({ dashboard_base_url: v }, "dashboard_base_url"); }}
            onSame={() => clearError("dashboard_base_url")}
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
          ["notify_partially_published", "A publish partly fails",
           "Live on some accounts, failed on others — names each failed account and its error."],
          ["notify_failed", "A video fails",
           "Rendering or publishing gave up and the video needs you — says why."],
        ] as const).map(([key, label, note]) => (
          <Row key={key} label={label} note={note}>
            <SaveStatus status={statuses.get(key)} testId={`status-toggle-${key.replace(/_/g, "-")}`} />
            <button
              data-testid={`toggle-${key.replace(/_/g, "-")}`}
              onClick={() => choose(key, !val(key))}
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
          Notifications are sent by the worker, so they arrive within a minute
          or so of the event, even while a video is rendering.
        </p>
      </div>
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
          {...numField("max_concurrent_agent_sessions")}
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
          {...numField("agent_session_timeout_secs", (mins) => mins * 60)}
        />
      </Row>
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
      <PreferencesEditor
        value={val("user_preferences") ?? ""}
        status={statuses.get("user_preferences")}
        inputStyle={inputStyle}
        onWaiting={() => statuses.pending("user_preferences")}
        onSame={() => statuses.clear("user_preferences")}
        onSave={(text) => { void save({ user_preferences: text }, "user_preferences"); }}
      />
      <Row
        label="Experimental formulas"
        note="Let Auto pick script formulas marked experimental. Off, Auto chooses among the core formulas only, and an experimental one is used only where you choose it yourself: as a domain's formula on Topics, or for one video at Topic Proposed. Applies to the next video picked for."
      >
        <SaveStatus status={statuses.get("auto_experimental_formulas")} testId="status-toggle-experimental-formulas" />
        <button
          data-testid="toggle-experimental-formulas"
          onClick={() => choose("auto_experimental_formulas", !val("auto_experimental_formulas"))}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.06em",
            padding: "7px 16px",
            border: `1px solid ${val("auto_experimental_formulas") ? "var(--green)" : "var(--border)"}`,
            background: val("auto_experimental_formulas") ? "rgba(74,222,128,0.1)" : "var(--panel)",
            color: val("auto_experimental_formulas") ? "var(--green)" : "var(--mute)",
            cursor: "pointer",
            transition: "all .15s",
          }}
        >
          {val("auto_experimental_formulas") ? "ON" : "OFF"}
        </button>
      </Row>
      <Row
        label="Learn from watch figures"
        note="Let Auto prefer the script formulas that hold your viewers in a domain, read from your own published videos' share watched. It only chooses among formulas that fit the topic, counts a formula once at least 20 of the domain's videos with figures use it on one account, and every fourth pick tries a formula with too few videos. Off, or with publishing off, Auto chooses from the topic alone."
      >
        <SaveStatus status={statuses.get("learned_routing")} testId="status-toggle-learned-routing" />
        <button
          data-testid="toggle-learned-routing"
          onClick={() => choose("learned_routing", !val("learned_routing"))}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.06em",
            padding: "7px 16px",
            border: `1px solid ${val("learned_routing") ? "var(--green)" : "var(--border)"}`,
            background: val("learned_routing") ? "rgba(74,222,128,0.1)" : "var(--panel)",
            color: val("learned_routing") ? "var(--green)" : "var(--mute)",
            cursor: "pointer",
            transition: "all .15s",
          }}
        >
          {val("learned_routing") ? "ON" : "OFF"}
        </button>
      </Row>
        </TabsContent>

        <TabsContent value="costs">
          <CostsPanel inputStyle={inputStyle} notify={(message, action) => push("success", message, action)} />
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
      <Dialog open={confirmPublishing} onOpenChange={(v) => !v && setConfirmPublishing(false)}>
        <DialogContent
          data-testid="publishing-confirm"
          className="border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff]"
          style={{ maxWidth: 520 }}
        >
          <DialogHeader>
            <DialogTitle style={{ fontSize: 15, fontWeight: 600 }}>Turn on publishing?</DialogTitle>
          </DialogHeader>
          <p style={{ fontSize: 13, lineHeight: 1.6, color: "var(--dim)", margin: 0 }}>
            Approved videos get a Publish button, and each publish you start asks you first.
          </p>
          {(autoPilotOn ?? s.auto_pilot_enabled) && (
            <p data-testid="publishing-confirm-auto-pilot"
               style={{ fontSize: 13, lineHeight: 1.6, color: "var(--amber)", margin: 0 }}>
              Auto Pilot is on: videos it approves in its projects start being scheduled to post,
              without asking.
            </p>
          )}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
            <button
              data-testid="publishing-confirm-cancel"
              onClick={() => setConfirmPublishing(false)}
              style={{
                fontFamily: "var(--mono)", fontSize: 11, padding: "7px 14px", cursor: "pointer",
                background: "transparent", border: "1px solid var(--border-2)", color: "var(--dim)",
              }}
            >
              Cancel
            </button>
            <button
              data-testid="publishing-confirm-ok"
              onClick={() => {
                setConfirmPublishing(false);
                choose("publishing_enabled", true);
              }}
              style={{
                fontFamily: "var(--mono)", fontSize: 11, padding: "7px 14px", cursor: "pointer",
                background: "transparent", border: "1px solid var(--amber)", color: "var(--amber)",
              }}
            >
              Turn on publishing
            </button>
          </div>
        </DialogContent>
      </Dialog>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </>
  );
}

// ── Voices roster editor (TMDEV-51) ───────────────────────────────────────────

/** A voice just removed, with what Undo needs to put it back. */
interface RemovedVoice {
  voice: Voice;
  index: number;
  wasDefault: boolean;
}

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
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
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
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
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
      <SpeedSelect
        testId={`voice-speed-${index}`}
        model={voice.model_id}
        speed={voice.speed ?? 1}
        onChange={(speed) => onCommit({ speed })}
        inputStyle={inputStyle}
      />
      <label
        data-testid={`voice-default-${index}`}
        style={{ display: "flex", alignItems: "center", gap: 4, fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-2)", cursor: "pointer" }}
      >
        <input type="radio" checked={isDefault} onChange={onSetDefault} />
        default
      </label>
      <VoicePreviewButton voiceId={voice.voice_id} modelId={voice.model_id}
                          speed={SPEED_MODELS.includes(voice.model_id) ? (voice.speed ?? 1) : 1} />
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
  /** Resolves to whether the change was stored. */
  onSave: (voices: Voice[], defaultVoiceId: string, removed?: RemovedVoice) => Promise<boolean>;
  saving: boolean;
  inputStyle: React.CSSProperties;
}) {
  const [newName, setNewName] = useState("");
  const [newId, setNewId] = useState("");
  const [newModel, setNewModel] = useState(DICTIONARY_COMPATIBLE_MODELS[0]);
  const [newSpeed, setNewSpeed] = useState(1);

  function commitRow(index: number, patch: Partial<Voice>) {
    // A new voice id on the default voice moves the default with it, or the
    // default would point at an id no longer in the roster and read as none.
    const wasDefault = voices[index].voice_id === defaultVoiceId;
    const nextDefault = wasDefault && patch.voice_id ? patch.voice_id : defaultVoiceId;
    onSave(voices.map((v, i) => (i === index ? withSpeed({ ...v, ...patch }) : v)), nextDefault);
  }

  function removeRow(index: number) {
    const removedId = voices[index].voice_id;
    onSave(
      voices.filter((_, i) => i !== index),
      defaultVoiceId === removedId ? "" : defaultVoiceId,
      { voice: voices[index], index, wasDefault: defaultVoiceId === removedId },
    );
  }

  function addVoice() {
    if (!newName.trim() || !newId.trim() || voices.length >= MAX_VOICES) return;
    // The row empties only once the voice is stored: refused, what you typed
    // (a long ElevenLabs id) is still there to correct.
    void onSave([...voices, withSpeed({ name: newName.trim(), voice_id: newId.trim(),
                                        model_id: newModel, speed: newSpeed })],
                defaultVoiceId).then((ok) => {
      if (!ok) return;
      setNewName("");
      setNewId("");
      setNewSpeed(1);
    });
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
          <SpeedSelect
            testId="voice-add-speed"
            model={newModel}
            speed={newSpeed}
            onChange={setNewSpeed}
            inputStyle={inputStyle}
          />
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
// the agent's models is its default are editable, each saved the moment it
// changes on its own endpoint, PATCH /agents/<id>.

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
  onInvalid,
  onSame,
}: {
  agent: Agent;
  disabled: boolean;
  inputStyle: React.CSSProperties;
  /** Resolves once the save is over, whatever became of it. */
  onSave: (n: number) => Promise<unknown>;
  onInvalid: (message: string) => void;
  /** Typed back to the stored weight: a refusal shown for it no longer applies. */
  onSame: () => void;
}) {
  const [local, setLocal] = useState(String(agent.weight));
  // The weight on its way, so Enter then blur sends it once. Cleared when
  // that save is over, so the same number can be sent again after a refusal.
  const sent = useRef<number | null>(null);
  useEffect(() => { setLocal(String(agent.weight)); sent.current = null; }, [agent.weight]);

  // Saved on blur or Enter, like every number on this page. An out-of-range
  // value stays in the box with the reason beside it, and is never sent.
  function commit() {
    const text = local.trim();
    const n = Number(text);
    if (!/^\d+$/.test(text) || n > MAX_AGENT_WEIGHT) {
      onInvalid(`weight must be a whole number from 0 to ${MAX_AGENT_WEIGHT}`);
      return;
    }
    if (n === agent.weight) {
      sent.current = null;
      onSame();
      return;
    }
    if (n === sent.current) return;
    sent.current = n;
    void onSave(n).finally(() => { if (sent.current === n) sent.current = null; });
  }

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
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
        style={{ ...inputStyle, width: 70 }}
      />
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
  const statuses = useSaveStatus();

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

  /** `key` names the status and error line the outcome shows in: the row's
   *  (the agent id), or the weight's own (`<id>:weight`), so a change to the
   *  effort or model never wipes a refusal shown for the weight. */
  async function mutate(id: string, init: RequestInit, key: string = id) {
    setBusy(id);
    setErrors((e) => ({ ...e, [key]: "" }));
    // The row shows "Saving…" then "✓ Saved"; a refusal shows in its own
    // red line under the row, as it always has.
    await statuses.run(key, async () => {
      try {
        const r = await apiFetch(`/agents/${id}`, { ...init, signal: AbortSignal.timeout(SAVE_TIMEOUT_MS) });
        if (!r.ok) {
          const detail = await errorDetail(r);
          setErrors((e) => ({ ...e, [key]: detail }));
          return detail;
        }
        // Reload rather than splice in the returned row: making one agent the
        // default clears is_default on whichever agent held it before.
        await load();
        return null;
      } catch (e) {
        const detail = e instanceof Error ? e.message : "unreachable";
        setErrors((prev) => ({ ...prev, [key]: detail }));
        return detail;
      } finally {
        setBusy(null);
      }
    });
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
    }, "weight" in body ? `${id}:weight` : id);
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
                    onInvalid={(message) => {
                      // Counted as not saved on the page line; the reason
                      // shows in the weight's own error line.
                      statuses.fail(`${a.id}:weight`, message);
                      setErrors((e) => ({ ...e, [`${a.id}:weight`]: message }));
                    }}
                    onSame={() => {
                      if (statuses.get(`${a.id}:weight`)?.state !== "error") return;
                      statuses.clear(`${a.id}:weight`);
                      setErrors((e) => ({ ...e, [`${a.id}:weight`]: "" }));
                    }}
                  />
                  {statuses.get(`${a.id}:weight`)?.state !== "error" && (
                    <SaveStatus status={statuses.get(`${a.id}:weight`)} testId={`status-agent-weight-${a.id}`} />
                  )}
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

                {statuses.get(a.id)?.state !== "error" && (
                  <div style={{ marginTop: 8 }}>
                    <SaveStatus status={statuses.get(a.id)} testId={`status-agent-${a.id}`} />
                  </div>
                )}
                {errors[a.id] && (
                  <div data-testid={`agent-error-${a.id}`} role="alert" style={{ ...mono, fontSize: 10.5, color: "var(--red)", marginTop: 8 }}>
                    {errors[a.id]}
                  </div>
                )}
                {errors[`${a.id}:weight`] && (
                  <div data-testid={`agent-weight-error-${a.id}`} role="alert" style={{ ...mono, fontSize: 10.5, color: "var(--red)", marginTop: 8 }}>
                    Weight not saved: {errors[`${a.id}:weight`]}
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
