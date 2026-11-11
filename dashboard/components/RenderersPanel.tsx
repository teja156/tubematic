"use client";

// Settings → Rendering → Renderers: every machine that renders for this
// install, the built-in renderer first, and the controls the dashboard has
// over them.
//
// Self-contained like CostsPanel: it reads and writes its own routes and sits
// outside the settings form's Save/dirty machinery. What it cannot do is
// change a renderer's GPU or start one: that is the host's job
// (`onboard.py --step gpu` for the built-in renderer, the remote renderer
// script for the others), because the dashboard has no Docker access by design.
//
// "GPU verified" is decided by the renderer from Chromium's WebGL renderer
// string, never from a render having finished: on the wrong GL device a render
// still finishes, just slowly. So the renderer string is always shown.

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { Renderer, RendererEnrollment, RenderersList } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatDate, formatDateTime } from "@/lib/datetime";
import { SaveStatus } from "@/components/SaveStatus";
import { useSaveStatus, type SaveState } from "@/lib/saveStatus";
import {
  CHIP, GPU_STEP_COMMAND, NAME_MAX_CHARS, REMOTE_SCRIPT, REMOTE_UPGRADE_COMMAND, RENDERERS_STEP_COMMAND,
  anyProbePending, computeLine, describeDevice, gpuVerdict, hasGpu, isRenderersList, lastSeen, nameError,
  rendererStatus, vramLine,
} from "@/lib/renderers";

const POLL_MS = 20_000;
// While a GPU test is outstanding: the answer arrives on the renderer's next
// heartbeat, or after the render it is busy with.
const PROBE_POLL_MS = 3_000;

type Answer = { ok: boolean; status: number; body: unknown };

async function request(path: string, init?: RequestInit): Promise<Answer> {
  const r = await fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
  let body: unknown = null;
  try { body = await r.json(); } catch { /* bodiless or not JSON */ }
  return { ok: r.ok, status: r.status, body };
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

const KNOWN_ERRORS: Record<string, string> = {
  remote_renderers_off: `Remote renderers are off. Turn them on first: ${RENDERERS_STEP_COMMAND}`,
  builtin: "The built-in renderer cannot be removed.",
  not_found: "That renderer no longer exists. It may have been removed.",
  gateway_certificate_missing: "The render gateway's certificate is missing, so no token can be issued.",
};

function errorText(a: Answer): string {
  const code = (a.body as { error?: unknown } | null)?.error;
  if (typeof code === "string" && code) return KNOWN_ERRORS[code] ?? code;
  return `HTTP ${a.status}`;
}

const mono = { fontFamily: "var(--mono)" } as const;
const note: CSSProperties = { ...mono, fontSize: 10, color: "var(--mute)", letterSpacing: "0.02em",
                              lineHeight: 1.6 };
const value: CSSProperties = { ...mono, fontSize: 11, color: "var(--ink)", wordBreak: "break-word" };
const button: CSSProperties = {
  ...mono, fontSize: 10, color: "var(--blue)", background: "var(--panel)",
  border: "1px solid var(--border)", padding: "4px 10px", cursor: "pointer",
};
const code: CSSProperties = { ...mono, fontSize: 11, color: "var(--blue)" };
const input: CSSProperties = {
  ...mono, fontSize: 11, padding: "5px 8px", background: "var(--panel)", color: "var(--ink)",
  border: "1px solid var(--border-2)", minWidth: 0,
};
const secret: CSSProperties = {
  ...mono, fontSize: 11, color: "var(--ink)", background: "var(--panel-2)", border: "1px solid var(--border)",
  padding: "8px 10px", wordBreak: "break-all", whiteSpace: "pre-wrap", userSelect: "all", margin: 0,
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
      <span style={{ ...note, minWidth: 110 }}>{label}</span>
      <span style={value}>{children}</span>
    </div>
  );
}

function dimmed(disabled: boolean): CSSProperties {
  return disabled ? { opacity: 0.5, cursor: "default" } : {};
}

// ── one renderer ─────────────────────────────────────────────────────────────

interface CardProps {
  r: Renderer;
  now: number;
  timeZone: string;
  busy: boolean;
  error: string;
  /** How the last change to this renderer went (enable, disable, rename). */
  status?: SaveState;
  onPatch: (body: { enabled?: boolean; name?: string }) => Promise<boolean>;
  onRemove: () => void;
  onTest: () => void;
}

function RendererCard({ r, now, timeZone, busy, error, status, onPatch, onRemove, onTest }: CardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(r.name);
  const [nameProblem, setNameProblem] = useState("");
  const chip = rendererStatus(r, now);
  const verdict = gpuVerdict(r);
  const gpus = r.compute?.gpus ?? [];
  const machine = computeLine(r);

  // The new name saves on Enter or when the field loses focus; Escape or
  // Cancel leaves the name as it was.
  async function saveName() {
    const problem = nameError(draft);
    setNameProblem(problem);
    if (problem) return;
    if (draft.trim() === r.name) { setEditing(false); return; }
    if (await onPatch({ name: draft.trim() })) setEditing(false);
  }

  function cancelRename() {
    setEditing(false);
    setNameProblem("");
  }

  // The probe verdict belongs to the configured GPU. With several GPUs
  // listed, the probe's name says which one that is.
  const verdictFor = (name: string) => gpus.length === 1 || !r.gpu?.name || r.gpu.name === name;

  return (
    <div data-testid={`renderer-card-${r.id}`} data-status={chip}
         style={{ border: "1px solid var(--border)", background: "var(--panel)", padding: "12px 14px",
                  display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        {editing ? (
          <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <input data-testid="renderer-rename-input" aria-label="Renderer name" value={draft}
                   maxLength={NAME_MAX_CHARS + 20} autoFocus style={input}
                   onChange={(e) => setDraft(e.target.value)}
                   onBlur={(e) => {
                     // Moving to Cancel, by mouse or by Tab, must not save the
                     // name Cancel is about to drop.
                     if ((e.relatedTarget as HTMLElement | null)?.dataset?.testid === "renderer-rename-cancel") return;
                     if (!busy) void saveName();
                   }}
                   onKeyDown={(e) => {
                     if (e.key === "Enter") void saveName();
                     if (e.key === "Escape") cancelRename();
                   }} />
            {/* mousedown is stopped so a click does not take focus from the
                field at all; Tab onto it is caught in the field's onBlur. */}
            <button type="button" data-testid="renderer-rename-cancel"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={cancelRename}
                    // Tab from the field lands here first. Tabbing on without
                    // pressing Cancel keeps the new name, as leaving the field
                    // any other way does.
                    onBlur={(e) => {
                      if ((e.relatedTarget as HTMLElement | null)?.dataset?.testid === "renderer-rename-input") return;
                      if (!busy) void saveName();
                    }}
                    style={{ ...button, color: "var(--dim)" }}>Cancel</button>
          </span>
        ) : (
          <span data-testid="renderer-name" style={{ ...mono, fontSize: 12, fontWeight: 700, color: "var(--ink)" }}>
            {r.name}
          </span>
        )}
        {r.builtin && <span style={note}>BUILT-IN</span>}
        {status?.state !== "error" && <SaveStatus status={status} testId="renderer-status" />}
        <span data-testid="renderer-chip" data-chip={chip}
              style={{ ...mono, fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", color: CHIP[chip].color,
                       border: `1px solid ${CHIP[chip].color}`, padding: "1px 6px", textTransform: "uppercase" }}>
          ● {CHIP[chip].label}
        </span>
      </div>
      {nameProblem && <div data-testid="renderer-name-error" style={{ ...note, color: "var(--red)" }}>{nameProblem}</div>}

      {chip === "busy" && (
        <Field label="Rendering">
          <span data-testid="renderer-current">{r.current_video_title || r.current_video_id || "a video"}</span>
        </Field>
      )}
      {!r.online && (
        <Field label="Last seen">
          <span data-testid="renderer-seen">{lastSeen(r.last_heartbeat_at, now)}</span>
        </Field>
      )}
      {r.host && <Field label="Host"><span data-testid="renderer-host">{r.host}</span></Field>}
      {machine && <Field label="Machine"><span data-testid="renderer-compute">{machine}</span></Field>}

      <Field label="GPU">
        <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {gpus.length === 0 && !r.gpu_configured && (
            <span data-testid="renderer-gpu">None — renders on the CPU</span>
          )}
          {gpus.length === 0 && r.gpu_configured && (
            <span data-testid="renderer-gpu" data-verdict={verdict.kind}>
              {r.gpu?.name || "Configured GPU"} — <Verdict kind={verdict.kind} text={verdict.text} />
            </span>
          )}
          {gpus.map((g) => {
            const v = verdictFor(g.name) ? verdict : { kind: "unused" as const, text: "not in use" };
            const mem = vramLine(g.memory_mb);
            return (
              <span key={g.uuid || g.name} data-testid="renderer-gpu" data-verdict={v.kind}>
                {g.name}{mem ? ` · ${mem}` : ""} — <Verdict kind={v.kind} text={v.text} />
              </span>
            );
          })}
        </span>
      </Field>

      {r.gpu && (
        <Field label="Chromium sees">
          <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span data-testid="renderer-device">{describeDevice(r.gpu.renderer, r.gpu_verified, r.gpu.name)}</span>
            {/* The raw string stays: it is the evidence the label is read from. */}
            <span data-testid="renderer-raw-device" style={{ ...note, wordBreak: "break-word" }}>
              {r.gpu.renderer || "no WebGL device"}
            </span>
            {r.gpu.at && <span style={note}>Last tested {formatDateTime(r.gpu.at, timeZone)}</span>}
          </span>
        </Field>
      )}

      {r.version && <Field label="Version">{r.version}</Field>}
      {!r.builtin && r.credential_expires_at && (
        <Field label="Credential expires">
          <span data-testid="renderer-credential">{formatDate(r.credential_expires_at, timeZone)}</span>
        </Field>
      )}
      {r.last_error && (
        <Field label="Last error">
          <span data-testid="renderer-last-error" style={{ color: "var(--red)" }}>{r.last_error}</span>
        </Field>
      )}

      <Help r={r} chip={chip} />

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" data-testid="renderer-toggle" disabled={busy}
                onClick={() => onPatch({ enabled: !r.enabled })} style={{ ...button, ...dimmed(busy) }}>
          {r.enabled ? "Disable" : "Enable"}
        </button>
        {!editing && (
          <button type="button" data-testid="renderer-rename" disabled={busy}
                  onClick={() => { setDraft(r.name); setNameProblem(""); setEditing(true); }}
                  style={{ ...button, ...dimmed(busy) }}>
            Rename
          </button>
        )}
        {/* Only with a GPU to test. Without one a test can only re-confirm the
            CPU, and choosing a GPU recreates the renderer, which tests as it
            starts. With one, a driver update or a failed render can change the
            answer while the container keeps running. */}
        {hasGpu(r) && (
          <button type="button" data-testid="renderer-test-gpu" disabled={busy || r.probe_pending}
                  onClick={onTest} style={{ ...button, ...dimmed(busy || r.probe_pending) }}>
            {r.probe_pending ? "Testing…" : "Test GPU"}
          </button>
        )}
        {!r.builtin && (
          <button type="button" data-testid="renderer-remove" disabled={busy} onClick={onRemove}
                  style={{ ...button, color: "var(--red)", ...dimmed(busy) }}>
            Remove
          </button>
        )}
        {r.probe_pending && (
          <span data-testid="renderer-probe-pending" style={note}>
            {r.state === "rendering"
              ? "Queued — the renderer runs the test once the current render finishes."
              : !r.online
                ? "Queued — the renderer runs the test once it is back online."
                : "The renderer runs the test on its next pass, usually within a minute."}
          </span>
        )}
      </div>
      {error && <div data-testid="renderer-error" role="alert" style={{ ...note, color: "var(--red)" }}>{error}</div>}
    </div>
  );
}

function Verdict({ kind, text }: { kind: string; text: string }) {
  const color = kind === "verified" ? "var(--green)" : kind === "failed" ? "var(--red)" : "var(--mute)";
  return <span data-testid="renderer-gpu-verdict" style={{ color }}>{text}</span>;
}

/** What to do about the state the card is in, on the host — the dashboard
 *  cannot do it. */
function Help({ r, chip }: { r: Renderer; chip: string }) {
  let text: ReactNode = null;
  if (chip === "credential_expired") {
    text = <>Its credential has expired, so it can no longer reach this install. Remove it, then add it
      again with a new token.</>;
  } else if (chip === "needs_upgrade" && !r.builtin) {
    text = <>It runs a different version from this install and takes no work until it is upgraded. On that
      host run <span style={code}>{REMOTE_UPGRADE_COMMAND}</span>.</>;
  } else if (r.builtin && !r.gpu_configured) {
    text = <>To render on an NVIDIA GPU, install the driver and the NVIDIA Container Toolkit, then run{" "}
      <span style={code}>{GPU_STEP_COMMAND}</span> on the host. See the GPU rendering guide in the docs.</>;
  } else if (r.builtin) {
    text = <>To use another GPU, or go back to the CPU, run <span style={code}>{GPU_STEP_COMMAND}</span> on
      the host.</>;
  }
  return text ? <div data-testid="renderer-help" style={note}>{text}</div> : null;
}

// ── Add renderer ─────────────────────────────────────────────────────────────

function CopyButton({ text, testId }: { text: string; testId: string }) {
  const [state, setState] = useState<"" | "copied" | "failed">("");
  async function copy() {
    try {
      // Absent on a plain-http page that is not localhost; the text is
      // selectable so it can still be copied by hand.
      if (!navigator.clipboard) throw new Error("no clipboard");
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }
  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <button type="button" data-testid={testId} onClick={copy} style={button}>Copy</button>
      {state === "copied" && <span data-testid={`${testId}-done`} style={{ ...note, color: "var(--green)" }}>Copied</span>}
      {state === "failed" && <span data-testid={`${testId}-failed`} style={note}>Copy failed — select the text and copy it by hand</span>}
    </span>
  );
}

function AddRendererDialog({ open, onClose, onAdded }: {
  open: boolean; onClose: () => void; onAdded: () => void;
}) {
  const { timeZone } = useTimeZone();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [enrollment, setEnrollment] = useState<RendererEnrollment | null>(null);

  // The token is shown once: closing forgets it, and reopening starts over.
  function close() {
    setName(""); setError(""); setEnrollment(null);
    onClose();
  }

  async function create() {
    const problem = nameError(name);
    if (problem) { setError(problem); return; }
    setSubmitting(true);
    try {
      const a = await request("/renderers/enrollments", jsonInit("POST", { name: name.trim() }));
      const body = a.body as RendererEnrollment | null;
      if (!a.ok) { setError(errorText(a)); return; }
      if (!body || typeof body.token !== "string" || typeof body.command !== "string") {
        setError("unexpected response");
        return;
      }
      setEnrollment(body);
      setError("");
      onAdded();
    } catch (e) {
      setError(`Could not create a token: ${(e as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && close()}>
      <DialogContent data-testid="add-renderer-dialog"
                     className="grid-cols-1 border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff]"
                     style={{ width: "90vw", maxWidth: 600 }}>
        <DialogHeader>
          <DialogTitle style={{ fontSize: 15, fontWeight: 600 }}>Add a renderer</DialogTitle>
        </DialogHeader>
        {!enrollment ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <label style={note} htmlFor="add-renderer-name">
              A name for the machine, as it will appear here (at most {NAME_MAX_CHARS} characters).
            </label>
            <input id="add-renderer-name" data-testid="add-renderer-name" value={name} autoFocus style={input}
                   placeholder="Studio PC" onChange={(e) => setName(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") create(); }} />
            <div data-testid="add-renderer-requirements" style={note}>
              The machine needs Docker, and for a GPU the NVIDIA driver and the NVIDIA Container Toolkit. It must
              be able to reach this install on the address set with{" "}
              <span style={code}>{RENDERERS_STEP_COMMAND}</span>.
            </div>
            {error && <div data-testid="add-renderer-error" style={{ ...note, color: "var(--red)" }}>{error}</div>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" onClick={close} style={{ ...button, color: "var(--dim)" }}>Cancel</button>
              <button type="button" data-testid="add-renderer-submit" disabled={submitting || !name.trim()}
                      onClick={create}
                      style={{ ...button, border: "1px solid var(--amber)", color: "var(--amber)",
                               ...dimmed(submitting || !name.trim()) }}>
                {submitting ? "Creating…" : "Create token"}
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div data-testid="add-renderer-once" style={{ ...note, color: "var(--amber)" }}>
              This token is shown only now. It is valid for 1 hour, single use
              {enrollment.expires_at ? ` (until ${formatDateTime(enrollment.expires_at, timeZone)})` : ""}.
            </div>
            <div style={note}>
              On the machine, get <span style={code}>{REMOTE_SCRIPT}</span> from this release&apos;s downloads
              (it is also in the release tarball&apos;s <span style={code}>scripts/</span> folder), then run:
            </div>
            <pre data-testid="add-renderer-command" style={secret}>{enrollment.command}</pre>
            <CopyButton text={enrollment.command} testId="copy-command" />
            <div data-testid="add-renderer-paste" style={note}>
              When it asks for the enrollment token, paste this one (it is not typed into the command, so it
              stays out of the machine&apos;s process list and shell history):
            </div>
            <pre data-testid="add-renderer-token" style={secret}>{enrollment.token}</pre>
            <CopyButton text={enrollment.token} testId="copy-token" />
            <div style={note}>
              The machine needs Docker, and for a GPU the NVIDIA Container Toolkit. It appears in this list once
              it has connected.
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button type="button" data-testid="add-renderer-done" onClick={close} style={button}>Done</button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── the panel ────────────────────────────────────────────────────────────────

export function RenderersPanel() {
  const { timeZone } = useTimeZone();
  const [list, setList] = useState<RenderersList | null>(null);
  const [error, setError] = useState("");
  const [cardErrors, setCardErrors] = useState<Record<string, string>>({});
  const statuses = useSaveStatus();
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [adding, setAdding] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  async function load(): Promise<RenderersList | null> {
    try {
      const a = await request("/renderers");
      if (!a.ok) throw new Error(errorText(a));
      if (!isRenderersList(a.body)) throw new Error("unexpected response");
      if (!alive.current) return null;
      setList(a.body);
      setError("");
      return a.body;
    } catch (e) {
      if (alive.current) setError(`Could not read the renderers: ${(e as Error).message}`);
      return null;
    }
  }

  // One timer: fast while any GPU test is outstanding, slow otherwise.
  function schedule(l: RenderersList | null) {
    if (timer.current) clearTimeout(timer.current);
    if (!alive.current) return;
    timer.current = setTimeout(async () => schedule(await load()),
                               anyProbePending(l) ? PROBE_POLL_MS : POLL_MS);
  }

  async function reload() {
    schedule(await load());
  }

  useEffect(() => {
    alive.current = true;
    load().then(schedule);
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function act(id: string, path: string, init: RequestInit): Promise<boolean> {
    setBusy((b) => ({ ...b, [id]: true }));
    try {
      const a = await request(path, init);
      if (!a.ok) {
        setCardErrors((m) => ({ ...m, [id]: errorText(a) }));
        return false;
      }
      setCardErrors((m) => ({ ...m, [id]: "" }));
      await reload();
      return true;
    } catch (e) {
      setCardErrors((m) => ({ ...m, [id]: (e as Error).message }));
      return false;
    } finally {
      setBusy((b) => ({ ...b, [id]: false }));
    }
  }

  const path = (r: Renderer) => `/renderers/${encodeURIComponent(r.id)}`;

  /** Enable, disable or rename: saved at once, with "Saving…" then "✓ Saved"
   *  beside the name. A refusal shows in the card's own error line. */
  async function patch(r: Renderer, body: { enabled?: boolean; name?: string }) {
    return statuses.run(r.id, async () =>
      (await act(r.id, path(r), jsonInit("PATCH", body))) ? null : "refused");
  }

  function remove(r: Renderer) {
    if (!window.confirm(`Remove the renderer "${r.name}"? It stops getting work at once, and a render it `
                        + "is running goes back in the queue. To use that machine again, add it with a new token.")) {
      return;
    }
    act(r.id, path(r), { method: "DELETE" });
  }

  const now = Date.now();
  const renderers = [...(list?.renderers ?? [])].sort((a, b) => Number(b.builtin) - Number(a.builtin));
  const remoteOn = !!list?.remote_enabled;

  return (
    <div data-testid="renderers-panel">
      <SectionLabel label="Renderers" count={list ? `${renderers.length}` : undefined} />
      {error && <div data-testid="renderers-error" style={{ ...note, color: "var(--red)", marginBottom: 8 }}>{error}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
        {renderers.map((r) => (
          <RendererCard key={r.id} r={r} now={now} timeZone={timeZone} busy={!!busy[r.id]}
                        error={cardErrors[r.id] ?? ""}
                        status={statuses.get(r.id)}
                        onPatch={(body) => patch(r, body)}
                        onRemove={() => remove(r)}
                        onTest={() => act(r.id, `${path(r)}/gpu-test`, { method: "POST" })} />
        ))}
      </div>

      {list && (
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button type="button" data-testid="renderers-add" disabled={!remoteOn} onClick={() => setAdding(true)}
                  style={{ ...button, ...dimmed(!remoteOn) }}>
            Add renderer
          </button>
          {remoteOn ? (
            <span data-testid="renderers-gateway" style={note}>
              Remote renderers reach this install at <span style={code}>{list.gateway_address}</span>.
            </span>
          ) : (
            <span data-testid="renderers-add-hint" style={note}>
              Turn on remote renderers first: <span style={code}>{RENDERERS_STEP_COMMAND}</span>
            </span>
          )}
        </div>
      )}

      <AddRendererDialog open={adding} onClose={() => setAdding(false)} onAdded={reload} />
    </div>
  );
}
