/*
 * Flat Vector Science's faces and their loader. Inter (the bold capitals of
 * the pills and readouts) and Fredoka (the rounded numbers and the captions,
 * which the pack points at) are bundled in public/fonts and loaded before the
 * first frame, so a renderer with no internet access renders the same picture.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const LABEL = "Inter, 'Helvetica Neue', Arial, sans-serif";
export const ROUND = "Fredoka, 'Nunito', 'Arial Rounded MT Bold', sans-serif";


const FONTS: [family: string, file: string, weight: string][] = [
  ["Inter", "fonts/inter-latin-800-normal.woff2", "800"],
  ["Fredoka", "fonts/fredoka-latin-600-normal.woff2", "600"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadFlatVectorFonts(): Promise<void> {
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
export function useFlatVectorFonts(label: string): boolean {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadFlatVectorFonts()
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
