// Ink outlines for the 3D world, matched to the reference measurements (references/reports/outlines.md recipe,
// post-agent changes: widths scale with the output height (pxScale = height / 1920, so 5.1 px at 1080x1920 is
// 6.8 px at 1440x2560), RMAX 9 for headroom at 1440, fog-tinted ink (scene.fog, x0.3), `noInkFallback` below.
// Round 2: widths x1.5 (5.1 -> 3.3 px from 6 to 90 m), pure near-black #030303, far opacity 0.95, depth jumps from 1 %.
//
// How it works
//  1. Re-render the WORLD ONLY (camera layer 0) into a non-MSAA target: view-space normal (rgb), coverage (a) and
//     a depth texture. Character billboards, effect cards, sky, clouds and smoke live on layer NOINK, so they never
//     get rectangle outlines and never cut holes into the world's lines.
//  2. Edge mask (full resolution), pixel steps 1..6 along x, y and both diagonals:
//       depth  - signed 2nd difference of 1/z (exactly 0 on any plane, so no grazing-angle false lines) -> only the
//                NEAR side of a depth jump is inked, as a band `width` px wide (silhouettes vs sky, object vs object,
//                thin ropes become solid lines like the reference);
//       crease - normal angle > ~50 deg to a neighbour at the same depth, two-sided band ~0.64*width px wide,
//                concave folds (object meets ground, inner corners) at 0.7 strength;
//       coverage is continuous in the width (no width popping when the camera moves), width shrinks a little with
//       distance (3.4 px at 6 m -> 2.2 px at 90 m, log-distance), opacity to 0.75, fades out by 450 m;
//       no ink where the main depth buffer has something nearer than the world (characters / cards in front).
//  3. Composite: 3x3 tent-filtered mask (anti-aliasing), near-black ink blended in display gamma (like Canvas2D),
//     written back into the input buffer (colour only; the composer's depth texture stays intact).
//     This is a Pass (not an Effect), so R3F's <EffectComposer> keeps it as its own pass BEFORE the merged
//     DOF + Bloom + ToneMapping EffectPass: the depth of field then blurs the lines together with the background.
// Verified in a toy scene with this exact stack (MSAA 4, HalfFloat, DOF/Bloom/Neutral): compiles, no GL errors,
// measured EW 3.7 / 3.2 / 2.6 / 1.5 / 1.1 px at 3 / 12 / 25 / 90 / 200 m (silhouettes) and 2.3 -> 0.9 px (creases).
import * as THREE from "three";
import { Pass } from "postprocessing";

/** Layer for things that must never be outlined (camera-facing sprites, sky, clouds, smoke). */
export const NOINK = 3;

export type InkOptions = {
  color?: THREE.ColorRepresentation; // sRGB hex of the ink
  strength?: number; // max opacity
  widthNear?: number; // silhouette / depth-jump line width in px at distNear (1080x1920 output)
  widthFar?: number; // ... at distFar
  distNear?: number; // m
  distFar?: number; // m
  creaseScale?: number; // crease line width / silhouette line width
  depthLo?: number; // relative depth jump (1 - z_near / z_far) where lines start
  depthHi?: number; // ... where they are full strength
  angleLo?: number; // crease angle (deg) where lines start
  angleHi?: number; // ... where they are full strength
  concaveGain?: number; // strength of concave folds (object meets ground, inner corners)
  farOpacity?: number; // opacity multiplier reached at distFar
  fadeNear?: number; // m: start of the far fade-out
  fadeFar?: number; // m: lines gone
};

const DEF: Required<InkOptions> = {
  // round 2 (reviewer: "world outlines ~1.5x thicker, pure black on every silhouette"): widths x1.5 (creases follow
  // via creaseScale), pure near-black, far opacity 0.75 -> 0.95; fog tint of the ink 0.6 -> 0.3 (compMat fogInk)
  color: "#030303", strength: 1.0,
  widthNear: 5.1, widthFar: 3.3, distNear: 6, distFar: 90, creaseScale: 0.8, // round 3: creases 0.64 -> 0.8 (building corners)
  depthLo: 0.01, depthHi: 0.03, angleLo: 35, angleHi: 50, concaveGain: 0.7, // depth jumps from 1 %; creases from 35 deg (roof eaves)
  farOpacity: 0.95, fadeNear: 150, fadeFar: 450,
};

const FS_VERT = /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

// world-only normal pass (scene.overrideMaterial); works for Mesh and InstancedMesh. Cut-out materials
// (map + alphaTest, e.g. the sign board, the church clock) keep their shape: see onBeforeRender in the constructor.
const NORMAL_VERT = /* glsl */ `
#include <common>
uniform mat3 cutUv;
varying vec3 vN;
varying vec3 vV;
varying vec2 vCut;
void main() {
  #include <beginnormal_vertex>
  #include <defaultnormal_vertex>
  vN = transformedNormal;
  vCut = (cutUv * vec3(uv, 1.0)).xy;
  #include <begin_vertex>
  #include <project_vertex>
  vV = mvPosition.xyz;
}`;
const NORMAL_FRAG = /* glsl */ `
uniform sampler2D tCut;
uniform float cut;
varying vec3 vN;
varying vec3 vV;
varying vec2 vCut;
void main() {
  if (cut > 0.0 && texture2D(tCut, vCut).a < cut) discard;
  vec3 n;
  if (dot(vN, vN) < 1e-8) n = normalize(cross(dFdx(vV), dFdy(vV)));   // geometry without normals
  else n = normalize(vN) * (gl_FrontFacing ? 1.0 : -1.0);            // back faces of double-sided planes
  gl_FragColor = vec4(n, 1.0);
}`;

const MASK_FRAG = /* glsl */ `
#include <packing>
uniform sampler2D tNormal;
uniform sampler2D tDepth;
uniform sampler2D tMainDepth;
uniform vec2 texel;
uniform float cNear;
uniform float cFar;
uniform float p00;
uniform float p11;
uniform float wNear;
uniform float wFar;
uniform float dNear;
uniform float dFar;
uniform float creaseScale;
uniform float depthLo;
uniform float depthHi;
uniform float cosLo;
uniform float cosHi;
uniform float concaveGain;
uniform float farOpacity;
uniform float fadeNear;
uniform float fadeFar;
uniform float strength;
uniform float useMain;
uniform float pxScale;   // output px per 1080x1920 px
uniform vec2 fogRange;   // scene fog near / far (m); far <= near = no fog tint
uniform float fogStart;  // ink stays pure black up to here (m), then tints toward the fog colour
varying vec2 vUv;

// pixel steps along x, y and both diagonals, and their length in px
const vec2 STEP[4] = vec2[4](vec2(1.0, 0.0), vec2(0.0, 1.0), vec2(1.0, 1.0), vec2(1.0, -1.0));
const float SLEN[4] = float[4](1.0, 1.0, 1.41421, 1.41421);
#define RMAX 9   // covers 5.1 px x pxScale 1.333 = 6.8 px at 1440x2560 (+0.5 AA ramp)

// textureLod: explicit LOD inside loops (nearest-filtered targets, no derivatives needed)
float dist(sampler2D t, vec2 uv) { return -perspectiveDepthToViewZ(textureLod(t, uv, 0.0).x, cNear, cFar); }
vec3 viewPos(vec2 uv, float d) { vec2 n = uv * 2.0 - 1.0; return vec3(n.x * d / p00, n.y * d / p11, -d); }

// crease strength between this pixel (n0, P0) and a neighbour
float crease(vec3 n0, vec3 P0, float zc, vec2 uq, float zq) {
  vec4 nq = textureLod(tNormal, uq, 0.0);
  if (nq.a < 0.5 || abs(zq - zc) > zc * depthLo) return 0.0;       // sky / depth jump: not a crease
  float k = 1.0 - smoothstep(cosHi, cosLo, dot(n0, nq.xyz));
  if (dot(viewPos(uq, zq) - P0, n0) > 0.0) k *= concaveGain;        // neighbour in front of our tangent plane: concave
  return k;
}

void main() {
  vec4 nc = textureLod(tNormal, vUv, 0.0);
  if (nc.a < 0.5) { gl_FragColor = vec4(0.0); return; }          // sky / empty: ink lives on the near object only
  float zc = dist(tDepth, vUv);

  // characters, cards etc. (not in the world buffer) in front of this pixel: no world ink over them
  if (useMain > 0.5) {
    float zm = dist(tMainDepth, vUv);
    zm = min(zm, dist(tMainDepth, vUv + vec2(texel.x, 0.0)));
    zm = min(zm, dist(tMainDepth, vUv - vec2(texel.x, 0.0)));
    zm = min(zm, dist(tMainDepth, vUv + vec2(0.0, texel.y)));
    zm = min(zm, dist(tMainDepth, vUv - vec2(0.0, texel.y)));
    if (zm < zc * 0.985 - 0.03) { gl_FragColor = vec4(0.0); return; }
  }

  float t = clamp(log(zc / dNear) / log(dFar / dNear), 0.0, 1.0);
  float w = mix(wNear, wFar, t) * pxScale;           // silhouette line width (output px) at this distance, near side only
  float hc = 0.5 * w * creaseScale;                  // crease line half width (px), drawn on both faces
  float Wc = 1.0 / zc;
  vec3 n0 = nc.xyz;
  vec3 P0 = viewPos(vUv, zc);
  float eD = 0.0, eN = 0.0;
  for (int a = 0; a < 4; a++) {
    for (int r = 1; r <= RMAX; r++) {
      vec2 o = STEP[a] * texel * float(r);
      float d = (float(r) - 0.5) * SLEN[a];          // distance of this pixel's centre to an edge first seen at r
      float cw = clamp(w + 0.5 - d, 0.0, 1.0);       // continuous coverage -> no width popping, built-in AA
      float ch = clamp(hc + 0.5 - d, 0.0, 1.0);
      if (cw <= 0.0 && ch <= 0.0) break;
      float z1 = dist(tDepth, vUv - o), z2 = dist(tDepth, vUv + o);
      // depth jump: this pixel is in front of its neighbours (2nd difference of 1/z < 0; exactly 0 on planes)
      float s = (1.0 / z1 + 1.0 / z2 - 2.0 * Wc) / Wc;
      eD = max(eD, smoothstep(depthLo, depthHi, -s) * cw);
      // crease: normal turns towards a neighbour at the same depth
      if (ch > 0.0) eN = max(eN, max(crease(n0, P0, zc, vUv - o, z1), crease(n0, P0, zc, vUv + o, z2)) * ch);
    }
  }

  float ink = max(eD, eN) * strength * mix(1.0, farOpacity, t) * (1.0 - smoothstep(fadeNear, fadeFar, zc));
  float f0 = max(fogRange.x, fogStart);
  float fogK = fogRange.y > f0 ? clamp((zc - f0) / (fogRange.y - f0), 0.0, 1.0) : 0.0;
  gl_FragColor = vec4(ink, fogK, 0.0, 1.0);
}`;

const COMP_FRAG = /* glsl */ `
uniform sampler2D inputBuffer;
uniform sampler2D tMask;
uniform sampler2D tNormal;
uniform vec2 texel;
uniform vec3 inkColor;
uniform vec3 fogColor;
uniform float fogInk;   // how far fully fogged ink moves toward the fog colour (0.3)
uniform int debug;
varying vec2 vUv;
float m(float x, float y) { return texture2D(tMask, vUv + vec2(x, y) * texel).r; }
void main() {
  float a = (4.0 * m(0.0, 0.0)
    + 2.0 * (m(1.0, 0.0) + m(-1.0, 0.0) + m(0.0, 1.0) + m(0.0, -1.0))
    + m(1.0, 1.0) + m(-1.0, 1.0) + m(1.0, -1.0) + m(-1.0, -1.0)) / 16.0;   // 1-2-1 tent = anti-aliasing
  vec4 c = texture2D(inputBuffer, vUv);
  if (debug == 1) { gl_FragColor = vec4(vec3(1.0 - a), 1.0); return; }               // mask only
  if (debug == 2) { gl_FragColor = vec4(texture2D(tNormal, vUv).xyz * 0.5 + 0.5, 1.0); return; } // world normals
  // blend in display (gamma) space like Canvas2D does for the character drawings: coverage -> darkness is linear
  // on screen, so the measured line widths equal the coverage widths (a linear-light blend reads ~30 % thinner)
  float fk = texture2D(tMask, vUv).g;                       // fog amount of the line (max over the AA footprint)
  fk = max(fk, max(texture2D(tMask, vUv + vec2(texel.x, 0.0)).g, texture2D(tMask, vUv - vec2(texel.x, 0.0)).g));
  fk = max(fk, max(texture2D(tMask, vUv + vec2(0.0, texel.y)).g, texture2D(tMask, vUv - vec2(0.0, texel.y)).g));
  vec3 inkC = mix(inkColor, fogColor, fk * fogInk);
  vec3 g = pow(max(c.rgb, 0.0), vec3(1.0 / 2.2));
  gl_FragColor = vec4(pow(mix(g, pow(inkC, vec3(1.0 / 2.2)), a), vec3(2.2)), c.a);
}`;

const COPY_FRAG = /* glsl */ `
uniform sampler2D tSrc;
varying vec2 vUv;
void main() {
  gl_FragColor = texture2D(tSrc, vUv);
  #include <colorspace_fragment>
}`;

export class InkPass extends Pass {
  /** 0 = normal, 1 = show the ink mask, 2 = show the world normal buffer */
  debug = 0;
  private world: THREE.Scene;
  private cam: THREE.PerspectiveCamera;
  private rt: THREE.WebGLRenderTarget;
  private maskRT: THREE.WebGLRenderTarget;
  private tmpRT: THREE.WebGLRenderTarget;
  private normalMat: THREE.ShaderMaterial;
  private maskMat: THREE.ShaderMaterial;
  private compMat: THREE.ShaderMaterial;
  private copyMat: THREE.ShaderMaterial;
  private fsScene = new THREE.Scene();
  private fsCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private quad: THREE.Mesh;
  private clearCol = new THREE.Color();

  constructor(scene: THREE.Scene, camera: THREE.PerspectiveCamera, options: InkOptions = {}) {
    super("InkPass");
    const o = { ...DEF, ...options };
    this.world = scene;
    this.cam = camera;
    this.cam.layers.enable(NOINK); // the main render still shows the NOINK layer (and its shadows)
    this.needsSwap = false; // writes back into the input buffer (keeps the composer's depth texture intact)
    this.needsDepthTexture = true;

    this.rt = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
      generateMipmaps: false, depthBuffer: true, samples: 0,
      depthTexture: new THREE.DepthTexture(1, 1, THREE.UnsignedIntType),
    });
    this.maskRT = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.UnsignedByteType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
      generateMipmaps: false, depthBuffer: false,
    });
    this.tmpRT = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.HalfFloatType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
      generateMipmaps: false, depthBuffer: false,
    });

    this.normalMat = new THREE.ShaderMaterial({
      vertexShader: NORMAL_VERT, fragmentShader: NORMAL_FRAG, side: THREE.DoubleSide,
      uniforms: { tCut: { value: null }, cut: { value: 0 }, cutUv: { value: new THREE.Matrix3() } },
    });
    // per object: copy the original material's cut-out (map + alphaTest) so alpha-tested world planes keep their shape
    this.normalMat.onBeforeRender = (_r, _s, _c, _g, object, group) => {
      const mat = (object as THREE.Mesh).material as THREE.Material | THREE.Material[];
      const gi = (group as unknown as { materialIndex?: number } | null)?.materialIndex ?? 0; // geometry group at runtime
      const src = (Array.isArray(mat) ? mat[gi] : mat) as THREE.MeshLambertMaterial;
      const u = this.normalMat.uniforms;
      const map = src && src.alphaTest > 0 ? src.map : null;
      u.tCut.value = map; u.cut.value = map ? src.alphaTest : 0;
      if (map) { map.updateMatrix(); (u.cutUv.value as THREE.Matrix3).copy(map.matrix); }
      this.normalMat.uniformsNeedUpdate = true;
    };
    const fs = (fragmentShader: string, uniforms: Record<string, THREE.IUniform>) =>
      new THREE.ShaderMaterial({ vertexShader: FS_VERT, fragmentShader, uniforms, depthTest: false, depthWrite: false });
    const texel = new THREE.Vector2(1, 1);
    this.maskMat = fs(MASK_FRAG, {
      tNormal: { value: this.rt.texture }, tDepth: { value: this.rt.depthTexture }, tMainDepth: { value: null },
      texel: { value: texel }, cNear: { value: 0.2 }, cFar: { value: 1500 }, p00: { value: 1 }, p11: { value: 1 },
      wNear: { value: o.widthNear }, wFar: { value: o.widthFar }, dNear: { value: o.distNear }, dFar: { value: o.distFar },
      creaseScale: { value: o.creaseScale }, depthLo: { value: o.depthLo }, depthHi: { value: o.depthHi },
      cosLo: { value: Math.cos((o.angleLo * Math.PI) / 180) }, cosHi: { value: Math.cos((o.angleHi * Math.PI) / 180) },
      concaveGain: { value: o.concaveGain }, farOpacity: { value: o.farOpacity },
      fadeNear: { value: o.fadeNear }, fadeFar: { value: o.fadeFar }, strength: { value: o.strength }, useMain: { value: 0 }, pxScale: { value: 1 }, fogRange: { value: new THREE.Vector2(0, 0) }, fogStart: { value: 60 },
    });
    this.compMat = fs(COMP_FRAG, {
      inputBuffer: { value: null }, tMask: { value: this.maskRT.texture }, tNormal: { value: this.rt.texture },
      texel: { value: texel }, inkColor: { value: new THREE.Color(o.color) }, debug: { value: 0 },
      fogColor: { value: new THREE.Color() }, fogInk: { value: 0.3 },
    });
    this.copyMat = fs(COPY_FRAG, { tSrc: { value: this.tmpRT.texture } });
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.maskMat);
    this.quad.frustumCulled = false;
    this.fsScene.add(this.quad);
  }

  /** live tuning, e.g. ink.set({ widthNear: 4.2, concaveGain: 0.5 }) */
  set(options: InkOptions) {
    const u = this.maskMat.uniforms;
    const map: [keyof InkOptions, string][] = [["widthNear", "wNear"], ["widthFar", "wFar"], ["distNear", "dNear"], ["distFar", "dFar"],
      ["creaseScale", "creaseScale"], ["depthLo", "depthLo"], ["depthHi", "depthHi"], ["concaveGain", "concaveGain"],
      ["farOpacity", "farOpacity"], ["fadeNear", "fadeNear"], ["fadeFar", "fadeFar"], ["strength", "strength"]];
    for (const [k, n] of map) if (options[k] !== undefined) u[n].value = options[k];
    if (options.angleLo !== undefined) u.cosLo.value = Math.cos((options.angleLo * Math.PI) / 180);
    if (options.angleHi !== undefined) u.cosHi.value = Math.cos((options.angleHi * Math.PI) / 180);
    if (options.color !== undefined) (this.compMat.uniforms.inkColor.value as THREE.Color).set(options.color);
  }

  override setDepthTexture(depthTexture: THREE.Texture) {
    this.maskMat.uniforms.tMainDepth.value = depthTexture ?? null;
    this.maskMat.uniforms.useMain.value = depthTexture ? 1 : 0;
  }

  override setSize(width: number, height: number) {
    this.rt.setSize(width, height);
    this.maskRT.setSize(width, height);
    this.tmpRT.setSize(width, height);
    (this.maskMat.uniforms.texel.value as THREE.Vector2).set(1 / width, 1 / height);
    this.maskMat.uniforms.pxScale.value = height / 1920; // widths are specified at 1080x1920
  }

  override render(renderer: THREE.WebGLRenderer, inputBuffer: THREE.WebGLRenderTarget) {
    const scene = this.world, cam = this.cam;
    const autoClear = renderer.autoClear, shadowAuto = renderer.shadowMap.autoUpdate;
    const mask = cam.layers.mask, override = scene.overrideMaterial, background = scene.background;
    renderer.getClearColor(this.clearCol);
    const clearAlpha = renderer.getClearAlpha();
    renderer.autoClear = false;

    // 1) world-only normals + depth (no characters / sprites / sky; shadow maps are not re-rendered)
    cam.layers.disable(NOINK);
    scene.overrideMaterial = this.normalMat;
    scene.background = null;
    renderer.shadowMap.autoUpdate = false;
    renderer.setClearColor(0x000000, 0);
    renderer.setRenderTarget(this.rt);
    renderer.clear(true, true, false);
    renderer.render(scene, cam);
    cam.layers.mask = mask;
    scene.overrideMaterial = override;
    scene.background = background;
    renderer.shadowMap.autoUpdate = shadowAuto;
    renderer.setClearColor(this.clearCol, clearAlpha);

    // 2) edge mask
    const u = this.maskMat.uniforms, e = cam.projectionMatrix.elements;
    u.cNear.value = cam.near; u.cFar.value = cam.far; u.p00.value = e[0]; u.p11.value = e[5];
    const fog = scene.fog as THREE.Fog | null;
    if (fog && (fog as THREE.Fog).isFog) { (u.fogRange.value as THREE.Vector2).set(fog.near, fog.far); (this.compMat.uniforms.fogColor.value as THREE.Color).copy(fog.color); }
    else (u.fogRange.value as THREE.Vector2).set(0, 0);
    this.quad.material = this.maskMat;
    renderer.setRenderTarget(this.maskRT);
    renderer.render(this.fsScene, this.fsCam);

    // 3) composite into a temp target, 4) copy back into the input buffer (colour only; depth untouched)
    this.compMat.uniforms.inputBuffer.value = inputBuffer.texture;
    this.compMat.uniforms.debug.value = this.debug;
    this.quad.material = this.compMat;
    renderer.setRenderTarget(this.tmpRT);
    renderer.render(this.fsScene, this.fsCam);
    this.quad.material = this.copyMat;
    renderer.setRenderTarget(this.renderToScreen ? null : inputBuffer);
    renderer.render(this.fsScene, this.fsCam);

    renderer.autoClear = autoClear;
  }

  override dispose() {
    this.rt.depthTexture?.dispose();
    this.rt.dispose(); this.maskRT.dispose(); this.tmpRT.dispose();
    this.normalMat.dispose(); this.maskMat.dispose(); this.compMat.dispose(); this.copyMat.dispose();
    this.quad.geometry.dispose();
  }
}

/** Safety net for the NOINK contract (CHAR / WORLD put cards, sky, clouds and smoke on NOINK themselves): anything
 *  that does not write depth in the main render (sky sphere, cloud and smoke cards, soft effect sprites) and every
 *  camera-facing billboard (meshes with a customDepthMaterial cut-out = cast actors; alpha-tested MeshBasicMaterial
 *  effect cards) goes on NOINK. Idempotent, cheap (one traversal), safe to call every frame. */
export function noInkFallback(root: THREE.Object3D) {
  root.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!(m.isMesh || (o as THREE.Sprite).isSprite || (o as THREE.Points).isPoints || (o as THREE.Line).isLine)) return;
    if (o.layers.mask === 1 << NOINK) return;
    const mats = (Array.isArray(m.material) ? m.material : [m.material]) as THREE.Material[];
    const card = !!m.customDepthMaterial || (o as THREE.Sprite).isSprite || (o as THREE.Points).isPoints || (o as THREE.Line).isLine;
    const noDepth = mats.some((x) => x && x.depthWrite === false);
    const basicCut = mats.some((x) => x && (x as THREE.MeshBasicMaterial).isMeshBasicMaterial && x.alphaTest > 0);
    if (card || noDepth || basicCut) o.layers.set(NOINK);
  });
}
