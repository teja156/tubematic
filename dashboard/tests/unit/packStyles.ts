/**
 * The visual-style list as GET /visual-styles serves it, built from the real
 * style packs (tubematic_core/style_packs/*.json) rather than a copy, so the
 * dashboard tests see whatever styles the API would. vitest.setup.ts makes
 * useVisualStyles() return this in every test; availability is left to the
 * pickers, which work it out from the settings and GPU status each test sets.
 */
import fs from "node:fs";
import path from "node:path";
import type { VisualStyleInfo } from "@/lib/types";

const PACKS_DIR = path.resolve(__dirname, "../../../tubematic_core/style_packs");

interface Pack {
  id: string;
  label: string;
  order: number;
  experimental: boolean;
  canvas: "dark" | "light" | null;
  needs: { openai_key: boolean; gpu: boolean };
  renderer: string;
  mascot?: boolean;
}

const packs: Pack[] = fs
  .readdirSync(PACKS_DIR)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(fs.readFileSync(path.join(PACKS_DIR, f), "utf8")) as Pack)
  .sort((a, b) => a.order - b.order);

export const PACK_STYLES: VisualStyleInfo[] = [
  { id: "auto", label: "Auto", experimental: false, canvas: null, needs: { openai_key: false, gpu: false }, mascot: true },
  ...packs.map((p) => ({
    id: p.id, label: p.label, experimental: p.experimental, canvas: p.canvas, needs: p.needs,
    // as visual_styles.py::public_list serves it
    mascot: p.renderer !== "cartoon_3d" && p.mascot !== false,
  })),
];
