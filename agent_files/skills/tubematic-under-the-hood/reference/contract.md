# Under the Hood: the data contract

Every field of `props.underTheHood`, with its limits. `write_scene_config` checks all of it. The
renderer's side is `renderer/remotion/src/scenes/installed/underTheHood/contract.ts`.

## The frame

A 1080 x 1920 frame in fixed zones, so nothing you place can land on another zone:

| Zone | From (y) | To (y) | Holds |
|---|---|---|---|
| Top margin | 0 | 270 | Nothing (the watermark is in its corner) |
| Caption band | 270 | 460 | The captions, centred at 365 (19%) |
| Plate band | 460 | 1350 | The photograph and everything pinned to it; the stat; the chart |
| Bottom left | 1400 | 1600 | The counter row (y 1400), the footnote (y 1560) |
| Bottom right | 1380 | 1920 | The presenter, from x 610 |

Chips stay between x 60 and 1020 and between y 468 and 1342.

## The whole video

```json
{"totalFrames": 858, "canvas": "dark", "subtitles": {"emphasis": [4, 15]},
 "scenes": [{"type": "generated", "source": "installed", "src": "UnderTheHood",
             "startFrame": 0, "durationInFrames": 858,
             "props": {"underTheHood": {"plates": [ ... ]}}}]}
```

## A plate

| Field | Type | Default | Rule |
|---|---|---|---|
| `start` | frame | | 0 for the first plate; then on a word, increasing; at least 1.5 s per plate; at most 30 plates |
| `image` | text | none | The `public_path` from `generate_image` for this video; none makes a plain dark panel (for a chart). At most 12 different images per video |
| `focus` | [u, v] | [0.5, 0.5] | The point of the photograph at the band's centre (x 540, y 905). Only with an image |
| `zoom` | number | 1 | 1 to 3. The photograph is 1080 px wide at zoom 1 and pushes in 1% per second on top of it |
| `enter` | `cut` or `zoom` | `cut` | `cut`: a 3-frame cross-fade. `zoom`: the camera rushes 1x to 4x into `through` on the previous plate over its last 6 frames, then this plate settles in from 1.25x over 8 |
| `through` | [u, v] | | With `enter: "zoom"` only: a point of the previous plate's photograph, visible when the zoom starts |
| `events` | list | [] | At most 16, in frame order |

The photograph must cover the plate band from the plate's first frame, which limits how far the focus
can move from the centre. For a square photograph (`aspect_ratio="1:1"`, which this style uses):

| `zoom` | `focus` u from | to | `focus` v from | to |
|---|---|---|---|---|
| 1 | 0.5 | 0.5 | 0.42 | 0.58 |
| 1.3 | 0.39 | 0.61 | 0.32 | 0.68 |
| 1.6 | 0.32 | 0.68 | 0.26 | 0.74 |
| 2 | 0.25 | 0.75 | 0.21 | 0.79 |

A point [u, v] of the photograph is drawn at x = 540 + (u - focus u) x 1080 x s and y = 905 + (v -
focus v) x 1080 x s, where s is the zoom times the push. Points far from the focus move outward as the
push grows, so a point pinned near the band's edge can leave it before the plate ends.

## Events

Every event has `type` and `frame`, inside its plate and at least 6 frames before its end.

**`callout`**: a capital label in a dark chip with a line to a part.

| Field | Rule |
|---|---|
| `text` | 1 to 18 characters, shown in capitals |
| `at` | [u, v] on the photograph, at least 45 px inside the band when it appears and at the plate's end (the band's top and bottom 90 px fade into the dark) |
| `chip` | [x, y], the chip's centre as fractions of the frame. The chip is (characters x 27 + 44) px wide and 60 px tall, inside the band and the side margins, at least 40 px from `at` |
| `tone` | `white` (default), `blue` or `gold` |

**`outline`**: a box or corner brackets over a region; it draws itself on in 8 frames.

| Field | Rule |
|---|---|
| `region` | [u0, v0, u1, v1], u0 < u1 and v0 < v1, both corners inside the band at the event and at the plate's end |
| `tone` | `blue` (default), `white` or `gold` |
| `shape` | `box` (default) or `bracket` |

**`arcs`**: a fan of gold field arcs rising from `from` and bending toward `to` over 20 frames, with
sparks; 65 frames after it starts, all of it holds still.

| Field | Rule |
|---|---|
| `from`, `to` | [u, v], both inside the band at the event and at the plate's end |
| `count` | 3 to 9, default 7 |

**`counters`**: a row of up to four monospace values in the bottom left, ticking from `from` to `to`
in 4-frame steps and settling in 16 frames. One row per plate; it stays until the next plate.

| Field | Rule |
|---|---|
| `values` | 1 to 4 `{"from": n, "to": n}`, whole numbers 0 to 99999. Values that change turn bold white and get a bracket under them. Each column is 520 px / the number of counters, a digit 39 px: four counters take up to 3 digits, three up to 4, one or two up to 5 |

**`stat`**: one huge numeral, counting up over 24 frames, right-aligned, with a capital label and an
optional chip under it. One per plate.

| Field | Rule |
|---|---|
| `value` | The number it ends on, -9999999 to 9999999 |
| `from` | Where it counts from, default 0, in the same range. The block is sized for the longer of the two |
| `decimals` | 0 (default), 1 or 2 |
| `prefix`, `suffix` | At most 3 characters each: `$`, `%`, `µm`, `pF` |
| `label` | 1 to 22 characters, shown in capitals |
| `chip` | Optional, 1 to 10 characters: `+429%` |
| `place` | `lower` (default, y 1050 to 1350) or `upper` (y 500 to 800). The numeral is 110 px a character and the label 28; the block must fit between x 60 and 1010 |

**`chart`**: a thin line drawing left to right on a plate with no photograph, the value at its head
shown large above it, the axis label typing on under it, and the chip popping at the end. One per
plate.

| Field | Rule |
|---|---|
| `points` | 2 to 24 numbers from -9999999 to 9999999, in order. The value shown above the chart is 96 px a character and must fit 900 px |
| `label` | The axis, 1 to 24 characters |
| `duration` | 30 to 150 frames, default 88; the chart starts at least `duration` + 20 frames (+ 4 with a chip) before its plate ends |
| `decimals`, `prefix`, `suffix`, `chip` | As for `stat` |

**`footnote`**: tiny grey text in the bottom left, until the next plate. One per plate, 1 to 32
characters.

**`pose`**: the presenter's pose, on a word, at least 8 frames after the last one.

| Field | Values |
|---|---|
| `pose` | `idle`, `point`, `present`, `think`, `surprise`, `hands_on_head`, `thumbs`, `shrug`, `explain` |

## Counted per plate

At most 6 callouts, outlines, arc fans, stats and charts together. Callouts, outlines and arcs need a
photograph. Chips, the stat and the chart may not overlap each other, and no pinned point (a
callout's `at`, an arc's `from` or `to`, an outline's corner) may sit under a chip or the stat, with
10 px to spare. A callout or a footnote starts at least 20 frames before its plate ends; a stat 44
(48 with a chip), a counter row 36, a chart its `duration` plus 20 (plus 4 with a chip), so the
number finishes and can be read. On a plate that a zoom-through ends, its pinned things leave 6
frames before the cut, so count from there.

On a plate that enters with a zoom, pinned points are also checked at the 1.25x it settles from, so a
point near the band's edge must wait until the settle is over (8 frames).

## The whole video

Something new (an event or a plate) at least every 3.5 seconds.
