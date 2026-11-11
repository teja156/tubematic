// Terminal Doc's contract and stage: the facts the MCP validator and the render
// rely on. The shared cases are the ones mcp/tests/test_terminal_doc.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { SIZES, maxChars, moveFrames, numberCells, wrapNote, type TDEvent, type TerminalDocData } from "./contract";
import { glowOn, beatIndexAt, beatState, pushScale, wallAt } from "./stage";
import { letterMap } from "./moves";
import { hash, noiseGlyph, scramble, typed } from "./kit";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/terminal_doc_contract.json"), "utf8"));
const EXAMPLE = JSON.parse(
  fs.readFileSync(path.join(ROOT, "agent_files/skills/tubematic-terminal-doc/reference/example-config.json"), "utf8"),
);
const DATA: TerminalDocData = EXAMPLE.scenes[0].props.terminalDoc;
const TOTAL: number = EXAMPLE.totalFrames;

describe("the shared contract cases", () => {
  it("fits the same number of characters per size as the validator", () => {
    for (const size of Object.keys(SIZES) as (keyof typeof SIZES)[]) expect(maxChars(size), size).toBe(CASES.max_chars[size]);
  });

  it("counts a number's cells the way the validator does", () => {
    for (const c of CASES.number_cells) expect(numberCells(c.value), c.value).toBe(c.cells);
  });

  it("wraps notes the way the validator does", () => {
    for (const c of CASES.wrap_note) expect(wrapNote(c.text), c.text).toEqual(c.lines);
  });

  it("times every move the way the validator does", () => {
    for (const c of CASES.move_frames) {
      expect(moveFrames(c.event as TDEvent, c.custom ?? {}, c.from ?? ""), JSON.stringify(c.event)).toBe(c.frames);
    }
  });
});

describe("the stage", () => {
  it("shows the beat that started last", () => {
    expect(beatIndexAt(DATA, 0)).toBe(0);
    expect(beatIndexAt(DATA, DATA.beats[1].start)).toBe(1);
    expect(beatIndexAt(DATA, TOTAL - 1)).toBe(DATA.beats.length - 1);
  });

  it("hands an encoded element's letters to the new one", () => {
    const enc = DATA.beats[0].events.find((e) => e.type === "encode")!;
    const before = beatState(DATA, 0, enc.at - 1, TOTAL).elements.map((e) => e.id);
    const after = beatState(DATA, 0, enc.at, TOTAL).elements.map((e) => e.id);
    expect(before).toContain("pw");
    expect(after).not.toContain("pw");
    expect(after).toContain("digest");
    expect(beatState(DATA, 0, enc.at, TOTAL).elements.find((e) => e.id === "digest")!.from?.id).toBe("pw");
  });

  it("starts each beat empty", () => {
    const b = DATA.beats[2];
    expect(beatState(DATA, 2, b.start - 1, TOTAL).elements).toEqual([]);
  });

  it("fades a glow out when the next one starts", () => {
    const glows = [
      { type: "glow", at: 0, target: "a", tone: "red" },
      { type: "glow", at: 50, target: "b", tone: "blue" },
    ] as Extract<TDEvent, { type: "glow" }>[];
    expect(glowOn(glows, "a", 20).k).toBe(1);
    expect(glowOn(glows, "a", 55).k).toBeCloseTo(0.5);
    expect(glowOn(glows, "a", 70).k).toBe(0);
    expect(glowOn(glows, "b", 70).k).toBe(1);
  });

  it("keeps the wall's level across beats until it changes", () => {
    const on = DATA.beats[1].start;
    const off = DATA.beats[2].start;
    expect(wallAt(DATA, on + 20).level).toBe(1);
    expect(wallAt(DATA, off + 20).level).toBe(0);
    expect(wallAt(DATA, 0).since).toBe(-Infinity);
  });

  it("pushes in slowly and holds", () => {
    const push = { at: 100, frames: 90, scale: 1.08 };
    expect(pushScale(push, 100, (t) => t)).toBe(1);
    expect(pushScale(push, 145, (t) => t)).toBeCloseTo(1.04);
    expect(pushScale(push, 400, (t) => t)).toBeCloseTo(1.08);
  });
});

describe("the moves", () => {
  it("flies the same letter to the nearest cell and makes new ones from noise", () => {
    expect(letterMap("SUNSHINE", "SUNSHINE")).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    const m = letterMap("SUN", "NUTS");
    expect(m).toEqual([2, 1, -1, 0]);
    expect(letterMap("AB", "A B")).toEqual([0, -1, 1]);
  });

  it("draws the same noise for the same seed and frame, so renders repeat", () => {
    expect(noiseGlyph(7, 12)).toBe(noiseGlyph(7, 12));
    expect(hash(1, 2, 3)).toBe(hash(1, 2, 3));
    expect(hash(1, 2, 3)).not.toBe(hash(1, 2, 4));
    expect(scramble("SUNSHINE", 40, 9, 1)).toBe("SUNSHINE");
    expect(scramble("SUNSHINE", -1, 9, 1)).toBe("");
  });

  it("types at its rate", () => {
    expect(typed("ABCDEFGH", 0, 1.6)).toBe("");
    expect(typed("ABCDEFGH", 5, 1.6)).toBe("ABCDEFGH");
  });
});
