# Paper Diorama: the data contract

Every field of `props.paperDiorama`, with its limits. `write_scene_config` checks all of it. The
renderer's side is `renderer/remotion/src/scenes/installed/paperDiorama/contract.ts`.

## The frame

A 1080 x 1920 frame in fixed zones, so nothing you place can land on another zone:

| Zone | From (y) | To (y) | Holds |
|---|---|---|---|
| Top margin | 0 | 270 | The room only (the watermark is in its corner) |
| Banner | 270 | 400 | The taped banner, centred, up to 860 px of text |
| Stage | 430 | the room's floor line | Props and the critter, in slots |
| Floor and captions | the floor line | 1920 | The torn-tag captions, centred at 1517 (79%) |

Each room's floor line is where a prop on the `floor` level stands:

| Room | Floor line (y) |
|---|---|
| `bank-vault`, `courtroom`, `warehouse`, `bedroom-day` | 1450 |
| `mission-control`, `airport-gate`, `subway-platform`, `diner` | 1440 |

## The whole video

```json
{"totalFrames": 956, "canvas": "light",
 "scenes": [{"type": "generated", "source": "installed", "src": "PaperDiorama",
             "startFrame": 0, "durationInFrames": 956,
             "props": {"paperDiorama": {"critter": {"color": "hero", "acc": "cap"},
                                         "customProps": { ... }, "sets": [ ... ]}}}]}
```

| Field | Rule |
|---|---|
| `critter` | Optional. `color`: `hero` (clay, the default), `cap`, `sage`, `amber`, `purple` or `pink`. `acc`: `none`, `cap`, `hardhat`, `headset`, `glasses`, `bowtie`, `beret` or `visor` |
| `customProps` | Optional. At most 8 props of your own, by name (lower-case letters, digits, hyphens, not a shipped prop's name) |
| `sets` | 1 to 24 sets, in frame order. The first starts at frame 0 |

## A set

| Field | Rule |
|---|---|
| `start` | The set's first frame. 0 for the first set; on a word for the others. A set lasts at least 1.2 s |
| `room` | One of the rooms above |
| `banner` | 1 to 28 characters on one line, drawn in capitals |
| `cut` | Optional. `cut` (default) or `tear`: how this set replaces the one before |
| `critter` | Optional. `{"slot", "face", "expr"}`: its slot, `face` 1 (facing right, default) or -1, its starting `expr`. Absent or `null`: no critter in this set |
| `items` | At most 6 props |
| `events` | What happens, each on a word. At most 160 in the whole video |

## An item

| Field | Rule |
|---|---|
| `id` | A name of its own in the set (lower-case letters, digits, hyphens), used by events |
| `prop` | A shipped prop (`style.extra.props`) or one of your `customProps` |
| `slot` | `l`, `cl`, `c`, `cr` or `r` (x 190, 365, 540, 715, 890: its centre) |
| `level` | Optional. `floor` (default), `shelf` (420 px up) or `air` (760 px up): where its bottom edge is |
| `scale` | Optional. `s` (0.7), `m` (1, default) or `l` (1.35) |
| `at` | The frame it enters: the set's start, or a word inside the set at least 8 frames before its end |
| `enter` | Optional. `pop` (default), `slide` or `drop` |

Two things on stage at the same time may overlap by at most 18% of the smaller one: the critter
counts, about 270 px wide and 230 px tall standing in its slot. Nothing may run off the left or right
edge, and no top edge may reach above y 430.

## An event

Every event has `at` (a word's frame inside the set, at least 8 frames before its end) and `do`.

| `do` | Fields | Rule |
|---|---|---|
| `exit` | `target` | An item that has entered |
| `move` | `target`, `to`, optional `level` | An item or `"critter"`; `to` a slot. The new place is checked like the old |
| `swap` | `target`, `prop` | An item; `prop` of the same size (its other state) |
| `expr` | `target: "critter"`, `value` | `idle`, `happy`, `shock`, `worried`, `squint` or `sleep` |
| `hop` | `target` | An item or `"critter"` |
| `stamp` | `text`, optional `target`, `level`, `color` | Text 1 to 12 characters. Over `target` when given, else mid-stage at `level` (default `shelf`) |
| `ring` | `target`, optional `color` | An item |
| `route` | `from`, `target`, optional `color` | Two different items of the set, both entered |
| `label` | `target`, `text` | An item; text 1 to 16 characters |
| `zoom` | `target` | An item. At most 3 in the whole video |

`color` is a palette colour name (`nogo` red is the default for a stamp and a ring, `tape` for a route).
An event may name an item only between its entrance and its `exit`.

## A prop of your own

`{"w", "h", "pieces"}`: `w` 20 to 520 and `h` 20 to 620 pixels at scale `m`, and 1 to 60 pieces.

| Piece field | Rule |
|---|---|
| `shape` | `rect`, `ellipse`, `poly` or `text` |
| `fill` | A palette colour name |
| `x`, `y`, `w`, `h`, `r` | `rect` and `ellipse`: the box's top-left corner and size; `r` rounds a rect's corners |
| `points` | `poly`: 3 to 40 `[x, y]` pairs |
| `text`, `font`, `size`, `x`, `y` | `text`: 1 to 14 characters, `font` `banner`, `label` (default) or `mono`, `size` 12 to 140, centred at `x, y` |
| `shade`, `shadeH` | Optional. A darker strip along the bottom, `shadeH` its share of the height |
| `hi`, `hiH` | Optional. A lighter strip along the top |
| `rot` | Optional. Degrees, -180 to 180, about the piece's centre |

Every piece stays inside `0..w` and `0..h`.

## The palette

`cream`, `creamHi`, `creamLo`, `paper`, `tape`, `ink`, `inkSoft`, `white`, `wood`, `woodLo`, `woodHi`,
`brass`, `brassLo`, `metal`, `metalLo`, `board`, `boardLo`, `boardHi`, `sage`, `sageLo`, `screen`,
`screenHi`, `screenText`, `hero`, `heroLo`, `cap`, `capLo`, `tag`, `purple`, `go`, `goDim`, `nogo`,
`nogoDim`, `amber`, `amberDim`, `yellow`, `pink`, `sky`, `skyLo`.
