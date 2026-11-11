/*
 * The Bean Explainer's faces and their loader, apart from the scene so that the
 * prop sheet and the preview of a video's own props can use them without
 * bundling the scene (which imports every agent-written prop).
 *
 * Fonts are bundled in public/fonts and loaded before the first frame, so a
 * renderer with no internet access renders the same picture. Instrument Sans
 * is loaded here for the captions, which the pack points at it.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const ROUND = "Fredoka, 'Arial Rounded MT Bold', system-ui, sans-serif";
export const HAND = "'Patrick Hand', 'Comic Sans MS', cursive";

const FONTS: [family: string, file: string, weight: string][] = [
  ["Fredoka", "fonts/fredoka-latin-600-normal.woff2", "600"],
  ["Fredoka", "fonts/fredoka-latin-700-normal.woff2", "700"],
  ["Patrick Hand", "fonts/patrick-hand-latin-400-normal.woff2", "400"],
  ["Instrument Sans", "fonts/instrument-sans-latin-700-normal.woff2", "700"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadBeanFonts(): Promise<void> {
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

export function useBeanFonts(label: string) {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  useEffect(() => {
    loadBeanFonts()
      .then(() => continueRender(handle))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error(`${label}: font load failed`, err);
        continueRender(handle);
      });
  }, [handle, label]);
}

