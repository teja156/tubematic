/*
 * The Mid-century How-To faces, apart from the scene so that the sheets and the
 * preview of a video's own props can load them without bundling the scene
 * (which imports every agent-written prop).
 */
import type { FontFile } from "../characterKit/fonts";

export const FONTS: FontFile[] = [
  { family: "Alfa Slab One", file: "fonts/alfa-slab-one-latin-400-normal.woff2", weight: "400" },
  { family: "Oleo Script", file: "fonts/oleo-script-latin-700-normal.woff2", weight: "700" },
  { family: "Jost", file: "fonts/jost-latin-500-normal.woff2", weight: "500" },
  { family: "Jost", file: "fonts/jost-latin-600-normal.woff2", weight: "600" },
];
