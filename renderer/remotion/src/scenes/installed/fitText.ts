/*
 * A one-line text's width in Barlow 700, estimated from the shape of each
 * character, and the largest font size at which it fits a width. Used where a
 * single line of agent text sits in a fixed box (Code Scenes' error callout,
 * Format Packs' quiz options and chat title): the validators cap these by
 * character count, and a count cannot tell "iiii" from "WWWW", so the line
 * shrinks to fit instead of running out of its box.
 *
 * The widths are on the wide side of Barlow's real advances, so an estimate
 * never comes out narrower than the text. Pure, so every frame gets the same
 * size.
 */

function charEm(ch: string): number {
  if (ch === " ") return 0.26;
  if ("iIjlt.,:;'!|`".includes(ch)) return 0.3;
  if ("fr()[]{}\"/\\-".includes(ch)) return 0.38;
  if ("MWmw@%".includes(ch)) return 0.92;
  if (/[A-Z]/.test(ch)) return 0.66;
  if (/[0-9]/.test(ch)) return 0.58;
  if (/[a-z]/.test(ch)) return 0.55;
  return 0.7;
}

/** The text's width in pixels at `fontSize`, with letter spacing in pixels. */
export function estimateWidth(text: string, fontSize: number, letterSpacing = 0): number {
  let em = 0;
  for (const ch of text) em += charEm(ch);
  return em * fontSize + letterSpacing * [...text].length;
}

/** The largest whole font size up to `base` at which `text` fits `maxWidth`,
 *  never under `min`. */
export function fitFontSize(text: string, maxWidth: number, base: number, min: number, letterSpacing = 0): number {
  for (let size = base; size > min; size--) {
    if (estimateWidth(text, size, letterSpacing) <= maxWidth) return size;
  }
  return min;
}
