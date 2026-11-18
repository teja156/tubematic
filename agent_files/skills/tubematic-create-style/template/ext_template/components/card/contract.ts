// The template's props contract. schema.json says the same in JSON Schema, and
// it is the one write_scene_config enforces: keep the two in step.
// Every palette is dark: the pack's captions are white with no background, so a light card would hide them.
export type PaletteName = "ink" | "ember" | "signal";

export const PALETTES: Record<PaletteName, { ground: string; ink: string; accent: string }> = {
  ink: { ground: "#101418", ink: "#f4f1e8", accent: "#ffb000" },
  ember: { ground: "#2a1410", ink: "#fbe9dc", accent: "#ff6a3d" },
  signal: { ground: "#0b2a4a", ink: "#ffffff", accent: "#39d98a" },
};

export type CardProps = {
  title: string;
  lines: string[];
  /** frame of this scene on which each line appears, one per line */
  lineAt: number[];
  palette: PaletteName;
};
