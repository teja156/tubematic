# Mid-century How-To data contract

The shape of `props.midcenturyHowTo`, the one prop of the one `MidcenturyHowTo` scene.
`write_scene_config` checks every rule here and names what is wrong. The worked example is
`example-config.json`, timed to `example-timeline.json`.

## The whole video

| Field | Holds |
|---|---|
| `title` | The task, as the running title at the top: 1 to 30 characters (`Turn on 2FA`) |
| `kicker` | Optional short line over the title on the title card, at most 22 characters |
| `presenter` | Optional `{"outfit", "hair"}`: outfit `coral` (default), `teal`, `mustard`, `blue`; hair `dark` (default), `red`, `blond`, `grey` |
| `steps` | 2 to 6 of `{"start", "header", "tag", "ground"}`, in order. The first starts at least 1.5 s in: before it is the title card |
| `summary` | Optional frame of the summary card, after the last step's start, to the end |
| `shots` | `[{"start", "presenter", "events": [...]}]`, in order, the first at frame 0 |
| `customProps` | Optional. Objects you drew for this video: `[{"id", "src", "w", "h", "text", "acts"}]` |

A step's `header` is at most 18 characters, its `tag` at most 26, its `ground`
one of `mustard`, `blue`, `olive`, `rose`, `sea`. A step lasts at least 3 s, the summary at
least 2 s.

A shot's `presenter` says where the presenter stands: `left` (the default), `right`, or `none` for a
close-up without him. On the summary card he always stands on the right, and his poses are `stand`,
`thumbsup`, `wave` or `hips`.

## Events

Every event has `type` and `frame` (a whole frame number), and a shot lists its events in frame
order.

| `type` | Fields |
|---|---|
| `pose` | `pose`, `face`, optional `at` (an object on stage, for `point` and `present`) |
| `object` | `object` (an id below or yours), `x`, `y` (0 to 1, its centre), optional `id` (lowercase, unique in the shot; defaults to the object name), `scale` (0.5 to 1.5), `enter`, `text` |
| `act` | `target`, `act` (one of that object's acts); plays for 20 frames, then the object holds |
| `press` | `target`: the presenter's hand, or a rubber-hose arm from the edge when he is not in the shot or cannot reach, pulls back and presses it on the frame, with a ring burst. On a screen, it lands on the row a `rowN` act of the same frame lights |
| `check` | `target`: a teal check medallion on the object's top right |
| `cross` | `target`: a coral cross medallion there |
| `inset` | `target`, `text` (1 to 10 characters), `x`, `y`: a circle with the text, joined to the object by a dashed line |
| `label` | `text` (1 to 22 characters), `x`, `y`: a tag card with a turning star |

Poses: `stand`, `present`, `point`, `thumbsup`, `wave`, `think`, `shrug`, `hips`. Faces: `neutral`,
`smile`, `grin`, `worried`, `surprised`, `proud`. Entrances: `pop` (default), `drop`, `slide`, `rise`.

## The stage

The frame is 1080 x 1920. Fractions are of that frame.

| Area | From | To |
|---|---|---|
| Running title, step medallion, header and tag | y 0.10 | y 0.30 |
| Stage of a step | y 0.31 | the floor, y 0.72 |
| Stage of the title card (under the big title) | y 0.45 | the floor |
| Captions | about y 0.78 | |
| Progress dots | about y 0.87 | |
| Side margins | x 0.06 | x 0.94 |

The presenter stands with his feet at x 0.19 (or 0.81 on the right) on the floor and is about 0.28 of
the frame wide and 0.43 high; nothing may overlap his body. His arm reaches 430 px from his
shoulder (about x 0.24, y 0.41): a press farther away comes from the frame's edge. A label is about
22 px a character plus 90 px, 64 px high; an inset is a circle of radius
120 px.

## Objects

Boxes are in pixels at scale 1. A screen's text is up to four lines split on `|`, the first its
title.

| Object | Box | Text | Acts | What it is |
|---|---|---|---|---|
| `phone` | 320 x 560 | 80 | `row1`, `row2`, `row3`, `done` | a phone; text "Title|row|row|row" |
| `laptop` | 540 x 420 | 70 | `row1`, `row2`, `row3`, `done` | a laptop; text "Title|row|row|row" |
| `window` | 600 x 440 | 80 | `row1`, `row2`, `row3`, `done` | a browser or app window; text "Title|row|row|row" |
| `qr` | 270 x 270 | - | `scan`, `done` | a QR code |
| `keypad` | 380 x 470 | 8 | `type`, `done` | a number pad; text is the code it types |
| `password` | 560 x 160 | 18 | `type`, `done` | a password field; text is what it types |
| `toggle` | 280 x 150 | - | `flip` | an on/off switch |
| `button` | 360 x 160 | 14 | `light` | a big button; text is its word |
| `app` | 240 x 270 | 10 | `bounce` | an app icon; text is its name |
| `router` | 440 x 290 | - | `blink` | a wifi router |
| `lock` | 230 x 310 | - | `unlock` | a padlock |
| `key` | 320 x 170 | - | `turn` | a key |
| `shield` | 250 x 300 | - | `glow` | a shield |
| `usb` | 320 x 150 | - | `plug` | a USB stick and port |
| `battery` | 320 x 170 | - | `fill` | a battery |
| `envelope` | 360 x 250 | 20 | `open` | an envelope; text is the address line |
| `document` | 310 x 390 | 40 | `stamp` | a page; text is its words |
| `checklist` | 360 x 420 | 72 | `tick1`, `tick2`, `tick3`, `tick4` | a clipboard list; text "item|item|item|item" |
| `card` | 390 x 250 | 16 | - | a bank card; text is printed on it |
| `sign` | 380 x 270 | 24 | `wobble` | a hanging sign; text is its words |
| `calendar` | 300 x 330 | 6 | `flip` | a calendar; text shows on its page after flip |
| `clock` | 300 x 300 | - | `spin` | an alarm clock |
| `bulb` | 230 x 330 | - | `light` | a light bulb |
| `gear` | 290 x 290 | - | `turn` | a cog |
| `magnifier` | 300 x 310 | - | `scan` | a magnifying glass |
| `bell` | 270 x 290 | - | `ring` | a bell |
| `cloud` | 380 x 250 | - | `upload` | a cloud (online storage) |
| `trash` | 250 x 310 | - | `drop` | a wastebasket |
| `table` | 480 x 300 | - | - | a mid-century table things stand on |

## Objects of your own

| Field | Holds |
|---|---|
| `id` | What object events and the rest call it: lowercase letters, digits or `_`, not a library id |
| `src` | The `src` `write_scene_file` returned for this video's `prop-<name>` file |
| `w`, `h` | Its box at scale 1, whole pixels from 60 to 700: every pixel it can reach, act included |
| `text` | Optional, the most characters its text slot takes, 0 to 80 |
| `acts` | Optional, at most 4 lowercase names it draws itself |

The file default-exports one component that takes `{phase, act, actT, text}` and draws centred on
(0, 0). It imports only `react`, `remotion` and `../../installed/midcenturyHowTo/cel` (or
`contract`), with `import`. Each video's object is drawn once per look into a cached picture, so it
never uses a hook (`useCurrentFrame`, `useState`...): it draws from its props alone. It never uses an
SVG filter, a gradient (SVG or CSS), a pattern, a dashed stroke (`Cel` breaks the ink line for you), a backdrop filter or blend mode, an image, embedded
HTML or a fetch, a Remotion media or render-control part (`Img`, `Audio`, `Video`, `staticFile`,
`delayRender`...), `Math.random`, `Date`, a timer, a dynamic import, `performance`, `crypto`,
`window`, `document`, `globalThis`, `eval`, `require`, a `constructor` lookup, `React[...]` or a `Function` constructor. The check reads comments too.
`example-prop-alarm.tsx` is a finished one.
