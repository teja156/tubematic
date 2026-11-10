# Bean Explainer data contract

The shape of `props.beanExplainer`, the one prop of the one `BeanExplainer` scene. `write_scene_config`
checks every rule here and names what is wrong. The worked example is `example-config.json`, timed to
`example-timeline.json`.

## The whole video

| Field | Holds |
|---|---|
| `field` | The colour of the background, one per video: `yellow`, `mint`, `sky`, `peach`, `lilac`. Default `yellow`. Pick by mood: yellow and peach are upbeat, mint and sky calm, lilac playful |
| `title` | Optional series line at the top, at most 40 characters (`every phishing trick, explained`) |
| `list` | `true` when the sections are the items of a list: the badge carousel runs between them |
| `cast` | One or two beans: `{"id": "narrator", "accessory": ..., "tint": ...}`, then optionally `{"id": "other", ...}` |
| `sections` | `[{"start", "header", "color", "badge"}]`, in order |
| `shots` | `[{"start", "events": [...]}]`, in order, the first at frame 0 |

Accessories: `none`, `glasses`, `cap`, `tie`, `headset`, `hardhat`, `beanie`. Tints: `cream`, `peach`, `grey`, `mint`, `lilac`. Section colours: `red`, `blue`, `green`, `orange`, `teal`, `purple`. A
section's `badge` is any prop id below; it is drawn inside the badge circle.

## Events

Every event has `type` and `frame` (a whole frame number), and a shot lists its events in frame order.

| `type` | Fields |
|---|---|
| `pose` | `who` (a cast id), `pose`, `face`, optional `look`, `x` (0.1 to 0.9, where the bean stands; required on its first pose in a shot, a later `x` makes it hop there), optional `at` (a prop id or cast id the `point`, `present` or `lean` arm reaches toward) |
| `prop` | `prop` (an id below), `x`, `y` (0 to 1, its centre), optional `id` (lowercase, unique in the shot; defaults to the prop name), `scale` (0.5 to 1.4), `enter`, `text` |
| `act` | `target` (a prop on stage), `act` (one of that prop's acts); plays for 2 seconds, then the prop holds |
| `label` | `text`, `x`, `y` (its centre), optional `tone`: `ink` or `red` |
| `mark` | `who`, `mark` |
| `impact` | optional `strength`: 1, 2 or 3; impacts at least 15 frames apart |
| `strike` | `target`: a prop on stage gets a red X |
| `arrow` | `from`, `to`: a prop or a bean on stage at each end |

Poses: `stand`, `point`, `present`, `wave`, `cheer`, `shrug`, `think`, `facepalm`, `hands-hips`, `panic`, `lean`. Faces: `neutral`, `happy`, `worried`, `shocked`, `squint`, `smug`, `sad`, `angry`. Looks: `front`, `left`, `right`. Marks: `sweat`, `alarm`, `question`, `exclaim`, `sparkle`, `shock`, `anger`, `idea`.
Entrances: `pop`, `drop`, `slide`, `rise`.

## The stage

The frame is 1080 x 1920. Fractions are of that frame.

| Area | From | To |
|---|---|---|
| Title line | y 0.10 | y 0.14 |
| Header and badge | y 0.15 | y 0.22 |
| Stage (beans, props, labels) | y 0.24 | y 0.68 |
| Floor and captions | y 0.68 | the bottom |
| Side margins | x 0.06 | x 0.94 |

A bean stands on the floor line (y 0.68) and is about 0.27 of the frame wide and 0.39 high (0.22 and
0.33 when two beans share the stage). A label is about 24 px per character and 60 px per line.

## The prop library

### Carry text

| Prop | Size at scale 1 (px) | Text slot | Acts |
|---|---|---|---|
| `phone` | 240 x 420 | up to 40 characters | `buzz` |
| `browser` | 620 x 130 | up to 26 characters | `flash` |
| `laptop` | 440 x 320 | up to 30 characters | `flash` |
| `sign` | 380 x 330 | up to 24 characters | `wobble` |
| `document` | 300 x 390 | up to 20 characters | `stamp` |
| `note` | 270 x 270 | up to 30 characters | none |
| `speech` | 440 x 250 | up to 40 characters | none |
| `thought` | 440 x 270 | up to 40 characters | none |
| `pricetag` | 320 x 190 | up to 10 characters | `swing` |
| `calendar` | 300 x 320 | up to 6 characters | `flip` |
| `envelope` | 340 x 240 | up to 20 characters | `shake` |

### Money

| Prop | Size at scale 1 (px) | Text slot | Acts |
|---|---|---|---|
| `coins` | 280 x 220 | none | `shake` |
| `banknote` | 380 x 190 | up to 6 characters | `swing` |
| `wallet` | 320 x 240 | none | `shake` |
| `piggybank` | 360 x 280 | none | `shake` |
| `creditcard` | 380 x 240 | up to 16 characters | `swing` |
| `chartup` | 380 x 320 | up to 16 characters | `grow` |
| `chartdown` | 380 x 320 | up to 16 characters | `grow` |

### Health and the body

| Prop | Size at scale 1 (px) | Text slot | Acts |
|---|---|---|---|
| `brain` | 340 x 280 | none | `spark` |
| `heart` | 300 x 280 | none | `beat` |
| `stomach` | 280 x 320 | none | `shake` |
| `pill` | 260 x 140 | none | `spin` |
| `coffee` | 260 x 320 | none | `steam` |
| `water` | 200 x 320 | none | `fill` |
| `bed` | 480 x 280 | none | `zzz` |
| `dumbbell` | 400 x 160 | none | `shake` |
| `apple` | 240 x 260 | none | `spin` |

### Tech

| Prop | Size at scale 1 (px) | Text slot | Acts |
|---|---|---|---|
| `lock` | 240 x 320 | none | `unlock` |
| `key` | 340 x 160 | none | `spin` |
| `server` | 300 x 380 | none | `flash` |
| `wifi` | 320 x 260 | none | `pulse` |
| `bug` | 280 x 280 | none | `wobble` |
| `shield` | 280 x 330 | none | `flash` |
| `cursor` | 160 x 220 | none | `click` |

### Time and feeling

| Prop | Size at scale 1 (px) | Text slot | Acts |
|---|---|---|---|
| `clock` | 300 x 330 | none | `ring` |
| `hourglass` | 220 x 340 | none | `spin` |
| `gears` | 360 x 300 | none | `turn` |
| `bulb` | 220 x 330 | none | `light` |
| `cloud` | 400 x 300 | none | `rain` |
| `trophy` | 300 x 340 | none | `spark` |
| `bomb` | 300 x 320 | none | `shake` |
| `magnifier` | 340 x 340 | none | `wobble` |
