import type { Agent, Mascot, Project, ScriptProfile, Voice, VisualStyleInfo } from "@/lib/types";
import { isUsable } from "@/lib/agents";
import { styleLabel } from "@/lib/visualStyles";

/**
 * A domain's defaults, as the Topics page edits them: on a domain's row (each
 * change is saved at once) and in the add-domain form (sent on submit). Every
 * value is a string and "" is a real choice in each: no style preference, the
 * install's voice and mascot, no profile, Automatic for the agent, the agent's
 * own model and effort.
 */
export interface DomainDefaultValues {
  default_visual_style: string;
  default_voice_id: string;
  default_script_profile_id: string;
  default_mascot_id: string;
  default_agent_id: string;
  default_agent_model: string;
  default_agent_effort: string;
}

export const NO_DOMAIN_DEFAULTS: DomainDefaultValues = {
  default_visual_style: "",
  default_voice_id: "",
  default_script_profile_id: "",
  default_mascot_id: "",
  default_agent_id: "",
  default_agent_model: "",
  default_agent_effort: "",
};

/** A domain's stored defaults. POST /projects replaces the whole row, so this
 *  is also the list of defaults every save has to send back. */
export function domainDefaults(p: Project): DomainDefaultValues {
  return {
    default_visual_style: p.default_visual_style ?? "",
    default_voice_id: p.default_voice_id ?? "",
    default_script_profile_id: p.default_script_profile_id ?? "",
    default_mascot_id: p.default_mascot_id ?? "",
    default_agent_id: p.default_agent_id ?? "",
    default_agent_model: p.default_agent_model ?? "",
    default_agent_effort: p.default_agent_effort ?? "",
  };
}

/** What the pickers choose from. `agents` is undefined until GET /agents
 *  answers; `styles` is null until the style list loads. */
export interface DomainLists {
  styles: VisualStyleInfo[] | null;
  voices: Voice[];
  profiles: ScriptProfile[];
  mascots: Pick<Mascot, "id" | "name" | "pickable">[];
  agents: Agent[] | undefined;
}

export interface DomainChip {
  key: "style" | "voice" | "profile" | "mascot" | "agent";
  label: string;
  value: string;
}

/**
 * What a collapsed domain row says about its defaults: one chip per default
 * the domain sets, none for one it leaves alone. A value the lists no longer
 * hold still gets its chip, named the way its picker names it, so a domain
 * never reads as "install defaults" while it holds something stale.
 */
export function domainChips(v: DomainDefaultValues, lists: DomainLists): DomainChip[] {
  const chips: DomainChip[] = [];
  if (v.default_visual_style) {
    chips.push({ key: "style", label: "Style", value: styleLabel(v.default_visual_style, lists.styles) });
  }
  if (v.default_voice_id) {
    const voice = lists.voices.find((x) => x.voice_id === v.default_voice_id);
    chips.push({ key: "voice", label: "Voice", value: voice ? voice.name : `${v.default_voice_id} (removed)` });
  }
  if (v.default_script_profile_id) {
    const profile = lists.profiles.find((p) => p.id === v.default_script_profile_id);
    chips.push({
      key: "profile", label: "Profile",
      value: profile?.status === "READY" ? profile.name
        : profile ? `${profile.name} (unavailable)` : "Unavailable profile",
    });
  }
  if (v.default_mascot_id) {
    const mascot = lists.mascots.find((m) => m.id === v.default_mascot_id);
    chips.push({
      key: "mascot", label: "Mascot",
      value: v.default_mascot_id === "none" ? "None"
        : mascot?.pickable ? mascot.name
        : mascot ? `${mascot.name} (unavailable)` : "Unavailable mascot",
    });
  }
  if (v.default_agent_id || v.default_agent_effort) {
    const parts = [v.default_agent_id ? domainAgentLabel(lists.agents, v.default_agent_id) : "Automatic"];
    if (v.default_agent_id && v.default_agent_model) parts.push(v.default_agent_model);
    if (v.default_agent_effort) parts.push(v.default_agent_effort);
    chips.push({ key: "agent", label: "Agent", value: parts.join(" · ") });
  }
  return chips;
}

export interface DomainOption {
  value: string;
  label: string;
  disabled: boolean;
}

/** The live agent a domain names, or null: Automatic, an agent uninstalled
 *  since, or a list that has not loaded. */
export function domainAgent(agents: Agent[] | undefined, agentId: string): Agent | null {
  if (!agentId) return null;
  return (agents ?? []).find((a) => a.id === agentId && !a.archived_at) ?? null;
}

/** How a domain's agent reads. The API hands such a domain's new videos to the
 *  weighted deal while its agent is not live, so the label says why. Before
 *  the list loads only the id is known, and nothing is claimed about it. */
function domainAgentLabel(agents: Agent[] | undefined, agentId: string): string {
  if (agents === undefined) return agentId;
  const agent = agents.find((a) => a.id === agentId);
  if (!agent) return `${agentId} (not installed)`;
  return agent.archived_at ? `${agent.name} (uninstalled)` : agent.name;
}

/** The agent picker: Automatic, then every live agent. An agent the domain
 *  holds that is not live stays listed and selected, but cannot be picked
 *  again: only a live agent can be handed new work. */
export function domainAgentOptions(agents: Agent[] | undefined, value: string): DomainOption[] {
  const out: DomainOption[] = [{ value: "", label: "Automatic (dealt by weight)", disabled: false }];
  const live = (agents ?? []).filter((a) => !a.archived_at);
  if (value && !live.some((a) => a.id === value)) {
    out.push({ value, label: domainAgentLabel(agents, value), disabled: true });
  }
  for (const a of live) out.push({ value: a.id, label: a.name, disabled: false });
  return out;
}

/** The model picker for a domain's agent. "" is a real choice here, unlike on
 *  a video: it means the agent's own default at the time each video is filed,
 *  so the domain follows a later change of that default. A model the agent no
 *  longer offers stays listed and selected; the API then starts new videos on
 *  the agent's default. */
export function domainModelOptions(agent: Agent | null, value: string): DomainOption[] {
  const models = isUsable(agent) ? agent.models : [];
  const out: DomainOption[] = [{
    value: "", label: models.length ? `${models[0]} (agent default)` : "Agent default", disabled: false,
  }];
  if (value && !models.includes(value)) {
    out.push({ value, label: `${value} (unavailable)`, disabled: true });
  }
  for (const m of models) out.push({ value: m, label: m, disabled: false });
  return out;
}
