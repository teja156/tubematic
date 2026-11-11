---
name: tubematic-storybook-atlas
description: Author a Storybook Atlas narrated Short as data — split the storyteller's narration into 3 to 5 chapters with a plaque each, choose each chapter's backdrop, cast people from history by name and costume, walk the mouse guide and the people on the narrator's words, place props from the hatched library (drawing one of your own, modelled on the library, when it lacks one), open plates (star lettering, a gauge, an ink-dot morph) — then write it with write_scene_config, preview your props, validate and submit it
---

# Tubematic Storybook Atlas authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-storybook-atlas` (its `visual_style` is `storybook_atlas`). Also take it, on **Revising**,
for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that looks like a vintage picture book: ivory paper with fine diagonal
hatching inside a dark double-rule frame. The story is told in **chapters**. Each one opens with a
**plaque** at the top (a Roman numeral, the chapter's title typing on, an italic byline, a red wax seal)
over a **backdrop**: a study, a laboratory, a harbour, a night sky. On the stage below, a small grey
**mouse in a waistcoat** (the guide) walks beside the story and reacts without speaking, **people**
from the story walk in and point and think, and hatched **props** pop, drop or slide in and stay. Now
and then a **plate** opens over the stage behind brass shutters: stars that join into a word, a brass
gauge whose needle springs to a number, or a swirl of ink dots that regroups into a picture. Chapters
change with a **push** through a door or porthole into white, or a hatched diagonal **wipe**. The
narration shows one short phrase at a time on a small ivory label near the bottom.

The look is calm and hand-made: a few things happen per sentence, each on the word that names it, and
then they stay. Plan something new at least every 2 to 4 seconds.

**You write data, never scene code.** The whole video is one installed scene, `StorybookAtlas`, and
everything about this video is its `props.storybookAtlas`: the guide's waistcoat, the cast, and the
chapters with their events timed to the narration. The guide, the people, every backdrop and library
prop, the plaque and the captions are drawn by the renderer. There are no images in this style: never
call `generate_image` or `generate_character`. Props come from the library in `reference/contract.md`;
when it has nothing for an object the story is about, you draw that one prop yourself, modelled on the
library (**Step 3b**).

The full field reference, the backdrops, the people's knobs and the prop catalogue are in
`reference/contract.md`; the worked example is `reference/example-config.json` (narration in
`reference/example-timeline.json`, and its own prop in `reference/example-prop-moth.tsx`). Read all of
them before you write.

## Rules the tools enforce

`write_scene_config` refuses a Storybook Atlas config that breaks any of these, and says which chapter
or event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "StorybookAtlas", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"storybookAtlas":
  {...}}}`.
- **Chapters:** 3 to 5. The first starts at frame 0, the others on a word (within 2 frames of a word's
  `startFrame`), each at least 8 seconds long. A title fits 2 lines of 18 characters; a byline is at
  most 28.
- **Events** land on a word (within 2 frames of its start), inside their chapter, and no later than 20
  frames before it ends.
- **A push** (`"enter": "push"`) goes through a prop with a portal (a door, a porthole, a window, an
  open book, the relay cabinet) that was on stage in the chapter before, at least 14 frames before the
  cut. Without one, use `"enter": "wipe"`.
- **Plates** (constellation, gauge, morph) last 2.5 to 8 seconds (`until`), are closed (`until` plus 10
  frames) 20 frames before their chapter ends, open 14 frames or more after a chapter other than the
  first starts (after its push or wipe), never overlap, and nothing else happens on stage while one
  is open.
- **People:** at most 4 in the cast, at most 2 on stage at once. Nobody stands where someone else or a
  floor prop stands (people need 160 px of floor, the guide 140); walking past is fine. The name tags
  printed under their feet must not touch.
- **Props:** at most 6 in a chapter, from the catalogue or your `customProps`; inside the stage
  (x 60 to 1020, below y 430); floor props do not overlap each other, nor do wall props; a wall prop
  hangs with its base `y` from 620 to 1240. An act starts once its prop has landed (10 frames after it
  appears) and is one of that prop's acts.
- **Tags** are at most 24 characters and go on a prop already on stage. A prop shows one tag: a new
  tag on it replaces the one before.
- **Your own props:** at most 8 per video, each a `prop-<name>` file of this video that exists before
  the config is written, with a box of 60 to 700 px a side, 1 to 4 states and 1 to 4 acts. The file
  default-exports the drawing, imports only `react` and `../../installed/storybookAtlas/ink` (or
  `palette`), and uses no filter, gradient, pattern of its own, SVG text, image, fetch, randomness,
  clock or timer, and nothing from the page (`window.`, `document.`, `globalThis`), `eval`, a
  `Function` constructor, a dynamic import or a network call. Comments are not checked. A dashed
  stroke is fine: a prop is drawn once into a bitmap.
- **Never still:** something new on stage at least every 4 seconds.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments, and
   `mascot`.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## What carries between chapters

Each chapter starts with an empty stage except for the guide, who stands at x 210 when it opens. People
and props do not carry over: a person's first event in a chapter walks them in again, and a prop that
is still part of the story is placed again (`"enter": "fade"` makes it simply be there).

## Step 1 — chapters

The script was written as a story in chapters (the problem, the attempt, the turn, what it changed).
Find where each chapter begins: the first word of the sentence that moves the story on ("Then one
afternoon...", "Years later..."). Each chapter gets:

- a **title** of a few words ("The Machine", "The Moth") and a **byline**, a place or a date ("Harvard,
  1947"). The plaque shows both for the whole chapter.
- a **backdrop** for where it happens: `study`, `workshop`, `laboratory`, `street`, `countryside`,
  `harbour`, `nightsky`, `blueprint`, `factory` or `maproom` (`reference/contract.md` says what each
  shows). Use a different one for each chapter when the place changes; the same one twice reads as the
  same room.
- an **enter** (every chapter after the first): `push` when the story goes into something (through the
  door, into the machine, into the book), else `wipe`.

## Step 2 — the guide and the cast

`guide` is `{"coat": ...}`: the guide's waistcoat colour (`blue`, `sage`, `brick`, `plum`, `mustard`).
The guide is in every chapter; it starts each one standing at x 210, it never speaks, and it never
exits.

`cast` lists the people of the story, at most four, each made of knobs (`reference/contract.md` lists
them): `{"id": "ada", "name": "Ada Lovelace", "build": "short", "skin": "light", "hair": "bun",
"hairColor": "dark", "face": "none", "hat": "none", "garment": "dress", "color": "plum"}`. Dress
people for their time and work: a frock coat and top hat for a Victorian inventor, a lab coat for a
chemist, overalls for a printer. They are picture-book figures recognised by their name tag and their
clothes, never by their face. Give two people different garments or colours so they are told apart.
A person's `color` holds for the whole video, so plan it with the backdrops: on a dark backdrop
(`nightsky`, `blueprint`) only the light colours `cream` and `sky` read well, and `ink` and `navy` all
but disappear. Either dress someone who appears on a dark backdrop in `cream` or `sky`, or keep the
dark-dressed people to the light chapters.

## Step 3 — events, timed to the words

| Event | When | Fields |
|---|---|---|
| `guide` | the guide moves or reacts | `at`, optional `x` (walks there first), `pose` (`stand`, `point`, `look`, `think`, `surprised`, `hop`), `facing` |
| `person` | someone enters (their first event walks them in from the nearer edge), moves, reacts, or leaves | `at`, `who`, optional `x`, `pose` (`stand`, `point`, `hold`, `think`, `surprised`), `facing`, `exit: true` |
| `prop` | the word that names the thing | `at`, `id` (your name for it), `prop`, `x`, `y` (wall props only), optional `scale`, `enter` |
| `act` | the prop does its thing | `at`, `id`, `act` (one of that prop's acts) |
| `tag` | a small printed label under a prop: a name, a date | `at`, `on` (a prop's `id`), `text` |
| `constellation` | a name or word worth revealing | `at`, `until`, `words` (1 or 2 words of letters and digits), optional `then` + `thenAt` |
| `gauge` | one number rises or hits a limit | `at`, `until`, `label`, `from`, `to`, `max`, optional `danger` |
| `morph` | ink dots swirl and become a thing or a word | `at`, `until`, `prop` or `word` |

**Walking.** Everyone walks at 9 px a frame, so crossing the stage takes about 3 seconds. A walk starts
on its word and the pose comes when it arrives. An `exit` walks off to the nearer edge at the same
speed and takes no `x`. A new event for someone still walking starts from wherever they are on that
frame. A walker faces the way they walk; once they stop they keep facing that way unless the event
gives `facing`. List events in any order; two may share a frame, and on one frame a prop arrives
before an act or a tag that names it.

**Where things stand.** Only where people stand still is checked; walking past anyone is fine. On the
floor line each thing takes a span centred on its `x`: a person x ± 80, the guide x ± 70, a floor prop
its box width × `scale` (the lamp at scale 1 takes x ± 70). Spans of people, the guide and floor props
must not overlap. A worked layout: the guide at 200 (130 to 270), a person at 380 (300 to 460), the
relay cabinet at 700, scale 1 (490 to 910): nothing touches. The tags under people and floor props
share one row: each is about 14 px a character plus 32, centred on its owner, two must not touch, and
none may run off the frame (x 30 to 1050) (Grace Hopper's 12-character tag is about 200 px wide). A wall prop's tag hangs 12 px under the
prop's base. Plan where people stand before you write: the guide usually stays to one side (x 150 to
350), the people in the middle, the props beside them. Point a person or the guide at what the line
is about (`pose: "point"` and `facing` towards it).

**Props.** `x` is the middle of the prop's base in frame pixels. Floor props stand on the floor line
(y 1344); wall props hang with their base at `y`. `scale` (0.6 to 1.4) sizes it; `enter` is `pop` (the
default), `drop` (falls in), `slide` (from the nearer edge), `rise` or `fade`. Each prop's box, place,
states and acts are in the catalogue: `switch` changes it to its second drawing for good (a lamp lit, a
book opened, a lock undone), `cycle` runs its drawings for 1.6 s (a telegraph tapping, relays
flickering), `glow` puts a warm halo behind it, and `wobble`, `bounce`, `shake`, `spin`, `swing` and
`pulse` move it once.

**Plates.** Use one or two a video, on the story's high points: the constellation for the name the
story ends on, the gauge for the one number the narration says, the morph for the moment a thing
appears or is found. Time `until` to the end of the line that explains it. A plate must be closed (its
`until` plus 10 frames) 20 frames before its chapter ends, so the next chapter's push or wipe never
cuts it off, and in a chapter other than the first it opens 14 frames or more after the chapter starts.
Nothing new starts on stage while it is open (a walk already under way finishes behind it).

- **Landing the last word.** The ending name is usually said in the last seconds, too late to open a
  2.5-second plate on it. Open the constellation a few seconds earlier, on the sentence that leads to
  it, with a word that sets it up, and give the name as `then` with `thenAt` on the word itself
  (`"words": ["BUG"], "then": ["DEBUGGING"]`). `then` replaces the first words; the same stars redraw
  it. Write words in capitals or not: they are drawn in capitals.
- **The gauge.** `from` is where the needle starts (often 0), `to` where it settles, `max` the top of
  the dial: pick a round number a little above `to`. `danger` marks a red band from there to `max`, for
  a limit. A number with no natural top (a ratio, "three times longer") is better said than gauged.

**Pacing.** Something new every 2 to 4 seconds; the tool refuses a stretch longer than 4. Every event
counts (a pose change, a tag, an act), and so do a walk's arrival, a plate closing and a
constellation's `then`. Build a chapter up: the place (the plaque), a prop, a person, a reaction, a
tag. Do not put things on stage that the narration does not name.

**A push.** The portal prop (a door, the porthole, the window, the book, the relay cabinet, or one of
yours with a `portal`) must have landed (10 frames after it appears) at least 14 frames before the
chapter it leads into starts; it need not be switched open first.

## Step 3b — a prop the library does not have

Use a library prop whenever one fits; a tag can name a generic one ("Mark II" under the relay
cabinet). Draw your own only for an object the story is about that the library lacks: the moth in the
relay, Babbage's engine, a particular instrument. Keep it to a few per video.

1. Read the closest library props and the ink they use: `read_scene_file` with `source="installed"`
   and `scene_name` `storybookAtlas/props/things` (books, keys, ships, houses, a press),
   `storybookAtlas/props/science` (machines and instruments), `storybookAtlas/props/room` (the lamp
   and the door), `storybookAtlas/ink` (the `Sh` shape and path helpers) and
   `storybookAtlas/palette`. `reference/example-prop-moth.tsx` is a finished one.
2. Draw it the same way: one component that takes `{ state }` and draws with its base at (0, 0),
   x from -w/2 to w/2 and y from -h to 0, ending 3 px inside the box. Use `Sh` for every filled shape
   (a flat fill, an ink outline, pencil hatching) and plain `<path>`, `<circle>` and `<line>` for ink
   lines and dots, colours from the palette, and big simple shapes that read at phone size. Write no
   text in it: fonts do not load inside a prop. A seeded random sequence of your own is fine;
   `Math.random` and the clock are not. The library's small helpers (gear outlines, rods) are not
   exported: copy one into your file when you need it. A prop that appears on a dark backdrop needs a
   light outline or light parts somewhere, or it disappears.
3. Write it with `write_scene_file(video_id, "prop-<name>", tsx)` and list it in `customProps`:
   `{"id": "moth", "src": "<the src write_scene_file returned>", "box": [300, 220], "place": "wall",
   "states": 1, "acts": ["wobble", "glow"]}` (add `"portal": [x, y]` if the camera should be able to
   push through it). Its `id` is then used like a library prop's.
4. After `write_scene_config`, call `render_storybook_props(video_id)` and look at the picture. Each of
   your props has a row (two a row when there are more than four): every state side by side on the
   paper inside its red box, the guide at the same scale on the left for size, and the first state
   again on a night-navy swatch on the right. A red "OVER" line under a prop means the drawing leaves
   its box and will be cut off: raise the box or shrink the drawing. A drawing that does not read as
   the thing at a glance, sits badly beside the guide, or vanishes on the navy when the prop appears on
   a dark backdrop: redraw it. Rewrite the file and call `render_storybook_props` again; three looks
   at most. `validate_job` typechecks the file and checks it against the rules above again.

## Step 4 — captions and mascot

Leave `subtitles` out: the style sets its caption label. If `get_video` has a `mascot`, add its cue
track as the mascot skill describes, small and to one side, away from the guide and the people.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out), `"sfx": []` (this style has no sound effects) and the one scene. Fix every problem it reports. If the video has props
   of your own, look at them now with `render_storybook_props` (Step 3b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   plaque, the tags and the plates' text in a browser; an overlap is a measurement, so move or shorten
   the text.
3. `submit_render(video_id)`.

In the handback, say how many chapters you made and their backdrops, who is in the cast, which plates
you used and why, which props you drew yourself and why the library could not show them.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong prop, a person in the wrong
clothes, a crowded page, a tag in the way) is fixed in `props.storybookAtlas`: edit the chapters and
events, then write, validate and submit again as above. Never change the video's style. If the voice
was redone, the word frames have changed: re-time every chapter and event from the new timeline.
