# Isometric Infographic: field reference

`props.isometric` of the one `IsometricInfographic` scene. Frames are the video's own (the timeline's
word frames); every frame you give sits within 2 frames of a word's start. Tiles: the board is 10 x 10,
x down to the right, y down to the left, (0, 0) at the top corner.

| Field | Holds |
|---|---|
| `title` | 1-22 characters, at the top |
| `readout` | Optional `{"label": 1-12 characters, "unit": up to 4, "steps": [{"value": 0-999999, "at", "red"?}, ...], "cubes"?: {"per": number, "color"}}` |
| `boards` | 1 to 3 boards |
| `legend` | Optional `{"at", "items": [{"color", "label": 1-12 characters}, ...]}`, 1 to 5 items |
| `customProps` | Optional, at most 6: `{"id", "main": colour, "height": tiles, "solids": [...]}` |

## A board

| Field | Holds |
|---|---|
| `start` | The frame it starts on |
| `areas` | Up to 8 `{"kind", "rect": [x0, y0, x1, y1]}`; kinds `land`, `forest`, `city`, `sand`, `water`, `road`, `plaza`, `field` |
| `props` | 1 to 14 `{"id", "what", "at": [x, y], "color"?, "scale"?: 0.6-1.6, "enter"?: frame}` |
| `routes` | Up to 3 `{"id", "points": [[x, y], ...] (2-8), "color", "at"}` |
| `movers` | Up to 4 `{"route", "what", "color"?, "at", "back"?: true}` |
| `pins` | Up to 4 `{"on": prop id, "label", "value"?: 1-8 characters, "unit"?: up to 4, "at", "side"?: "left" or "right"}` |
| `camera` | Up to 8 `{"at", "focus"?: prop id, "zoom"?: 1-2}`, in order |
| `lifts` | Up to 3 `{"prop", "at"}` |
| `cutaways` | Up to 3 `{"prop", "at", "inside": [1-3 props]}`, on `house`, `office`, `factory`, `warehouse`, `data_centre`, `shop`, `bank`, `hospital`, `school`, `power_plant` |
| `explodes` | Up to 3 `{"prop", "at"}`, on `server_rack`, `container_stack` |

## Library

- Props: `house`, `office`, `tower_block`, `factory`, `warehouse`, `data_centre`, `server_rack`, `cell_tower`, `dish`, `router`, `phone`, `laptop`, `shop`, `bank`, `hospital`, `school`, `power_plant`, `wind_turbine`, `solar_panel`, `water_tower`, `tank`, `pipe`, `truck`, `van`, `car`, `bus`, `train`, `ship`, `plane`, `crane`, `container_stack`, `conveyor`, `tree`, `cloud`, `person`, `crowd`, `parcel`, `cube`, `coin`, `dam`, `silo`
- Colours: `red`, `gold`, `slate`, `teal`, `green`, `blue`, `cream`, `grey`, `plum`
- Movers that read well: `cube`, `parcel`, `truck`, `van`, `car`, `bus`, `ship`, `plane`, `train`, `person`, `coin`

## Solids (custom props)

| `s` | Fields |
|---|---|
| `box` | `x`, `y`, `z`?, `w`, `d`, `h`, `c`, `layer`? (0-4) |
| `gable` | `x`, `y`, `z`?, `w`, `d`, `h`, `c` (a roof along x) |
| `cyl`, `cone`, `pyr` | `x`, `y`, `z`?, `r`, `h`, `c` |

x and y from -0.8 to 0.8, z from 0 to 3, sizes above 0 up to 1.6, heights up to 3; `c` is `main`, `accent` or
a colour name. List them back to front.
