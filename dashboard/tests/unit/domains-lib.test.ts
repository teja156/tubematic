/**
 * lib/domains.ts (TMDEV-207): what a collapsed domain row says about its
 * defaults, and the options its agent and model pickers offer. The rule both
 * share: a value the domain holds that the lists no longer offer stays visible,
 * named for what happened to it, and can never be picked again.
 */
import { describe, expect, it } from "vitest";
import {
  NO_DOMAIN_DEFAULTS, domainAgent, domainAgentOptions, domainChips, domainDefaults,
  domainModelOptions, type DomainLists,
} from "@/lib/domains";
import type { Agent, Project } from "@/lib/types";

function agent(over: Partial<Agent>): Agent {
  return {
    id: "claude", name: "Claude Code", binary: "/bin/claude", run_path: "/w", install_scope: "user",
    models: ["opus", "sonnet"], effort: "high", is_default: true, weight: 1, verified_at: "",
    archived_at: null, created_at: "", updated_at: "", ...over,
  } as Agent;
}

const AGENTS = [agent({}), agent({ id: "old", name: "Old Agent", archived_at: "2026-01-02T00:00:00Z" })];

const LISTS: DomainLists = {
  styles: [{ id: "stick", label: "Stick Explainer", experimental: false, needs: {} }] as DomainLists["styles"],
  voices: [{ name: "Adam", voice_id: "a1", model_id: "eleven_v3" }],
  profiles: [
    { id: "p1", name: "Fireship", status: "READY" },
    { id: "p2", name: "Still building", status: "PENDING" },
  ] as DomainLists["profiles"],
  mascots: [{ id: "tubi", name: "Tubi", pickable: true }, { id: "moss", name: "Moss", pickable: false }],
  agents: AGENTS,
  formulaNames: { formulas: [{ id: "scene-story", label: "Scene Story" }], hook_types: [] },
};

function chips(over: Partial<typeof NO_DOMAIN_DEFAULTS>, lists = LISTS) {
  return domainChips({ ...NO_DOMAIN_DEFAULTS, ...over }, lists).map((c) => `${c.label}: ${c.value}`);
}

describe("domainDefaults", () => {
  it("reads every default as a string, blank when the row has none", () => {
    const row = { id: "d", name: "D", default_voice_id: "a1", default_formula_id: "scene-story" } as Project;
    expect(domainDefaults(row)).toEqual({ ...NO_DOMAIN_DEFAULTS, default_voice_id: "a1",
                                          default_formula_id: "scene-story" });
  });
});

describe("domainChips", () => {
  it("has no chip for a default the domain leaves alone", () => {
    expect(chips({})).toEqual([]);
  });

  it("names each default the domain sets", () => {
    expect(chips({
      default_visual_style: "stick", default_voice_id: "a1", default_script_profile_id: "p1",
      default_mascot_id: "tubi", default_agent_id: "claude", default_agent_model: "sonnet",
      default_agent_effort: "max", default_formula_id: "scene-story",
    })).toEqual(["Style: Stick Explainer", "Voice: Adam", "Profile: Fireship", "Formula: Scene Story",
                 "Mascot: Tubi", "Agent: Claude Code · sonnet · max"]);
  });

  it("leaves a blank model and effort out of the agent chip", () => {
    expect(chips({ default_agent_id: "claude" })).toEqual(["Agent: Claude Code"]);
  });

  it("reads an effort with no agent as Automatic with that effort", () => {
    expect(chips({ default_agent_effort: "low" })).toEqual(["Agent: Automatic · low"]);
  });

  it("names a formula the list does not know by its id, and none while it loads", () => {
    expect(chips({ default_formula_id: "retired-formula" })).toEqual(["Formula: retired-formula"]);
    expect(chips({ default_formula_id: "scene-story" }, { ...LISTS, formulaNames: null }))
      .toEqual(["Formula: scene-story"]);
  });

  it("reads the mascot value none as a choice, not as nothing", () => {
    expect(chips({ default_mascot_id: "none" })).toEqual(["Mascot: None"]);
  });

  it("names a stale value for what happened to it", () => {
    expect(chips({
      default_voice_id: "gone", default_script_profile_id: "p2", default_mascot_id: "moss",
      default_agent_id: "old",
    })).toEqual(["Voice: gone (removed)", "Profile: Still building (unavailable)",
                 "Mascot: Moss (unavailable)", "Agent: Old Agent (uninstalled)"]);
    expect(chips({ default_script_profile_id: "deleted", default_mascot_id: "deleted",
                   default_agent_id: "ghost" }))
      .toEqual(["Profile: Unavailable profile", "Mascot: Unavailable mascot",
                "Agent: ghost (not installed)"]);
  });

  it("claims nothing about an agent before the agent list has loaded", () => {
    expect(chips({ default_agent_id: "claude" }, { ...LISTS, agents: undefined }))
      .toEqual(["Agent: claude"]);
  });
});

describe("domainAgent / domainAgentOptions", () => {
  it("resolves only a live agent", () => {
    expect(domainAgent(AGENTS, "claude")?.name).toBe("Claude Code");
    expect(domainAgent(AGENTS, "old")).toBeNull();
    expect(domainAgent(AGENTS, "")).toBeNull();
    expect(domainAgent(undefined, "claude")).toBeNull();
  });

  it("offers Automatic and every live agent", () => {
    expect(domainAgentOptions(AGENTS, "")).toEqual([
      { value: "", label: "Automatic (dealt by weight)", disabled: false },
      { value: "claude", label: "Claude Code", disabled: false },
    ]);
  });

  it("keeps a held agent that is not live listed but unpickable", () => {
    expect(domainAgentOptions(AGENTS, "old")[1])
      .toEqual({ value: "old", label: "Old Agent (uninstalled)", disabled: true });
    expect(domainAgentOptions(AGENTS, "ghost")[1])
      .toEqual({ value: "ghost", label: "ghost (not installed)", disabled: true });
    expect(domainAgentOptions(undefined, "claude")[1])
      .toEqual({ value: "claude", label: "claude", disabled: true });
  });
});

describe("domainModelOptions", () => {
  it("names the model that blank resolves to, then lists the agent's models", () => {
    expect(domainModelOptions(AGENTS[0], "").map((o) => o.label))
      .toEqual(["opus (agent default)", "opus", "sonnet"]);
  });

  it("keeps a held model the agent dropped listed but unpickable", () => {
    expect(domainModelOptions(AGENTS[0], "haiku")[1])
      .toEqual({ value: "haiku", label: "haiku (unavailable)", disabled: true });
  });

  it("offers only the blank choice when there is no usable agent", () => {
    expect(domainModelOptions(null, "").map((o) => o.label)).toEqual(["Agent default"]);
    expect(domainModelOptions(agent({ models: [] }), "").map((o) => o.label)).toEqual(["Agent default"]);
  });
});
