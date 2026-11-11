import { describe, expect, it } from "vitest";
import {
  approvalMascot, mascotGate, mascotGateNote, mascotOptions, mascotSheetUrl, showMascotPicker, styleTakesMascot,
} from "@/lib/mascots";
import { PACK_STYLES } from "./packStyles";

const M = [
  { id: "tubi", name: "Tubi", pickable: true },
  { id: "moss", name: "Moss", pickable: false },
];

describe("mascotGate", () => {
  it("is open only while the GPU is working", () => {
    expect(mascotGate({ status: "working" })).toBe("ok");
    expect(mascotGate({ status: "unknown" })).toBe("unknown");
    expect(mascotGate({ status: "not_usable" })).toBe("unavailable");
    expect(mascotGate({ status: "not_configured" })).toBe("unavailable");
  });
  it("fails closed while the status has not loaded (unlike Cartoon 3D)", () => {
    expect(mascotGate(null)).toBe("loading");
    expect(mascotGate(undefined)).toBe("loading");
  });
  it("words each refusal", () => {
    expect(mascotGateNote("unavailable")).toBe("Mascots need a working GPU");
    expect(mascotGateNote("unknown")).toBe("GPU not tested yet");
    expect(mascotGateNote("ok")).toBe("");
  });
});

describe("mascotSheetUrl", () => {
  it("maps the API-relative path to the dashboard's image route", () => {
    expect(mascotSheetUrl("/mascots/tubi/versions/2/sheets/turn")).toBe("/mascot-sheets/tubi/versions/2/sheets/turn");
  });
});

describe("mascotOptions", () => {
  it("lists None then the pickable mascots only", () => {
    expect(mascotOptions(M, { status: "working" }, "").map((o) => o.value)).toEqual(["", "tubi"]);
  });
  it("disables mascots (not None) with the reason when the GPU is not working", () => {
    const opts = mascotOptions(M, { status: "not_usable" }, "");
    expect(opts[0]).toMatchObject({ value: "", disabled: false });
    expect(opts[1]).toMatchObject({ value: "tubi", disabled: true, label: "Tubi (Mascots need a working GPU)" });
  });
  it("keeps a held, still-pickable mascot selectable so an untouched picker re-sends it", () => {
    const opts = mascotOptions(M, { status: "not_usable" }, "tubi");
    expect(opts.find((o) => o.value === "tubi")!.disabled).toBe(false);
  });
  it("shows a held mascot that is no longer pickable as unavailable, never as None", () => {
    expect(mascotOptions(M, { status: "working" }, "moss")[1])
      .toMatchObject({ value: "moss", label: "Moss (unavailable)", disabled: true });
    expect(mascotOptions(M, { status: "working" }, "ghost")[1])
      .toMatchObject({ value: "ghost", label: "Unavailable mascot" });
  });
});

describe("showMascotPicker / approvalMascot", () => {
  it("shows when something can be picked or is held", () => {
    expect(showMascotPicker(M, "")).toBe(true);
    expect(showMascotPicker([M[1]], "")).toBe(false);
    expect(showMascotPicker([M[1]], "moss")).toBe(true);
  });
  it("sends no mascot on Cartoon 3D", () => {
    expect(approvalMascot("cartoon_3d", "tubi")).toBe("");
    expect(approvalMascot("stick", "tubi")).toBe("tubi");
    // a style whose pack takes no mascot, from the served style list
    expect(approvalMascot("under_the_hood", "tubi", PACK_STYLES)).toBe("");
    expect(approvalMascot("under_the_hood", "tubi", null)).toBe("tubi");   // list not loaded: the API decides
    expect(styleTakesMascot("under_the_hood", PACK_STYLES)).toBe(false);
    expect(styleTakesMascot("bean_explainer", PACK_STYLES)).toBe(true);
  });
});
