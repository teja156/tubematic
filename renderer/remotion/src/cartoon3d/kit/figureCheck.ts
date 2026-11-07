// The deterministic half of the gate for a cast figure (pure, no DOM): names, colours, hats, builds, height.
import { BUILD_HEIGHT, FIGURE_COATS, FIGURE_HATS, FIGURE_HOLDS, type FigureSpec } from "./Figure";

const HEX = /^#[0-9a-fA-F]{6}$/;
export const validateFigure = (name: string, f: unknown): string[] => {
  const errs: string[] = [];
  if (!/^[a-z][A-Za-z0-9]{1,31}$/.test(name)) errs.push(`cast name "${name}" must match ^[a-z][A-Za-z0-9]{1,31}$`);
  if (name === "newsboy" || name === "operator") errs.push(`"${name}" is a fixed cast member`);
  if (!f || typeof f !== "object") return [...errs, "a figure must be an object"];
  const s = f as FigureSpec;
  if (!s.blurb || typeof s.blurb !== "string" || s.blurb.length > 200) errs.push("blurb: 1-200 characters");
  for (const k of ["jacket", "pants", "boots"] as const) if (!HEX.test(String(s[k] ?? ""))) errs.push(`${k}: a #rrggbb colour is required`);
  for (const k of ["cap", "hair", "dress", "buttons", "sash", "moustache"] as const) if (s[k] !== undefined && !HEX.test(String(s[k]))) errs.push(`${k}: #rrggbb`);
  if (s.belt !== undefined && s.belt !== null && !HEX.test(String(s.belt))) errs.push("belt: #rrggbb or null");
  if (s.hat !== undefined && s.hat !== null && !(FIGURE_HATS as readonly string[]).includes(s.hat)) errs.push(`hat: one of ${FIGURE_HATS.join(", ")}, or null`);
  if (s.skin !== undefined && !(typeof s.skin === "number" ? s.skin >= 0 && s.skin <= 3 : HEX.test(String(s.skin)))) errs.push("skin: #rrggbb or 0-3");
  if (s.build !== undefined && !(s.build in BUILD_HEIGHT)) errs.push(`build: one of ${Object.keys(BUILD_HEIGHT).join(", ")}`);
  if (s.height !== undefined && !(s.height >= 0.9 && s.height <= 2.2)) errs.push("height: 0.9-2.2 m");
  if (s.holds !== undefined && !FIGURE_HOLDS.includes(s.holds)) errs.push(`holds: one of ${FIGURE_HOLDS.join(", ")}`);
  if (s.heldColor !== undefined && !HEX.test(String(s.heldColor))) errs.push("heldColor: #rrggbb");
  if (s.coat !== undefined && !(FIGURE_COATS as readonly string[]).includes(s.coat)) errs.push(`coat: one of ${FIGURE_COATS.join(", ")}`);
  return errs;
};
