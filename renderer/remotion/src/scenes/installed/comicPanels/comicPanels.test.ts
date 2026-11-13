// Comic Panels' contract, stage and library: the facts the MCP validator and the
// render rely on. The shared cases are the ones mcp/tests/test_comic_panels.py runs.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  ACTOR, BALLOONS, CAST_KINDS, CUSTOM, FACES, HAIRS, ITEM_TYPES, LAYOUTS, LIMITS, LINES, OUTFITS, PAGE, POSES, PROPS, SCALE, SKINS,
  TIMING, TONES, balloonSize, itemBox, sfxSize, type ComicPanelsData,
} from "./contract";
import { PROP_DRAWINGS } from "./props";
import { VIEW, WHOLE_PAGE, cameraAt, frameRect, inkAt, pageAt, panelAt, popAt, readRect } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/comic_panels_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/comic_panels.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-comic-panels/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: ComicPanelsData = EXAMPLE.scenes[0].props.comicPanels;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({
      LIMITS, TIMING, PAGE, LAYOUTS, TONES: Object.keys(TONES), CAST_KINDS, HAIRS, OUTFITS, SKINS, POSES, FACES, BALLOONS, LINES, ITEM_TYPES,
      PROPS, SCALE, CUSTOM, ACTOR,
    })));
  });

  it("works out boxes the way the validator does", () => {
    for (const c of CASES.item_box) expect(itemBox(LAYOUTS[c.layout as keyof typeof LAYOUTS][c.panel], c.x, c.y, c.w, c.h, c.scale)).toEqual(c.box);
    for (const c of CASES.balloon_size) expect(balloonSize(c.text)).toEqual(c.size);
    for (const c of CASES.sfx_size) expect(sfxSize(c.text)).toEqual(c.size);
  });

  it("is what character-tools/sync-contract.mjs writes today", () => {
    const files = ["mcp/tests/fixtures/comic_panels_contract.json", "tubematic_core/style_packs/comic_panels.json"];
    const before = files.map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
    execFileSync(process.execPath, ["character-tools/sync-contract.mjs", "comic_panels"], { cwd: path.join(ROOT, "renderer/remotion") });
    expect(files.map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"))).toEqual(before);
  });

  it("lays every panel out on the page, under the title bar", () => {
    for (const rects of Object.values(LAYOUTS)) {
      for (const [x, y, w, h] of rects) {
        expect(x).toBeGreaterThanOrEqual(0);
        expect(y).toBeGreaterThanOrEqual(PAGE.titleH);
        expect(x + w).toBeLessThanOrEqual(PAGE.w);
        expect(y + h).toBeLessThanOrEqual(PAGE.h);
      }
    }
  });
});

describe("the library", () => {
  it("draws every prop the contract lists", () => {
    expect(Object.keys(PROP_DRAWINGS).sort()).toEqual(Object.keys(PROPS).sort());
    expect(Object.keys(PACK.extra.props).sort()).toEqual(Object.keys(PROPS).sort());
  });
});

describe("the stage", () => {
  it("opens on page 1, panel 1, framed and inked at frame 0", () => {
    expect(pageAt(DATA, 0)).toBe(0);
    expect(panelAt(DATA.pages[0], 0)).toBe(0);
    const cam = cameraAt(DATA, 0);
    expect(cam.scale).toBeCloseTo(frameRect(readRect(LAYOUTS[DATA.pages[0].layout][0])).scale);
    // the opening panel and what is in it are drawn finished at frame 0: never an empty page
    expect(inkAt(0, 0)).toBe(1);
    expect(popAt(0, 0)).toBe(1);
    expect(inkAt(30, 30)).toBe(0);
    expect(inkAt(30, 30 + TIMING.inkIn)).toBe(1);
  });

  it("frames a top-row panel with the whole title bar, so the title is never cut", () => {
    for (const rects of Object.values(LAYOUTS)) {
      const r = readRect(rects[0]);
      expect([r[0], r[1], r[2]]).toEqual([0, 0, PAGE.w]);
      expect(frameRect(r).scale * PAGE.w).toBeLessThanOrEqual(VIEW.maxW + 1e-9);
    }
    expect(readRect(LAYOUTS.stack3[1])).toEqual(LAYOUTS.stack3[1]);
  });

  it("glides to the next panel over TIMING.read frames, then holds still", () => {
    const next = DATA.pages[0].panels[2].start;
    const target = frameRect(LAYOUTS[DATA.pages[0].layout][2]);
    const settled = cameraAt(DATA, next + TIMING.read);
    expect(settled.cx).toBeCloseTo(target.cx);
    expect(settled.cy).toBeCloseTo(target.cy);
    expect(cameraAt(DATA, next + TIMING.read + 10)).toEqual(settled);
    expect(cameraAt(DATA, next + 2).cx).not.toBeCloseTo(target.cx);
  });

  it("pulls back to the whole page at the splash", () => {
    const whole = frameRect(WHOLE_PAGE);
    const end = cameraAt(DATA, DATA.splash! + TIMING.pullBack);
    expect(end.scale).toBeCloseTo(whole.scale);
    expect(whole.scale * WHOLE_PAGE[3]).toBeLessThanOrEqual(VIEW.maxH + 1e-9);
  });

  it("punches in and shakes on a hit, then settles", () => {
    const hit = DATA.pages[0].panels[3].items.find((i) => i.type === "hit")!.frame;
    const on = cameraAt(DATA, hit + 1), after = cameraAt(DATA, hit + TIMING.hit);
    expect(on.scale).toBeGreaterThan(after.scale);
    expect(Math.abs(on.shakeX) + Math.abs(on.shakeY)).toBeGreaterThan(0);
    expect(after.shakeX).toBe(0);
  });

  it("pops an item in and lands on exactly 1", () => {
    expect(popAt(10, 9)).toBe(0);
    expect(popAt(10, 10 + TIMING.pop)).toBe(1);
  });
});
