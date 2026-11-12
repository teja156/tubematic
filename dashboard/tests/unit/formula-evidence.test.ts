import { describe, expect, it } from "vitest";
import { formulaEvidenceLine, type ScriptFormulaNames } from "@/lib/scriptFormulas";

// The "Why this formula" row's line on whether the pick leaned on this
// install's watch figures (TMDEV-217). The record is written by the server.

const NAMES: ScriptFormulaNames = {
  formulas: [{ id: "follow-the-flow", label: "Follow the Flow" }],
  hook_types: [],
};

const record = (over: Record<string, unknown>) => JSON.stringify({
  formula: "follow-the-flow", mode: "learned", measure: "watched_pct", standing: "better",
  points: 2, videos: 24, accounts: 1, min_group: 20, ...over,
});

describe("formulaEvidenceLine", () => {
  it("says nothing for a pick made without figures, or a record it cannot read", () => {
    expect(formulaEvidenceLine("", NAMES)).toBe("");
    expect(formulaEvidenceLine(undefined, NAMES)).toBe("");
    expect(formulaEvidenceLine("{not json", NAMES)).toBe("");
    expect(formulaEvidenceLine("[]", NAMES)).toBe("");
  });

  it("names the formula and the videos behind a pick that leaned on the figures", () => {
    expect(formulaEvidenceLine(record({}), NAMES)).toBe(
      "Leaned on this install's watch figures: Follow the Flow held more of each video than this "
      + "domain's videos as a whole (24 videos on 1 account).");
  });

  it("says when the figures were read and did not favour the formula", () => {
    expect(formulaEvidenceLine(record({ standing: "worse", points: -1, accounts: 2 }), NAMES))
      .toContain("held less of each video than this domain's videos as a whole (24 videos on 2 accounts)");
    expect(formulaEvidenceLine(record({ standing: "even", points: 0 }), NAMES))
      .toContain("about as much");
    expect(formulaEvidenceLine(record({ standing: "mixed", points: 0 }), NAMES))
      .toContain("the accounts disagree");
    expect(formulaEvidenceLine(record({ standing: "thin", points: 0, videos: 0 }), NAMES))
      .toContain("fewer than 20 of this domain's videos with figures use Follow the Flow");
  });

  it("calls a trial pick a trial pick", () => {
    expect(formulaEvidenceLine(record({ mode: "explore", standing: "thin", points: 2 }), NAMES))
      .toBe("A trial pick: fewer than 20 of this domain's videos with watch figures use Follow the "
        + "Flow, so Auto tried it to learn how it holds viewers.");
    expect(formulaEvidenceLine(record({ mode: "explore", points: 0 }), NAMES))
      .toBe("A trial pick, made without this domain's watch figures.");
  });

  it("falls back to the formula's id when the names have not loaded", () => {
    expect(formulaEvidenceLine(record({}), null)).toContain("follow-the-flow held more");
  });
});
