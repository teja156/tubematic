// The Carrington Event test scene: set, lights, character, effects and the
// whole timeline as a pure function of the frame number.
import * as THREE from "three";
import { applyPose, Beat, poseAt } from "../kit/cameraPath";
import { Cutout } from "../kit/Cutout";
import type { Dof, Grade } from "../kit/InkPipeline";
import { clamp01, hash, lerp, ramp } from "../kit/prng";
import { makeSky } from "../kit/Sky";
import { softDot } from "../kit/textures";
import { buildDesk, DESK, leadGeometry } from "./desk";
import { OPERATOR_STATES } from "./operator";
import { buildTown, PORCH_H } from "./town";

export const FPS = 30;
export const DURATION = 810; // 27 s

// ---- beats (frames) ----
export const T = {
  duskStart: 150,
  sunset: 230,
  dusk: 290,
  night: 345,
  auroraStart: 255,
  auroraFull: 370,
  sparksStart: 448,
  recoil: 462,
  reach: 600,
  unplugged: 626,
  amazed: 652,
};

const OP = { x: DESK.x, z: 0.84 }; // operator plane base

export const BEATS: Beat[] = [
  // 1. late afternoon: the street, poles and wires leading to the office
  {
    start: 0,
    end: 105,
    from: { pos: [-7.2, 2.1, 14.5], target: [-1.6, 2.4, 0.6], fov: 52, focus: 13.5 },
    to: { pos: [-6.0, 2.0, 12.4], target: [-1.3, 2.3, 0.7], fov: 50, focus: 11.6 },
  },
  // 2. glide up to the wires and along them toward the setting sun
  {
    start: 185,
    end: 285,
    from: { pos: [-5.6, 6.0, 6.2], target: [-26, 5.4, 3.4], fov: 50, focus: 9 },
    to: { pos: [-11.5, 5.9, 6.4], target: [-33, 5.2, 3.4], fov: 50, focus: 9 },
    via: [[-6.4, 3.6, 10.0]],
  },
  // 3. night: tilt up to the aurora over the rooftops
  {
    start: 330,
    end: 385,
    from: { pos: [-11, 4.0, 10.5], target: [-4, 11.5, -12], fov: 56, focus: 18 },
    to: { pos: [-9.6, 3.6, 10.0], target: [-3.2, 10.8, -12], fov: 56, focus: 16 },
  },
  // 4. the operator at his desk; sparks, recoil
  {
    start: 440,
    end: 585,
    from: { pos: [0.2, 1.85, 5.0], target: [-0.6, 1.5, 1.0], fov: 42, focus: 4.25 },
    to: { pos: [-0.05, 1.8, 4.4], target: [-0.6, 1.5, 1.0], fov: 41, focus: 3.65 },
    via: [[-4.5, 2.6, 8.2]],
  },
  // 5. unplug, the key keeps clicking; slow push-in on his face
  {
    start: 620,
    end: 809,
    from: { pos: [0.15, 1.7, 3.7], target: [-0.5, 1.45, 1.0], fov: 40, focus: 2.95 },
    to: { pos: [-0.42, 1.78, 2.35], target: [-0.6, 1.62, 0.84], fov: 36, focus: 1.52 },
  },
];

// time of day: 0 = late afternoon, 0.5 = sunset, 1 = aurora night
const todAt = (f: number) => {
  if (f < T.duskStart) return 0;
  if (f < T.sunset) return 0.5 * ramp(f, T.duskStart, T.sunset);
  if (f < T.dusk) return 0.5 + 0.3 * ramp(f, T.sunset, T.dusk);
  return 0.8 + 0.2 * ramp(f, T.dusk, T.night);
};

const C = (r: number, g: number, b: number) => new THREE.Color(r, g, b);
// keyframed palette over tod: [day, sunset, dusk, night]
const KEYS = [0, 0.5, 0.8, 1];
const pal = (vals: THREE.Color[], tod: number) => {
  for (let i = 0; i < KEYS.length - 1; i++) {
    if (tod <= KEYS[i + 1]) {
      const t = (tod - KEYS[i]) / (KEYS[i + 1] - KEYS[i]);
      return vals[i].clone().lerp(vals[i + 1], t);
    }
  }
  return vals[vals.length - 1].clone();
};
const num = (vals: number[], tod: number) => {
  for (let i = 0; i < KEYS.length - 1; i++) {
    if (tod <= KEYS[i + 1]) return lerp(vals[i], vals[i + 1], (tod - KEYS[i]) / (KEYS[i + 1] - KEYS[i]));
  }
  return vals[vals.length - 1];
};

export class CarringtonScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(50, 1080 / 1920, 0.1, 500);
  private sky = makeSky();
  private key = new THREE.DirectionalLight(0xffffff, 3);
  private hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 1);
  private sparkLight = new THREE.PointLight(0xaad8ff, 0, 6, 2);
  private town = buildTown();
  private desk = buildDesk();
  private op = new Cutout(1.7, OPERATOR_STATES);
  private sparks: THREE.Points;
  private sparkGeo: THREE.BufferGeometry;
  private arcs: THREE.Mesh[] = [];
  private arcMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(2.2, 2.8, 4.0) });
  private smoke: THREE.Sprite[] = [];
  private fog = new THREE.Fog(0xffffff, 60, 330);
  private static readonly NSPARK = 90;
  grade!: Grade;
  dof!: Dof;

  constructor(shadows: boolean) {
    const s = this.scene;
    s.fog = this.fog;
    s.add(this.sky.sky);
    s.add(this.town.root);
    s.add(this.desk.root);
    this.op.mesh.position.set(OP.x, PORCH_H, OP.z);
    s.add(this.op.mesh);

    this.key.castShadow = shadows;
    this.key.shadow.mapSize.set(2048, 2048);
    const sc = this.key.shadow.camera;
    sc.left = -32;
    sc.right = 32;
    sc.top = 32;
    sc.bottom = -32;
    sc.near = 1;
    sc.far = 140;
    this.key.shadow.bias = -0.0008;
    this.key.shadow.normalBias = 0.03;
    this.key.target.position.set(-10, 0, 4);
    s.add(this.key, this.key.target, this.hemi, this.sparkLight);

    // sparks: additive points, positions written per frame
    this.sparkGeo = new THREE.BufferGeometry();
    this.sparkGeo.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(CarringtonScene.NSPARK * 3), 3));
    this.sparkGeo.setAttribute("size", new THREE.Float32BufferAttribute(new Float32Array(CarringtonScene.NSPARK), 1));
    const sparkMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { scale: { value: 1 } },
      vertexShader: /* glsl */ `
        attribute float size;
        uniform float scale;
        varying float vA;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * scale / -mv.z;
          vA = step(0.001, size);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        varying float vA;
        void main() {
          float d = length(gl_PointCoord - 0.5) * 2.0;
          float a = (1.0 - smoothstep(0.2, 1.0, d)) * vA;
          gl_FragColor = vec4(vec3(3.0, 2.6, 1.6) * a + vec3(1.0, 2.0, 3.0) * a * (1.0 - d), a);
        }`,
    });
    this.sparks = new THREE.Points(this.sparkGeo, sparkMat);
    this.sparks.frustumCulled = false;
    this.sparks.userData.noInk = true;
    s.add(this.sparks);

    for (let i = 0; i < 3; i++) {
      const m = new THREE.Mesh(new THREE.BufferGeometry(), this.arcMat);
      m.userData.noInk = true;
      m.frustumCulled = false;
      this.arcs.push(m);
      s.add(m);
    }
    const puff = softDot("rgba(255,255,255,0.75)", "rgba(255,255,255,0)");
    for (let i = 0; i < 8; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: puff, color: 0xb8a8e8, transparent: true, depthWrite: false, opacity: 0 }));
      sp.userData.noInk = true;
      this.smoke.push(sp);
      s.add(sp);
    }
  }

  // pixel scale for point sprites (call once the drawing buffer size is known)
  setResolution(heightPx: number) {
    ((this.sparks.material as THREE.ShaderMaterial).uniforms.scale as { value: number }).value = heightPx / 1920;
  }

  sparkIntensity(f: number) {
    if (f < T.sparksStart) return 0;
    const on = ramp(f, T.sparksStart, T.sparksStart + 8);
    const off = 1 - ramp(f, T.unplugged - 6, T.unplugged + 2);
    return on * off;
  }

  update(f: number) {
    const tod = todAt(f);
    const aur = ramp(f, T.auroraStart, T.auroraFull);
    const time = f / FPS;
    const pulse = 0.5 + 0.5 * Math.sin(time * 1.3) * Math.sin(time * 0.7 + 1);

    // ---- sky ----
    const u = this.sky.uniforms;
    u.zenith.value.copy(pal([C(0.18, 0.42, 0.95), C(0.22, 0.2, 0.62), C(0.07, 0.07, 0.3), C(0.02, 0.03, 0.14)], tod));
    u.horizon.value.copy(pal([C(1.0, 0.78, 0.48), C(1.0, 0.38, 0.22), C(0.42, 0.18, 0.42), C(0.08, 0.1, 0.3)], tod));
    u.ground.value.copy(pal([C(0.6, 0.45, 0.4), C(0.5, 0.25, 0.3), C(0.18, 0.1, 0.3), C(0.06, 0.06, 0.2)], tod));
    u.cloudColor.value.copy(pal([C(1.0, 0.92, 0.85), C(1.0, 0.5, 0.45), C(0.5, 0.25, 0.55), C(0.12, 0.12, 0.32)], tod));
    const sunEl = num([0.32, 0.05, -0.08, -0.2], tod);
    u.sunDir.value.set(-1, sunEl, 0.25).normalize();
    u.sunColor.value.copy(pal([C(1, 0.85, 0.55), C(1, 0.45, 0.2), C(0.5, 0.15, 0.2), C(0, 0, 0)], tod));
    u.stars.value = clamp01((tod - 0.7) / 0.3);
    u.aurora.value = aur * (0.75 + 0.25 * pulse);
    u.time.value = time;
    this.fog.color.copy(u.horizon.value).lerp(u.zenith.value, 0.25);

    // ---- key + fill ----
    const auroraTint = C(0.3, 1.0, 0.6).lerp(C(0.85, 0.35, 1.0), pulse * 0.6);
    const keyCol = pal([C(1.0, 0.82, 0.55), C(1.0, 0.5, 0.28), C(0.5, 0.45, 1.0), auroraTint], tod);
    this.key.color.copy(keyCol);
    this.key.intensity = num([3.2, 2.4, 1.1, 1.5], tod);
    // the key swings from a low western sun to a high night light over the town
    const dir = pal([C(-26, 16, 20), C(-30, 7, 14), C(-16, 22, 18), C(-12, 30, 16)], tod);
    this.key.position.set(-10 + dir.r, dir.g, 4 + dir.b);
    this.hemi.color.copy(pal([C(0.55, 0.72, 1.0), C(0.55, 0.45, 0.95), C(0.35, 0.35, 0.95), C(0.32, 0.45, 0.95).lerp(auroraTint, 0.35)], tod));
    this.hemi.groundColor.copy(pal([C(0.55, 0.38, 0.3), C(0.45, 0.25, 0.35), C(0.2, 0.12, 0.38), C(0.18, 0.12, 0.38)], tod));
    this.hemi.intensity = num([1.15, 0.95, 0.85, 1.05], tod);

    for (const g of this.town.windowGlow) {
      const lit = g.color.r > 0.9; // warm windows glow after dusk
      if (lit) g.emissive.setRGB(1.0, 0.55, 0.15).multiplyScalar(clamp01((tod - 0.55) / 0.3) * 1.4);
    }

    // ---- camera ----
    const pose = poseAt(BEATS, f);
    applyPose(this.camera, pose);
    this.sky.sky.position.copy(this.camera.position);

    // ---- desk mechanics ----
    const clicking = f < T.unplugged ? hash(Math.floor(f / 3), 7) > 0.45 : hash(Math.floor(f / 4), 11) > 0.5;
    const tapping = f < T.recoil || f >= T.unplugged;
    const down = tapping && clicking;
    this.desk.lever.rotation.x = down ? 0.09 : -0.02;
    this.desk.sounderArm.rotation.z = down ? -0.06 : 0.04;

    // battery lead: plugged in, then pulled out and held up
    const hand = this.op.canvasToWorld(448, 300);
    const reachHand = this.op.canvasToWorld(472, 392);
    const tPull = ramp(f, T.reach + 8, T.unplugged);
    const plug = f < T.reach + 8 ? this.desk.terminal.clone() : this.desk.terminal.clone().lerp(reachHand, 0.15).lerp(hand, tPull);
    this.desk.leadMesh.geometry.dispose();
    this.desk.leadMesh.geometry = leadGeometry(this.desk.keyPost, plug, f >= T.unplugged ? 0.1 : 0);

    // ---- sparks / arcs / light ----
    const si = this.sparkIntensity(f);
    const pos = this.sparkGeo.getAttribute("position") as THREE.BufferAttribute;
    const size = this.sparkGeo.getAttribute("size") as THREE.BufferAttribute;
    const o = this.desk.keyContact;
    for (let i = 0; i < CarringtonScene.NSPARK; i++) {
      // each spark slot re-fires every 9 frames with a hashed phase
      const period = 9;
      const phase = Math.floor(hash(i, 1) * period);
      const birth = Math.floor((f - phase) / period) * period + phase;
      const age = (f - birth) / FPS;
      const alive = si > 0 && hash(i, birth, 2) < si * 0.85;
      if (!alive) {
        size.setX(i, 0);
        pos.setXYZ(i, o.x, o.y, o.z);
        continue;
      }
      const src = hash(i, 3) < 0.6 ? o : this.desk.sounderPos;
      const vx = (hash(i, birth, 4) - 0.5) * 2.2;
      const vy = hash(i, birth, 5) * 2.0 + 0.4;
      const vz = (hash(i, birth, 6) - 0.2) * 2.0;
      pos.setXYZ(i, src.x + vx * age, src.y + vy * age - 4.9 * age * age, src.z + vz * age);
      size.setX(i, (1 - age / (period / FPS)) * 34 * (0.5 + hash(i, birth, 8)));
    }
    pos.needsUpdate = true;
    size.needsUpdate = true;
    const flicker = 0.4 + 0.6 * hash(f, 9);
    this.sparkLight.position.set(o.x, o.y + 0.15, o.z + 0.15);
    this.sparkLight.intensity = si * flicker * 9;

    for (const [k, arc] of this.arcs.entries()) {
      arc.geometry.dispose();
      const show = si > 0.2 && hash(f, k, 12) < 0.55;
      if (!show) {
        arc.geometry = new THREE.BufferGeometry();
        continue;
      }
      const a = o;
      const b = k === 0 ? this.desk.sounderPos : k === 1 ? this.desk.keyPost : this.desk.terminal;
      const pts: THREE.Vector3[] = [];
      for (let j = 0; j <= 7; j++) {
        const t = j / 7;
        const p = a.clone().lerp(b, t);
        const amp = Math.sin(t * Math.PI) * 0.035;
        p.x += (hash(f, k, j, 13) - 0.5) * 2 * amp;
        p.y += (hash(f, k, j, 14) - 0.3) * 2 * amp + Math.sin(t * Math.PI) * 0.04;
        p.z += (hash(f, k, j, 15) - 0.5) * 2 * amp;
        pts.push(p);
      }
      arc.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, false, "catmullrom", 0), 28, 0.0035, 4, false);
    }

    // paper tape smoulders: ember glow + rising smoke
    const smoulder = ramp(f, T.recoil + 8, T.recoil + 40);
    this.desk.tapeGlow.emissive.setRGB(1.0, 0.35, 0.05).multiplyScalar(smoulder * (1.2 + 0.8 * hash(f, 21)));
    for (const [i, sp] of this.smoke.entries()) {
      const life = 40;
      const age = ((f + i * 5) % life) / life;
      const e = this.desk.tapeEnd;
      sp.position.set(e.x + Math.sin(age * 5 + i) * 0.04 * age, e.y + age * 0.55, e.z + age * 0.05);
      sp.scale.setScalar(0.05 + age * 0.22);
      (sp.material as THREE.SpriteMaterial).opacity = smoulder * 0.55 * Math.sin(age * Math.PI);
    }

    // ---- operator ----
    let state: string;
    if (f < 300) state = "tap:smile";
    else if (f < T.recoil) state = "tap:focus";
    else if (f < T.reach) state = "recoil:shock";
    else if (f < T.reach + 12) state = "reach:shock";
    else if (f < T.amazed) state = "hold:shock";
    else state = "hold:amazed";
    const blinkAt = [60, 210, 380, 700, 768];
    const blinking = blinkAt.some((b) => f >= b && f < b + 4);
    if (blinking && OPERATOR_STATES[`${state}:blink`]) state = `${state}:blink`;
    this.op.setState(state);
    const recoilT = f >= T.recoil && f < T.reach ? ramp(f, T.recoil, T.recoil + 5) * (1 - 0.3 * ramp(f, T.recoil + 5, T.recoil + 30)) : 0;
    const bob = Math.sin(time * 2.4) * 0.008 + (down && tapping && f < T.recoil ? -0.006 : 0);
    this.op.mesh.position.set(OP.x, PORCH_H + bob + recoilT * 0.05, OP.z - recoilT * 0.06);
    this.op.face(this.camera, 0.8);
    this.op.setTint(this.hemi.color.clone().lerp(C(1, 0.95, 0.9), 0.3), num([0.22, 0.2, 0.22, 0.26], tod) + si * 0.1);

    // ---- grade + dof ----
    this.grade = {
      exposure: num([1.0, 1.05, 1.25, 1.35], tod),
      saturation: num([1.3, 1.35, 1.3, 1.35], tod),
      contrast: num([1.06, 1.08, 1.05, 1.05], tod),
      lift: pal([C(0.07, 0.05, 0.09), C(0.08, 0.04, 0.1), C(0.05, 0.04, 0.12), C(0.045, 0.045, 0.13)], tod),
      gain: pal([C(1, 0.99, 0.96), C(1, 0.96, 0.93), C(0.95, 0.96, 1), C(0.94, 0.98, 1)], tod),
      shadowTint: pal([C(0.85, 0.88, 1.15), C(0.85, 0.78, 1.2), C(0.72, 0.72, 1.3), C(0.72, 0.75, 1.3)], tod),
      hiTint: pal([C(1.06, 1.0, 0.9), C(1.08, 0.97, 0.88), C(1.0, 0.98, 1.0), C(0.98, 1.0, 1.02)], tod),
    };
    const near = clamp01((pose.focus - 2) / 9);
    this.dof = { focus: pose.focus, strength: lerp(16, 9, near), maxRadius: 10 };
  }
}
