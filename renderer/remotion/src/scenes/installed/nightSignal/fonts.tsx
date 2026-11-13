/*
 * Night Signal's face and its loader. Montserrat is bundled in public/fonts
 * and loaded before the first frame, so a renderer with no internet access
 * renders the same picture; the canvas draws its card text with it, and the
 * captions (the pack points at it) and the HUD use it too.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";


const FONTS: [family: string, file: string, weight: string][] = [
  ["Montserrat", "fonts/montserrat-latin-600-normal.woff2", "600"],
  ["Montserrat", "fonts/montserrat-latin-700-normal.woff2", "700"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadNightSignalFonts(): Promise<void> {
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

/** Loads the face before the first frame; true once it is in (the canvas redraws then). */
export function useNightSignalFonts(label: string): boolean {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadNightSignalFonts()
      .then(() => {
        setReady(true);
        continueRender(handle);
      })
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error(`${label}: font load failed`, err);
        setReady(true);
        continueRender(handle);
      });
  }, [handle, label]);
  return ready;
}
