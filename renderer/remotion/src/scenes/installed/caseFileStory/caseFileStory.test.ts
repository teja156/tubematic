// Case File Story's contract and stage: the facts the MCP validator and the render
// rely on. The shared cases are the ones mcp/tests/test_case_file_story.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  ACCENTS, ACCENT_NAMES, CAMERA, ICONS, TIMING, barLayout, fitFontSize, formatValue, hudCells, partFrames, shotScale, shotView,
  termFontSize,
  type Beat, type CaseFileData, type Shot,
} from "./contract";
import { ICON_DRAW, ICON_FILL } from "./icons";
import { barsAt, beatIndexAt, countAt, hudAt, meterValues, panelAt, quietSpans, viewAt } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/case_file_story_contract.json"), "utf8"));
const EXAMPLE = JSON.parse(
  fs.readFileSync(path.join(ROOT, "agent_files/skills/tubematic-case-file-story/reference/example-config.json"), "utf8"),
);
const DATA: CaseFileData = EXAMPLE.scenes[0].props.caseFile;
const TOTAL: number = EXAMPLE.totalFrames;
const close = (xs: number[]) => xs.map((v) => expect.closeTo(v, 6));

describe("the shared contract cases", () => {
  it("formats numbers the way the validator does", () => {
    for (const c of CASES.format_value) expect(formatValue(c.kind, c.value)).toBe(c.text);
  });

  it("lays out the meter row, the camera and the cards the way the validator does", () => {
    for (const c of CASES.hud_cells) expect(hudCells(c.n).flat()).toEqual(close(c.cells.flat()));
    for (const c of CASES.shot_scale) expect(shotScale(c.t, c.fps, c.punchAfter)).toBeCloseTo(c.scale, 9);
    for (const c of CASES.shot_view) expect(shotView(c.scale, c.u, c.v)).toEqual(close(c.view));
    for (const c of CASES.term_font_size) expect(termFontSize(c.term)).toBe(c.size);
    for (const c of CASES.fit_font_size) expect(fitFontSize(c.text, c.size, c.width)).toBe(c.fit);
    for (const c of CASES.bar_layout) {
      const got = barLayout(c.values, c.threshold);
      expect(got.bars.flat()).toEqual(close(c.bars.flat()));
      expect(got.lineY).toBeCloseTo(c.lineY, 6);
    }
  });

  it("times a beat's parts and the quiet stretches the way the validator does", () => {
    for (const c of CASES.part_frames) expect(partFrames(c.beat as Beat)).toEqual(c.frames);
    for (const c of CASES.quiet_spans) expect(quietSpans(c.data as CaseFileData, c.total)).toEqual(c.spans);
  });
});

describe("the catalogues", () => {
  it("has a colour for every accent and a drawing and a fill for every icon", () => {
    expect(Object.keys(ACCENTS).sort()).toEqual([...ACCENT_NAMES].sort());
    expect(Object.keys(ICON_DRAW).sort()).toEqual([...ICONS].sort());
    expect(Object.keys(ICON_FILL).sort()).toEqual([...ICONS].sort());
  });
});

describe("the camera on a still", () => {
  it("never shows an edge of the still, whatever the focus", () => {
    for (const [u, v] of [[0, 0], [1, 1], [0.5, 0.45], [0.02, 0.98]]) {
      for (const s of [1, 1.1, 1.5, 2.2]) {
        const [x, y, w, h] = shotView(s, u, v);
        expect(x).toBeGreaterThanOrEqual(0);
        expect(y).toBeGreaterThanOrEqual(0);
        expect(x + w).toBeLessThanOrEqual(1080 + 1e-9);
        expect(y + h).toBeLessThanOrEqual(1920 + 1e-9);
      }
    }
  });

  it("pushes in slowly, then cuts tighter on the punch frame and moves to the punch point", () => {
    const shot: Shot = { type: "shot", start: 100, image: "x", focus: [0.5, 0.5], punch: { frame: 160, at: [0.25, 0.25] } };
    const before = viewAt(shot, 159, 30), after = viewAt(shot, 160, 30);
    expect(viewAt(shot, 100, 30)[2]).toBeCloseTo(1080, 6);
    expect(before[2]).toBeLessThan(1080);
    expect(before[2] / after[2]).toBeCloseTo(CAMERA.punch, 2);
    expect(after[0] + after[2] / 2).toBeLessThan(before[0] + before[2] / 2);
  });
});

describe("the meter row", () => {
  it("shows the starting values, then a shot's new values dissolving in from its cut", () => {
    const setter = DATA.beats.find((b): b is Shot => b.type === "shot" && !!b.set)!;
    const id = Object.keys(setter.set!)[0];
    const meter = DATA.hud.find((m) => m.id === id)!;
    expect(meterValues(DATA, 0)[id]).toBe(meter.value);
    expect(meterValues(DATA, setter.start)[id]).toBe(setter.set![id]);
    const cell = hudAt(DATA, setter.start)!.find((c) => c.id === id)!;
    expect(cell.from).toBe(formatValue(meter.kind, meterValues(DATA, setter.start - 1)[id]));
    expect(cell.mix).toBe(0);
    const later = hudAt(DATA, setter.start + TIMING.hudDissolve)!.find((c) => c.id === id)!;
    expect(later).toMatchObject({ from: null, mix: 1, text: formatValue(meter.kind, setter.set![id]) });
  });

  it("is hidden on a card, on a shot that says so and on the choice", () => {
    for (const b of DATA.beats) {
      const hidden = b.type !== "shot" || b.hud === false;
      expect(hudAt(DATA, b.start + 1) === null).toBe(hidden);
    }
  });

  it("counts the large panel from the old value to the new one", () => {
    const shot = DATA.beats.find((b): b is Shot => b.type === "shot" && !!b.panel)!;
    const meter = DATA.hud.find((m) => m.id === shot.panel)!;
    const from = meterValues(DATA, shot.start - 1)[meter.id], to = shot.set![meter.id];
    expect(panelAt(DATA, shot, shot.start)!.text).toBe(formatValue(meter.kind, from));
    expect(panelAt(DATA, shot, shot.start + TIMING.panelCount)).toMatchObject({ text: formatValue(meter.kind, to), counting: false });
  });
});

describe("the cards", () => {
  it("fills the count grid and the counter together, then lands the result on its frame", () => {
    const card = DATA.beats.find((b) => b.type === "count")!;
    if (card.type !== "count") throw new Error("no count card");
    const [, counted, result] = partFrames(card);
    expect(countAt(card, card.start)).toMatchObject({ cells: 0, result: false });
    expect(countAt(card, counted)).toMatchObject({ total: 40, cells: 40, text: formatValue(card.kind, card.to), result: false });
    expect(countAt(card, result).result).toBe(true);
  });

  it("shows as many icons as the number when it is under forty", () => {
    const card = { type: "count" as const, start: 0, title: "T", icon: "envelope" as const, to: 7, kind: "count" as const, result: "R" };
    expect(countAt(card, 0)).toMatchObject({ total: 7, cells: 0 });
    expect(countAt(card, partFrames(card)[1])).toMatchObject({ total: 7, cells: 7, text: "7" });
  });

  it("puts each bar up on its own frame and the payoff after the last", () => {
    const card = DATA.beats.find((b) => b.type === "bars")!;
    if (card.type !== "bars") throw new Error("no bars card");
    card.bars.forEach((bar, i) => {
      expect(barsAt(card, bar.frame - 1).shown).toBe(i);
      expect(barsAt(card, bar.frame).shown).toBe(i + 1);
    });
    const parts = partFrames(card);
    expect(barsAt(card, parts[parts.length - 1] - 1).payoff).toBe(false);
    expect(barsAt(card, parts[parts.length - 1]).payoff).toBe(true);
  });
});

describe("the worked example", () => {
  it("starts at frame 0, ends on the choice and shows the consequence before it", () => {
    expect(DATA.beats[0].start).toBe(0);
    expect(DATA.beats[DATA.beats.length - 1].type).toBe("choice");
    expect(DATA.beats.some((b) => b.type === "term")).toBe(true);
    expect(beatIndexAt(DATA, TOTAL - 1)).toBe(DATA.beats.length - 1);
  });

  it("has no stretch longer than the stillness limit", () => {
    for (const [from, to] of quietSpans(DATA, TOTAL)) expect(to - from).toBeLessThanOrEqual(4 * 30);
  });
});
