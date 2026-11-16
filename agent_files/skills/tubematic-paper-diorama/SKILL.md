---
name: tubematic-paper-diorama
description: Author a Paper Diorama narrated Short as data — pick a paper room and a taped banner per beat, stand paper props and the house critter in named slots, time pop-ins, swaps, stamps, rings, routes, labels and the critter's faces to the narration's words, build any missing prop from paper pieces and check it with render_paper_props — then write it with write_scene_config, validate and submit it
---

# Tubematic Paper Diorama authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-paper-diorama` (its `visual_style` is `paper_diorama`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its `style.authoring_skill`
names.

---

## What you are making

A vertical 1080x1920 Short told inside paper rooms. Each beat is a **set**: one room of cut paper (a
diner, a bank vault, a courtroom) with a cream **banner** taped across the top that names the beat in
two to five words. On the stage, **props** of flat cut paper (a laptop, an envelope, a padlock, a server
rack) pop, slide or drop into place on the stressed words, and the house **critter** (a small boxy clay
creature with eyes, no mouth and stubby legs) stands among them and reacts with its face. Red rubber
**stamps** slam in, red **rings** are drawn around a prop, dark **label** pills name things, a dotted
paper **route** joins two props, and a **snap zoom** punches in on a hit. The captions are torn coral
paper tags, one per word, low on the floor.

**You write data, never code.** The whole video is one installed scene, `PaperDiorama`, and everything
about this video is its `props.paperDiorama`: the critter's look, any props of your own (as paper
pieces, below), and the sets timed to the narration. The rooms, props, critter, banner, stamps and
captions are drawn by the renderer. This style makes no images: never call `generate_image` or
`generate_character`.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three before
you write.

## Rules the tools enforce

`write_scene_config` refuses a Paper Diorama config that breaks any of these, and says which set, item
or event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "PaperDiorama", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"paperDiorama": {...}}}`.
  Insert scenes go in the config's own `inserts` list (**Inserts** below).
- **Sets** are cuts: the first starts at frame 0; the others start on a word (within 2 frames of a
  word's `startFrame`); each lasts at least 1.2 seconds; at most 24.
- **Everything happens on a word.** Every item's `at` (except one at its set's start) and every
  event's `at` is within 2 frames of a word's `startFrame`, inside its set, and at least 8 frames
  before the set ends.
- **Slots, never coordinates.** A prop stands in a slot (`l`, `cl`, `c`, `cr`, `r`, left to right) at
  a level (`floor`, `shelf`, `air`) at a scale (`s`, `m`, `l`). Two things on stage at once may not
  stand on top of each other (the critter counts), nothing may run off the frame's edge, and nothing
  may reach up into the banner.
- **Props** are the shipped props `get_video` lists under `style.extra.props` (name and size), or your
  own `customProps`. A `swap` changes a prop to another of the **same size**, such as its other state
  (`envelope` to `envelope-sealed`).
- **Events** act on an item of their own set that has entered and not left, or on `"critter"` (only
  `expr`, `hop` and `move`).
- **Lengths:** a banner at most 28 characters, a label 16, a stamp 12.
- **The camera** holds still: at most 3 `zoom` events in the whole video, for the hits that matter most.
- **Never still:** something new on the stage (a cut, an entrance, an event) at least every 3 seconds. A silent pause in the narration (a `[pause]`, a `[long pause]`) is not counted: the stage may hold through one.
  The critter's idle bob does not count.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs (set briefs: the
   room, the banner and what happens), the comments, and `style.extra` (the rooms, the props and their
   sizes, the critter's expressions and accessories).
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1 — plan the sets

One set per idea, usually one per sentence or two; a new idea is a new room and banner. A set holds
2 to 5 seconds. Pick each set's room for what the idea is about, not for variety alone:

| Room | Reads as |
|---|---|
| `bedroom-day` | home, the viewer's own device, everyday life |
| `diner` | a public place, a cafe, strangers nearby |
| `bank-vault` | money, secrets, safekeeping, a heist |
| `mission-control` | servers, the cloud, monitoring, the internet |
| `courtroom` | rules, judgement, blame, consequences |
| `warehouse` | storage, shipping, things piling up |
| `airport-gate` | travel, waiting, departures, a journey |
| `subway-platform` | a network, routes, schedules, crowds |

The banner names the beat in capitals-friendly words: "FREE CAFE WI-FI", "A VPN SEALS IT". Never the
whole sentence; the captions carry the words.

## Step 2 — stage each set

Choose the props that stand in for the idea: a note for data, a padlock for encryption, a server rack
for the cloud, coins for money. One hero prop per set, at most six things on stage. Give the critter a
slot in most sets (`critter: {"slot": "l"}`; `null` or no `critter` leaves it out) and its accessory
for the whole video in `critter.acc` (a `cap` for an everyday viewer, a `hardhat` for building, a
`headset` for support, `glasses` for a careful thinker).

Size matters on a phone: make the hero prop `m` or `l`; use `s` for small things beside it. Keep a slot
between big things: the critter takes about one and a half slots, so a prop next to it goes two slots
away (critter `l`, prop `c`). `shelf` and `air` hang a prop higher up the wall, which is fine in paper.

Then time the events, one per stressed word:

| Event | Does | Fields |
|---|---|---|
| (item `at`) | the prop enters: `pop` (default), `slide` in from the nearest side, or `drop` from above | `enter` on the item |
| `exit` | the prop shrinks away | `target` |
| `move` | the prop or the critter glides to another slot | `target`, `to`, optional `level` |
| `swap` | the prop becomes its other state in a frame | `target`, `prop` |
| `expr` | the critter's face: `idle`, `happy`, `shock`, `worried`, `squint`, `sleep` | `target: "critter"`, `value` |
| `hop` | a little hop | `target` (an item or `"critter"`) |
| `stamp` | a red stamp slams in over a prop, or mid-stage | `text`, optional `target`, `level`, `color` |
| `ring` | a red ring is drawn around a prop | `target`, optional `color` |
| `route` | a dotted paper path unrolls from one prop to another | `from`, `target`, optional `color` |
| `label` | a dark pill names a prop | `target`, `text` |
| `zoom` | a snap zoom onto a prop, back after half a second | `target` |

Each set may also take `cut: "tear"` (the new room is torn in from the bottom, for a turn or a new
chapter; the default is a hard `cut`).

The critter reacts on the word that earns it: `shock` when something goes wrong, `worried` on a risk,
`happy` on the fix, `squint` on a doubt. Never on every word.

## Step 3 — props of your own

When no shipped prop stands for a thing, build it from paper pieces in `customProps`:

```json
"customProps": {
  "ticket": {"w": 220, "h": 120, "pieces": [
    {"shape": "rect", "fill": "paper", "x": 0, "y": 0, "w": 220, "h": 120, "r": 8, "shade": "creamLo", "shadeH": 0.15},
    {"shape": "rect", "fill": "tag", "x": 0, "y": 0, "w": 50, "h": 120, "r": 8},
    {"shape": "text", "fill": "ink", "text": "ADMIT", "font": "banner", "size": 30, "x": 135, "y": 60}
  ]}
}
```

A piece is a `rect`, `ellipse` (its box `x, y, w, h`), `poly` (`points`) or `text` (centred at `x, y`),
filled with a palette colour name (never a hex value), with an optional darker `shade` strip along its
bottom, a lighter `hi` strip along its top, and a `rot` in degrees. Pieces paint in order, later on top,
and stay inside the prop's `w` x `h`. Build the silhouette first, then stack lighter and darker pieces
for shading, as the shipped props do. Text on a prop is a short generic word, never a brand.

Write the config, then call `render_paper_props(video_id)` and look at every prop of yours: it must
read as what it stands for at phone size. Fix what does not, write again and look again.

## Step 4 — write and check

1. `write_scene_config(video_id, config)`. Leave `subtitles` out: the style fills in its own torn-tag
   captions. Fix every problem it lists.
2. `validate_job(video_id)`. Read every warning.
3. **Look before you submit.** Call `preview_frames(video_id, frames)` first, as the **tubematic-scene-config** skill's *Look before you submit* step says: frame 0, the first words of the turn and the payoff, and the way in and out of any insert. Fix what you see and look again. `submit_render` refuses with `preview_not_taken` until the current config has been looked at.
   Check the props of your own with `render_paper_props`. Then read back the config once against the
   narration: each set's room and banner fit what is said, each event lands on the word it shows, and
   the critter's face matches the moment.
4. `submit_render(video_id)`.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame`. The first
segment's role is `opening`. A `turn` or `reopen` segment needs a visible change on its first word, the
`payoff` segment the video's strongest picture, and a segment with role `""` only its own brief.
`get_video`'s `style.picture` says how this style does each; in short:

- Opening: set 1 is the room of the first sentence with its banner, and the first sentence's subject
  as a prop entering at frame 0.
- Turn or re-opening: a new set (often with `cut: "tear"`) on its first word, or a stamp or ring on it.
- Payoff: the payoff set's prop the largest thing on stage, with a stamp, a ring or a `zoom` on the
  payoff word.
- Ending: hold on the payoff set to the last frame. No closing card, recap or sign-off.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has no new set, entrance or event within about 0.4 s of its first word. Fix what is a real miss; say in
the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. The stage is hidden while an insert plays, so inside each insert's window no set
starts, no prop enters and no event lands; `write_scene_config` refuses one that does. Put the set's
events before and after the window, and bring the stage back on the next word after it. The captions
stay on screen through the insert. Write any `inserts` in the same `write_scene_config` call as the
scene.

## Revising

Read every comment and the AI review's findings. Change only what they name: a wrong prop, an event on
the wrong word, a crowded stage. Keep the rest as it was, write the whole config again, validate and
submit.
