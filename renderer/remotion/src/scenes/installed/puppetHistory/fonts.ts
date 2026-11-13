/*
 * The Puppet History faces, apart from the scene so that the sheets and the
 * preview of a video's own props can load them without bundling the scene
 * (which imports every agent-written prop).
 */
import type { FontFile } from "../characterKit/fonts";

export const FONTS: FontFile[] = [
  { family: "Fredoka", file: "fonts/fredoka-latin-700-normal.woff2", weight: "700" },
  { family: "Kalam", file: "fonts/kalam-latin-700-normal.woff2", weight: "700" },
  { family: "IBM Plex Mono", file: "fonts/ibm-plex-mono-latin-700-normal.woff2", weight: "700" },
];
