// The four sets of the "dig" example. A set is a class with a `root` built once and a `pose(id, f, cam)` that moves what
// moves, as a pure function of the frame. Each builds its own hero from the kit's figure; sets are far apart in x.
import * as THREE from "three";
import { buildFigure, HOUSE, randomOutfit, type Figure } from "../../figure";
import { setFace } from "../../faces";
import { applyPose, POSES, poseTrack, type Pose } from "../../poses";
import { dancePose, idlePose, walkPose } from "../../cycles";
import { Crowd } from "../../crowd";
import { Burst, ComicWord, Debris } from "../../fx";
import { box, cyl, discs, flat, globe, strata } from "../../diorama";
import type { SetPiece } from "../../def";
import { BURST_AT, ORIGINS, depthAt } from "./story";

const hero = (shirt = "#2f9aa8") => buildFigure({ ...HOUSE, shirt });
const shovel = (parent: THREE.Object3D, big = false) => {
  const g = new THREE.Group();
  box(g, 0.04, 0.5 * (big ? 1.3 : 1), 0.04, "#8a6a3c", 0, -0.25, 0);
  box(g, 0.16 * (big ? 1.6 : 1), 0.2, 0.02, "#9aa0a8", 0, -0.45, 0);
  g.rotation.x = Math.PI / 2;
  parent.add(g);
  return g;
};

export class Garden implements SetPiece {
  root = new THREE.Group();
  private h = hero();
  constructor() {
    this.root.position.set(...ORIGINS.garden);
    box(this.root, 9, 0.2, 9, "#6fae4f", 0, -0.2, 0);
    box(this.root, 2.6, 1.6, 1.8, "#d8c9a8", -2.4, 0, -3.2); box(this.root, 2.9, 0.35, 2.1, "#a8432b", -2.4, 1.6, -3.2);
    for (let i = 0; i < 7; i++) box(this.root, 0.08, 0.7, 0.04, "#f2efe6", -3.6 + i * 0.5, 0, -1.8);
    cyl(this.root, 0.12, 1.1, "#7a5230", 2.6, 0, -2.4); cyl(this.root, 0.7, 0.9, "#3f8f4a", 2.6, 1.0, -2.4, 5);
    box(this.root, 0.9, 0.02, 0.9, "#2a1b10", 0, 0, 0.1);
    this.h.root.position.set(0, 0, 0.9); this.root.add(this.h.root);
    shovel(this.h.handR);
  }
  pose(id: number, f: number) {
    if (id === 1) { applyPose(this.h, walkPose(f)); this.h.root.position.set(1.8 - f * 0.055, 0, 0.9 + f * 0.01); this.h.root.rotation.y = -1.3; setFace(this.h.headMount, "neutral"); }
    else {
      const k = poseTrack([{ f: 30, pose: POSES.stand }, { f: 36, pose: POSES.bang, dur: 3 }, { f: 44, pose: POSES.stand, dur: 4 }, { f: 50, pose: POSES.bang, dur: 3 }, { f: 58, pose: POSES.stand, dur: 4 }], f);
      applyPose(this.h, k); this.h.root.position.set(0, 0, 0.9); this.h.root.rotation.y = 0.5; setFace(this.h.headMount, f < 52 ? "smug" : "grin");
    }
  }
}

/** a vertical cutaway of the ground with the hero in a shaft at the depth `depthAt` says */
export class Cutaway implements SetPiece {
  root = new THREE.Group();
  private h = hero();
  private burst = new Burst(0.7, 4);
  private deb = new Debris(16, 4, 22, "#c9ccd2");
  private word = new ComicWord("CLANG!", 1.7, 18);
  private shovel: THREE.Group;
  constructor() {
    this.root.position.set(...ORIGINS.cutaway);
    // two walls of layers with a shaft between them, and a dark panel behind the shaft: the hero stands in the gap
    const LAYERS = [{ h: 0.2, color: "#6fae4f" }, { h: 2.3, color: "#8b5a2b" }, { h: 1.4, color: "#b5651d" }, { h: 2.2, color: "#7a7f87" }, { h: 2.0, color: "#e07a1f" }, { h: 3, color: "#c0392b" }];
    for (const x of [-1.25, 1.25]) { const w = strata(this.root, 1.6, 0.8, LAYERS); w.position.x = x; }
    box(this.root, 0.9, 10.5, 0.1, "#2b1d12", 0, -10.5, -0.35);
    this.root.add(this.h.root, this.burst.root, this.deb.root, this.word.root);
    this.shovel = shovel(this.h.handR, true);
  }
  pose(id: number, f: number, camera: THREE.PerspectiveCamera) {
    const d = depthAt(f);
    this.h.root.position.set(0, -d, 0.15);
    this.h.root.rotation.y = 0;
    let p: Pose = POSES.stand, face: Parameters<typeof setFace>[1] = "neutral";
    if (id === 3 || id === 4) { p = poseTrack([{ f: 60, pose: POSES.bang }, { f: 70, pose: POSES.stand, dur: 4 }, { f: 78, pose: POSES.bang, dur: 3 }, { f: 86, pose: POSES.stand, dur: 4 }], f); face = "smile"; }
    if (id === 5) { p = POSES.shrug; face = "worry"; }
    if (id === 6) { p = poseTrack([{ f: 155, pose: POSES.stand }, { f: 168, pose: POSES.bang, dur: 3 }, { f: 176, pose: POSES.stand, dur: 5 }], f); face = f >= 168 && f < 184 ? "shout" : "grin"; }
    if (id === 7) { p = POSES.slump; face = "worry"; }
    if (id === 8) { p = POSES.flinch; face = "shock"; }
    applyPose(this.h, p); setFace(this.h.headMount, face);
    this.shovel.visible = id <= 6;
    const at = [0.25, -d + 1.55, 0.55] as [number, number, number];
    this.burst.at(BURST_AT, at); this.deb.at(BURST_AT, at); this.word.at(BURST_AT + 1, [0.9, -d + 1.9, 0.9]);
    this.burst.update(f, camera); this.deb.update(f); this.word.update(f, camera);
  }
}

export class Street implements SetPiece {
  root = new THREE.Group();
  private crowd: Crowd;
  private h = hero("#ef6a4a");
  constructor() {
    this.root.position.set(...ORIGINS.crowd);
    box(this.root, 14, 0.2, 14, "#7d8a72", 0, -0.2, -3);
    box(this.root, 1.4, 0.02, 1.0, "#2a1b10", 0, 0, 0.5);
    this.crowd = new Crowd(Crowd.block(18, 9, { z0: -0.6, dx: 0.5, dz: 0.5, rise: 0.1, seed: 21, outfit: randomOutfit, smileRate: 0.5 }), (f, b) => (f > 300 ? dancePose(f + b) : idlePose(f, b)));
    this.root.add(this.crowd.root, this.h.root);
    this.h.root.position.set(0, 0, 1.5); this.h.root.rotation.y = Math.PI;
  }
  pose(id: number, f: number) {
    this.crowd.update(f);
    const cheer = id === 10 && f % 12 < 6;
    applyPose(this.h, id === 9 ? POSES.stand : cheer ? POSES.cheer : POSES.thrust);
    setFace(this.h.headMount, id === 9 ? "smug" : "grin");
    this.h.root.rotation.y = 0;
  }
}

export class Planet implements SetPiece {
  root = new THREE.Group();
  private tiny = hero();
  private tiny2 = hero("#ef6a4a");
  private ball: THREE.Object3D;
  constructor() {
    this.root.position.set(...ORIGINS.planet);
    const cut = new THREE.Group(); cut.position.set(-3, 0, 0); this.root.add(cut);
    discs(cut, [{ r: 1.7, color: "#8b5a2b" }, { r: 1.45, color: "#e07a1f" }, { r: 0.9, color: "#f4b942" }, { r: 0.45, color: "#fff1a8" }]);
    cut.add(this.tiny.root); this.tiny.root.scale.setScalar(0.5); this.tiny.root.position.set(0, -0.25, 0.4);
    const g = new THREE.Group(); g.position.set(3, 0, 0); this.root.add(g);
    this.ball = globe(g, 1.5, { seed: 4 });
    g.add(this.tiny2.root); this.tiny2.root.scale.setScalar(0.45); this.tiny2.root.position.set(0, 1.5, 0);
    this.root.add(flatStars());
  }
  pose(id: number, f: number) {
    applyPose(this.tiny, id === 11 ? POSES.flinch : POSES.lie);
    this.tiny.root.position.y = id === 12 ? -0.1 + Math.sin(f * 0.15) * 0.15 : -0.5;
    setFace(this.tiny.headMount, "shock");
    applyPose(this.tiny2, f % 14 < 7 ? POSES.cheer : idlePose(f)); setFace(this.tiny2.headMount, "grin");
    this.ball.rotation.y = f * 0.01;
  }
}
const flatStars = () => {
  const g = new THREE.Group();
  for (let i = 0; i < 26; i++) { const m = new THREE.Mesh(new THREE.OctahedronGeometry(0.03, 0), flat("#f5f3ee")); m.position.set(((i * 37) % 17) - 8, ((i * 53) % 9) - 4, -3 - ((i * 13) % 4)); g.add(m); }
  return g;
};
export type { Figure };
