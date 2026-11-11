"use client";

import type { Agent } from "@/lib/types";
import { AGENT_EFFORTS, effortOptionLabel, isUsable } from "@/lib/agents";

const mono = { fontFamily: "var(--mono)" } as const;

export const selectStyle = {
  ...mono, fontSize: 11, padding: "7px 8px", width: "100%",
  background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--border-2)",
} as const;

/** A captioned control. A <label>, so the caption is the control's accessible
 *  name. The note sits outside the label, or it would become part of that name. */
export function Field({ label, note, children }: { label: string; note?: string; children: React.ReactNode }) {
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

/**
 * Agent, Model and Effort selects, as three grid children (a fragment).
 * "" for the agent is Automatic: no agent_id goes out and the API deals one.
 * `model` is null until touched; the resolved model (what to send) is
 * exported by resolvePickedModel so the caller and the select agree.
 */
export function resolvePickedModel(picked: Agent | null, model: string | null): string {
  if (!isUsable(picked)) return "";
  return model !== null && picked.models.includes(model) ? model : picked.models[0];
}

export function AgentPickers({
  agents, agentsFailed, agentId, model, effort, onAgent, onModel, onEffort, testIdPrefix, automatic,
}: {
  /** undefined until /agents answers. */
  agents: Agent[] | undefined;
  agentsFailed: boolean;
  agentId: string;
  model: string | null;
  effort: string;
  onAgent: (id: string) => void;
  onModel: (model: string) => void;
  onEffort: (effort: string) => void;
  /** Test ids are `${prefix}-agent`, `-model`, `-effort`. */
  testIdPrefix: string;
  /** What the three blank options read as while no agent is picked, for a page
   *  whose "Automatic" resolves to something it can name (the New Video page:
   *  its domain's agent). Omitted, they read as the weighted deal. */
  automatic?: { agent: string; model: string; effort: string };
}) {
  const liveAgents = (agents ?? []).filter((a) => !a.archived_at);
  const picked = liveAgents.find((a) => a.id === agentId) ?? null;
  const resolved = resolvePickedModel(picked, model);
  const agentNote = agentsFailed
    ? "Agent list not loaded — the video will be dealt an agent automatically."
    : agents !== undefined && liveAgents.length === 0
      ? "No agents installed. Install one on the host with onboard.py --install-agent."
      : undefined;

  return (
    <>
      <Field label="Agent" note={agentNote}>
        <select
          data-testid={`${testIdPrefix}-agent`}
          value={agentId}
          disabled={liveAgents.length === 0}
          onChange={(e) => onAgent(e.target.value)}
          style={selectStyle}
        >
          <option value="">{automatic?.agent ?? "Automatic (dealt by weight)"}</option>
          {liveAgents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </Field>

      <Field label="Model">
        <select
          data-testid={`${testIdPrefix}-model`}
          value={resolved}
          disabled={!isUsable(picked)}
          onChange={(e) => onModel(e.target.value)}
          style={selectStyle}
        >
          {isUsable(picked)
            ? picked.models.map((m, i) => (
                <option key={m} value={m}>{i === 0 ? `${m} (default)` : m}</option>
              ))
            : <option value="">{automatic?.model ?? "Agent default"}</option>}
        </select>
      </Field>

      <Field label="Effort">
        <select
          data-testid={`${testIdPrefix}-effort`}
          value={effort}
          onChange={(e) => onEffort(e.target.value)}
          style={selectStyle}
        >
          <option value="">{picked ? effortOptionLabel(picked) : automatic?.effort ?? effortOptionLabel(null)}</option>
          {AGENT_EFFORTS.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
      </Field>
    </>
  );
}
