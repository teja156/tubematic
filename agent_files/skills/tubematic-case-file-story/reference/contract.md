# Case File Story: the data contract

Every field of `props.caseFile`, with its limits. `write_scene_config` checks all of it. The renderer's
side is `renderer/remotion/src/scenes/installed/caseFileStory/contract.ts`.

## The frame

A 1080 x 1920 frame in fixed zones, so nothing you place can land on another zone:

| Zone | From (y) | To (y) | Holds |
|---|---|---|---|
| Top margin | 0 | 232 | The painting only (the watermark is in its corner) |
| Meter row | 232 | 338 | Two or three meter cells, x 60 to 1020 |
| Panel | 366 | 616 | The large meter panel, when a shot has one |
| Picture | 338 | 1240 | The painting; on a card, its title, grid, bars, term and stamp |
| Captions | 1290 | 1470 | The captions, centred at 1382 (72%) |
| Buttons | 1500 | 1650 | The two choice buttons, on the last beat |

A count card or a bars card is a cream panel from the top to y 1240 with a near-black band under it. A
term card is near-black all over.

## The whole video

```json
{"totalFrames": 1441, "canvas": "dark",
 "scenes": [{"type": "generated", "source": "installed", "src": "CaseFileStory",
             "startFrame": 0, "durationInFrames": 1441,
             "props": {"caseFile": {"accent": "pink", "hud": [ ... ], "beats": [ ... ]}}}]}
```

| Field | Rule |
|---|---|
| `accent` | `pink`, `amber`, `teal` or `red` |
| `hud` | 2 or 3 meters |
| `beats` | 1 to 48 beats, in frame order. The first is a `shot` at frame 0; the last is the only `choice`; a `term` comes before it |

## A meter

| Field | Type | Rule |
|---|---|---|
| `id` | text | A short lower-case name of its own (letters, digits, `_`), like `cash`. Shots refer to it |
| `label` | text | 1 to 12 characters, in capitals |
| `kind` | `money`, `count` or `percent` | How the value is drawn |
| `value` | whole number | The value at frame 0. 0 to 999999999; a `percent` at most 100 |

How a number is drawn:

| Kind | 4200 | 40000 | 1250000 |
|---|---|---|---|
| `money` | $4,200 | $40,000 | $1.2M |
| `count` | 4,200 | 40,000 | 1.2M |
| `percent` | (0 to 100 only) 58% | | |

A million or more is shown in millions with one decimal, cut and never rounded up.

## A beat

Every beat has `type` and `start`. `start` is 0 for the first beat, then a frame within 2 of a word's
`startFrame`, increasing. A beat ends where the next starts. A field a beat's type does not list is
refused.

### `shot`

| Field | Type | Default | Rule |
|---|---|---|---|
| `image` | text | | The `public_path` from `generate_image` for this video. At most 16 different stills per video. Never the lead sheet |
| `focus` | [u, v] | [0.5, 0.45] | The point of the still the push-in closes on, 0 to 1 from its top left |
| `punch` | `{frame, at}` | none | A hard cut to a crop 1.5 times tighter around `at` [u, v]. `frame` is on a word, at least 12 frames after the shot starts and before it ends |
| `set` | object | none | Meter id to its new value, shown from this cut (the old value dissolves out over 2 frames) |
| `hud` | true or false | true | false hides the meter row for this shot |
| `panel` | meter id | none | Shows that meter large, counting from its old value to the one this shot's `set` gives it over 12 frames. Needs the meter in `set` and the meter row on |

The still covers the frame and pushes in 2.5% per second. A shot lasts at least 1 second, and no
more than 4 seconds may pass between its cut, its punch-in and its end.

### `count`

| Field | Type | Rule |
|---|---|---|
| `title` | text | 1 to 26 characters |
| `unit` | text | Optional, 1 to 26 characters: what one icon stands for, or the conversion |
| `icon` | text | `bill`, `coin`, `envelope`, `person`, `box`, `card`, `phone`, `document`, `key` or `goldbar` |
| `to` | whole number | What the counter climbs to, above 0 |
| `kind` | `money`, `count` or `percent` | How the counter is drawn |
| `result` | text | 1 to 14 characters: what it comes to |
| `resultFrame` | frame | Optional. On a word, after the counter stops |

The grid of 40 icons (or of `to` icons, when `to` is under 40) and the counter start 10 frames
after the card and run for 36. Without
`resultFrame` the result lands 12 frames after the counter stops.

### `bars`

| Field | Type | Rule |
|---|---|---|
| `title` | text | 1 to 26 characters |
| `kind` | `money`, `count` or `percent` | The kind of the bars' values |
| `threshold` | `{value, label}` | `value` a whole number above 0; `label` 1 to 24 characters, drawn above the dashed line |
| `bars` | list | 2 to 6 bars, each `{label, value, frame}`: `label` 1 to 6 characters, `value` a whole number, `frame` on the word that counts it. Frames in order, at least 8 apart, inside the beat |
| `payoff` | text | 1 to 30 characters: what the bars add up to |
| `payoffFrame` | frame | Optional. On a word, after the last bar. Without it, 11 frames after the last bar |

### `term`

| Field | Type | Rule |
|---|---|---|
| `term` | text | 1 to 26 characters, in capitals. A long one is drawn smaller to fit |
| `definition` | text | 1 to 110 characters, one sentence |
| `stamp` | text | 1 to 16 characters, in capitals |
| `citation` | text | Optional, 1 to 34 characters: the law or rule, as the script gives it |
| `definitionFrame` | frame | Optional. On a word. Without it, 20 frames after the card starts |
| `stampFrame` | frame | Optional. On a word, after the definition. Without it, 25 frames after the definition |

The citation appears 14 frames after the stamp lands.

### `choice`

| Field | Type | Rule |
|---|---|---|
| `image` | text | A still of this video, as for a shot |
| `focus` | [u, v] | As for a shot |
| `options` | two texts | Two different labels, 1 to 10 characters each, in capitals, in the order the narration says them |
| `optionFrames` | two frames | Optional. Each on a word, in order, inside the beat. Without them, 8 and 28 frames after the beat starts |

## Reading time

The last part of a card (the result, the payoff line, the stamp or the citation, the second button)
must appear at least 20 frames before its beat ends. No more than 4 seconds may pass between one part
of a beat and the next, or between the last part and the beat's end.

## The pictures

| Call | Makes |
|---|---|
| `generate_image(video_id, "lead", "<the outfit>", reference="house")` | The video's lead sheet (always 16:9). Once per video, first |
| `generate_image(video_id, "<name>", "<the scene>", reference="lead")` | A still with the lead painted in (always 9:16) |
| `generate_image(video_id, "<name>", "<the scene> No people.")` | A still without the lead (always 9:16) |

The server adds the lead's description and the painting style to every prompt of a Case File Story
video. A video may hold 16 stills, and the lead sheet besides; regenerating a name replaces it and
does not count again.
