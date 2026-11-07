/**
 * Tests for the Illustrated-style availability helpers in lib/visualStyles.
 *
 * The Illustrated style's characters can only be drawn by OpenAI (the one
 * provider with transparent output), so with no key stored the API refuses it.
 * The dashboard reads that from GET /settings, which masks every secret to ""
 * when unset — so set-versus-unset is readable without seeing the key.
 */
import { describe, expect, it } from "vitest";
import { cartoon3dAvailable, illustratedAvailable, styleOptions, videoStyleLabel, VISUAL_STYLE_OPTIONS } from "@/lib/visualStyles";

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
  it("disables only Illustrated, and says why, when it is unavailable", () => {
    const opts = styleOptions(false);
    expect(opts.map((o) => o.value)).toEqual(VISUAL_STYLE_OPTIONS.map((o) => o.value));
    expect(opts.filter((o) => o.disabled).map((o) => o.value)).toEqual(["illustrated"]);
    expect(opts.find((o) => o.value === "illustrated")!.label).toMatch(/needs an OpenAI key/);
  });

  it("changes nothing when it is available", () => {
    expect(styleOptions(true)).toEqual(VISUAL_STYLE_OPTIONS.map((o) => ({ ...o, disabled: false })));
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
  it("disables Cartoon 3D and says why without a working GPU", () => {
    const opts = styleOptions(true, { status: "not_usable" });
    expect(opts.filter((o) => o.disabled).map((o) => o.value)).toEqual(["cartoon_3d"]);
    expect(opts.find((o) => o.value === "cartoon_3d")!.label).toMatch(/needs a working GPU/);
  });

  it("tells an untested GPU apart from a missing one", () => {
    expect(styleOptions(true, { status: "unknown" }).find((o) => o.value === "cartoon_3d")!.label).toMatch(/not tested yet/);
  });

  it("leaves Cartoon 3D enabled while the GPU is working or the status is unloaded", () => {
    expect(styleOptions(true, { status: "working" }).every((o) => !o.disabled)).toBe(true);
    expect(styleOptions(true, null).every((o) => !o.disabled)).toBe(true);
  });

  it("disables both when neither an OpenAI key nor a GPU is there", () => {
    expect(styleOptions(false, { status: "not_configured" }).filter((o) => o.disabled).map((o) => o.value))
      .toEqual(["illustrated", "cartoon_3d"]);
  });
});

describe("videoStyleLabel with a resolved renderer", () => {
  it("names the world auto settled on before any canvas", () => {
    expect(videoStyleLabel({ visual_style: "auto", resolved_visual_style: "", resolved_renderer: "cartoon_3d" })).toBe("Auto — Cartoon 3D");
    expect(videoStyleLabel({ visual_style: "auto", resolved_visual_style: "dark", resolved_renderer: "dom" })).toBe("Auto — dark canvas");
    expect(videoStyleLabel({ visual_style: "cartoon_3d", resolved_visual_style: "", resolved_renderer: "" })).toBe("Cartoon 3D");
  });
});
