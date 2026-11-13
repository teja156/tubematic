# Flat Vector Science: field reference

`props.flatVector` of the one `FlatVectorScience` scene. Frames are the video's own (the timeline's word
frames); every frame you give sits within 2 frames of a word's start.

```json
{"shots": [ ... ], "customProps": [ ... ]}
```

| Field | Holds |
|---|---|
| `shots` | 3 to 12 shots, in order; the first starts at 0 on a `cut` |
| `customProps` | Optional, at most 8 props you drew: `{"id", "src": "<video_id>/prop-<name>", "box": [w, h], "light"?: "#rrggbb"}`, box sides 60 to 1000 |

## Every shot

| Field | Holds |
|---|---|
| `kind` | One of `subject`, `ladder`, `zoom`, `descent`, `stages` |
| `start` | The frame it starts on (on a word); it lasts until the next shot, at least 1.5 s |
| `backdrop` | One of `abyss`, `ocean`, `night`, `sky`, `strata`, `inside` (a `descent` scrolls through the ocean whatever it names) |
| `cut` | Optional, how it arrives: `cut`, `lens`, `flash`, `push` (`cut` is the default; `lens` and `push` run over the 18 and 12 frames before the start, `flash` over the 6 after) |
| `counter` | Optional `{"label": 1-14 characters, "value": 0-999999999, "unit": up to 4 characters, "at": frame, "from"?: number, "red"?: true}` |

## `subject`

`items`: 1 to 3 `{"what": prop, "slot": slot, "size": size, "at"?: frame, "flip"?: true}`, each in its own
slot; slots `center`, `left`, `right`, `top`, `bottom`, sizes `s`, `m`, `l`. `pills`: up to 2 `{"on": slot, "parts": [{"text": 1-18
characters, "at": frame, "red"?: true}, ...]}` (1 or 2 parts). `rule`: optional `{"beside": slot, "label":
1-12 characters, "at": frame}`.

## `ladder`

`rungs`: 2 to 5 `{"what", "label": 1-14 characters, "value": 1-12 characters, "at", "red"?}`, smallest first.

## `zoom`

`levels`: 2 to 6 `{"what", "label": 1-12 characters (the scale bar's, like "10 KM"), "at", "red"?}`,
closest first.

## `descent`

`label` (1-14 characters, "DEPTH"), `unit` (up to 4 characters), `layers`: 2 to 6 `{"name": 1-14
characters, "value": deeper than the last, "at", "what"?, "red"?}`.

## `stages`

`steps`: 2 to 5 `{"what", "label": 1-14 characters, "at", "red"?}`, in order.

## The library

- sea: `whale`, `shark`, `squid`, `jellyfish`, `anglerfish`, `fish`, `fish_school`, `diver`, `submarine`, `shipwreck`, `coral`
- body: `cell`, `red_blood_cell`, `neuron`, `virus`, `bacterium`, `dna`, `heart`, `lungs`, `brain`, `eye`, `mitochondrion`
- space: `sun`, `star`, `earth`, `moon`, `mars`, `jupiter`, `saturn`, `black_hole`, `galaxy`, `comet`, `rocket`, `astronaut`, `satellite`
- earth: `mountain`, `volcano`, `cloud`, `raindrop`, `lightning`, `iceberg`, `tree`, `rock`
- scale: `bus`, `person`, `skyscraper`, `plane`, `car`

Halos: `jellyfish`, `anglerfish`, `diver`, `submarine`, `neuron`, `sun`, `star`, `black_hole`, `galaxy`, `comet`, `rocket`, `volcano`, `lightning`.
