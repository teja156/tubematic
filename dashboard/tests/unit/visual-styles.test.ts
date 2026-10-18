/**
 * Tests for the Illustrated-style availability helpers in lib/visualStyles.
 *
 * The Illustrated style's characters can only be drawn by OpenAI (the one
 * provider with transparent output), so with no key stored the API refuses it.
 * The dashboard reads that from GET /settings, which masks every secret to ""
 * when unset — so set-versus-unset is readable without seeing the key.
 */
import { describe, expect, it } from "vitest";
import { illustratedAvailable, styleOptions, VISUAL_STYLE_OPTIONS } from "@/lib/visualStyles";

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
