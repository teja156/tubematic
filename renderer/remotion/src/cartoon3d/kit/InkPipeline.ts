// The look's render pipeline, one class so a scene only has to hand it a scene,
// a camera and per-frame parameters.
//
// Order (fixed, and the reason this is hand-rolled rather than an EffectComposer):
//   1. scene  -> rtMain   (linear HDR colour + float depth texture, shadows)
//   2. scene  -> rtNormal (view-space normals; cutouts alpha-tested)      [ink]
//   3. composite: tonemap -> ink lines (depth + normals) -> colour grade,
//      writes the signed circle of confusion into alpha                   [ink, grade]
//   4. depth of field gather over the composited, inked, graded image     [dof]
// The blur reads the already-inked image, so it can soften background lines but
// can never erase the lines on the in-focus subject.
import * as THREE from "three";

export interface FxFlags {
  shadows: boolean;
  ink: boolean;
  grade: boolean;
  dof: boolean;
}

export interface Grade {
  exposure: number;
  saturation: number;
  contrast: number;
  lift: THREE.Color; // floor colour: the darkest any pixel can get
  gain: THREE.Color;
  shadowTint: THREE.Color; // multiplied into the darks (cool blue / purple)
  hiTint: THREE.Color; // multiplied into the lights (warm)
}

export interface Dof {
  focus: number; // metres
  strength: number; // blur radius (px @1080 wide) per unit of |1/z - 1/focus|*focus
  maxRadius: number; // px @1080 wide
}

// 0 = final image, 1 = ink mask with breakup, 2 = ink mask without breakup
export type DebugView = 0 | 1 | 2;

const VERT = /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const COMPOSITE = /* glsl */ `
precision highp float;
varying vec2 vUv;
uniform sampler2D tColor;
uniform sampler2D tDepth;
uniform sampler2D tNormal;
uniform vec2 texel;
uniform float near;
uniform float far;
uniform float lineScale;
uniform mat4 projInv;
uniform mat4 viewInv;
uniform vec3 inkColor;
uniform float exposure;
uniform float saturation;
uniform float contrast;
uniform vec3 lift;
uniform vec3 gain;
uniform vec3 shadowTint;
uniform vec3 hiTint;
uniform float focusInv;
uniform float cocScale;
uniform int debugView;

float invZ(vec2 uv) {
  float d = texture2D(tDepth, uv).x;
  return (far - (far - near) * d) / (near * far);
}

vec3 aces(vec3 x) {
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

float hash3(vec3 p) {
  p = fract(p * 0.3183099 + 0.1);
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x),
                 mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x),
                 mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z);
}

void main() {
  vec3 hdr = texture2D(tColor, vUv).rgb * exposure;
  // Tonemap the LUMINANCE only and keep the chroma: a per-channel filmic
  // curve bleaches every bright saturated colour toward white (the sky went
  // pale cyan, the sunlit sand cream). A cartoon wants flat saturated colour.
  float lum = dot(hdr, vec3(0.2126, 0.7152, 0.0722));
  float tl = aces(vec3(lum)).x;
  vec3 c = hdr * (tl / max(lum, 1e-4));
  // a soft per-channel clip keeps out-of-gamut colours from clipping harshly
  c = c / (1.0 + max(max(c.r, c.g), max(c.b, 1.0)) - 1.0);
  c = pow(clamp(c, 0.0, 1.0), vec3(1.0 / 2.2));
  float w0 = invZ(vUv);

#ifdef INK
  // Depth: second difference of 1/z, which is exactly zero across any plane,
  // so grazing ground and walls never produce false lines. Only the nearer
  // side of a step is marked, so silhouettes get one clean line.
  float de = 0.0;
  vec2 dirs[4];
  dirs[0] = vec2(1.0, 0.0); dirs[1] = vec2(0.0, 1.0);
  dirs[2] = vec2(0.7071, 0.7071); dirs[3] = vec2(0.7071, -0.7071);
  vec4 nc = texture2D(tNormal, vUv);
  vec3 n0 = nc.xyz * 2.0 - 1.0;
  float ne = 0.0;
  for (int i = 0; i < 4; i++) {
    vec2 o = dirs[i] * texel * lineScale;
    float a = invZ(vUv + o);
    float b = invZ(vUv - o);
    de = max(de, (2.0 * w0 - a - b) / max(w0, 1e-5));
    vec4 sa = texture2D(tNormal, vUv + o);
    vec4 sb = texture2D(tNormal, vUv - o);
    if (nc.a > 0.5 && sa.a > 0.5) ne = max(ne, 1.0 - dot(n0, sa.xyz * 2.0 - 1.0));
    if (nc.a > 0.5 && sb.a > 0.5) ne = max(ne, 1.0 - dot(n0, sb.xyz * 2.0 - 1.0));
  }
  float line = max(smoothstep(0.05, 0.16, de), smoothstep(0.22, 0.42, ne));
  if (nc.a < 0.5 && de < 0.05) line = 0.0; // sky, particles, aurora: no ink

  // World position, for a stable (non-boiling) line breakup and distance fade.
  vec4 ndc = vec4(vUv * 2.0 - 1.0, texture2D(tDepth, vUv).x * 2.0 - 1.0, 1.0);
  vec4 vp = projInv * ndc;
  vp /= vp.w;
  vec3 wp = (viewInv * vp).xyz;
  float dist = length(vp.xyz);
  float rawLine = line;
  // roughly a quarter of the edges drop out, like a hand-inked panel
  float brk = smoothstep(0.30, 0.42, vnoise(wp * 0.55));
  line *= brk;
  line *= 1.0 - 0.55 * smoothstep(25.0, 110.0, dist);
  if (debugView == 1) { gl_FragColor = vec4(vec3(line), 1.0); return; }
  if (debugView == 2) { gl_FragColor = vec4(vec3(rawLine * (1.0 - 0.55 * smoothstep(25.0, 110.0, dist))), 1.0); return; }
  c = mix(c, inkColor, line);
#endif

#ifdef GRADE
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(l), c, saturation);
  float sh = 1.0 - smoothstep(0.0, 0.6, l);
  float hi = smoothstep(0.45, 1.0, l);
  c *= mix(vec3(1.0), shadowTint, sh);
  c *= mix(vec3(1.0), hiTint, hi);
  c = (c - 0.5) * contrast + 0.5;
  c = clamp(c, 0.0, 1.0);
  c = lift + c * (gain - lift);
#endif

  // a light vignette: the frame's corners fall off ~18%, which pulls the eye
  // to the subject and reads as a finished, graded picture
  {
    vec2 q = vUv - 0.5;
    q.x *= 0.5625; // 9:16
    float vig = 1.0 - 0.18 * smoothstep(0.18, 0.62, dot(q, q) * 2.4);
    c *= vig;
  }

  // signed circle of confusion: >0.5 behind the focus plane, <0.5 in front
  float coc = clamp((focusInv - w0) * cocScale, -1.0, 1.0);
  gl_FragColor = vec4(c, 0.5 + 0.5 * coc);
}
`;

const DOF = /* glsl */ `
precision highp float;
varying vec2 vUv;
uniform sampler2D tComp;
uniform vec2 texel;
uniform float maxRadius;
const int N = 24;

void main() {
  vec4 c0 = texture2D(tComp, vUv);
  float s0 = c0.a * 2.0 - 1.0;
  float r0 = abs(s0) * maxRadius;
  vec3 acc = c0.rgb;
  float wsum = 1.0;
  // per-pixel rotation (screen-space, deterministic) hides the sample pattern
  float rot = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) * 6.2831;
  for (int i = 0; i < N; i++) {
    float t = (float(i) + 0.5) / float(N);
    float r = sqrt(t) * maxRadius;
    float a = float(i) * 2.39996 + rot;
    vec4 s = texture2D(tComp, vUv + vec2(cos(a), sin(a)) * r * texel);
    float ss = s.a * 2.0 - 1.0;
    float rs = abs(ss) * maxRadius;
    // a sample behind us may only spread as far as our own blur (no halo of
    // background over a sharp subject); a sample in front spreads by its own.
    float reach = ss > s0 ? min(rs, r0) : rs;
    float w = smoothstep(r - 1.0, r + 1.0, reach);
    acc += s.rgb * w;
    wsum += w;
  }
  gl_FragColor = vec4(acc / wsum, 1.0);
}
`;

export class InkPipeline {
  private rtMain: THREE.WebGLRenderTarget;
  private rtNormal: THREE.WebGLRenderTarget;
  private rtComp: THREE.WebGLRenderTarget;
  private normalMat = new THREE.MeshNormalMaterial({ side: THREE.DoubleSide });
  private quadScene = new THREE.Scene();
  private quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private quad: THREE.Mesh;
  private compMat: THREE.ShaderMaterial;
  private dofMat: THREE.ShaderMaterial;
  readonly width: number;
  readonly height: number;
  readonly flags: FxFlags;

  constructor(gl: THREE.WebGLRenderer, flags: FxFlags, debugView: DebugView = 0) {
    this.flags = flags;
    const size = gl.getDrawingBufferSize(new THREE.Vector2());
    this.width = size.x;
    this.height = size.y;
    gl.shadowMap.enabled = flags.shadows;
    gl.shadowMap.type = THREE.PCFShadowMap;
    const depthTexture = new THREE.DepthTexture(size.x, size.y, THREE.FloatType);
    this.rtMain = new THREE.WebGLRenderTarget(size.x, size.y, {
      type: THREE.HalfFloatType,
      depthTexture,
      depthBuffer: true,
    });
    this.rtNormal = new THREE.WebGLRenderTarget(size.x, size.y, { depthBuffer: true });
    this.rtComp = new THREE.WebGLRenderTarget(size.x, size.y, { depthBuffer: false });
    const texel = new THREE.Vector2(1 / size.x, 1 / size.y);
    const res = size.x / 1080; // effects are tuned at 1080 wide
    const defines: Record<string, string> = {};
    if (flags.ink) defines.INK = "";
    if (flags.grade) defines.GRADE = "";
    this.compMat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: COMPOSITE,
      defines,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        tColor: { value: this.rtMain.texture },
        tDepth: { value: depthTexture },
        tNormal: { value: this.rtNormal.texture },
        texel: { value: texel },
        near: { value: 0.1 },
        far: { value: 500 },
        lineScale: { value: 2.4 * res },
        projInv: { value: new THREE.Matrix4() },
        viewInv: { value: new THREE.Matrix4() },
        inkColor: { value: new THREE.Color(0.07, 0.045, 0.13) },
        exposure: { value: 1 },
        saturation: { value: 1 },
        contrast: { value: 1 },
        lift: { value: new THREE.Color(0, 0, 0) },
        gain: { value: new THREE.Color(1, 1, 1) },
        shadowTint: { value: new THREE.Color(1, 1, 1) },
        hiTint: { value: new THREE.Color(1, 1, 1) },
        focusInv: { value: 0.1 },
        cocScale: { value: 1 },
        debugView: { value: debugView },
      },
    });
    this.dofMat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: DOF,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        tComp: { value: this.rtComp.texture },
        texel: { value: texel },
        maxRadius: { value: 9 * res },
      },
    });
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.compMat);
    this.quad.frustumCulled = false;
    this.quadScene.add(this.quad);
  }

  private normalPass(gl: THREE.WebGLRenderer, scene: THREE.Scene, cam: THREE.Camera) {
    const swapped: [THREE.Mesh, THREE.Material | THREE.Material[]][] = [];
    const hidden: THREE.Object3D[] = [];
    const bg = scene.background;
    scene.background = null;
    scene.traverse((o) => {
      if (!o.visible) return;
      if (o.userData.noInk) {
        o.visible = false;
        hidden.push(o);
        return;
      }
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        swapped.push([m, m.material]);
        m.material = (o.userData.normalMaterial as THREE.Material) ?? this.normalMat;
      }
    });
    gl.setRenderTarget(this.rtNormal);
    gl.setClearColor(0x000000, 0);
    gl.clear();
    gl.render(scene, cam);
    for (const [m, mat] of swapped) m.material = mat;
    for (const o of hidden) o.visible = true;
    scene.background = bg;
  }

  render(
    gl: THREE.WebGLRenderer,
    scene: THREE.Scene,
    cam: THREE.PerspectiveCamera,
    grade: Grade,
    dof: Dof,
  ) {
    gl.autoClear = true;
    // Re-assert every frame: R3F's configure() runs on every React re-render of
    // the <Canvas> and resets shadowMap.enabled from its `shadows` prop. When it
    // went false after frame 1, every later frame in a tab silently reused the
    // first frame's shadow map (found by diffing a sequential render against
    // single stills).
    gl.shadowMap.enabled = this.flags.shadows;
    gl.shadowMap.type = THREE.PCFShadowMap;
    gl.shadowMap.autoUpdate = false;
    gl.shadowMap.needsUpdate = this.flags.shadows;
    gl.setRenderTarget(this.rtMain);
    gl.setClearColor(0x000000, 1);
    gl.render(scene, cam);
    if (this.flags.ink) this.normalPass(gl, scene, cam);

    const u = this.compMat.uniforms;
    u.near.value = cam.near;
    u.far.value = cam.far;
    u.projInv.value.copy(cam.projectionMatrixInverse);
    u.viewInv.value.copy(cam.matrixWorld);
    u.exposure.value = grade.exposure;
    u.saturation.value = grade.saturation;
    u.contrast.value = grade.contrast;
    u.lift.value.copy(grade.lift);
    u.gain.value.copy(grade.gain);
    u.shadowTint.value.copy(grade.shadowTint);
    u.hiTint.value.copy(grade.hiTint);
    u.focusInv.value = 1 / dof.focus;
    // |1/z - 1/f| * focus is the relative defocus; blur px = strength * that,
    // stored in alpha as a fraction of maxRadius.
    const res = this.width / 1080;
    const maxR = dof.maxRadius * res;
    this.dofMat.uniforms.maxRadius.value = maxR;
    u.cocScale.value = (dof.focus * dof.strength * res) / maxR;

    this.quad.material = this.compMat;
    gl.setRenderTarget(this.flags.dof ? this.rtComp : null);
    gl.render(this.quadScene, this.quadCam);
    if (this.flags.dof) {
      this.quad.material = this.dofMat;
      gl.setRenderTarget(null);
      gl.render(this.quadScene, this.quadCam);
    }
  }
}

// Normal-pass material for an alpha-tested cutout: the plane's own normal, with
// the same alpha test as its colour material, so the ink pass sees the shape.
export const cutoutNormalMaterial = (map: THREE.Texture) =>
  new THREE.ShaderMaterial({
    side: THREE.DoubleSide,
    uniforms: { map: { value: map } },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      varying vec3 vN;
      void main() {
        vUv = uv;
        vN = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform sampler2D map;
      varying vec2 vUv;
      varying vec3 vN;
      void main() {
        if (texture2D(map, vUv).a < 0.5) discard;
        vec3 n = gl_FrontFacing ? vN : -vN;
        gl_FragColor = vec4(n * 0.5 + 0.5, 1.0);
      }`,
  });
