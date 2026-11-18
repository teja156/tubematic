# `renderer/remotion` (vitest)

The suite covers the pure TypeScript helpers of the Remotion project's
[Cartoon 3D kit](../09-remotion-project.md#the-cartoon-3d-kit) and of the
[`SystemFlow`](../09-remotion-project.md#systemflow),
[`BeanExplainer`](../09-remotion-project.md#beanexplainer),
[`Whiteboard`](../09-remotion-project.md#whiteboard),
[`TerminalDoc`](../09-remotion-project.md#terminaldoc),
[`UnderTheHood`](../09-remotion-project.md#underthehood),
[`CaseFileStory`](../09-remotion-project.md#casefilestory),
[`PaperDiorama`](../09-remotion-project.md#paperdiorama),
[`ArchiveEngraving`](../09-remotion-project.md#archiveengraving),
[`EditorialCollage`](../09-remotion-project.md#editorialcollage),
[`StorybookReveal`](../09-remotion-project.md#storybookreveal),
[`PuppetHistory`](../09-remotion-project.md#puppethistory),
[`MidcenturyHowTo`](../09-remotion-project.md#midcenturyhowto),
[`ComicPanels`](../09-remotion-project.md#comicpanels) and
[`ProcessCast`](../09-remotion-project.md#processcast) scenes. Each test file sits beside the code
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

## External styles

### `webpack-override.test.ts`

Covers `webpack-override.mjs`, the bundler override of every bundle that compiles the whole project.

- The external scene context matches only the named style's files, and nothing when no style is
  named. An id outside the `ext_` namespace is refused before it reaches a regular expression.
- The override adds the `@tubematic/scene-api` alias and the context rule.
- A real webpack compile with two packages, one of which does not parse: the broken package's own
  bundle fails, and a bundle for the other style or for no external style still builds.
- The generated-scene context matches the named video's scenes and the legacy flat files, treats a
  legacy id's dots and spaces as plain characters, and stays whole when no video is named. A real
  compile where another video's scene imports a missing package still builds this video's bundle.

Trap: the composition's `import()` of `./scenes/external/${src}.tsx` is a webpack context, which
compiles every matching file into every bundle. Without the context rule, one installed package that
fails to compile breaks every render on the install.

### `src/sceneApi/v1.test.ts`

Pins the names `src/sceneApi/v1.ts` exports, the scene API v1 that installed packages import as
`@tubematic/scene-api`.

Trap: an installed package compiles against these names. Removing or renaming one breaks packages
already installed, so a breaking change is a new `v2.ts` and a new `SCENE_API` in
`tubematic_core/external_styles.py`, never an edit to this list.

## Caption looks

### `src/scenes/installed/subtitleLooks.test.ts`

Covers the `tags`, `highlight` and `karaoke` looks of `Subtitles.tsx`
([Grouping words](../09-remotion-project.md#grouping-words)).

- A word's tag has the same tilt and torn edge on every frame and every render, and two words get
  different edges. The torn outline stays inside the tag's box.
- A tag pops from 0.6 past 1 and is back at 1 from its fourth frame, so a still tag costs nothing to
  repaint.
- The marker under an emphasis word starts at the word's first frame, wipes in over 8 frames and
  holds.
- A word keeps the text colour until its start frame, then turns to the accent for good: the
  default `#FFD221`, or the one the config names. The look has no pop and no dimming of the words
  still to come.

## Low-Poly Skit

The tests sit beside the kit in `src/cartoon3d/lowpoly/`. They run under node, with no browser: a
test that needs a canvas stands in a stub that accepts every call.

### `lowpoly/poses.test.ts`

Covers `poses.ts` and `cycles.ts`.

- A pose is applied by meaning (forward, out, bend), so the left and right arms mirror and a hand
  goes where its name says. Lying lays the figure on its back above the floor; sitting puts the feet
  on it. A pose leaves what it does not name at rest.
- A snap lands in the frames given with no anticipation, a track holds and then snaps on its key.
- A step lands every 11 frames, the legs swing in opposition, the jig alternates its lifts every
  5 frames, and a crowd's idles differ by seed.

Trap: the left shoulder's out is positive z and the right's is negative, and a swing forward is a
negative x rotation. A pose written the other way round passes its own look and breaks every mirror.

### `lowpoly/kit.test.ts`

Covers `figure.ts`, `faces.ts`, `crowd.ts`, `fx.ts` and `diorama.ts`.

- The figure stands one unit tall on the floor with about two dozen parts at most, and a seeded
  outfit is the same on every render.
- A face swap replaces the previous face, and every face merges into one geometry for the crowd.
- A crowd is a few dozen instanced meshes however many people it holds, hides the optional parts
  (hair variants, stubble) a member lacks, and members of different phase buckets are posed
  differently.
- A burst pops on its frame, holds and goes; debris falls and is gone after its life.

### `lowpoly/camera-moves.test.ts`

Covers `joltAt`, `jolted` and `whip` in `camera.ts`: a jolt starts on its hit frame, rings and is gone
after six frames, hits add, and the camera and its look point move together so the view does not
tilt. A whip holds before and lands after, and its blur peaks in the middle. The shared
`camera.test.ts` keeps covering the moves Cartoon 3D uses.

### `lowpoly/examples/dig/dig.test.ts`

Covers the worked example the skill points at: its shots tile the video with about one shot a second,
every set builds and poses on every frame of its shots, every camera is finite, and only the one
shot that says so is blurred. A skill example that stops running sends an agent into a copy of the
fault.

## Insert scenes

### `src/inserts/transitions.test.ts`

Covers `src/inserts/transitions.ts`, how an insert scene goes in and out over its main style
([Main styles and inserts](../10-scene-authoring.md#main-styles-and-inserts)).

- An unknown or missing transition reads as a cut.
- The way in runs over the frames before the insert's window and the way out over the frames after
  it, so the whole window is fully in; a cut shows the insert only during its window.
- The insert covers the frame only when fully in, so the main style is never hidden while it still
  shows. A dip veils the main in the canvas colour before the insert fades up; a push moves the main
  out as the insert comes in; a wipe uncovers the insert from the right.
- A glitch tears the insert in over 4 frames: the same frame always gives the same bands, a later frame
  never shows fewer bands than an earlier one, the main layer jolts the other way from the insert, and the
  insert covers the frame only at full progress (`glitchBands`).
- `activeInsert` finds the window a frame falls in.
- `heldFrame` is the way in plus the insert's `firstFrames`, never before the way in ends and never
  past the window: the frame `CompositionBuilder` freezes the scene on until then, so no insert opens
  on an empty board.

### `src/scenes/installed/codeScenes/codeScenes.test.ts`

Covers `codeScenes/contract.ts`, `tokens.ts` and `morph.ts`
([Code Scenes](../10-scene-authoring.md#code-scenes)).

- The languages, limits, timings and band equal `mcp/tests/fixtures/code_scenes_contract.json`, and
  the fixture's font sizes, typing frames and output panes come out the same as in
  `mcp/code_scenes.py`.
- The largest code the limits allow, a callout and a full output pane fit inside the band at 32 px
  or more.
- Every language colours without throwing, pieces keep their columns, and keywords take a colour of
  their own.
- The morph keeps unchanged pieces still, moves the pieces a new line pushes down, fades new pieces
  in and removed ones out.

### `src/scenes/installed/formatPacks/formatPacks.test.ts`

Covers `formatPacks/contract.ts` and `draw.ts` ([Format Packs](../10-scene-authoring.md#format-packs)).

- The formats, limits, timings, band and lists equal `mcp/tests/fixtures/format_packs_contract.json`;
  wrapping and thread heights come out as in `mcp/format_packs.py`, and the largest thread and the
  phone stay inside the band.
- Fiction-range phone numbers are told from real-looking ones the same way as the validator.
- Every change is listed in order with the insert's first frame first; rows ease on the card's
  curve, and marks are drawn as single paths.

The Code Scenes and Format Packs tests also pin the watermark's position and keep-out line
(`src/watermarkBox.ts`) to their fixtures, and check that the Code Scenes header and every Format
Packs top-row text end left of it, so a lifted insert never puts text under the mark.

### `src/scenes/installed/fitText.test.ts`

Covers `fitText.ts`, the width estimate that sizes a one-line text down to fit its box and counts a
wrapped text's lines ([Format Packs](../10-scene-authoring.md#format-packs)). Its widths, fitted
sizes and line counts equal `mcp/tests/fixtures/text_fit_contract.json`, which `mcp/text_fit.py`
runs too; wide letters count wider than narrow ones, the base size is kept when the text fits, a
long wide line shrinks until its estimate fits, and the size never goes under the minimum.

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

## Paper Diorama

### `src/scenes/installed/paperDiorama/paperDiorama.test.ts`

Covers `contract.ts`, `stage.ts`, `paint.ts`, `critter.ts` and the shipped props
([Paper Diorama](../10-scene-authoring.md#paper-diorama)).

- The pop, a prop's box in a slot, the stage scale, the banner's font size and the critter's box are
  computed as in the shared cases `mcp/tests/test_paper_diorama.py` runs.
- An item is hidden before its frame, pops in, moves to another slot, swaps its prop and leaves on
  its events, and the critter changes its face on its event.
- A torn reveal grows over its frames, and a ring is drawn partway when it is partly through.
- A rounded rectangle's outline stays inside its box with a rough edge of about a pixel.
- Every shipped prop uses the palette and keeps its pieces inside its box, the critter is drawn
  inside its own box in every expression, and every room has its picture.

## Archive and Engraving

### `src/scenes/installed/archiveEngraving/archiveEngraving.test.ts`

Covers `contract.ts`, `stage.ts` and `emblems.ts` ([Archive and Engraving](../10-scene-authoring.md#archive-and-engraving)).

- Title layout, the plate's push and crop, a still's point on the page, the ruler's scale and a
  cleaned title word are computed as in the shared cases `mcp/tests/test_archive_engraving.py` runs.
- The renderer draws the "Illustration" and "Recreation" footnotes itself, and a person has no
  picture, face or portrait field in the contract.
- The ruler's marker slides from one year to the next, a document line writes on and a route is drawn
  dot by dot, and the magnifier goes to the side away from its point.
- Plates are numbered in Roman numerals.
- Every emblem is drawn inside the roundel's field and the ring stays inside its box.

## Editorial Collage

### `src/scenes/installed/editorialCollage/editorialCollage.test.ts`

Covers `contract.ts`, `stage.ts` and `paint.ts` ([Editorial Collage](../10-scene-authoring.md#editorial-collage)).

- The stepped motion, the station layout, the camera, the headline layout, a typed index line, a
  figure's text and a cleaned headline word are computed as in the shared cases
  `mcp/tests/test_editorial_collage.py` runs.
- Stations zig-zag down the desk, a column each side. The camera rests, then glides for
  `TIMING.glide` frames from a station's start, and never scales.
- Pieces move on twelve steps a second, the string sags below the straight line between its pins, the
  pen ellipse is an unclosed stroke, and a figure counts up from zero over `TIMING.count` frames.
- Every hero kind, at every picture aspect, stays inside the station's zones.
- The renderer paints the "Illustration" and "Recreation" notes itself, which no data can switch
  off, and the contract has no field for a person's face.

## Storybook Reveal

### `src/scenes/installed/storybookReveal/storybookReveal.test.ts`

Covers `contract.ts` and `stage.ts` ([Storybook Reveal](../10-scene-authoring.md#storybook-reveal)).

- The title size, the picture's fit in the panel, the push and where the colour lands are computed as
  in the shared cases `mcp/tests/test_storybook_reveal.py` runs.
- The title wipes in (whole at once on the first page), the pencil wipes in (whole at frame 0 on a
  first page that opens on it), and the push holds until the colour has landed and never goes past it.
- A square still fills the panel's height, whole and centred, a tall one stays whole inside the panel,
  and the push keeps its focus point.
- The colour flood starts left of the panel and ends right of it even at its softest edge, runs from
  top to bottom with a ragged edge, and the page curl turns the old page away over `TIMING.curl`
  frames from the bottom-right corner.
- The scene's source holds no SVG filter, gradient or blur, which keeps its render cost low.

## Puppet History

### `src/scenes/installed/puppetHistory/puppetHistory.test.ts`

Covers `contract.ts`, `stage.ts`, the library and the map
([Puppet History](../10-scene-authoring.md#puppet-history)).

- The constants agree with the shared cases `mcp/tests/test_puppet_history.py` runs, and running
  `character-tools/sync-contract.mjs` leaves the fixture and the style pack unchanged, so a
  catalogue or limit changed without the sync fails here.
- The library draws every costume, set and prop the contract lists, and every set keeps its decor
  on stage and off the caption band.
- The stage opens with the first puppet in place at frame 0. A puppet slides in from the nearest
  edge and stops dead in its slot, a puppet in the right slot faces left, a swapped costume lasts
  into later beats, and a card line is struck out before the new value is scrawled. Beats change
  with a hard cut.
- A sign's centre is pulled in from the frame's edges for a wide sign in a side slot (`signX`, the
  cases `mcp/tests/test_puppet_history.py` runs).
- The map knows today's countries by `world-atlas`'s names and fits the focus countries by their
  largest landmass, so a far territory does not pull the map across an ocean.

## Mid-century How-To

### `src/scenes/installed/midcenturyHowTo/midcenturyHowTo.test.ts`

Covers `contract.ts`, `stage.ts`, the presenter's arm and the object library
([Mid-century How-To](../10-scene-authoring.md#mid-century-how-to)).

- The constants and the geometry (object, label, inset and presenter boxes, the arm's reach, a
  screen's lines, the blink) agree with the shared cases `mcp/tests/test_midcentury_howto.py` runs.
- Running `character-tools/sync-contract.mjs` leaves the fixture and the style pack unchanged, so a
  catalogue or limit changed without the sync fails here.
- The library draws every object the contract and the pack list, and each object's acts have
  distinct names.
- The `point` and `present` poses aim the glove at the object, and each pose's bitmap box holds its
  arm and glove.
- The worked example opens on the title card, walks the steps and ends on the summary, where the
  presenter stands on the right; a close-up shot has no presenter.
- A press lands on the row its act lights and uses the presenter's own hand within reach and the
  hose arm from the edge out of it; the hand pulls back before the press, holds, then returns. Each
  shot starts empty.

## Comic Panels

### `src/scenes/installed/comicPanels/comicPanels.test.ts`

Covers `contract.ts`, `stage.ts` and the library
([Comic Panels](../10-scene-authoring.md#comic-panels)).

- The constants and the box helpers (balloon and sound-effect sizes, a character's box) agree with
  the shared cases `mcp/tests/test_comic_panels.py` runs.
- Running `character-tools/sync-contract.mjs` leaves the fixture and the style pack unchanged, so a
  catalogue or limit changed without the sync fails here.
- Every layout's panels lie on the page under the title bar, and the library draws every prop the
  contract lists.
- The stage opens on page 1, panel 1, framed and inked at frame 0. The camera glides to the next
  panel over `TIMING.read` frames and then holds still (the two top panels of a page share one
  framing with the title bar), pulls back to the whole page at the splash,
  and punches in and shakes on a hit before it settles. An item pops in and lands on 1, so a
  held picture never repaints, and a panel or item that starts at frame 0 is drawn finished.

## Process Cast

### `src/scenes/installed/processCast/processCast.test.ts`

Covers `contract.ts`, `stage.ts` and the library
([Process Cast](../10-scene-authoring.md#process-cast)).

- The constants and the geometry (body sizes, slot positions and counts, where a prop sits, clone
  ids, the blink) agree with the shared cases `mcp/tests/test_process_cast.py` runs.
- Running `character-tools/sync-contract.mjs` leaves the fixture and the style pack unchanged, so a
  catalogue or limit changed without the sync fails here.
- The library draws every prop the contract and the pack list, and every kind of furniture.
- The worked example brings its first character in at frame 0 at the first station with the camera
  there; a split shows its clones as silhouettes for the first frames and a merge takes them back;
  a join adds the cubes up and removes the other body; the camera glides to the next station while
  the character makes the trip; a focus holds until it is cleared and ends when its actor leaves, so
  the others at the station are not left shrunk.

## Night Signal

### `src/scenes/installed/nightSignal/nightSignal.test.ts`

Covers `contract.ts`, `parts.ts` and `stage.ts`
([Night Signal](../10-scene-authoring.md#night-signal)).

- The constants, and events, still stretches, tears, an item's position, timecodes and text fits, are
  computed as in the shared cases `mcp/tests/test_night_signal.py` runs.
- The catalogues the pack carries are the ones the renderer draws, every library part draws, and
  every part stands on the ground inside the box a custom part is held to.
- The stage knows which scene is on screen, tears into a scene around its start and not at a hard
  cut, pushes in slowly and never past the camera's limit, pops an item in with an overshoot, walks it
  on its step and reddens the threat on its frame. A camera clock runs on through its minutes and hours.

## Flat Vector Science

### `src/scenes/installed/flatVector/flatVector.test.ts`

Covers `contract.ts`, `props.tsx` and `stage.ts`
([Flat Vector Science](../10-scene-authoring.md#flat-vector-science)).

- The constants, and events, still stretches, counters, steps and widths, are computed as in the
  shared cases `mcp/tests/test_flat_vector_science.py` runs.
- The pack lists what the renderer draws and nothing else; every backdrop has a look and every prop a group, a
  box and a drawing, and a prop's longest side is drawn at its size.
- The stage knows which shot is on screen and runs each transition at its own frames, opens a ladder
  on its first picture before the first rung's word, pops an item in with an overshoot and never stops
  drifting, and rolls a descent's depth from one layer to the next.

## Isometric Infographic

### `src/scenes/installed/isometric/isometric.test.ts`

Covers `contract.ts`, `kit.ts` and `stage.ts`
([Isometric Infographic](../10-scene-authoring.md#isometric-infographic)).

- The constants and the shared cases the validator runs
  (`mcp/tests/test_isometric_infographic.py`) agree (the footprint of a set of solids included), and the
  pack lists what the kit draws and nothing else.
- The projection is true isometric and shades three tones from one colour, a solid named with a palette
  colour shades too; the whole board is in view at zoom 1 and every prop's solids stand on its footprint.
- A camera move that starts while another still glides starts from the view on screen, so it never jumps.
- A prop drops in from above with a squash, and one with no `enter` stays where it is.
- The pin layout leaves a lone pin and pins far apart at their default place, moves the second of two
  close pins to the other side or up a lane (up a lane only when `side` fixes the side or the other side
  would leave the frame), never puts a label outside the safe margins when a clear place exists, and gives
  the same answer every time it is asked.

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

### `renderer/remotion/cartoon-tools/merged-public.test.ts`

Covers `renderer/remotion/cartoon-tools/merged-public.mjs::syncMergedPublic`, the directory the
[stills server](../11-rendering-and-review.md#the-stills-server) and its local fallback serve as
`/public/`.

- A video's files and the project's fonts and watermark come out of one directory. A folder is a link
  and a plain file is a copy.
- A video filed after the first sync is served by the next one, and a video that is gone is dropped.
- The jobs volume wins a name clash, and neither source directory is written to.

Trap: Remotion's static server answers 404 for a symlinked file, so the watermark must be a copy.
Without the fonts and the watermark a frame of a video fails on the image or draws its text in a
fallback font, which would make a preview misreport the text layout.

### `renderer/remotion/cartoon-tools/out-path.test.ts`

Covers `renderer/remotion/cartoon-tools/out-path.mjs::outPathError` and `planRequest`, the checks the
[stills server](../11-rendering-and-review.md#the-stills-server) runs on every file a request would
write, before it bundles or opens a browser.

- The paths the Cartoon 3D tools write (`<video_id>/cartoon/stills/…`, `<video_id>/cartoon/beatgate/…`)
  pass, and an output directory under a video's `cartoon/` folder passes.
- The folder `preview_frames` writes (`<video_id>/preview/…`) passes by the same rules. Look-alikes
  (`previews/`, `Preview/`, a file named `preview.png`, a `preview` that is not under a video) and a
  non-PNG in it are refused, as is a `preview/` that is a symlink.
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
