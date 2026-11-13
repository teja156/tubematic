/*
 * Isometric Infographic's face and its loader. Jost (the caps titles, the pins,
 * the readout and the caption card, which the pack points at) is bundled in
 * public/fonts and loaded before the first frame, so a renderer with no
 * internet access renders the same picture.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const JOST = "Jost, 'Futura', 'Century Gothic', sans-serif";


const FONTS: [family: string, file: string, weight: string][] = [
  ["Jost", "fonts/jost-latin-400-normal.woff2", "400"],
  ["Jost", "fonts/jost-latin-500-normal.woff2", "500"],
  ["Jost", "fonts/jost-latin-600-normal.woff2", "600"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadIsometricFonts(): Promise<void> {
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
export function useIsometricFonts(label: string): boolean {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadIsometricFonts()
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
