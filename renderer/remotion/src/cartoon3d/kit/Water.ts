// WATER AS A KIT SURFACE: a flat sheet whose colour is a ramp by distance from the lens (the reference's water is a
// flat saturated vertical gradient, dark near, lighter cyan at the horizon, >= 10 L* top to bottom), that takes the
// scene's light (day cyan, golden-hour peach on the far water and a violet-blue near sheet), with sparse rounded
// crest dashes that thin toward the lens (area far 1.5-5 %, mid <= 1.6 %, near <= 0.9 %, aspect 3-6, within +-9 deg
// of the flow) and drift with the current. No ink (a water surface has no silhouette), no shadows, scene fog.
// Every water mesh shares ONE uniform block (WATER_U), which the scene sets once per frame.
import * as THREE from "three";

/** water colours decode with a softer curve than S() (2.2): measured, the chain crushes the dark end of a blue */
const WATER_GAMMA = 1.6;
const W = (hex: number) => { const c = new THREE.Color(hex); return c.setRGB(Math.pow(c.r, WATER_GAMMA), Math.pow(c.g, WATER_GAMMA), Math.pow(c.b, WATER_GAMMA)); };

export const WATER_U = {
  camPos: { value: new THREE.Vector3() },
  time: { value: 0 },
  /** 0 day .. 1 golden */
  golden: { value: 0 },
  // palettes CALIBRATED BY MEASUREMENT against the on-screen targets (LOOK-TARGETS 10: day #0c5a8c near / #1679ad
  // mid / #2a9cc8 far, crest #5fcfe6; golden from the skill's lights.ts): the v2 chain (grade, tone map, encode)
  // takes a dark saturated blue down ~20 L* and ~50 deg toward violet, so these are authored lighter and more cyan
  dayNear: { value: W(0x3c78a4) }, dayMid: { value: W(0x4a9cc0) }, dayFar: { value: W(0x66b8d0) }, dayCrest: { value: W(0x9ae6f2) },
  goldNear: { value: W(0x5660ac) }, goldMid: { value: W(0x8a86b8) }, goldFar: { value: W(0xe8b8a0) }, goldCrest: { value: W(0xf6cab0) },
};

const VERT = /* glsl */ `
#include <fog_pars_vertex>
varying vec3 vW;
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  vec4 mvPosition = viewMatrix * w;
  gl_Position = projectionMatrix * mvPosition;
  #include <fog_vertex>
}`;

const FRAG = /* glsl */ `
precision highp float;
#include <fog_pars_fragment>
varying vec3 vW;
uniform vec3 camPos;
uniform float time;
uniform float golden;
uniform vec3 dayNear, dayMid, dayFar, dayCrest, goldNear, goldMid, goldFar, goldCrest;
uniform vec2 flow;     // current, m/s in world xz
uniform float marks;   // crest density multiplier (1 = the reference)
float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
// a rounded dash: distance from p to the segment a-b, as a soft 0..1 coverage of half-width r
float dash(vec2 p, vec2 a, vec2 b, float r) {
  vec2 pa = p - a, ba = b - a;
  float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  float d = length(pa - ba * h);
  return 1.0 - smoothstep(r * 0.7, r, d);
}
void main() {
  float dist = length(vW.xz - camPos.xz);
  vec3 near = mix(dayNear, goldNear, golden), mid = mix(dayMid, goldMid, golden), far = mix(dayFar, goldFar, golden), crest = mix(dayCrest, goldCrest, golden);
  vec3 col = mix(near, mid, smoothstep(2.0, 22.0, dist));
  col = mix(col, far, smoothstep(22.0, 90.0, dist));
  // crest dashes on a grid aligned with the flow, drifting with it; sparser near the lens
  // the marks lie ACROSS the line of sight (the reference's crests are within +-9 deg of screen-horizontal in every
  // shot), and drift with the current
  vec2 toCam = normalize(camPos.xz - vW.xz);
  vec2 f = vec2(-toCam.y, toCam.x);
  vec2 q = vW.xz - flow * time;
  vec2 along = vec2(dot(q, f), dot(q, vec2(-f.y, f.x)));
  float density = mix(0.025, 0.3, smoothstep(4.0, 70.0, dist)) * marks;
  float cov = 0.0;
  for (int k = 0; k < 2; k++) {
    vec2 cell = vec2(2.4, 0.9) * (k == 0 ? 1.0 : 1.7);
    vec2 g = along / cell;
    vec2 id = floor(g), fr = fract(g);
    float r1 = h21(id + 7.0 * float(k)), r2 = h21(id + 3.3 + 7.0 * float(k)), r3 = h21(id + 9.1 + 7.0 * float(k));
    if (r1 < density) {
      float len = (0.9 + 0.6 * r2) * cell.x * 0.22;   // ~1-1.5 m long
      float tilt = (r3 - 0.5) * 0.3;              // within ~+-9 deg of the flow
      vec2 c = (id + vec2(0.5, 0.2 + 0.6 * r2)) * cell;
      vec2 a = c - vec2(len, len * tilt), b = c + vec2(len, len * tilt);
      float w = 0.11 + 0.04 * r3;                 // half-width: aspect ~4-6
      cov = max(cov, dash(along, a, b, w));
    }
  }
  col = mix(col, crest, cov * 0.95);
  gl_FragColor = vec4(col, 1.0);
  #include <fog_fragment>
}`;

export interface WaterOpts {
  /** current in m/s (world xz); crests drift with it and align to it */
  flow?: [number, number];
  /** crest density, 1 = the reference's */
  marks?: number;
}

export const makeWaterMaterial = (o: WaterOpts = {}) =>
  new THREE.ShaderMaterial({
    uniforms: { ...THREE.UniformsUtils.merge([THREE.UniformsLib.fog]), ...WATER_U, flow: { value: new THREE.Vector2(...(o.flow ?? [0.6, 0])) }, marks: { value: o.marks ?? 1 } },
    vertexShader: VERT, fragmentShader: FRAG, fog: true,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });

/** a w x d sheet of water, centred at the origin, on y = 0 (place it ~6 cm above the ground so it wins) */
export const makeWater = (w: number, d: number, o: WaterOpts = {}) => {
  const geo = new THREE.PlaneGeometry(w, d);
  geo.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(geo, makeWaterMaterial(o));
  m.userData.noInk = true;
  m.userData.water = true;
  m.receiveShadow = false;
  m.castShadow = false;
  return m;
};

/** once per frame, before the render */
export const updateWater = (cam: THREE.Camera, time: number, golden: number) => {
  WATER_U.camPos.value.copy(cam.position);
  WATER_U.time.value = time;
  WATER_U.golden.value = golden;
};
