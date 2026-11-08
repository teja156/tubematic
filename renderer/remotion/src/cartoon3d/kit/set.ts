// Shared bits for the sets: the SetPiece contract world.ts drives, ground quads, the set's local frame.
import * as THREE from "three";
import { V } from "./build";

export interface SetPiece {
  root: THREE.Group;
  /** pose everything that moves for shot `id` at frame f */
  pose(id: number, f: number, cam: THREE.PerspectiveCamera): void;
}
/** horizontal quad facing up at height y covering x0..x1, z0..z1, uv tiled every `tile` metres */
export function quadUp(x0: number, x1: number, z0: number, z1: number, y: number, tile = 8) {
  const g = new THREE.BufferGeometry(), u = (x1 - x0) / tile, v = (z1 - z0) / tile;
  g.setAttribute("position", new THREE.Float32BufferAttribute([x0, y, z1, x1, y, z1, x1, y, z0, x0, y, z1, x1, y, z0, x0, y, z0], 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0], 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, u, 0, u, v, 0, 0, u, v, 0, v], 2));
  return g;
}
/** a translation matrix (sets are built at the origin and moved to their place in the world) */
export const at = (x: number, y: number, z: number) => new THREE.Matrix4().makeTranslation(x, y, z);
export { V };
