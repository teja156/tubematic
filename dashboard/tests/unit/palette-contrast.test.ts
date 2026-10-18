/**
 * The secondary text tokens in app/globals.css must stay readable.
 *
 * `--mute` shipped at ~2.4:1 and `--dim` at ~4.2:1 against the dark surfaces:
 * both below WCAG AA's 4.5:1 for normal text, and both used at 10–11px mono,
 * where it matters most. They were fixed at the token, not per call site, and
 * this test keeps them fixed: any later edit that dims either one fails here
 * rather than on someone's eyes.
 *
 * It also pins the four-step hierarchy, so "readable" never becomes "as loud as
 * primary text", and that shadcn's `--muted-foreground` points at `--dim`
 * instead of holding its own hardcoded copy, which is how it drifted before.
 */
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

const css = fs.readFileSync(path.resolve(__dirname, "../../app/globals.css"), "utf8");

function token(name: string): string {
  const m = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`));
  if (!m) throw new Error(`--${name} not found as a #rrggbb value in globals.css`);
  return m[1];
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const SURFACES = ["bg", "panel", "panel-2"];

describe("secondary text tokens", () => {
  for (const text of ["dim", "mute"]) {
    for (const surface of SURFACES) {
      it(`--${text} meets WCAG AA (4.5:1) on --${surface}`, () => {
        expect(contrast(token(text), token(surface))).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  it("keeps the hierarchy ink > ink-2 > dim > mute on every surface", () => {
    for (const surface of SURFACES) {
      const bg = token(surface);
      const [ink, ink2, dim, mute] = ["ink", "ink-2", "dim", "mute"].map((t) => contrast(token(t), bg));
      expect(ink).toBeGreaterThan(ink2);
      expect(ink2).toBeGreaterThan(dim);
      expect(dim).toBeGreaterThan(mute);
    }
  });

  it("--muted-foreground follows --dim rather than holding its own copy", () => {
    const decls = [...css.matchAll(/--muted-foreground:\s*([^;]+);/g)].map((m) => m[1].trim());
    expect(decls.length).toBeGreaterThan(0);
    for (const value of decls) expect(value).toBe("var(--dim)");
  });
});
