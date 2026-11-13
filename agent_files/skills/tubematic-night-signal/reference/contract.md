# Night Signal: field reference

`props.nightSignal` of the one `NightSignal` scene. Frames are the video's own (the timeline's word
frames); every frame you give sits within 2 frames of a word's start.

```json
{"file": {"number": 31, "title": "QR STRANGER"},
 "clock": "03:12",
 "scenes": [ ... ],
 "customParts": [ ... ]}
```

| Field | Holds |
|---|---|
| `file` | `{"number": 1-999, "title": 1-16 characters}`: the case file row near the top |
| `clock` | Optional, `"HH:MM"` (24-hour): when the story happens; the timecode and the camera clock start there |
| `scenes` | 3 to 14 scenes, in order; the first starts at 0 and is a `tableau`, `camera` or `phone` |
| `customParts` | Optional, at most 6 parts of your own: `{"id", "shapes"}` |

## Every scene

| Field | Holds |
|---|---|
| `kind` | One of `tableau`, `camera`, `phone`, `rule`, `case`, `steps` |
| `start` | The frame it starts on (on a word); it lasts until the next scene starts, at least 1.5 s |
| `cut` | Optional, how it arrives: `glitch`, `hard` (a glitch tear is the default) |

## `tableau`

| Field | Holds |
|---|---|
| `setting` | One of `night`, `street`, `room`, `plain` |
| `items` | 1 to 4 items, each in its own slot |
| `connector` | Optional `{"from": slot, "to": slot, "at": frame}`: a dotted line drawing between two items |
| `bubble` | Optional `{"over": slot, "icon": part, "kind": kind, "at": frame}`, kind `thought` (the default) or `speech` |

An item: `{"what": part, "slot": slot, "at"?: frame, "threat"?: true, "redAt"?: frame, "face"?: "left" or "right", "to"?: {"slot", "at"}}`.
Slots, left to right: `left`, `midleft`, `center`, `midright`, `right`. At most one item per scene is the threat; it is red from its
first frame, or turns red on `redAt`.

## `camera`

`label` (1-22 characters), `items` and `connector` as in a tableau (drawn smaller, inside the panel),
and an optional `button`: `{"text": 1-6 characters, "crossAt"?: frame}`.

## `phone`

`screen`: one of `message`, `link`, `qr`, `call`, `alert`; `title` (1-12 characters); `lines` (1 to 3 lines of 1-16
characters: a message's lines, a link card's lines (the first is a small grey label), a code's caption,
a caller's lines, an alert's lines); an optional `mark`: `{"kind": one of `check`, `cross`, "at": frame}`.
A `check` is green and used once in a video.

## `rule`

`number` (1-99), `lines` (1 or 2 lines of 1-12 characters, under the number), `icon` (a part, drawn
inside the ring), an optional `slashAt` (at least 16 frames into the card; absent, 16 frames in).

## `case`

`label` (1-10 characters, `WITNESS`, `SUSPECT`), `name` (1-12 characters), `icon` (a part, the ID
photo), `bars` (2-4 redaction bars), an optional `stamp`: `{"text": 1-10 characters, "at": frame}`.

## `steps`

`title` (1-20 characters) and `steps`: 2 to 4 `{"text": 1-24 characters, "at": frame}`, in order.

## The library

- People: `person`, `person_walk`, `person_point`, `person_phone`, `person_hold`, `person_scared`, `person_hands_up`, `person_wave`, `person_sit`, `person_run`, `person_sleep`
- Animals: `dog`, `cat`, `bear`, `bird`
- Objects: `door`, `doorway`, `window`, `house`, `car`, `phone`, `laptop`, `qr`, `envelope`, `wallet`, `card`, `lock`, `key`, `lamp`, `tree`, `bed`, `table`, `atm`, `parcel`, `money`, `camera`, `router`, `moon`, `chat`, `warning`, `link`

## Custom parts

`{"id": "a_name", "shapes": [...]}`, 1 to 40 shapes. The box: x from -200 to 200, y from -400 to 0
(the ground); a circle's radius and a line's half width stay inside it (a line's end may sit on the ground). A shape:

| `shape` | Fields |
|---|---|
| `circle` | `cx`, `cy`, `r` (1-200) |
| `rect` | `x`, `y`, `w`, `h` (above 0), optional `r` (corner radius) |
| `line` | `points` (2-12 `[x, y]`), `width` (2-60); round ends and joins |
| `poly` | `points` (3-16 `[x, y]`), filled |

Every shape has a `tone`: one of `ink`, `grey`, `dim`, `core`, `red`, `hole`. `hole` is the black field: a wide `hole` line under
a limb, or a `hole` rect for a window, keeps parts readable without outlines. `red` belongs to the threat.
