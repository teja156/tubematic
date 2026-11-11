# `renderer/remotion` (vitest)

The suite covers the pure TypeScript helpers of the Remotion project's
[Cartoon 3D kit](../09-remotion-project.md#the-cartoon-3d-kit) and of the
[`SystemFlow`](../09-remotion-project.md#systemflow) scene. Each test file sits beside the code
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

### `renderer/remotion/cartoon-tools/out-path.test.ts`

Covers `renderer/remotion/cartoon-tools/out-path.mjs::outPathError` and `planRequest`, the checks the
[stills server](../11-rendering-and-review.md#the-stills-server) runs on every file a request would
write, before it bundles or opens a browser.

- The paths the Cartoon 3D tools write (`<video_id>/cartoon/stills/…`, `<video_id>/cartoon/beatgate/…`)
  pass, and an output directory under a video's `cartoon/` folder passes.
- A path elsewhere in `/jobs`, outside it, relative, or escaping with `..` is refused, as is a file that
  is not a PNG and a missing path.
- A path that goes through a planted symlink out of the public directory is refused. A folder not
  yet created passes.
- `planRequest` returns the exact frame and file pairs the server writes. Frames that are not a list
  of non-negative integers are refused, because a string iterates character by character and would
  skip the per-file check. A `/stills` prefix that climbs out of the folder is refused.

Trap: the renderer mounts `/jobs` read-write so the server can write stills, and its port takes
requests with no credential. This check is what keeps such a request from overwriting a video's
scene-config, timeline or audio.
