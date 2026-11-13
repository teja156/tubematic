/*
 * The paper styles' bundled faces (TMDEV-228..231) and one loader for them.
 * Every font is a woff2 in public/fonts with its licence beside it, loaded
 * before the first frame, so a renderer with no internet access renders the
 * same picture: @remotion/google-fonts would fetch at render time.
 */
import { useEffect, useState } from "react";
import { continueRender, delayRender, staticFile } from "remotion";

export type FontFile = [family: string, file: string, weight: string, style?: string];

const loaded = new Map<string, Promise<void>>();

/** Load each face once per page; a second scene asking for it waits on the same promise. */
export function loadFonts(files: FontFile[]): Promise<void> {
  return Promise.all(
    files.map(([family, file, weight, style]) => {
      const key = `${family}|${file}`;
      let p = loaded.get(key);
      if (!p) {
        p = new FontFace(family, `url(${staticFile(file)}) format("woff2")`, { weight, style: style ?? "normal" })
          .load()
          .then((face) => {
            document.fonts.add(face);
          });
        loaded.set(key, p);
      }
      return p;
    }),
  ).then(() => undefined);
}

/** Hold the render until the faces are in. A face that will not load renders
 *  with its fallbacks and says so in the render log, rather than hang. */
export function useFonts(label: string, files: FontFile[]) {
  const [handle] = useState(() => delayRender(`${label}: loading bundled fonts`));
  useEffect(() => {
    loadFonts(files)
      .then(() => continueRender(handle))
      .catch((err) => {
        console.error(`${label}: font load failed`, err);
        continueRender(handle);
      });
    // the file list is a module constant of each style
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle, label]);
}
