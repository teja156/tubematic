/*
 * Storybook Atlas's serif and its loader, apart from the scene so that the
 * model sheet and the prop preview can use them without bundling the scene
 * (which imports every agent-written prop).
 *
 * EB Garamond is bundled in public/fonts and loaded before the first frame, so
 * a renderer with no internet access renders the same picture. It is loaded
 * here for the captions too, which the pack points at it.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

const FONTS: [family: string, file: string, weight: string, style: string][] = [
  ["EB Garamond", "fonts/eb-garamond-latin-400-normal.woff2", "400", "normal"],
  ["EB Garamond", "fonts/eb-garamond-latin-500-normal.woff2", "500", "normal"],
  ["EB Garamond", "fonts/eb-garamond-latin-400-italic.woff2", "400", "italic"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadStorybookFonts(): Promise<void> {
  if (!fontsLoaded) {
    fontsLoaded = Promise.all(
      FONTS.map(([family, file, weight, style]) =>
        new FontFace(family, `url(${staticFile(file)}) format("woff2")`, { weight, style }).load().then((face) => {
          document.fonts.add(face);
        }),
      ),
    ).then(() => undefined);
  }
  return fontsLoaded;
}

export function useStorybookFonts(label: string) {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  useEffect(() => {
    loadStorybookFonts()
      .then(() => continueRender(handle))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error(`${label}: font load failed`, err);
        continueRender(handle);
      });
  }, [handle, label]);
}
