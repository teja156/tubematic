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
| `customProps` | Optional. Props you drew for this video: `[{"id", "src", "w", "h", "text", "acts"}]`. See [Props of your own](#props-of-your-own) |

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

## Props of your own

| Field | Holds |
|---|---|
| `id` | What prop events, acts and badges call it: lowercase letters, digits or `_`, not a library prop's id |
| `src` | The `src` `write_scene_file` returned for this video's `prop-<name>` file |
| `w`, `h` | Its box at scale 1, in pixels, outline and act included: 60 to 700 |
| `text` | Optional. The most characters its text slot takes, 0 to 40 (0, no slot, is the default) |
| `acts` | Optional. Up to 4 lowercase act names. `shake`, `swing`, `wobble`, `spin`, `beat` and `buzz` move the whole prop; any other is drawn by the prop from `actT` |

At most 8 per video. The file default-exports one component taking `PropDrawProps` from
`../../installed/beanExplainer/props/common`, imports nothing else but `react`, `remotion` and that
folder's `bean` and `contract` with a static `import`, and uses no filter, gradient (SVG or CSS),
backdrop filter, blend mode, pattern, dashed stroke, image, embedded HTML, audio or video, `staticFile`,
`delayRender`, fetch, `import(...)`, randomness, clock, `performance.now`, `crypto`, timers
(`setTimeout`, `requestAnimationFrame`), the page (`window`, `document`, `globalThis`), `eval` or a
`Function` constructor. The check reads the whole file, so do not name any of these in a comment either.
`example-prop-rocket.tsx` is a worked example; `render_bean_props`
shows yours.

## The prop library

### Carry text

| Prop | Size at scale 1 (px), its outline included | Text slot | Acts |
|---|---|---|---|
| `phone` | 260 x 440 | up to 40 characters | `buzz` |
| `browser` | 640 x 150 | up to 26 characters | `flash` |
| `laptop` | 460 x 340 | up to 30 characters | `flash` |
| `sign` | 400 x 350 | up to 24 characters | `wobble` |
| `document` | 330 x 410 | up to 20 characters | `stamp` |
| `note` | 300 x 310 | up to 30 characters | none |
| `speech` | 460 x 270 | up to 40 characters | none |
| `thought` | 450 x 300 | up to 40 characters | none |
| `pricetag` | 340 x 210 | up to 10 characters | `swing` |
| `calendar` | 320 x 340 | up to 6 characters | `flip` |
| `envelope` | 360 x 260 | up to 20 characters | `shake` |

### Money

| Prop | Size at scale 1 (px), its outline included | Text slot | Acts |
|---|---|---|---|
| `coins` | 280 x 250 | none | `shake` |
| `banknote` | 400 x 210 | up to 6 characters | `swing` |
| `wallet` | 340 x 270 | none | `shake` |
| `piggybank` | 390 x 310 | none | `shake` |
| `creditcard` | 400 x 260 | up to 16 characters | `swing` |
| `chartup` | 400 x 340 | up to 16 characters | `grow` |
| `chartdown` | 400 x 340 | up to 16 characters | `grow` |

### Health and the body

| Prop | Size at scale 1 (px), its outline included | Text slot | Acts |
|---|---|---|---|
| `brain` | 400 x 330 | none | `spark` |
| `heart` | 300 x 260 | none | `beat` |
| `stomach` | 260 x 340 | none | `shake` |
| `pill` | 270 x 180 | none | `spin` |
| `coffee` | 310 x 390 | none | `steam` |
| `water` | 210 x 340 | none | `fill` |
| `bed` | 500 x 370 | none | `zzz` |
| `dumbbell` | 410 x 150 | none | `shake` |
| `apple` | 260 x 250 | none | `spin` |

### Tech

| Prop | Size at scale 1 (px), its outline included | Text slot | Acts |
|---|---|---|---|
| `lock` | 260 x 430 | none | `unlock` |
| `key` | 330 x 220 | none | `spin` |
| `server` | 320 x 400 | none | `flash` |
| `wifi` | 350 x 260 | none | `pulse` |
| `bug` | 290 x 300 | none | `wobble` |
| `shield` | 280 x 340 | none | `flash` |
| `cursor` | 270 x 350 | none | `click` |

### Time and feeling

| Prop | Size at scale 1 (px), its outline included | Text slot | Acts |
|---|---|---|---|
| `clock` | 360 x 340 | none | `ring` |
| `hourglass` | 240 x 360 | none | `spin` |
| `gears` | 360 x 280 | none | `turn` |
| `bulb` | 340 x 390 | none | `light` |
| `cloud` | 410 x 330 | none | `rain` |
| `trophy` | 360 x 370 | none | `spark` |
| `bomb` | 330 x 340 | none | `shake` |
| `magnifier` | 260 x 350 | none | `wobble` |
