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
 *
 * Keep in sync: mcp/text_fit.py, which the validators use to refuse a text
 * that cannot fit at the smallest size, and to count wrapped lines. Both run
 * the shared cases in mcp/tests/fixtures/text_fit_contract.json.
 */

function charEm(ch: string): number {
  if (ch === " ") return 0.26;
  // An emoji or other astral character (one code point, two UTF-16 units).
  if ((ch.codePointAt(0) ?? 0) > 0xffff) return 1.25;
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

/** Lines `text` takes wrapped greedily at word breaks in `maxWidth`, a word
 *  wider than a line broken where it reaches the edge. The browser wraps the
 *  same text in at most as many lines. */
export function wrapCount(text: string, size: number, maxWidth: number): number {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return 1;
  const space = estimateWidth(" ", size);
  let lines = 1;
  let used = 0;
  for (const word of words) {
    const w = estimateWidth(word, size);
    if (used > 0 && used + space + w <= maxWidth) {
      used += space + w;
      continue;
    }
    if (used > 0) lines += 1;
    used = 0;
    for (const ch of word) {
      const cw = estimateWidth(ch, size);
      if (used > 0 && used + cw > maxWidth) {
        lines += 1;
        used = 0;
      }
      used += cw;
    }
  }
  return lines;
}
