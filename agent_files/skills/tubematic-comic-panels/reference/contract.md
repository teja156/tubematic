# Comic Panels data contract

The shape of `props.comicPanels`, the one prop of the one `ComicPanels` scene. `write_scene_config`
checks every rule here and names what is wrong. The worked example is `example-config.json`, timed to
`example-timeline.json`.

## The whole video

| Field | Holds |
|---|---|
| `cast` | 1 to 4 characters: `{"id", "kind", "hair", "outfit", "skin"}` |
| `pages` | 1 to 3 pages, in order: `{"start", "layout", "title", "panels"}` |
| `splash` | Optional. The frame the camera pulls back to the whole last page for the ending |
| `customProps` | Optional. Props you drew for this video: `[{"id", "src", "w", "h", "text"}]` |

A character's `id` is lowercase letters, digits and `_`, and starts with a letter. Kinds: `hero`
(the house hero: a big round head and spiky black hair; at most one), `person` (an invented person
built from knobs), `villain` (a hooded silhouette with a grin). Hairs: `spiky`, `bob`, `bun`,
`short`, `bald`, `curly`. Outfits: `blue`, `red`, `green`, `yellow`, `purple`, `grey`. Skins:
`light`, `tan`, `brown`, `dark`. Knobs apply to a `person`; the hero and the villain keep their look.

## Pages and panels

The page is 1000 x 1700 units: a title bar 120 units tall, then the panels. A `title` is at most 28
characters. A panel is `{"start", "tone", "items"}`; it starts on a word, is read for at least 1.5
seconds, and its items appear while it is read. Tones: `cream`, `pink`, `blue`, `yellow`, `green`,
`dark`.

| Layout | Panels (x, y, w, h in page units), in reading order |
|---|---|
| `stack3` | three full-width rows: 952 x 500, 952 x 500, 952 x 496 |
| `stack4` | four full-width rows, each 952 x about 370 |
| `2+1` | two side by side (466 x 760), then one full-width (952 x 756) |
| `1+2` | one full-width (952 x 760), then two side by side (466 x 756) |
| `2+2` | a grid of four, each 466 x about 760 |

A wide panel suits a scene with two characters or a character and a big prop; a tall half-width panel
suits one character and a balloon.

## Items

Every item has `type` and `frame` (a whole frame on a word, or its panel's start). Positions `x` and
`y` are fractions of the panel, 0 to 1, the item's centre.

| `type` | Fields |
|---|---|
| `actor` | `who` (a cast id), `pose`, `face`, `x`, `y`, optional `scale` (0.5 to 1.6), `flip`, `id` |
| `prop` | `prop`, `x`, `y`, optional `scale` (0.5 to 1.6), `text`, `id` |
| `balloon` | `kind`: `speech`, `thought`, `shout`; `text` (at most 40 characters); `x`, `y`; `to` |
| `caption` | `text` (at most 40 characters), a yellow box in the panel's top-left corner |
| `sfx` | `text` (at most 10 characters, a sound: `POW!`, `CLICK`, `RING!`), `x`, `y` |
| `lines` | `kind`: `speed` (action) or `focus` (a shock) |
| `hit` | none: the camera punches in and shakes for 8 frames |

Poses: `stand`, `point`, `panic`, `cheer`, `think`, `type`, `shrug`, `facepalm`. Faces: `neutral`,
`happy`, `shocked`, `worried`, `angry`, `smug`, `sad`, `grin`.

A character is 260 x 300 units at scale 1, framed from the waist up; it must stay inside its panel's
top and sides, and may be cut off at the bottom. A balloon is sized from its text (about 16 characters
a line, up to 3 lines) and must stay inside its panel and off every other balloon and sound effect. `to` is the `id` given
to an actor or prop in this panel, or the actor's cast id, or the prop's name. A sound effect is
about 52 units a character wide and 110 tall.

## Props

| Prop | Box | Text | What it is |
|---|---|---|---|
| `phone` | 150 x 260 | 24 | a phone, its screen showing the text |
| `laptop` | 300 x 220 | 24 | a laptop |
| `inbox` | 420 x 220 | 30 | an email inbox with a subject line |
| `login` | 340 x 260 | 20 | a login form with a site name |
| `browser` | 420 x 120 | 24 | a browser address bar |
| `monitor` | 320 x 260 | 24 | a desktop monitor |
| `server` | 160 x 260 | 0 | a server rack |
| `lock` | 120 x 160 | 0 | a padlock |
| `key` | 170 x 90 | 0 | a key |
| `shield` | 150 x 180 | 0 | a shield |
| `bug` | 160 x 150 | 0 | a bug |
| `virus` | 160 x 160 | 0 | a virus |
| `cell` | 180 x 180 | 0 | a cell |
| `bomb` | 160 x 170 | 0 | a cartoon bomb |
| `money` | 200 x 120 | 8 | a banknote |
| `document` | 160 x 210 | 20 | a sheet of paper with a heading |
| `envelope` | 200 x 140 | 16 | an envelope with an address |
| `rocket` | 140 x 260 | 0 | a rocket |
| `planet` | 220 x 220 | 0 | a ringed planet |
| `clock` | 150 x 160 | 0 | an alarm clock |
| `sign` | 260 x 160 | 16 | a signboard |
| `door` | 180 x 300 | 0 | a door |

## Props of your own

| Field | Holds |
|---|---|
| `id` | What prop items call it: lowercase letters, digits or `_`, not a library prop's id |
| `src` | The `src` `write_scene_file` returned for this video's `prop-<name>` file |
| `w`, `h` | Its box at scale 1, whole units from 60 to 500 |
| `text` | Optional, the most characters its text takes, 0 to 24 |

The file default-exports one component that takes `{text}` and draws centred on (0, 0). It imports
only `react`, `remotion` and `../../installed/comicPanels/ink` (or `contract`), with `import`. Each
prop is drawn once into a cached picture, so it never uses a hook (`useCurrentFrame`, `useState`...):
it draws from `text` alone. It never uses an SVG filter, a gradient (SVG or CSS), a dashed stroke, a
backdrop filter or blend mode, an image, embedded HTML or a fetch, a Remotion media or render-control
part (`Img`, `Audio`, `Video`, `staticFile`, `delayRender`...), `Math.random`, `Date`, a timer, a
dynamic import, `performance`, `crypto`, `window`, `document`, `globalThis`, `eval`, `require`, a `constructor` lookup, `React[...]` or a `Function`
constructor, and no SVG pattern of its own: halftone dots come from `Dots` in `ink`. The check reads
comments too. `example-prop-trophy.tsx` is a finished one.
