/**
 * Tests for the visual-style helpers in lib/visualStyles.
 *
 * The list comes from the style packs (GET /visual-styles); PACK_STYLES is
 * built from the real pack files. A style that needs an OpenAI key (Illustrated
 * draws its characters with OpenAI, the one provider with transparent output)
 * or a working GPU (Cartoon 3D) is disabled, with the reason, when the install
 * cannot make it. GET /settings masks every secret to "" when unset, so
 * set-versus-unset is readable without seeing the key.
 */
import { describe, expect, it } from "vitest";
import { cartoon3dAvailable, illustratedAvailable, previewableRows, previewUrls, routeLabel, styleGroups, styleLabel, videoStyleId, videoStyleLabel } from "@/lib/visualStyles";
import { INSERT_IDS, PACK_STYLES } from "./packStyles";

describe("illustratedAvailable", () => {
  it("is false when the masked key is empty or missing", () => {
    expect(illustratedAvailable({ openai_api_key: "" })).toBe(false);
    expect(illustratedAvailable({})).toBe(false);
  });

  it("is true for any masked value", () => {
    expect(illustratedAvailable({ openai_api_key: "••••••••abcd" })).toBe(true);
  });

  it("is true when settings have not loaded, leaving the API to refuse", () => {
    expect(illustratedAvailable(undefined)).toBe(true);
    expect(illustratedAvailable(null)).toBe(true);
  });
});

const values = (gs: ReturnType<typeof styleGroups>) => gs.flatMap((g) => g.rows.map((r) => r.value));
const unchoosable = (gs: ReturnType<typeof styleGroups>) => gs.flatMap((g) => g.rows).filter((r) => !r.choosable).map((r) => r.value);
const row = (gs: ReturnType<typeof styleGroups>, v: string) => gs.flatMap((g) => g.rows).find((r) => r.value === v)!;

describe("styleGroups", () => {
  it("lists every style: Auto first, then 2D, then 3D, each group in pack order", () => {
    const gs = styleGroups(PACK_STYLES, true);
    expect(gs.map((g) => g.key)).toEqual(["top", "2d", "3d"]);
    expect(gs[0].rows.map((r) => r.value)).toEqual(["auto"]);
    const pack = PACK_STYLES.filter((s) => s.id !== "auto");
    expect(gs[1].rows.map((r) => r.value)).toEqual(pack.filter((s) => s.dimension === "2d").map((s) => s.id));
    expect(gs[2].rows.map((r) => r.value)).toEqual(pack.filter((s) => s.dimension === "3d").map((s) => s.id));
    expect([...values(gs)].sort()).toEqual(PACK_STYLES.map((s) => s.id).sort());
  });

  it("takes the group and the GPU tag from the pack fields, never a list here", () => {
    const gs = styleGroups(PACK_STYLES, true, { status: "working" });
    expect(gs.find((g) => g.key === "3d")!.rows.map((r) => r.value))
      .toEqual(PACK_STYLES.filter((s) => s.dimension === "3d").map((s) => s.id));
    expect(gs.flatMap((g) => g.rows).filter((r) => r.gpu).map((r) => r.value))
      .toEqual(PACK_STYLES.filter((s) => s.needs.gpu).map((s) => s.id));
    // Low-Poly Skit is a 3D style that needs no GPU, so it carries no GPU tag and is choosable with none
    expect(row(gs, "cartoon_3d").gpu).toBe(true);
    expect(row(gs, "low_poly_skit").gpu).toBe(false);
    expect(row(styleGroups(PACK_STYLES, true, { status: "none" }), "low_poly_skit").choosable).toBe(true);
    expect(row(styleGroups(PACK_STYLES, true, { status: "none" }), "cartoon_3d").choosable).toBe(false);
    expect(row(gs, "cartoon_3d").experimental).toBe(true);
    expect(row(gs, "system_flow").experimental).toBe(false);
    expect(row(gs, "storybook_atlas").preview).toBe("storybook_atlas");
    expect(row(gs, "auto").preview).toBeNull();
  });

  it("lists insert styles in their own group, last, and never lets them be picked", () => {
    const styles = PACK_STYLES.map((s) => (INSERT_IDS.includes(s.id) ? { ...s, role: "insert" as const } : s));
    const gs = styleGroups(styles, true, { status: "working" });
    expect(gs.map((g) => g.key)).toEqual(["top", "2d", "3d", "insert"]);
    expect(INSERT_IDS).toEqual(expect.arrayContaining(["system_flow", "terminal_doc", "code_scenes", "format_packs"]));
    expect(gs[3].rows.map((r) => r.value).sort()).toEqual([...INSERT_IDS].sort());
    expect(gs[1].rows.map((r) => r.value)).not.toContain("system_flow");
    expect(unchoosable(gs).sort()).toEqual([...INSERT_IDS].sort());
    expect(row(gs, "system_flow").preview).toBe("system_flow");
  });

  it("counts a style an older API sends without a dimension or role as a 2D main style", () => {
    const old = PACK_STYLES.map(({ dimension: _d, role: _r, ...rest }) => rest);
    const gs = styleGroups(old, true);
    expect(gs.map((g) => g.key)).toEqual(["top", "2d"]);
    expect(unchoosable(gs)).toEqual([]);
  });

  it("makes the styles that need an OpenAI key unpickable, and says why, without one", () => {
    const gs = styleGroups(PACK_STYLES, false);
    const needKey = PACK_STYLES.filter((s) => s.needs.openai_key).map((s) => s.id);
    expect(needKey).toEqual(expect.arrayContaining(["illustrated", "under_the_hood"]));
    expect(unchoosable(gs).sort()).toEqual([...needKey].sort());
    expect(row(gs, "illustrated").why).toBe("needs an OpenAI key");
  });

  it("changes nothing when everything is available", () => {
    expect(unchoosable(styleGroups(PACK_STYLES, true, { status: "working" }))).toEqual([]);
  });

  it("offers only the value it holds until the list has loaded", () => {
    const gs = styleGroups(null, true, null, "stick");
    expect(values(gs)).toEqual(["stick"]);
    expect(gs[0].rows[0].label).toBe("stick");
    expect(styleGroups(null, true, null, "")).toEqual([]);
  });
});

describe("previewableRows", () => {
  it("is every style with a preview, in picker order, inserts included", () => {
    const styles = PACK_STYLES.map((s) => (s.id === "system_flow" ? { ...s, role: "insert" as const } : s));
    const rows = previewableRows(styleGroups(styles, true));
    expect(rows.map((r) => r.value)).not.toContain("auto");
    expect(rows[rows.length - 1].value).toBe("system_flow");
    expect(rows).toHaveLength(PACK_STYLES.length - 1);
  });
});

describe("previewUrls", () => {
  it("points at the files the dashboard serves", () => {
    expect(previewUrls("whiteboard")).toEqual({ video: "/style-previews/whiteboard.mp4", poster: "/style-previews/whiteboard.webp" });
  });
  it("points an installed external style at its package, through the dashboard's preview route", () => {
    expect(previewUrls("ext_paper", true)).toEqual({
      video: "/external-style-previews/ext_paper/preview.mp4", poster: "/external-style-previews/ext_paper/preview.webp" });
  });
});

describe("cartoon3dAvailable", () => {
  it("is true only while the renderer's GPU probe says working", () => {
    expect(cartoon3dAvailable({ status: "working" })).toBe(true);
    expect(cartoon3dAvailable({ status: "not_usable" })).toBe(false);
    expect(cartoon3dAvailable({ status: "not_configured" })).toBe(false);
    expect(cartoon3dAvailable({ status: "unknown" })).toBe(false);
  });

  it("is true when the GPU status has not loaded, leaving the API to refuse", () => {
    expect(cartoon3dAvailable(undefined)).toBe(true);
    expect(cartoon3dAvailable(null)).toBe(true);
  });
});

describe("styleGroups with the GPU status", () => {
  it("makes the GPU-only styles unpickable and says why without a working GPU", () => {
    const gs = styleGroups(PACK_STYLES, true, { status: "not_usable" });
    expect(unchoosable(gs)).toEqual(["cartoon_3d"]);
    expect(row(gs, "cartoon_3d").why).toBe("needs a working GPU");
  });

  it("tells an untested GPU apart from a missing one", () => {
    expect(row(styleGroups(PACK_STYLES, true, { status: "unknown" }), "cartoon_3d").why).toBe("GPU not tested yet");
  });

  it("leaves GPU styles pickable while the GPU is working or the status is unloaded", () => {
    expect(unchoosable(styleGroups(PACK_STYLES, true, { status: "working" }))).toEqual([]);
    expect(unchoosable(styleGroups(PACK_STYLES, true, null))).toEqual([]);
  });

  it("makes every style that needs an OpenAI key or a GPU unpickable when neither is there", () => {
    expect(unchoosable(styleGroups(PACK_STYLES, false, { status: "not_configured" })).sort())
      .toEqual(PACK_STYLES.filter((s) => s.needs.openai_key || s.needs.gpu).map((s) => s.id).sort());
  });
});

describe("styleLabel", () => {
  it("names a style by its pack label", () => {
    expect(styleLabel("stick", PACK_STYLES)).toBe("Stick Explainer");
    expect(styleLabel("system_flow", PACK_STYLES)).toBe("System Flow");
    expect(styleLabel("", PACK_STYLES)).toBe("Auto");
  });

  it("shows a value it does not know as itself", () => {
    expect(styleLabel("from_a_newer_backend", PACK_STYLES)).toBe("from_a_newer_backend");
    expect(styleLabel("stick", null)).toBe("stick");
  });
});

describe("videoStyleLabel with a resolved renderer", () => {
  it("names the world auto settled on before any canvas", () => {
    expect(videoStyleLabel({ visual_style: "auto", resolved_visual_style: "", resolved_renderer: "cartoon_3d" }, PACK_STYLES)).toBe("Auto — Cartoon 3D (experimental)");
    expect(videoStyleLabel({ visual_style: "auto", resolved_visual_style: "dark", resolved_renderer: "dom" }, PACK_STYLES)).toBe("Auto — dark canvas");
    expect(videoStyleLabel({ visual_style: "cartoon_3d", resolved_visual_style: "", resolved_renderer: "" }, PACK_STYLES)).toBe("Cartoon 3D (experimental)");
    expect(videoStyleLabel({ visual_style: "system_flow", resolved_visual_style: "", resolved_renderer: "" }, PACK_STYLES)).toBe("System Flow");
  });
});

describe("videoStyleLabel with Auto's style pick (TMDEV-203)", () => {
  const v = (visual_style: string, style_pick: string, resolved_visual_style = "") =>
    ({ visual_style, style_pick, resolved_visual_style, resolved_renderer: "" as const });

  it("marks a style Auto picked as automatic", () => {
    expect(videoStyleLabel(v("system_flow", "system_flow"), PACK_STYLES)).toBe("Auto — System Flow");
  });

  it("names mixed scenes, and its canvas once chosen", () => {
    expect(videoStyleLabel(v("auto", "scenes"), PACK_STYLES)).toBe("Auto — Mixed scenes");
    expect(videoStyleLabel(v("auto", "scenes", "light"), PACK_STYLES)).toBe("Auto — Mixed scenes, light canvas");
  });

  it("reads a person's choice and an undecided video as before", () => {
    expect(videoStyleLabel(v("system_flow", ""), PACK_STYLES)).toBe("System Flow");
    expect(videoStyleLabel(v("auto", ""), PACK_STYLES)).toBe("Auto (not yet chosen)");
    expect(videoStyleLabel(v("auto", "", "dark"), PACK_STYLES)).toBe("Auto — dark canvas");
  });

  it("labels a routing outcome", () => {
    expect(routeLabel("scenes", PACK_STYLES)).toBe("Mixed scenes");
    expect(routeLabel("system_flow", PACK_STYLES)).toBe("System Flow");
  });
});

describe("videoStyleId", () => {
  it("names the style the frozen row shows, for its preview", () => {
    expect(videoStyleId({ visual_style: "stick", resolved_renderer: "", style_pick: "" })).toBe("stick");
    // Auto's pick is written into visual_style; a pre-pick Auto video names none yet
    expect(videoStyleId({ visual_style: "auto", resolved_renderer: "", style_pick: "" })).toBe("");
    expect(videoStyleId({ visual_style: "auto", resolved_renderer: "", style_pick: "whiteboard" })).toBe("whiteboard");
    // the mixed scene system has no pack, so no preview
    expect(videoStyleId({ visual_style: "auto", resolved_renderer: "dom", style_pick: "scenes" })).toBe("");
    expect(videoStyleId({ visual_style: "auto", resolved_renderer: "cartoon_3d", style_pick: "" })).toBe("cartoon_3d");
  });
});
