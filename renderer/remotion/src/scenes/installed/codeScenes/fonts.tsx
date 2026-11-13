/*
 * Code Scenes' faces: JetBrains Mono for code and output, Barlow for the tag,
 * the step label and the callout. Bundled in public/fonts and loaded before
 * the first frame, so a renderer with no internet access draws the same
 * picture.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const MONO = "'JetBrains Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace";
export const SANS = "Barlow, 'Liberation Sans', Arial, sans-serif";

const FONTS: [family: string, file: string, weight: string][] = [
  ["JetBrains Mono", "fonts/jetbrains-mono-latin-500-normal.woff2", "500"],
  ["JetBrains Mono", "fonts/jetbrains-mono-latin-700-normal.woff2", "700"],
  ["Barlow", "fonts/barlow-latin-600-normal.woff2", "600"],
  ["Barlow", "fonts/barlow-latin-700-normal.woff2", "700"],
];
let loaded: Promise<void> | null = null;
function loadFonts(): Promise<void> {
  if (!loaded) {
    loaded = Promise.all(
      FONTS.map(([family, file, weight]) =>
        new FontFace(family, `url(${staticFile(file)}) format("woff2")`, { weight }).load().then((face) => {
          document.fonts.add(face);
        }),
      ),
    ).then(() => undefined);
  }
  return loaded;
}

/** Holds the render until the faces are in (or failed, logged). */
export function useCodeFonts(label: string): void {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadFonts()
      .then(() => setReady(true))
      .catch((err) => {
        console.error(`${label}: font load failed`, err);
        setReady(true);
      });
  }, [label]);
  useEffect(() => {
    if (ready) continueRender(handle);
  }, [ready, handle]);
}
