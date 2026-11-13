# Archive and Engraving: the data contract

Every field of `props.archive`, with its limits. `write_scene_config` checks all of it. The renderer's
side is `renderer/remotion/src/scenes/installed/archiveEngraving/contract.ts`.

## The page

A 1080 x 1920 page in fixed zones, so nothing you write can land on another zone:

| Zone | From (y) | To (y) | Holds |
|---|---|---|---|
| Top margin and header | 0 | 270 | The running header and the plate number over a double rule at y 244 |
| Title band | 270 | 690 | The date (at y 280), the title from y 336 (one or two lines), and a strike's replacement under it |
| Card band | 700 | 1268 | The one card of the beat, 900 px wide from x 90 |
| Captions | about 1290 | about 1520 | The chip captions, centred at 1402 (73%) |
| Ruler | 1560 | 1700 | The timeline ruler at y 1640, once a `timeline` event has fired |

A plate's or a chart's window is 840 x 430 px at x 120, y 726. It shows a wide band of the tall still
around `focus`, pushing in from 1 to 1.06 across the beat. The title is set at 104, 92, 80 or 70 px,
the largest at which it fits two lines of 952 px.

## The whole video

```json
{"totalFrames": 1218, "canvas": "light",
 "scenes": [{"type": "generated", "source": "installed", "src": "ArchiveEngraving",
             "startFrame": 0, "durationInFrames": 1218,
             "props": {"archive": {"header": "Histories of Computing", "beats": [ ... ]}}}]}
```

| Field | Rule |
|---|---|
| `header` | The running header, 1 to 34 characters, the same for the whole video |
| `beats` | 1 to 32 beats, in frame order. The first starts at frame 0 |

## A beat

| Field | Rule |
|---|---|
| `start` | The beat's first frame. 0 for the first beat; on a word for the others. A beat lasts at least 1.5 s |
| `title` | `{"text", "red"}`: `text` 1 to 48 characters that fit two lines; `red` one word of it, drawn in red |
| `date` | Optional. 1 to 24 characters, typed on at the beat's start ("9 September 1947") |
| `card` | One card, below |
| `events` | Optional. What happens on the page, each on a word |

## The cards

Every card has a `kind`: `plate`, `chart`, `person`, `people` or `document`.

| `kind` | Fields | Rule |
|---|---|---|
| `plate` | `image`, optional `focus`, `name`, optional `note` | `image` is `/public/<video_id>/images/treated/<name>.engraving.png` from `treat_image`; `focus` is `[u, v]` (default `[0.5, 0.5]`); `name` 1 to 28 characters; `note` 1 to 40. The footnote "Illustration" is always drawn |
| `chart` | the plate's fields and `route` | `route` is 2 to 8 `[u, v]` points on the still, all inside the window's view. One `route` event draws it. The footnote "Illustration" is always drawn |
| `person` | `name`, `dates`, `role`, and `emblem` or `initials` | `name` 1 to 28 characters, `dates` 1 to 20, `role` 1 to 32; `emblem` one of the ten below, or `initials` 1 to 3 capital letters. There is no picture field |
| `people` | `people` | 2 to 4 people, each a person's fields plus `at`, the word they arrive on (the first may be the beat's start, and arrives within 1.5 s of it). Each arrives after the one before; a red arrow joins them |
| `document` | `lines`, optional `hand` | 1 to 6 lines, each `{"text", "at"}`: `text` 1 to 40 characters, `at` the word it starts writing on, in order. `hand: true` writes by hand, `false` (the default) types. The footnote "Recreation" is always drawn |

The emblems: `laurel`, `quill`, `gear`, `compass`, `scroll`, `book`, `anchor`, `telescope`, `scales`,
`lamp`.

A point `[u, v]` is a fraction of the still from its top left (u left to right, v top to bottom), read
off `read_image`'s grid. A `magnify` point or a route point must stay at least 30 still pixels inside
the part the window shows at the start and at the end of the push.

## An event

Every event has `at` (a word's frame inside the beat, at least 8 frames before its end) and `do`.

| `do` | Fields | Rule |
|---|---|---|
| `strike` | `word`, `with` | `word` one word of the title; `with` 1 to 28 characters, drawn in italic red under the title. At most one per beat |
| `underline` | `word` | One word of the title, once per beat |
| `stamp` | `text` | 1 to 14 capital letters, digits or spaces. At most one per beat |
| `magnify` | `point` | `[u, v]` on a plate's or a chart's still. At most one per beat |
| `route` | (none) | A chart card only; draws its route over 20 frames |
| `timeline` | `from`, `to` | Years from 0 to 2100. The ruler appears at the first one and stays; its marker slides from `from` to `to` |

Drawing times, in frames at 30 fps: a strike 15, an underline 12, a stamp 6, a magnify 14, a route 20,
a timeline slide 20. A typed line writes 2 characters a frame, a handwritten one 1.5.

Something new must happen (a beat, an event, a person or a line arriving) at least every 3.5 seconds,
outside insert windows.
