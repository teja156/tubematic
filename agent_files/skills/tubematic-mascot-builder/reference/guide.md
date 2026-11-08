# Writing a mascot's drawing code

The code you submit is plain JavaScript that runs in a page where p5.js (global mode), the p5.brush
watercolour library and the engine's kit are already loaded. The kit gives you the helpers named below
as globals. You write one drawing function and register it.

## The contract

```js
const MYCOLS = { col: '#…', dk: '#…', lt: '#…' /* plus any extra colours of your own */ };
window.MASCOT_COLS = { col: MYCOLS.col, dk: MYCOLS.dk, lt: MYCOLS.lt };  // main body colour, its shade, its light
function mymascot(x, y, u, o = {}) { /* draw */ }
window.MASCOT = mymascot;
```

- `(x, y)` is the ground point between the feet. `u` is the body unit, about 1/10 of the body width. Draw in
  body-local coordinates in multiples of `u`, negative y going up, after `push(); translate(x, y + dy); …`
  and a matching `pop()`.
- `window.MASCOT` and `window.MASCOT_COLS` are both required. The code is loaded as one script with no
  module system: no `import`, no `export`.

## Determinism (a render calls your function once per frame, in several browser tabs)

The output must be a **pure function of the options `o` and the global time `T`**. Two tabs rendering the
same frame must paint the same pixels.

- Never use `Math.random()`, `Date.now()`, `performance.now()` or any state that survives between calls.
- Before each separate part (body, each arm, each leg, eyes, mouth, emote…), call a seed function so a
  part's hand-drawn wobble is the same on every call and re-boils only when the engine's boil frame
  changes: `const rs = part => boilSeed(\`mymascot ${id} ${part}\`); rs('body');`. Take `id` from
  `o.boilKey ?? 1`, never from a counter that increments per call.
- Do not cache drawn results in module variables between calls.

## What the engine hands you in `o`

Honour all of these:

- pose: `dx`, `dy` (in u; negative is up), `sq` (squash; negative stretches), `take`, `rot`, `flip`, `sx`, `sy`
- arms: `aL`, `aR` (raise angle: 0 straight out, positive up, negative down)
- legs: `walk` (a phase number while walking, `null` when standing), `noLegs`, `noShadow`
- view: `o.view` is one of `front`, `q` (three-quarter), `side`, `back`. Each is a **separately
  drawn key view facing screen-right**; `flip` mirrors it (the three-quarter view, flipped, is also what a
  video shows while the mascot walks or faces left or right, so it must look good walking). Never fake a turn by squashing the front view. A
  data table of per-view numbers (face position, legs, arms) keeps this tidy.
- face: `eyes`, `mouth`, `lookX`, `lookY`, `squint`, `blush`, `seed`. Use the kit's `eye(kind, side, u, o, sw)`
  for every expressive eye (happy, heart, swirl, …) and `mouth(u, kind, sw)` for mouths. You may draw your
  own calm eyes (`normal`, `look`, `wide`) and your own default mouth (when `o.mouth` is empty).
- colour: take the body colours from `tintCols({ ...o, col: o.col || MYCOLS.col, dk: …, lt: … })` so moods
  tint them.
- emote: draw the emote at the end with `emote(o.emote, ex, ey, u * .9, o.emoteK ?? 1, o.emoteAge ?? T)`.
  Kinds in `EMOTE_TOP` sit over the head, the others by its top corner. Place them near the head, not on it.
- `o.draw`, when present, is a callback `(u, sw)` to call inside the body-local space after the face.

## The face

The kit's eyes and mouths are drawn at **fixed positions**: eye centres at (±2.5u, -6u) and the mouth around
(0, -4.3u), for a face about 5u wide. If your character's face is elsewhere or a different size,
`push(); translate(…); scale(…)` before drawing the face and `pop()` after.

Each view has a **face record**: `{ cx, fw, sides, bx }`.

- `cx`: face centre (u), `fw`: width factor (the three-quarter and side views narrow it), `sides`: which
  eyes show (`[-1, 1]`, or `[1]` in a true side view; `[]` or no face for the back).
- **`bx` is required**: the cheek x in u. The blush uses it, and a face record without it makes every blush
  `NaN`: the cheeks silently vanish and nothing throws.

Put the face on a **light area** of the body (a belly patch, a light screen, a pale face): the ink eyes and
mouth must read on it, including after a mood tint darkens or colours the body. A dark body with a dark face
fails the feels sheet.

**There is no talking mouth.** The mouth shows the emotion (`mouth(u, o.mouth, sw)`) and nothing else. Do not
add a speech or "talk" pose, and do not time anything to words.

## Drawing helpers

`paint(pts, { wash, washOp, fill, fillOp, bleed, tex, border, ink, sw, curv })` paints a closed shape: `wash`
is a flat colour layer, `fill` a watercolour layer, `ink` the outline colour (`null` for none), `sw` its
weight. `inkLine(pts, sw, colour, brush, curve)` draws a line (brushes include `'ink'`, `'inkfine'`, `'dry'`).
Shapes: `ellPts(cx, cy, rx, ry, n, jitter, rot)`, `rrPts(x, y, w, h, r, jitter)` (rounded rectangle),
`rectPts`, `starPts`, `ribbon(points, w0, w1)` (a tapered strip), `through(points, n)` (a smooth curve
through points). Colour: `mixCol(a, b, k)` and the palette `PAL` (`PAL.ink` is the outline colour,
`PAL.cream`, `PAL.rose`, …). Maths: `clamp`, `lerp`, `ease`, `seg`, `TAU`.

## Brush traps (measured; they cost real renders)

- **A `fill` bleeds colour.** p5.brush mixes a fill with what is already painted under it. A fill over a
  different colour picks up that colour as a muddy (often olive) bleed. Lay a flat `wash` base first in the
  colour you want, then put a `fill` of the same family on top, with `bleed: 0` or small, inset from the
  edges.
- **The first use of a brush drops the wash pending before it.** The first time a page uses a brush
  (notably `'dry'`), the paint pending just before it can be lost, so the first figure on a sheet may lose a
  limb's paint. Work around it at the start of your function with one tiny off-canvas stroke of each brush
  you use later, for example `inkLine([[x - 40 * u, y], [x - 39 * u, y]], .1, someColour, 'dry', 0);`.
- **The paper is the background.** Draw on nothing: the engine keys the figure out of the paper and adds a
  die-cut sticker edge. Do not paint a background, and do not rely on near-white fills inside the figure
  (the keying treats them as paper). Use a cream or a tint, not pure white.
- **Never use `random()` or `noise()` directly** in a way that changes between calls; seed through
  `boilSeed` first.
- No fonts, no `text()` for the figure's own content (the kit's `letter()` is fine for tiny marks).

## Staying in the box

Keep the body compact and centred on `x`, roughly 10u wide and 11u tall, as the shipped mascots are; emotes
float above that. Anything drawn far outside that is cropped by the engine's canvas, so look at the sheets for
clipping.

## A good shape of the code

A data table of views, a few small part functions (`body`, `arm`, `leg`, `face`), then the main function
that sets up the seed, the pose transforms, the arms behind, legs, body, face, arms in front, the optional
`o.draw`, and the emote. Keep it lean: a tidy 150–250 lines is plenty. Use `rs(part)` before every part.

## Working method

1. Start from `previous_code` or `based_on_code` if the job has one; otherwise write the contract skeleton
   first with a plain body and face and render the `turn` sheet to see the engine in action.
2. Render `turn`, look, fix. Render `feels`, look, fix. Render `act`, look, fix. Then, if you changed shared
   parts (a colour, the face, a limb), render every sheet again from the final code.
3. When you fix a view, check the **other** views for the same fault.
4. Stop at the checklist in SKILL.md, or when `renders_left` is near zero: submit what you have, honestly.
