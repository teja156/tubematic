---
name: tubematic-terminal-doc
description: Author a Terminal Doc narrated Short as data — choose the skin, split the narration into beats, show each beat's one string, number or quote with the shipped moves (words that scramble in, letters that arc into a new word, strings encoded through a box, numbers resolving from noise, a ciphertext wall, guesses racing to a match, bracket notes with citations, one glow at a time), writing a move of your own only when none fits — then write it with write_scene_config, preview your moves, validate and submit it
---

# Tubematic Terminal Doc authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-terminal-doc` (its `visual_style` is `terminal_doc`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short in a dark typographic documentary look: sparse monospace capitals on a
near-black frame, where **the text is the picture**. A password lifts into a box marked HASH and
comes out as a hex digest; the letters of a word lift out and arc into a new order; a number
resolves out of flickering glyph noise, right to left; a grey wall of ciphertext fades up behind the
stage; guesses race through one slot until one locks red; a thin bracket under a string names it,
with a quoted source and a `[n]` citation below. One element glows red or blue at a time. The
captions are a terminal log strip under the stage, typed on word by word.

The look is **restraint**. Most of the frame is empty. A beat holds one idea: one string, one
number, one comparison. Something small changes every 1.5 to 3 seconds (a letter moves, a row
lights, a bracket draws on), and a transformation is always shown as motion, never as a cut.

**You write data.** The whole video is one installed scene, `TerminalDoc`, and everything about this
video is its `props.terminalDoc`: the skin, the beats, and the moves in each beat, timed to the
narration and placed in named slots. The renderer draws every glyph, the wall, the brackets and the
captions. There are no images in this style: never call `generate_image` or `generate_character`.
When no shipped move can show a beat, you may write one move of your own (**Step 3b**).

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`), and
`reference/example-move-caesar.tsx` is a finished move of your own. Read them before you write.

## Rules the tools enforce

`write_scene_config` refuses a Terminal Doc config that breaks any of these, and says which beat and
event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "TerminalDoc", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"terminalDoc":
  {...}}}`.
- **Beats** are cuts: the first starts at frame 0, the others on a word (within 2 frames of a word's
  `startFrame`), each at least 2 seconds long, at most 40 beats. A beat starts empty.
- **Events** in a beat are listed in frame order, at most 24, each inside its beat. A move must
  finish at least 15 frames before its beat's cut, or nobody sees it land.
- **Slots:** one element per slot at a time. A slot is freed by a `clear`, or by a `rearrange` or
  `encode` that takes the element's letters, once the last of them has left. An `encode`'s box holds
  slot `b` until it has played, a bracket's note holds the `note` slot until the cut, and a bracket
  that reaches below its slot holds the slot below until its element is cleared.
- **Restraint:** at most 4 elements on screen at once, the context line and a bracket's note
  included.
- **Fit:** a string fits the frame at its size: at most 40 characters at `s`, 25 at `m`, 16 at `l`,
  12 at `xl`. A context line is size `s` or `m`; a note wraps to at most 2 lines of 36 characters.
- **Stage text never repeats 4 or more narration words in a row.** The captions carry the sentence;
  the stage shows the thing the sentence is about.
- **Order:** a `rearrange`, `encode`, `bracket` or `glow` acts on an element that is on stage and has
  finished its own move. A typed command and a move of your own do not glow, and a move of your own
  takes no bracket. Only a word, a single-line number (no exponent) or a string another move made can
  be the `from` of a `rearrange` or `encode`: a grid, a typed command and a move of your own cannot,
  and neither can an element that already has a bracket (transform first, then bracket).
- **Push:** under a beat's `push`, every string must still fit at its size times the push's scale,
  and a beat with a push has no move of your own.
- **Never still:** something changes on stage at least every 3 seconds.
- **Your own moves:** at most 6 per video, each a `move-<name>` file of this video that exists before
  the config is written, lasting 15 to 240 frames and given at most 40 characters of text. The file
  default-exports the move, imports only `react`, `remotion` and
  `../../installed/terminalDoc/kit` (or `contract`) with a static `import` (never `require` or
  `import(...)`), and uses no filter, gradient (SVG or CSS), backdrop filter, blend mode, pattern,
  dashed stroke, image, audio or video, `staticFile`, `delayRender`, fetch, randomness, clock,
  `performance.now`, state, effects or timers (`useState`, `useRef`, `useEffect`, `setTimeout`),
  `useCurrentFrame` or `useVideoConfig`: it is a pure function of `t`. The check reads comments too,
  so do not name any of these in a comment either.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs (each names the
   string, number or source the beat shows), the comments, and `mascot`.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`. Every frame you write comes from here.

## Step 1 — the skin

`skin` is `house` or `crt`, for the whole video.

- `house` (the default): near-black, white and grey monospace, red and blue glow. Use it for almost
  everything: ciphers, passwords, security, how a computer handles text and numbers.
- `crt`: amber phosphor on dark glass, pixel lettering, scanlines. Use it when the topic itself is
  retro computing: early machines, hacker lore, a 1980s or 1990s system, a famous old program or
  message. A person may ask for it in a comment.

The captions follow the skin by themselves.

## Step 2 — beats

Cut to a new beat when the narration moves to a new idea: from the password to its hash, from the
hash to the keyspace, from the attack to the defence. A beat is usually one or two sentences, 3 to 10
seconds. Inside a beat, build: the context line, then the string, then what happens to it, then the
bracket or glow that says why it matters.

`cut: "collapse"` (the screen squeezes to a line, like a CRT turning off) marks a turn in the
argument; use it once or twice per video at most. Every other cut is hard.

## Step 3 — moves

Every element has an `id` (lowercase, unique in its beat) and most go in a **slot**:

| Slot | Where | Holds |
|---|---|---|
| `context` | above the stage | one mono question or label for the beat, size `s` or `m`, usually `grey` |
| `a`, `b`, `c` | the stage, top to bottom | the strings, numbers and commands |
| `stage` | all of `a`, `b` and `c` | a `grid`, or a wide move of your own |
| `note` | below the stage | a bracket's quoted source and citation (written by `bracket`) |

The captions sit below the note slot, and the bottom of the frame stays empty.

| Move | Shows | Fields |
|---|---|---|
| `word` | a string appearing in a slot | `id`, `slot`, `text`, optional `size`, `tone`, `reveal` (`scramble`, `type`, `cut`), `accent` (a part of the text drawn in red) |
| `rearrange` | the letters of one element lifting and arcing into a new string; letters it lacks come out of noise | `id`, `from`, `text`, optional `slot` (where the new string lands), `size`, `tone` |
| `encode` | a string flying into a box labelled with an operation and coming out as another string | `id`, `from`, `text`, `slot`, `label` (`HASH`, `BASE64`, `XOR`), optional `sub` (`SHA-256`), `size`, `tone` |
| `number` | a number resolving out of noise right to left, or counting up | `id`, `slot`, `value`, optional `size`, `tone`, `count` (frames to count up from 0) |
| `wall` | the grey ciphertext wall behind the stage | `level`: 0 off, 1 faint, 2 bright |
| `grid` | an alphabet or table building row by row across the stage | `id`, `rows`, optional `size` (`s` or `m`), `tone` |
| `stream` | guesses racing through a slot and locking on the target in red | `id`, `slot`, `guesses`, `target`, `frames` (30 to 150), optional `size` (`m` or `l`) |
| `bracket` | a hairline under an element with a short label, and optionally a quoted note with a citation | `target`, `label`, optional `tone`, `note`, `cite` |
| `glow` | one element, or one `row` or `span` of it, turning red or blue | `target`, `tone` (`red`, `blue`), optional `row`, `span` |
| `type` | a command typed behind a `$` prompt, then its output | `id`, `slot`, `text`, optional `output` (up to 3 lines), `size` (`s` or `m`) |
| `push` | a slow push-in over a held beat (once per beat) | `frames` (45 to 450), `scale` (1.02 to 1.15) |
| `clear` | elements fading out, freeing their slots | `targets` |
| `custom` | a move of your own (Step 3b) | `id`, `move`, `slot`, optional `text` |

**What each move is for.**

- A hash, an encoding, an encryption: `encode`. It goes from slot `a` to `c` or from `c` to `a`, and
  the box takes slot `b` between them, so `b` must be empty while it plays.
- An anagram, a transposition, a word built up from another: `rearrange`.
- A count, a keyspace, a time to crack, a date as the punchline: `number`. Use `^` for an exponent
  (`"1.3 × 10^31"`).
- An alphabet, a cipher table, a substitution key: `grid`, then `glow` with `row` or `span` on the row
  or letters that matter.
- A brute-force attack, a search: `stream`.
- A cited claim: `bracket` with `note` and `cite`, the source as the narration names it
  (`"THE NEW YORK TIMES, 1990"`).
- What the computer is told: `type`.
- Atmosphere behind a dense subject (ciphertext, a dump, noise): `wall` at 1, briefly 2 for the
  moment it matters, then back to 0.

**Glow is emphasis.** One glowing element at a time: a new glow fades the last one out. Red is the
key, the danger, the match, the attacker; blue is the other side of a comparison, the defender, the
stored value. Glow the thing the narration is talking about at that moment, on its word.

**Tones.** `white` for the subject, `grey` for context, `dim` for what is past, `red` and `blue`
only with meaning. Write strings in capitals, except a command, code or a value whose case matters.

**Timing.** Put each move's `at` on the word that names its thing. A move takes time to play (a word
9 frames, an encode about 3 frames per letter plus 36, a number about 1.4 frames per character plus 7;
`reference/contract.md` has every one), and anything acting on its element waits until it has
finished.

## Step 3b — a move of your own

Write one only when no shipped move can show a beat: a Caesar shift, an XOR of two strings, bits
flipping, a checksum adding up. Keep it to one or two per video.

1. Read the kit with `read_scene_file` (`source="installed"`, `scene_name="terminalDoc/kit"`) and
   `reference/example-move-caesar.tsx`.
2. Write a component that draws from the props it is given: `t` (its own frame: 0 at its event,
   `frames` at its end and after), `frames`, `text`, `box` (the slot it draws in, in frame pixels),
   `skin` (the colours and font) and `seed`. Draw glyphs with the kit's `Glyph` or `Row` in
   `skin.tones`, place them with `cellX`, ease with `ease` and `clamp01`, and make noise with
   `noiseGlyph` and `seed`. It must settle: at `t = frames` it shows its final state.
3. Write it with `write_scene_file(video_id, "move-<name>", tsx)` and list it in `customMoves`:
   `{"id": "caesar", "src": "<the src write_scene_file returned>", "frames": 60, "text": 12}`. Use it
   with a `custom` event: `{"type": "custom", "at": ..., "id": "shift", "move": "caesar", "slot":
   "b", "text": "ATTACK"}`.
4. After `write_scene_config`, call `preview_terminal_moves(video_id)` and look at the picture: four
   moments of each move inside its slot box. Ink outside the box will run into the next slot; text
   too small to read, a move that does not show what the narration says, or a last moment that is
   not the final state: rewrite it. Rewrite the file and call `preview_terminal_moves` again; three
   looks at most. `validate_job` typechecks the file and checks it against the rules above again.

## Step 4 — captions and mascot

Leave `subtitles` out. The style sets the typed log captions in the skin's colours; a key you set
overrides them, so leave them alone.

If `get_video` has a `mascot`, add its cue track as the mascot skill describes. Keep it in the bottom
of the frame, below the captions and off the stage, and bring it on only for a few reactions.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "dark"` (or leave it out) and the one scene. Fix every problem it reports. If the video has moves
   of your own, look at them now with `preview_terminal_moves` (Step 3b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   stage text in a browser; an overlap is a measurement, so move, shorten or clear the text.
3. `submit_render(video_id)`.

In the handback, say which skin you chose and why, how many beats you made, which moves carried the
video, and any move you wrote yourself and why no shipped move could show it.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong value, a crowded beat, a glow
on the wrong thing, a string cut off) is fixed in `props.terminalDoc`: edit the beats and events, then
write, validate and submit again as above. Never change the video's style. If the voice was redone,
the word frames have changed: re-time every beat and event from the new timeline.
