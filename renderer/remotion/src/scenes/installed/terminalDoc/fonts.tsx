/*
 * Terminal Doc's faces and their loader, apart from the scene so that the
 * preview of a video's own moves can load them without bundling the scene
 * (which imports every agent-written move).
 *
 * Bundled in public/fonts and loaded before the first frame, so a renderer
 * with no internet access renders the same picture. The LOG captions use the
 * same faces, which the pack points at.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

const FONTS: [family: string, file: string, weight: string][] = [
  ["IBM Plex Mono", "fonts/ibm-plex-mono-latin-400-normal.woff2", "400"],
  ["IBM Plex Mono", "fonts/ibm-plex-mono-latin-700-normal.woff2", "700"],
  ["VT323", "fonts/vt323-latin-400-normal.woff2", "400"],
];
let fontsLoaded: Promise<void> | null = null;
export function loadTerminalFonts(): Promise<void> {
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

/** Loads the faces before the first frame; true once they are in (or failed,
 *  so a canvas that draws text knows when to draw it again). */
export function useTerminalFonts(label: string): boolean {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  const [ready, setReady] = useState(false);
  useEffect(() => {
    loadTerminalFonts()
      .then(() => setReady(true))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallbacks rather than hang, and say so in the render log.
        console.error(`${label}: font load failed`, err);
        setReady(true);
      });
  }, [label]);
  // Released only after the commit that drew with the faces: a canvas child
  // draws its text in a layout effect, which runs before this one.
  useEffect(() => {
    if (ready) continueRender(handle);
  }, [ready, handle]);
  return ready;
}
