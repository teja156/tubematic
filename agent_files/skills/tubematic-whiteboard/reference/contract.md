# Whiteboard: the `props.whiteboard` contract

The one scene of a Whiteboard video:

```json
{"type": "generated", "source": "installed", "src": "Whiteboard",
 "startFrame": 0, "durationInFrames": <totalFrames>,
 "props": {"whiteboard": {"regions": [ <region>, ... ], "recapFrame": <frame>}}}
```

## `whiteboard`

| Field | Type | Rule |
|---|---|---|
| `regions` | list | 2 to 6 regions, in the order the camera visits them |
| `doodles` | object, optional | the video's own doodles, `{name: strokes}`; see **Doodles** below |
| `recapFrame` | integer | within 2 frames of a word's `startFrame`, after the last region starts; from here to the end the camera pulls back to the whole board over 30 frames, then a circled number pops onto each region every 6 frames. The recap lasts at most 8 seconds, and at least 2 seconds or 30 + 6 x (regions - 1) + 15 frames, whichever is longer |

## Region

| Field | Type | Rule |
|---|---|---|
| `startFrame` | integer | 0 for the first region; later regions within 2 frames of a word, in increasing order, each at least 42 frames plus 2 seconds before the next region or the recap |
| `layout` | string | `stack`, `pair`, `compare` or `focus` |
| `items` | list | 1 to 12 items, in drawing order |

The camera glides to a region over its first 42 frames. In every region after the first, the first
item's `at` is at least 30 frames after the region's `startFrame`.

## Slots

| Layout | Slots (board pixels, inside a 1080 x 1040 region) |
|---|---|
| `stack` | `1` `2` `3` `4`: rows of 960 x 230, top to bottom |
| `pair` | `top` and `bottom` 960 x 200; `left` and `right` 450 x 480 between them |
| `compare` | `left_title`, `right_title` 450 x 150; `left_1`..`left_3`, `right_1`..`right_3` 450 x 230 |
| `focus` | `top` and `bottom` 960 x 220; `center` 960 x 440 |

Each slot holds at most one item. A slot's content is centred in it.

## Items

Every item has `id` (1 to 24 lowercase letters, digits or underscores, unique in its region), `kind`
and `at` (within 2 frames of a word's `startFrame`, later than the previous item's `at`). `ink`, where
allowed, is `black` (default), `blue` or `orange`.

| Kind | Fields | Rule |
|---|---|---|
| `text` | `slot`, `text`, `big`, `ink` | 68 px handwriting, wrapped by words into the slot's lines (2, or 1 in a `compare` title); `big: true` is 92 px on one line |
| `formula` | `slot`, `text`, `ink` | 80 px on one line, no wrapping |
| `doodle` | `slot`, `doodle`, `label`, `ink` | `doodle` is a library name; the optional `label` (58 px, at most 2 lines) sits beside the doodle in a wide slot and below it in `pair` left/right; a labelled doodle must keep at least 120 px |
| `arrow` | `from`, `to`, `ink` | ids of two earlier `text`, `formula` or `doodle` items of the region; the straight line between them may not pass through any other placed item |
| `highlight` | `target` | an earlier `text` or `formula`; always yellow (no `ink`); at most one per region |
| `underline` | `target`, `ink` | an earlier `text` or `formula` |
| `circle`, `box`, `cross` | `target`, `ink` | any earlier `text`, `formula` or `doodle` |

Text uses only characters the bundled Kalam font has: printable ASCII and Latin-1 (so `× ÷ ² ³ ° ±
½ µ € £` are fine, `→ √ π ≈` are not).

## Doodles

A doodle is a list of strokes in a 100 x 100 box, y pointing down, drawn in order. A stroke is a list
of segments joined into one continuous line; a segment is an object with one primitive: `line`
(`[[x, y], ...]`), `poly` (at least 3 points, closed), `curve` (start, control, end), `arc` (`[cx, cy,
rx, ry, from, to]`), `circle` (`[cx, cy, r]` plus an optional start angle), `ellipse` (`[cx, cy, rx,
ry]` plus an optional rotation and start angle), `rect` (`[x, y, w, h]` plus an optional corner
radius up to half the shorter side), `star` (`[cx, cy, inner, outer, points]`, 3 to 12 points) and
`gear` (`[cx, cy, inner, outer, teeth]`, 3 to 24 teeth). Angles are degrees, 0 to the right and 90
down. `reference/doodles.json` is the shipped library in this format.

A video's own doodles (`whiteboard.doodles`): at most 8; names of 1 to 24 lowercase letters, digits
or underscores that are not shipped names; each at most 20 strokes and 400 points once expanded,
every stroke at least two points, every point inside the box; each one drawn by an item.
`preview_doodles` applies the same checks and returns a picture.

## Timing

The marker starts each item 12 frames after its `at` and draws for the item's natural time: about 1.9
frames per character of body text, 4 per character of a big title, 2.5 per character of a formula, 30
frames for a doodle (plus its label), 14 for an arrow, 12 for a mark. When the next item comes sooner,
the item is drawn faster, down to a floor: 0.9 frames per character of text (at least 8), 1 per
character of a formula (at least 8), 18 for a doodle plus its label's floor, 8 for an arrow or a mark.
The next item's `at` must leave the floor plus 2 frames; the last item of a region must finish its
floor 15 frames before the next region or the recap starts. Something (a region, an item or the
recap) starts at least every 3.5 seconds.
