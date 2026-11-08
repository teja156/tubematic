import { describe, expect, it } from "vitest";
import { beatGateStatus, describeStatus, type JudgeRecord } from "./beatVerdict";

const judge = (at: string, ...shows: boolean[]): JudgeRecord => ({ at, answers: shows.map((s) => ({ shows: s, why: "w", seen: "s" })) });

describe("the beat gate's verdict (two judges, a third on a split)", () => {
  it("has no verdict with fewer than two judges", () => {
    expect(beatGateStatus([], 3)).toMatchObject({ pass: false, need: "two judges", judges: 0 });
    const one = beatGateStatus([judge("a", true, true, true)], 3);
    expect(one).toMatchObject({ pass: false, need: "a second judge", judges: 1 });
    expect(describeStatus(one, 3)).toMatch(/second fresh judge/);
  });

  it("passes when two judges agree every beat shows its sentence", () => {
    const s = beatGateStatus([judge("a", true, true), judge("b", true, true)], 2);
    expect(s).toMatchObject({ pass: true, need: null, tie: [], fails: [] });
    expect(describeStatus(s, 2)).toMatch(/^PASS/);
  });

  it("fails when two judges agree a beat does not", () => {
    const s = beatGateStatus([judge("a", true, false), judge("b", true, false)], 2);
    expect(s).toMatchObject({ pass: false, need: null, fails: [1] });
    expect(describeStatus(s, 2)).toMatch(/^FAIL: beat 1/);
  });

  it("sends a split beat to a third judge, whose majority decides", () => {
    const two = [judge("a", true, true, false), judge("b", true, false, false)];
    const s = beatGateStatus(two, 3);
    expect(s).toMatchObject({ pass: false, need: "a third judge to break the tie", tie: [1] });
    expect(describeStatus(s, 3)).toMatch(/split on beat 1/);
    // the third judge passes beat 1: majority yes on 1, but beat 2 is a unanimous fail
    expect(beatGateStatus([...two, judge("c", true, true, false)], 3)).toMatchObject({ pass: false, need: null, fails: [2] });
    // a third judge for a sheet where only the split beat was in doubt
    const split = [judge("a", true, true), judge("b", true, false)];
    expect(beatGateStatus([...split, judge("c", true, true)], 2)).toMatchObject({ pass: true, need: null });
    expect(beatGateStatus([...split, judge("c", true, false)], 2)).toMatchObject({ pass: false, fails: [1] });
  });

  it("treats a missing answer as not shown", () => {
    expect(beatGateStatus([judge("a", true), judge("b", true)], 2)).toMatchObject({ pass: false, fails: [1] });
  });
});
