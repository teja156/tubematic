# Process Cast data contract

The shape of `props.processCast`, the one prop of the one `ProcessCast` scene. `write_scene_config`
checks every rule here and names what is wrong. The worked example is `example-config.json`, timed to
`example-timeline.json`.

## The whole video

| Field | Holds |
|---|---|
| `cast` | 1 to 6 characters: `{"id", "name", "body", "tint", "units", "accessory"}` |
| `stations` | 1 to 6 stations along the ground line, in order: `{"id", "kind", "sign"}` |
| `events` | At most 120 events, in frame order |
| `customProps` | Optional. Props you drew for this video: `[{"id", "src", "w", "h", "text"}]` |

A character's `id` is lowercase letters, digits and `_`, starts with a letter and does not end in a
digit (clones are named `<id>2`, `<id>3`). `name` is its tag, at most 14 characters.
Bodies: `bean`, `blob`, `block`, `gem`, `units`; a `units` body has `units`, 1 to 16 cubes, drawn
52 px each in a near-square grid. Tints: `teal`, `olive`, `coral`, `sky`, `mustard`, `plum`, `cream`. Accessories:
`none`, `glasses`, `tuft`, `sprout`, `cap`.

A station's `id` is unique and not also a cast id; its `sign` is at most 14 characters.

## Events

Every event has `type` and `frame` (a whole frame on a word, or 0).

| `type` | Fields |
|---|---|
| `enter` | `who`, `station`, `slot`, optional `from`: `pop`, `drop`, `slide` |
| `move` | `who`, `station`, `slot`: a hop at the same station (10 frames), a trip to another (20 frames) |
| `exit` | `who` |
| `clone` | `who`, `count` (2 to 3, the number after the split) |
| `merge` | `who`: its clones come back (12 frames) |
| `react` | `who`, `face`, optional `mark` (shown 45 frames) |
| `look` | `who`, `at`: another character on stage, a station, or `front` |
| `carry` | `who`, `text` (at most 18 characters; `""` puts the card down) |
| `hand` | `from`, `to`: two characters at the same station (12 frames) |
| `prop` | `station`, `prop`, optional `text`; one prop at a station at a time, a new one replaces it |
| `join` | `who`, `with`: two `units` bodies at the same station; the cubes add up |
| `focus` | `who`: that character grows and the rest at its station shrink; `""` ends it |
| `camera` | `station`, optional `move`: `glide`, `cut` (a glide takes 20 frames) |

Faces: `neutral`, `happy`, `curious`, `proud`, `surprised`, `worried`, `sad`. Marks: `question`, `exclaim`, `sweat`, `check`, `cross`, `idea`.

## The stage

The frame is 1080 x 1920. The ground line is at y 1190 (0.62). Stations stand
1080 px apart along it, and the camera shows one at a time, starting at the first. A
station has 3 slots before its furniture (x -390, -160, 70 from its centre)
or 5 across a `stage` (x -420, -210, 0, 210, 420), where characters are drawn at
0.9 size. A character is 190 x 250 px (a `units` body is sized by its
count). Two bodies at one station, or a body and the furniture, may not overlap: a wide `units` body
needs the slot beside it free. Signs hang near y 330; captions sit at about y 0.72.

## Stations

| Kind | Furniture box | What it is |
|---|---|---|
| `desk` | 300 x 170 | a clerk's desk; a prop rests on its top |
| `board` | 300 x 330 | a cork board; a prop is pinned to it |
| `door` | 230 x 380 | a door in its frame; a prop is pinned to it |
| `shelf` | 280 x 300 | a storage shelf; a prop rests on top |
| `machine` | 290 x 280 | a machine that transforms; a prop rests on top |
| `server` | 220 x 360 | a server rack; a prop rests on top |
| `cell` | 340 x 300 | a cell membrane in cross-section; a prop is pinned inside it |
| `stage` | 0 x 0 | no furniture: five slots for a line-up; a prop is held up over the middle |

## Props

| Prop | Box | Text | What it is |
|---|---|---|---|
| `card` | 200 x 120 | 18 | an index card |
| `envelope` | 190 x 130 | 14 | an envelope |
| `packet` | 170 x 130 | 10 | a parcel or data packet |
| `box` | 170 x 150 | 10 | a box |
| `file` | 140 x 180 | 12 | a sheet of paper |
| `folder` | 190 x 150 | 12 | a folder |
| `key` | 170 x 90 | - | a key |
| `lock` | 120 x 160 | - | a padlock |
| `coin` | 120 x 120 | - | a coin |
| `cookie` | 130 x 130 | - | a browser cookie |
| `gear` | 140 x 140 | - | a cog |
| `bug` | 150 x 140 | - | a bug |
| `shield` | 130 x 160 | - | a shield |
| `stamp` | 130 x 160 | - | a rubber stamp |
| `clock` | 140 x 150 | - | a clock |
| `phone` | 110 x 190 | 12 | a phone |
| `laptop` | 230 x 160 | 14 | a laptop |
| `bulb` | 110 x 160 | - | a light bulb |
| `magnifier` | 160 x 160 | - | a magnifying glass |
| `molecule` | 170 x 150 | - | a molecule |
| `virus` | 150 x 150 | - | a virus |
| `battery` | 180 x 100 | - | a battery |

## Props of your own

| Field | Holds |
|---|---|
| `id` | What prop events call it: lowercase letters, digits or `_`, not a library prop's id |
| `src` | The `src` `write_scene_file` returned for this video's `prop-<name>` file |
| `w`, `h` | Its box at scale 1, whole pixels from 60 to 400 |
| `text` | Optional, the most characters its label takes, 0 to 18 |

The file default-exports one component that takes `{text}` and draws centred on (0, 0). It imports
only `react`, `remotion` and `../../installed/processCast/ink` (or `contract`), with `import`. Each
prop is drawn once into a cached picture, so it never uses a hook (`useCurrentFrame`, `useState`...):
it draws from `text` alone. It never uses an SVG filter, a gradient (SVG or CSS), a dashed stroke, a
backdrop filter or blend mode, an image, embedded HTML or a fetch, a Remotion media or render-control
part (`Img`, `Audio`, `Video`, `staticFile`, `delayRender`...), `Math.random`, `Date`, a timer, a
dynamic import, `performance`, `crypto`, `window`, `document`, `globalThis`, `eval` or a `Function`
constructor, and no SVG pattern of its own: hatching comes from `Hatches` and `Inked` in `ink`. The
check reads comments too.
`example-prop-ticket.tsx` is a finished one.
