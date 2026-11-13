---
name: tubematic-puppet-history
description: Author a Puppet History narrated Short as data — cast house puppets in era costumes, lay the story out as beats joined by hard cuts (an illustrated set, a document card or a flat map of today's countries), and time each puppet's entrance, pose, face, costume swap, sign and prop, each stamp, strike-out, map fill, arrow and label to the narrator's words (drawing a hand prop of your own, modelled on the library, when it lacks one) — then write it with write_scene_config, preview your props, validate and submit it
---

# Tubematic Puppet History authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-puppet-history` (its `visual_style` is `puppet_history`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short of "you are now a..." history, acted by cut-out **puppets**: one house
puppet with a big round white head, dot eyes and mitten hands, framed from the waist up, dressed in
an era **costume**. The video is a run of **beats** joined by hard cuts:

- a **set**: a flat illustrated place (a farm, a street, a palace hall...) where puppets slide or pop
  in, strike poses, change faces, swap costumes on a hard cut, hold up a prop or a sign, and a stamp
  lands;
- a **card**: a typed document (a contract, an order, a ticket) where a stamp lands and a line is
  struck out with a new value scrawled in red;
- a **map**: today's countries, flat, where regions fill in, a curved arrow grows and a hand-lettered
  label appears; puppets may stand in front of it.

A hand-lettered **date** can sit in the corner of any beat. The narrator is off screen: a puppet never
speaks. This style takes no mascot.

**Real people.** A real, historical person is the house puppet in a generic costume of their era with
their name on a plate (`name` in the cast). The puppet has no likeness and you never add one: no
prop, costume or sign that copies their face, uniform or signature feature. **Never** put a living
person or a leader of a regime still in power on a plate. **Never** play a tragedy for laughs: a
war's dead, a disaster, a persecution or a famine is left out of the gags.

**You write data, never code**, except a hand prop the library lacks (**Step 3b**). The whole video is
one installed scene, `PuppetHistory`, and everything about this video is its `props.puppetHistory`:
the cast and the beats. There are no images in this style: never call `generate_image` or
`generate_character`. Nothing here runs code or a shell.

The full field reference and the catalogues are in `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three
before you write. `get_video`'s `style.extra` lists every costume, pose, face, set, prop and country
the tools accept.

## Rules the tools enforce

`write_scene_config` refuses a Puppet History config that breaks any of these, and says which event is
wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "PuppetHistory", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"puppetHistory":
  {...}}}`. Insert scenes go in the config's own `inserts` list (**Inserts**).
- **Cast:** 1 to 4 puppets, each with a unique lowercase `id`, a `costume` and an optional `name` of
  at most 18 characters (a name plate).
- **Beats:** 1 to 14, the first at frame 0, each starting on a word and lasting at least 1.5 seconds.
  A set beat names its `set`; a map beat its `focus`, 1 to 8 countries by the names in
  `style.extra.countries`; a card beat its `title` (at most 22 characters) and 1 to 5 `lines` of at
  most 26 characters. A card never repeats 5 narration words in a row.
- **Events** are listed in frame order, at most 100 in the video, each on a word (within 2 frames of
  a word's `startFrame`, or at its beat's start), during its beat and at least 6 frames before the
  beat ends. A beat takes only its kind's events (a card: stamps, strikes and dates).
- **Puppets:** nobody carries over a cut, so each beat's puppets `enter` in it, into slot 0, 1 or 2
  (left, middle, right), one puppet a slot. A puppet is busy for 16 frames after a slide-in or a move
  and 8 after a pop-in, and two of its changes are at least 6 frames apart (or on the same frame).
  Every other puppet event needs it on stage.
- **Signs:** two puppets' signs on stage never overlap (a 14-character sign is about 540 wide, so
  hold long signs one at a time or from slots 0 and 2); a wide sign from a side slot is pulled in from
  the frame's edge.
- **Text:** a sign at most 14 characters, a stamp at most 10, a date at most 12, a struck-out line's
  new value at most 12, a map label at most 18, a prop's label no more than its slot takes.
- **Maps:** a fill, an arrow or a label names countries from the beat's `focus`; at most 6 arrows.
- **Opening:** if beat 1 is a set, a puppet enters it at frame 0.
- **Your own props:** at most 6, each a `prop-<name>` file of this video written before the config,
  with a box of 50 to 300 units a side and a label of at most 10 characters. It imports only
  `react`, `remotion` and `../../installed/puppetHistory/ink` (or `contract`), uses no hook, filter,
  gradient, image, media part, fetch, randomness, clock, timer or page access
  (`reference/contract.md` lists them all), and default-exports the drawing.
- **Never still:** something new at least every 3 seconds.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps`, every word's frames, and each
   segment's `beat`, `role` and `insert`. Every frame you write comes from here.

## Step 1 — the cast and the beats

- **"You" is a puppet** in the costume of the era and job the narration gives (a `legionary`, a
  `peasant`, a `clerk`). Other people are puppets too: an officer, a king, a merchant. A real person
  gets their name on the plate and a generic costume of their era; nothing else marks them.
- **One beat per idea**, cut on its first word: the place (a set), the paper (a card), the journey (a
  map). A short video is 4 to 8 beats.
- **Maps use today's borders.** Show a historical region as the modern countries it covers (Gaul is
  `France`, Mesopotamia is `Iraq` and `Syria`) and give it its old name with a `label`. Keep `focus` to
  the countries the beat is about, since the map fits itself to them.
- **The gag is a reversal on a hard cut:** the same puppet in a new costume (`swap`), a number struck
  out (`strike`), a stamp landing (`stamp`), a sign held up in deadpan (`sign`).

## Step 2 — events, timed to the words

| Event | When | Fields |
|---|---|---|
| `enter` | the word that brings the puppet in | `who`, `slot`, optional `from` (`slide`, `pop`, `cut`), `pose`, `face` |
| `move` | it walks to another slot | `who`, `slot` |
| `exit` | it leaves (slides out) | `who` |
| `act` | a pose, a face or both change | `who`, `pose` and/or `face` |
| `swap` | its costume changes on the spot, for the rest of the video | `who`, `costume` |
| `sign` | it holds a sign in front of its chest (`""` lowers it) | `who`, `text` |
| `hold` | it holds a prop up in its hand (`""` drops it) | `who`, `prop`, optional `text` |
| `stamp` | a rubber stamp lands with a kick | `text`, optional `color` (`red`, `green`, `blue`) |
| `date` | the hand-lettered date in the corner changes | `text` |
| `strike` | a card line is struck out and a new value scrawled | `line` (0-based), `text` |
| `fill` | a country fills with a colour | `region`, `color` |
| `arrow` | a curved arrow grows from one country to another | `from`, `to` |
| `label` | a hand-lettered label appears on a country | `region`, `text` |

**Pacing.** Something new every 1.5 to 3 seconds. Enter a puppet on the word that names it, act on the
word that changes its mood, cut on the word that changes the place. A deadpan sign holds 2 to 4
seconds. Do not put on screen anything the narration does not name.

## Step 3b — a hand prop the library does not have

Use a library prop whenever one fits; use a `scroll`, `letter` or `flag` with a label when the thing
is really a word or a name. Draw your own only for a thing the viewer must recognise that the library
lacks (an hourglass, a horseshoe, a ballot box). Keep it to a few per video, and keep it generic: no
real flag, emblem, logo or currency symbol.

1. Read the library and its helpers: `read_scene_file` with `source="installed"` and `scene_name`
   `puppetHistory/props` and `puppetHistory/ink` (the palette, `inked`, `LW`).
   `reference/example-prop-hourglass.tsx` is a finished one.
2. Draw it the same way: one component, centred on (0, 0) inside a `w` x `h` box at scale 1, dark
   brown ink outlines at `LW`, flat warm fills, big simple shapes. It receives `text` and nothing
   else, and draws from it alone.
3. Write it with `write_scene_file(video_id, "prop-<name>", tsx)` and list it in `customProps`:
   `{"id": "hourglass", "src": "<the src write_scene_file returned>", "w": 110, "h": 170, "text": 0}`.
   Its `id` is then used like a library prop's in a `hold` event.
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

- Opening: beat 1 at frame 0, a set with "you" already in it (`enter` at frame 0, `from: "cut"`), or a
  card or a map.
- Turn or re-opening: a hard cut to a new beat on its first word, or a puppet entering, acting,
  swapping costume or holding up a sign, or a stamp landing, on that word.
- Payoff: the reversal (a costume swap, a strike-out, a stamp) with the strongest face.

`validate_job` returns advisory warnings when no puppet is on the first set by frame 3 or when a
`turn`, `reopen` or `payoff` segment has nothing new starting within about 0.4 s of its first word.
Fix what is a real miss; say in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it. The stage is hidden while an insert plays, so no beat starts and no event has its
`frame` inside an insert's window; time the next one after the window. The "never still" rule does
not count a window. With no marked segment, write no `inserts`.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out), the one scene and any `inserts`. Fix every problem it reports. If the
   video has props of your own, look at them now with `render_style_props` (Step 3b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   name plates, dates, card text and map labels in a browser; an overlap is a measurement, so move or
   shorten what it reports. Signs, stamps and prop labels are drawn into pictures, which
   `write_scene_config` already sized from their text.
3. **Look before you submit.** (Reserved: a later tool lets you look at chosen frames of the composed
   video here. Until it exists, go straight on.)
4. `submit_render(video_id)`.

In the handback, say how many beats of each kind you made, who the cast is in which costumes (and
which real people have name plates), which props you used, and which you drew yourself and why the
library could not show them.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong costume, a name plate on the
wrong puppet, a crowded set, a wrong country) is fixed in `props.puppetHistory`: edit the cast and the
beats, then write, validate and submit again as above. Never change the video's style. If the voice
was redone, the word frames have changed: re-time every beat and event from the new timeline, and
recount the `emphasis` indexes.
