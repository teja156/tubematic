/**
 * TMDEV-110: the pure logic behind the agent picker, shared by ActionPane and
 * VideoModal. What matters most is agentPicksPayload's "untouched" contract —
 * an approval nobody touched must not send a value the page guessed, which is
 * exactly the TMDEV-106 defect class.
 */
import { describe, expect, it } from "vitest";
import {
  UNTOUCHED_PICKS, agentChanged, agentOptions, agentPicksPayload, pickedAgent,
  topicApprovalPayload,
} from "@/lib/agents";
import type { Agent, Video } from "@/lib/types";

function agent(id: string, over: Partial<Agent> = {}): Agent {
  return {
    id, name: id[0].toUpperCase() + id.slice(1), binary: `/bin/${id}`, run_path: "/w",
    install_scope: "user", models: [`${id}-a`, `${id}-b`], effort: "high",
    is_default: false, weight: 1, verified_at: "", archived_at: null,
    created_at: "", updated_at: "", ...over,
  } as Agent;
}

const CLAUDE = agent("claude", { is_default: true, models: ["sonnet", "opus"] });
const CODEX = agent("codex", { models: ["gpt-5", "gpt-5-mini"] });
const OLD = agent("old", { archived_at: "2026-01-02T00:00:00Z" });
const AGENTS = [CLAUDE, CODEX, OLD];

type V = Pick<Video, "status" | "agent_id" | "agent_model" | "agent_effort">;
const v = (over: Partial<V> = {}): V => ({
  status: "SCRIPT_READY", agent_id: "claude", agent_model: "opus", agent_effort: "", ...over,
});

describe("agentOptions", () => {
  it("offers every live agent and never an uninstalled one", () => {
    expect(agentOptions(v(), AGENTS)).toEqual([
      { id: "claude", label: "Claude", disabled: false },
      { id: "codex", label: "Codex", disabled: false },
    ]);
  });

  it("shows the video's own uninstalled agent, but not as a choice", () => {
    expect(agentOptions(v({ agent_id: "old" }), AGENTS)).toEqual([
      { id: "old", label: "Old (uninstalled)", disabled: true },
      { id: "claude", label: "Claude", disabled: false },
      { id: "codex", label: "Codex", disabled: false },
    ]);
  });

  it("keeps an unresolvable pin traceable by its raw id", () => {
    expect(agentOptions(v({ agent_id: "ghost" }), AGENTS)[0]).toEqual(
      { id: "ghost", label: "ghost (not installed)", disabled: true });
  });

  it("offers nothing when the agent list never loaded", () => {
    expect(agentOptions(v(), [])).toEqual([]);
  });
});

describe("pickedAgent / agentChanged", () => {
  it("is the effective agent until a live one is picked", () => {
    expect(pickedAgent(v(), AGENTS, null)?.id).toBe("claude");
    expect(pickedAgent(v(), AGENTS, "codex")?.id).toBe("codex");
    expect(pickedAgent(v(), AGENTS, "old")?.id).toBe("claude");
  });

  it("does not count picking the current agent — or an unpinned video's default — as a change", () => {
    expect(agentChanged(v(), AGENTS, "claude")).toBe(false);
    expect(agentChanged(v({ agent_id: null }), AGENTS, "claude")).toBe(false);
    expect(agentChanged(v(), AGENTS, "codex")).toBe(true);
    expect(agentChanged(v(), AGENTS, null)).toBe(false);
  });
});

describe("agentPicksPayload", () => {
  it.each(["SCRIPT_READY", "VIDEO_READY"] as const)(
    "%s: untouched sends nothing at all, loaded or not", (status) => {
      expect(agentPicksPayload(v({ status }), AGENTS, UNTOUCHED_PICKS)).toEqual({});
      expect(agentPicksPayload(v({ status }), [], UNTOUCHED_PICKS)).toEqual({});
    });

  it("a changed agent sends the new id and that agent's default model, keeping effort", () => {
    expect(agentPicksPayload(v(), AGENTS, { ...UNTOUCHED_PICKS, agentId: "codex" }))
      .toEqual({ agent_id: "codex", agent_model: "gpt-5" });
  });

  it("a changed agent sends the model picked from its own list", () => {
    expect(agentPicksPayload(v(), AGENTS, { agentId: "codex", model: "gpt-5-mini", effort: null }))
      .toEqual({ agent_id: "codex", agent_model: "gpt-5-mini" });
  });

  it("a model left over from the old agent is never sent for the new one", () => {
    expect(agentPicksPayload(v(), AGENTS, { agentId: "codex", model: "sonnet", effort: null }))
      .toEqual({ agent_id: "codex", agent_model: "gpt-5" });
  });

  it("picking the current agent again is not a change", () => {
    expect(agentPicksPayload(v(), AGENTS, { ...UNTOUCHED_PICKS, agentId: "claude" })).toEqual({});
  });

  it("a touched model or effort is sent on its own", () => {
    expect(agentPicksPayload(v(), AGENTS, { ...UNTOUCHED_PICKS, model: "sonnet" }))
      .toEqual({ agent_model: "sonnet" });
    expect(agentPicksPayload(v(), AGENTS, { ...UNTOUCHED_PICKS, effort: "max" }))
      .toEqual({ agent_effort: "max" });
    expect(agentPicksPayload(v(), AGENTS, { ...UNTOUCHED_PICKS, effort: "" }))
      .toEqual({ agent_effort: "" });
  });
});

describe("agentPicksPayload for a revision at TOPIC_PROPOSED", () => {
  it("untouched sends nothing — a revision never pins a model", () => {
    const topic = v({ status: "TOPIC_PROPOSED", agent_model: "opus" });
    expect(agentPicksPayload(topic, AGENTS, UNTOUCHED_PICKS)).toEqual({});
    expect(agentPicksPayload(topic, [], UNTOUCHED_PICKS)).toEqual({});
  });
});

describe("topicApprovalPayload keeps today's approval", () => {
  const topic = v({ status: "TOPIC_PROPOSED", agent_model: "", agent_effort: "" });

  it("untouched pins the resolved model and sends the stored effort", () => {
    expect(topicApprovalPayload(topic, AGENTS, UNTOUCHED_PICKS))
      .toEqual({ agent_model: "sonnet", agent_effort: "" });
  });

  it("untouched with no agent list sends a blank model, never a guess", () => {
    expect(topicApprovalPayload(topic, [], UNTOUCHED_PICKS))
      .toEqual({ agent_model: "", agent_effort: "" });
  });

  it("a changed agent adds its id and pins its default model", () => {
    expect(topicApprovalPayload(topic, AGENTS, { ...UNTOUCHED_PICKS, agentId: "codex" }))
      .toEqual({ agent_id: "codex", agent_model: "gpt-5", agent_effort: "" });
  });
});
