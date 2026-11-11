/*
 * Case File Story's faces and their loader. Fonts are bundled in public/fonts
 * and loaded before the first frame, so a renderer with no internet access
 * renders the same picture. Instrument Sans is also the captions' face, which
 * the pack points at.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const SANS = "'Instrument Sans', 'Helvetica Neue', Arial, sans-serif";
export const MONO = "'IBM Plex Mono', 'SFMono-Regular', Menlo, monospace";

const FONTS: [family: string, file: string, weight: string][] = [
  ["Instrument Sans", "fonts/instrument-sans-latin-700-normal.woff2", "700"],
  ["IBM Plex Mono", "fonts/ibm-plex-mono-latin-400-normal.woff2", "400"],
  ["IBM Plex Mono", "fonts/ibm-plex-mono-latin-700-normal.woff2", "700"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadCaseFileFonts(): Promise<void> {
  if (!fontsLoaded) {
    fontsLoaded = Promise.all(
      FONTS.map(([family, file, weight]) =>
        new FontFace(family, `url(${staticFile(file)}) format("woff2")`, { weight }).load().then((face) => {
          document.fonts.add(face);
        }),
      ),
    ).then(() => undefined);
  }
  return fontsLoaded;
}

export function useCaseFileFonts(label: string) {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  useEffect(() => {
    loadCaseFileFonts()
      .then(() => continueRender(handle))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error(`${label}: font load failed`, err);
        continueRender(handle);
      });
  }, [handle, label]);
}
