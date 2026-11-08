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
| `src/cartoon3d/camera.test.ts` | The camera grammar a video's `camAt` is built from (`camera.ts`): a glide is a symmetric smootherstep (0, ½, 1 at the ends and the middle, clamped), a key glides in from its frame over `dur` and a cut lands at once with the default lens where none is given, `keyEnd` is where the current move finishes, a kick starts on the first frame at or after its event, flips sign every frame and is gone in seven, `shotAt` holds the last shot past the end, a crossfade draws the previous shot under the next one centred on the boundary, `lin` interpolates and clamps, and the lens table eases `cInf` in from the previous entry over `dur` |
| `src/cartoon3d/gate/beatVerdict.test.ts` | The beat gate's verdict from its judges (`gate/beatVerdict.ts::beatGateStatus`), the rule that replaced one judge per beat sheet: there is **no verdict with fewer than two judges**, two who agree on every beat pass or fail it, a beat they split on is sent to a third judge and the majority decides, and a missing answer counts as "does not show". The rule exists because one judge passed a frame the next failed; the test pins the exact `need` messages the tools print so an author is told which judge is still owed |

## The soundtrack engine

`renderer/remotion/cartoon-tools/audio/tests/test_mix_rules.py` (pytest, needs numpy and scipy, so it skips on a
host without them and runs in the MCP image: `cd renderer/remotion/cartoon-tools/audio && python3 -m pytest tests/`)
pins the rules an author relies on: an event is placed at exactly its `naive` level, the music ducks under every
event, and the cue sheet and `loudness.json` say which events the band covers.
