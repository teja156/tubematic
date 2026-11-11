# Terminal Doc data contract

The shape of `props.terminalDoc` on the one `TerminalDoc` scene. `write_scene_config` checks every
rule here before the config is written.

```json
{
  "skin": "house",
  "beats": [
    {"start": 0, "events": [ ... ]},
    {"start": 291, "cut": "collapse", "events": [ ... ]}
  ],
  "customMoves": [
    {"id": "caesar", "src": "<video_id>/move-caesar", "frames": 60, "text": 12}
  ]
}
```

## The video

| Field | Values |
|---|---|
| `skin` | `house` (near-black, white and grey, red and blue glow) or `crt` (amber phosphor, scanlines) |
| `beats` | 1 to 40 beats; the first starts at frame 0 |
| `customMoves` | optional, at most 6 moves of your own |

## A beat

| Field | Values |
|---|---|
| `start` | the frame the beat cuts in: within 2 frames of a word's `startFrame` (the first: 0). A beat lasts at least 2 seconds |
| `cut` | optional: `hard` (the default) or `collapse` (the previous beat squeezes to a line and a dot, like a CRT turning off) |
| `events` | at most 24, in frame order, each with a whole-number `at` inside the beat |

A beat starts empty. Every event's move must finish at least 15 frames before the beat's cut.

## Slots and sizes

| Slot | Centre (y px) | Sizes | Notes |
|---|---|---|---|
| `context` | 384 | `s`, `m` | one line above the stage |
| `a` | 640 | `s`, `m`, `l`, `xl` | top of the stage |
| `b` | 845 | `s`, `m`, `l`, `xl` | middle of the stage; an `encode` box takes it |
| `c` | 1050 | `s`, `m`, `l`, `xl` | bottom of the stage |
| `note` | 1248 | `s` | a bracket's note goes here |
| `stage` | 845 | `s`, `m` | all of `a`, `b` and `c` at once |

| Size | Type (px) | Characters across the frame |
|---|---|---|
| `s` | 40 | 40 |
| `m` | 64 | 25 |
| `l` | 96 | 16 |
| `xl` | 128 | 12 |

Every glyph sits in a cell 0.6 of its size wide, so the character count decides the fit. One element
per slot at a time; at most 4 elements on screen at once, the context line and a note included.
Default sizes: a word in `context` or `note` is `s`, a `number` is `xl`, a `type` is `m`, a `grid` is
`s`, anything else `l`.

Tones: `white`, `grey`, `dim`, `red`, `blue`.

## Moves

Frames per move are how long it plays; anything acting on its element (a `rearrange`, `encode`,
`bracket` or `glow`) starts after it.

| `type` | Fields | Frames |
|---|---|---|
| `word` | `id`, `slot` (not `stage`), `text`; optional `size`, `tone`, `reveal` (`scramble`, `type`, `cut`), `accent` (a part of `text` drawn in red) | 9 to scramble, 1 to cut, the text's length ÷ 1.6 to type |
| `rearrange` | `id`, `from` (an element on stage), `text`; optional `slot` (default: the source's), `size`, `tone` | 16 + 3 per letter after the first (letters of the longer string) |
| `encode` | `id`, `from` (in slot `a` or `c`), `text`, `slot` (the other of `a` and `c`), `label` (1 to 12 characters); optional `sub` (1 to 12), `size`, `tone` | 36 + 3 per letter of the source after the first. Slot `b` must be empty when it starts and stays taken by the box until it ends |
| `number` | `id`, `slot` (not `stage`), `value`; optional `size`, `tone`, `count` (15 to 240 frames, a whole number with commas or none, counted up from 0) | 7 + 1.4 per character after the first (spaces and `^` do not count); `count` when set |
| `wall` | `level`: 0, 1 or 2 | 9 (the fade). The level holds across beats until the next `wall` |
| `grid` | `id`, `rows` (1 to 8 strings); optional `size` (`s`, `m`), `tone` | 9 + 4 per row after the first. Takes the whole stage; the rows must fit its height |
| `stream` | `id`, `slot` (`a`, `b`, `c`), `guesses` (1 to 40 strings), `target`, `frames` (30 to 150); optional `size` (`m`, `l`) | `frames`. Locks the target in red |
| `bracket` | `target`, `label` (1 to 16 characters); optional `tone` (default `red`), `note`, `cite` (1 to 99, with a note) | 23. The note and `[cite]` type into the `note` slot and hold it to the cut; the note and its citation wrap to at most 2 lines of 36 characters |
| `glow` | `target`, `tone` (`red`, `blue`); optional `row` (a grid row, from 0), `span` (`[first, last + 1]` character positions) | 10. A later glow fades this one out. Not on a `type` or `custom` element; no `span` on a number with an exponent |
| `type` | `id`, `slot` (`a`, `b`, `c`), `text` (the command; the `$ ` prompt counts in the fit); optional `output` (up to 3 lines, each fitting at `s`), `size` (`s`, `m`) | the text's length ÷ 1.6 + 2 per output line + 9. Command and output must fit the slot's height |
| `push` | `frames` (45 to 450), `scale` (1.02 to 1.15) | `frames`. One per beat; the stage holds the push to the cut. Every string in the beat must fit at its size times `scale`, and the beat has no `custom` move |
| `clear` | `targets` (ids on stage) | 8. Their slots are free after it |
| `custom` | `id`, `move` (a `customMoves` id), `slot` (`a`, `b`, `c`, `stage`); optional `text` (within the move's `text`) | the move's `frames` |

A bracket that reaches below its slot (a large string at the bottom of a band) needs the slot below it
empty, and holds it until its element is cleared (its own note may go there). A `rearrange` or
`encode` holds its source's slot until the last of the source's letters has left it, and its `from`
is a `word`, a number without an exponent, or a string a `rearrange`, `encode` or `stream` made:
never a `grid`, a `type` or a `custom` element. A `bracket` never goes under a `custom` element. Stage text (a word, a string a move makes, a label, a note, a grid row, a command or its
output) may not repeat 4 or more narration words in a row.

## Moves of your own

| Field | Values |
|---|---|
| `id` | lowercase letters, digits or `_`, not a shipped move's name |
| `src` | the src `write_scene_file` returned for this video's `move-<name>` file: `"<video_id>/move-<name>"` |
| `frames` | 15 to 240 |
| `text` | 0 to 40: the most characters a `custom` event may give it |

The file default-exports a component taking `MoveProps` from `../../installed/terminalDoc/kit`:

| Prop | Meaning |
|---|---|
| `t` | the move's own frame: 0 at its event, `frames` at its end and after |
| `frames` | its length |
| `text` | the event's text |
| `box` | the slot it draws in, `{x, y, w, h}` in frame pixels |
| `skin` | `tones` (the five tone colours), `font`, `fontScale`, `weight`, `noise`, `line`, `bloom` |
| `seed` | a number fixed for this element, for `hash` and `noiseGlyph` |

The kit also has `Glyph` (one glyph centred on a point), `Row` (a centred row of glyphs), `cellX`,
`cellOf`, `scramble`, `typed`, `noiseGlyph`, `hash`, `ease`, `tween`, `clamp01`, `lerp`, `quad` and
`glowShadow`. A move imports only `react`, `remotion` and `../../installed/terminalDoc/kit` (or
`contract`) with a static `import`, and uses no filter, gradient (SVG or CSS), backdrop filter,
blend mode, pattern, dashed stroke, image, audio or video, `staticFile`, `delayRender`, fetch,
`import(...)`, `Math.random`, `Date`, `performance.now`, state, effects or timers (`useState`,
`useRef`, `useEffect`, `setTimeout`, `requestAnimationFrame`), `useCurrentFrame` or `useVideoConfig`.
