---
name: tubematic-case-file-story
description: Author a Case File Story narrated Short as data — make the video's lead sheet from the house lead, generate painted stills of the story's scenes with the lead painted in (at most 16) and check each with read_image, time shots, punch-ins and meter changes to the narration, add the count, bars and term cards and the closing choice — then write it with write_scene_config, validate and submit it
---

# Tubematic Case File Story authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-case-file-story` (its `visual_style` is `case_file_story`). Also take it, on **Revising**,
for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short that tells a suspense story to the viewer: "you" are inside a scheme or a
money dilemma. The pictures are painted stills that fill the frame and push in slowly; on a word that
lands, the same painting cuts hard to a tighter crop (a **punch-in**). The person in the paintings is
the **lead**: one house character with a smooth ivory rounded-cube head, round black glasses and short
eyebrows, no nose and no mouth, who stands in for the viewer. A row of two or three **meters** near the
top (cash, money banked, suspicion) changes as the plot moves. Between shots, **cards** make the
numbers physical: a grid of icons that fills while a counter climbs, bars appearing one by one under a
dashed limit, a term with its definition and a tilted stamp. The video ends on the last painting with
two **choice** buttons. Captions sit at 72% of the height and show a short phrase at once, the words
still to come in grey.

**You write data, never code.** The whole video is one installed scene, `CaseFileStory`, and everything
about this video is its `props.caseFile`: an accent colour, the meters and the beats timed to the
narration. The meters, the cards, the stamp, the buttons and the captions are drawn by the renderer.
You make the paintings with `generate_image`; never call `generate_character` (the lead is painted
into each still from a reference picture, not cut out).

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses a Case File Story config that breaks any of these, and says which meter or
beat is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "CaseFileStory", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"caseFile": {...}}}`.
- **Meters:** 2 or 3, each `{id, label, kind, value}`. The label is at most 12 characters in capitals;
  `kind` is `money`, `count` or `percent`; a value is a whole number from 0 (a percentage at most 100).
- **Beats** are cuts: the first starts at frame 0 and is a `shot`; the others start on a word (within
  2 frames of a word's `startFrame`), at most 48 beats. A beat takes only its own fields.
- **The ending:** exactly one `choice`, and it is the last beat. A `term` card comes somewhere before
  it: the consequence is shown before the viewer is asked to choose.
- **Stills:** at most **16 different ones per video**, besides the lead sheet. `generate_image`
  refuses a 17th new still; reuse a still in another shot with a different `focus` or a punch-in. An
  `image` is the `public_path` `generate_image` returned. The lead sheet (`lead`) is a reference and is
  never an `image`.
- **A shot** lasts at least 1 second. A punch-in lands on a word, at least 12 frames after the shot
  starts and before it ends. `set` may name only meters `hud` lists; `panel` names a meter this shot's
  `set` changes.
- **Card parts land on words:** each bar's `frame`, and `resultFrame`, `payoffFrame`,
  `definitionFrame`, `stampFrame` and `optionFrames` when you give them. Bars are at least 8 frames
  apart. A card's last part needs at least 20 frames on screen before the beat ends.
- **Lengths:** a card title is at most 26 characters, a unit line 26, a result 14, a bar label 6, a
  threshold label 24, a payoff line 30, a term 26, a definition 110, a stamp 16, a citation 34, a
  choice option 10. A term, a stamp and the options are in capitals.
- **Never still:** something new (a cut, a punch-in, a part of a card) at least every 4 seconds.

`generate_image` refuses, before any paid call: a `reference` on a video of another style, the lead
sheet made without `reference="house"`, a `reference` naming a picture that does not exist yet, and a
picture past the cap.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, and the comments.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1 — plan the beats

Read the segments' `visual` briefs: each is a shot brief (a place, what you are doing, the light) or a
card brief. Lay the story out as beats:

- A **shot** for each moment of the story. A new still when the place or the moment changes; the same
  still again, or a punch-in on it, when a line lands on one word. A shot holds 2 to 4 seconds.
- A **count** card where the narration makes one number physical ("that is two thousand bills").
- A **bars** card where it says several amounts one by one against a limit ("nine thousand on Monday,
  nine on Tuesday").
- A **term** card where it names what this is and what it is in law: the consequence.
- The **choice** on the sentence that is only the two options: the script's last, or the one before
  a closing line when the preferences asked for one.

Plan the stills first and count them: 8 to 12 is usual, 16 is the ceiling. Choose the meters from what
the script counts, and note the beat where each value changes.

## Step 2 — make the lead sheet

The lead looks the same in every video apart from the clothes. Decide one outfit that fits who "you"
are in this story (a grey hooded jacket and jeans, an office shirt with a lanyard) and keep it for the
whole video. Then, once:

```
generate_image(video_id, "lead", "<the outfit, in one sentence>", reference="house")
```

The prompt is only the outfit. The server adds the lead's description and makes a sheet of three views.
Open it with `read_image(video_id, "lead", grid=False)` and check it: the ivory rounded-cube head, the
round black glasses, the eyebrows, no nose or mouth, and your outfit. Regenerate under the same name
if not. The sheet is a reference for the stills and is never shown in the video.

## Step 3 — make and check the stills

For a still **with the lead** in it:

```
generate_image(video_id, "<name>", "<the scene>", reference="lead")
```

For a still **without the lead** (an object, a street, an empty room), leave `reference` out and end
the prompt with "No people." Name a still anything except `lead` and `house`, which are kept for the
two sheets.

The prompt is only the scene. The server adds the lead's description and the painting style to every
prompt, so do not describe the lead's head or the art style. Write three things:

1. **The moment and the light:** "Night." "Late evening, wet street." "Cold fluorescent office light."
   One strong coloured light makes the look: neon through blinds, a street lamp, a bare bulb, a laptop
   screen, police lights from off screen.
2. **The place and what the character is doing**, with the camera's view: "The character sits on the
   floor of a storage unit, facing us, counting bundles of banknotes." "Seen from behind over the
   shoulder." "Extreme close-up of the head and shoulders, looking over one shoulder." Call the lead
   "the character". Vary the view from still to still: wide, over the shoulder, profile, close-up.
3. **Anyone else** as "a second plain figure" with what they do (a teller behind glass, a guard at a
   door). Other people are drawn as plain grey-headed figures; never describe a face.

Keep what matters (the head, the hands, the object) in the middle of the picture: the meter row covers
a strip near the top, the captions sit at 72% of the height, and the last still carries two buttons
across its lower fifth. Never ask for writing, a logo, a brand, a real bank or a real place in a
picture, and never for a weapon or violence.

Open every still with `read_image(video_id, "<name>")` (the grid is on) and check:

- it shows what the narration says at that moment;
- the lead is the same character as on the sheet: the same head shape and colour, the glasses, the
  same clothes, no nose or mouth;
- there is no lettering, logo or brand in it.

Regenerate under the same name if any of these fails (a regeneration replaces the still and does not
count against the 16). Then read off the grid, per still, the `[u, v]` of what the shot is about (its
`focus`) and of what a punch-in should close on (u left to right, v top to bottom, 0 to 1).

## Step 4 — meters and beats

`props.caseFile` is `{"accent", "hud", "beats"}`.

- `accent` is one of `pink`, `amber`, `teal`, `red`: the colour of the stamp, the threshold, the
  percentage meter and the second choice button. `pink` is the house colour; take `red` for a story
  about danger or the law closing in, `amber` for money and greed, `teal` for a cold, technical scheme.
- `hud` lists the meters with their starting values. Name them from the story (`CASH`, `BANKED`,
  `SUSPICION`; `EMAILS SENT`, `REPLIES`, `RISK`). A `percent` meter is drawn in the accent colour.

| Beat | When | Fields |
|---|---|---|
| `shot` | a moment of the story | `image`, optional `focus` [u, v], `punch` `{frame, at}`, `set` (meter id to new value), `hud` (`false` hides the meter row for a close-up), `panel` (a meter id) |
| `count` | one number made physical | `title`, optional `unit`, `icon`, `to`, `kind`, `result`, optional `resultFrame` |
| `bars` | amounts against a limit | `title`, `kind`, `threshold` `{value, label}`, `bars` (each `{label, value, frame}`), `payoff`, optional `payoffFrame` |
| `term` | the name of what this is | `term`, `definition`, `stamp`, optional `citation`, `definitionFrame`, `stampFrame` |
| `choice` | the last sentence | `image`, optional `focus`, `options` (two labels), optional `optionFrames` |

**Shots.** Start a shot on the first word of its line. `focus` is where the slow push-in closes on
(default the middle, slightly high). A `punch` cuts to a crop one and a half times tighter around `at`,
on the word that lands ("twice", "report", "pays"): once on about every second or third shot, and on
any shot longer than 4 seconds. Put a meter's new value in `set` on the shot where the narration says
it; it changes on that cut. When suspicion or risk jumps, add `panel` with that meter's id: a large
panel shows it counting up over the shot.

**Icons** for a count card: `bill`, `coin`, `envelope`, `person`, `box`, `card`, `phone`, `document`,
`key`, `goldbar`. Take the one the number counts. The grid shows forty icons, or the number itself
when it is under forty, so say in `unit` what one stands for when the number is larger ("each one is
50 bills").

**Timing a card's parts.** A card starts on the first word of its line. Give each bar the `frame` of
the word that counts it. Put the result, the payoff line, the stamp and each choice button on the word
that says it (`resultFrame`, `payoffFrame`, `stampFrame`, `optionFrames`); leave one out and that part
follows the one before it after a short fixed delay, which is right only when the card is short.

**The term card** is the consequence. `term` is the real name of what happened, `definition` one plain
sentence, `stamp` what it is ("FEDERAL CRIME", "FRAUD", "RED FLAG"), `citation` the real law or rule
when the script gives one. Use the script's words; never invent a law.

**The choice** reuses the last moment's still or a new one. `options` are the two things the last
sentence offers, in the order it says them, at most 10 characters each, in capitals. The second is drawn in
the accent colour.

## Step 5 — captions

Leave `subtitles` out of the config. The style fills in its own caption look; any key you set
overrides it.

## Step 6 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` from the timeline, `"canvas": "dark"` (or
   leave it out) and the one scene. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   meters and the cards in a browser; an overlap is a measurement, so shorten the text it names.
3. `submit_render(video_id)`.

In the handback, say how many stills you made, the outfit you gave the lead, the meters you chose, and
any still you regenerated and why.

## Revising

Read the comments on `get_video`. A comment about a picture (the lead looks different, the wrong
place, lettering in a painting) is fixed by regenerating that still under its own name, with
`reference="lead"` again, and checking it with `read_image`. A comment about a card, a meter or the
timing is fixed in `props.caseFile`. Then write, validate and submit again as above. Never change the
video's style, and do not remake the lead sheet unless the comment is about the lead's clothes: a new
sheet means every still with the lead must be remade to match. If the voice was redone, the word
frames have changed: re-time every beat and every card part from the new timeline.
