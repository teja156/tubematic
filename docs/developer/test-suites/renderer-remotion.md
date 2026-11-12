# `renderer/remotion` (vitest)

The suite covers the pure TypeScript helpers of the Remotion project's
[Cartoon 3D kit](../09-remotion-project.md#the-cartoon-3d-kit) and of the
[`SystemFlow`](../09-remotion-project.md#systemflow),
[`BeanExplainer`](../09-remotion-project.md#beanexplainer),
[`Whiteboard`](../09-remotion-project.md#whiteboard),
[`TerminalDoc`](../09-remotion-project.md#terminaldoc),
[`UnderTheHood`](../09-remotion-project.md#underthehood) and
[`CaseFileStory`](../09-remotion-project.md#casefilestory) scenes. Each test file sits beside the code
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

## Storybook Atlas

### `src/scenes/installed/storybookAtlas/storybookAtlas.test.ts`

Covers `contract.ts`, `stage.ts`, the glyphs, the plates' gauge and the prop library
([Storybook Atlas](../10-scene-authoring.md#storybook-atlas)).

- The constants, title wrapping and walks agree with the shared cases `mcp/tests/test_storybook_atlas.py`
  runs.
- The style pack lists the coats, backdrops, poses and knobs the renderer draws, and no others, and its
  `extra.props` equals the catalogue the library declares beside its drawings; its captions use the
  `label` background and the bundled serif.
- Every library prop has a box, a place, at least one act, a second state when it can `switch` or
  `cycle`, and a portal inside its box; the door and the porthole have portals. Every glyph the
  contract allows can be lettered, and a nine-letter word fits its plate.
- A `switch` shows the second drawing and stays there; a transform act runs for its length and stops;
  the gauge needle overshoots and settles on its value with no remainder; a plate opens, holds and closes; the
  example pushes out of its first chapter and wipes into its third; its events stay inside their
  chapters.

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
- The prop kit serves a video's own prop (drawing, box, acts) like a library prop, and a library prop
  always wins over a custom prop of the same id.

Trap: a remainder matters for render time. A spring that only approaches its rest repaints its
layer on every frame, which on the CPU renderer cost more than drawing the bean.

## Terminal Doc

### `src/scenes/installed/terminalDoc/terminalDoc.test.ts`

Covers `contract.ts`, `stage.ts`, the letter map in `moves.tsx` and the kit
([Terminal Doc](../10-scene-authoring.md#terminal-doc)).

- The characters that fit at each size, a number's cells, note wrapping and every move's length
  agree with the shared cases `mcp/tests/test_terminal_doc.py` runs.
- The beat on screen is the last one started, and a beat starts empty. An `encode` hands its source's
  letters to the new element. A later glow fades the earlier one out, the wall's level holds across
  beats, and a push eases in and holds.
- A `rearrange` flies each letter to the nearest cell holding the same character and makes the rest
  from noise. Noise, scrambles and typing are pure functions of their seed and frame, so two renders
  of a video draw the same frames.

## Under the Hood

### `src/scenes/installed/underTheHood/underTheHood.test.ts`

Covers `contract.ts`, `stage.ts` and the presenter's pose table
([Under the Hood](../10-scene-authoring.md#under-the-hood)).

- Points, the photograph's box, the push, chip and stat boxes, the stat's text, the leader's start
  and overlap are computed as in the shared cases `mcp/tests/test_under_the_hood.py` runs.
- Every pose the contract lists has a drawing. The presenter starts idle and swaps on a pose's frame
  with one dissolve frame; its mouth moves only while a word is spoken; it blinks for two frames.
- The plate on screen changes at its start; the push grows the scale and keeps a pinned point on its
  spot; a zoom-through rushes the outgoing plate into its `through` point, which holds still, and the
  new plate settles from 1.25x; a cut cross-fades over its fade frames.
- Counters tick in steps and settle on their value; a stat counts up to its value and stays there.

## Case File Story

### `src/scenes/installed/caseFileStory/caseFileStory.test.ts`

Covers `contract.ts`, `stage.ts` and the icon tables
([Case File Story](../10-scene-authoring.md#case-file-story)).

- The number format, the meter cells, the camera's scale and view, the fit of a one-line text, the
  bars' layout, the frames of a beat's parts and the quiet stretches are computed as in the shared cases
  `mcp/tests/test_case_file_story.py` runs.
- Every accent has a colour, and every icon has a drawing and a fill.
- The view of a still never reaches past its edge at any focus or scale. A shot pushes in, then
  cuts 1.5 times tighter on its punch frame and moves toward the punch point.
- The meter row shows the starting values, then a shot's new value dissolving in from its cut. It
  is hidden on a card, on a shot that hides it and on the choice. The large panel counts from the
  old value to the new one.
- The count grid and its counter finish together and the result lands on its frame; a count under
  forty shows that many icons, centred in the grid's box, with the counter level with the icons; each bar comes
  up on its own frame and the payoff line after the last.
- The worked example starts at frame 0, shows a term card before its closing choice and has no
  stretch over the stillness limit.
- Under the `fill` caption look a word is grey until it is spoken, then the text colour, and a
  text colour the blend cannot parse switches on the word's frame without throwing.

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

## Whiteboard

### `src/scenes/installed/whiteboard/whiteboard.test.ts`

Covers `contract.ts`, `layout.ts`, `schedule.ts`, `camera.ts` and `doodles.ts`
([Whiteboard](../10-scene-authoring.md#whiteboard)).

- Text wraps and measures, items get their drawing times, content is placed and judged to fit,
  regions and arrows are placed, and the marker is scheduled as in the shared cases
  `mcp/tests/test_whiteboard.py` runs (`mcp/tests/fixtures/whiteboard_contract.json`), the item that
  opens the video starting `TIMING.openLead` frames before frame 0.
- `expandDoodle` answers the shared expander cases and the shipped library's digest as the
  validator does.
- The doodle library is the pack's `extra.doodles`, no more and no less, and every doodle stroke stays inside its
  100 x 100 box.
- Every slot lies inside its region, and no two slots of a layout overlap.
- A resting region's centre sits in the writing band with the next region out of frame, and a
  full-width line stays inside the side safe zone at the end of a region's creep.
- Writing in a region the camera has left counts as off screen, and the resting region's as on
  screen.
- For every region count, the recap's whole-board view, circled numbers included, fits inside the
  safe zone and above the captions, and the camera is still moving late in the recap.
- A labelled doodle squeezed anywhere between its floor and its natural time keeps the doodle's
  floor and the label's floor.

Trap: the validator in `mcp/whiteboard.py` repeats this arithmetic step for step. Change a size, a
slot or a timing here and the shared fixture fails until the Python side matches, which is the point:
a validator that disagrees with the renderer passes writing that overflows its slot.

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
- A path through any symlink is refused, a dangling one and one pointing back inside included,
  because a dangling link at the end of the path looks like a file not yet created. A folder not yet
  created passes.
- `planRequest` returns the exact frame and file pairs the server writes. Frames that are not a list
  of non-negative integers are refused, because a string iterates character by character and would
  skip the per-file check. A `/stills` prefix that climbs out of the folder is refused.

Trap: the renderer mounts `/jobs` read-write so the server can write stills, and its port takes
requests with no credential. This check is what keeps such a request from overwriting a video's
scene-config, timeline or audio.
