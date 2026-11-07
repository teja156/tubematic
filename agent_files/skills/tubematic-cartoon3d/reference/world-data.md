# Cartoon 3D: the data contract

Everything the renderer needs is three JSON objects inside one scene of the scene-config:

```json
{
  "totalFrames": 984, "fps": 30, "canvas": "dark",
  "subtitles": {"background": "outline", "fontFamily": "Montserrat", "fontSize": 70, "maxWords": 4},
  "scenes": [{
    "type": "generated", "source": "installed", "src": "Cartoon3D",
    "startFrame": 0, "durationInFrames": 984,
    "props": {"world": {...}, "beats": [...], "opts": {"post": "v2", "motion": {...}}},
    "transitionToNext": {"durationInFrames": 0}
  }],
  "sfx": []
}
```

`totalFrames` and `durationInFrames` are the timeline's `total_frames`. Units are **metres** and
**frames**; angles are **degrees**; colours are `{hue, sat, light}` (HSL, hue 0-360, the others 0-1) in
the world and `#rrggbb` on the cast and in fog colours.

## The world

| key | what |
|---|---|
| `name` | a title for the checks' output |
| `plan` | the ground plan that owns every position. A **street**: `{"kind": "street", "northZ", "southZ", "pitch", "x0"}` — two rows of slots facing each other across a road, slot `n` at `x0 + n * pitch`, the north row at `northZ` facing +z and the south row at `southZ` facing −z. A **clearing**: `{"kind": "clearing", "radius", "slots"}` — slots on a ring, each facing the centre |
| `ground` | `{"tex": "dirt" \| "cobbles" \| "stone", "hsl": {...}, "seed"}` |
| `pieces` | what stands in the world (below) |
| `marks` | named places the cast stands at and walks between: `{"name", "at": {row?, slot}, "out", "along"?}` — `out` metres in front of the slot's facing, `along` metres to its right |
| `shots` | named camera set-ups (below) |
| `water` | sheets of water: `{"pos": [x, z]}` or `{"at": {...}, "out", "along"?}`, `"w"`, `"d"`, `"y"`? (surface height, default 0.06), `"yaw"`?, `"flow"`? (`[vx, vz]` m/s, crests drift with it), `"marks"`? (crest density, 1 = reference). Coloured by distance and by the light; not solid, not walkable |
| `terrain` | rolling land beyond a flat zone: `{"seed", "flat": {"kind": "rect", x0, x1, z0, z1} \| {"kind": "circle", x, z, r}, "edge" (falloff metres), "amp" (hill height), "scale" (hill wavelength)}`. Absent = flat everywhere |
| `detail` | flat decals inside the flat zone: `{"ruts": [{x0, z0, x1, z1, width}], "puddles": [{x, z, r}], "worn": [{x, z, r}]}` |
| `atmos` | `{"dust": {"count", "area": {x0, x1, z0, z1}, "y": [lo, hi]}, "fireflies": {...}}`. Smoke comes from chimneys, fires and stacks by itself |
| `fog` | the world's aerial fog `{"near", "far"}` in metres (a beat may override it) |
| `tod` | the clock over the video `[from, to]`: 0 day, 0.5 golden hour, 0.8 dusk, 1 night. Beats override it; prefer `[0, 0]` and per-beat `tod` |
| `look` | `{"warmth": -1..1, "saturation": ~1.2, "rim": 0..1}` grade knobs. Leave the sky alone |
| `parts` | parts this world invents, by name, in the part grammar (below) |
| `cast` | the people of this video, by name (below) |

### Pieces

Every piece is placed at a slot (`at: {row?, slot}`) unless said otherwise. A slot number may be negative
or beyond the plan's count; `out` is metres in front of the slot's facing, `along` metres to its right.

| kind | fields |
|---|---|
| `building` | `w, h, d` (metres), `wall: {hue, sat, light, clapboard?, painted?: {hue, sat, light, wear}}`, `roof: {hsl}`, `windows` (per floor), `lit`? (window indices lit at night), `sign`? `{text, bg, fg}` (a board over the door; keep text to one or two short words), `seed`, `style`? — `{"wall": planks \| clapboard \| logs \| stone \| brick \| adobe, "roof": gable \| hip \| shed \| flat \| falseFront, "roofMat": shingles \| tin \| planks, "foundation": stone \| posts \| none, "porch": {depth?, rail?, roof?}, "awning": {depth?, kind: canvas \| wood, stripe?}, "door": false \| {at: -1..1, open?, lit?, color?}, "chimney": true \| {side: -1 \| 1, kind: stone \| brick, outside?}, "steps"?, "shutters": true \| hsl, "trim": hsl, "storeys": 1 \| 2, "balcony"?}`; `falseFront`? height for a false-front roof |
| `platform` | a raised deck: `w, d, h, out, wood: {hsl}` — walkable |
| `path` | the road's own surface: `{"width", "hsl"}` (no slot) |
| `poleRun` | telegraph poles: `count, spacing, height, out, axis: "x" \| "z"` |
| `scatter` | many of one thing: `what` (`tree`, `rock`, `tuft`, or any catalog kind), `count`, `ring: {r0, r1}` or `band: {x0, x1, z0, z1}` (no slot), `scale: [min, max]`, `seed`, `leaf`? hsl |
| `prop` | one catalog part: `what, at, out, along?, turn?` (degrees), `name`? (lets beats move, show, hide and act it), `hidden`? (out of the world until a beat shows it) |
| `cluster` | set dressing packed near a mark: `near` (mark name), `side`: `behind` \| `left` \| `right` \| `around` \| `upstage` (behind the subject as seen from `shot`: the side a 9:16 frame reliably shows), `shot`?, `r0, r1` (distance band), `count`, `what: [kinds]`, `seed` |
| `fence` | `at, out, along?, length, turn?` |

### Shots

`{"name", "subject": <mark>, "dist", "height", "swing", "fov", "aim", "push"?, "rise"?, "fg"?, "follow"?, "creep"?, "dof"?}`

- The camera sits `dist` metres from the subject mark at `height` metres, swung `swing` degrees around it
  (0 = looking along the slot's facing), with a vertical field of view of `fov` degrees (34-46), aimed
  `aim` metres above the mark. `push` and `rise` are the metres the camera travels over the beat.
- `fg: {"what": kind, "side": -1 | 1, "dist"?, "turn"?}` puts a foreground prop just inside one frame edge,
  softened by the depth of field: the near/mid/far layering about a third of shots should have.
- `follow: "<prop name>"` makes the camera travel with a named prop (a boat under way stays framed).
- `creep` multiplies the slow push every held shot has (default 1; a `follow` shot 0).
- `dof` is the blur-disc radius in pixels: close-ups and inserts 12-14, medium shots 10-12, wides and
  aerials 0; absent = from the focus distance.

### Parts in the grammar (`world.parts`)

```json
"parts": {
  "bollard": {
    "name": "bollard", "blurb": "iron mooring post on a square base",
    "prims": [
      {"kind": "box", "size": [0.6, 0.1, 0.6], "at": [0, 0.05, 0], "mat": "iron"},
      {"kind": "cylinder", "r": 0.12, "h": 0.9, "at": [0, 0.55, 0], "mat": "iron"}
    ],
    "solid": true, "walkable": false
  }
}
```

A part stands on y = 0 and faces +z; long things lie along x. Primitives: `box {size}`, `cylinder {r,
rTop?, h}` (rTop 0 = cone), `rod {from, to, r, rTop?}`, `sphere {r}` (a number or `[rx, ry, rz]`), `torus
{r, tube}` (ring in the xy plane), `lathe {points: [[radius, y], ...]}`, `shape {points: [[x, y], ...],
depth?}`, `plane {size: [w, h]}`, `group {items}`. Every primitive may carry `at`, `rot` (degrees), `mat`
(a kit material name from the catalog's list, a list of them, or `{"hsl": [h, s, l]}`), `noInk`, `repeat
{n, step, turn}` and `jitter {at, rot}`. Optional on the part: `smoke: [{at, kind: chimney | fire |
stack}]`, `lamp: [{at, colour?}]`, `solid` (default true), `walkable`, `lightAtNight`. Limits: 160
primitives after repeats, 4 levels of groups, 14 m tall, 18 m wide or deep, nothing floating (every
primitive touches, through others, one that touches the ground). Names are lowerCamelCase and must not be
a catalog kind. Props name a part like a kit kind: `{"kind": "prop", "what": "bollard", ...}`.

### The cast (`world.cast`)

```json
"cast": {
  "captain": {
    "blurb": "a stout riverboat captain of 1870: navy frock coat with brass buttons, a top hat, a dark moustache, a cane",
    "jacket": "#2c3566", "pants": "#3a3550", "boots": "#2b1d18", "hat": "tophat", "cap": "#3a3150",
    "buttons": "#f0c850", "moustache": "#140c0a", "coat": "tails", "holds": "cane", "build": "stout", "skin": 1, "seed": 7
  }
}
```

`jacket`, `pants`, `boots` (hex, required); `hat`: `cap | hair | bonnet | tophat | shako | shako_tall | null`;
`cap`, `hair` colours; `dress` (instead of trousers; the jacket becomes the bodice); `belt`, `buttons`,
`sash`, `moustache`; `skin` 0-3 or a hex; `build`: `adult | stout | kid`; `height` metres; `holds`: `paper |
bundle | satchel | cane | flag | lantern` with `heldColor`; `coat`: `tails | long`; `seed`. Very dark fills
are lifted to the look's floor by the renderer. The blurb is what the judge is told: say what the viewer
will see, including what is held. The catalog lists promoted cast you may copy by name.

## The beats

```json
{"start": 90, "end": 184, "shot": "landing", "cut": true, "tod": 0.5,
 "fog": {"near": 20, "far": 90, "color": "#e8e4e6", "blend": 12},
 "cast": [
   {"who": "captain", "mark": "deck", "action": "idle", "gesture": "point", "headTurn": 0.3,
    "cues": [{"frame": 128, "gesture": "cheer"}, {"frame": 160, "headTurn": -0.6}]},
   {"who": "newsboy", "mark": "a", "to": "b", "action": "walk"}
 ],
 "props": [{"name": "lee", "from": "deckSpot", "to": {"row": "north", "slot": 3, "out": 20, "along": 40}, "ease": "linear", "turn": -90, "visible": true}]}
```

- `start`/`end` are inclusive frames; beats tile the video exactly. `shot` names a shot. `cut: true` cuts
  to this beat instead of gliding.
- `cast[]`: `who` is `newsboy`, `operator` or a `world.cast` name; `mark` where they are, `to` where they walk
  to (`action: "walk"`); `action`: `idle | walk | point | react`; `gesture` held through the beat — newsboy:
  `none wave cheer shout holdPaper shrug lookUp think`; operator: `idle wave point armsCrossed handsOnHips
  talk`; cast figures: `none wave cheer shout point shrug lookUp think talk armsCrossed handsOnHips
  holdPaper`; `headTurn` −1..1; operator `pointAngle` degrees; **`cues`** change the gesture or the head
  turn at a frame inside the beat (in order) so a reaction lands on its word. `cast: []` is allowed.
- `props[]` cues named props: `from` and `to` are a mark name or `{row?, slot, out, along?}`; `ease`
  `linear` (a vehicle under way) or `inOut`; `visible` shows or hides; `turn` degrees; `act` for parts that
  animate (the catalog lists their acts). A prop keeps where its last cue left it.
- `tod` snaps this beat's time of day; `fog` overrides the world's fog for the beat, blended in over
  `blend` frames (0 cuts; default 12), `color` on screen (absent = aerial perspective).

## The options

```json
{"post": "v2",
 "motion": {"creep": 0.0022, "kicks": [142, 518], "emphasis": [[90, 128], [948, 983]],
            "rolls": [{"at": 452, "deg": 4, "dur": 24}, {"at": 540, "deg": 0, "dur": 20}]}}
```

`post` is always `"v2"`. `motion.creep` is the hold creep as a fraction of the aim distance per frame
(0.0015-0.0035); `kicks` are frames where an impact kick starts; `emphasis` spans push faster on punch
words; `rolls` ease the roll to `deg` over `dur` frames (set it back to 0 afterwards).

## A complete small example

A one-street river town, two beats, one invented part, one cast figure. Frame numbers assume a 150-frame
timeline; take yours from `get_timeline`.

```json
{
  "world": {
    "name": "Landing",
    "plan": {"kind": "street", "northZ": -8, "southZ": 40, "pitch": 10, "x0": -20},
    "ground": {"tex": "dirt", "hsl": {"hue": 38, "sat": 0.3, "light": 0.55}, "seed": 3},
    "pieces": [
      {"kind": "path", "width": 7, "hsl": {"hue": 35, "sat": 0.25, "light": 0.5}},
      {"kind": "building", "at": {"row": "north", "slot": 0}, "w": 9, "h": 6, "d": 8, "windows": 3, "seed": 11,
       "wall": {"hue": 200, "sat": 0.3, "light": 0.7}, "roof": {"hue": 15, "sat": 0.3, "light": 0.4},
       "sign": {"text": "HOTEL", "bg": "#f1e6c8", "fg": "#30241c"},
       "style": {"wall": "clapboard", "roof": "hip", "storeys": 2, "balcony": true, "porch": {"depth": 2.2, "rail": true, "roof": true}}},
      {"kind": "building", "at": {"row": "north", "slot": 1}, "w": 7, "h": 4.5, "d": 7, "windows": 2, "seed": 12,
       "wall": {"hue": 30, "sat": 0.4, "light": 0.5}, "roof": {"hue": 20, "sat": 0.3, "light": 0.35},
       "style": {"wall": "planks", "roof": "falseFront", "awning": {"depth": 1.6, "kind": "canvas"}}},
      {"kind": "prop", "what": "bollard", "at": {"row": "south", "slot": 0}, "out": 2, "along": 3},
      {"kind": "prop", "what": "crate", "at": {"row": "north", "slot": 0}, "out": 11, "along": 5, "turn": 20},
      {"kind": "cluster", "near": "wharf", "side": "upstage", "shot": "wharf", "r0": 4, "r1": 9, "count": 5, "what": ["barrel", "crate", "lamp"], "seed": 5},
      {"kind": "cluster", "near": "street", "side": "upstage", "shot": "town", "r0": 3, "r1": 8, "count": 6, "what": ["barrel", "crate", "cart", "lamp"], "seed": 6},
      {"kind": "scatter", "what": "tree", "count": 30, "band": {"x0": -80, "x1": 80, "z0": -60, "z1": -20}, "scale": [0.8, 1.3], "seed": 8}
    ],
    "water": [{"pos": [0, 70], "w": 300, "d": 50, "y": 0.1, "flow": [0.5, 0]}],
    "terrain": {"seed": 2, "flat": {"kind": "rect", "x0": -90, "x1": 90, "z0": -70, "z1": 48}, "edge": 30, "amp": 5, "scale": 70},
    "marks": [
      {"name": "wharf", "at": {"row": "south", "slot": 0}, "out": -3, "along": 0},
      {"name": "street", "at": {"row": "north", "slot": 0}, "out": 9, "along": 0}
    ],
    "shots": [
      {"name": "wharf", "subject": "wharf", "dist": 7, "height": 1.6, "swing": 150, "fov": 40, "aim": 1.3, "push": 0.6, "dof": 11, "fg": {"what": "barrel", "side": -1, "dist": 3}},
      {"name": "town", "subject": "street", "dist": 12, "height": 1.7, "swing": 160, "fov": 42, "aim": 2.2, "push": 1.2, "dof": 0}
    ],
    "fog": {"near": 25, "far": 220},
    "tod": [0, 0],
    "look": {"warmth": 0.1, "saturation": 1.2},
    "parts": {
      "bollard": {"name": "bollard", "blurb": "iron mooring post on a square base",
        "prims": [{"kind": "box", "size": [0.6, 0.1, 0.6], "at": [0, 0.05, 0], "mat": "iron"},
                  {"kind": "cylinder", "r": 0.12, "h": 0.9, "at": [0, 0.55, 0], "mat": "iron"}]}
    },
    "cast": {
      "clerk": {"blurb": "a telegraph clerk of the 1870s in white shirtsleeves with dark braces and a green cap, holding a sheet of paper",
        "jacket": "#f2efe6", "pants": "#3b3f52", "boots": "#4a3426", "hat": "cap", "cap": "#3f7a4a", "holds": "paper", "heldColor": "#f6f1dc", "skin": 2, "seed": 4}
    }
  },
  "beats": [
    {"start": 0, "end": 74, "shot": "wharf", "tod": 0.5,
     "cast": [{"who": "clerk", "mark": "wharf", "action": "idle", "gesture": "holdPaper", "cues": [{"frame": 40, "gesture": "shout"}]}]},
    {"start": 75, "end": 149, "shot": "town", "cut": true, "tod": 0, "cast": []}
  ],
  "opts": {"post": "v2", "motion": {"creep": 0.002, "kicks": [40], "emphasis": [[40, 70]]}}
}
```
