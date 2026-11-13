---
name: tubematic-storybook-reveal
description: Author a Storybook Reveal narrated Short as data: make the story's hero sheet once with generate_image and check it with read_image, plan the tale as pages with short titles, paint each page from the hero sheet (at most 12 pictures), bake each page's pencil plate with treat_image and check both, time each page's pencil wipe and colour flood to the narration, then write it with write_scene_config, validate and submit it
---

# Tubematic Storybook Reveal authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-storybook-reveal` (its `visual_style` is `storybook_reveal`). Also take it, on **Revising**,
for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that reads like a children's picture book read aloud. The page is cream
paper. Each **page** of the story has a short hand-lettered **title** in capitals near the top, one
large rounded panel in the middle holding a square painted **picture** (coloured pencil and watercolour), the
captions under the panel and a small page number ("~ 2 ~") near the bottom.

Every page reveals its picture in steps, on the narration's words:

1. the title wipes in from the left as the page starts;
2. the picture's **pencil plate** (a grey pencil drawing of the same picture) wipes in from the left;
3. the **colour** floods over the drawing from the left with a soft, ragged watercolour edge, within a
   second of the pencil;
4. the picture then pushes in very slowly until the page ends.

A page arrives on a hard cut, or turns over from its bottom-right corner (a **curl**). The same hero, in
the same clothes, is on every page.

**You write data, never code.** The whole video is one installed scene, `StorybookReveal`, and
everything about this video is its `props.reveal`: the pages timed to the narration. The page, the
panel, the reveal, the curl and the captions are drawn by the renderer. You make the pictures with
`generate_image` and `treat_image`; never call `generate_character`.

**Never a real or named person, and never a brand.** The hero is invented, and so is everyone else in
the story.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`), the tale of a
lighthouse keeper told in three pages. Read all three before you write.

## Rules the tools enforce

`write_scene_config` refuses a Storybook Reveal config that breaks any of these, and says which page is
wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is one entry: `{"type": "generated", "source": "installed", "src":
  "StorybookReveal", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"reveal": {"pages":
  [...]}}}`. Insert scenes go in the config's own `inserts` list (**Inserts** below).
- **Pages:** the first starts at frame 0; the others start on a word (within 2 frames of a word's
  `startFrame`); each lasts at least 2.5 seconds; at most 24 pages.
- **The title** is 1 to 3 words and at most 24 characters.
- **The reveal:** `pencilAt` is on a word at least 6 frames after the page starts (the first page may
  instead give 0 and open on its drawing); `colourAt` is on a word 12 to 30 frames after `pencilAt`
  (within a second of the pencil), and the colour (18 frames) must finish flooding at least 8 frames
  before the page ends.
- **Pictures:** `image` is the `public_path` `generate_image` returned,
  `/public/<video_id>/images/<name>.png`, and `pencil` is the `public_path`
  `treat_image(video_id, "<name>", "pencil")` returned for that same name,
  `/public/<video_id>/images/treated/<name>.pencil.png`. The hero sheet is never a page. At most
  **12 different pictures per video**; `generate_image` refuses a 13th new one before it is paid for.
  A page may show a picture again.
- **Curls:** at most 2 per video, never on the first page. Every other page is a cut.
- **Never still:** something new on each page (the page, its pencil wipe, its colour flood) at least
  every 6 seconds. The slow push does not count. A page whose colour has landed holds at most 6 seconds.

## Step 0: read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs (page briefs: the
   title, the picture and the word the colour arrives on), the comments, and `style.extra` (the turns,
   the treatment and the sheet's name).
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1: make the hero sheet once

The hero sheet is the reference every page is painted from, so the hero looks the same on every page.
Make it before any page, in one call, from a description of the hero alone:

```
generate_image(video_id, "hero", "<who the hero is and what they wear>")
```

Describe the hero only: their age, build, hair, face and clothes ("an old woman with grey hair in a
bun, round glasses, a long yellow raincoat with a hood and black rubber boots"). Use the script's own
description if it gives one. The server adds the sheet's layout and style (three views side by side,
coloured pencil and watercolour, no text) and makes it wide (16:9), so do not describe the art style.
The sheet has a slot of its own and never counts against the 12 pictures.

Open it with `read_image(video_id, "hero")` and check that it shows one invented character three times
in the same clothes, with no lettering and nobody who looks like a real person. Regenerate it under the
same name if not. The sheet is never shown in the video.

## Step 2: plan the pages

One page per moment of the story, usually one or two sentences, about 3 to 8 seconds each. For each
page decide:

- the **title**: one to three words that name the moment ("The Keeper", "One Stormy Night", "Home
  Safe"); the lesson's page names the lesson;
- the **picture**: what the hero is doing and where, at that moment;
- the word the **colour** floods in on: the stressed word of the page, where the picture pays off ("the
  beam found the boat" floods on "beam");
- the word the **pencil** wipes in on: time it to a word within a second before the colour, so the
  drawing has just been traced when the colour arrives (the word one or two before the stressed word).

The page then holds its finished picture: put the stressed word early enough that the hold after the
colour is at most 6 seconds, and split a long stretch of narration over two pages.

Plan at most 12 pictures. A page may show a picture again when the story stays in one place, but most
pages are a new moment and a new picture.

## Step 3: paint and check each page

For each picture, in two calls:

```
generate_image(video_id, "<name>", "<the scene>", reference="hero")
treat_image(video_id, "<name>", "pencil")
```

The prompt is only the scene: where the hero is, what they do, what else is there and the light ("She
climbs a spiral stone staircase inside the lighthouse, holding a lantern, a small window at the top
showing the evening sky."). The server adds the hero from the sheet and the picture-book style (coloured
pencil, watercolour, plain paper around the scene, no lettering) and makes every picture square (1:1),
so do not describe the art style or the hero's clothes again. A picture with no hero in it is made
without `reference`. Keep the scene in the middle of the picture: the panel shows the whole picture,
and the paper around it fades into the page.

`treat_image(..., "pencil")` is free. It writes a pencil drawing that lines up with the picture pixel
for pixel, so the colour floods over it in place. Make it again after you regenerate a picture.

Open both with `read_image` and check:

- the picture shows what the narration says at that moment;
- the hero has the same face, hair and clothes as on the sheet;
- there is no lettering, logo, brand or real person in it;
- the pencil plate shows the same drawing.

Regenerate a picture under the same name if it fails (a regeneration does not count against the 12),
then bake its pencil plate again. Read off the grid the `[u, v]` of what the page is about (u left to
right, v top to bottom, 0 to 1): it is the page's `focus`, the point the slow push keeps in place.

## Step 4: write and check

1. `write_scene_config(video_id, config)`. Leave `subtitles` out: the style fills in its own captions.
   Fix every problem it lists.
2. `validate_job(video_id)`. Read every warning.
3. **Look before you submit.** Call `preview_frames(video_id, frames)` first, as the **tubematic-scene-config** skill's *Look before you submit* step says: frame 0, the first words of the turn and the payoff, and the way in and out of any insert. Fix what you see and look again. `submit_render` refuses with `preview_not_taken` until the current config has been looked at.
   Look at every picture and pencil plate again with `read_image`. Then read back the config once
   against the narration: each page's title and picture fit what is said, each colour floods on the word
   it pays off, and the hero is the same on every page.
4. `submit_render(video_id)`.

## The opening and the pages

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame`. The first
segment's role is `opening`. A `turn` or `reopen` segment needs a visible change on its first word, the
`payoff` segment the video's strongest picture, and a segment with role `""` only its own brief.
`get_video`'s `style.picture` says how this style does each; in short:

- Opening: page 1 shows its title and its pencil drawing from frame 0 (`pencilAt: 0`), and its colour
  floods in on a word within the first second. Keep page 1 short (one sentence), so its hold stays
  under 6 seconds.
- Turn or re-opening: a new page on its first word (a curl suits the story's big turn), or the colour
  flooding in on it.
- Payoff: the lesson's page; its title names the lesson and its colour floods in on the payoff word.
- Ending: hold on the lesson's page to the last frame. No closing card, recap or sign-off.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has no new page, pencil wipe or colour flood within about 0.4 s of its first word. Fix what is a real
miss; say in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. The page is hidden while an insert plays, so inside each insert's window no page
starts, no pencil wipes in and no colour floods, and none of them may still be running when a window
opens (a turn-in takes 10 frames, 14 with a curl; the pencil 12; the colour 18); `write_scene_config`
refuses one that does. Put them on words before and after the window. The captions stay on screen through the insert. Write any `inserts`
in the same `write_scene_config` call as the scene.

## Revising

Read every comment and the AI review's findings. Change only what they name: a wrong picture, a hero who
changed, a colour on the wrong word, a wrong title. For a bad picture, regenerate it under the same name
with `reference="hero"`, bake its pencil plate again and keep the config. Keep the rest as it was, write
the whole config again, validate and submit.
