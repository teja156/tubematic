/*
 * Types for the parts of Shiki that Code Scenes uses. Shiki ships its types
 * behind package `exports`, which this project's TypeScript resolution
 * ("module": "commonjs") does not read; the bundler and vitest resolve the
 * real modules. Keep to what tokens.ts calls.
 */
declare module "shiki/core" {
  export type ThemeRegistrationAny = {
    name?: string;
    type?: "dark" | "light";
    fg?: string;
    bg?: string;
    tokenColors?: { scope?: string | string[]; settings: { foreground?: string; fontStyle?: string } }[];
    [key: string]: unknown;
  };
  export type ThemedTokenBase = { content: string; color?: string };
  export interface HighlighterCore {
    codeToTokensBase(code: string, options: { lang: string; theme: string }): ThemedTokenBase[][];
  }
  export function createHighlighterCoreSync(options: {
    themes: ThemeRegistrationAny[];
    langs: unknown[];
    engine: unknown;
  }): HighlighterCore;
}

declare module "shiki/engine/javascript" {
  export function createJavaScriptRegexEngine(): unknown;
}

declare module "@shikijs/langs/*" {
  const lang: unknown[];
  export default lang;
}

declare module "@shikijs/themes/*" {
  import type { ThemeRegistrationAny } from "shiki/core";
  const theme: ThemeRegistrationAny;
  export default theme;
}
