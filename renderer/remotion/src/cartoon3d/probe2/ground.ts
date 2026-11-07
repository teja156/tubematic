// PROBE 2 — the DOM half of the terrain: the displaced ground mesh and the flat
// ground decals (ruts, puddles, trampled patches). Heights come only from
// groundSpec.ts::terrainHeight, so anything seated with that function sits on
// exactly the surface drawn here.
import * as THREE from "three";
import { makeRng, range, type Rng } from "../kit/prng";
import * as T from "../kit/textures";
import { flatDistance, terrainHeight, type TerrainSpec } from "./groundSpec";

/** Metres per ground-texture tile: the same as the old flat plane (600 m / 150). */
const TILE_M = 8; // round 4: the 1024 px dirt covers 8 m, so the repeat is not seen

/**
 * The ground. A disc centred on the world origin (where the cyclorama is
 * centred), so no corner ever pokes past the painted backdrop: the backdrop
 * writes no depth, so any land behind it would draw OVER the painting. Rings
 * are spaced densely near the middle and sparsely at the rim; angular
 * segments are fixed, so cells near the play area are well under a metre.
 *
 * Ink: the ink pass reads the depth second difference, which is zero on a
 * plane and small on a gentle curve, so smooth rolling hills draw only their
 * silhouette against the land behind them (a clean storybook ridge line).
 * Measured on the debug ink mask; see the gallery's page 4.
 */
export const makeTerrain = (
  t: TerrainSpec,
  tex: { kind: "dirt" | "cobbles" | "stone"; hue: number; sat: number; light: number; seed: number },
  extent = 490,
): THREE.Mesh => {
  const R = extent / 2;
  const RINGS = 96;
  const SEGS = 256;
  // r(u) = R (a u + (1 - a) u^3): spacing R*a/RINGS at the centre (~0.15 m)
  const a = 0.06;
  const ringR = (j: number) => {
    const u = j / RINGS;
    return R * (a * u + (1 - a) * u * u * u);
  };
  const pos: number[] = [];
  const uv: number[] = [];
  const col: number[] = [];
  const idx: number[] = [];
  const vert = (x: number, z: number) => {
    const y = terrainHeight(t, x, z);
    pos.push(x, y, z);
    uv.push(x / TILE_M, -z / TILE_M);
    // a whisper of variation: hills slightly lighter on top, the ramp foot a
    // touch darker, so rises read as land and not as a stretched texture.
    const lift = Math.min(1, y / Math.max(1, t.amp * 3));
    const foot = flatDistance(t, x, z) > 0 ? 0.04 * Math.exp(-flatDistance(t, x, z) / Math.max(1, t.edge)) : 0;
    const k = 1 - foot + 0.1 * lift;
    col.push(k, k, k * 0.98);
    return pos.length / 3 - 1;
  };
  const centre = vert(0, 0);
  const rings: number[][] = [];
  for (let j = 1; j <= RINGS; j++) {
    const r = ringR(j);
    const ring: number[] = [];
    for (let s = 0; s < SEGS; s++) {
      const th = (s / SEGS) * Math.PI * 2;
      ring.push(vert(Math.cos(th) * r, Math.sin(th) * r));
    }
    rings.push(ring);
  }
  // CCW seen from above (+y), so the faces point up
  for (let s = 0; s < SEGS; s++) idx.push(centre, rings[0][(s + 1) % SEGS], rings[0][s]);
  for (let j = 1; j < RINGS; j++) {
    const A = rings[j - 1];
    const B = rings[j];
    for (let s = 0; s < SEGS; s++) {
      const s1 = (s + 1) % SEGS;
      idx.push(A[s], A[s1], B[s]);
      idx.push(A[s1], B[s1], B[s]);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  // the flat zone must be EXACTLY up: averaging with a neighbouring ring on the
  // ramp would tilt the boundary normals a hair (invisible, but keep it exact)
  const nrm = geo.getAttribute("normal") as THREE.BufferAttribute;
  for (let i = 0; i < nrm.count; i++) {
    if (pos[i * 3 + 1] === 0 && flatDistance(t, pos[i * 3], pos[i * 3 + 2]) === 0) nrm.setXYZ(i, 0, 1, 0);
  }
  const map =
    tex.kind === "cobbles" ? T.cobbles(tex.seed) : tex.kind === "stone" ? T.stoneBlocks(tex.seed) : T.dirt(tex.seed, tex.hue, tex.sat, tex.light);
  const mat = new THREE.MeshLambertMaterial({ map, vertexColors: true });
  // Soft fog ceiling. Fully fogged far land is a flat band of fog colour that
  // reads as a sand bar under the painting (seen in the first renders). Capped
  // at ~0.3, the far hills stay a hazy darker ridge that steps into the
  // backdrop's own (fog-tinted ~35-75%) ridges. tanh keeps the near ramp of the
  // fog unchanged and saturates smoothly, so no kink line appears.
  const fogCap = { value: 0.3 };
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.fogCap = fogCap;
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <fog_pars_fragment>", "#include <fog_pars_fragment>\nuniform float fogCap;")
      .replace(
        "#include <fog_fragment>",
        `#ifdef USE_FOG
          float fogF = smoothstep( fogNear, fogFar, vFogDepth );
          float e2 = exp( -2.0 * fogF / fogCap );
          fogF = fogCap * ( 1.0 - e2 ) / ( 1.0 + e2 );
          gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogF );
        #endif`,
      );
  };
  mat.customProgramCacheKey = () => "terrain-fogcap";
  const m = new THREE.Mesh(geo, mat);
  /** tweakable per frame: m.userData.fogCap.value (0..1) */
  m.userData.fogCap = fogCap;
  m.castShadow = false;
  m.receiveShadow = true;
  m.name = "terrain";
  return m;
};

// ---------------------------------------------------------------- decals

const hsl = (h: number, s: number, l: number, a = 1) => `hsla(${h.toFixed(1)},${(s * 100).toFixed(1)}%,${(l * 100).toFixed(1)}%,${a})`;

/** A soft-edged irregular blob drawn as a stack of feathered ellipses. */
const blobCanvas = (rng: Rng, paint: (ctx: CanvasRenderingContext2D, S: number) => void) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  paint(ctx, S);
  // irregular outline: punch the alpha with soft lobes
  const mask = T.makeCanvas(S, S);
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2 + range(rng, -0.3, 0.3);
    const rr = range(rng, 0.14, 0.3) * S;
    const off = range(rng, 0.04, 0.2) * S;
    const cx = S / 2 + Math.cos(a) * off;
    const cy = S / 2 + Math.sin(a) * off * 0.8;
    const g = mask.ctx.createRadialGradient(cx, cy, 0, cx, cy, rr);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.55, "rgba(255,255,255,0.85)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    mask.ctx.fillStyle = g;
    mask.ctx.fillRect(0, 0, S, S);
  }
  ctx.globalCompositeOperation = "destination-in";
  ctx.drawImage(mask.c, 0, 0);
  ctx.globalCompositeOperation = "source-over";
  return T.toTexture(c, false);
};

const decalMat = (map: THREE.Texture, color: THREE.ColorRepresentation, opacity: number, order: number) =>
  new THREE.MeshLambertMaterial({
    map,
    color,
    transparent: true,
    opacity,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -1 - order,
    polygonOffsetUnits: -1 - order,
  });

const flatQuad = (w: number, d: number, mat: THREE.Material, x: number, z: number, yaw: number, y: number) => {
  const geo = new THREE.PlaneGeometry(w, d);
  geo.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  m.rotation.y = yaw;
  m.receiveShadow = true;
  m.castShadow = false;
  m.userData.noInk = true; // a flat decal has no silhouette to ink
  return m;
};

/** Long soft strip texture for a wheel rut: dark centre, feathered sides, broken ends. */
const rutTexture = (seed: number) => {
  const W = 64;
  const H = 512;
  const { c, ctx } = T.makeCanvas(W, H);
  const rng = makeRng(seed);
  for (let y = 0; y < H; y += 2) {
    const wob = Math.sin(y * 0.031 + seed) * 3 + Math.sin(y * 0.11) * 1.2;
    const half = W * (0.28 + 0.06 * Math.sin(y * 0.05 + seed * 2));
    const g = ctx.createLinearGradient(W / 2 + wob - half, 0, W / 2 + wob + half, 0);
    g.addColorStop(0, "rgba(255,255,255,0)");
    g.addColorStop(0.35, "rgba(255,255,255,0.9)");
    g.addColorStop(0.65, "rgba(255,255,255,0.9)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, y, W, 2);
  }
  // pebbles/clods in the groove
  for (let i = 0; i < 60; i++) {
    ctx.fillStyle = `rgba(255,255,255,${range(rng, 0.4, 0.9).toFixed(2)})`;
    ctx.beginPath();
    ctx.arc(W / 2 + range(rng, -10, 10), rng() * H, range(rng, 1, 3), 0, Math.PI * 2);
    ctx.fill();
  }
  const t = T.toTexture(c, false);
  t.wrapT = THREE.RepeatWrapping;
  return t;
};

/** Puddle water: an irregular soft blob with a pale reflection streak. */
const puddleTexture = (seed: number) =>
  blobCanvas(makeRng(seed), (ctx, S) => {
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, S, S);
    // sky reflection is lighter toward the far side, with a soft sheen streak
    const g = ctx.createLinearGradient(0, S, 0, 0);
    g.addColorStop(0, "rgba(120,120,130,1)");
    g.addColorStop(1, "rgba(255,255,255,1)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, S, S);
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.beginPath();
    ctx.ellipse(S * 0.46, S * 0.4, S * 0.22, S * 0.035, -0.2, 0, Math.PI * 2);
    ctx.fill();
  });

/** Mud rim under a puddle, and the trampled patches: a soft dark/pale blob. */
const smudgeTexture = (seed: number) =>
  blobCanvas(makeRng(seed), (ctx, S) => {
    const rng = makeRng(seed + 5);
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, S, S);
    // scuffs, so it reads as trodden earth and not as a spray-paint dot
    for (let i = 0; i < 70; i++) {
      ctx.fillStyle = hsl(0, 0, range(rng, 0.65, 1), range(rng, 0.2, 0.5));
      ctx.beginPath();
      ctx.ellipse(rng() * S, rng() * S, range(rng, 4, 18), range(rng, 2, 6), rng() * 3, 0, Math.PI * 2);
      ctx.fill();
    }
  });

export interface GroundDetail {
  ruts?: { x0: number; z0: number; x1: number; z1: number; width: number }[];
  puddles?: { x: number; z: number; r: number }[];
  worn?: { x: number; z: number; r: number }[];
}

/**
 * Flat decals just above y = 0. They lie flat, so place them only inside the
 * terrain's flat zone. All noInk, depthWrite false, polygon-offset over the
 * ground. update(fogColor, tod) tints the puddles toward the sky each frame.
 */
export const makeGroundDetail = (d: { seed: number } & GroundDetail): { group: THREE.Group; update: (fogColor: THREE.Color, tod: number) => void } => {
  const group = new THREE.Group();
  group.name = "groundDetail";
  const rng = makeRng(d.seed);

  // worn patches first (lowest), then ruts, then puddle mud, then water
  const smudges = [smudgeTexture(d.seed + 1), smudgeTexture(d.seed + 2), smudgeTexture(d.seed + 3)];
  // trampled earth: bare, packed soil showing through (pale), or scuffed and
  // damp (dark). Earth tones, never white, so they sit in any ground palette.
  const paleWorn = decalMat(smudges[0], new THREE.Color(0.74, 0.6, 0.44), 0.42, 0);
  const darkWorn = decalMat(smudges[1], new THREE.Color(0.3, 0.22, 0.18), 0.36, 0);
  const trackMat = decalMat(smudges[0], new THREE.Color(0.7, 0.56, 0.42), 0.2, 0);
  (d.worn ?? []).forEach((w, i) => {
    const pale = i % 2 === 0;
    const q = flatQuad(w.r * 2.2, w.r * 2.2 * range(rng, 0.7, 1), pale ? paleWorn : darkWorn, w.x, w.z, range(rng, 0, Math.PI), 0.004);
    group.add(q);
  });

  const rutTex = rutTexture(d.seed + 9);
  const rutMat = decalMat(rutTex, new THREE.Color(0.22, 0.15, 0.13), 0.62, 1);
  for (const r of d.ruts ?? []) {
    const dx = r.x1 - r.x0;
    const dz = r.z1 - r.z0;
    const len = Math.hypot(dx, dz);
    if (len < 1e-3) continue;
    const yaw = Math.atan2(dx, dz); // plane's local z (its "d" axis) along the run
    const px = dz / len; // perpendicular, for the two wheel tracks
    const pz = -dx / len;
    const strip = Math.max(0.12, r.width * 0.22);
    for (const side of [-0.5, 0.5]) {
      const geo = new THREE.PlaneGeometry(strip, len);
      geo.rotateX(-Math.PI / 2);
      const u = geo.getAttribute("uv") as THREE.BufferAttribute;
      for (let i = 0; i < u.count; i++) u.setY(i, (u.getY(i) * len) / 6); // texture repeats every 6 m
      const m = new THREE.Mesh(geo, rutMat);
      m.position.set((r.x0 + r.x1) / 2 + px * side * r.width, 0.006, (r.z0 + r.z1) / 2 + pz * side * r.width);
      m.rotation.y = yaw;
      m.receiveShadow = true;
      m.userData.noInk = true;
      group.add(m);
    }
    // the whole track is faintly worn to bare earth, wider than the wheels
    group.add(flatQuad(r.width * 1.6, len * 1.04, trackMat, (r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2, yaw, 0.005));
  }

  const mudMat = decalMat(smudges[2], new THREE.Color(0.2, 0.14, 0.13), 0.75, 2);
  const waterMats: THREE.MeshBasicMaterial[] = [];
  (d.puddles ?? []).forEach((p, i) => {
    const yaw = range(rng, 0, Math.PI);
    const stretch = range(rng, 0.65, 0.95);
    group.add(flatQuad(p.r * 3, p.r * 3 * stretch, mudMat, p.x, p.z, yaw, 0.007));
    const wm = new THREE.MeshBasicMaterial({
      map: puddleTexture(d.seed + 40 + i),
      transparent: true,
      opacity: 0.92,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -4,
      polygonOffsetUnits: -4,
    });
    waterMats.push(wm);
    const q = flatQuad(p.r * 2, p.r * 2 * stretch, wm, p.x, p.z, yaw, 0.008);
    q.receiveShadow = false; // basic material: unlit, the colour is the reflection
    group.add(q);
  });

  const dark = new THREE.Color(0.03, 0.035, 0.06);
  const cool = new THREE.Color(0.04, 0.11, 0.15); // water reads blue-ish whatever the sky
  const tmp = new THREE.Color();
  return {
    group,
    update: (fogColor, tod) => {
      // the puddle shows the sky: a darkened copy of the horizon colour,
      // brightest at sunset (low sun on water), dim at night
      const k = 0.2 + 0.14 * Math.exp(-((tod - 0.5) ** 2) / 0.02) + 0.1 * Math.max(0, (tod - 0.6) / 0.4);
      tmp.copy(dark).lerp(fogColor, k).lerp(cool, 0.25);
      for (const m of waterMats) m.color.copy(tmp);
    },
  };
};
