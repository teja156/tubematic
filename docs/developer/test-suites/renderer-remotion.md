# `renderer/remotion` (vitest)

The suite covers the pure TypeScript helpers of the Remotion project's
[Cartoon 3D kit](../09-remotion-project.md#the-cartoon-3d-kit) and of the
[`SystemFlow`](../09-remotion-project.md#systemflow) and
[`BeanExplainer`](../09-remotion-project.md#beanexplainer) scenes. Each test file sits beside the code
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

## Bean Explainer

### `src/scenes/installed/beanExplainer/beanExplainer.test.ts`

Covers `contract.ts`, `stage.ts`, the rig in `bean.tsx` and the prop library
([Bean Explainer](../10-scene-authoring.md#bean-explainer)).

- Labels wrap and prop, label and bean boxes are computed as in the shared cases
  `mcp/tests/test_bean_explainer.py` runs.
- Every prop the contract lists has a drawing and every pose a pose spec; every whole-prop act is
  back at rest when its play time ends.
- Inside a shot the stage only grows, and a cut empties it. The badge carousel plays at a list
  section change and holds that section's content until it ends. A pose swaps in two frames. A
  bean's marks clear at its next pose.
- The arm never reaches past its length, nothing squashes after the snap, a settled spring is
  1 with no remainder, and blinks are brief and rare.

Trap: a remainder matters for render time. A spring that only approaches its rest repaints its
layer on every frame, which on the CPU renderer cost more than drawing the bean.

## System Flow

### `src/scenes/installed/systemFlow/systemFlow.test.ts`

Covers `contract.ts`, `layout.ts` and `camera.ts` ([System Flow](../10-scene-authoring.md#system-flow)).

- Labels wrap and rows are assigned as in the shared cases `mcp/tests/test_system_flow.py` runs.
- dagre puts each node on its computed row and keeps the listed order within a row; an edge starts
  below its source's label and ends above its target's box.
- A full board of three rows of three, every label on two lines, shows labels of 40 px or more at
  the pull-back.
- On every frame, every node that has entered sits inside the diagram band, a focus push included.
- A value chip sits beside its connector on the side with room, and stays inside the side margins
  whatever its length and wherever the connector is.

Trap: the band check is what keeps a new node out of the captions. The camera starts moving
`cameraLead` frames before an event so it has made room when the node lands; a shorter lead lets a
node appear over the captions for most of a second.

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
