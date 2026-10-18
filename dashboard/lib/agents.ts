import type { Agent, Video } from "@/lib/types";

/** The agent a video runs under: its pinned agent_id, else (unpinned) the live
 *  default, else the first live agent. A pinned id that GET /agents cannot
 *  resolve is deliberately NOT replaced by the default — the API checks a
 *  video's model against that video's own agent, so offering another agent's
 *  list would only produce a rejected approve. */
export function effectiveAgent(video: Pick<Video, "agent_id">, agents: Agent[]): Agent | null {
  if (video.agent_id) return agents.find((a) => a.id === video.agent_id) ?? null;
  const live = agents.filter((a) => !a.archived_at);
  return live.find((a) => a.is_default) ?? live[0] ?? null;
}

/** Whether a model can be picked for this agent at all. An uninstalled agent
 *  (archived_at set), or one with no models, gets a disabled picker and an
 *  empty agent_model. */
export function isUsable(agent: Agent | null): agent is Agent {
  return !!agent && !agent.archived_at && agent.models.length > 0;
}

/** Read-only agent name. Falls back to the raw id (like a deleted script
 *  profile does) so an unresolvable pin still shows something traceable. */
export function agentLabel(video: Pick<Video, "agent_id">, agent: Agent | null): string {
  if (agent) return agent.archived_at ? `${agent.name} (uninstalled)` : agent.name;
  return video.agent_id || "Default agent";
}

/** Read-only model. A blank stored model means the agent's own default, which
 *  is spelled out rather than left blank. Pages that do not fetch agents
 *  (Library, Projects) get the generic wording. */
export function modelLabel(video: Pick<Video, "agent_model">, agent: Agent | null): string {
  if (video.agent_model) return video.agent_model;
  const fallback = agent?.models[0];
  return fallback ? `${fallback} (default)` : "Agent default";
}

/** The picker's starting value: the stored model if the agent still offers it,
 *  else the agent's own default (models[0]). Recomputed on every render rather
 *  than captured in state, because the agent list arrives after first paint. */
export function initialModel(video: Pick<Video, "agent_model">, agent: Agent | null): string {
  const models = agent?.models ?? [];
  const stored = video.agent_model ?? "";
  return models.includes(stored) ? stored : models[0] ?? "";
}

/** The effort levels the agent CLI accepts, as it documents them in its own
 *  --help. A closed set fixed by the CLI, unlike `models`, which is discovered
 *  per install — which is why this list is a constant here rather than
 *  something read off the agent row.
 *  Keep in sync: renderer/api/pipeline.py and mcp/server.py's AGENT_EFFORTS,
 *  and scripts/agent_adapters.py's ClaudeAdapter.EFFORTS. */
export const AGENT_EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;

/** Read-only effort. A blank stored effort means the agent's own level, which
 *  is spelled out rather than left blank — the same bargain modelLabel makes.
 *  Pages that do not fetch agents (Library, Projects) get the generic wording. */
export function effortLabel(video: Pick<Video, "agent_effort">, agent: Agent | null): string {
  if (video.agent_effort) return video.agent_effort;
  const fallback = agent?.effort;
  return fallback ? `${fallback} (default)` : "Agent default";
}

/** The picker's starting value, which is simply the column's own value.
 *
 *  "" is a REAL choice here, not an absence — it is what `videos.agent_effort`
 *  stores to mean "use this video's agent's level", exactly as "" on
 *  script_profile_id means the generic style. So the picker always carries a
 *  blank option (see effortOptionLabel) and an untouched approval submits "".
 *
 *  This is deliberately NOT initialModel's shape. That one resolves to the
 *  agent's models[0] and the approval pins it, which is right for a model: the
 *  list is per-install, and pinning records which model actually made a video.
 *  Resolving an effort the same way means *guessing* whenever the agent row is
 *  unavailable — on Projects and Library, which never fetch /agents at all, and
 *  on Pipeline before /agents answers. A guess submitted as an explicit value
 *  silently overrides an agent configured for anything but the guess. */
export function initialEffort(video: Pick<Video, "agent_effort">): string {
  const stored = video.agent_effort ?? "";
  return (AGENT_EFFORTS as readonly string[]).includes(stored) ? stored : "";
}

/** Label for the picker's blank option. Names the level that blank will
 *  actually produce when the agent is known, and says only what it knows when
 *  it is not — the one thing it must never do is show a level it guessed. */
export function effortOptionLabel(agent: Agent | null): string {
  const effort = agent?.effort ?? "";
  return (AGENT_EFFORTS as readonly string[]).includes(effort)
    ? `${effort} (agent default)`
    : "Agent default";
}

// ── Changing the agent at a human checkpoint (TMDEV-110) ────────────────────

/** A picker's three choices. null = untouched, the idiom every per-video
 *  picker uses: the shown value tracks the video (and the agent list, which
 *  can arrive after first paint) until the human actually picks. */
export interface AgentPicks {
  agentId: string | null;
  model: string | null;
  effort: string | null;
}

export const UNTOUCHED_PICKS: AgentPicks = { agentId: null, model: null, effort: null };

export interface AgentOption {
  id: string;
  label: string;
  disabled: boolean;
}

/** What the agent <select> lists: every live agent, and only those — an
 *  uninstalled agent can never be handed new work. The video's own agent is
 *  prepended as a disabled option when it is not live, so the select can still
 *  show what the video is on without offering it. Empty when the list never
 *  loaded; the picker disables itself then. */
export function agentOptions(video: Pick<Video, "agent_id">, agents: Agent[]): AgentOption[] {
  const live = agents.filter((a) => !a.archived_at)
    .map((a) => ({ id: a.id, label: a.name, disabled: false }));
  if (agents.length === 0) return live;
  const current = effectiveAgent(video, agents);
  if (current?.archived_at) {
    return [{ id: current.id, label: `${current.name} (uninstalled)`, disabled: true }, ...live];
  }
  if (!current && video.agent_id) {
    return [{ id: video.agent_id, label: `${video.agent_id} (not installed)`, disabled: true }, ...live];
  }
  return live;
}

/** The agent the model list comes from: the picked one while it is live,
 *  else the video's own. */
export function pickedAgent(
  video: Pick<Video, "agent_id">, agents: Agent[], pickedAgentId: string | null,
): Agent | null {
  const picked = pickedAgentId
    ? agents.find((a) => a.id === pickedAgentId && !a.archived_at)
    : undefined;
  return picked ?? effectiveAgent(video, agents);
}

/** Whether the human picked an agent other than the one the video already
 *  runs under. An unpinned video runs under the default, so picking the
 *  default is not a change. */
export function agentChanged(
  video: Pick<Video, "agent_id">, agents: Agent[], pickedAgentId: string | null,
): boolean {
  if (!pickedAgentId) return false;
  return pickedAgentId !== (effectiveAgent(video, agents)?.id ?? video.agent_id ?? null);
}

/** The model the picker shows. After a change of agent it restarts at the new
 *  agent's default: the old pick belongs to another agent's list, and the API
 *  would reject it. */
export function resolvedModel(
  video: Pick<Video, "agent_id" | "agent_model">, agents: Agent[], picks: AgentPicks,
): string {
  const agent = pickedAgent(video, agents, picks.agentId);
  if (!isUsable(agent)) return "";
  if (picks.model !== null && agent.models.includes(picks.model)) return picks.model;
  return agentChanged(video, agents, picks.agentId) ? agent.models[0] : initialModel(video, agent);
}

/** The agent fields an approve-script or any revise PATCH carries — merged
 *  into the action's `extra`. Only what the human touched goes out:
 *
 *  - agent_id only when they picked a *different* agent, so an untouched
 *    picker can never move a video, whatever the state of GET /agents;
 *  - agent_model when they picked one, or when the agent changed (the old
 *    model belongs to another agent's list);
 *  - agent_effort when they picked one.
 *
 *  Sending an untouched value would re-pin one the page may only have guessed:
 *  with no agent list the model resolves to "", which would silently wipe the
 *  one chosen at the topic. Approving the topic is the one action that pins
 *  regardless — see topicApprovalPayload. */
export function agentPicksPayload(
  video: Pick<Video, "agent_id" | "agent_model" | "agent_effort">,
  agents: Agent[],
  picks: AgentPicks,
): Record<string, string> {
  const out: Record<string, string> = {};
  const changed = agentChanged(video, agents, picks.agentId);
  if (changed) out.agent_id = picks.agentId as string;
  if (changed || picks.model !== null) out.agent_model = resolvedModel(video, agents, picks);
  if (picks.effort !== null) out.agent_effort = picks.effort;
  return out;
}

/** What approve-topic carries: the model and effort go out exactly as they
 *  always have — approving the topic pins the resolved model (see
 *  initialModel), so the row records which model actually made the video,
 *  and the stored effort. Plus agent_id, only when a different agent was
 *  picked. */
export function topicApprovalPayload(
  video: Pick<Video, "agent_id" | "agent_model" | "agent_effort">,
  agents: Agent[],
  picks: AgentPicks,
): Record<string, string> {
  return {
    ...agentPicksPayload(video, agents, picks),
    agent_model: resolvedModel(video, agents, picks),
    agent_effort: picks.effort ?? initialEffort(video),
  };
}
