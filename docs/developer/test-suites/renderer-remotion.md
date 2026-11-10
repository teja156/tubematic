# `renderer/remotion` (vitest)

The suite covers the pure TypeScript helpers of the Remotion project's
[Cartoon 3D kit](../09-remotion-project.md#the-cartoon-3d-kit). Each test file sits beside the code
it covers as `*.test.ts`. The tests run under Node 22 with no browser, canvas or render, because the
math and geometry classes of `three` work in Node without a DOM.

```bash
cd renderer/remotion
npm test                 # vitest run
npm test -- camera       # one file
```

`vitest` is a devDependency of the Remotion project because CI runs `tsc --noEmit` over this tree,
test files included, and a test file whose `vitest` import does not resolve fails that typecheck. CI
does not run `npm test`, so run the suite yourself after you change either module.

The soundtrack tools under `cartoon-tools/audio/` have a pytest suite of their own, described on
[`cartoon-audio.md`](cartoon-audio.md).

## Cartoon 3D

### `src/cartoon3d/camera.test.ts`

Covers the camera grammar in `src/cartoon3d/camera.ts`, the functions a video's `camAt` is built
from.

- A glide is a symmetric, clamped smootherstep. A key glides in from its frame over `dur` frames, a
  cut lands at once with the default lens, and `keyEnd` returns the frame the current move finishes
  on.
- A kick starts on the first frame at or after its event, flips sign every frame and is gone after
  seven frames.
- `shotAt` finds the shot of a frame and holds the last shot past the end. A crossfade draws the
  previous shot under the next one, centred on the boundary between them.
- `lin` interpolates and clamps at both ends, and the lens table eases `cInf` in from the previous
  entry over `dur`.

Trap: an agent writes each video's shot plan against these timings, so a change to one of them moves
the camera in every Cartoon 3D video written afterwards.

### `src/cartoon3d/gate/beatVerdict.test.ts`

Covers `gate/beatVerdict.ts::beatGateStatus` and `describeStatus`, which turn the judges' recorded
answers into the [beat gate](../10-scene-authoring.md#cartoon-3d)'s verdict.

- Fewer than two judges give no verdict, and the status names the judge still owed.
- Two judges who agree on every beat pass or fail the video.
- A beat they split on goes to a third judge, and the majority decides it.
- A missing answer counts as "the picture does not show the sentence".

Trap: the verdict needs two judges because two judges can disagree about the same frame. The `need`
values are asserted word for word because `gate/beatGateCli.ts` prints them to tell the author which
judge to run next.
