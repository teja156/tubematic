---
name: tubematic-editorial-collage
description: Author an Editorial Collage narrated Short as data: plan stations on a paper desk with a headline and one hero each, make halftone prints and cut-out stickers with generate_image and treat_image (at most 10) and check them with read_image, type recreated documents on index cards, count figures up, time circles, underlines, highlights, strikes, stamps and arrows to the narration, then write it with write_scene_config, validate and submit it
---

# Tubematic Editorial Collage authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-editorial-collage` (its `visual_style` is `editorial_collage`). Also take it, on **Revising**,
for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that looks like an investigation pinned to a paper desk. The desk is larger
than the frame. Each **station** is one idea: a **headline** at the top and one **hero** under it. The
camera rests on a station, then glides diagonally to the next one while a red string draws between
them. Pieces move in small steps, twelve a second; the camera moves smoothly.

A headline is one of:

- a `clipping`: a torn, yellowed newspaper strip with a large serif headline and an optional small
  red kicker line above it ("TECH · FEB 28, 2017");
- a `label`: a black label bar with white capitals;
- a `black` card: white serif words on a black card, for a dark beat. With no hero it fills the
  station.

A hero is one of:

- a `print`: a grey halftone print with a white border, taped and slightly tilted, with an optional
  typed caption;
- a `sticker`: one object cut out with a white edge and a hard shadow, swaying a little, with an
  optional black label bar;
- an `index` card: a ruled card whose lines type on letter by letter, for a command, a memo line or a
  message;
- a `figure`: a big yellow pill whose number counts up from zero, with a black label bar under it;
- a `stack`: two or three small prints or stickers side by side.

On the stressed words a red pen **circle** goes round the hero, a red pen **underline** or **strike**
marks a headline word, a yellow **highlight** wipes in behind a clipping's word, a red rubber **stamp**
lands on the hero with a kick, and a red paper **arrow** points at it. The captions sit on a cream strip
under the hero, with a yellow marker under the key words you pick.

**You write data, never code.** The whole video is one installed scene, `EditorialCollage`, and
everything about this video is its `props.collage`: the stations timed to the narration. The code lays
the stations out on the desk and moves the camera; you write no position, size or angle. You make the
prints and stickers with `generate_image` and `treat_image`; never call `generate_character`.

**A real person is never pictured.** No still and no card shows a real person's face; a real person is
named in words only (a headline, a label bar, an index line). The renderer paints the small note
"Illustration" on every print and "Recreation" on every index card marked `recreation`; they are always
there.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses an Editorial Collage config that breaks any of these, and says which
station, hero or event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is one entry: `{"type": "generated", "source": "installed", "src":
  "EditorialCollage", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"collage": {...}}}`.
  Insert scenes go in the config's own `inserts` list (**Inserts** below).
- **Stations:** the first starts at frame 0; the others start on a word (within 2 frames of a word's
  `startFrame`); each lasts at least 1.5 seconds; at most 20. The camera glides for 36 frames from each
  station's start.
- **Everything happens on a word.** Every event's `at`, every index line's `at` and a figure's
  `countAt` (except one at its station's start) is within 2 frames of a word's `startFrame`, inside its
  station, and at least 8 frames before the station ends. Lines arrive in order, and each must finish
  typing before its station ends (13 characters a second).
- **The headline** is at most 60 characters and must fit its kind (the tool says when it does not);
  the kicker at most 28 characters. Every station has a hero, except one whose headline is a `black`
  card.
- **Lengths:** a print's caption at most 40 characters, a sticker's label 24, an index line 34 (one to
  four lines), a figure's label 24, its prefix 3 and its suffix 10, a stack item's caption 24, a stamp
  12 capital letters.
- **Pictures:** a print's `image` is the `public_path` that `treat_image(..., "print")` returned,
  `/public/<video_id>/images/treated/<name>.print.png`; a sticker's is the one from
  `treat_image(..., "sticker")`, `/public/<video_id>/images/treated/<name>.sticker.png`. A stack item
  takes either. An untreated still, or a print where a sticker belongs, is refused. At most **10
  different stills per video**; `generate_image` refuses an 11th new still before it is paid for. Show
  one again on another station.
- **A figure** is a number from 0 to 999999999 with at most 2 decimals.
- **One of each per station:** at most one circle, one stamp, one arrow and one strike; an underline or
  a highlight marks a word once. `underline`, `highlight` and `strike` need a word of the headline;
  `highlight` needs a `clipping`; `circle`, `stamp` and `arrow` need a hero.
- **No face field.** A field for a person's face or portrait is refused, and so is any field that
  would hide a note or place a piece.
- **Never still:** something new on the desk (a station, an event, a line or a count starting) at
  least every 3.5 seconds. A silent pause in the narration is not counted: the desk may hold through one.

## Step 0: read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs (station briefs:
   the headline, the hero and what lands on it), the comments, and `style.extra` (the headline kinds,
   the hero kinds, the events and the treatments).
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1: plan the stations

One station per idea, usually one to three sentences, 3 to 8 seconds each. Every station costs a
36-frame glide, so do not cut a station shorter than the idea. For each station decide:

- the **headline**: a few words that name the idea ("The typo that took down the internet", "S3 goes
  dark"). Use a `clipping` for the story's facts and dates, a `label` for a short name or a place, a
  `black` card for the darkest beat. Put the date and the section in a clipping's kicker when the
  narration says it;
- the **hero**: a print of the place or the thing the sentence names, a sticker of one object, an index
  card when the story quotes a command, a memo or a message, a figure when a number carries the stakes,
  a stack when the point is "several of these";
- the **events**, one per stressed word (table below).

| Event | Does | Fields |
|---|---|---|
| `circle` | a red pen ellipse draws round the hero in one stroke | (none) |
| `underline` | a red pen line draws under a headline word | `word` |
| `highlight` | a yellow bar wipes in behind a clipping's headline word | `word` |
| `strike` | a red pen line draws through a headline word | `word` |
| `stamp` | a red rubber stamp lands on the hero with a kick | `text` (capitals) |
| `arrow` | a red paper arrow lands beside the hero, pointing at it | `from`: `left` or `right` |

Use `circle` or `arrow` for "this one", `stamp` for a verdict ("OFFLINE", "FIXED"), `highlight` or
`underline` for the headline's key word, and `strike` when the narration corrects a word. The captions
take your key words too: add `"subtitles": {"emphasis": [<word indexes>]}` with the narration's most
important words (at most one word in five, indexes from 0 into the timeline's words); the style fills
in the rest of its captions.

## Step 2: make and check the prints and stickers

Plan at most 10 stills for the whole video: a new one when the subject changes, never one per sentence.
Make each in two calls:

```
generate_image(video_id, "<name>", "<the subject>", aspect_ratio="1:1")
treat_image(video_id, "<name>", "print")      # or "sticker"
```

The prompt is only the subject. The server adds the house look (a plain documentary photograph with no
lettering, no logos and small faceless people), so do not describe the art style. Pick the shape: a
print is widest at `16:9` or `1:1`; a `9:16` print stands as a narrow strip in the middle of the
station. For a **sticker**, ask for one isolated object on a plain flat light grey background with no
shadow ("A red rotary telephone, alone on a plain flat light grey background, no shadow"), usually
`1:1`: the treatment cuts the object out of that background, and a busy background leaves holes or
specks. For a **print**, write the place or the thing and the view: "A long aisle between server racks
in a data centre, seen from one end." "A stack of printed invoices on an office desk."

**Never ask for a named person in a still,** and never describe anyone's face. Unnamed people may
appear in a print, small and far away. Never ask for writing, a logo, a brand mark, a masthead, a
newspaper page or a real document in a picture: headlines and documents are the station's own cards.

Open every still with `read_image(video_id, "<name>")` and check:

- it shows what the narration says at that moment;
- no person in it has a detailed, recognisable face;
- there is no lettering, logo or brand mark in it;
- a sticker's object stands alone on a plain background.

Regenerate under the same name if any of these fails (a regeneration replaces the still and does not
count against the 10), then call `treat_image` again. In the config, a hero's `image` is the
`public_path` `treat_image` returned.

## Step 3: people, documents and numbers

**People are named, never shown.** A real person appears in words only: a headline ("One engineer, one
command"), a sticker's label, an index line. Show their work, the place or the object instead.

**Documents are recreations.** An `index` card is `{"kind": "index", "lines": [{"text", "at"}, ...],
"recreation": true or false}`: one to four short lines that type on at their words. Write the lines in
the video's own words: a command or a famous line the narration quotes may appear as it is spoken,
everything else short and paraphrased. Never copy a real document's layout, letterhead, masthead or
signature. Mark a card that stands for a real document (a command someone ran, a memo, a message)
`"recreation": true`; it then carries the note "Recreation".

**Figures count up.** A `figure` is `{"kind": "figure", "value", "prefix", "suffix", "label",
"countAt"}`: the value the narration says ("4" with suffix "hours", "33" with suffix "%", "150000000"
with prefix "$"), counting from zero on the word it is said. Never name a publication in a kicker or a
label: a clipping carries the video's own words and its date and section only.

## Step 4: write and check

1. `write_scene_config(video_id, config)`. Give `subtitles` only its `emphasis`: the style fills in its
   own captions. Fix every problem it lists.
2. `validate_job(video_id)`. Read every warning.
3. **Look before you submit.** <!-- frame-preview: a look-then-fix step goes here once a frame preview exists -->
   Look at every still again with `read_image`. Then read back the config once against the narration:
   each station's headline and hero fit what is said, each event lands on the word it shows, each date,
   name and number matches the narration, and no card or still shows a real person's face.
4. `submit_render(video_id)`.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame`. The first
segment's role is `opening`. A `turn` or `reopen` segment needs a visible change on its first word, the
`payoff` segment the video's strongest picture, and a segment with role `""` only its own brief.
`get_video`'s `style.picture` says how this style does each; in short:

- Opening: station 1 is the headline over the hero of the first sentence's subject, usually a print, on
  the desk from frame 0, with a mark landing in the first seconds. An index card types its first line
  from frame 0.
- Turn or re-opening: a new station on its first word, or a circle, a stamp or an arrow on it.
- Payoff: the payoff station's headline names the answer, and a stamp, a circle or a highlight lands on
  the payoff word.
- Ending: hold on the payoff station to the last frame. No closing card, recap or sign-off.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has no new station, event, line or count within about 0.4 s of its first word (an underline or a
highlight alone does not count). Fix what is a real miss; say in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. The desk is hidden while an insert plays, so inside each insert's window no
station starts, no glide runs (a station starts at least 36 frames before the window, or after it) and
no event, line or count lands; `write_scene_config` refuses one that does. Put the station's events
before and after the window. The captions stay on screen through the insert. Write any `inserts` in the
same `write_scene_config` call as the scene.

## Revising

Read every comment and the AI review's findings. Change only what they name: a wrong still, an event on
the wrong word, a wrong date, name or number. For a bad still, regenerate it under the same name, treat
it again and keep the config. Keep the rest as it was, write the whole config again, validate and
submit.
