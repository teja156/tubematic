# Storybook Atlas contract

The whole video is one scene: `{"type": "generated", "source": "installed", "src": "StorybookAtlas",
"startFrame": 0, "durationInFrames": <totalFrames>, "props": {"storybookAtlas": {...}}}`. This page
lists every field of `storybookAtlas` and everything you can name in it. `write_scene_config` checks
a config against exactly these lists and limits.

Frames come from `get_timeline(video_id, include_words=True)`. "On a word" means within 2 frames of a
word's `startFrame`. Positions are frame pixels: x from 0 (left) to 1080, y from 0 (top) to 1920.

## The frame

| Band | Holds |
|---|---|
| y 210 to 410 | the chapter plaque (numeral, title, byline, seal) |
| y 430 to 1344 | the stage: the backdrop's wall or sky, wall props, people and the guide |
| y 1344 | the floor line: floor props, people and the guide stand on it |
| y 1356 to 1410 | the name tags printed under people and floor props |
| y 1480 to 1640 | the caption label |
| x 60 to 1020 | the stage's sides |

## `storybookAtlas`

| Field | Holds |
|---|---|
| `guide` | `{"coat": ...}`: the guide's waistcoat, one of the coats below |
| `cast` | 0 to 4 people: `{"id", "name", ...knobs}` |
| `chapters` | 3 to 5 chapters, in order |
| `customProps` | optional, 0 to 8 props you drew: `{"id", "src", "box", "place", "states", "acts", "portal"?}` |

### A chapter

| Field | Holds |
|---|---|
| `start` | its first frame: 0 for the first chapter, on a word for the others; at least 8 s long |
| `title` | the plaque's title, 2 lines of at most 18 characters (it wraps at spaces) |
| `byline` | the plaque's italic line, at most 28 characters: a place or a date |
| `backdrop` | one of the backdrops below |
| `enter` | chapters after the first: `push` (through a portal prop of the chapter before) or `wipe` (the default) |
| `events` | what happens, each on a word, no later than 20 frames before the chapter ends |

### Events

| `type` | Fields | Notes |
|---|---|---|
| `guide` | `at`, optional `x` (110 to 970), `pose`, `facing` (`left`, `right`) | Walks to `x` at 9 px a frame, then takes `pose` |
| `person` | `at`, `who` (a cast id), optional `x` (110 to 970), `pose`, `facing`, `exit` | The first event walks them in from the nearer edge, to `x`, or to the middle (540) without one; `exit: true` walks them off |
| `prop` | `at`, `id`, `prop`, `x`, `y` (wall props, 620 to 1240), optional `scale` (0.6 to 1.4), `enter` | `x` is the middle of its base; `id` is your name for it in this chapter |
| `act` | `at`, `id`, `act` | One of the prop's acts, 10 frames or more after it appeared |
| `tag` | `at`, `on` (a prop's `id`), `text` (at most 24 characters) | Printed under the prop; a new tag on a prop replaces the one before |
| `constellation` | `at`, `until`, `words`, optional `then`, `thenAt` | 1 or 2 words of 1 to 10 letters or digits; `thenAt` at least 1.5 s after `at` and 1 s before `until` |
| `gauge` | `at`, `until`, `label` (at most 24 characters), `from`, `to`, `max`, optional `danger` | 0 to max; the red band runs from `danger` to `max` |
| `morph` | `at`, `until`, `prop` or `word` (1 to 10 characters) | The dots become the prop (library or yours) or the word |

A plate (`constellation`, `gauge`, `morph`) lasts 2.5 to 8 s, is closed (`until` plus 10 frames) 20
frames before its chapter ends, opens 14 frames or more after a chapter other than the first starts,
never overlaps another, and nothing else happens on stage while it is open.

`enter` for a prop: `pop` (the default), `drop`, `slide`, `rise`, `fade`.

### Poses

| Who | Poses |
|---|---|
| the guide | `stand`, `point`, `look` (looks up), `think`, `surprised`, `hop` (a hop, then it stands) |
| a person | `stand`, `point`, `hold` (both hands forward, as if holding something), `think` (hand to chin), `surprised` |

The walking drawings are the scene's; a pose is what someone does once they arrive.

### People's knobs

| Knob | Values |
|---|---|
| `build` | `tall`, `short` |
| `skin` | `light`, `tan`, `brown`, `deep` |
| `hair` | `short`, `long`, `bun`, `curly`, `bald` |
| `hairColor` | `dark`, `brown`, `auburn`, `grey`, `fair` |
| `face` | `none`, `moustache`, `beard` |
| `hat` | `none`, `tophat`, `bowler`, `cap`, `bonnet` |
| `garment` | `frockcoat`, `suit`, `dress`, `labcoat`, `overalls`, `waistcoat` |
| `color` | `ink`, `navy`, `brick`, `moss`, `plum`, `ochre`, `cream`, `sky` |

The guide's coats: `blue`, `sage`, `brick`, `plum`, `mustard`.

## Backdrops

| Backdrop | Shows |
|---|---|
| `study` | a Victorian study: a bookcase, striped wallpaper, a curtained window at night, a rug |
| `workshop` | a pegboard of tools, shelves of jars, a hanging lamp, a low workbench, a stone floor |
| `nightsky` | a starry navy sky, a crescent moon, dark rolling hills; dark |
| `laboratory` | a cabinet of flasks, a molecule chart, a bench with a retort, a tiled floor |
| `street` | an old street: two shops with awnings, gas lamps, rooftops, cobbles |
| `countryside` | fields, a hedge, an oak, a windmill on the hills, daytime |
| `harbour` | a quay, calm water, a moored sailing ship, a lighthouse on a headland |
| `blueprint` | a blueprint sheet with a pale grid and white line drawings at the edges; dark |
| `factory` | a mill hall: high windows, iron columns, belts to a lathe and a press |
| `maproom` | an explorer's map on the wall, a plan chest, a globe |

On a dark backdrop dress people in the light colours, `cream` or `sky`.

Each backdrop's own furniture and landmarks are part of the picture, so a prop placed over one hides
it or reads as a mistake (a letter hung across the harbour's ship). Keep wall props in the open areas
below, and stand floor props and people in front of low furniture, never inside a
tall piece. Boxes are frame pixels; "full height" means from the top of the stage to the floor line.

| Backdrop | Busy: keep wall props off these | Open wall |
|---|---|---|
| `study` | the bookcase x 0 to 270, full height; the curtained window x 770 to 1060, y 410 to 900 | x 300 to 740, y 430 to 1100 |
| `workshop` | the pegboard x 40 to 370, y 430 to 900; two jar shelves x 780 to 1050, y 530 to 620 and 760 to 840; the workbench x 30 to 330, y 1100 down | x 400 to 760, full height; x 780 to 1020 below y 860 |
| `nightsky` | the moon x 870 to 1000, y 520 to 650; the hills y 1160 down | the sky x 60 to 840, y 430 to 1100 |
| `laboratory` | the flask cabinet x 30 to 260, full height; the molecule chart x 800 to 1030, y 490 to 720; the bench and retort x 800 to 1060, y 1000 down | x 300 to 760, y 430 to 1000 |
| `street` | the left shop x 0 to 250 and the right shop x 820 to 1080, full height, with their gas lamps | x 280 to 800, y 430 to 950 |
| `countryside` | the oak x 0 to 280, y 540 down; the sun x 850 to 950, y 450 to 550; the windmill x 840 to 960, y 830 to 1000; the fence x 860 to 1080, y 1220 down | x 300 to 820, y 470 to 1000 |
| `harbour` | the ship x 740 to 1080, full height; the lighthouse x 80 to 160, y 830 to 1080 | the sky x 200 to 720, y 430 to 1050 |
| `blueprint` | the gear drawing x 20 to 260 and the wheel drawing x 840 to 1060, both y 450 to 660; the piston x 60 to 240 and the bolt x 850 to 1000, both y 950 to 1300 | x 300 to 800, full height |
| `factory` | the left window, column, belts and lathe x 0 to 290, and the right window, column, wheel and press x 740 to 1080, full height | x 300 to 720, full height |
| `maproom` | the wall map x 130 to 1020, y 410 to 810; the plan chest x 30 to 300 and the globe x 840 to 1060, both y 1000 down | x 300 to 820, y 830 to 1000 |

The open areas are where the eye goes: in a busy backdrop such as `street`, `harbour` or `factory`,
put the chapter's main prop and people in the middle third.

## Props

`box` is the prop's size at scale 1 (width x height, px). `states` is how many drawings it has:
`switch` shows the second for good, `cycle` runs through them for 1.6 s. A prop with a `portal` can be
pushed through into the next chapter.

| `prop` | What it is | `place` | `box` | `states` | `acts` | `portal` |
|---|---|---|---|---|---|---|
| `lamp` | oil lamp | floor | 140 x 232 | 2 | switch, glow, wobble |  |
| `door` | door | floor | 312 x 500 | 2 | switch | yes |
| `lightbulb` | light bulb | floor | 160 x 228 | 2 | switch, glow, pulse, wobble |  |
| `battery` | battery | floor | 140 x 214 | 1 | wobble, bounce, pulse, glow |  |
| `gears` | gears | wall | 290 x 290 | 1 | spin, wobble, pulse |  |
| `telegraph` | telegraph key | floor | 270 x 140 | 3 | cycle, wobble, bounce |  |
| `telephone` | candlestick telephone | floor | 200 x 302 | 3 | cycle, shake, wobble |  |
| `radio` | valve radio | floor | 240 x 290 | 2 | switch, glow, shake, wobble |  |
| `typewriter` | typewriter | floor | 290 x 238 | 3 | cycle, shake, wobble |  |
| `punchcard` | punched card | wall | 324 x 154 | 1 | wobble, bounce, pulse |  |
| `relaycabinet` | relay computer | floor | 420 x 540 | 3 | switch, cycle, shake, glow | yes |
| `terminal` | computer terminal | floor | 320 x 310 | 3 | switch, cycle, glow, wobble |  |
| `microscope` | microscope | floor | 190 x 274 | 1 | wobble, glow, pulse |  |
| `testtubes` | test tubes | floor | 240 x 214 | 3 | cycle, shake, glow, wobble |  |
| `magnifier` | magnifying glass | wall | 214 x 262 | 1 | wobble, pulse, bounce, glow |  |
| `telescope` | telescope | floor | 320 x 330 | 1 | wobble, pulse |  |
| `compass` | compass | wall | 180 x 208 | 3 | cycle, wobble, pulse, glow |  |
| `globe` | globe | floor | 250 x 340 | 5 | cycle, wobble, pulse |  |
| `rocket` | rocket | floor | 260 x 500 | 2 | switch, shake, wobble, glow |  |
| `starchart` | star chart | wall | 290 x 350 | 3 | cycle, glow, wobble, swing |  |
| `coin` | coin | wall | 160 x 160 | 1 | spin, bounce, glow, pulse |  |
| `anvil` | anvil | floor | 280 x 214 | 1 | shake, wobble, pulse |  |
| `book` | book | floor | 304 x 254 | 2 | switch, wobble, glow | yes |
| `letter` | letter | wall | 252 x 270 | 2 | switch, bounce, wobble |  |
| `candle` | candle | floor | 180 x 240 | 3 | glow, cycle, wobble |  |
| `clock` | wall clock | wall | 200 x 334 | 5 | cycle, wobble, pulse |  |
| `map` | map | wall | 340 x 222 | 2 | switch, pulse, glow, wobble |  |
| `scroll` | scroll | wall | 250 x 318 | 2 | switch, wobble, glow |  |
| `quill` | quill and inkwell | floor | 160 x 268 | 1 | wobble, bounce |  |
| `key` | iron key | wall | 250 x 96 | 1 | spin, glow, bounce, wobble |  |
| `lock` | padlock | wall | 140 x 272 | 2 | switch, shake, bounce |  |
| `chest` | chest | floor | 292 x 302 | 2 | switch, shake, glow, wobble |  |
| `porthole` | porthole | wall | 292 x 266 | 1 | pulse, glow, wobble | yes |
| `window` | window | wall | 350 x 356 | 2 | switch, glow | yes |
| `hourglass` | hourglass | floor | 152 x 238 | 4 | cycle, spin, wobble |  |
| `ship` | sailing ship | floor | 480 x 480 | 1 | wobble, bounce |  |
| `train` | steam locomotive | floor | 548 x 404 | 4 | cycle, shake |  |
| `lighthouse` | lighthouse | floor | 400 x 562 | 2 | switch, glow |  |
| `house` | cottage | floor | 400 x 412 | 2 | switch, glow, wobble |  |
| `tree` | tree | floor | 400 x 530 | 1 | wobble, shake |  |
| `printingpress` | printing press | floor | 440 x 540 | 3 | cycle, shake |  |
| `signpost` | signpost | floor | 340 x 446 | 1 | wobble, shake |  |
| `lantern` | hanging lantern | wall | 170 x 320 | 2 | swing, switch, glow |  |

Acts: `wobble` rocks it, `bounce` hops it, `shake` jitters it, `spin` turns it all the way round,
`swing` rocks it from its top, `pulse` grows it a little twice, `glow` puts a warm halo behind it for
good, `switch` and `cycle` change its drawing.

## Your own props

An entry in `customProps`:

| Field | Holds |
|---|---|
| `id` | your name for it, lowercase letters, digits and `_`, not a library prop's |
| `src` | the src `write_scene_file` returned for `prop-<name>` |
| `box` | `[width, height]` at scale 1, 60 to 700 px each, holding every state |
| `place` | `floor` or `wall` |
| `states` | 1 to 4 |
| `acts` | 1 to 4 of the acts above; `switch` and `cycle` need 2 states or more |
| `portal` | optional `[x, y]` inside the box, base at `[0, 0]`, y negative upward |

The file default-exports a component that takes `{ state }` and draws with its base at (0, 0). It may
import only `react` and `../../installed/storybookAtlas/ink` (or `palette`).
