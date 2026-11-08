# `renderer/remotion` (vitest)

Tests for pure code in the Remotion project: no browser, no canvas, no render. Test files sit beside
the code they cover as `*.test.ts`.

```bash
cd renderer/remotion
npm test                 # vitest run
npm test -- partGrammar
```

**Stack:** vitest, Node 22, `three` (its math and geometry classes run in Node without a DOM).

`vitest` is a devDependency of the Remotion project, not a tool borrowed from the dashboard. That is
deliberate: `validate_job` runs `tsc --noEmit` over this whole tree for every video, and a test file
whose `vitest` import does not resolve there would fail validation for every video.

---

## Files

| File | Covers |
|---|---|
| `src/cartoon3d/probe2/partGrammar.test.ts` | The part grammar of the inked-3D spike: parts written as JSON data (`partSpecs/`), built by `partCompile.ts`, with the footprint the layout and its checker use derived by `partGrammar.ts::deriveDims`. Pins the derived box of a small two-primitive spec (rotations applied, centred on the origin, from the ground up), that `deriveInfo` passes the flags through and turns smoke attach points into the smoke flag, and that every spec survives a JSON round trip unchanged and is named after its part kind (the compiler seeds a part's jitter from its name the same way `makePart` seeds the hand-built kind, so the seeded variants of a converted part stay the ones the worlds were laid out with). It also compiles each spec with stand-in materials and checks every mesh lies **inside** its derived footprint and not far inside it. That is the guarantee the derivation exists for: the box the checker reasons about cannot be smaller than what is drawn. Cards are left out of that check because drawing one needs a canvas; the gallery renders them |
| `src/cartoon3d/probe2/partGate.test.ts` | The gate an agent-made part passes before a world may use it, the deterministic half (`partGrammar.ts::validatePartSpec`): a sound spec passes clean; a kit name, a malformed name and an unknown material are each refused with a reason; a primitive that touches neither the ground nor anything that does is named as **floating** (the check the vision judge cannot be trusted to make); the size limits hold at both ends (a 20 m box, a hairline); and a malformed primitive explains itself instead of throwing. Also pins that a world carrying its own part (`WorldSpec.parts`) is laid out with the part's **derived** footprint and catalog facts (`partsSpec.ts::partDims`, the `solid`/`walkable` facts stored on the placed prop so the checker never looks them up), that the headless QA blocks on an unsound or misnamed part (`qa.ts::checkParts`), that naming a part the world does not carry throws rather than placing a phantom, and that the stager's enforcement (`gate/verdicts.ts::unpassed`) counts only a judged PASS for the part's *current* spec, so a verdict for an earlier version of the same name does not carry over |
| `src/cartoon3d/probe2/gate/beatVerdict.test.ts` | The beat gate's verdict from its judges (`gate/beatVerdict.ts::beatGateStatus`), the rule that replaced one judge per beat sheet: there is **no verdict with fewer than two judges**, two who agree on every beat pass or fail it, a beat they split on is sent to a third judge and the majority decides, and a missing answer counts as "does not show". The rule exists because one judge passed a frame the next failed; the test pins the exact `need` messages the tools print so an author is told which judge is still owed |
| `src/cartoon3d/probe2/cues.test.ts` | Gesture cues timed inside a beat (`worldKit.ts::gestureAt`): the beat's own gesture and head turn hold until a cue's frame, the switch lands the drawers' lead early, the previous gesture is remembered to blend from, and a cue that sets only one of gesture or head turn carries the other through. Also pins that the checker (`qa.ts::checkWorld`) refuses, as a BLOCK, a gesture name the newsboy, operator or a `world.cast` figure cannot make (on the beat or in a cue), a cue outside its beat or out of order, and a cue that changes nothing. An unknown gesture is a crash in the drawer mid-render, which is why it is caught on the data. Also the beat sheet itself (`checkBeats`): ordered, contiguous beats from frame 0 to the last frame pass; a gap, an overlap, a late start, an empty sheet and a sheet shorter than the video are each a BLOCK naming the first uncovered frame |
