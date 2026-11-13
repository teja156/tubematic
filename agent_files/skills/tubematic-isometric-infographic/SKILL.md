---
name: tubematic-isometric-infographic
description: Author an Isometric Infographic narrated Short as data — one thing's journey across a little isometric board of flat three-tone blocks — lay out 1 to 3 boards (ground areas, props on tiles, routes that draw ahead of movers, label pins, camera glides, lifts, cutaways, explodes), time them to the narration with a readout and a legend, build a prop of your own from the kit's solids when the library lacks one and look at it with render_style_parts, then write it with write_scene_config, validate and submit it
---

# Tubematic Isometric Infographic authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-isometric-infographic` (its `visual_style` is `isometric_infographic`). Also take it, on
**Revising**, for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that follows ONE thing on its journey through a system of places: a parcel
from warehouse to door, a request from a phone to a data centre and back, water from a reservoir to a
tap. The world is one floating isometric **board** of 10 x 10 tiles on cream paper, drawn in flat
three-tone blocks: forest, a river, a city of small blocks, and the **props** you place on it (buildings,
vehicles, towers, billboard people). The followed thing travels a **route** that draws itself ahead of
it; buildings drop in with a squash; **pins** name places with a big number; the camera **glides** in on
one place and back out; a building **lifts** while everything else fades back; a wall **cuts away** to
show what is inside; a stack **explodes** into its layers. A title and a **readout** (a big number with a
row of small cubes counting it) sit at the top; a **legend** of colours can rise in at the foot to end
the video. The engine fills free land with trees and free city with blocks, so a handful of props make
a full board. Captions sit in a white card under the board.

**You write data, never code.** The whole video is one installed scene, `IsometricInfographic`, and
everything about it is its `props.isometric`. You never call `generate_image` or `generate_character`.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses an Isometric Infographic config that breaks any of these, and says which
board and which field:

- A title of 1 to 22 characters. 1 to 3 boards; the first starts at frame 0, every other on a word, each
  lasting at least 2 s (a new board is a hard cut: use it only when the place changes).
- Every frame you give is inside its board and within 2 frames of a word's start.
- A board holds up to 8 areas, 1 to 14 props, up to 3 routes of 2 to 8 points, up to 4 movers, up to 4
  pins, up to 8 camera moves and up to 3 lifts, cutaways and explodes each.
- Props stand on the board (`at` from 0.4 to 9.6) and at least 0.6 tiles from each other; each has an id
  of its own. Routes stay on the board.
- A mover sets off no earlier than its route starts to draw: the line leads every move.
- A pin names a prop of its board: a label of 1 to 12 characters, a value of 1 to 8, a unit of up to 4.
- A camera move centres on a prop (`focus`) or the whole board, at a zoom from 1 to 2, in order.
- A cutaway opens a building that has an inside (`house`, `office`, `factory`, `warehouse`, `data_centre`, `shop`, `bank`, `hospital`, `school`, `power_plant`), with 1 to 3 props shown inside; an
  explode separates a stack (`server_rack`, `container_stack`).
- The readout has 1 to 8 steps in order, red at most once; its cubes count one per `per` units, at most 12.
- The legend has 1 to 5 entries of 1 to 12 characters and must fit the frame.
- Nothing may sit still for more than 4 seconds: a prop, a route, a mover, a pin, a camera move, a lift,
  a cutaway, an explode, a readout step or the legend must arrive on a word within every 4-second
  stretch (the drift, the clouds and things already moving do not count).
- Your own props: at most 6 in `customProps`, each at most 16 solids.

## Step 0 — read

`get_video(video_id)` for the style block (`style.extra` holds the props, colours, area kinds, rooms,
stacks and solids), `get_timeline(video_id)` for the words, the segments, their `beat`, `role` and
`insert`.

## Step 1 — lay out the board

Draw the board as a map of the journey: tile x runs down to the right on screen, y down to the left,
(0, 0) is the top corner and (10, 10) the bottom. Put the start near the top, the end near the bottom
corner, and the stations in between, so the route crosses the board. Cover the ground with areas
(`land`, `forest`, `city`, `sand`, `water`, `road`, `plaza`, `field`): `forest` and `land` fill with trees, `city` with blocks, `water` ripples, `road` gets
lane marks. Give each meaning one colour (`red`, `gold`, `slate`, `teal`, `green`, `blue`, `cream`, `grey`, `plum`) and keep it: the followed thing and its
route in `red`, say.

## Step 2 — props, routes and movers

Props come from the library: `house`, `office`, `tower_block`, `factory`, `warehouse`, `data_centre`, `server_rack`, `cell_tower`, `dish`, `router`, `phone`, `laptop`, `shop`, `bank`, `hospital`, `school`, `power_plant`, `wind_turbine`, `solar_panel`, `water_tower`, `tank`, `pipe`, `truck`, `van`, `car`, `bus`, `train`, `ship`, `plane`, `crane`, `container_stack`, `conveyor`, `tree`, `cloud`, `person`, `crowd`, `parcel`, `cube`, `coin`, `dam`, `silo`. Good movers: `cube`, `parcel`, `truck`, `van`, `car`, `bus`, `ship`, `plane`, `train`, `person`, `coin`. A prop with `enter` drops
in on its word; without it, it stands there from the board's start. A route's `points` are tiles along
roads and across the board; it draws ahead on its `at`, and its mover sets off on its own word (`back`
sends it home along the same line).

When the library lacks a thing, build it from the kit's solids (`box`, `cyl`, `cone`, `pyr`, `gable`) in `customProps`:
`{"id": "kiosk", "main": "teal", "height": 0.9, "solids": [...]}`, each solid in the prop's own footprint
(x and y from -0.8 to 0.8, z up from 0), back to front, coloured `main`, `accent` or a palette name. A box
takes `w`, `d`, `h` (and `layer` 0 to 4 if it is a stack's layer); a gable roof `w`, `d`, `h`; a cylinder,
a cone and a pyramid `r`, `h`. Then look at it: `render_style_parts(video_id)` (after
`write_scene_config`) draws your props on a patch of board beside a house.

## Step 3 — pins, the camera and the readout

- Pin a place when the narration names it, with its number when there is one.
- Glide in (`focus`, `zoom` about 1.5) when the narration goes into one place, and back out (`zoom` 1, no
  focus) before the next leg. A lift marks the stage the narration is at; a cutaway shows what happens
  inside a building; an explode opens a stack.
- The readout counts the running number the narration says aloud (hours, kilometres, milliseconds); put
  its last step in red when it is the total.

## Step 4 — captions

Leave `subtitles` out of the config. The style fills in its own caption look (the `card`); any key you
set overrides it.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame` (the formula's
line on what the first frame shows, `""` when the video has no formula). The first segment's role is
`opening`. A `turn` or `reopen` segment needs a visible change on its first word, the `payoff` segment
the video's strongest picture, and a segment with role `""` only its own brief. `get_video`'s
`style.picture` says how this style does each; in short:

- Opening: the board is on screen from frame 0 with the first sentence's place standing on it.
- Turn or re-opening: a camera glide, a building dropping in, a cutaway or a route drawing on its first word.
- Payoff: the stage the answer lives in lifted, with its pin and the readout.
- Ending: the camera back on the whole board and the legend rising in.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has nothing new within about 0.4 s of its first word. Fix what is a real miss; say in the handback why
any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. This style pushes into and out of an insert. The board is hidden while an insert
plays, so inside each insert's window nothing on the board, the readout or the legend changes. Start
the next board on the window's end (its last frame + 1), or let the board from before the insert carry
on. The "never still" rule does not count a window. With no marked segment, write no `inserts`.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` from the timeline, `"canvas": "light"` (or
   leave it out), the one scene and any `inserts`. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the pins,
   the title and the readout in a browser; an overlap is a measurement, so move a pin to its other
   `side`, shorten its text or glide the camera.
3. Before submit_render: check the opening, the turn and the payoff against the narration once more
   (every number on a pin or the readout matches what is said).
4. `submit_render(video_id)`.

In the handback, say what the followed thing is, its stations, which props you built yourself, and any
warning you left and why.

## Revising

Read the comments on `get_video`. A comment about the board, a pin, a route or the timing is fixed in
`props.isometric`; a comment about a prop you built is fixed in its `customProps` entry (look at it again
with `render_style_parts`). Then write, validate and submit again as above. Never change the video's
style. If the voice was redone, the word frames have changed: re-time every board and every event from
the new timeline.
