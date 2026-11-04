// The operator's desk on the porch: telegraph key, sounder, tape register,
// a three-cell glass-jar battery, and the wiring between them.
import * as THREE from "three";
import { mesh, tubeThrough, worldBox } from "../kit/geometry";
import * as T from "../kit/textures";
import { PORCH_H } from "./town";

const lam = (color: number, extra: THREE.MeshLambertMaterialParameters = {}) =>
  new THREE.MeshLambertMaterial({ color, ...extra });

export const DESK = { x: -0.6, z: 1.35, top: PORCH_H + 0.8 };

// flat paper ribbon along a polyline (width along +x)
const ribbon = (pts: THREE.Vector3[], width: number) => {
  const curve = new THREE.CatmullRomCurve3(pts);
  const n = 40;
  const pos: number[] = [];
  const uv: number[] = [];
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    const p = curve.getPoint(i / n);
    pos.push(p.x - width / 2, p.y, p.z, p.x + width / 2, p.y, p.z);
    uv.push(0, i / n, 1, i / n);
    if (i < n) idx.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return { geo: g, end: curve.getPoint(1) };
};

export interface Desk {
  root: THREE.Group;
  lever: THREE.Group; // rotate .rotation.x to click
  sounderArm: THREE.Group;
  keyContact: THREE.Vector3;
  sounderPos: THREE.Vector3;
  terminal: THREE.Vector3; // battery post the lead is plugged into
  keyPost: THREE.Vector3;
  leadMesh: THREE.Mesh; // battery lead, rebuilt per frame
  leadMat: THREE.Material;
  tapeEnd: THREE.Vector3;
  tapeGlow: THREE.MeshLambertMaterial;
}

export const buildDesk = (): Desk => {
  const root = new THREE.Group();
  const wood = new THREE.MeshLambertMaterial({ map: T.planks({ seed: 71, planks: 5, hue: 24, sat: 0.7, light: 0.42 }) });
  const brass = lam(0xffc23a, { emissive: new THREE.Color(0x2a1500) });
  const dark = lam(0x4a2a6a);
  const { x, z, top } = DESK;
  root.add(mesh(worldBox(1.45, 0.07, 0.64, 1), wood, [x, top - 0.035, z]));
  root.add(mesh(worldBox(1.45, 0.76, 0.05, 1), wood, [x, PORCH_H + 0.38, z + 0.29])); // modesty panel
  for (const sx of [-0.7, 0.7]) root.add(mesh(worldBox(0.06, 0.76, 0.6, 1), wood, [x + sx, PORCH_H + 0.38, z]));

  // telegraph key (oversized a little so it reads at phone size)
  const kx = x - 0.12;
  const kz = z - 0.12;
  root.add(mesh(worldBox(0.3, 0.05, 0.16, 0.5), wood, [kx, top + 0.025, kz]));
  root.add(mesh(new THREE.BoxGeometry(0.05, 0.05, 0.05), brass, [kx, top + 0.075, kz]));
  const lever = new THREE.Group();
  lever.position.set(kx, top + 0.1, kz);
  lever.add(mesh(new THREE.BoxGeometry(0.03, 0.025, 0.3), brass, [0, 0, 0.02]));
  lever.add(mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.03, 14), lam(0x8a2a4a), [0, 0.03, 0.16]));
  root.add(lever);
  const keyContact = new THREE.Vector3(kx, top + 0.08, kz + 0.14);
  const keyPost = new THREE.Vector3(kx + 0.12, top + 0.07, kz - 0.04);
  root.add(mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.05, 10), brass, [keyPost.x, keyPost.y, keyPost.z]));

  // sounder: two coils and a clicking arm
  const sx = x + 0.2;
  const sz = z - 0.1;
  root.add(mesh(worldBox(0.26, 0.04, 0.16, 0.5), wood, [sx, top + 0.02, sz]));
  for (const dx of [-0.05, 0.05]) root.add(mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.11, 14), dark, [sx + dx, top + 0.095, sz]));
  const sounderArm = new THREE.Group();
  sounderArm.position.set(sx - 0.11, top + 0.17, sz);
  sounderArm.add(mesh(new THREE.BoxGeometry(0.22, 0.02, 0.03), brass, [0.11, 0, 0]));
  root.add(sounderArm);
  const sounderPos = new THREE.Vector3(sx, top + 0.17, sz);

  // tape register with paper tape curling over the desk front
  const rx = x - 0.5;
  root.add(mesh(worldBox(0.24, 0.16, 0.2, 0.5), wood, [rx, top + 0.08, z - 0.12]));
  root.add(mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.05, 16), lam(0xfff4dd), [rx, top + 0.2, z - 0.12], { rot: [0, 0, Math.PI / 2] }));
  const tape = ribbon(
    [
      new THREE.Vector3(rx, top + 0.15, z - 0.02),
      new THREE.Vector3(rx + 0.02, top + 0.012, z + 0.12),
      new THREE.Vector3(rx + 0.06, top + 0.012, z + 0.26),
      new THREE.Vector3(rx + 0.07, top - 0.08, z + 0.34),
      new THREE.Vector3(rx + 0.05, top - 0.3, z + 0.36),
    ],
    0.035,
  );
  const tapeMat = new THREE.MeshLambertMaterial({ color: 0xfff1d0, side: THREE.DoubleSide });
  root.add(mesh(tape.geo, tapeMat, [0, 0, 0]));
  const tapeGlow = lam(0xff7a2a, { emissive: new THREE.Color(0, 0, 0) });
  const ember = mesh(new THREE.SphereGeometry(0.022, 10, 8), tapeGlow, [tape.end.x, tape.end.y, tape.end.z]);
  ember.userData.noInk = true;
  root.add(ember);

  // battery: three glass jar cells with copper and zinc plates
  const glass = lam(0x55d6ff, { emissive: new THREE.Color(0x0a3050) });
  const liquid = lam(0x2f6bff, { emissive: new THREE.Color(0x061a60) });
  const copper = lam(0xff7a3a);
  const zinc = lam(0xb8c8ff);
  const cells = [x + 0.38, x + 0.52, x + 0.66];
  let terminal = new THREE.Vector3();
  for (const [i, cx] of cells.entries()) {
    const cz = z + 0.02;
    root.add(mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.17, 18), glass, [cx, top + 0.085, cz]));
    root.add(mesh(new THREE.CylinderGeometry(0.061, 0.061, 0.03, 18), liquid, [cx, top + 0.12, cz]));
    root.add(mesh(new THREE.BoxGeometry(0.012, 0.12, 0.06), copper, [cx - 0.022, top + 0.19, cz]));
    root.add(mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.12, 8), zinc, [cx + 0.025, top + 0.19, cz]));
    for (const dx of [-0.022, 0.025]) root.add(mesh(new THREE.SphereGeometry(0.014, 8, 6), brass, [cx + dx, top + 0.255, cz]));
    if (i === 0) terminal = new THREE.Vector3(cx - 0.022, top + 0.26, cz);
    if (i > 0) {
      const a = new THREE.Vector3(cells[i - 1] + 0.025, top + 0.26, cz);
      const b = new THREE.Vector3(cx - 0.022, top + 0.26, cz);
      const mid = a.clone().lerp(b, 0.5).add(new THREE.Vector3(0, 0.05, 0));
      root.add(mesh(tubeThrough([a, mid, b], 0.006, 10), lam(0x8a2a4a), [0, 0, 0]));
    }
  }

  // line wire coming down the facade to the key
  const lineMat = lam(0x3a2560);
  root.add(
    mesh(
      tubeThrough(
        [
          new THREE.Vector3(-2.6, PORCH_H + 3.4, 0.3),
          new THREE.Vector3(-2.2, PORCH_H + 2.9, 0.06),
          new THREE.Vector3(-1.6, PORCH_H + 1.6, 0.06),
          new THREE.Vector3(-1.3, top + 0.05, 0.5),
          new THREE.Vector3(keyPost.x - 0.24, top + 0.03, keyPost.z - 0.02),
          new THREE.Vector3(kx - 0.14, top + 0.06, kz),
        ],
        0.008,
        48,
      ),
      lineMat,
      [0, 0, 0],
    ),
  );

  const leadMat = lam(0xd23a5a);
  const leadMesh = mesh(new THREE.BufferGeometry(), leadMat, [0, 0, 0]);
  root.add(leadMesh);

  return { root, lever, sounderArm, keyContact, sounderPos, terminal, keyPost, leadMesh, leadMat, tapeEnd: tape.end, tapeGlow };
};

// The battery lead: from the key post to wherever its plug currently is.
export const leadGeometry = (keyPost: THREE.Vector3, plug: THREE.Vector3, slack: number) => {
  const mid = keyPost.clone().lerp(plug, 0.5);
  mid.y = Math.max(keyPost.y, plug.y) + 0.06 - slack;
  const q1 = keyPost.clone().lerp(mid, 0.5).add(new THREE.Vector3(0, 0.03, 0.03));
  return tubeThrough([keyPost, q1, mid, plug], 0.007, 24);
};
