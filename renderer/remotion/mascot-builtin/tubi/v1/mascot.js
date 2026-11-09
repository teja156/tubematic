// mascot.js: "Tubi", Tubematic's own mascot: a small living retro terminal (a cathode-ray TUBE, hence the name). Its
// front face is the logo: a thick amber frame round a navy panel, a pale lit screen that carries the face, and the
// logo's cursor block on the chin. It never talks: the mouth only ever shows an emotion.
//
// This is the BUILT-IN version 1 and it is immutable: installs and approved videos pin it by version. A change to the
// drawing ships as v2 (a new mascot-builtin/tubi/v2/ directory) together with a migration that moves the builtin row.
//
// Contract (the engine's): (x, y) is the ground point between the feet, u is the body unit, and every frame is a pure
// function of the options + T. Body-local coordinates, front view: a box 10u wide from y -10.2u to -1.5u. Two stubby
// legs with amber feet reach y 0, two stubby navy arms with amber mitts pivot at the box's sides, and a power cord
// trails behind it like a tail.

const TUBI = { col: '#F5A623', dk: '#D4922A', lt: '#FCE6B4', navy: '#1C2330', navyDk: '#11151F', navyLt: '#3A4866',
               cursorDim: '#9A6A20', led: '#65D27A' };
window.MASCOT_COLS = { col: TUBI.col, dk: TUBI.dk, lt: TUBI.lt };

// Drawn key views. Every view faces screen-right; flip mirrors it.
//   front: [x0, x1] of the front face (frame).  side: [x0, x1] of the box's visible side panel (null = none).
//   profile: the true side view (the CRT seen side-on), drawn by tubiProfile.
//   face: cx / fw / sides / bx as in the kit, plus mx (the mouth's x in face space). bx is required: see blush().
//   legs: [x, far].  arms: [pivotX, dir, which, layer] (0 = far, behind and darker; 1 = behind the box's edge; 2 = in
//   front).  cord: the power cord's path, behind the box (back: in front of it).  rx: half width.  hx: head centre x.
const TUBI_VIEWS = {
  front: { rx: 5, front: [-5, 5], side: null, face: { cx: 0, fw: 1, sides: [-1, 1], bx: 2.85, mx: 0 },
           legs: [[-2.3, 0], [2.3, 0]], arms: [[-4.85, -1, 'L', 1], [4.85, 1, 'R', 1]], cord: null },
  q:     { rx: 4.9, front: [-2.3, 5], side: [-4.7, -2.0], face: { cx: 1.35, fw: .73, sides: [-1, 1], bx: 2.85, mx: 0 },
           legs: [[-1.6, 1], [2.4, 0]], arms: [[-4.5, -1, 'L', 0], [4.85, 1, 'R', 1]],
           cord: [[-4.2, -2.6], [-5.3, -1.2], [-5.7, -.3], [-6.7, -.25], [-7.3, -.9]] },
  side:  { rx: 4.7, hx: .2, profile: true, front: null, side: null,
           face: { cx: 3.5, fw: .4, sides: [1], bx: 2.63, mx: 2.25 },
           legs: [[-.95, 1], [.75, 0]], arms: [[-.4, 0, 'R', 2]],
           cord: [[-4.2, -2.7], [-5.2, -1.4], [-5.6, -.35], [-6.6, -.25], [-7.2, -.9]] },
  back:  { rx: 5, front: null, side: null, face: null, back: true,
           legs: [[-2.3, 0], [2.3, 0]], arms: [[-4.85, -1, 'R', 1], [4.85, 1, 'L', 1]],
           cord: [[3.3, -2.6], [4.3, -1.9], [4.9, -.7], [5.9, -.3], [6.6, -.8]] },
};
// How much the housing tapers toward the back (in u, top and bottom), shared by the q view's side panel and the profile.
const TAPER = [.7, .45];

// Tubi's own calm eyes: little ink cursor blocks with a glint. Every expressive state uses the kit's eye().
function tubiEye(e, s, u, o, sw) {
  if (!['normal', 'look', 'wide'].includes(e)) return eye(e, s, u, o, sw);
  const lx = (o.lookX || 0) * u * .45, ly = (o.lookY || 0) * u * .4, k = e === 'wide' ? 1.25 : 1;
  if (((T * .9 + (o.seed || 0) * 1.7) % 3.3) < .12) { inkLine([[-.75 * u, .45 * u], [.75 * u, .45 * u]], sw * 1.2, PAL.ink, 'ink', 0); return; }
  const w = 1.15 * u * k, h = 1.85 * u * k;
  paint(rrPts(lx - w / 2, ly - h / 2, w, h, .42 * u * k), { wash: PAL.ink, ink: null });
  paint(ellPts(lx - .2 * u * k, ly - .45 * u * k, .2 * u * k, .3 * u * k, 10), { wash: PAL.cream, washOp: 240, ink: null });
}
function tubiEyes(u, o, sw, sides) {
  const kinds = Array.isArray(o.eyes) ? o.eyes : o.eyes === 'wink' ? ['happy', 'normal'] : [o.eyes || 'normal', o.eyes || 'normal'];
  if (kinds[0] === 'shades') return eyes(u, o, sw, sides, 0);
  const sqz = clamp(o.squint || 0);
  if (sqz > .8) { for (const s of sides) inkLine([[s * 2.5 * u - .8 * u, -5.9 * u], [s * 2.5 * u + .8 * u, -5.9 * u]], sw, PAL.ink, 'ink', 0); return; }
  if (sqz > 0) { push(); translate(0, -6 * u); scale(1 + sqz * .15, 1 - sqz); translate(0, 6 * u); }
  for (const s of sides) { push(); translate(s * 2.5 * u, -6 * u); tubiEye(kinds[s < 0 ? 0 : 1], s, u, o, sw); pop(); }
  if (sqz > 0) pop();
}
// The default mouth: a small content smile.
function tubiMouth(u, sw) {
  inkLine([[-.7 * u, -4.55 * u], [0, -4.15 * u], [.7 * u, -4.55 * u]], sw * .85, PAL.ink, 'ink', .6);
}

// The screen's mood colour. The kit tints lt by mixing it a little toward the mood colour; for a cool mood (sad blue)
// that lands between cream and blue, on a muddy grey. Tubi pushes the kit's shift further the same way, capped, so the
// screen turns a clean cool blue (or rose, or salmon) instead. It depends on the kit's lt alone, so an acted
// cross-fade between two emotions stays continuous.
const rgbOf = h => [16, 8, 0].map(s => (parseInt(h.slice(1), 16) >> s) & 255);
function tubiScreen(lt) {
  const a = rgbOf(TUBI.lt), d = rgbOf(lt).map((v, i) => (v - a[i]) * 6), m = Math.hypot(...d), k = m > 85 ? 85 / m : 1;
  const c = a.map((v, i) => Math.round(clamp(v + d[i] * k, 0, 255)));
  return '#' + ((1 << 24) + (c[0] << 16) + (c[1] << 8) + c[2]).toString(16).slice(1);
}

// The amber of the frame, painted like watercolour. p5.brush mixes a watercolour fill with whatever is already on the
// canvas, and a fill bleeds past its outline: over navy that turns olive (the arms and legs behind the frame, the
// panel in front of it). So: a flat amber base, flushed onto the canvas so the glaze mixes with amber only; then a
// granulating amber glaze inset from the edges, so its bleed stays on amber; then dry-brush strokes (strokes never
// bleed), deep amber low and right, light amber high and left. box = [x, y, w, h] in px; b = the band's width in px.
function tubiAmber(shape, box, C, sw, J, u) {
  const [x, y, w, h] = box, i = .22 * u, b = Math.min(.95 * u, w / 2);
  paint(shape, { wash: C.col, washOp: 255, ink: null });
  flushBrush();
  paint(rrPts(x + i, y + i, w - 2 * i, h - 2 * i, .6 * u), { fill: C.col, fillOp: 140, bleed: 0, tex: .9, border: .7, ink: null });
  const m = b / 2, lt = mixCol(C.col, PAL.cream, .5), dry = (pts, col, k) => inkLine(pts, sw * k, col, 'dry', .4);
  dry([[x + w * .12, y + m], [x + w * .55, y + m * .9], [x + w - b * 1.2, y + m]], lt, .55);
  dry([[x + m, y + b * 1.3], [x + m * 1.05, y + h * .45], [x + m, y + h - b * 1.4]], lt, .45);
  dry([[x + b * 1.2, y + h - m], [x + w * .5, y + h - m * 1.1], [x + w - w * .1, y + h - m]], C.dk, .6);
  dry([[x + w - m, y + b * 1.4], [x + w - m * 1.05, y + h * .55], [x + w - m, y + h - b * 1.2]], C.dk, .5);
  paint(shape, { ink: PAL.ink, sw });
}

// The front face: amber frame, navy panel, lit screen, and the chin with the cursor block and LED.
// k = horizontal foreshortening (1 in the front view).
function tubiFront(x0, x1, u, sw, C, J, scr) {
  const w = x1 - x0, k = w / 10, X = f => (x0 + f * k) * u;
  rs_('frame');   // a thick amber frame, like the logo's border
  tubiAmber(rrPts(x0 * u, -10.2 * u, w * u, 8.7 * u, .95 * u, J * .5), [x0 * u, -10.2 * u, w * u, 8.7 * u], C, sw, J, u);
  rs_('panel');
  paint(rrPts(X(.95), -9.25 * u, (10 - 1.9) * k * u, 6.9 * u, .5 * u, J * .4), { wash: TUBI.navy, washOp: 255, ink: PAL.ink, sw: sw * .6 });
  rs_('screen');
  const sx0 = X(1.35), sw_ = (10 - 2.7) * k * u, s = rrPts(sx0, -8.85 * u, sw_, 5.55 * u, Math.min(1.1 * u, sw_ * .3), J * .3);
  paint(s, { wash: scr, washOp: 255, ink: null });
  // faint scanlines, as on a CRT
  for (let i = 0; i < 6; i++) { const yy = (-8.25 + i * .95) * u; inkLine([[sx0 + .5 * u * Math.max(k, .5), yy], [sx0 + sw_ - .5 * u * Math.max(k, .5), yy]], sw * .3, mixCol(scr, C.dk, .3), 'inkfine', 0); }
  paint(s, { ink: PAL.ink, sw: sw * .8 });
  rs_('chin');   // the logo's blinking cursor block, and a power LED
  const blink = frac(T * 1.1) < .55;
  paint(rrPts(X(7.55), -3.08 * u, .85 * k * u, .55 * u, .06 * u), { wash: blink ? C.col : TUBI.cursorDim, washOp: 255, ink: null });
  paint(ellPts(X(2.05), -2.8 * u, .2 * u * Math.max(k, .5), .2 * u, 10), { wash: TUBI.led, washOp: 255, ink: null });
}
// The navy housing's side, from x0 (back) to x1 (front): shorter at the back, as an old tube monitor tapers.
function tubiHousing(x0, x1, u, sw, J, vents) {
  const P = rrPts(x0 * u, -10.1 * u, (x1 - x0) * u, 8.55 * u, .8 * u, J * .5).map(([px, py]) => {
    const back = clamp((x1 * u - px) / ((x1 - x0) * u));   // 1 at the back edge
    return [px, py < -5.8 * u ? py + back * TAPER[0] * u : py - back * TAPER[1] * u];
  });
  paint(P, { wash: TUBI.navy, washOp: 255, ink: PAL.ink, sw });
  // a dry-brush sheen along the top (strokes, not a fill: a navy fill bleeds a grey halo)
  const top = -9.45 + TAPER[0] * .35;
  inkLine([[(x0 + .8) * u, (top + .1) * u], [(x0 + (x1 - x0) * .55) * u, (top - .05) * u], [(x1 - .6) * u, (top - .1) * u]], sw * .45, TUBI.navyLt, 'dry', .5);
  const vx0 = x0 + .6, vx1 = x0 + Math.min(vents, (x1 - x0) * .55);
  for (let i = 0; i < 3; i++) inkLine([[vx0 * u, (-7.6 + i * .7) * u], [vx1 * u, (-7.65 + i * .7) * u]], sw * 1.1, TUBI.navyDk, 'ink', 0);
}
// The true side view: the housing seen side-on, the amber frame as a thick strip at the front, and the screen's convex
// glass bulging just past it, which carries the face in profile.
function tubiProfile(u, sw, C, J, scr) {
  rs_('panel'); tubiHousing(-4.5, 3.1, u, sw, J, 3.2);
  rs_('frame'); tubiAmber(rrPts(2.95 * u, -10.2 * u, 1.05 * u, 8.7 * u, .45 * u, J * .4), [2.95 * u, -10.2 * u, 1.05 * u, 8.7 * u], C, sw, J, u);
  rs_('screen');
  const G = []; for (let i = 0; i <= 14; i++) { const a = -Math.PI / 2 + i / 14 * Math.PI; G.push([(3.95 + Math.cos(a) * 1.15) * u, (-6.07 + Math.sin(a) * 2.62) * u]); }
  paint(G, { wash: scr, washOp: 255, ink: PAL.ink, sw: sw * .8 });
  rs_('chin');   // the LED, seen edge-on on the frame
  paint(ellPts(3.5 * u, -2.8 * u, .14 * u, .2 * u, 10), { wash: TUBI.led, washOp: 255, ink: null });
}
let rs_ = () => {};

let TUBI_N = 0;
function tubi(x, y, u, o = {}) {
  const id = o.boilKey ?? ++TUBI_N, rs = part => boilSeed(`tubi ${id} ${part}`); rs_ = rs;
  x += (o.dx || 0) * u;
  const V = TUBI_VIEWS[o.view] || TUBI_VIEWS.front;
  const dy = (o.dy || 0) * u, sq = (o.sq || 0) + (o.take || 0), sw = clamp(u / 15, .45, 2.4) * (o.swMul || 1), J = u * .05;
  const C = tintCols({ ...o, col: o.col || TUBI.col, dk: o.dk || TUBI.dk, lt: o.lt || TUBI.lt });
  const scr = tubiScreen(C.lt);
  const farNavy = mixCol(TUBI.navy, PAL.ink, .35);

  // Measured: the first use of the dry brush on a page dropped the wash still pending before it (the first figure on
  // a sheet lost its left arm's paint). So the dry brush is used first, off to one side, before anything is painted.
  inkLine([[x - 40 * u, y], [x - 39 * u, y]], .1, TUBI.navy, 'dry', 0);
  rs('shadow');
  if (!o.noShadow) {
    const f = 1 - Math.min(.5, Math.abs(o.dy || 0) * .06);
    paint(ellPts(x, y + u * .15, u * V.rx * 1.15 * f, u * f, 22), { fill: PAL.ink, fillOp: 90, bleed: .25, tex: .3, border: .1, ink: null });
  }

  push();
  translate(x, y + dy);
  if (o.rot) rotate(o.rot);
  scale((o.flip ? -1 : 1) * (o.sx ?? 1) * (1 + sq * .6), (o.sy ?? 1) * (1 - sq));

  const arm = ([px, dir, which, layer]) => {
    rs('arm' + which);
    const a = which === 'L' ? (o.aL ?? .2) : (o.aR ?? .2), hook = which === 'L' ? o.armL : o.armR, d = dir || 1, isFar = layer === 0;
    const lift = dir ? clamp((Math.abs(a) - .6) / .9) : 0;   // a raised arm slides out past the box's edge
    push(); translate((px + d * .9 * lift) * u, (-5.7 - .6 * lift) * u);
    const ar = a > 0 ? a * .8 : a;   // raised arms angle outward, away from the face
    rotate(dir === 0 ? .7 - a : d < 0 ? ar : -ar);
    const al = 2.2 * u, aw = 1.05 * u;
    // the arm's root starts inside the box (hidden behind its edge), so a raised arm never floats free of it
    const root = (dir ? 1.6 : .9) * u;
    paint(rrPts(d < 0 ? -al : -root, -aw / 2, al + root, aw, aw * .48, J * .4), { wash: isFar ? farNavy : TUBI.navy, washOp: 255, ink: PAL.ink, sw: sw * .8 });
    paint(ellPts(d * (al - .1 * u), 0, .62 * u, .6 * u, 12, J * .3), { wash: isFar ? mixCol(C.dk, PAL.ink, .2) : C.col, washOp: 255, fill: C.dk, fillOp: 80, ink: PAL.ink, sw: sw * .7 });   // amber mitt
    if (hook) { translate(d * 2.3 * u, 0); if (d < 0) scale(-1, 1); hook(u, sw); }
    pop();
  };

  const cord = () => {
    if (!V.cord) return;
    rs('cord');
    const P = V.cord.map(([cx, cy], i) => [cx * u, (cy + (i === V.cord.length - 1 ? .25 * Math.sin(T * TAU * .6 + 1) : 0)) * u]);
    const last = P[P.length - 1], prev = P[P.length - 2];
    paint(ribbon(P, .42 * u, .36 * u), { wash: TUBI.navyDk, washOp: 255, ink: PAL.ink, sw: sw * .6 });
    // the plug: a small amber block with two prongs, pointing along the cord's end
    push(); translate(last[0], last[1]); rotate(Math.atan2(last[1] - prev[1], last[0] - prev[0]));
    paint(rrPts(-.1 * u, -.42 * u, .9 * u, .84 * u, .2 * u), { wash: C.dk, washOp: 255, ink: PAL.ink, sw: sw * .6 });
    for (const py of [-.2, .2]) inkLine([[.8 * u, py * u], [1.25 * u, py * u]], sw * .7, PAL.ink, 'ink', 0);
    pop();
  };

  // cord and far arms behind, legs, body, near arms
  if (!V.back) cord();
  V.arms.filter(a => a[3] < 2).sort((p, q) => p[3] - q[3]).forEach(arm);
  if (!o.noLegs) V.legs.forEach(([lx, isFar], i) => {
    rs('leg' + i);
    let lift = 0, sx = 0;
    if (o.walk != null) {
      if (o.view === 'side' || o.view === 'q') { const ph = (o.walk + (i % 2 ? .5 : 0)) * TAU; sx = Math.sin(ph) * .55; lift = Math.max(0, Math.cos(ph)) * .65; }
      else { const ph = Math.sin((o.walk + (i % 2 ? .5 : 0)) * TAU); if (ph > 0) lift = ph * .7; }
    }
    const lw = 1.35, lx0 = (lx + sx - lw / 2) * u, bot = -lift;
    paint(rrPts(lx0, -2.3 * u, lw * u, (2.3 + bot - .2) * u, .5 * u, J * .4), { wash: isFar ? farNavy : TUBI.navy, washOp: 255, ink: PAL.ink, sw: sw * .8 });
    paint(ellPts(lx0 + (lw / 2 + .15) * u, (bot - .3) * u, .95 * u, .42 * u, 14, J * .3), { wash: isFar ? mixCol(C.dk, PAL.ink, .25) : C.dk, washOp: 255, ink: PAL.ink, sw: sw * .7 });
  });

  rs('body');
  if (V.back) {
    // the back: the frame's amber rim peeks round a navy rear housing with vent slots
    tubiAmber(rrPts(-5 * u, -10.2 * u, 10 * u, 8.7 * u, .95 * u, J * .5), [-5 * u, -10.2 * u, 10 * u, 8.7 * u], C, sw, J, u);
    rs('house');
    const house = rrPts(-4.25 * u, -9.45 * u, 8.5 * u, 7.25 * u, .8 * u, J * .5);
    paint(house, { wash: TUBI.navy, washOp: 255, ink: null });
    for (let i = 0; i < 4; i++) inkLine([[-2.3 * u, (-8.1 + i * .7) * u], [2.3 * u, (-8.1 + i * .7) * u]], sw * 1.1, TUBI.navyDk, 'ink', 0);
    // a small amber T badge, the logo's letter
    paint(rectPts(-.75 * u, -4.85 * u, 1.5 * u, .38 * u), { wash: C.col, washOp: 255, ink: null });
    paint(rectPts(-.2 * u, -4.55 * u, .4 * u, 1.25 * u), { wash: C.col, washOp: 255, ink: null });
    paint(house, { ink: PAL.ink, sw: sw * .8 });
  } else if (V.profile) {
    tubiProfile(u, sw, C, J, scr);
  } else {
    if (V.side) tubiHousing(V.side[0], V.side[1], u, sw, J, 2.6);
    tubiFront(V.front[0], V.front[1], u, sw, C, J, scr);
  }
  if (V.back) cord();

  if (V.face) {
    const F = V.face;
    push(); translate(F.cx * u, -.4 * u); scale(F.fw, 1);
    if (o.blush) blush(u, sw, F, o.blush === true ? 1 : o.blush);
    rs('eyes'); tubiEyes(u, o, sw, F.sides);
    rs('mouth');
    push(); translate(F.mx * u, 0); if (o.mouth) mouth(u, o.mouth, sw); else tubiMouth(u, sw); pop();
    pop();
  }
  V.arms.filter(a => a[3] === 2).forEach(arm);
  rs('draw'); if (o.draw) o.draw(u, sw);
  pop();

  rs('emote');
  if (o.emote) {
    const top = EMOTE_TOP.includes(o.emote), dir = o.flip ? -1 : 1, hx = V.hx ?? (V.front ? (V.front[0] + V.front[1]) / 2 : 0);
    const ex = top ? x + dir * (hx + 1.6) * u : x + dir * (V.rx + 1.0) * u, ey = y + dy + (top ? -13.0 : -10.4) * u * (1 - sq);
    emote(o.emote, ex, ey, u * .9, o.emoteK ?? 1, o.emoteAge ?? T);
  }
  rs('after');
}
window.MASCOT = tubi;
