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

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n1(float x) { float i = floor(x); float f = fract(x); f = f*f*(3.0-2.0*f); return mix(h21(vec2(i, 0.0)), h21(vec2(i + 1.0, 0.0)), f); }
float n2(vec2 p) {
  vec2 i = floor(p); vec2 f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(h21(i), h21(i + vec2(1,0)), f.x), mix(h21(i + vec2(0,1)), h21(i + vec2(1,1)), f.x), f.y);
}

void main() {
  vec3 d = normalize(vDir);
  float el = d.y;
  vec3 col = el > 0.0
    ? mix(horizon, zenith, pow(clamp(el, 0.0, 1.0), 0.55))
    : mix(horizon, ground, clamp(-el * 6.0, 0.0, 1.0));

  // painted cloud bands near the horizon
  float az = atan(d.x, -d.z);
  float band = n2(vec2(az * 3.0, el * 18.0)) * smoothstep(0.02, 0.10, el) * (1.0 - smoothstep(0.18, 0.32, el));
  col = mix(col, cloudColor, smoothstep(0.55, 0.75, band) * 0.75);

  // sun
  float sd = dot(d, normalize(sunDir));
  col += sunColor * (smoothstep(1.0 - sunSize, 1.0 - sunSize * 0.6, sd) * 6.0 + pow(max(sd, 0.0), 24.0) * 0.8);

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
