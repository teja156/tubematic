---
name: tubematic-process-cast
description: Author a Process Cast narrated Short as data — cast the parts of an invisible process as little drawn characters with faces, set up stations along one ground line, and time their entrances, hops, task cards, clones, joins and reactions and the camera's moves to the narrator's words (drawing a prop of your own, modelled on the library, when it lacks one) — then write it with write_scene_config, preview your props, validate and submit it
---

# Tubematic Process Cast authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-process-cast` (its `visual_style` is `process_cast`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short in a storybook look on warm grey paper: the parts of an invisible process
(a packet, a cell, a stage of a build, a byte made of unit cubes) are little drawn **characters with
faces**, standing at **stations** along one long ground line. Each station has a hanging sign and a
piece of furniture (a desk, a board, a door, a shelf, a machine, a server rack, a cell membrane) or
is an open stage. The characters pop in, hop between spots, carry **task cards** over their heads
and hand them on, split into look-alike **clones** and **merge** back, **join** (cubes add up into a
bigger body), and react with their faces and small marks, while the **camera** glides from station
to station.

**Nobody talks.** A face shows a feeling; it never moves its mouth with the words, and the narrator
is off screen. These characters are this style's own cast and have nothing to do with an install's
mascot; this style takes no mascot.

**You write data, never code**, except a prop the library lacks (**Step 3b**). The whole video is one
installed scene, `ProcessCast`, and everything about this video is its `props.processCast`: the
cast, the stations and the events timed to the narration. There are no images in this style: never
call `generate_image` or `generate_character`. Nothing here runs code or a shell.

The full field reference and the catalogues are in `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three
before you write.

## Rules the tools enforce

`write_scene_config` refuses a Process Cast config that breaks any of these, and says which event is
wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "ProcessCast", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"processCast":
  {...}}}`. Insert scenes go in the config's own `inserts` list (**Inserts**).
- **Cast:** 1 to 6 characters, each with a unique lowercase `id` that does not end in a digit (a
  clone of `packet` is `packet2`), a `body`, a `tint`, an optional `accessory` and `name` (its tag, at
  most 14 characters). A `units` body has `units`, 1 to 16 cubes; no other body has it.
- **Stations:** 1 to 6, each with a unique `id`, a `kind` and a `sign` of at most 14 characters. The
  camera starts at the first station and must show every station at least once.
- **Events** are listed in frame order, at most 120, each on a word (within 2 frames of a word's
  `startFrame`, or at frame 0), and at least 8 frames before the end.
- **On camera:** everything happens where the camera is. An actor enters, reacts, carries, clones,
  merges, joins and hands over only at the station the camera shows; a prop appears only there. A
  trip to another station starts at the camera's station or ends at it.
- **Slots:** a station has 3 slots before its furniture (0 to 2) or 5 across an open stage (0 to 4);
  two characters never share one, and two bodies (or a body and the furniture) may not overlap, so a
  wide `units` body needs the slot beside it free.
- **Timing:** a character is busy for 8 frames after it enters, 10 after a hop, 20 after a trip to
  another station, 12 after a merge, a join or a hand-over (a reaction or a look may come sooner), and two of
  its changes are at least 6 frames apart (a reaction or a look excepted). The camera stays at a station at least 1.5
  seconds.
- **Clones:** `clone` splits a character into 2 or 3 (it needs that many free slots); its clones are
  `<id>2` and `<id>3` and act like any character; `merge` brings them back. A clone does not split.
- **Join:** two `units` bodies at the same station; the cubes add up to at most 16.
- **Cards:** `carry` gives a character a card of at most 18 characters (`""` puts it down); `hand`
  passes it to another character at the same station.
- **Your own props:** at most 8, each a `prop-<name>` file of this video written before the config,
  with a box of 60 to 400 px a side and a label of at most 18 characters. It imports only `react`,
  `remotion` and `../../installed/processCast/ink` (or `contract`), uses no hook, filter, gradient,
  image, media part, fetch, randomness, clock, timer or page access (`reference/contract.md` lists
  them all), and default-exports the drawing.
- **Never still:** something new at least every 3 seconds (a look alone does not count).

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps`, every word's frames, and each
   segment's `beat`, `role` and `insert`. Every frame you write comes from here.

## Step 1 — the cast and the stations

- **Cast the parts, never the people.** Each thing the narration names as an actor of the process is a
  character: the request is a `bean` named `REQUEST`, a red blood cell a `blob`, a compiler stage a
  `block` with `glasses`, a byte a `units` body of 8. People who use the system are not in the cast.
  Give characters that work together the same tint and an intruder or a failure another (`coral`).
- **Stations are places.** Each place the process moves through is a station named as its sign reads
  (`ROUTER`, `MEMORY`, `STOMACH`), with furniture that suits it: a `desk` for a clerk or a resolver, a
  `board` for a lookup table, a `door` for a gate, a `shelf` for storage, a `machine` for a step that
  transforms, a `server` for a server, a `cell` for biology, a `stage` for a line-up (meet the cast)
  or a place with nothing in it.

## Step 2 — events, timed to the words

| Event | When | Fields |
|---|---|---|
| `enter` | the word that names the character | `who`, `station`, `slot`, optional `from` (`pop`, `drop`, `slide`) |
| `move` | it goes somewhere: a hop within a station, a trip to another | `who`, `station`, `slot` |
| `exit` | it leaves | `who` |
| `react` | a feeling, with an optional mark beside its head | `who`, `face`, optional `mark` |
| `look` | its eyes turn to another character or a station | `who`, `at` |
| `carry` | it holds up a task card with a few words | `who`, `text` |
| `hand` | it passes its card to another character | `from`, `to` |
| `clone` | it splits into copies that share the work | `who`, `count` |
| `merge` | the copies come back into it | `who` |
| `join` | two cube bodies add up | `who`, `with` |
| `prop` | a thing appears at a station (on its desk, pinned to its board) | `station`, `prop`, optional `text` |
| `focus` | one character grows and the rest shrink, to introduce it; `""` ends it | `who` |
| `camera` | the camera goes to another station | `station`, optional `move` (`glide`, `cut`) |

**Pacing.** Something new every 1.5 to 3 seconds. Build each station up: a character arrives, gets
its card, reacts, hands over. Move the camera on the word that names the next place, and send the
character on the same word so it travels with the camera. Do not put on stage anything the
narration does not name.

## Step 3b — a prop the library does not have

Use a library prop whenever one fits; use a `card`, `file` or `envelope` with a label when the thing
is really a word or a name. Draw your own only for a thing the viewer must recognise that the
library lacks (a tooth, a ribosome, a ticket). Keep it to a few per video.

1. Read the library and its helpers: `read_scene_file` with `source="installed"` and `scene_name`
   `processCast/props/index` and `processCast/ink` (the palette, `Hatches`, `Inked`, the wobble
   helpers). `reference/example-prop-ticket.tsx` is a finished one.
2. Draw it the same way: one component, centred on (0, 0) inside a `w` x `h` box at scale 1, wobbly
   ink outlines with hatched fills (`<Hatches>` for each tone you use, then `Inked`), big simple
   shapes. It receives `text` and nothing else, and draws from it alone.
3. Write it with `write_scene_file(video_id, "prop-<name>", tsx)` and list it in `customProps`:
   `{"id": "ticket", "src": "<the src write_scene_file returned>", "w": 200, "h": 120, "text": 12}`.
   Its `id` is then used like a library prop's.
4. After `write_scene_config`, call `render_style_props(video_id)` and look at the picture. Ink outside
   the red box means the box is too small. A drawing that does not read as the thing at a glance, or
   looks unlike the library beside it: redraw it. Three looks at most. `validate_job` checks the file
   against the rules again.

## Step 4 — captions

Leave the caption look to the style: leave `subtitles` out, or set only `emphasis` (the indexes of the
key words in the timeline's word list, at most one word in 5). The style fills in the rest.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`; `get_video`'s `style.picture` says how this
style does each:

- Opening: the first station with the first character entering at frame 0.
- Turn or re-opening: a camera move to a new station on its first word, or a character entering,
  hopping, splitting, joining, reacting or handing over a card on that word.
- Payoff: the process finishing (the card arriving, the clones merging, the cubes joining) with the
  strongest reaction.

`validate_job` returns advisory warnings when nothing enters by frame 3 or when a `turn`, `reopen` or
`payoff` segment has nothing new starting within about 0.4 s of its first word (a look alone does not
count). Fix what is a real miss; say in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it. The stage is hidden while an insert plays, so no event has its `frame` inside an
insert's window; time the next event after the window. The "never still" rule does not count a
window. With no marked segment, write no `inserts`.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out), the one scene and any `inserts`. Fix every problem it reports. If the
   video has props of your own, look at them now with `render_style_props` (Step 3b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   signs, tags and cards in a browser; an overlap is a measurement, so move a character or shorten
   the text.
3. **Look before you submit.** (Reserved: a later tool lets you look at chosen frames of the composed
   video here. Until it exists, go straight on.)
4. `submit_render(video_id)`.

In the handback, say how many characters and stations you made, which props you used, and which
props you drew yourself and why the library could not show them.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong character, a card handed to
the wrong one, a crowded station) is fixed in `props.processCast`: edit the cast, stations and
events, then write, validate and submit again as above. Never change the video's style. If the voice
was redone, the word frames have changed: re-time every event from the new timeline, and recount the
`emphasis` indexes.
