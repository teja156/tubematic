// Level 2: one generated image, wrapped on a cyclorama shell the TEMPLATE owns.
// The agent supplies the picture; radius, height and centre are the set's.
import * as THREE from "three";
import type { WorldSpec } from "./worldKit";

export interface Cyc {
  mesh: THREE.Mesh;
  setTod: (fogColor: THREE.Color, tod: number) => void;
}

/** Mirrored wrapping makes the seam match without asking the image model for a
 *  tileable panorama, which it cannot reliably produce. */
export const makeCyc = (tex: THREE.Texture, o: NonNullable<WorldSpec["backdrop"]>): Cyc => {
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.MirroredRepeatWrapping;
  tex.repeat.set(o.repeat, 1);
  tex.anisotropy = 4;
  const mat = new THREE.MeshBasicMaterial({
    map: tex,
    transparent: true,
    depthWrite: false,
    // The scene fog would erase anything this far out; the painting carries its
    // own light and is tinted toward the frame's fog colour by hand instead.
    fog: false,
    side: THREE.BackSide,
  });
  const m = new THREE.Mesh(new THREE.CylinderGeometry(o.radius, o.radius, o.height, 96, 1, true), mat);
  m.position.set(0, o.y, 0);
  m.renderOrder = -1;
  // Soft hazy ridges carry no ink line — real atmospheric distance has none.
  m.userData.noInk = true;
  return {
    mesh: m,
    setTod: (fogColor, tod) => {
      mat.color.setRGB(1, 1, 1).lerp(fogColor, 0.35 + 0.4 * tod);
      mat.color.multiplyScalar(1 - 0.3 * tod);
    },
  };
};
