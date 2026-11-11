/*
 * Under the Hood's faces and their loader. Fonts are bundled in public/fonts
 * and loaded before the first frame, so a renderer with no internet access
 * renders the same picture. Space Grotesk is also the captions' face, which
 * the pack points at: the caption layer draws the spoken word at 700 and the
 * earlier words at 400.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export const SANS = "'Space Grotesk', 'Helvetica Neue', Arial, sans-serif";
export const MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, monospace";

const FONTS: [family: string, file: string, weight: string][] = [
  ["Space Grotesk", "fonts/space-grotesk-latin-400-normal.woff2", "400"],
  ["Space Grotesk", "fonts/space-grotesk-latin-700-normal.woff2", "700"],
  ["JetBrains Mono", "fonts/jetbrains-mono-latin-500-normal.woff2", "500"],
  ["JetBrains Mono", "fonts/jetbrains-mono-latin-700-normal.woff2", "700"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadUthFonts(): Promise<void> {
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

export function useUthFonts(label: string) {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  useEffect(() => {
    loadUthFonts()
      .then(() => continueRender(handle))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error(`${label}: font load failed`, err);
        continueRender(handle);
      });
  }, [handle, label]);
}
