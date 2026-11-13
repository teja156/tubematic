/*
 * Font loading for the code-drawn character styles (Mid-century How-To,
 * Process Cast, Comic Panels, Puppet History).
 *
 * Every face is bundled in public/fonts and loaded before the first frame, so a
 * renderer with no internet access draws the same picture. A style names its
 * faces once; `useStyleFonts` holds the first frame until they are in
 * document.fonts.
 *
 * Text inside a cached sprite (./sprite.tsx) is drawn by the browser from an
 * SVG image, which cannot see the document's fonts. `fontFaceCss` gives the
 * same faces as @font-face rules with the files inlined as data URLs, for the
 * sprite's own <style>.
 */
import { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender, staticFile } from "remotion";

export type FontFile = { family: string; file: string; weight: string };

const loaded = new Map<string, Promise<void>>();

function loadOne(f: FontFile): Promise<void> {
  const key = `${f.family}|${f.weight}|${f.file}`;
  let job = loaded.get(key);
  if (!job) {
    job = new FontFace(f.family, `url(${staticFile(f.file)}) format("woff2")`, { weight: f.weight })
      .load()
      .then((face) => {
        document.fonts.add(face);
      });
    loaded.set(key, job);
  }
  return job;
}

/** Load the faces before the first frame; a face that will not load fails the render. */
export function useStyleFonts(label: string, fonts: readonly FontFile[]): void {
  const [handle] = useState(() => delayRender(`${label}: loading fonts`));
  useEffect(() => {
    Promise.all(fonts.map(loadOne))
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
    // The font list is fixed for a style.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle]);
}

const inlined = new Map<string, Promise<string>>();

async function dataUrl(file: string): Promise<string> {
  const res = await fetch(staticFile(file));
  if (!res.ok) throw new Error(`font ${file}: HTTP ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return `data:font/woff2;base64,${btoa(bin)}`;
}

/** @font-face rules for `fonts` with each file inlined, for text drawn inside a sprite. */
export function fontFaceCss(fonts: readonly FontFile[]): Promise<string> {
  const key = fonts.map((f) => `${f.family}|${f.weight}|${f.file}`).join(";");
  let job = inlined.get(key);
  if (!job) {
    job = Promise.all(
      fonts.map(async (f) => `@font-face{font-family:'${f.family}';font-weight:${f.weight};src:url(${await dataUrl(f.file)}) format('woff2');}`),
    ).then((rules) => rules.join(""));
    inlined.set(key, job);
  }
  return job;
}
