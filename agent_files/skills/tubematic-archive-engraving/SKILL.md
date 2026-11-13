---
name: tubematic-archive-engraving
description: Author an Archive and Engraving narrated Short as data: plan dated beats with a serif title and one museum card each, make engraved plates with generate_image and treat_image (at most 10) and check them with read_image, show people as name cards with an emblem or initials, recreate documents line by line, time strikes, stamps, magnifiers, routes, underlines and the timeline ruler to the narration, then write it with write_scene_config, validate and submit it
---

# Tubematic Archive and Engraving authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-archive-engraving` (its `visual_style` is `archive_engraving`). Also take it, on **Revising**,
for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that reads like a page of an old museum catalogue. The page is warm
parchment with a ruled border and a small-caps **running header** at the top ("Histories of
Computing"), the same for the whole video. Each beat is a new page: a **date** typed on in spaced
capitals, a large serif **title** of one or two lines with **one word in red**, and one cream museum
**card** under it:

- a `plate`: an engraving (a place, a machine, an object, a scene of unnamed people at work) seen
  through a wide window that pushes in slowly, with a small-caps name and an italic note under it;
- a `chart`: an engraved antique map whose route appears as a row of red dots;
- a `person`: a name card with a coin-like engraved **roundel** holding an emblem or the person's
  initials, the name, the dates and the role;
- `people`: two to four name cards in a row, arriving one by one, joined by red arrows (a lineage of
  ideas);
- a `document`: a lined paper card whose lines write on, typed or by hand.

On the stressed words a red line **strikes** through a title word and an italic replacement rises under
the title, a red line **underlines** a title word, a red **stamp** lands with a kick, a **magnifying**
roundel flies out of a plate and shows one part enlarged, a chart's **route** draws, and a **timeline**
ruler at the bottom slides its red year marker. The captions sit on a small cream chip under the card.

**You write data, never code.** The whole video is one installed scene, `ArchiveEngraving`, and
everything about this video is its `props.archive`: the header and the beats timed to the narration.
The page, cards, roundels, stamps, ruler and captions are drawn by the renderer. You make the
engravings with `generate_image` and `treat_image`; never call `generate_character`.

**People are never pictured.** A real person is a name card with an emblem or initials, never a face.
The renderer puts the small footnote "Illustration" under every plate and chart and "Recreation" under
every document; they are always there.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses an Archive and Engraving config that breaks any of these, and says which
beat, card or event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is one entry: `{"type": "generated", "source": "installed", "src":
  "ArchiveEngraving", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"archive": {...}}}`.
  Insert scenes go in the config's own `inserts` list (**Inserts** below).
- **Beats** are pages: the first starts at frame 0; the others start on a word (within 2 frames of a
  word's `startFrame`); each lasts at least 1.5 seconds; at most 32.
- **Everything happens on a word.** Every event's `at`, every person's `at` and every document line's
  `at` (except one at its beat's start) is within 2 frames of a word's `startFrame`, inside its beat,
  and at least 8 frames before the beat ends. People and lines arrive in order, and the first person
  of a people card arrives within 1.5 seconds of the beat's start, so the card is never left empty.
- **The title** is at most 48 characters and must fit two lines; `red` is one word of it. A strike or
  an underline names one word of the title.
- **Lengths:** the header at most 34 characters, a date 24, a plate's name 28 and its note 40, a
  person's name 28, dates 20 and role 32, a document line 40, a strike's replacement 28, a stamp 14
  capital letters.
- **Pictures:** a plate or chart `image` is the `public_path` that `treat_image(..., "engraving")`
  returned, `/public/<video_id>/images/treated/<name>.engraving.png`. An untreated still is refused.
  At most **10 different engravings per video**; `generate_image` refuses an 11th new still before it
  is paid for. Show one engraving again on another beat with a different `focus`.
- **Points on a plate** (a magnify `point`, a chart's `route`) must lie inside the part of the
  engraving the window shows. The window is a wide band of the tall still around `focus`.
- **One of each per beat:** at most one strike, one stamp and one magnify; a chart has one
  `route` event, and `route` is for charts only; `magnify` needs a plate or a chart.
- **A person card** takes `name`, `dates`, `role` and one of `emblem` or `initials` (never both). A field
  for a picture or a face of a person is refused.
- **Never still:** something new on the page (a beat, an event, a person or a line arriving) at least
  every 3.5 seconds. The slow push does not count. A silent pause in the narration is not counted: the
  page may hold through one.

## Step 0: read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs (card briefs: the
   title, the card and what changes on it), the comments, and `style.extra` (the card kinds, the
   events and the emblems).
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1: plan the beats

One beat per idea, usually one or two sentences, 2 to 7 seconds each. For each beat decide:

- the **title**: two to six words that name the idea, with the stressed word in red ("The first
  computer **bug**.", "A word **older** than computers");
- the **date** when the narration names one ("9 September 1947"); leave it out otherwise;
- the **card**: an engraved plate for a place, a machine or an object; a chart for a voyage or a route;
  a person card when one person's work is the point; a row of people for a line of ideas passed on; a
  document when the story quotes a log, a letter or a telegram;
- the **events**, one per stressed word (table below).

Write the header once for the whole video: the field of history, in two to four words ("Histories of
Computing", "Histories of the Sea").

| Event | Does | Fields |
|---|---|---|
| `strike` | a red line through a title word, and the italic words in `with` rise under the title | `word`, `with` |
| `underline` | a red line draws under a title word | `word` |
| `stamp` | a red stamp lands on the card with a kick | `text` (capitals) |
| `magnify` | a roundel flies out of the plate and shows one part enlarged | `point` [u, v] |
| `route` | a chart's route draws as red dots | (none) |
| `timeline` | the ruler at the bottom appears (the first time) and slides its marker from one year to another | `from`, `to` |

Use `strike` for a correction the narration makes (an old word and the new one), `stamp` for a verdict
or a date in a record ("DISPROVED", "9 SEP 1947"), `magnify` for the one detail the sentence names,
and `timeline` whenever the narration jumps in time. The ruler stays on screen from its first event to
the end of the video and spans every year the timeline events name.

## Step 2: make and check the engravings

Plan at most 10 engravings for the whole video: a new one when the subject changes, never one per
sentence. Make each in two calls:

```
generate_image(video_id, "<name>", "<the subject>")
treat_image(video_id, "<name>", "engraving")
```

The prompt is only the subject. The server adds the engraving style (fine black crosshatching on cream
paper, no colour, small faceless figures, no lettering) and makes every still tall (9:16), so do not
describe the art style. Write the place or the object, what is in it, and the view: "Rows of tall
relay cabinets in a long machine room, seen from one end." "An antique sea chart of a coastline with a
compass rose and one sailing ship." "An eighteenth-century printing workshop, two workers at a wooden
press, seen from behind." Keep what matters in the middle band of the picture: the window shows a wide
strip of the tall still.

**Never ask for a named person in a still,** and never describe anyone's face. A real person is a name
card (Step 3). Unnamed people may appear in a scene, small, from behind or in profile. Never ask for
writing, a logo, a masthead, a publication's name or a real document page in a picture.

Open every still with `read_image(video_id, "<name>")` (the grid is on) and check:

- it shows what the narration says at that moment;
- no person in it has a detailed, recognisable face;
- there is no lettering, logo or masthead in it.

Regenerate under the same name if any of these fails (a regeneration replaces the still and does not
count against the 10), then call `treat_image` again. Then read off the grid, per still, the `[u, v]`
of what the plate is about (its `focus`, u left to right, v top to bottom, 0 to 1), of the one detail a
`magnify` should show, and of a chart's route points. The treated engraving has the same layout as
the still, so the grid's numbers hold for it.

In the config, a card's `image` is the `public_path` `treat_image` returned.

## Step 3: people and documents

**People are name cards.** A `person` card or each entry of a `people` card is `{"name", "dates",
"role"}` plus an `emblem` or `initials`:

| Emblem | Stands for |
|---|---|
| `laurel` | honour, a prize, a victory, a leader |
| `quill` | a writer, a poet, a letter, a law |
| `gear` | an engineer, a machine, industry |
| `compass` | navigation, exploration, maps |
| `scroll` | an old text, a decree, a scholar of the ancient world |
| `book` | a scholar, a teacher, a library, a theory |
| `anchor` | the sea, a sailor, a port, trade by ship |
| `telescope` | astronomy, discovery, observation |
| `scales` | justice, a judge, money and trade |
| `lamp` | an inventor, an idea, light, learning |

Use `initials` (one to three capital letters, "GH") when no emblem fits the person's work. Dates are
the person's years ("1815-1852", "c. 100-170"); the role is a few words ("mathematician", "ship's
captain"). In a `people` card each person has an `at`, the word their name is spoken on.

**Documents are recreations.** A `document` card is `{"lines": [{"text", "at"}, ...], "hand": true or
false}`: one to six short lines that write on at their words, by hand (`hand: true`) or typed. Write
the lines in the video's own words: a famous line the narration quotes may appear as it is spoken,
everything else is short and paraphrased. Never copy a real document's layout, letterhead, masthead
or signature. The card always carries the footnote "Recreation".

## Step 4: write and check

1. `write_scene_config(video_id, config)`. Leave `subtitles` out: the style fills in its own chip
   captions. Fix every problem it lists.
2. `validate_job(video_id)`. Read every warning.
3. **Look before you submit.** Call `preview_frames(video_id, frames)` first, as the **tubematic-scene-config** skill's *Look before you submit* step says: frame 0, the first words of the turn and the payoff, and the way in and out of any insert. Fix what you see and look again. `submit_render` refuses with `preview_not_taken` until the current config has been looked at.
   Look at every engraving again with `read_image` and check its `focus` and points against the grid.
   Then read back the config once against the narration: each beat's title and card fit what is said,
   each event lands on the word it shows, each date and name matches the narration, and no card
   pictures a person.
4. `submit_render(video_id)`.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame`. The first
segment's role is `opening`. A `turn` or `reopen` segment needs a visible change on its first word, the
`payoff` segment the video's strongest picture, and a segment with role `""` only its own brief.
`get_video`'s `style.picture` says how this style does each; in short:

- Opening: beat 1 is the dated title over the card of the first sentence's subject, usually a plate,
  on screen from frame 0. A `people` or `document` card brings its first person or line in at frame 0.
- Turn or re-opening: a new beat on its first word, or a strike, a stamp or a magnify on it.
- Payoff: the payoff beat's title names the answer with the answer in red, and a stamp, an underline
  or a magnify lands on the payoff word.
- Ending: hold on the payoff beat to the last frame. No closing card, recap or sign-off.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has no new beat, event, person or line within about 0.4 s of its first word (an underline or a timeline
slide alone does not count). Fix what is a real miss; say in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. The page is hidden while an insert plays, so inside each insert's window no beat
starts and no event, person or line lands; `write_scene_config` refuses one that does. Put the beat's
events before and after the window, and bring the page back on the next word after it. The captions
stay on screen through the insert. Write any `inserts` in the same `write_scene_config` call as the
scene.

## Revising

Read every comment and the AI review's findings. Change only what they name: a wrong engraving, an
event on the wrong word, a wrong date or name. For a bad engraving, regenerate it under the same name,
treat it again and keep the config. Keep the rest as it was, write the whole config again, validate and
submit.
