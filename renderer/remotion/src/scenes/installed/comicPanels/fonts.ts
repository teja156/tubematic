/*
 * The Comic Panels faces, apart from the scene so that the sheets and the
 * preview of a video's own props can load them without bundling the scene
 * (which imports every agent-written prop).
 */
import type { FontFile } from "../characterKit/fonts";

export const FONTS: FontFile[] = [
  { family: "Bangers", file: "fonts/bangers-latin-400-normal.woff2", weight: "400" },
  { family: "Comic Neue", file: "fonts/comic-neue-latin-700-normal.woff2", weight: "700" },
];
