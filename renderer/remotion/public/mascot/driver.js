// Cue-track driver: turns the per-video mascot DATA (what the agent writes) into a pose per frame.
// The host page sets window.TRACK = { fps, width, height, cues: [...] } before the first renderMascot(t). A cue is
// { frame, emotion?, x?, y?, scale?, look?, facing?, jump?, on? }:
//   x, y     where the feet stand, as fractions of the video frame; a change makes the mascot WALK there from the cue
//   on       true: walk in from the nearer edge to x, y.  false: walk off past the nearer edge.  Sticky.
//   look     up | down | left | right | none, sticky (overrides the emotion's gaze)
//   facing   left | right | front, sticky (which way it stands when not walking)
//   jump     true: one hop at this cue
// The mascot starts OFF screen: until an `on: true` cue it is not drawn (renderMascot returns null).
// No coordinate is ever 3D and nothing here is per-video code: the agent writes only this list. The mascot never speaks:
// its mouth shows the emotion only.
const FEET_Y = H - 50, BASE_U = 18, WALK_PX_PER_S = 320, EDGE_PX = W / 2 + 40;
const LOOK = { up: [0, -.9], down: [0, .8], left: [-.9, 0], right: [.9, 0] };

let TRK = null;
// Where the move in progress at time t has the feet, as frame fractions; null when no move is in progress.
function movingAt(moves, t) {
  let m = null; for (const x of moves) if (x.t0 <= t) m = x;
  if (!m || t >= m.t1) return null;
  const k = ease(seg(t, m.t0, m.t1));
  return { x: lerp(m.x0, m.x1, k), y: lerp(m.y0, m.y1, k) };
}
function compile(track) {
  const fps = track.fps, Wv = track.width, Hv = track.height;
  const cues = [...track.cues].sort((a, b) => a.frame - b.frame);
  const st = { x: .8, y: .96, scale: 1, look: 'none', facing: 'front', on: false };
  // the feet position, as a frame fraction, that puts the whole box past the nearer edge
  const edgeX = x => x < .5 ? -EDGE_PX / Wv : 1 + EDGE_PX / Wv;
  const keys = [], moves = [], jumps = [], states = [{ t: -Infinity, ...st }];
  for (const c of cues) {
    const t = c.frame / fps, prev = { ...st };
    for (const k of ['x', 'y', 'scale', 'look', 'facing', 'on']) if (c[k] !== undefined) st[k] = c[k];
    if (c.emotion) keys.push([t, c.emotion]);
    if (c.jump) jumps.push(t);
    // a new move starts from where the mascot actually is at this cue, so a cue that lands mid-walk never pops it
    const here = movingAt(moves, t);
    let x0 = null, y0 = null, x1 = st.x, y1 = st.y;
    if (st.on && !prev.on && !here) { x0 = edgeX(st.x); y0 = st.y; }       // walk in from the nearer edge
    else if (!st.on && (prev.on || here)) {                                  // walk off
      x0 = here ? here.x : prev.x; y0 = here ? here.y : prev.y; x1 = edgeX(x0); y1 = y0;
    } else if (st.on && ((!prev.on && here) || st.x !== prev.x || st.y !== prev.y)) { x0 = here ? here.x : prev.x; y0 = here ? here.y : prev.y; }
    if (x0 !== null) {
      const d = Math.hypot((x1 - x0) * Wv, (y1 - y0) * Hv);
      moves.push({ t0: t, t1: t + clamp(d / WALK_PX_PER_S, .5, 3.2), x0, y0, x1, y1, scale: st.scale });
    }
    states.push({ t, ...st });
  }
  if (!keys.length || keys[0][0] > 0) keys.unshift([0, 'neutral']);
  return { fps, Wv, Hv, keys, moves, jumps, states };
}
const stateAt = t => { let s = TRK.states[0]; for (const x of TRK.states) if (x.t <= t) s = x; return s; };
// Position + walk: the last move that has started decides where the feet are. A mascot that is off screen and not
// walking is not placed at all.
function where(t) {
  const s = stateAt(t); let m = null; for (const x of TRK.moves) if (x.t0 <= t) m = x;
  if (!m || t >= m.t1) return s.on ? { x: s.x, y: s.y, moving: false, walk: null, dir: 0 } : null;
  const k = ease(seg(t, m.t0, m.t1)), x = lerp(m.x0, m.x1, k), y = lerp(m.y0, m.y1, k);
  const dpx = Math.hypot((x - m.x0) * TRK.Wv, (y - m.y0) * TRK.Hv);
  return { x, y, moving: true, walk: dpx / (4 * BASE_U * m.scale), dir: Math.sign(m.x1 - m.x0) };
}
window.placeAt = t => {
  if (!window.TRACK) return null;
  if (!TRK) TRK = compile(window.TRACK);
  const p = where(t);
  return p && { left: p.x * TRK.Wv - W / 2, top: p.y * TRK.Hv - FEET_Y };
};
window.LOOP = t => {
  if (!window.TRACK) return; // p5 draws once right after setup, before the host has handed over the track
  if (!TRK) TRK = compile(window.TRACK);
  const p = where(t);
  if (!p) return;
  const s = stateAt(t), u = BASE_U * s.scale;
  const e = emotions(t, TRK.keys);
  let j = { dy: 0, sq: 0 }; for (const t0 of TRK.jumps) if (t >= t0 - .15 && t < t0 + 1.2) { const r = jump(t, t0, t0 + .55, 3); j = { dy: j.dy + r.dy, sq: j.sq + r.sq }; }
  const o = { ...e, dy: (e.dy || 0) + j.dy, sq: (e.sq || 0) + j.sq, boilKey: 'mascot' };
  if (p.moving) { o.walk = p.walk; o.view = 'q'; o.flip = p.dir < 0; o.dy += -Math.abs(Math.sin(p.walk * Math.PI)) * .5; }
  else if (s.facing === 'left' || s.facing === 'right') { o.view = 'q'; o.flip = s.facing === 'left'; }
  if (s.look !== 'none' && LOOK[s.look]) { o.lookX = LOOK[s.look][0]; o.lookY = LOOK[s.look][1]; o.eyes = o.eyes === 'happy' || o.eyes === 'closed' ? 'look' : o.eyes; }
  o.noShadow = true; // the sticker composite draws a plain-alpha shadow instead (see core.js composite)
  const lift = Math.min(.5, Math.abs(o.dy || 0) * .06);
  window.SHADOW = { x: W / 2, y: FEET_Y + .2 * u, rx: 5.2 * u * (1 - lift), ry: 1.1 * u * (1 - lift) };
  window.MASCOT(W / 2, FEET_Y, u, o);
};
