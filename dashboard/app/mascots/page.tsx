"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { Agent, GpuStatus, Mascot, MascotSheets, MascotStatus } from "@/lib/types";
import { AgentPickers, resolvePickedModel } from "@/components/AgentPickers";
import { ProfilesNav } from "@/components/ProfilesNav";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDate } from "@/lib/datetime";
import { MASCOT_SETTINGS_HREF, mascotGate, mascotGateNote, mascotSheetUrl } from "@/lib/mascots";

// The mascot library (Profiles tab, second page). A mascot is drawn by an
// agent session on the next scheduled poll and approved here by a person.

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const STATUS_ACCENT: Record<MascotStatus, string> = {
  PENDING:   "var(--dim)",
  BUILDING:  "var(--amber)",
  IN_REVIEW: "var(--amber)",
  READY:     "var(--green)",
  FAILED:    "var(--red)",
};

const STATUS_NOTE: Record<MascotStatus, string> = {
  PENDING:   "Queued — the next scheduled poll draws it.",
  BUILDING:  "Being drawn now by an agent session.",
  IN_REVIEW: "Drawn. Look at the sheets, then approve it or ask for changes.",
  READY:     "Selectable on any topic awaiting approval.",
  FAILED:    "Could not be drawn. Ask for changes to try again.",
};

const SHEET_NAMES = ["turn", "feels", "act"] as const;
const SHEET_TITLES: Record<(typeof SHEET_NAMES)[number], string> = {
  turn: "Turnaround", feels: "Feelings", act: "Actions",
};

const mono = { fontFamily: "var(--mono)" } as const;

const inputStyle = {
  ...mono, fontSize: 12, width: "100%", padding: "8px 10px",
  background: "var(--panel)", border: "1px solid var(--border-2)", color: "var(--ink)",
} as const;

function btn(color: string, enabled = true): React.CSSProperties {
  return {
    ...mono, fontSize: 10, padding: "6px 12px", cursor: enabled ? "pointer" : "not-allowed",
    background: "transparent", border: `1px solid ${color}`, color,
    textTransform: "uppercase", letterSpacing: "0.1em", opacity: enabled ? 1 : 0.5,
  };
}

export default function MascotsPage() {
  const { timeZone } = useTimeZone();
  const [mascots, setMascots] = useState<Mascot[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Mascot | null>(null);
  const [gpu, setGpu] = useState<GpuStatus | null>(null);
  const [agents, setAgents] = useState<Agent[] | undefined>(undefined);
  const [agentsFailed, setAgentsFailed] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [agentId, setAgentId] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [effort, setEffort] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [comment, setComment] = useState("");
  const [varName, setVarName] = useState("");
  const [varDescription, setVarDescription] = useState("");
  const [detailError, setDetailError] = useState("");

  const loadDetail = useCallback((id: string) => {
    apiFetch(`/mascots/${id}`)
      .then((r) => r.json())
      .then((full: Mascot) => { if (full && typeof full.id === "string") setDetail(full); })
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    apiFetch("/mascots")
      .then((r) => r.json())
      .then((data: Mascot[]) => setMascots(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5_000);
    return () => clearInterval(id);
  }, [load]);

  // The open mascot is re-read on the same beat: a sheet appears (or a status
  // changes) while its pane is open.
  useEffect(() => {
    if (!selectedId) return;
    loadDetail(selectedId);
    const id = setInterval(() => loadDetail(selectedId), 5_000);
    return () => clearInterval(id);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    apiFetch("/agents")
      .then((r) => r.json())
      .then((data: Agent[]) => { if (Array.isArray(data)) setAgents(data); else setAgentsFailed(true); })
      .catch(() => setAgentsFailed(true));
    apiFetch("/render/gpu")
      .then((r) => (r.ok ? r.json() : null))
      .then((g) => setGpu(g && typeof g.status === "string" ? (g as GpuStatus) : null))
      .catch(() => {});
  }, []);

  function agentPicks(): Record<string, string> {
    const live = (agents ?? []).filter((a) => !a.archived_at);
    const picked = live.find((a) => a.id === agentId) ?? null;
    const resolved = resolvePickedModel(picked, model);
    return {
      ...(agentId ? { agent_id: agentId } : {}),
      ...(agentId && resolved ? { agent_model: resolved } : {}),
      ...(effort ? { agent_effort: effort } : {}),
    };
  }

  async function post(path: string, body: Record<string, unknown> | undefined) {
    const r = await apiFetch(path, {
      method: "POST",
      ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
    });
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, data };
  }

  async function create(surprise: boolean) {
    if (!surprise && (!name.trim() || !description.trim())) {
      setError("A name and a description are required (or press Surprise me).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = surprise
        ? { surprise: true, ...agentPicks() }
        : { name: name.trim(), description: description.trim(), ...agentPicks() };
      const { ok, data } = await post("/mascots", body);
      if (!ok) { setError(data?.error ?? "Could not create the mascot."); return; }
      setName("");
      setDescription("");
      load();
      if (data?.id) { setSelectedId(data.id); setDetail(data as Mascot); }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the mascot.");
    } finally {
      setBusy(false);
    }
  }

  function open(m: Mascot) {
    setSelectedId(m.id);
    setDetail(m);
    setComment("");
    setDetailError("");
    setVarName("");
    setVarDescription("");
  }

  async function act(fn: () => Promise<{ ok: boolean; data: { error?: string } & Partial<Mascot> }>) {
    setBusy(true);
    setDetailError("");
    try {
      const { ok, data } = await fn();
      if (!ok) { setDetailError(data?.error ?? "That did not work."); return; }
      if (data?.id) setDetail(data as Mascot);
      setComment("");
      load();
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }

  const approve = (m: Mascot) => act(() => post(`/mascots/${m.id}/approve`, undefined));
  const requestChanges = (m: Mascot) =>
    act(() => post(`/mascots/${m.id}/request-changes`, { comment: comment.trim() }));
  const askVariation = (m: Mascot) => act(async () => {
    const res = await post("/mascots", {
      name: varName.trim(), description: varDescription.trim(), based_on: m.id,
    });
    if (res.ok && res.data?.id) { setSelectedId(res.data.id); }
    return res;
  });

  // Busy like every other action: an archive and an approve, request or variation
  // in flight together race at the API (which refuses the loser), so the page
  // offers only one at a time.
  async function archive(m: Mascot) {
    if (busy) return;
    if (!confirm(`Archive "${m.name}"? Videos already using it keep it; it can no longer be picked.`)) return;
    setDetailError("");
    setBusy(true);
    try {
      const r = await apiFetch(`/mascots/${m.id}`, { method: "DELETE" });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        setDetailError(data?.error ?? "Could not archive the mascot.");
        return;
      }
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Could not archive the mascot.");
      return;
    } finally {
      setBusy(false);
    }
    if (selectedId === m.id) { setSelectedId(null); setDetail(null); }
    load();
  }

  const gate = mascotGate(gpu);
  const gateNote = mascotGateNote(gate);
  const selected = detail && detail.id === selectedId ? detail : null;

  return (
    <>
      <ProfilesNav />
      <SectionLabel
        label="Mascots"
        count={`${mascots.length} mascot${mascots.length !== 1 ? "s" : ""}`}
      />

      {gate !== "ok" && gate !== "loading" && (
        <div data-testid="mascot-gpu-note" style={{ ...mono, fontSize: 10, color: "var(--amber)", marginBottom: 12, lineHeight: 1.5 }}>
          {gateNote} — mascots are drawn in a video on the GPU only, so none can be chosen for a video until it works.{" "}
          <Link href={MASCOT_SETTINGS_HREF} style={{ color: "var(--amber)" }}>Test the GPU in Settings → Rendering</Link>
        </div>
      )}

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* minWidth: 0 keeps the 340px basis when a name has no break opportunity. */}
        <div style={{ flex: "0 0 340px", minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ border: "1px solid var(--border)", padding: "14px" }}>
            <div style={{ ...mono, fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--dim)", marginBottom: 10 }}>
              New mascot
            </div>
            <input
              data-testid="mascot-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name"
              maxLength={60}
              style={{ ...inputStyle, marginBottom: 8 }}
            />
            <textarea
              data-testid="mascot-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the character: what it is, how it looks, how it carries itself"
              rows={4}
              maxLength={2000}
              style={{ ...inputStyle, fontSize: 11, resize: "vertical" }}
            />
            <div style={{ display: "grid", gap: 10, margin: "10px 0" }}>
              <AgentPickers
                agents={agents}
                agentsFailed={agentsFailed}
                agentId={agentId}
                model={model}
                effort={effort}
                onAgent={(id) => { setAgentId(id); setModel(null); }}
                onModel={setModel}
                onEffort={setEffort}
                testIdPrefix="mascot"
              />
            </div>
            <div style={{ ...mono, fontSize: 10, color: "var(--dim)", margin: "8px 0", lineHeight: 1.5 }}>
              An agent draws it on the next scheduled poll, then it waits here for your review.
            </div>
            {error && (
              <div data-testid="mascot-error" style={{ ...mono, fontSize: 10, color: "var(--red)", marginBottom: 8 }}>{error}</div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button data-testid="mascot-create" onClick={() => create(false)} disabled={busy}
                      style={{ ...btn("var(--amber)", !busy), flex: 1 }}>
                Create
              </button>
              <button data-testid="mascot-surprise" onClick={() => create(true)} disabled={busy}
                      title="The agent invents a character; no name or description needed"
                      style={{ ...btn("var(--dim)", !busy), flex: 1 }}>
                Surprise me
              </button>
            </div>
          </div>

          {mascots.length === 0 ? (
            <div style={{ ...mono, fontSize: 10, letterSpacing: "0.24em", color: "var(--mute)", textTransform: "uppercase", padding: "16px 0" }}>
              — No mascots yet —
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {mascots.map((m) => {
                const isSelected = selectedId === m.id;
                return (
                  <div
                    key={m.id}
                    data-testid={`mascot-row-${m.id}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => open(m)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(m); } }}
                    style={{
                      padding: "12px 14px", cursor: "pointer",
                      background: isSelected ? "var(--panel)" : "transparent",
                      border: `1px solid ${isSelected ? "var(--border-2)" : "var(--border)"}`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span style={{ ...mono, fontSize: 12, fontWeight: 700, minWidth: 0, overflowWrap: "anywhere", color: isSelected ? "var(--amber)" : "var(--ink)" }}>
                        {m.name}
                      </span>
                      <span style={{
                        ...mono, fontSize: 9, letterSpacing: "0.12em", padding: "2px 6px",
                        border: `1px solid ${STATUS_ACCENT[m.status]}`, color: STATUS_ACCENT[m.status], textTransform: "uppercase",
                      }}>
                        {m.status}
                      </span>
                    </div>
                    <div style={{ ...mono, fontSize: 10, color: "var(--dim)", marginTop: 4 }}>
                      {m.builtin ? "Built in" : formatDate(m.created_at, timeZone)}
                      {m.approved_version > 0 && ` · v${m.approved_version}`}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!selected ? (
            <div style={{ ...mono, fontSize: 10, letterSpacing: "0.24em", color: "var(--mute)", textTransform: "uppercase", padding: "24px 0" }}>
              — Select a mascot —
            </div>
          ) : (
            <MascotDetail
              m={selected}
              busy={busy}
              error={detailError}
              comment={comment}
              setComment={setComment}
              varName={varName}
              setVarName={setVarName}
              varDescription={varDescription}
              setVarDescription={setVarDescription}
              onApprove={() => approve(selected)}
              onRequestChanges={() => requestChanges(selected)}
              onVariation={() => askVariation(selected)}
              onArchive={() => archive(selected)}
              timeZone={timeZone}
            />
          )}
        </div>
      </div>
    </>
  );
}

function SheetStrip({ which, sheets }: { which: "approved" | "draft"; sheets: MascotSheets | null }) {
  if (!sheets || Object.keys(sheets).length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {SHEET_NAMES.map((n) => sheets[n] && (
        <figure key={n} style={{ margin: 0 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            data-testid={`mascot-sheet-${which}-${n}`}
            src={mascotSheetUrl(sheets[n] as string)}
            alt={`${SHEET_TITLES[n]} sheet (${which})`}
            style={{ width: "100%", maxWidth: 720, border: "1px solid var(--border)", background: "#fff", display: "block" }}
          />
          <figcaption style={{ ...mono, fontSize: 10, color: "var(--dim)", marginTop: 4 }}>{SHEET_TITLES[n]}</figcaption>
        </figure>
      ))}
    </div>
  );
}

function MascotDetail(p: {
  m: Mascot; busy: boolean; error: string; timeZone: string;
  comment: string; setComment: (v: string) => void;
  varName: string; setVarName: (v: string) => void;
  varDescription: string; setVarDescription: (v: string) => void;
  onApprove: () => void; onRequestChanges: () => void; onVariation: () => void; onArchive: () => void;
}) {
  const { m, busy } = p;
  const canRequest = !m.builtin && (m.status === "IN_REVIEW" || m.status === "READY" || m.status === "FAILED");
  const agentLine = [m.agent_id, m.agent_model, m.agent_effort].filter(Boolean).join(" · ");
  return (
    <div data-testid="mascot-detail" style={{ border: "1px solid var(--border)", padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <span style={{ ...mono, fontSize: 14, fontWeight: 700, color: "var(--amber)" }}>{m.name}</span>
        {!m.archived && (
          <button data-testid="mascot-archive" onClick={p.onArchive} disabled={busy}
                  style={btn("var(--red)", !busy)}>Archive</button>
        )}
      </div>

      <div style={{ ...mono, fontSize: 10, color: "var(--dim)", marginTop: 8, lineHeight: 1.6 }}>
        {m.archived ? "Archived — it can no longer be picked." : STATUS_NOTE[m.status]}
        {m.error && <div data-testid="mascot-detail-error" style={{ color: "var(--red)", marginTop: 4 }}>{m.error}</div>}
      </div>
      {m.description && (
        <div style={{ ...mono, fontSize: 11, color: "var(--mute)", marginTop: 10, whiteSpace: "pre-wrap" }}>{m.description}</div>
      )}
      {agentLine && (
        <div data-testid="mascot-built-by" style={{ ...mono, fontSize: 10, color: "var(--dim)", marginTop: 8 }}>
          Drawn by {agentLine}
        </div>
      )}
      {p.error && <div data-testid="mascot-action-error" style={{ ...mono, fontSize: 10, color: "var(--red)", marginTop: 10 }}>{p.error}</div>}

      {!m.archived && (
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
          {m.status === "IN_REVIEW" && (
            <div>
              <button data-testid="mascot-approve" onClick={p.onApprove} disabled={busy}
                      style={btn("var(--green)", !busy)}>
                Approve
              </button>
            </div>
          )}
          {canRequest && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
              <textarea
                data-testid="mascot-comment"
                value={p.comment}
                onChange={(e) => p.setComment(e.target.value)}
                placeholder="What should change?"
                aria-label="Requested changes"
                rows={3}
                maxLength={2000}
                style={{ ...inputStyle, fontSize: 11, resize: "vertical" }}
              />
              <div>
                <button data-testid="mascot-request-changes" onClick={p.onRequestChanges}
                        disabled={busy || !p.comment.trim()}
                        style={btn("var(--amber)", !busy && !!p.comment.trim())}>
                  Request changes
                </button>
              </div>
            </div>
          )}
          {m.builtin && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 520 }}>
              <div style={{ ...mono, fontSize: 10, color: "var(--dim)", lineHeight: 1.5 }}>
                A built-in mascot cannot be edited. Ask for a variation: a new mascot drawn from this one.
              </div>
              <input data-testid="mascot-variation-name" value={p.varName}
                     onChange={(e) => p.setVarName(e.target.value)} placeholder="Name of the variation"
                     aria-label="Variation name" maxLength={60} style={inputStyle} />
              <textarea data-testid="mascot-variation-description" value={p.varDescription}
                        onChange={(e) => p.setVarDescription(e.target.value)} rows={3}
                        placeholder="How should it differ?" aria-label="Variation description"
                        maxLength={2000} style={{ ...inputStyle, fontSize: 11, resize: "vertical" }} />
              <div>
                <button data-testid="mascot-variation" onClick={p.onVariation}
                        disabled={busy || !p.varName.trim() || !p.varDescription.trim()}
                        style={btn("var(--amber)", !busy && !!p.varName.trim() && !!p.varDescription.trim())}>
                  Ask for a variation
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {m.sheets?.draft && Object.keys(m.sheets?.draft).length > 0 && (
        <Block title={`Draft${m.draft_version ? ` (version ${m.draft_version})` : ""} — awaiting your review`}>
          {m.change_request && (
            <div style={{ ...mono, fontSize: 10, color: "var(--dim)", marginBottom: 8 }}>Asked for: {m.change_request}</div>
          )}
          <SheetStrip which="draft" sheets={m.sheets?.draft} />
        </Block>
      )}
      {m.sheets?.approved && Object.keys(m.sheets?.approved).length > 0 && (
        <Block title={`Approved${m.approved_version ? ` (version ${m.approved_version})` : ""}`}>
          <SheetStrip which="approved" sheets={m.sheets?.approved} />
        </Block>
      )}

      {m.versions && m.versions.length > 0 && (
        <Block title="Version history">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[...m.versions].sort((a, b) => b.version - a.version).map((v) => (
              <div key={v.version} data-testid={`mascot-version-${v.version}`}
                   style={{ ...mono, fontSize: 11, color: "var(--mute)", overflowWrap: "anywhere" }}>
                <b style={{ color: "var(--ink)" }}>v{v.version}</b>
                {" · "}{v.approved_at ? "approved" : "not approved"}
                {" · "}{formatDate(v.created_at, p.timeZone)}
                {v.change_request && <div style={{ color: "var(--dim)" }}>{v.change_request}</div>}
              </div>
            ))}
          </div>
        </Block>
      )}
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 18 }}>
      <div style={{ ...mono, fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--dim)", marginBottom: 8 }}>
        {title}
      </div>
      {children}
    </div>
  );
}
