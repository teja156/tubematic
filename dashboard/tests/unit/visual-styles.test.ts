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
import { cartoon3dAvailable, illustratedAvailable, routeLabel, styleLabel, styleOptions, videoStyleLabel } from "@/lib/visualStyles";
import { PACK_STYLES } from "./packStyles";

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

describe("styleOptions", () => {
  it("offers every style, Auto first, in pack order", () => {
    const values = styleOptions(PACK_STYLES, true).map((o) => o.value);
    expect(values[0]).toBe("auto");
    expect(values).toEqual(PACK_STYLES.map((s) => s.id));
    expect(values).toEqual(expect.arrayContaining(["motion_graphics", "stick", "illustrated", "cartoon_3d", "system_flow"]));
  });

  it("disables only the styles that need an OpenAI key, and says why, without one", () => {
    const opts = styleOptions(PACK_STYLES, false);
    const needKey = PACK_STYLES.filter((s) => s.needs.openai_key).map((s) => s.id);
    expect(needKey).toEqual(expect.arrayContaining(["illustrated", "under_the_hood"]));
    expect(opts.filter((o) => o.disabled).map((o) => o.value)).toEqual(needKey);
    expect(opts.find((o) => o.value === "illustrated")!.label).toMatch(/needs an OpenAI key/);
  });

  it("changes nothing when everything is available", () => {
    expect(styleOptions(PACK_STYLES, true, { status: "working" }).every((o) => !o.disabled)).toBe(true);
  });

  it("marks an experimental style in its label", () => {
    expect(styleOptions(PACK_STYLES, true).find((o) => o.value === "cartoon_3d")!.label).toBe("Cartoon 3D (experimental)");
    expect(styleOptions(PACK_STYLES, true).find((o) => o.value === "system_flow")!.label).toBe("System Flow");
  });

  it("offers only the value it holds until the list has loaded", () => {
    expect(styleOptions(null, true, null, "stick")).toEqual([{ value: "stick", label: "stick", disabled: false }]);
    expect(styleOptions(null, true, null, "")).toEqual([]);
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

describe("styleOptions with the GPU status", () => {
  it("disables the GPU-only styles and says why without a working GPU", () => {
    const opts = styleOptions(PACK_STYLES, true, { status: "not_usable" });
    expect(opts.filter((o) => o.disabled).map((o) => o.value)).toEqual(["cartoon_3d"]);
    expect(opts.find((o) => o.value === "cartoon_3d")!.label).toMatch(/needs a working GPU/);
  });

  it("tells an untested GPU apart from a missing one", () => {
    expect(styleOptions(PACK_STYLES, true, { status: "unknown" }).find((o) => o.value === "cartoon_3d")!.label).toMatch(/not tested yet/);
  });

  it("leaves GPU styles enabled while the GPU is working or the status is unloaded", () => {
    expect(styleOptions(PACK_STYLES, true, { status: "working" }).every((o) => !o.disabled)).toBe(true);
    expect(styleOptions(PACK_STYLES, true, null).every((o) => !o.disabled)).toBe(true);
  });

  it("disables every style that needs an OpenAI key or a GPU when neither is there", () => {
    expect(styleOptions(PACK_STYLES, false, { status: "not_configured" }).filter((o) => o.disabled).map((o) => o.value))
      .toEqual(PACK_STYLES.filter((s) => s.needs.openai_key || s.needs.gpu).map((s) => s.id));
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
