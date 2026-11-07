// Sky dome: gradient, sun disc, painted cloud bands, stars and aurora curtains,
// all driven by uniforms (no clock: `time` is set from the Remotion frame).
import * as THREE from "three";

const FRAG = /* glsl */ `
precision highp float;
varying vec3 vDir;
uniform vec3 zenith;
uniform vec3 horizon;
uniform vec3 ground;
uniform vec3 sunDir;
uniform vec3 sunColor;
uniform float sunSize;
uniform float stars;
uniform float aurora;
uniform float time;
uniform vec3 cloudColor;
uniform vec3 cloudShade;
uniform float cloudAmount;
uniform vec3 stopCol[6];   // the sky by elevation: six colour stops (look.ts skyStops)
uniform float stopEl[6];   // their elevations as sin(deg)
uniform float sunGlow;
uniform vec3 fogCol;     // a beat's own fog greys the sky too, most at the horizon
uniform float skyFog;

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n1(float x) { float i = floor(x); float f = fract(x); f = f*f*(3.0-2.0*f); return mix(h21(vec2(i, 0.0)), h21(vec2(i + 1.0, 0.0)), f); }
float n2(vec2 p) {
  vec2 i = floor(p); vec2 f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(h21(i), h21(i + vec2(1,0)), f.x), mix(h21(i + vec2(0,1)), h21(i + vec2(1,1)), f.x), f.y);
}
float fbm(vec2 p) {
  float a = 0.5, s = 0.0;
  for (int i = 0; i < 5; i++) { s += a * n2(p); p = p * 2.03 + vec2(13.1, 7.7); a *= 0.5; }
  return s;
}
// Cartoon cumulus: a flat cloud layer seen in perspective, thresholded to a
// crisp edge, with a bright puffy core and a shaded underside (the part of
// each cloud nearer the horizon). Returns coverage in x, "lit-ness" in y.
vec2 cumulus(vec3 d, float el) {
  if (el < 0.01) return vec2(0.0);
  // project onto a plane at height 1: distant clouds crowd the horizon
  vec2 p = d.xz / max(el, 0.06);
  p *= 0.32;
  p += vec2(time * 0.003, 0.0);
  float clump = n2(p * 0.35 + 3.0);
  float v = fbm(p) * 0.62 + clump * 0.5;
  float thr = 0.80 - 0.2 * cloudAmount;
  float cov = smoothstep(thr, thr + 0.03, v);
  // the underside: sample a little further OUT on the plane (lower in the
  // sky). Where the field is denser there, this point is the cloud's base.
  float lower = fbm(p * 1.045) * 0.62 + n2(p * 1.045 * 0.35 + 3.0) * 0.5;
  float core = smoothstep(thr, thr + 0.14, v);
  float under = smoothstep(-0.015, 0.025, lower - v);
  float lit = clamp(0.25 + 0.75 * core - 0.7 * under, 0.0, 1.0);
  // fade into the horizon haze and above ~45 deg elevation
  cov *= smoothstep(0.012, 0.07, el) * (1.0 - smoothstep(0.6, 0.9, el));
  return vec2(cov, lit);
}

void main() {
  vec3 d = normalize(vDir);
  float el = d.y;
  vec3 col;
  if (el > 0.0) {
    col = stopCol[5];
    for (int i = 0; i < 5; i++) {
      if (el >= stopEl[i] && el < stopEl[i + 1]) col = mix(stopCol[i], stopCol[i + 1], (el - stopEl[i]) / (stopEl[i + 1] - stopEl[i]));
    }
  } else col = mix(horizon, ground, clamp(-el * 6.0, 0.0, 1.0));

  // a thin haze band right on the horizon
  float az = atan(d.x, -d.z);
  float band = n2(vec2(az * 3.0, el * 18.0)) * smoothstep(0.0, 0.05, el) * (1.0 - smoothstep(0.08, 0.16, el));
  col = mix(col, mix(horizon, cloudColor, 0.5), smoothstep(0.5, 0.8, band) * 0.5);
  // cartoon cumulus
  vec2 cu = cumulus(d, el);
  vec3 cloudCol = mix(cloudShade, cloudColor, cu.y);
  col = mix(col, cloudCol, cu.x * 0.96);

  // sun
  float sd = dot(d, normalize(sunDir));
  col += sunColor * (smoothstep(1.0 - sunSize, 1.0 - sunSize * 0.6, sd) * 6.0 + pow(max(sd, 0.0), 90.0) * 0.5 + pow(max(sd, 0.0), 14.0) * sunGlow * 0.45);

  // stars
  vec2 sp = vec2(az * 120.0, el * 120.0);
  float s = step(0.985, h21(floor(sp))) * smoothstep(0.05, 0.3, el);
  col += vec3(0.9, 0.95, 1.0) * s * stars * (0.5 + 0.5 * h21(floor(sp) + 3.0));

  // aurora: three curtain layers with folds and vertical rays
  if (aurora > 0.001 && el > 0.0) {
    vec3 acc = vec3(0.0);
    for (int k = 0; k < 3; k++) {
      float fk = float(k);
      // each curtain's lower edge snakes across the sky
      float base = 0.12 + 0.11 * fk + 0.07 * sin(az * (1.6 + fk * 0.7) + time * (0.22 + 0.08 * fk) + fk * 2.1)
                 + 0.035 * sin(az * 5.0 - time * 0.5 + fk * 3.0);
      float h = el - base;
      float body = smoothstep(-0.012, 0.006, h) * exp(-max(h, 0.0) * (11.0 - 2.0 * fk));
      float rays = pow(n1(az * (70.0 + fk * 25.0) + time * (1.0 + fk * 0.4) + fk * 9.0), 1.6);
      // ribbons: only some stretches of azimuth carry a curtain
      float ribbon = smoothstep(0.35, 0.75, n1(az * (2.2 + fk) + time * 0.15 + fk * 5.0));
      float fold = 0.35 + 0.65 * pow(0.5 + 0.5 * sin(az * (11.0 + fk * 3.0) + time * 0.7 + n1(az * 4.0 + time * 0.2) * 3.0), 2.0);
      float strength = body * (0.25 + 0.75 * rays) * fold * ribbon;
      vec3 green = vec3(0.12, 1.0, 0.42);
      vec3 red = vec3(1.0, 0.12, 0.35);
      vec3 magenta = vec3(0.8, 0.15, 1.0);
      vec3 c = mix(green, mix(magenta, red, fk / 2.0), smoothstep(0.0, 0.12, h));
      acc += c * strength * (k == 0 ? 1.4 : 1.0);
    }
    col += acc * aurora * 1.3;
  }
  col = mix(col, fogCol, skyFog * (1.0 - smoothstep(0.0, 0.5, el)));
  gl_FragColor = vec4(col, 1.0);
}
`;

export const makeSky = () => {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: {
      zenith: { value: new THREE.Color() },
      horizon: { value: new THREE.Color() },
      ground: { value: new THREE.Color() },
      sunDir: { value: new THREE.Vector3(-1, 0.2, 0) },
      sunColor: { value: new THREE.Color() },
      sunSize: { value: 0.0015 },
      stars: { value: 0 },
      aurora: { value: 0 },
      time: { value: 0 },
      cloudColor: { value: new THREE.Color() },
      cloudShade: { value: new THREE.Color() },
      cloudAmount: { value: 0.5 },
      stopCol: { value: Array.from({ length: 6 }, () => new THREE.Color()) },
      stopEl: { value: [0, 4, 10, 20, 40, 90].map((d) => Math.sin((d * Math.PI) / 180)) },
      sunGlow: { value: 0.5 },
      fogCol: { value: new THREE.Color() },
      skyFog: { value: 0 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = position;
        vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_Position = p.xyww; // always at the far plane
      }`,
    fragmentShader: FRAG,
  });
  const sky = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), mat);
  sky.userData.noInk = true;
  sky.frustumCulled = false;
  sky.renderOrder = -1;
  return { sky, uniforms: mat.uniforms };
};
