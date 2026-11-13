// Puppet History's contract, stage, map and library: the facts the MCP
// validator and the render rely on. The shared cases are the ones
// mcp/tests/test_puppet_history.py runs.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  BEAT_EVENTS, BEAT_TYPES, COSTUMES, COUNTRIES, CUSTOM, ENTRANCES, EVENT_TYPES, FACES, FILLS, GEOMETRY, LIMITS, POSES, PROPS, SETS,
  STAMP_COLORS, TIMING, puppetBox, signWidth, type PuppetHistoryData,
} from "./contract";
import { COSTUME_DRAWINGS } from "./costumes";
import { mapProjection, regionCentre } from "./map";
import { PROP_DRAWINGS } from "./props";
import { SET_DRAWINGS } from "./sets";
import { beatAt, blinkAt, costumeAt, puppetsAt, strikesAt } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/puppet_history_contract.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-puppet-history/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: PuppetHistoryData = EXAMPLE.scenes[0].props.puppetHistory;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({
      LIMITS, TIMING, GEOMETRY, POSES, FACES, COSTUMES, SETS, PROPS, STAMP_COLORS, FILLS: Object.keys(FILLS), ENTRANCES, BEAT_TYPES, EVENT_TYPES,
      BEAT_EVENTS, CUSTOM,
    })));
    for (const c of CASES.puppet_box) expect(puppetBox(c.slot)).toEqual(c.box);
    for (const c of CASES.sign_width) expect(signWidth(c.text)).toBe(c.w);
    for (const c of CASES.blink) expect(blinkAt(c.frame, c.seed)).toBe(c.blink);
  });

  it("is what character-tools/sync-contract.mjs writes today", () => {
    const files = ["mcp/tests/fixtures/puppet_history_contract.json", "tubematic_core/style_packs/puppet_history.json"];
    const before = files.map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
    execFileSync(process.execPath, ["character-tools/sync-contract.mjs", "puppet_history"], { cwd: path.join(ROOT, "renderer/remotion") });
    expect(files.map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"))).toEqual(before);
  });
});

describe("the library", () => {
  it("draws every costume, set and prop the contract lists", () => {
    expect(Object.keys(COSTUME_DRAWINGS).sort()).toEqual([...COSTUMES].sort());
    expect(Object.keys(SET_DRAWINGS).sort()).toEqual([...SETS].sort());
    expect(Object.keys(PROP_DRAWINGS).sort()).toEqual(Object.keys(PROPS).sort());
  });

  it("keeps every set's decor on stage and off the caption band", () => {
    for (const s of SETS) {
      for (const d of SET_DRAWINGS[s].decor) {
        // the captions sit near y 270: decor starts at y 180 at the highest (sets.tsx keeps the band calm)
        expect(d.y + d.box.top, `${d.id} top`).toBeGreaterThanOrEqual(180);
        expect(d.y + d.box.top + d.box.height, `${d.id} bottom`).toBeLessThanOrEqual(GEOMETRY.frontY + 60);
      }
    }
  });
});

describe("the stage", () => {
  it("opens with the first puppet already in place at frame 0", () => {
    const [p] = puppetsAt(DATA, DATA.beats[0], 0);
    expect(p.x).toBe(GEOMETRY.slots[1]);
    expect(p.pop).toBe(1);
  });

  it("slides a puppet in from the nearest edge and stops it dead in its slot", () => {
    const map = DATA.beats[2];
    const enter = map.events[0];
    const first = puppetsAt(DATA, map, enter.frame)[0];
    expect(first.x).toBeLessThan(0);
    expect(puppetsAt(DATA, map, enter.frame + TIMING.slide)[0].x).toBe(GEOMETRY.slots[0]);
  });

  it("faces a puppet in the right slot to the left", () => {
    const data: PuppetHistoryData = { ...DATA, beats: [{ type: "set", start: 0, set: "office", events: [{ type: "enter", frame: 0, who: "you", slot: 2 }] }] };
    expect(puppetsAt(data, data.beats[0], 0)[0].flip).toBe(true);
  });

  it("keeps a swapped costume into later beats", () => {
    const swap = DATA.beats[4].events.find((e) => e.type === "swap")!;
    expect(costumeAt(DATA, "you", swap.frame - 1)).toBe("legionary");
    expect(costumeAt(DATA, "you", swap.frame)).toBe("farmer");
  });

  it("strikes a card line out, then scrawls the new value", () => {
    const card = DATA.beats[1];
    const strike = card.events.find((e) => e.type === "strike")!;
    const s0 = strikesAt(card, strike.frame).get(2)!;
    expect(s0.strike).toBe(0);
    const s1 = strikesAt(card, strike.frame + TIMING.strike * 2).get(2)!;
    expect([s1.strike, s1.scrawl]).toEqual([1, 1]);
  });

  it("cuts between beats", () => {
    expect(beatAt(DATA, DATA.beats[1].start - 1)).toBe(0);
    expect(beatAt(DATA, DATA.beats[1].start)).toBe(1);
  });
});

describe("the map", () => {
  it("knows today's countries by world-atlas's names", () => {
    expect(COUNTRIES).toContain("France");
    expect(new Set(COUNTRIES).size).toBe(COUNTRIES.length);
  });

  it("fits the focus countries by their mainland, so a far territory does not pull the map across an ocean", () => {
    const [x, y, w, h] = GEOMETRY.map;
    const p = regionCentre(["France", "Italy"], "France")!;
    expect(p[0]).toBeGreaterThan(x);
    expect(p[0]).toBeLessThan(x + w);
    expect(p[1]).toBeGreaterThan(y);
    expect(p[1]).toBeLessThan(y + h);
    // France's mainland fills a good part of the map, not a speck beside French Guiana
    const proj = mapProjection(["France"]);
    const [ax] = proj([-4.5, 48.4])!, [bx] = proj([7.5, 48.4])!;
    expect(bx - ax).toBeGreaterThan(w * 0.5);
  });
});
