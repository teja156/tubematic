# Puppet History data contract

The shape of `props.puppetHistory`, the one prop of the one `PuppetHistory` scene. `write_scene_config`
checks every rule here and names what is wrong. The worked example is `example-config.json`, timed to
`example-timeline.json`.

## The whole video

| Field | Holds |
|---|---|
| `cast` | 1 to 4 puppets: `{"id", "costume", "name"}` |
| `beats` | 1 to 14 beats, in order, each `{"type", "start", ..., "events"}` |
| `customProps` | Optional. Hand props you drew for this video: `[{"id", "src", "w", "h", "text"}]` |

A puppet's `id` is lowercase letters, digits and `_`, and starts with a letter. `name` is optional, at
most 18 characters, shown on a plate under the puppet: a real, historical person's name, or a role
("THE TAX MAN"). Never a living person or a leader of a regime still in power.

Costumes: `plain` (a plain modern shirt), `dress` (a long dress and bonnet), `peasant` (a medieval
tunic and cap), `farmer` (overalls and a straw hat), `worker` (a work jacket and flat cap), `clerk` (a
suit, tie and bowler hat), `noble` (a doublet, ruff and feathered cap), `royal` (a robe with white
trim and a plain crown), `knight` (armour, visor up), `legionary` (an ancient soldier's tunic, armour
bands and crested helmet), `soldier_1910s` (a khaki tunic and shallow helmet), `soldier_1940s` (an
olive tunic and round helmet), `sailor` (a striped top and sailor cap), `pilot` (a leather jacket,
cap and goggles), `explorer` (a khaki shirt and pith helmet), `scientist` (a lab coat), `monk` (a
habit and hood). Every costume is generic: none is the uniform of one army or the dress of one
person.

## Beats

| `type` | Fields | Takes the events |
|---|---|---|
| `set` | `set` | `enter`, `move`, `exit`, `act`, `swap`, `sign`, `hold`, `stamp`, `date` |
| `map` | `focus`: 1 to 8 countries | `enter`, `move`, `exit`, `act`, `swap`, `sign`, `hold`, `fill`, `arrow`, `label`, `date` |
| `card` | `title` (at most 22 characters), `lines`: 1 to 5 lines of at most 26 | `stamp`, `strike`, `date` |

A beat starts on a word (the first at frame 0), lasts at least 1.5 seconds, and ends where the next
one starts. Beats change on a hard cut and nobody carries over: puppets enter in each beat. A
costume swap lasts into later beats.

Sets: `farm` (sky, hills, a windmill, wheat and a fence), `street` (old town houses and a lamp post),
`office` (a wall with a window and a picture, a green dado), `palace` (columns, an arched window, a
red carpet), `castle` (a stone wall with battlements, a tower and a plain banner), `deck` (a ship's
deck, a mast and sail, the sea), `market` (stalls with awnings and crates), `factory` (a brick wall,
pipes, windows and a gear), `camp` (tents, a pennant and a crate in a field), `lab` (shelves of
flasks and a chalkboard), `classroom` (a chalkboard, a wall map and a clock), `field` (hills, a tree
and bushes).

A map shows today's countries (Natural Earth, 1:110m), by the names in `style.extra.countries`
(`France`, `United Kingdom`, `United States of America`, `Dem. Rep. Congo`, ...). It fits itself to the
`focus` countries, by each one's mainland.

## Events

Every event has `type` and `frame` (a whole frame on a word, or its beat's start), in frame order,
during its beat and at least 6 frames before it ends.

| `type` | Fields |
|---|---|
| `enter` | `who`, `slot` (0, 1, 2: left, middle, right), optional `from`: `slide` (from the nearest edge, 16 frames), `pop` (8 frames), `cut` (already there); optional `pose`, `face` |
| `move` | `who`, `slot`: another free slot (16 frames) |
| `exit` | `who`: it slides out to the nearest edge |
| `act` | `who`, `pose` and/or `face` |
| `swap` | `who`, `costume` |
| `sign` | `who`, `text` (at most 14 characters; `""` lowers the sign) |
| `hold` | `who`, `prop` (`""` drops it), optional `text` (at most what the prop's label takes) |
| `stamp` | `text` (at most 10 characters), optional `color`: `red`, `green`, `blue` |
| `date` | `text` (at most 12 characters) |
| `strike` | `line` (the card line's index, from 0), `text` (the new value, at most 12 characters) |
| `fill` | `region` (a focus country), `color`: `red`, `blue`, `green`, `yellow`, `purple`, `grey` |
| `arrow` | `from`, `to`: two focus countries; at most 6 a map |
| `label` | `region` (a focus country), `text` (at most 18 characters) |

Poses: `stand`, `point`, `salute`, `wave`, `shrug`, `hold`, `cheer`, `panic`, `think`, `sign` (a held
sign sets it). Faces: `stern`, `happy`, `proud`, `worried`, `shock`, `sad`, `smug`, `angry`.

## The stage

The frame is 1080 x 1920. Puppets are framed from the waist up; the waist is at y 1640, behind the
set's foreground band (from y 1600). The three slots are at x 210, 540 and 870, and a puppet in the
right slot faces left, the others right. A puppet is about 330 wide and 470 tall from the waist, its
hat included. Name plates sit on the foreground band near y 1735; a sign is held in front of the
chest near y 1440; a stamp lands near y 860 (y 1180 on a card); the date sits near the top left (y
400). Captions sit near the top, about y 270. A map fills x 40 to 1040, y 330 to 1070; a card x 150
to 930, y 430 to 1370.

## Hand props

| Prop | Box | Text | What it is |
|---|---|---|---|
| `scroll` | 150 x 170 | 10 | a rolled scroll, a decree |
| `letter` | 150 x 120 | 10 | a sealed letter |
| `coin_bag` | 130 x 140 | - | a bag of coins |
| `quill` | 90 x 170 | - | a quill pen |
| `book` | 150 x 120 | - | a closed book |
| `lantern` | 100 x 160 | - | an oil lantern |
| `hammer` | 110 x 170 | - | a hammer |
| `shovel` | 80 x 200 | - | a shovel |
| `flag` | 160 x 200 | 6 | a plain flag on a pole |
| `telescope` | 180 x 80 | - | a spyglass |
| `cup` | 100 x 110 | - | a mug |
| `bread` | 150 x 90 | - | a loaf |
| `sword` | 60 x 200 | - | a sword |
| `basket` | 150 x 130 | - | a basket of produce |

## Props of your own

| Field | Holds |
|---|---|
| `id` | What `hold` events call it: lowercase letters, digits or `_`, not a library prop's id |
| `src` | The `src` `write_scene_file` returned for this video's `prop-<name>` file |
| `w`, `h` | Its box at scale 1, whole units from 50 to 300 |
| `text` | Optional, the most characters its label takes, 0 to 10 |

The file default-exports one component that takes `{text}` and draws centred on (0, 0). It imports
only `react`, `remotion` and `../../installed/puppetHistory/ink` (or `contract`), with `import`. Each
prop is drawn once into a cached picture, so it never uses a hook (`useCurrentFrame`, `useState`...):
it draws from `text` alone. It never uses an SVG filter, a gradient (SVG or CSS), a dashed stroke, a
backdrop filter or blend mode, an image, embedded HTML or a fetch, a Remotion media or render-control
part (`Img`, `Audio`, `Video`, `staticFile`, `delayRender`...), `Math.random`, `Date`, a timer, a
dynamic import, `performance`, `crypto`, `window`, `document`, `globalThis`, `eval` or a `Function`
constructor, and no SVG pattern. The check reads comments too. `example-prop-hourglass.tsx` is a
finished one.
