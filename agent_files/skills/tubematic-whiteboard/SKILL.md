---
name: tubematic-whiteboard
description: Author a Whiteboard narrated Short as data — split the narration into regions of one big board, fill each region's layout with handwritten text, formulas, doodles, arrows and marks timed to the narration's words, and end on the recap — then write it with write_scene_config, validate and submit it
---

# Tubematic Whiteboard authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-whiteboard` (its `visual_style` is `whiteboard`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its `style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that works an idea out on one big whiteboard while the narrator explains
it. The camera rests on one **region** of the board at a time; a floating marker writes and draws
there a moment after the narrator says each thing, in three inks; when the narration moves to the next
step the camera glides to the next region, and the regions already written stay on the board. The
video ends with the **recap**: the camera pulls back to the whole board and each region gets a circled
number, so the viewer sees the argument as one map.

**You write data, never code.** The whole video is one installed scene, `Whiteboard`, and everything
about this video is its `props.whiteboard`: the regions, their layouts, the items in each layout's
slots, and the frame the recap starts. The renderer does the positions, the handwriting, the marker,
the camera and the captions. You give no coordinates and no sizes, except inside a doodle you draw
yourself (see **Drawing your own doodle**).

There are no images in this style (never call `generate_image` or `generate_character`) and no
people: a role ("the saver", "an attacker") is the `person` or `group` doodle with a label, or just a
written word.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json`, timed to `reference/example-timeline.json`. Read all three before you
write.

## Rules the tools enforce

`write_scene_config` refuses a Whiteboard config that breaks any of these and says which region and
item is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "Whiteboard", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"whiteboard": {...}}}`.
- **2 to 6 regions.** The first starts at frame 0, each later one on a word (within 2 frames of a word's
  `startFrame`), each at least 102 frames long (the camera's 42-frame glide plus 2 seconds).
- **Every item's `at` is a word's `startFrame`** (within 2 frames). Items draw one at a time in the
  order you list them, so each `at` is later than the one before. In regions after the first, the
  first item comes at least 30 frames after the region starts (the camera is still gliding).
- **Fit.** Text, formulas and labels must fit their slot (the table below). Only characters the
  handwriting font has: letters, digits, common punctuation, `× ÷ ² ³ ° ± ½ % $ € £`. No `→`, `√` or
  `π`: write `->`, `sqrt` or `pi`.
- **The marker must keep up.** Each item needs a minimum number of frames before the next item's `at`
  (body text about 0.9 frames a character, a doodle 18 frames plus its label, a mark or arrow 8). The
  last item of a region must also be finished 15 frames before the camera leaves. The tool tells you
  which item is too tight.
- **Never still.** An item, a region or the recap starts at least every 3.5 seconds.
- **The recap** starts on a word and runs to the end of the video: at most 8 seconds, and at least
  2 seconds or the time every region's number needs to pop and be seen (45 frames plus 6 for each
  region after the first, so 75 frames for six regions), whichever is longer.
- **Marks and arrows** point at earlier items of the same region; one highlight per region.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments, and
   `mascot`.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1 — split the narration into regions

A region is one step of the argument: the setup, the first year, the second year, the result. Start a
new region on the first word of the sentence where the step changes. Most Shorts need three to five.
Leave the closing sentence (the takeaway) for the recap: `recapFrame` is its first word.

## Step 2 — a layout for each region

| Layout | Slots | Use it for |
|---|---|---|
| `stack` | `1`, `2`, `3`, `4` (rows, top to bottom) | a list, or a derivation built line by line |
| `pair` | `top`, `left`, `right`, `bottom` | two things and how one leads to the other (an arrow from `left` to `right`) |
| `compare` | `left_title`, `right_title`, `left_1`..`left_3`, `right_1`..`right_3` | two columns side by side: before and after, A against B |
| `focus` | `top`, `center`, `bottom` | one big doodle with a line of writing above and below |

You need not fill every slot. Empty slots stay empty board.

## Step 3 — what goes in the slots

The board is a teacher's notes, never the script: write the keyword, the number, the formula, the
three-word claim. The captions already show the spoken words, so a board line that repeats the
sentence is wasted.

| Kind | Fields | Notes |
|---|---|---|
| `text` | `slot`, `text`, optional `big`, `ink` | `big: true` for the one title of a region (one line) |
| `formula` | `slot`, `text`, optional `ink` | one line, written character by character: `100 × 1.1 = 110` |
| `doodle` | `slot`, `doodle`, optional `label`, `ink` | a drawing from the library below |
| `arrow` | `from`, `to`, optional `ink` | between two earlier items of the region; never across a third item |
| `highlight` | `target` | yellow marker behind a text or formula item; once per region, on the phrase that matters |
| `underline` | `target`, optional `ink` | under a text or formula item |
| `circle`, `box` | `target`, optional `ink` | around any earlier item: the answer, the surprising number |
| `cross` | `target`, optional `ink` | strike an item out: the wrong idea, the old way |

Every item also has an `id` (lowercase letters, digits, underscores, unique in its region) and `at`.

Roughly what fits (the tool has the exact answer):

| Slot | Text | Big title | Formula | Doodle label |
|---|---|---|---|---|
| `stack` rows, `pair` top/bottom, `focus` top/bottom | 2 lines of about 30 characters | about 22 characters | about 25 characters | about 27 characters, beside the doodle |
| `pair` left/right | 2 lines of about 14 | about 10 | about 11 | about 16, below the doodle |
| `compare` cells | 2 lines of about 14 | about 10 | about 11 | one short word |
| `compare` titles | 1 line of about 14 | about 10 | about 11 | no label (the doodle is too small) |
| `focus` center | 2 lines of about 30 | about 22 | about 25 | about 20, beside a large doodle |

**Doodles**, by name: `atom`, `battery`, `brain`, `calendar`, `car`, `cart`, `chart_down`, `chart_up`,
`check`, `chip`, `clock`, `cloud`, `coin`, `cross`, `database`, `document`, `drop`, `envelope`,
`factory`, `flame`, `gear`, `globe`, `group`, `heart`, `hourglass`, `house`, `key`, `laptop`,
`lightbulb`, `magnet`, `magnifier`, `money_bag`, `padlock`, `person`, `phone`, `question`, `rocket`,
`scales`, `server`, `shield`, `star`, `sun`, `target`, `tree`, `warning`, `wifi`. Pick the nearest
meaning and let the label say the rest. (The `cross` doodle is an X drawn as a picture; the `cross`
item kind strikes out another item.) When none of them carries the meaning, draw your own (below).

**Inks** each mean one thing for the whole video: `black` (the default) for structure and plain
writing, `blue` for the second concept or the thing that flows, `orange` for the keyword or the part
you are tracking. Use the highlight for the single phrase the region exists to say.

### Drawing your own doodle

Draw one only for a specific object the step needs and the library has no doodle for: a bicycle, a
dam, a lever. When a shipped doodle carries the meaning, use it, even if yours would be a little more
exact. A video holds at most 8 of its own.

1. Read `reference/doodles.json`, the shipped library in the format you write. Find the shipped
   doodles closest to your object and copy how they are built: the outline first, then a few details;
   2 to 8 strokes; simple shapes; about 6 units of margin inside the box.
2. Write yours in `props.whiteboard.doodles`: `{"bicycle": [<stroke>, ...]}`. A stroke is a list of
   segments joined into one line, and a segment is one primitive:

   | Primitive | Value |
   |---|---|
   | `line` | `[[x, y], ...]`, an open line through the points |
   | `poly` | `[[x, y], ...]`, closed back to the first point |
   | `curve` | `[[x, y], [cx, cy], [x, y]]`, start, control point, end |
   | `arc` | `[cx, cy, rx, ry, from, to]`, angles in degrees: 0 is right, 90 is down |
   | `circle` | `[cx, cy, r]`, optionally a 4th value for the angle it starts at |
   | `ellipse` | `[cx, cy, rx, ry]`, optionally a rotation in degrees and a start angle |
   | `rect` | `[x, y, w, h]`, optionally a corner radius; without one it overlaps 1 unit above its top-left corner, so keep its top at 1 or more |
   | `star` | `[cx, cy, inner radius, outer radius, points]` |
   | `gear` | `[cx, cy, inner radius, outer radius, teeth]` |

   Coordinates are in a 100 x 100 box, y pointing down, and every point must stay inside it. Two
   segments in one stroke are joined by a line, so start a new stroke wherever the pen lifts.
   At most 20 strokes and 400 points (a circle is about 47).
3. Never draw a person, a face or a body: a role is the shipped `person` or `group` doodle.
4. Call `preview_doodles` with the same object. It checks each doodle against the rules above and shows it beside
   two shipped ones at the same scale. Look at it: if it does not read at once as the thing it is meant
   to be, simplify it and preview again. Then use its name as an item's `doodle`, like a shipped one.

A doodle you define but do not draw is refused, and its name may not reuse a shipped name. The worked
example draws a `piggy_bank` this way.

## Step 4 — timing

Set each item's `at` to the `startFrame` of the word it shows: the marker starts about 12 frames later,
which reads as the hand following the voice. The one exception is the item that opens the video:
region 1's first item at `at: 0` need not be on a word, and the marker is already drawing it on the
first frame. List items in the order they should be drawn. Give
each item room: a long phrase on two quick words is refused, so time it to an earlier word or shorten
it. Aim for something new every 1.5 to 3 seconds; a mark or an arrow is a cheap way to keep a region
moving while the narrator dwells on it. Do not draw what the narration does not say: a circle on a
number nobody mentions is a defect the review reports.

## Step 5 — captions and mascot

Leave `subtitles` out: the style fills in its own captions. If `get_video` has a `mascot`, add its cue
track as the mascot skill describes and keep the mascot out of the writing band (14% to 68% of the
height): the bottom band below the captions.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame` (the formula's line on what the first frame shows, `""` when the video has no formula). The first segment's role is `opening`. A `turn` or `reopen` segment needs a visible change on its first word, the `payoff` segment the video's strongest picture, and a segment with role `""` only its own brief. `get_video`'s `style.picture` says how this style does each; in short:

- Opening: region 1's first item is a `doodle` at `at: 0` that draws the first sentence's subject. It may sit before the first word, and the marker is already drawing it on the first frame. Never a blank board, and never words first.
- Turn or re-opening: a new region on its first word, or a doodle or arrow drawn at that word.
- Payoff: the region the answer lives in, with the biggest doodle and its highlight. The recap is this style's ending.

`validate_job` returns warnings (advisory, never blocking) when region 1 does not open on a doodle at frame 0 or when a `turn`, `reopen` or `payoff` segment has no region, doodle, arrow or recap starting within about 0.4 s of its first word. Fix what is a real miss; say in the handback why any warning stands.

## Step 6 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out) and the one scene. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures each
   region's writing in a browser; an overlap is a measurement, so move or shorten the text.
3. `submit_render(video_id)`.

In the handback, say how many regions you made, the step each shows, and anything you left out to
stay within the limits.

## Revising

Read the comments on `get_video`. A comment about the board (wrong writing, a missing step, a crowded
region, a mark at the wrong moment) is fixed in `props.whiteboard`: edit the regions and items, then
write, validate and submit again as above. Never change the video's style. If the voice was redone,
the word frames have changed: re-time every region, item and the recap from the new timeline.
