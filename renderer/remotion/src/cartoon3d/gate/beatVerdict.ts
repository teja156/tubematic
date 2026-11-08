// The beat gate's verdict from its judges: TWO judges must agree on every beat; a beat they split on goes to a
// third, and the majority decides. One judge passed a fog frame that the next judge failed (round 6), and a single
// opinion on a sentence-versus-picture question is noise; two that agree are evidence. Pure, so it is unit-tested.
export interface BeatAnswer { shows: boolean; why: string; seen: string; fix?: string }
export interface JudgeRecord { at: string; answers: BeatAnswer[] }

export interface BeatGateStatus {
  pass: boolean;
  /** what is still needed before a verdict exists: null when the judges have decided */
  need: "two judges" | "a second judge" | "a third judge to break the tie" | null;
  /** beats the judges split evenly on (needs another judge) */
  tie: number[];
  /** beats a majority says do not show their sentence */
  fails: number[];
  judges: number;
}

export const beatGateStatus = (records: JudgeRecord[], nBeats: number): BeatGateStatus => {
  const judges = records.length;
  if (judges === 0) return { pass: false, need: "two judges", tie: [], fails: [], judges };
  if (judges === 1) return { pass: false, need: "a second judge", tie: [], fails: [], judges };
  const beats = Array.from({ length: nBeats }, (_, i) => i);
  const yes = beats.map((i) => records.filter((r) => r.answers[i]?.shows).length);
  const tie = beats.filter((i) => yes[i] * 2 === judges);
  if (tie.length) return { pass: false, need: "a third judge to break the tie", tie, fails: [], judges };
  const fails = beats.filter((i) => yes[i] * 2 < judges);
  return { pass: fails.length === 0, need: null, tie: [], fails, judges };
};

/** one line for the console and the tools */
export const describeStatus = (s: BeatGateStatus, nBeats: number): string => {
  if (s.need === "two judges") return "no judge has answered yet: two fresh judges must";
  if (s.need === "a second judge") return "1 of 2 judges recorded: a second fresh judge must answer the same prompt";
  if (s.need) return `${s.judges} judges split on beat${s.tie.length > 1 ? "s" : ""} ${s.tie.join(", ")}: a third fresh judge breaks the tie`;
  return s.pass ? `PASS: ${s.judges} judges agree every one of ${nBeats} beats shows its sentence` : `FAIL: beat${s.fails.length > 1 ? "s" : ""} ${s.fails.join(", ")} do not show their sentence (${s.judges} judges)`;
};
