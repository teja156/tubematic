import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { buildFigure } from "./figure";
import { applyPose, lerpPose, poseTrack, POSES, snapK } from "./poses";
import { dancePose, footfalls, idlePose, STEP_FRAMES, walkPose } from "./cycles";

describe("applyPose", () => {
  it("raising an arm forward lifts the hand; the left and right arms mirror", () => {
    const fig = buildFigure();
    applyPose(fig, { shL: [Math.PI / 2, 0], shR: [Math.PI / 2, 0] });
    fig.root.updateMatrixWorld(true);
    const l = new THREE.Vector3(), r = new THREE.Vector3();
    fig.handL.getWorldPosition(l); fig.handR.getWorldPosition(r);
    expect(l.z).toBeGreaterThan(0.1);          // forward is +z
    expect(l.z).toBeCloseTo(r.z);
    expect(l.x).toBeCloseTo(-r.x);
  });
  it("out moves each hand away from the body on its own side", () => {
    const fig = buildFigure();
    applyPose(fig, POSES.stand);
    fig.root.updateMatrixWorld(true);
    const l = new THREE.Vector3(), r = new THREE.Vector3();
    fig.handL.getWorldPosition(l); fig.handR.getWorldPosition(r);
    const rest = l.x;
    applyPose(fig, { shL: [0, 0.8], shR: [0, 0.8] });
    fig.root.updateMatrixWorld(true);
    fig.handL.getWorldPosition(l); fig.handR.getWorldPosition(r);
    expect(Math.abs(l.x)).toBeGreaterThan(Math.abs(rest));
    expect(l.x).toBeGreaterThan(0); expect(r.x).toBeLessThan(0);
  });
  it("lie lays the figure on its back, head toward -z, a little above the floor", () => {
    const fig = buildFigure();
    applyPose(fig, POSES.lie);
    fig.root.updateMatrixWorld(true);
    const head = new THREE.Vector3(); fig.headMount.getWorldPosition(head);
    expect(head.z).toBeLessThan(-0.7);
    expect(head.y).toBeLessThan(0.2);
    expect(head.y).toBeGreaterThan(0);
  });
  it("sit puts the feet on the floor", () => {
    const fig = buildFigure();
    applyPose(fig, POSES.sit);
    fig.root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(fig.root);
    expect(box.min.y).toBeGreaterThan(-0.02);
    expect(box.min.y).toBeLessThan(0.03);
  });
  it("a pose leaves out what it does not name: at rest", () => {
    const fig = buildFigure();
    applyPose(fig, POSES.cheer);
    applyPose(fig, {});
    expect(fig.joints.shoulderL.rotation.x).toBeCloseTo(0);
    expect(fig.body.rotation.x).toBeCloseTo(0);
  });
});

describe("snaps", () => {
  it("land in the frames given: 0 before, 1 at the end, no anticipation", () => {
    expect(snapK(9, 10, 3)).toBe(0);
    expect(snapK(10, 10, 3)).toBe(0);
    expect(snapK(13, 10, 3)).toBe(1);
    expect(snapK(11, 10, 3)).toBeGreaterThan(0.5);   // ease-out: most of the move in the first frame or two
  });
  it("a track holds, then snaps into the next pose on its key", () => {
    const keys = [{ f: 0, pose: POSES.stand }, { f: 20, pose: POSES.thrust, dur: 2 }];
    expect(poseTrack(keys, 19).shL).toEqual(POSES.stand.shL);
    expect(poseTrack(keys, 22).shL?.[0]).toBeCloseTo(3.05);
  });
  it("lerp blends numbers and pairs, and a missing key counts as rest", () => {
    const m = lerpPose({ lean: 0.2, shL: [1, 0] }, { shL: [3, 1] }, 0.5);
    expect(m.lean).toBeCloseTo(0.1);
    expect(m.shL).toEqual([2, 0.5]);
  });
});

describe("cycles", () => {
  it("a step lands every STEP_FRAMES, offset from the walk's start", () => {
    expect(STEP_FRAMES).toBe(11);
    expect(footfalls(0, 60, 0)).toEqual([6, 17, 28, 39, 50]);
    expect(footfalls(30, 60, 0)).toEqual([39, 50]);
    expect(footfalls(0, 5, 0)).toEqual([]);
  });
  it("the walk is periodic over two steps", () => {
    const a = walkPose(3), b = walkPose(3 + STEP_FRAMES * 2);
    expect(a.hipL?.[0]).toBeCloseTo(b.hipL?.[0] as number);
    expect(walkPose(0).hipL?.[0]).toBeCloseTo(0);
  });
  it("the legs swing in opposition", () => {
    const p = walkPose(4);
    expect((p.hipL as number[])[0]).toBeCloseTo(-(p.hipR as number[])[0]);
  });
  it("the jig alternates its knee lifts every 5 frames and loops every 10", () => {
    expect(dancePose(2).knL).toBeGreaterThan(dancePose(2).knR as number);
    expect(dancePose(7).knR).toBeGreaterThan(dancePose(7).knL as number);
    expect(dancePose(3).knL).toBeCloseTo(dancePose(13).knL as number);
  });
  it("idles differ by seed", () => {
    expect(Math.abs((idlePose(10, 0).y as number) - (idlePose(10, 3).y as number))).toBeGreaterThan(1e-3);
  });
});
