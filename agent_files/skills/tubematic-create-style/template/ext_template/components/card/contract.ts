// The template's props contract. schema.json says the same in JSON Schema, and
// it is the one write_scene_config enforces: keep the two in step.
export type PaletteName = "ink" | "paper" | "signal";

export const PALETTES: Record<PaletteName, { ground: string; ink: string; accent: string }> = {
  ink: { ground: "#101418", ink: "#f4f1e8", accent: "#ffb000" },
  paper: { ground: "#f4f1e8", ink: "#16181c", accent: "#d6452f" },
  signal: { ground: "#0b2a4a", ink: "#ffffff", accent: "#39d98a" },
};

export type CardProps = {
  title: string;
  lines: string[];
  /** frame of this scene on which each line appears, one per line */
  lineAt: number[];
  palette: PaletteName;
};
