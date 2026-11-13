# Editorial Collage: the data contract

Every field of `props.collage`, with its limits. `write_scene_config` checks all of it. The renderer's
side is `renderer/remotion/src/scenes/installed/editorialCollage/contract.ts`.

## The desk

The video is a paper desk larger than the frame. The code lays the stations out on it in a zig-zag:
station 1 on the left, station 2 on the right and 1140 px lower, station 3 on the left again and lower
still. The camera rests on a station and glides to the next for 36 frames (1.2 s) from the next
station's start, along the diagonal, while a red string draws from the last station's hero to the new
one. The camera only moves; it never zooms. You write no position, size or angle.

While the camera rests on a station, the station fills the frame in fixed zones:

| Zone | From (y) | To (y) | Holds |
|---|---|---|---|
| Top margin | 0 | 236 | The desk (and a corner of the station before) |
| Headline | 236 | 600 | The clipping, label bar or black card, with its kicker |
| Hero | 640 | 1280 | The print, sticker, index card, figure or stack, centred at y 960, between x 100 and 980 |
| Captions | about 1320 | about 1490 | The cream caption strip, centred at 1402 (73%) |
| Lower desk | 1500 | 1920 | Paper scraps on the desk |

A black card with no hero fills both the headline and the hero zones.

## The whole video

```json
{"totalFrames": 1023, "canvas": "light",
 "subtitles": {"emphasis": [11, 23, 36]},
 "scenes": [{"type": "generated", "source": "installed", "src": "EditorialCollage",
             "startFrame": 0, "durationInFrames": 1023,
             "props": {"collage": {"stations": [ ... ]}}}]}
```

| Field | Rule |
|---|---|
| `stations` | 1 to 20 stations, in frame order. The first starts at frame 0 |
| `subtitles.emphasis` | Optional. Word indexes (from 0) that get the yellow marker in the captions, at most one word in five. The style fills in the rest of `subtitles` |

## A station

| Field | Rule |
|---|---|
| `start` | The station's first frame. 0 for the first; on a word for the others. A station lasts at least 1.5 s, and its first 36 frames are the camera's glide |
| `headline` | Optional. `{"text", "kind", "kicker"}`, below |
| `hero` | One hero, below. Required unless the headline is a `black` card |
| `events` | Optional. What lands on the station, each on a word |

## The headline

| Field | Rule |
|---|---|
| `text` | 1 to 60 characters on one line. It must fit its kind at one of its sizes (the tool says when it does not) |
| `kind` | `clipping`, `label` or `black` |
| `kicker` | Optional. 1 to 28 characters, a small line above the headline: a date and a section ("TECH · FEB 28, 2017"), never a publication's name |

| `kind` | Looks like | Sizes (px) | Most lines |
|---|---|---|---|
| `clipping` | A torn, yellowed newspaper strip, a serif headline, a double rule under the kicker | 96, 84, 72, 62 | 3 |
| `label` | A black bar with white capitals | 72, 62, 52, 44 | 2 |
| `black` | A torn black card with white serif words | 96, 84, 72, 62 | 3 |
| `black` with no hero | The same card filling the station | 128, 112, 96, 84, 72 | 6 |

## The heroes

Every hero has a `kind`: `print`, `sticker`, `index`, `figure` or `stack`.

| `kind` | Fields | Rule |
|---|---|---|
| `print` | `image`, optional `caption` | `image` is `/public/<video_id>/images/treated/<name>.print.png` from `treat_image(..., "print")`; `caption` 1 to 40 characters, typed under it. The note "Illustration" is always painted on it. Fitted into 760 x 600 px |
| `sticker` | `image`, optional `label` | `image` is `/public/<video_id>/images/treated/<name>.sticker.png` from `treat_image(..., "sticker")`; `label` 1 to 24 characters, a black label bar at its lower left. Fitted into 700 x 600 px |
| `index` | `lines`, optional `recreation` | 1 to 4 lines, each `{"text", "at"}`: `text` 1 to 34 characters, `at` the word it starts typing on, in order, done before the station ends. `recreation: true` paints the note "Recreation" |
| `figure` | `value`, optional `prefix`, optional `suffix`, `label`, `countAt` | `value` from 0 to 999999999 with at most 2 decimals; `prefix` 1 to 3 characters; `suffix` 1 to 10 (a word of three letters or more gets a space before it); `label` 1 to 24 characters; `countAt` the word it counts up on |
| `stack` | `items` | 2 to 3 items, each `{"image", "caption"}`: a print or a sticker path as above, `caption` 1 to 24 characters |

A video uses at most 10 different stills across all its prints, stickers and stacks.

## An event

Every event has `at` (a word's frame inside the station, at least 8 frames before its end) and `do`.

| `do` | Fields | Rule |
|---|---|---|
| `circle` | (none) | A hero only. At most one per station |
| `underline` | `word` | One word of the headline, once per station |
| `highlight` | `word` | One word of a `clipping` headline, once per station |
| `strike` | `word` | One word of the headline. At most one per station |
| `stamp` | `text` | 1 to 12 capital letters, digits or spaces. A hero only. At most one per station |
| `arrow` | `from` | `left` or `right`: the side the arrow comes from. A hero only. At most one per station |

Drawing times, in frames at 30 fps, on twelve steps a second: a circle 30, an underline 15, a highlight
10, a strike 10, a stamp 6, an arrow 8, a figure's count 30. An index line types 13 characters a second.

Something new must happen (a station, an event, a line or a count starting) at least every 3.5 seconds,
outside insert windows. Inside an insert's window nothing starts and no glide runs.
