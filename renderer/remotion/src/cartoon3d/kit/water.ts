// The skill's river shader (templates/bridge/world.ts, MIT, Copyright (c) 2026 Mr omi), lifted into its own module so
// every set can pour water: the lake, the river, the puddles. Colours by depression angle of the view ray + sparse
// painted marks drifting along +x. world.ts writes the uniforms once per frame from LOOK[light].water.
import * as THREE from "three";
import { LFB } from "./shade";
import { waterNear, waterFar } from "./paint";

export const WU: Record<string, THREE.IUniform> = {
  wNearC: { value: new THREE.Color() }, wMidC: { value: new THREE.Color() }, wFarC: { value: new THREE.Color() },
  wCrest: { value: new THREE.Color() }, wTrough: { value: new THREE.Color() }, wGlint: { value: new THREE.Color() },
  wShade: { value: new THREE.Vector3(0.5, 0.56, 0.72) }, wNearTex: { value: null }, wFarTex: { value: null }, wTime: { value: 0 },
};
const WATER_DECL = `#include <common>
varying vec3 vWP;
uniform vec3 wNearC, wMidC, wFarC, wCrest, wTrough, wGlint, wShade;
uniform sampler2D wNearTex, wFarTex;
uniform float wTime; uniform float wFlow; uniform vec3 wTint; uniform float wTintK;`;
const WATER_COL = `
  vec3 wV = vWP - cameraPosition;
  float wd = length(wV);
  float wDep = asin(clamp(-wV.y / wd, 0.0, 1.0));       // depression angle of the view ray
  float wf = 1.0 - smoothstep(0.0, 0.42, wDep);         // 1 at the horizon .. 0 at 24 deg down
  vec3 wc = mix(mix(wNearC, wMidC, smoothstep(0.0, 0.55, wf)), wFarC, smoothstep(0.55, 1.0, wf));
  vec2 wp = vWP.xz + vec2(wFlow * wTime, 0.0);         // slow drift along +x
  vec4 mk = mix(texture2D(wNearTex, wp / 8.0), texture2D(wFarTex, wp / 40.0 + 0.37), smoothstep(25.0, 90.0, wd));
  wc = mix(wc, wTrough, mk.g * 0.6);
  wc = mix(wc, wCrest, mk.r * 0.7);
  wc = mix(wc, wGlint, mk.b * (0.3 + 0.5 * wf));
  wc = mix(wc, wTint, wTintK);                          // ours: muddy puddles / sewage lean brown
  diffuseColor.rgb = wc;`;
const cache = new Map<string, THREE.MeshLambertMaterial>();
/** water material; tint/k pull it toward a colour (k 0 = clean lake), flow = drift speed (m/s along +x) */
export const waterMat = (tint = "#000000", k = 0, flow = 0.35) => {
  const key = `${tint}|${k}|${flow}`;
  let m = cache.get(key);
  if (m) return m;
  if (!WU.wNearTex.value) {
    const wNear = waterNear(), wFar = waterFar();
    for (const t of [wNear, wFar]) { t.colorSpace = THREE.NoColorSpace; t.anisotropy = 16; t.needsUpdate = true; }
    WU.wNearTex.value = wNear; WU.wFarTex.value = wFar;
  }
  m = new THREE.MeshLambertMaterial({ color: 0xffffff });
  const own = { wFlow: { value: flow }, wTint: { value: new THREE.Color(tint) }, wTintK: { value: k } };
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, WU, own);
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vWP;")
      .replace("#include <project_vertex>", "#include <project_vertex>\nvWP = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", WATER_DECL)
      .replace("#include <map_fragment>", WATER_COL)
      .replace("#include <lights_fragment_begin>", "float sunVis = 1.0;\n" + LFB)
      .replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\n  reflectedLight.directDiffuse = diffuseColor.rgb * mix(wShade, vec3(1.0), sunVis);\n  reflectedLight.indirectDiffuse = vec3(0.0);");
  };
  m.customProgramCacheKey = () => "chWater1";
  cache.set(key, m);
  return m;
};
