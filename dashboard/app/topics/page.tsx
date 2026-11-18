"use client";

import { useEffect, useRef, useState } from "react";
import type { Agent, GpuStatus, Mascot, Project, ProjectStatus, ScriptProfile, Voice } from "@/lib/types";
import { AGENT_EFFORTS, effortOptionLabel } from "@/lib/agents";
import {
  NO_DOMAIN_DEFAULTS, domainAgent, domainAgentOptions, domainChips, domainDefaults,
  domainModelOptions, type DomainDefaultValues, type DomainLists,
} from "@/lib/domains";
import { mascotGate, mascotGateNote, mascotOptions } from "@/lib/mascots";
import { voiceLabel } from "@/lib/voices";
import { illustratedAvailable } from "@/lib/visualStyles";
import { StylePicker } from "@/components/StylePicker";
import { codePoints } from "@/lib/utils";
import { SectionLabel } from "@/components/SectionLabel";
import { MiningSources } from "@/components/MiningSources";
import { useVisualStyles } from "@/components/VisualStylesProvider";
import { SaveStatus } from "@/components/SaveStatus";
import { ToastStack, useToasts } from "@/components/Toast";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { responseError, useSaveStatus, useSerialQueue, type SaveState } from "@/lib/saveStatus";
import { formulaOptions, type ScriptFormulaNames } from "@/lib/scriptFormulas";
import { INSERT_MODE_OPTIONS, INSERTS_TITLE, insertMode } from "@/lib/inserts";
import { useScriptFormulaNames } from "@/lib/useScriptFormulas";

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

// ── Default formula picker ──────────────────────────────────────────────────

function DomainFormulaSelect({ testId, value, names, onChange }: {
  testId: string; value: string; names: ScriptFormulaNames | null; onChange: (next: string) => void;
}) {
  return (
    <select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title="The script formula every new video in this domain is written in. Auto picks one for each video from its topic."
      style={pickerStyle}
    >
      {formulaOptions(names, value).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
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

// Tallest the description box grows to on its own; past it the box scrolls,
// and the corner handle still drags it taller.
const DESCRIPTION_MAX_AUTO_HEIGHT = 320;

// What the agent does with a domain's description. The skills read it as the
// domain's standing instructions (TMDEV-256): keep this in step with
// tubematic-operator, tubematic-topic-research and the script-writing skill.
const DESCRIPTION_NOTE =
  "Research works from this description, and the agent follows what it says about this " +
  "domain's topics, scripts and look on every video here: what to cover or leave out, the " +
  "audience, the tone. It cannot skip a step that waits for your approval.";

// The edit `next` makes to `prev`, with what it inserts cut so the text holds at
// most `limit` code points. Only the inserted run is cut: a paste or a letter
// typed into the middle of a full text must not push the end of it out.
// `caret` is where the browser put the caret after the edit, the end of what
// was inserted: the text after it is what the edit left in place. Comparing
// the two strings alone cannot tell where a paste over a selection ends when
// the pasted text repeats what it replaced.
function clampEdit(prev: string, next: string, limit: number, caret = next.length): string {
  const total = codePoints(next).length;
  if (total <= limit) return next;
  const end = Math.min(Math.max(caret, 0), next.length);
  const kept = next.slice(end);
  // Not an edit this function can read: refuse it rather than guess.
  if (!prev.endsWith(kept)) return prev;
  let start = 0;
  const maxStart = Math.min(end, prev.length - kept.length);
  while (start < maxStart && prev[start] === next[start]) start++;
  // Never split a surrogate pair: back up to its first half.
  if (start > 0 && /[\uD800-\uDBFF]/.test(next[start - 1])) start--;
  const inserted = codePoints(next.slice(start, end));
  const room = Math.max(0, limit - (total - inserted.length));
  return next.slice(0, start) + inserted.slice(0, room).join("") + kept;
}

// The description box on the add form and on a domain's open row: one
// component so the cap, the counter and the note cannot drift apart. It grows
// with its text, so a scope written in paragraphs is read without scrolling.
function DomainDescriptionField({ testId, countTestId, value, onChange, onFocus, onBlur }: {
  testId: string; countTestId: string; value: string;
  onChange: (next: string) => void; onFocus?: () => void; onBlur?: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight + 2, DESCRIPTION_MAX_AUTO_HEIGHT)}px`;
  }, [value]);
  const count = codePoints(value).length;
  return (
    <div style={{ width: "100%" }}>
      <textarea
        ref={ref}
        data-testid={testId}
        aria-label="Description"
        value={value}
        rows={3}
        onChange={(e) => {
          // The cap stops the text growing; it never cuts one stored longer
          // before the cap existed, which the API keeps until it changes.
          onChange(clampEdit(value, e.target.value, Math.max(MAX_DOMAIN_DESCRIPTION_CHARS, count),
                             e.target.selectionEnd ?? undefined));
        }}
        placeholder="Description: what this domain covers, and any instructions for the agent (optional)"
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
        onFocus={(e) => { e.currentTarget.style.borderColor = "var(--indigo)"; onFocus?.(); }}
        onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; onBlur?.(); }}
      />
      <div style={{ display: "flex", gap: 16, alignItems: "baseline", marginTop: 4 }}>
        <div data-testid={`${testId}-note`} style={{ ...noteStyle, flex: 1, minWidth: 0 }}>
          {DESCRIPTION_NOTE}
        </div>
        <div
          data-testid={countTestId}
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10.5,
            whiteSpace: "nowrap",
            color: count >= MAX_DOMAIN_DESCRIPTION_CHARS * 0.9 ? "var(--amber)" : "var(--mute)",
          }}
        >
          {count} / {MAX_DOMAIN_DESCRIPTION_CHARS}
        </div>
      </div>
    </div>
  );
}

// A domain's description on its open row, saved on blur like the topic cap:
// a save per keystroke would re-send the whole row for every letter. Trailing
// space is trimmed as the add form trims it. A refused save keeps the text in
// the box so it can be corrected; the row says why. The stored text is copied
// in only while the box is not being edited and no newer text is still being
// saved: an older save that lands after you typed again must not put the older
// text back, nor leave it there if the newer save is then refused.
function DomainDescriptionInput({ testId, value, onCommit }: {
  testId: string; value: string; onCommit: (next: string) => Promise<boolean>;
}) {
  const [local, setLocal] = useState(value);
  const editing = useRef(false);
  // The last text sent, until its save answers.
  const pending = useRef<string | null>(null);
  useEffect(() => {
    if (editing.current) return;
    if (pending.current !== null && value !== pending.current) return;
    pending.current = null;
    setLocal(value);
  }, [value]);
  function commit() {
    editing.current = false;
    const next = local.trim();
    if (next === value) {
      // A save landing while the box was focused was not copied in: show it
      // now that nothing is left to send.
      if (pending.current === null) setLocal(value);
      return;
    }
    pending.current = next;
    const settle = () => { if (pending.current === next) pending.current = null; };
    onCommit(next).then(settle, settle);
  }
  return (
    <DomainDescriptionField
      testId={testId}
      countTestId={`${testId}-count`}
      value={local}
      onChange={setLocal}
      onFocus={() => { editing.current = true; }}
      onBlur={commit}
    />
  );
}

// Commits on blur or Enter, like Settings' number fields, so typing "300" is
// one save rather than three. An entry outside the bounds is kept, with the
// reason on the domain's line, so it can be corrected.
function DomainCapInput({ testId, value, onCommit, onInvalid }: {
  testId: string; value: number; onCommit: (next: number) => Promise<boolean>;
  onInvalid: (message: string) => void;
}) {
  const [local, setLocal] = useState(String(value));
  useEffect(() => { setLocal(String(value)); }, [value]);
  function commit() {
    const n = Number(local);
    if (Number.isInteger(n) && n >= MIN_TOPIC_CAP && n <= MAX_TOPIC_CAP) {
      // A save that was refused, or never reached the API, leaves `value` as
      // it was, so the effect above does not run: put the stored cap back by
      // hand, or the field keeps showing a number the domain does not have.
      const revert = () => setLocal(String(value));
      if (n !== value) onCommit(n).then((saved) => { if (!saved) revert(); }, revert);
    } else {
      onInvalid(`topic cap must be a whole number from ${MIN_TOPIC_CAP} to ${MAX_TOPIC_CAP}`);
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
// gave no place to say so. The bases are what each group needs for its
// pickers to show their longest usual value ("Automatic (dealt by weight)",
// "Use install default") in full: where three groups do not fit on one line,
// the Agent group wraps onto its own line instead of cutting text short.
function DomainGroup({ title, accent, note, flex = "1.1 1 360px", children }: {
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

type DefaultControl = "style" | "inserts" | "voice" | "profile" | "formula" | "mascot" | "agent" | "agent-model" | "agent-effort";

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
      {/* Wider than the default group basis: a third picker (Inserts) sits beside the style and mascot. */}
      <DomainGroup title="Look" flex="1.2 1 460px"
                   note="The style starts this domain's curriculum videos. The mascot and the inserts setting start every new video.">
        <div style={{ display: "flex", gap: 8 }}>
          <DomainField label="Visual style" flex="1.2 1 0">
            <StylePicker
              testId={testId("style")}
              styles={lists.styles}
              canUseOpenAI={canIllustrate}
              gpu={gpu}
              value={values.default_visual_style}
              onChange={(next) => onChange({ default_visual_style: next })}
              noneLabel="No style"
              title="Register this domain's curriculum videos start in"
              buttonStyle={pickerStyle}
            />
          </DomainField>
          <DomainField label="Mascot (exp.)" flex="1 1 0">
            <DomainMascotSelect testId={testId("mascot")} value={values.default_mascot_id}
                                mascots={lists.mascots} gpu={gpu}
                                onChange={(next) => onChange({ default_mascot_id: next })} />
          </DomainField>
          {/* Not locked by the style above: that style reaches curriculum videos
              only, while this setting starts every new video in the domain. */}
          <DomainField label="Inserts" flex="0.7 1 0">
            <select
              data-testid={testId("inserts")}
              value={values.default_insert_mode}
              onChange={(e) => onChange({ default_insert_mode: insertMode(e.target.value) })}
              title={INSERTS_TITLE}
              style={pickerStyle}
            >
              {INSERT_MODE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </DomainField>
        </div>
      </DomainGroup>

      <DomainGroup title="Narration" flex="1.5 1 540px"
                   note="The voice and the formula start every new video. The profile starts curriculum videos.">
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
          <DomainField label="Formula" flex="1 1 0">
            <DomainFormulaSelect testId={testId("formula")} value={values.default_formula_id}
                                 names={lists.formulaNames}
                                 onChange={(next) => onChange({ default_formula_id: next })} />
          </DomainField>
        </div>
      </DomainGroup>

      <DomainGroup title="Agent" accent flex="1.6 1 600px"
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
// status. The description and the defaults sit in a panel under the line,
// opened by "Edit domain". Seven pickers and a cap on the line itself left no room
// for the name, and nowhere to say which videos each default applies to.
function DomainRow({ project, videoCounts, status, onToggle, onDelete, onSave, onInvalid, lists, canIllustrate, gpu }: {
  project: Project;
  videoCounts: Record<string, number>;
  /** How the last change to this domain went: shown on the line itself, so a
   *  refusal is seen with the panel closed too. */
  status?: SaveState;
  onToggle: (id: string, next: ProjectStatus) => void;
  /** Asks to delete this domain; the page opens the confirmation. */
  onDelete: (project: Project) => void;
  /** Resolves to whether the change was stored. */
  onSave: (id: string, patch: Partial<Project>) => Promise<boolean>;
  /** An entry refused before it is sent, shown like a refused save. */
  onInvalid: (id: string, message: string) => void;
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
            <span data-testid={`domain-name-${project.id}`} title={project.name} style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 600, color: "var(--ink)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flexShrink: 0, maxWidth: "100%" }}>
              {project.name}
            </span>
            {project.description && (
              <span data-testid={`domain-description-${project.id}`} title={project.description} style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--dim)", letterSpacing: "0.06em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
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

            {/* Delete is offered on a paused seed only: pausing first is the
                second step that keeps a domain from being deleted by one
                stray click. The confirmation says what goes with it. */}
            {isPaused && (
              <button
                data-testid={`delete-domain-${project.id}`}
                onClick={() => onDelete(project)}
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  padding: "6px 14px",
                  background: "transparent",
                  border: "1px solid var(--border-2)",
                  color: "var(--red)",
                  cursor: "pointer",
                  transition: "all .12s",
                  flexShrink: 0,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255,107,107,0.5)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-2)"; }}
              >
                Delete
              </button>
            )}
          </>
        )}

        <SaveStatus status={status} testId={`domain-save-status-${project.id}`} />

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
          {open ? "Close" : "Edit domain"}
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
          {/* The description is the domain's standing instructions to the
              agent (TMDEV-256), so it opens the panel, across its full width. */}
          <DomainGroup title="Description" flex="1 1 100%"
                       note="Saved when you click away from the box.">
            <DomainDescriptionInput
              testId={`domain-description-input-${project.id}`}
              value={project.description ?? ""}
              onCommit={(next) => onSave(project.id, { description: next })}
            />
          </DomainGroup>
          <DomainDefaults
            values={values}
            onChange={(patch) => { void onSave(project.id, patch as Partial<Project>); }}
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
                  onInvalid={(message) => onInvalid(project.id, message)}
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
      <DomainDescriptionField
        testId="domain-description-input"
        countTestId="domain-description-count"
        value={description}
        onChange={setDescription}
      />

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

// What the message beside the domain calls the field a refused save was about, when the API gave
// no reason of its own.
const SAVED_FIELD: Record<string, string> = {
  description: "description",
  default_visual_style: "style",
  default_voice_id: "default voice",
  default_script_profile_id: "script profile",
  default_formula_id: "formula",
  default_insert_mode: "inserts setting",
  default_mascot_id: "mascot",
  default_agent_id: "agent",
  default_agent_model: "agent's model",
  default_agent_effort: "agent's effort",
  topic_cap: "topic cap",
};


// How long one write to a domain may go unanswered. Writes to a domain wait
// for one another, so one that never answered would hold every later change
// to that domain behind it; past this it counts as not having reached the API.
const DOMAIN_WRITE_TIMEOUT_MS = 30_000;
// A delete removes every render and job folder under the domain before it
// answers, so it is given longer than a field change.
const DOMAIN_DELETE_TIMEOUT_MS = 120_000;

export default function TopicsPage() {
  const [projects, setProjectsState] = useState<Project[]>([]);
  // The rows as of the last write, readable by a save the moment the one
  // before it finishes. State alone is too late for that: it reaches a closure
  // only on the next render. Every write to the list goes through setProjects.
  const projectsRef = useRef<Project[]>([]);
  function setProjects(next: (prev: Project[]) => Project[]) {
    projectsRef.current = next(projectsRef.current);
    setProjectsState(projectsRef.current);
  }
  // One chain of writes per domain. POST /projects replaces the whole row, so
  // two writes to one domain sent side by side would each carry the other's
  // field as it was before, and the later answer would win with the earlier
  // change lost. Queued, each is built from the row as the one before left it,
  // and a refused one is simply not there for the next. A pause goes through
  // the same chain, or a change sent behind it would re-send "active".
  const domainWrites = useRef<Record<string, Promise<void>>>({});
  function queued<T>(id: string, write: () => Promise<T>): Promise<T> {
    const run = (domainWrites.current[id] ?? Promise.resolve()).then(write);
    // The chain goes on whatever became of this write: one that threw must
    // not hold up every later change to the domain.
    domainWrites.current[id] = run.then(() => {}, () => {});
    return run;
  }
  const [videoCounts, setVideoCounts] = useState<Record<string, number>>({});
  const [activeStrategies, setActiveStrategies] = useState<string[]>(["curriculum", "trending", "mining"]);
  const [miningUrls, setMiningUrls] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [modesError, setModesError] = useState<string | null>(null);
  // Assumed until /research/strategies answers, so a slow load never shows the
  // toggle greyed out on an install that has the key.
  const [miningAvailable, setMiningAvailable] = useState(true);
  const [savingMining, setSavingMining] = useState(false);
  const [miningError, setMiningError] = useState<string | null>(null);
  const statuses = useSaveStatus();
  const { toasts, push, dismiss } = useToasts();
  // The newest list, for an Undo clicked after later changes.
  const miningUrlsRef = useRef<string[]>([]);
  miningUrlsRef.current = miningUrls;
  const storedMiningRef = useRef<string[]>([]);
  const miningInFlight = useRef(0);
  const enqueueMining = useSerialQueue();
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
  const formulaNames = useScriptFormulaNames(true);
  const lists: DomainLists = { styles: visualStyles, voices, profiles, mascots, agents, formulaNames };

  async function loadAll() {
    const [projRes, vidRes, stratRes, miningRes] = await Promise.all([
      apiFetch("/projects"),
      apiFetch("/videos"),
      apiFetch("/research/strategies"),
      apiFetch("/research/mining-sources"),
    ]);
    if (projRes.ok) {
      const p: Project[] = await projRes.json();
      setProjects(() => p);
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
      storedMiningRef.current = m.youtube_urls;
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

  function handleToggleDomain(id: string, next: ProjectStatus) {
    void statuses.run(id, () => queued(id, async () => {
      const r = await apiFetch(`/projects/${id}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
        signal: AbortSignal.timeout(DOMAIN_WRITE_TIMEOUT_MS),
      }).catch(() => null);
      // A refusal is reported beside the domain, not shown as success: only a
      // curriculum seed can be paused, and the row may have stopped being one
      // since this page loaded.
      if (!r?.ok) {
        return r ? responseError(r) : "could not change this domain's status";
      }
      setProjects((prev) => prev.map((p) => p.id === id ? { ...p, status: next } : p));
      return null;
    }));
  }

  // The domain waiting on the delete confirmation, and whether the Paused
  // group is open. Paused seeds sit in a collapsed group so the active ones
  // are what the page opens on.
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [pausedOpen, setPausedOpen] = useState(false);

  function handleDeleteDomain(project: Project) {
    const id = project.id;
    void statuses.run(id, () => queued(id, async () => {
      const r = await apiFetch(`/projects/${id}`, {
        method: "DELETE",
        signal: AbortSignal.timeout(DOMAIN_DELETE_TIMEOUT_MS),
      }).catch(() => null);
      // A refusal (a video still rendering, the domain no longer paused) is
      // reported beside the row, which stays.
      if (!r?.ok) {
        return r ? responseError(r) : "could not delete this domain";
      }
      setProjects((prev) => prev.filter((p) => p.id !== id));
      push("success", `Deleted domain “${project.name}” and everything filed under it.`);
      return null;
    }));
  }

  function saveDomain(id: string, patch: Partial<Project>): Promise<boolean> {
    return statuses.run(id, () => queued(id, async () => {
      const project = projectsRef.current.find((p) => p.id === id);
      if (!project) return "this domain is no longer listed";
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
        signal: AbortSignal.timeout(DOMAIN_WRITE_TIMEOUT_MS),
      }).catch(() => null);
      // A save that never reached the API is reported like a refused one, and
      // the row keeps showing what is stored.
      if (!r?.ok) {
        const body = r ? await r.json().catch(() => ({})) : {};
        return typeof body.error === "string" && body.error
          ? body.error
          : `could not change this domain's ${SAVED_FIELD[Object.keys(patch)[0]] ?? "settings"}`;
      }
      // The saved row carries the topic count and expiry as they are now. The
      // count loaded with the page can be stale (research may have filed since),
      // so expiry is never worked out here from the new cap. The id check keeps
      // a response that is not a project row from being merged in.
      const saved = await r.json().catch(() => null);
      const fresh = saved && saved.id === id ? (saved as Project) : {};
      setProjects((prev) => prev.map((p) => p.id === id ? { ...p, ...patch, ...fresh } : p));
      return null;
    }));
  }

  async function handleModeChange(next: string[]) {
    setModesError(null);
    await statuses.run("modes", async () => {
      const res = await apiFetch("/research/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategies: next }),
      }).catch(() => null);
      if (res?.ok) {
        setActiveStrategies(next);
        return null;
      }
      // Nothing was stored, so the toggles keep showing what is in effect.
      const body = res ? await res.json().catch(() => ({})) : {};
      const message = typeof body.error === "string" && body.error
        ? body.error
        : "Failed to save research modes — changes were not persisted.";
      setModesError(message);
      return message;
    });
  }

  // Mining saves run one at a time: each sends a whole list, so two side by
  // side would race, and the screen could show the answer that lost.
  function handleMiningUrlsChange(next: string[]) {
    setMiningUrls(next);
    setSavingMining(true);
    setMiningError(null);
    miningInFlight.current += 1;
    return enqueueMining(() => saveMiningUrls(next));
  }

  async function saveMiningUrls(next: string[]) {
    // What is stored when this save goes out, not what the screen shows.
    const prev = storedMiningRef.current;
    const removed = prev.filter((u) => !next.includes(u));
    const ok = await statuses.run("mining", async () => {
      const res = await apiFetch("/research/mining-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_urls: next }),
      }).catch(() => null);
      const body = res ? await res.json().catch(() => ({})) : {};
      if (!res?.ok) {
        setMiningUrls(prev);
        // The API's 400 names the entries it refused; say that, not just "failed".
        const message = typeof body.error === "string" && body.error
          ? body.error
          : "Failed to save mining sources — changes were not persisted.";
        setMiningError(message);
        return message;
      }
      // The list as stored: canonical and deduplicated by the API.
      const stored = Array.isArray(body.youtube_urls) ? body.youtube_urls as string[] : next;
      storedMiningRef.current = stored;
      setMiningUrls(stored);
      return null;
    });
    miningInFlight.current -= 1;
    if (miningInFlight.current === 0) setSavingMining(false);
    // A removal applies at once. Undo puts that one URL back into the list as
    // it is then, so a change made after the removal is kept.
    if (ok && removed.length === 1 && next.length === prev.length - 1) {
      const url = removed[0];
      const index = prev.indexOf(url);
      push("success", `Removed ${url}.`, {
        label: "Undo",
        onClick: () => {
          const current = miningUrlsRef.current;
          if (current.includes(url)) return;
          const restored = [...current];
          restored.splice(Math.min(index, restored.length), 0, url);
          void handleMiningUrlsChange(restored);
        },
      });
    }
  }

  const seedDomains = projects.filter((p) => p.is_curriculum_seed === 1);
  const activeSeeds = seedDomains.filter((p) => p.status !== "paused");
  const pausedSeeds = seedDomains.filter((p) => p.status === "paused");
  const otherDomains = projects.filter((p) => p.is_curriculum_seed !== 1);

  return (
    <>
      <SectionLabel label="Topics & Modes" count={`${projects.length} domains`} />

      {/* Research Modes */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--mute)", marginBottom: 10 }}>
          Research Modes
          {statuses.get("modes")?.state !== "error" && (
            <span style={{ marginLeft: 10, textTransform: "none", letterSpacing: "normal" }}>
              <SaveStatus status={statuses.get("modes")} testId="modes-save-status" />
            </span>
          )}
        </div>
        <ModeToggles active={activeStrategies} miningAvailable={miningAvailable}
                     onChange={handleModeChange} />
        {modesError && (
          <div data-testid="mode-error" role="alert" style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--red)", letterSpacing: "0.04em" }}>
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
          {statuses.get("mining")?.state !== "error" && (
            <span style={{ marginLeft: 10, textTransform: "none", letterSpacing: "normal" }}>
              <SaveStatus status={statuses.get("mining")} testId="mining-save-status" />
            </span>
          )}
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
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 24 }}>
            {activeSeeds.map((p) => (
              <DomainRow key={p.id} project={p} videoCounts={videoCounts} status={statuses.get(p.id)} onToggle={handleToggleDomain} onDelete={setDeleting} onSave={saveDomain} onInvalid={statuses.fail} lists={lists} canIllustrate={canIllustrate} gpu={gpu} />
            ))}
          </div>

          {/* Paused seeds, collapsed: they generate nothing, and deleting a
              domain starts here. */}
          {pausedSeeds.length > 0 && (
            <section data-testid="paused-domains" style={{ marginBottom: 24 }}>
              <button
                type="button"
                data-testid="paused-domains-toggle"
                aria-expanded={pausedOpen}
                aria-controls="paused-domains-list"
                onClick={() => setPausedOpen((o) => !o)}
                style={{
                  fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase",
                  color: "var(--mute)", background: "transparent", border: "none", cursor: "pointer",
                  padding: 0, marginBottom: 10,
                }}
              >
                {pausedOpen ? "▾" : "▸"} Paused ({pausedSeeds.length})
              </button>
              {pausedOpen && (
                <div id="paused-domains-list" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {pausedSeeds.map((p) => (
                    <DomainRow key={p.id} project={p} videoCounts={videoCounts} status={statuses.get(p.id)} onToggle={handleToggleDomain} onDelete={setDeleting} onSave={saveDomain} onInvalid={statuses.fail} lists={lists} canIllustrate={canIllustrate} gpu={gpu} />
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {/* Other domains */}
      {otherDomains.length > 0 && (
        <section>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.22em", textTransform: "uppercase", color: "var(--mute)", marginBottom: 10 }}>
            Other Domains (trending / mining / manual)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {otherDomains.map((p) => (
              <DomainRow key={p.id} project={p} videoCounts={videoCounts} status={statuses.get(p.id)} onToggle={handleToggleDomain} onDelete={setDeleting} onSave={saveDomain} onInvalid={statuses.fail} lists={lists} canIllustrate={canIllustrate} gpu={gpu} />
            ))}
          </div>
        </section>
      )}
      <Dialog open={deleting !== null} onOpenChange={(v) => !v && setDeleting(null)}>
        <DialogContent
          data-testid="delete-domain-confirm"
          className="border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff]"
          style={{ maxWidth: 520 }}
        >
          <DialogHeader>
            <DialogTitle style={{ fontSize: 15, fontWeight: 600 }}>
              Delete “{deleting?.name}”?
            </DialogTitle>
          </DialogHeader>
          <p data-testid="delete-domain-warning" style={{ fontSize: 13, lineHeight: 1.6, color: "var(--dim)", margin: 0 }}>
            This permanently deletes the domain and all {deleting?.topic_count ?? 0} topics
            and videos filed under it, with their rendered files, comments and publishing
            records. It cannot be undone. Posts already live on YouTube, Instagram, TikTok
            or Facebook stay up there; only this record of them goes. Spending history is kept.
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
            <button
              data-testid="delete-domain-cancel"
              onClick={() => setDeleting(null)}
              style={{
                fontFamily: "var(--mono)", fontSize: 11, padding: "7px 14px", cursor: "pointer",
                background: "transparent", border: "1px solid var(--border-2)", color: "var(--dim)",
              }}
            >
              Cancel
            </button>
            <button
              data-testid="delete-domain-ok"
              onClick={() => {
                const target = deleting;
                setDeleting(null);
                if (target) handleDeleteDomain(target);
              }}
              style={{
                fontFamily: "var(--mono)", fontSize: 11, padding: "7px 14px", cursor: "pointer",
                background: "transparent", border: "1px solid var(--red)", color: "var(--red)",
              }}
            >
              Delete domain
            </button>
          </div>
        </DialogContent>
      </Dialog>
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </>
  );
}
