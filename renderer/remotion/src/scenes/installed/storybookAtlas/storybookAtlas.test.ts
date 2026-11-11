// Storybook Atlas's contract, stage and library: the facts the MCP validator and
// the render rely on. The shared cases are the ones mcp/tests/test_storybook_atlas.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { BACKDROPS } from "./backdrops";
import {
  ENTERS, FACINGS, GLYPHS, LIMITS, PLATE_EVENTS, PROPS, PROP_ENTRANCES, STAGE, TIMING, wrapTitle, type StorybookAtlasData,
} from "./contract";
import { BUILDS, FACES, GARMENTS, HAIRS, HAIR_COLORS, HATS, PERSON_POSES } from "./figure";
import { GLYPH_SET, letter } from "./glyphs";
import { GUIDE_POSES } from "./guide";
import { COAT_COLORS, GARMENT_COLORS, SKIN } from "./palette";
import { PROPS as DRAWINGS } from "./props";
import { ACTS } from "./props/types";
import { actMotion, actorAt, plateAt, propsAt, transitionAt, walkFrames } from "./stage";
import { needleAt } from "./plates";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/storybook_atlas_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/storybook_atlas.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-storybook-atlas/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: StorybookAtlasData = EXAMPLE.scenes[0].props.storybookAtlas;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({ LIMITS, TIMING, STAGE, ACTS, ENTERS, FACINGS, GLYPHS, PLATE_EVENTS, PROP_ENTRANCES })));
  });

  it("wraps titles the way the validator does", () => {
    for (const c of CASES.wrap_title) expect(wrapTitle(c.title)).toEqual(c.lines);
  });

  it("walks the way the validator does", () => {
    for (const c of CASES.walk_frames) expect(walkFrames(c.a, c.b)).toBe(c.frames);
    for (const w of CASES.actor_at) {
      w.frames.forEach((f: number, k: number) => {
        const s = actorAt(w.moves, f, w.start);
        expect({ x: s.x, visible: s.visible, walking: s.walking }, `frame ${f}`).toEqual(w.states[k]);
      });
    }
  });
});

describe("the pack", () => {
  it("lists exactly what the renderer draws", () => {
    const x = PACK.extra;
    expect(x.coats).toEqual(Object.keys(COAT_COLORS));
    expect(x.backdrops).toEqual([...BACKDROPS]);
    expect(x.guidePoses).toEqual([...GUIDE_POSES]);
    expect(x.personPoses).toEqual([...PERSON_POSES]);
    expect(x.knobs).toEqual({
      build: [...BUILDS], skin: Object.keys(SKIN), hair: [...HAIRS], hairColor: [...HAIR_COLORS], face: [...FACES],
      hat: [...HATS], garment: [...GARMENTS], color: Object.keys(GARMENT_COLORS),
    });
  });

  it("carries the prop catalogue the library declares", () => {
    expect(PACK.extra.props).toEqual(JSON.parse(JSON.stringify(PROPS)));
  });

  it("points its captions at the label background and the bundled serif", () => {
    expect(PACK.captions.background).toBe("label");
    expect(PACK.captions.fontFamily).toContain("EB Garamond");
  });
});

describe("the library", () => {
  it("gives every prop a box, a place, an act, and states its acts can use", () => {
    for (const [id, e] of Object.entries(DRAWINGS)) {
      expect(/^[a-z0-9_]{1,24}$/.test(id), id).toBe(true);
      expect(e.box[0] > 0 && e.box[1] > 0, id).toBe(true);
      expect(e.acts.length, id).toBeGreaterThan(0);
      expect(e.acts.every((a) => (ACTS as readonly string[]).includes(a)), id).toBe(true);
      if (e.acts.includes("switch") || e.acts.includes("cycle")) expect(e.states, id).toBeGreaterThan(1);
      if (e.portal) {
        expect(Math.abs(e.portal[0]) <= e.box[0] / 2 && e.portal[1] <= 0 && e.portal[1] >= -e.box[1], id).toBe(true);
      }
    }
  });

  it("has a door and a porthole to push through", () => {
    expect(PROPS.door.portal).toBeDefined();
    expect(PROPS.porthole.portal).toBeDefined();
  });

  it("can letter every glyph the contract allows", () => {
    for (const ch of GLYPHS) expect(GLYPH_SET[ch], ch).toBeDefined();
    const l = letter(["DEBUGGING"], 450, 430, 760);
    const xs = l.stars.map((s) => s[0]);
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(450 - 380 - 1);
    expect(Math.max(...xs)).toBeLessThanOrEqual(450 + 380 + 1);
  });
});

describe("the stage", () => {
  const events = [
    { type: "prop", at: 10, id: "l", prop: "lamp", x: 500 },
    { type: "act", at: 30, id: "l", act: "switch" },
    { type: "act", at: 80, id: "l", act: "wobble" },
  ] as StorybookAtlasData["chapters"][0]["events"];

  it("switches a prop to its second drawing and keeps it there", () => {
    expect(propsAt(events, 20, PROPS)[0].state).toBe(0);
    const p = propsAt(events, 31, PROPS)[0];
    expect([p.state, p.from]).toEqual([1, 0]);
    expect(propsAt(events, 200, PROPS)[0]).toMatchObject({ state: 1, base: 1, from: null });
  });

  it("runs a transform act for its length, then stops", () => {
    expect(propsAt(events, 90, PROPS)[0].motion?.act).toBe("wobble");
    expect(propsAt(events, 80 + TIMING.act + 1, PROPS)[0].motion).toBeNull();
    expect(actMotion("spin", 1).rot).toBeCloseTo(360);
    expect(actMotion("wobble", 1).rot).toBeCloseTo(0);
  });

  it("settles the gauge needle exactly", () => {
    const e = { from: 0, to: 3000 };
    expect(needleAt(e, 5)).toBe(0);
    expect(Math.max(...Array.from({ length: 40 }, (_, t) => needleAt(e, TIMING.plateOpen + t)))).toBeGreaterThan(3000);
    expect(needleAt(e, TIMING.plateOpen + 40)).toBe(3000);
  });

  it("opens a plate, holds it, and closes it", () => {
    const ev = [{ type: "gauge", at: 100, until: 200, label: "x", from: 0, to: 1, max: 2 }] as StorybookAtlasData["chapters"][0]["events"];
    expect(plateAt(ev, 99)).toBeNull();
    expect(plateAt(ev, 150)?.open).toBe(1);
    expect(plateAt(ev, 200 + TIMING.plateOpen)).toBeNull();
  });

  it("pushes out of the example's first chapter and wipes into its third", () => {
    const [, c2, c3] = DATA.chapters;
    expect(transitionAt(DATA, c2.start - 1)?.kind).toBe("push");
    expect(transitionAt(DATA, c2.start)?.kind).toBe("white");
    expect(transitionAt(DATA, c3.start + 1)?.kind).toBe("wipe");
    expect(transitionAt(DATA, c3.start + TIMING.wipeFrames)).toBeNull();
  });

  it("keeps the example's events inside its chapters", () => {
    const total = EXAMPLE.totalFrames;
    DATA.chapters.forEach((c, i) => {
      const end = i + 1 < DATA.chapters.length ? DATA.chapters[i + 1].start : total;
      for (const e of c.events) expect(e.at >= c.start && e.at < end - TIMING.endMargin, `${c.title} ${e.type} ${e.at}`).toBe(true);
    });
    expect(DATA.chapters.length).toBeGreaterThanOrEqual(LIMITS.chapters[0]);
  });
});
