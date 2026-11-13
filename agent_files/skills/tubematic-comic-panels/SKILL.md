---
name: tubematic-comic-panels
description: Author a Comic Panels narrated Short as data — lay the story out as 1 to 3 comic pages of 3 or 4 panels, cast a house hero, invented people and a villain, and time each panel and its characters, props, balloons, caption boxes, sound effects, speed lines and hits to the narrator's words (drawing a prop of your own, modelled on the library, when it lacks one) — then write it with write_scene_config, preview your props, validate and submit it
---

# Tubematic Comic Panels authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-comic-panels` (its `visual_style` is `comic_panels`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short told as a comic: **pages** of cream newsprint with a title bar, each laid
out as 3 or 4 **panels** with thick black borders. A panel inks in on the word that starts it, and the
camera reads the page panel by panel, then pulls back to show the whole finished page at the
**splash**. Inside a panel, characters framed from the waist up (a house **hero**, invented
**people** and a hooded **villain** silhouette) and props pop in on words, with speech, thought and
shout **balloons**, yellow **caption boxes**, slammed **sound effects**, speed or focus **lines** and
**hits** that punch the camera in and shake it.

**The narrator is off screen.** A balloon is a short line a character says or thinks, never the
narration read aloud: the captions already carry the narrator's words. The cast are invented comic
characters; this style takes no mascot, and never draws a real, recognisable person.

**You write data, never code**, except a prop the library lacks (**Step 3b**). The whole video is one
installed scene, `ComicPanels`, and everything about this video is its `props.comicPanels`: the cast,
the pages, their panels and the items in each. There are no images in this style: never call
`generate_image` or `generate_character`. Nothing here runs code or a shell.

The full field reference and the catalogues are in `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three
before you write.

## Rules the tools enforce

`write_scene_config` refuses a Comic Panels config that breaks any of these, and says which item is
wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "ComicPanels", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"comicPanels":
  {...}}}`. Insert scenes go in the config's own `inserts` list (**Inserts**).
- **Cast:** 1 to 4 characters, each with a unique lowercase `id` and a `kind` (`hero`, `person`,
  `villain`); at most one hero. A person takes optional `hair`, `outfit` and `skin`.
- **Pages:** 1 to 3, the first at frame 0, each with a `layout` and an optional `title` of at most 28
  characters. A layout fixes the number of panels: list exactly that many.
- **Panels** start in order, from their page's start, each on a word, and each is read for at least
  1.5 seconds before the next.
- **Items** are listed in frame order, at most 8 a panel, each on a word (within 2 frames of a
  word's `startFrame`, or at its panel's start), while its panel is read and at least 6 frames
  before the panel ends. Two items in a panel are at least 4 frames apart, or on the same frame.
- **Inside the panel:** a character, prop, balloon or sound effect stays inside its panel's edges (a
  character may be cut off at the bottom). A character's reach depends on its pose: a `cheer` raises
  its hands above its hair, a `shrug` or a `point` spreads them past its shoulders. Balloons and sound effects in a panel do not overlap each
  other.
- **Text:** a balloon at most 40 characters, a caption box at most 40, a sound effect at most 10, a
  prop's text no more than its slot takes. A balloon or caption never repeats 5 narration words in a
  row.
- **Balloons point at someone:** `to` names a character or prop already in the panel.
- **Every panel has a picture:** at least one character or prop.
- **Splash:** optional, a frame on the last page at least 1.5 s before the end.
- **Your own props:** at most 8, each a `prop-<name>` file of this video written before the config,
  with a box of 60 to 500 units a side and a text slot of at most 24 characters. It imports only
  `react`, `remotion` and `../../installed/comicPanels/ink` (or `contract`), uses no hook, filter,
  gradient, image, media part, fetch, randomness, clock, timer or page access
  (`reference/contract.md` lists them all), and default-exports the drawing.
- **Never still:** something new at least every 3 seconds (a caption box alone does not count).

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps`, every word's frames, and each
   segment's `beat`, `role` and `insert`. Every frame you write comes from here.

## Step 1 — the cast and the pages

- **Cast by side.** The viewer's side (you, your password, your immune system, the antibiotic) is
  the `hero`; the threat (a guessing attack, a superbug, a spammer) is the `villain`; anyone else is
  a `person` with knobs. Never make a character look like a real person, and never name a real one.
- **One page per act.** A short video is one page; a setup, a fight and a payoff can be up to three.
  Give each page a title that names its act ("The bank call", "Round two"). Choose a layout whose
  panel count fits the act's beats: `stack3`, `stack4`, `2+1`, `1+2`, `2+2`.
- **One panel per beat**, read for 1.5 to about 4 seconds. Start each panel on the word of the beat
  it shows. Pick a `tone` per panel (`dark` for the villain's moment).

## Step 2 — items, timed to the words

| Item | When | Fields |
|---|---|---|
| `actor` | the word that names or moves the character | `who`, `pose`, `face`, `x`, `y`, optional `scale`, `flip`, `id` |
| `prop` | the word that names the thing | `prop`, `x`, `y`, optional `scale`, `text`, `id` |
| `balloon` | the moment the character speaks or thinks | `kind`, `text`, `x`, `y`, `to` |
| `caption` | a scene-setting box at the panel's top-left | `text` |
| `sfx` | the word where something lands | `text`, `x`, `y` |
| `lines` | a burst of action or a shock | `kind` (`speed`, `focus`) |
| `hit` | the strongest moment: the camera punches in and shakes | (none) |

`x` and `y` are fractions of the panel (0 to 1), the item's centre. A character sits low (`y` about
0.6 to 0.7) with room above for its balloon.

**Pacing.** Something new every 1 to 3 seconds. Build each panel up: the character, then what it
says, then the sound. Put a `hit` on the payoff and nowhere near another. Do not put in a panel
anything the narration does not name.

## Step 3b — a prop the library does not have

Use a library prop whenever one fits; use a `sign`, `document` or `envelope` with text when the
thing is really a word or a name. Draw your own only for a thing the viewer must recognise that the
library lacks (a trophy, a pill, a satellite). Keep it to a few per video.

1. Read the library and its helpers: `read_scene_file` with `source="installed"` and `scene_name`
   `comicPanels/props/index` and `comicPanels/ink` (the palette, `Dots`, `starPoints`,
   `SpeedLines`). `reference/example-prop-trophy.tsx` is a finished one.
2. Draw it the same way: one component, centred on (0, 0) inside a `w` x `h` box at scale 1, flat
   colour, halftone `<Dots>` with an id that starts with your prop's id, heavy black outlines
   (6 to 7 units) drawn last. It receives `text` and nothing else, and draws from it alone.
3. Write it with `write_scene_file(video_id, "prop-<name>", tsx)` and list it in `customProps`:
   `{"id": "trophy", "src": "<the src write_scene_file returned>", "w": 180, "h": 220, "text": 0}`.
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

- Opening: page 1, panel 1 at frame 0 with its first character or prop in it.
- Turn or re-opening: a new panel on its first word, or a character, balloon, sound effect or hit on
  that word.
- Payoff: the winning move as the strongest panel (a shout balloon, a sound effect and a `hit`),
  then the `splash` pulls back to the whole page.

`validate_job` returns advisory warnings when page 1 has no character or prop by frame 3 or when a
`turn`, `reopen` or `payoff` segment has nothing new starting within about 0.4 s of its first word (a
caption box alone does not count). Fix what is a real miss; say in the handback why any warning
stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it. The page is hidden while an insert plays, so no panel starts and no item has its
`frame` inside an insert's window; time the next one after the window. The "never still" rule does
not count a window. With no marked segment, write no `inserts`.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out), the one scene and any `inserts`. Fix every problem it reports. If the
   video has props of your own, look at them now with `render_style_props` (Step 3b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   page titles and the captions in a browser; an overlap is a measurement, so shorten the title or
   move what it reports. Balloons, caption boxes and sound effects are drawn into pictures, which
   `write_scene_config` already sized from their text.
3. **Look before you submit.** Call `preview_frames(video_id, frames)`, as the **tubematic-scene-config** skill's
   *Look before you submit* step says: frame 0, the first words of the turn and the payoff, and the way in and out of any
   insert. Fix what you see and look again. `submit_render` refuses with `preview_not_taken` until the current config
   has been looked at, and a config rewritten after the look needs a new look.
4. `submit_render(video_id)`.

In the handback, say how many pages and panels you made, who the cast is, which props you used, and
which props you drew yourself and why the library could not show them.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong character, a balloon pointing
at the wrong one, a crowded panel) is fixed in `props.comicPanels`: edit the cast, pages, panels and
items, then write, validate and submit again as above. Never change the video's style. If the voice
was redone, the word frames have changed: re-time every page, panel and item from the new timeline,
and recount the `emphasis` indexes.
