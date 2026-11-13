/*
 * The Process Cast faces, apart from the scene so that the sheets and the
 * preview of a video's own props can load them without bundling the scene
 * (which imports every agent-written prop).
 */
import type { FontFile } from "../characterKit/fonts";

export const FONTS: FontFile[] = [
  { family: "JetBrains Mono", file: "fonts/jetbrains-mono-latin-700-normal.woff2", weight: "700" },
  { family: "Nunito", file: "fonts/nunito-latin-800-normal.woff2", weight: "800" },
];
