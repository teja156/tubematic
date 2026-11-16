// Low-Poly Skit house figure (TMDEV-250): one jointed figure of about 18 rigid flat-shaded primitives, about 4.3 heads
// tall, a short neck, a faceted head under a hair cap, tapered torso, chunky boots. Tubematic's own design: its
// proportions, palette and parts are not any reference's. Units: the figure stands 1.0 tall, feet at y = 0, facing +z.
// Every joint is a Group the pose library rotates (x = swing, z = out to the side); a figure is data (an Outfit) plus
// the shared geometry below, so a crowd can instance the same parts.
import * as THREE from "three";

export type HairStyle = "cap" | "tuft" | "bob" | "bald";

/** the knobs that tell two figures apart; everything else (mesh, proportions) is shared */
export type Outfit = {
  skin: string; hair: string; hairStyle: HairStyle; shirt: string; trousers: string; boots: string; sole: string;
  /** a darker jaw patch */
  stubble?: boolean;
};

/** palette of the house cast: warm skin tones, readable bright shirts, deep trousers */
export const SKINS = ["#f1b27a", "#d98d57", "#a8683c", "#7a4a2b", "#f6cba3"] as const;
export const HAIRS = ["#3a2616", "#d8a23a", "#8a8a92", "#f2f0ea", "#16161c", "#a2492a"] as const;
export const SHIRTS = ["#2f9aa8", "#ef6a4a", "#e7b53c", "#6d5bc9", "#4faa5b", "#d9507f", "#3f6fc4", "#f08a3a"] as const;
export const TROUSERS = ["#27304f", "#3a3a40", "#5a4630", "#2c4a3e"] as const;

export const HOUSE: Outfit = {
  skin: SKINS[0], hair: HAIRS[0], hairStyle: "cap", shirt: SHIRTS[0], trousers: TROUSERS[0], boots: "#e9e6df", sole: "#33333b",
};

/** z of the flat face plate on the head; faces.ts draws its decals on it */
export const FACE_Z = 0.088;

/** shared geometry, built once: parts are scaled and tinted, never rebuilt */
const G = (() => {
  const cyl = (rt: number, rb: number, h: number, seg = 6) => new THREE.CylinderGeometry(rt, rb, h, seg, 1);
  const head = new THREE.IcosahedronGeometry(0.115, 1);
  head.scale(1, 1.06, 0.98);
  // the front of the head is one flat plate (a face), so decals sit flush on it from every angle
  const pos = head.getAttribute("position") as THREE.BufferAttribute;
  for (let i = 0; i < pos.count; i++) if (pos.getZ(i) > FACE_Z) pos.setZ(i, FACE_Z);
  head.computeVertexNormals();
  return {
    head,
    cap: new THREE.SphereGeometry(0.126, 8, 4, 0, Math.PI * 2, 0, Math.PI * 0.47),
    bob: new THREE.BoxGeometry(0.2, 0.15, 0.06),
    tuft: new THREE.ConeGeometry(0.04, 0.075, 5),
    neck: cyl(0.036, 0.04, 0.05),
    torso: cyl(0.105, 0.085, 0.27, 6),
    pelvis: new THREE.BoxGeometry(0.17, 0.07, 0.11),
    upperArm: cyl(0.04, 0.034, 0.12, 5),
    foreArm: cyl(0.034, 0.029, 0.11, 5),
    hand: new THREE.OctahedronGeometry(0.037, 0),
    thigh: cyl(0.048, 0.04, 0.165, 5),
    shin: cyl(0.04, 0.033, 0.17, 5),
    boot: new THREE.BoxGeometry(0.095, 0.055, 0.14),
    sole: new THREE.BoxGeometry(0.1, 0.014, 0.15),
    jaw: new THREE.BoxGeometry(0.1, 0.04, 0.05),
  };
})();

const mat = (c: string) => new THREE.MeshLambertMaterial({ color: c, flatShading: true });

export type Joint = THREE.Group;
export type Figure = {
  /** where the figure stands: position, yaw and scale belong to the set */
  root: THREE.Group;
  /** the body inside root: a pose lays it down, tips it or lifts it (poses.ts) */
  body: THREE.Group;
  /** rotate these: spine, neck, shoulderL/R, elbowL/R, hipL/R, kneeL/R */
  joints: Record<"spine" | "neck" | "shoulderL" | "shoulderR" | "elbowL" | "elbowR" | "hipL" | "hipR" | "kneeL" | "kneeR", Joint>;
  /** where the face decals attach: the front of the head, in the neck's frame */
  headMount: THREE.Group;
  /** a hand's local frame, for parenting a prop on a set frame */
  handL: THREE.Group;
  handR: THREE.Group;
  outfit: Outfit;
};

export type Role = "skin" | "hair" | "shirt" | "trousers" | "boots" | "sole" | "stubble";
/** a part's tint comes from its role, so a crowd can re-tint instances; `optional` parts exist only for some outfits */
const part = (geo: THREE.BufferGeometry, color: string, parent: THREE.Object3D, role: Role, x = 0, y = 0, z = 0, optional?: "cap" | "tuft" | "bob" | "jaw") => {
  const m = new THREE.Mesh(geo, mat(color));
  m.position.set(x, y, z);
  m.userData.role = role;
  if (optional) m.userData.optional = optional;
  parent.add(m);
  return m;
};
const grp = (parent: THREE.Object3D, x = 0, y = 0, z = 0) => {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  parent.add(g);
  return g;
};

/** `all`: also build every optional part (cap, tuft, bob, jaw), for the prototype a crowd instances from */
export function buildFigure(o: Outfit = HOUSE, all = false): Figure {
  const root = new THREE.Group();
  const body = grp(root);
  part(G.pelvis, o.trousers, body, "trousers", 0, 0.41, 0);
  const spine = grp(body, 0, 0.44, 0);
  part(G.torso, o.shirt, spine, "shirt", 0, 0.135, 0).scale.z = 0.7;
  const neck = grp(spine, 0, 0.275, 0);
  part(G.neck, o.skin, neck, "skin", 0, 0.02, 0);
  const headMount = grp(neck, 0, 0.11, 0);
  part(G.head, o.skin, headMount, "skin");
  if (o.stubble || all) part(G.jaw, "#6b4a30", headMount, "stubble", 0, -0.07, 0.05, "jaw");
  if (all || o.hairStyle === "cap" || o.hairStyle === "tuft" || o.hairStyle === "bob") { const c = part(G.cap, o.hair, headMount, "hair", 0, 0.03, -0.012, "cap"); c.rotation.x = -0.22; }
  if (all || o.hairStyle === "tuft") part(G.tuft, o.hair, headMount, "hair", 0, 0.165, -0.01, "tuft");
  if (all || o.hairStyle === "bob") part(G.bob, o.hair, headMount, "hair", 0, -0.03, -0.075, "bob");

  const arm = (side: 1 | -1) => {
    const shoulder = grp(spine, side * 0.13, 0.245, 0);
    part(G.upperArm, o.shirt, shoulder, "shirt", 0, -0.06, 0);
    const elbow = grp(shoulder, 0, -0.12, 0);
    part(G.foreArm, o.skin, elbow, "skin", 0, -0.055, 0);
    const hand = grp(elbow, 0, -0.125, 0);
    part(G.hand, o.skin, hand, "skin");
    return { shoulder, elbow, hand };
  };
  const leg = (side: 1 | -1) => {
    const hip = grp(body, side * 0.048, 0.39, 0);
    part(G.thigh, o.trousers, hip, "trousers", 0, -0.0825, 0);
    const knee = grp(hip, 0, -0.165, 0);
    part(G.shin, o.trousers, knee, "trousers", 0, -0.085, 0);
    part(G.boot, o.boots, knee, "boots", 0, -0.17, 0.02);
    part(G.sole, o.sole, knee, "sole", 0, -0.2, 0.02);
    return { hip, knee };
  };
  const aL = arm(1), aR = arm(-1), lL = leg(1), lR = leg(-1);
  return {
    root, body, outfit: o, headMount, handL: aL.hand, handR: aR.hand,
    joints: { spine, neck, shoulderL: aL.shoulder, shoulderR: aR.shoulder, elbowL: aL.elbow, elbowR: aR.elbow, hipL: lL.hip, hipR: lR.hip, kneeL: lL.knee, kneeR: lR.knee },
  };
}

/** seeded pick, so a crowd's cast is the same on every render */
export const mulberry = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export function randomOutfit(rnd: () => number): Outfit {
  const pick = <T,>(a: readonly T[]) => a[Math.floor(rnd() * a.length)];
  return {
    skin: pick(SKINS), hair: pick(HAIRS), hairStyle: pick(["cap", "cap", "tuft", "bob", "bald"] as const), shirt: pick(SHIRTS),
    trousers: pick(TROUSERS), boots: rnd() < 0.7 ? "#e9e6df" : "#4b3a2e", sole: "#33333b", stubble: rnd() < 0.2,
  };
}
