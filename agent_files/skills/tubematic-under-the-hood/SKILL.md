---
name: tubematic-under-the-hood
description: Author an Under the Hood narrated Short as data — plan close-up photographs of one physical object (at most 12), generate and check each with read_image, pin capital labels, outlines and gold field arcs to points of each photograph, add ticking counters, a big stat, a line chart and footnotes, pose the house presenter on the narrator's words — then write it with write_scene_config, validate and submit it
---

# Tubematic Under the Hood authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-under-the-hood` (its `visual_style` is `under_the_hood`). Also take it, on **Revising**, for
a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short in the dark "how it really works" look. The middle of the frame (from 24% to
70% of its height, the **plate band**) is a close-up photograph of the object the video is about, a
**plate**, pushing in slowly the whole time. On it, short capital labels sit in dark chips, each joined
by a thin line to the part it names; parts are boxed or bracketed in blue or gold; gold field arcs rise
from one part and bend toward another. A fast zoom into a point of one photograph cuts to a closer
photograph. Under the band, a row of monospace counters ticks and a tiny grey footnote keeps the
picture honest; in the bottom right, the house presenter (a cartoon bench technician) swaps whole poses
on the narrator's words. Captions sit near the top and build word by word, with the key word in a blue
selection box.

**You write data, never code.** The whole video is one installed scene, `UnderTheHood`, and everything
about this video is its `props.underTheHood`: the plates and, on each plate, events timed to the
narration. The presenter, the captions and every overlay are drawn by the renderer. You make the
photographs with `generate_image`; never call `generate_character` (the presenter is fixed).

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses an Under the Hood config that breaks any of these, and says which plate or
event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "UnderTheHood", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"underTheHood":
  {...}}}`.
- **Plates** are cuts: the first starts at frame 0, the others on a word (within 2 frames of a word's
  `startFrame`), each at least 1.5 seconds long, at most 30 plates.
- **Photographs:** at most **12 different ones per video**. `generate_image` refuses a 13th new name;
  reuse a photograph on another plate with a different `focus` and `zoom` instead. An `image` is the
  `public_path` `generate_image` returned. A plate with no `image` is a plain dark panel, for a chart.
- **The photograph covers the band.** At `zoom` 1 the `focus` must be `[0.5, v]` with v from 0.42 to
  0.58; a larger `zoom` lets the focus move further (table in `reference/contract.md`).
- **Pinned points stay visible.** Every `at`, `region`, `from` and `to` must be inside the plate band
  when the event starts and still inside at the end of the plate, because the slow push moves points
  away from the focus. Keep pinned points well inside the photograph's middle.
- **Chips** stay inside the band and the side margins, at least 40 px from the point they label, and
  never overlap another chip or the stat. No pinned point may sit under a chip or the stat.
- **Per plate:** at most 16 events, listed in frame order; at most 6 callouts, outlines, arc fans, stats
  and charts together; one counter row, one stat, one chart and one footnote. Callouts, outlines and
  arcs need a photograph; a chart needs a plate without one.
- **Timing:** a pose lands on a word, at least 8 frames after the last pose. Text (a callout, a
  footnote) starts at least 20 frames before its plate ends, or before the zoom that ends it (a
  zoom-through takes the plate's labels away 6 frames early). A number must finish and then be read:
  a stat starts at least 44 frames before (48 with a chip), a counter row 36, a chart its `duration`
  plus 20 (plus 4 with a chip).
- **Lengths:** a callout is at most 18 characters, a stat label 22, a chart label 24, a footnote 32, a
  chip 10, a unit or sign 3. A stat or chart number is at most 9999999 either way; the stat must fit
  the frame and the chart's value 900 px (about 9 characters). A counter row of four takes up to 3
  digits each, three up to 4, one or two up to 5.
- **Never still:** something new (an event, a pose or a plate) at least every 3.5 seconds.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, and the comments.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here, and a word's index in this list is
   what `subtitles.emphasis` uses.

## Step 1 — plan the plates

Read the segments' `visual` briefs. The video goes **one layer deeper per plate**: the object whole,
then the part under the surface, then the part inside that. A new plate when the camera goes a layer
deeper or the narration moves to another part; not one per sentence. A plate holds 3 to 8 seconds
with something new every 1.5 to 3. Plan the photographs first and count them: 5 to 8 is usual, 12 is
the ceiling. A plate can reuse a photograph with a different `focus` and `zoom` (a closer look at the
same thing costs nothing).

A beat about a value that changed over time (a price over a year, a signal across a scan) is a chart
plate: no photograph, a `chart` event. A beat about numbers on a part is a `counters` row or a `stat`
on that part's plate.

## Step 2 — make and check the photographs

Call `generate_image(video_id, image_name, prompt, aspect_ratio="1:1")` for each planned photograph,
with this prompt shape (fill in the subject):

> Photorealistic studio macro photograph of **<the subject, the part, the angle>**. Pure black seamless
> background, soft rim light, shallow depth of field. The subject sits in the centre of the frame and
> stays inside the middle 60 percent of it, with plain black all around. No text, no labels, no logos,
> no watermark, no diagrams, no arrows.

Name the part and the view precisely: "a cut-away cross-section of a smartphone touchscreen as three
stacked slabs seen from a low three-quarter angle", not "how a touchscreen works". A cut-away or an
exploded view is how the inside of something is shown.

Open every photograph with `read_image(video_id, image_name)` (the grid is on). Check that it shows the
thing the narration names, that a cross-section is plausible, and that no text or logo is printed in
it. Regenerate under the same name if not (a regeneration replaces it and does not count against the
12). Then **read every anchor off the grid**: the [u, v] of each part you will label, box or join with
arcs (u left to right, v top to bottom, 0 to 1). Write them down per photograph before Step 3; a label
pinned to the wrong part is the defect this style's review looks for first.

## Step 3 — plates and events

A plate is `{"start", "image", "focus", "zoom", "enter", "through", "events"}`:

- `focus` is the [u, v] of the photograph at the band's centre (default [0.5, 0.5]); `zoom` from 1 to 3
  (default 1). Point the focus at what the plate is about, and raise `zoom` for a closer look.
- `enter` is `cut` (a 3-frame cross-fade, the default) or `zoom`: the camera rushes into `through`, a
  [u, v] of the **previous** plate's photograph, and cuts to this one. Use `zoom` when this plate is
  the inside of that point ("under the glass"): it is the style's signature move, two or three times a
  video. The camera fills the band with what lies around `through` at 4x, so put it on a lit, detailed
  part of the photograph, never on the black backdrop or a dark surface, or the rush dips to black.

| Event | When | Fields |
|---|---|---|
| `callout` | the word that names a part | `text` (the part's name), `at` [u, v] on the photograph, `chip` [x, y] where the label sits (fractions of the frame), optional `tone` `white`, `blue`, `gold` |
| `outline` | the part the line is about | `region` [u0, v0, u1, v1], optional `tone`, `shape` `box` or `bracket` |
| `arcs` | a field, a force, a flow of charge or heat | `from` and `to` [u, v], optional `count` 3 to 9 |
| `counters` | values that change on the part | `values`: 1 to 4 `{from, to}` whole numbers (changed ones turn bold white) |
| `stat` | the one number of the beat | `value`, optional `from`, `decimals`, `prefix`, `suffix`, `label`, optional `chip`, `place` `upper` or `lower` |
| `chart` | a value over time, on a plate with no photograph | `points`, `label` (the axis), optional `duration`, `decimals`, `prefix`, `suffix`, `chip` |
| `footnote` | the first plate of a magnified view, or of illustrative numbers | `text`: "Magnified illustration", "Values illustrative", "Not to scale" |
| `pose` | the presenter reacts, on the word that causes it | `pose` |

**Placing a chip.** Put the chip in the dark part of the photograph near its part, on the side away
from the subject, and let the line cross a short gap: chip x 0.15 to 0.3 for a part on the left, 0.7
to 0.85 for one on the right, chip y from 0.27 to 0.68. Keep chips apart (one chip's box is its text
length times 27 px plus 44, by 60 px). Two or three callouts per plate read; more crowd the subject.

**The presenter.** Poses: `idle` (the start), `point` (up at the photograph, the default for "this
part"), `present` (an open hand toward it), `explain`, `think` (a question), `surprise` (a reveal),
`hands_on_head` (something huge or alarming), `thumbs` (the payoff), `shrug` (nobody knows). Pose on
the word that causes the reaction, every 1.5 to 4 seconds; a pose that contradicts the line is a
defect the review reports. The mouth moves by itself while the narration speaks.

**Numbers.** Say a number in the narration and show it once: a `stat` for the one number of a beat
("5 µm", "2 pF", "+429%"), `counters` for several values changing together, a `chart` for a value over
time. Use the real figure from the script; put "Values illustrative" in a footnote when the numbers
are only representative.

## Step 4 — captions

Leave the caption look to the style: either leave `subtitles` out, or set only `emphasis`, the indexes
of the key words in the timeline's word list (the part's name, the number, the turn of the line). At
most one word in 5, and usually one per sentence. The style fills in the rest of the caption look; any
other key you set overrides it, so leave them alone.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` from the timeline, `"canvas": "dark"` (or
   leave it out) and the one scene. It reads each photograph's shape from its file; you never write
   `aspect`. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   chips, the stat and the chart text in a browser; an overlap is a measurement, so move a chip or
   shorten a label.
3. `submit_render(video_id)`.

In the handback, say how many plates and photographs you made, which zoom-throughs you used, and any
photograph you regenerated and why.

## Revising

Read the comments on `get_video`. A comment about the picture (a label on the wrong part, a crowded
plate, a photograph that shows the wrong thing) is fixed in `props.underTheHood`, or by regenerating
that photograph under its own name and re-reading its anchors: then write, validate and submit again as
above. Never change the video's style. If the voice was redone, the word frames have changed: re-time
every plate and event from the new timeline, and recount the `emphasis` indexes.
