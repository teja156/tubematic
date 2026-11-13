/*
 * Format Packs' faces: Barlow for bubbles, rows, titles and labels, IBM Plex
 * Mono for numbers, dates and the EXAMPLE tag. Bundled in public/fonts and loaded before
 * the first frame, so a renderer with no internet access draws the same
 * picture.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const MONO = "'IBM Plex Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace";
export const SANS = "Barlow, 'Liberation Sans', Arial, sans-serif";

const FONTS: [family: string, file: string, weight: string][] = [
  ["IBM Plex Mono", "fonts/ibm-plex-mono-latin-400-normal.woff2", "400"],
  ["IBM Plex Mono", "fonts/ibm-plex-mono-latin-700-normal.woff2", "700"],
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
export function useFormatFonts(label: string): void {
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
