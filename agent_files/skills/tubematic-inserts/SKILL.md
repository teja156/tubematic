---
name: tubematic-inserts
description: Place a video's insert scenes (System Flow diagrams, Terminal Doc strings, Code Scenes code, Format Packs messages and lists) inside its main style — one insert inside each script segment marked as an insert, the main style's data held quiet under it, written in the config's inserts list — the rules every main-style authoring skill follows
---

# Tubematic insert scenes

**Invoke this skill when:** you are authoring a video's scenes at `VOICE_READY` or revising them at
`REVISION_REQUESTED`, with its main style's own skill, and `get_timeline(video_id)` shows a segment
whose `insert` is not `""`. Your main style's skill sends you here at its step for inserts. Read it
once, place the inserts, and go back to your main style's skill.

A video with no marked segment has no inserts. Never add an insert to a segment the script did not
mark.

---

## What you are making

The main style is drawn across the whole video, as always. An insert is a short scene in an insert
style, drawn over the main style for a window of frames inside a marked segment, and under the
captions. The main style goes into and out of it with its own transition (`style.inserts.transition`
on `get_video`), which the renderer draws: you write none of it.

## The config

Inserts go in a top-level list beside `scenes`. You write four keys per insert:

```json
"inserts": [
  {
    "style": "system_flow",
    "startFrame": 612,
    "durationInFrames": 228,
    "props": {"systemFlow": {"boards": [ ... ]}}
  }
]
```

- `style`: the segment's `insert` value from `get_timeline`.
- `startFrame`, `durationInFrames`: the window, in the video's frames.
- `props`: the insert style's data, under its props key (`systemFlow`, `terminalDoc`, `codeScenes`,
  `formatPacks`). Write it with the insert style's own skill, section **As an insert**
  (`tubematic-system-flow`, `tubematic-terminal-doc`, `tubematic-code-scenes`,
  `tubematic-format-packs`; the pack's `authoring_skill`). Its frames are the video's frames, like the main style's.

Leave out `src`, `palette`, `shift` and `insertTransition`: `write_scene_config` fills them. The
insert follows the video's canvas (a light video gets the insert's light look) and moves clear of the
main style's captions by itself.

## Placing the window

1. Take the marked segment's `startFrame` and `endFrame` from `get_timeline`, and its words from
   `get_timeline(video_id, include_words=True)`.
2. Start the window on the first word of the part the insert shows: the segment's first word, or a
   later word in it. It must start within 2 frames of a word's `startFrame`.
3. Make it last at most 8 seconds (the tool refuses past 9) and at least 2. When the segment is
   longer, cover the part that names what the insert shows and let the main style carry the rest.
4. End it no later than the next segment's first word.

The tool also refuses an insert in the first or last segment, over the payoff's first word, closer
than 1.5 seconds to the start, the end or another insert, and inserts that add up to more than a
third of the video. The script's marks already keep to these, so they come up only when a window is
placed carelessly.

## The main style under an insert

The main style is hidden while the insert covers the frame, and comes back on the picture its frame
gives it. So inside every window:

- **Nothing of the main style starts**: no cut (a new board, region, shot, chapter, plate or beat)
  and no event. Put the main style's next cut exactly on the window's last frame + 1 (the first frame
  after the insert), so the video comes back on something new, or let the picture from before the
  insert continue.
- The main style's "nothing changes for too long" rule skips the window; you do not need events in it.
- A scene system with several scenes (`tubematic-scene-config`) keeps its scenes covering every
  frame; no scene may start inside a window.
- A mascot is hidden during inserts and while they slide in and out: no mascot cue inside a window or
  within 12 frames either side of it.

Your main style's skill names its own exceptions (Case File Story takes inserts only over shots
before the term card).

## When the tool refuses

`write_scene_config` answers "The insert scenes have problems:" with one sentence per problem, naming
the insert and what to change, or your main style's own message naming a cut or an event inside an
insert. Fix every one and write again. A refusal about the insert's own data (a board, a beat, a
move) is fixed with the insert style's skill.

## Worked example

A Whiteboard video, 1500 frames, five segments of 10 seconds; the script marked segment 3
(frames 600 to 890) `"insert": "system_flow"`. The narration in it: "Your browser asks a resolver,
which asks the root servers, and gets back an address."

- Window: the first word "Your" starts at 600. The part worth a diagram runs to "address" ending at
  828. `startFrame` 600, `durationInFrames` 240 (8 s).
- Whiteboard: region 3 starts at 840, the first frame after the insert; no item has `at` from 600 to
  839.
- The insert: one board starting at 600, three nodes (browser, resolver, root), packets timed to
  "asks" and "gets back", a chip with the address. Written with `tubematic-system-flow`, **As an
  insert**.

```json
"inserts": [
  {"style": "system_flow", "startFrame": 600, "durationInFrames": 240,
   "props": {"systemFlow": {"boards": [{"startFrame": 600, "headline": "Who knows the address?",
     "nodes": [{"id": "browser", "label": "Browser", "icon": "browser"},
               {"id": "resolver", "label": "Resolver", "icon": "dns"},
               {"id": "root", "label": "Root Server", "icon": "server"}],
     "edges": [{"from": "browser", "to": "resolver"}, {"from": "resolver", "to": "root"}],
     "events": [{"type": "node", "node": "browser", "at": 600},
                {"type": "node", "node": "resolver", "at": 640},
                {"type": "edge", "edge": "browser>resolver", "at": 650},
                {"type": "packet", "edge": "browser>resolver", "at": 670},
                {"type": "node", "node": "root", "at": 700},
                {"type": "edge", "edge": "resolver>root", "at": 710},
                {"type": "packet", "edge": "resolver>root", "at": 730},
                {"type": "packet", "edge": "resolver>root", "at": 770, "reverse": true},
                {"type": "chip", "edge": "browser>resolver", "at": 790, "text": "93.184.216.34"}]}]}}}
]
```

## Checklist

- [ ] One insert inside every segment `get_timeline` marks, none anywhere else
- [ ] Each window starts on a word, lasts 2 to 8 seconds, ends by the next segment's first word
- [ ] The insert's data written with its style's skill, **As an insert**
- [ ] Nothing of the main style starts inside a window; its next cut sits at the window's end
- [ ] `src`, `palette`, `shift` and `insertTransition` left out
