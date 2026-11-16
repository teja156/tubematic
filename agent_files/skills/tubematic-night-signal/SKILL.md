---
name: tubematic-night-signal
description: Author a Night Signal narrated Short as data — a deadpan warning told in glowing pictograms on black, one red threat per scene — plan the scenes (tableaux, a doorbell camera, a phone, RULE cards, a case card, a card of steps), time items, connectors, bubbles and marks to the narration, add your own pictograms from flat shapes if the library lacks one, then write it with write_scene_config, validate and submit it
---

# Tubematic Night Signal authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-night-signal` (its `visual_style` is `night_signal`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that warns the viewer about one danger, in the voice of a calm case file.
Every picture is a small scene of flat warm-white **pictograms** on a near-black field: faceless
round-headed people, animals and simple objects standing on one thin ground line, glowing softly as if
on an old screen. In each scene exactly one thing may be **red**: the threat (a stranger, a laptop that
is not yours, the door that should stay shut). A row near the top reads like a case file: `FILE 031`,
a short title, a row of small squares (one per scene) and a running timecode. Scenes change through a
glitch tear of two to four frames. Captions are spaced white capitals at 70% of the height.

The scene kinds:

| Kind | What it shows |
|---|---|
| `tableau` | Up to 4 pictograms in named slots on a ground line, in a setting (`night`, `street`, `room`, `plain`); a dotted connector between two of them; a thought or speech bubble holding an icon |
| `camera` | A doorbell camera panel (REC dot, clock, a label like `CAM 02 / FRONT DOOR`) framing a smaller tableau, with an optional button (`OPEN`, `TALK`) that a red stroke crosses out |
| `phone` | You behind a table and a large phone: a `message`, a `link` preview, a `qr` code being scanned, a `call` or an `alert`, with an optional mark (a green `check` once in a video, or a red `cross`) |
| `rule` | `RULE 01`, one or two short lines in grey, and the forbidden thing inside a red prohibition ring that draws on, then its slash |
| `case` | A case card: `WITNESS: NAME`, a pictogram ID photo, grey redaction bars, an optional red stamp |
| `steps` | A navy card titled in capitals with 2 to 4 numbered steps, each appearing on its word |

**You write data, never code.** The whole video is one installed scene, `NightSignal`, and everything
about it is its `props.nightSignal`. You never call `generate_image` or `generate_character`: this style
has no pictures but its pictograms.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses a Night Signal config that breaks any of these, and says which scene and
which field:

- 3 to 14 scenes. The first starts at frame 0 and is a picture (`tableau`, `camera` or `phone`), never a
  card. Every other scene starts within 2 frames of a word's start, and lasts at least 1.5 s.
- Every frame you give (`at`, `redAt`, `to.at`, `slashAt`, `crossAt`, a mark's or a stamp's `at`, each
  step's `at`) is inside its scene and within 2 frames of a word's start.
- A `tableau` or `camera` holds 1 to 4 items, each in its own slot (`left`, `midleft`, `center`,
  `midright`, `right`). An item's step (`to`) may not end where another item stands, and starts no
  earlier than the item appears.
- At most one item per scene has `"threat": true`; `redAt` is only for the threat.
- A connector joins two slots that hold items; a bubble sits over a slot that holds an item.
- Every `what`, `icon` and bubble `icon` is a library part (`style` → `extra.people`, `extra.animals`,
  `extra.objects`) or one of your `customParts`.
- Text limits: the file title 16 characters, a camera label 22, a button 6, a phone title 12 and 1 to 3
  phone lines of 16, a rule's 1 or 2 lines of 12, a case label 10 and name 12, a stamp 10, a steps title
  20 and 2 to 4 steps of 24. Write them in capitals where the card shows capitals; the card draws
  them in capitals anyway.
- A card (`phone`, `rule`, `case`, `steps`) keeps its last part on screen at least 20 frames after it
  has finished arriving (a slash draws for 6 frames, a mark, a stamp or a step for 8; a phone's lines
  and a case's bars slide in over the card's first frames) before the next scene.
- Green is used once: at most one `check` mark in a video.
- Nothing may sit still for more than 5 seconds: some item, connector, bubble, mark, stamp or step must
  arrive on a word within every 5-second stretch (the small running loops do not count).
- Your own parts: at most 6 in `customParts`, each at most 40 shapes inside its box.

## Step 0 — read

`get_video(video_id)` for the style block (`style.extra` holds the catalogues), `get_timeline(video_id)`
for the words, the segments, their `beat`, `role` and `insert`.

## Step 1 — plan the scenes

Give most sentences their own scene: the situation as a tableau or a camera panel, each rule as a
`rule` card, the reason as a tableau or a phone, what to do as a `steps` card or a phone with a mark.
Decide the one threat in each scene and whether it is red from the start or turns red on the word that
names it (`redAt`). A rule card that names what to do can end the video; a `steps` card can too.

## Step 2 — the case file

`file.number` is any number from 1 to 999 (it is a case number, not a count) and `file.title` two or
three words in capitals that name the danger (`QR STRANGER`, `NIGHT CALLER`). `clock` is when the
story happens, `"HH:MM"` (24-hour): the camera panel's clock and the timecode start there.

## Step 3 — scenes, items and their timing

- Place people where they face each other: `face` turns an item to the `left` or `right` (people face
  right unless told otherwise). The person on the left is usually you.
- Bring an item in on the word that names it (`at`); leave `at` out for what is there from the
  start. A small `to` step moves an item to another slot on a word.
- A connector (`from`, `to`, `at`) draws a dotted line from one item to another: a message sent, a
  code passing, a path someone takes.
- A bubble (`over`, `icon`, `kind`, `at`) pops a thought or speech bubble with an icon over an item.
- On a camera panel, the button is crossed out on the word that forbids it (`crossAt`).
- A rule card's slash lands on its own word (`slashAt`, at least 16 frames into the card); leave it
  out and it lands 16 frames in.

## Step 4 — your own pictograms (only when the library lacks one)

Look in `style.extra` first. When a thing the narration names is not there, draw it as a custom part:
`{"id": "parking_meter", "shapes": [...]}` in `customParts`, and use its id like a library name. Shapes
are `circle` (`cx`, `cy`, `r`), `rect` (`x`, `y`, `w`, `h`, optional corner `r`), `line` (`points`,
`width`, round ends) and `poly` (`points`), each with a `tone`: `ink` (the warm white), `core` (the
brightest), `grey`, `dim`, `red` (only on the threat) or `hole` (the black field, to cut a window or a
gap). The box: x from -200 to 200, y from -400 (top) to 0 (the ground the part stands on); a circle's
radius and a line's half width must stay inside it too (a line's end may sit on the ground). A standing
person is about 330 tall, a door 264. Keep a part simple and flat: 5 to 15 shapes, no outlines, a
`hole` line under a limb or a handle where it must read as separate.

Look at your parts before you use them: `render_style_parts(video_id)` draws every custom part of the
video (after `write_scene_config` has stored them) and returns the picture. Fix what does not read
and write again.

## Step 5 — captions

Leave `subtitles` out of the config. The style fills in its own caption look; any key you set
overrides it.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame` (the formula's
line on what the first frame shows, `""` when the video has no formula). The first segment's role is
`opening`. A `turn` or `reopen` segment needs a visible change on its first word, the `payoff` segment
the video's strongest picture, and a segment with role `""` only its own brief. `get_video`'s
`style.picture` says how this style does each; in short:

- Opening: the first scene is the situation, a picture on screen from frame 0 (the style requires it).
- Turn or re-opening: a new scene on its first word, or the threat turning red (`redAt`) then.
- Payoff: the RULE card that names what to do or not do, or the scene where the threat is plainest.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has no new scene or event starting within about 0.4 s of its first word. Fix what is a real miss; say
in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. This style goes into and out of an insert through a glitch tear. The pictograms
are hidden while an insert plays, so inside each insert's window no scene starts and no item, step,
connector, bubble, mark, stamp or slash lands. Start the next scene on the window's end (its last
frame + 1), so the video comes back on a new picture, or let the scene from before the insert carry on.
A scene never starts on the frame just before an insert: its tear runs one frame past its start.
The "never still" rule does not count a window. Plan the gap with the scenes: the segment marked
`insert` is where no scene starts and nothing lands, so let the scene before it keep its last event
before the segment's first word, and start the scene after on the window's end (a window of about 140
frames fits in a scene whose quiet tail is that long, however many events it had before). With no
marked segment, write no `inserts`.

## Step 6 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` from the timeline, `"canvas": "dark"` (or
   leave it out), the one scene and any `inserts`. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`.
3. **Look before you submit.** Call `preview_frames(video_id, frames)`, as the **tubematic-scene-config** skill's
   *Look before you submit* step says: frame 0, the first words of the turn and the payoff, and the way in and out of any
   insert. Fix what you see and look again. `submit_render` refuses with `preview_not_taken` until the current config
   has been looked at, and a config rewritten after the look needs a new look.
4. Before submit_render: check the opening, the turn and the payoff scenes against the narration once
   more (what is red, what is on each card).
5. `submit_render(video_id)`.

In the handback, say what the threat is in each scene, which custom parts you drew, and any warning you
left and why.

## Revising

Read the comments on `get_video`. A comment about a scene, a card, the timing or what is red is fixed
in `props.nightSignal`; a comment about a drawn thing you made is fixed in its `customParts` entry
(look at it again with `render_style_parts`). Then write, validate and submit again as above. Never
change the video's style. If the voice was redone, the word frames have changed: re-time every scene
start and every event from the new timeline.
