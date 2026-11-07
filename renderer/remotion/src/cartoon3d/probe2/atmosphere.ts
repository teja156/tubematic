// PROBE 2 — atmosphere: dust motes, fireflies, chimney/fire smoke, tree sway.
//
// DETERMINISM: Remotion renders frames out of order across tabs, so nothing
// here keeps state between frames. Every particle's position at frame f is
// computed from scratch: a seeded birth (hash of seed, particle, life cycle),
// a constant velocity and closed-form wobble, on a looping lifetime. Calling
// update(f) for frames 90, 12, 90 gives frame 90 twice, identically.
import * as THREE from "three";
import { clamp01, hash, lerp, smooth } from "../kit/prng";
import * as T from "../kit/textures";

const FPS = 30;
type Area = { x0: number; x1: number; z0: number; z1: number };

export interface AtmosphereOpts {
  seed: number;
  dust?: { count: number; area: Area; y: [number, number] };
  fireflies?: { count: number; area: Area; y: [number, number] };
  smoke?: { at: THREE.Vector3; kind: "chimney" | "fire" | "stack" }[];
}

/** tod keys shared with WorldScene: 0 day, 0.5 sunset, 0.8 dusk, 1 night */
const KEYS = [0, 0.5, 0.8, 1];
const num = (vals: number[], tod: number) => {
  for (let i = 0; i < KEYS.length - 1; i++) {
    if (tod <= KEYS[i + 1]) return lerp(vals[i], vals[i + 1], (tod - KEYS[i]) / (KEYS[i + 1] - KEYS[i]));
  }
  return vals[vals.length - 1];
};
const pal = (vals: [number, number, number][], tod: number, out: THREE.Color) =>
  out.setRGB(num(vals.map((v) => v[0]), tod), num(vals.map((v) => v[1]), tod), num(vals.map((v) => v[2]), tod));

/** fade a particle out as it nears the lens, so nothing blows up to a blob */
const nearFade = (p: THREE.Vector3, cam: THREE.Camera, near: number, far: number) =>
  smooth((p.distanceTo(cam.position) - near) / (far - near));

/** A glow point: tight bright core inside a wide soft halo. */
const glowTexture = (core: string, halo: string) => {
  const S = 128;
  const { c, ctx } = T.makeCanvas(S, S);
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, core);
  g.addColorStop(0.1, core);
  g.addColorStop(0.22, halo);
  g.addColorStop(0.5, halo.replace(/[\d.]+\)$/, "0.08)"));
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return T.toTexture(c, false);
};

/** A lumpy smoke puff: overlapping soft blobs, never a perfect disc. */
const puffTexture = (seed: number) => {
  const S = 128;
  const { c, ctx } = T.makeCanvas(S, S);
  for (let i = 0; i < 7; i++) {
    const a = hash(seed, i, 1) * Math.PI * 2;
    const off = (i === 0 ? 0 : 0.12 + 0.12 * hash(seed, i, 2)) * S;
    const r = (0.2 + 0.14 * hash(seed, i, 3)) * S;
    const cx = S / 2 + Math.cos(a) * off;
    const cy = S / 2 + Math.sin(a) * off;
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, "rgba(255,255,255,0.55)");
    g.addColorStop(0.6, "rgba(255,255,255,0.25)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, S, S);
  }
  return T.toTexture(c, false);
};

const pointsLayer = (count: number, size: number, map: THREE.Texture) => {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  const mat = new THREE.PointsMaterial({
    size,
    map,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    // additive points under fog would ADD the fog colour; keep them out of it
    fog: false,
    sizeAttenuation: true,
  });
  const pts = new THREE.Points(geo, mat);
  pts.frustumCulled = false;
  pts.userData.noInk = true;
  pts.renderOrder = 2;
  return pts;
};

export const makeAtmosphere = (
  o: AtmosphereOpts,
): { group: THREE.Group; update: (f: number, tod: number, camera: THREE.Camera) => void } => {
  const group = new THREE.Group();
  group.name = "atmosphere";
  const updaters: ((f: number, tod: number, cam: THREE.Camera) => void)[] = [];
  const p = new THREE.Vector3();
  const tint = new THREE.Color();

  // ---------------------------------------------------------------- dust
  if (o.dust && o.dust.count > 0) {
    const { count, area, y } = o.dust;
    const pts = pointsLayer(count, 0.055, glowTexture("rgba(255,255,255,1)", "rgba(255,255,255,0.3)"));
    group.add(pts);
    const pos = pts.geometry.getAttribute("position") as THREE.BufferAttribute;
    const col = pts.geometry.getAttribute("color") as THREE.BufferAttribute;
    const S = o.seed * 7 + 1;
    updaters.push((f, tod, cam) => {
      const t = f / FPS;
      // catches the light: brightest against a low sun, gone in the dark
      const vis = num([0.55, 0.9, 0.35, 0], tod);
      pal([[1.0, 0.92, 0.78], [1.0, 0.78, 0.5], [0.75, 0.7, 0.95], [0.5, 0.55, 0.8]], tod, tint);
      for (let i = 0; i < count; i++) {
        const life = 7 + 6 * hash(S, i, 1); // seconds
        const ph = hash(S, i, 2) * life;
        const cyc = Math.floor((t + ph) / life);
        const age = (t + ph) / life - cyc; // 0..1 within this life
        const tl = age * life;
        // birth point is re-drawn for every life cycle, so the field never repeats visibly
        const bx = lerp(area.x0, area.x1, hash(S, i, cyc, 3));
        const bz = lerp(area.z0, area.z1, hash(S, i, cyc, 4));
        const by = lerp(y[0], y[1], hash(S, i, cyc, 5));
        const vx = 0.12 + 0.1 * hash(S, i, 6);
        const vy = 0.035 * (hash(S, i, 7) - 0.4);
        const vz = 0.08 * (hash(S, i, 8) - 0.5);
        const w = 0.8 + 0.8 * hash(S, i, 9);
        p.set(
          bx + vx * tl + 0.12 * Math.sin(w * t + 6.28 * hash(S, i, 10)),
          by + vy * tl + 0.08 * Math.sin(0.7 * w * t + 6.28 * hash(S, i, 11)),
          bz + vz * tl + 0.12 * Math.cos(0.9 * w * t + 6.28 * hash(S, i, 12)),
        );
        pos.setXYZ(i, p.x, p.y, p.z);
        const env = Math.sin(Math.PI * age) ** 2;
        // a mote flashes as it tumbles through the light
        const glint = 0.35 + 0.65 * Math.max(0, Math.sin(t * (1.5 + 2 * hash(S, i, 13)) + 6.28 * hash(S, i, 14))) ** 6;
        const b = vis * env * glint * nearFade(p, cam, 0.5, 1.6) * 1.8;
        col.setXYZ(i, tint.r * b, tint.g * b, tint.b * b);
      }
      pos.needsUpdate = true;
      col.needsUpdate = true;
      pts.visible = vis > 0.001;
    });
  }

  // ---------------------------------------------------------------- fireflies
  if (o.fireflies && o.fireflies.count > 0) {
    const { count, area, y } = o.fireflies;
    const pts = pointsLayer(count, 0.34, glowTexture("rgba(255,255,235,1)", "rgba(255,220,120,0.3)"));
    group.add(pts);
    const pos = pts.geometry.getAttribute("position") as THREE.BufferAttribute;
    const col = pts.geometry.getAttribute("color") as THREE.BufferAttribute;
    const S = o.seed * 13 + 5;
    updaters.push((f, tod, cam) => {
      const t = f / FPS;
      const vis = smooth((tod - 0.6) / 0.25);
      pts.visible = vis > 0.001;
      if (!pts.visible) return;
      for (let i = 0; i < count; i++) {
        const hx = lerp(area.x0, area.x1, hash(S, i, 1));
        const hz = lerp(area.z0, area.z1, hash(S, i, 2));
        const hy = lerp(y[0], y[1], hash(S, i, 3));
        const w = 0.25 + 0.3 * hash(S, i, 4);
        const q = (k: number) => 6.28 * hash(S, i, k);
        // a slow lazy meander around a home point (bounded, closed form)
        p.set(
          hx + 0.9 * Math.sin(w * t + q(5)) + 0.35 * Math.sin(2.3 * w * t + q(6)),
          hy + 0.3 * Math.sin(1.7 * w * t + q(7)) + 0.12 * Math.sin(3.1 * w * t + q(8)),
          hz + 0.9 * Math.cos(0.8 * w * t + q(9)) + 0.35 * Math.sin(1.9 * w * t + q(10)),
        );
        pos.setXYZ(i, p.x, p.y, p.z);
        // blink: a soft half-second swell, then dark for a few seconds
        const per = 2.4 + 2.8 * hash(S, i, 11);
        const ph = ((t + per * hash(S, i, 12)) / per) % 1;
        const on = 0.9 / per;
        const pulse = ph < on ? Math.sin((Math.PI * ph) / on) ** 2 : 0;
        const b = vis * (0.07 + 1.6 * pulse) * nearFade(p, cam, 0.6, 2.0);
        col.setXYZ(i, 1.0 * b, 0.86 * b, 0.42 * b);
      }
      pos.needsUpdate = true;
      col.needsUpdate = true;
    });
  }

  // ---------------------------------------------------------------- smoke
  const puffTexs = [puffTexture(o.seed + 101), puffTexture(o.seed + 102), puffTexture(o.seed + 103)];
  (o.smoke ?? []).forEach((em, e) => {
    const fire = em.kind === "fire";
    // a locomotive stack: a fat dark plume, the story prop of a railway shot
    const stack = em.kind === "stack";
    const N = fire ? 22 : stack ? 44 : 16;
    const life = fire ? 4.2 : stack ? 6.5 : 7.5; // seconds
    const rise = fire ? 0.85 : stack ? 1.7 : 0.5; // m/s
    const size0 = fire ? 0.35 : stack ? 0.9 : 0.22;
    const size1 = fire ? 1.9 : stack ? 5.5 : 2.1;
    const peak = fire ? 0.4 : stack ? 0.85 : 0.24;
    const S = o.seed * 31 + e * 101 + 17;
    // a gentle steady wind, same for every emitter in one world
    const windA = hash(o.seed, 77) * Math.PI * 2;
    const wind = new THREE.Vector3(Math.cos(windA), 0, Math.sin(windA)).multiplyScalar(fire ? 0.28 : 0.38);
    const sprites: THREE.Sprite[] = [];
    for (let i = 0; i < N; i++) {
      const m = new THREE.SpriteMaterial({ map: puffTexs[i % 3], transparent: true, depthWrite: false, fog: true });
      const s = new THREE.Sprite(m);
      s.userData.noInk = true;
      s.frustumCulled = false;
      s.renderOrder = 3;
      sprites.push(s);
      group.add(s);
    }
    const grey = new THREE.Color();
    const warm = new THREE.Color();
    updaters.push((f, tod, cam) => {
      const t = f / FPS;
      pal([[0.8, 0.78, 0.78], [0.8, 0.62, 0.58], [0.34, 0.31, 0.43], [0.12, 0.125, 0.18]], tod, grey);
      if (stack) grey.multiplyScalar(0.45);
      // the fire's own light: pale in daylight, glowing after dark
      const glow = 0.7 + 1.2 * smooth((tod - 0.45) / 0.4);
      warm.setRGB(1.0 * glow, 0.5 * glow, 0.18 * glow);
      for (let i = 0; i < N; i++) {
        const s = sprites[i];
        const tt = t + (i / N) * life; // evenly staggered births
        const cyc = Math.floor(tt / life);
        const a = tt / life - cyc; // age 0..1
        const ta = a * life;
        const j = (k: number) => hash(S, i, cyc, k) - 0.5;
        // rises, slows, and leans downwind as it climbs
        const up = rise * ta * (1 - 0.25 * a);
        const lean = a * a * life;
        p.set(
          em.at.x + j(1) * (fire ? 0.35 : 0.1) + wind.x * lean + 0.18 * a * Math.sin(1.3 * t + 6.28 * j(2)),
          em.at.y + up,
          em.at.z + j(3) * (fire ? 0.35 : 0.1) + wind.z * lean + 0.18 * a * Math.cos(1.1 * t + 6.28 * j(4)),
        );
        s.position.copy(p);
        const sz = lerp(size0, size1, Math.sqrt(a)) * (0.85 + 0.3 * (j(5) + 0.5));
        s.scale.set(sz, sz, 1);
        const m = s.material;
        m.rotation = 6.28 * j(6) + (j(7) > 0 ? 1 : -1) * 0.25 * ta;
        const env = smooth(a / 0.12) * Math.pow(1 - a, 1.4);
        m.opacity = peak * env * nearFade(p, cam, 0.8, 2.5);
        if (fire) m.color.copy(warm).lerp(grey, smooth(a / 0.35));
        else m.color.copy(grey);
      }
    });
  });

  return {
    group,
    update: (f, tod, camera) => {
      for (const u of updaters) u(f, clamp01(tod), camera);
    },
  };
};

/**
 * Gentle canopy sway for trees built by kit/geometry.ts::tree() (or any
 * group whose children stand on its origin). Each child pivots about the
 * tree's base by an angle that grows with its height, so the trunk barely
 * leans and the crown moves a degree or two. Per-tree phase and period; slow.
 * Returns a function of the frame number only (no state).
 */
export const makeSway = (trees: THREE.Object3D[], seed: number): ((f: number) => void) => {
  const rec = trees.map((tr, ti) => {
    const kids = tr.children.map((c) => ({ c, pos: c.position.clone(), rot: c.rotation.clone() }));
    const top = Math.max(1e-3, ...kids.map((k) => k.pos.y));
    return {
      kids,
      top,
      amp: THREE.MathUtils.degToRad(1.1 + 0.8 * hash(seed, ti, 1)),
      per: 4.5 + 2.5 * hash(seed, ti, 2), // seconds
      ph: 6.28 * hash(seed, ti, 3),
    };
  });
  const e = new THREE.Euler();
  const q = new THREE.Quaternion();
  const v = new THREE.Vector3();
  return (f: number) => {
    const t = f / FPS;
    rec.forEach((r, ti) => {
      const w = (2 * Math.PI) / r.per;
      // mostly along the wind (x), a little across it
      const ax = r.amp * (0.75 * Math.sin(w * t + r.ph) + 0.25 * Math.sin(2.7 * w * t + 1.3 * r.ph));
      const az = 0.35 * r.amp * Math.sin(0.8 * w * t + r.ph + 1.7);
      r.kids.forEach((k, ki) => {
        const h = clamp01(k.pos.y / r.top);
        const lag = h * h; // the crown moves, the trunk barely leans
        // each blob flutters a hair on its own
        const flut = r.amp * 0.18 * Math.sin(2.2 * w * t + 6.28 * hash(seed, ti, ki, 4));
        e.set(az * lag + flut, 0, -ax * lag);
        q.setFromEuler(e);
        v.copy(k.pos).applyQuaternion(q);
        k.c.position.copy(v);
        k.c.rotation.set(k.rot.x + e.x, k.rot.y, k.rot.z + e.z);
      });
    });
  };
};
