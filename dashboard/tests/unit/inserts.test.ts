/**
 * lib/inserts.ts (TMDEV-224): the per-video Inserts setting and how a video's
 * inserts read in the video window. The traps it guards: the stored list is
 * JSON text, and "" (undecided) must not read as [] (decided, none); a style
 * that takes no inserts says so, and the setting None outranks everything.
 */
import { describe, expect, it } from "vitest";
import {
  INSERT_MODE_OPTIONS, insertMode, insertsLockedReason, insertsRowText, parseInsertStyles, styleHostsInserts,
} from "@/lib/inserts";
import type { Video } from "@/lib/types";
import { PACK_STYLES } from "./packStyles";

type RowVideo = Parameters<typeof insertsRowText>[0];

function video(over: Partial<Video>): RowVideo {
  return { status: "SCRIPT_READY", insert_mode: "auto", insert_styles: "", insert_summary: null,
           visual_style: "stick", resolved_renderer: "", style_pick: "", ...over };
}

describe("INSERT_MODE_OPTIONS and insertMode", () => {
  it("offers Auto then None", () => {
    expect(INSERT_MODE_OPTIONS.map((o) => o.label)).toEqual(["Auto", "None"]);
  });

  it("reads anything but none as auto, the API's default", () => {
    expect(insertMode("none")).toBe("none");
    expect(insertMode("auto")).toBe("auto");
    expect(insertMode(undefined)).toBe("auto");
    expect(insertMode("")).toBe("auto");
  });
});

describe("styleHostsInserts", () => {
  it("follows the pack's inserts.host", () => {
    expect(styleHostsInserts("stick", PACK_STYLES)).toBe(true);
    expect(styleHostsInserts("cartoon_3d", PACK_STYLES)).toBe(false);
  });

  it("is true for Auto, for no style, for a style the list lacks, and before the list loads", () => {
    expect(styleHostsInserts("auto", PACK_STYLES)).toBe(true);
    expect(styleHostsInserts("", PACK_STYLES)).toBe(true);
    expect(styleHostsInserts("from_a_newer_api", PACK_STYLES)).toBe(true);
    expect(styleHostsInserts("cartoon_3d", null)).toBe(true);
  });

  it("names the style when it locks the picker", () => {
    expect(insertsLockedReason("cartoon_3d", PACK_STYLES)).toBe("Cartoon 3D takes no inserts.");
    expect(insertsLockedReason("stick", PACK_STYLES)).toBe("");
  });
});

describe("parseInsertStyles", () => {
  it("keeps undecided apart from none", () => {
    expect(parseInsertStyles("")).toBeNull();
    expect(parseInsertStyles(undefined)).toBeNull();
    expect(parseInsertStyles("[]")).toEqual([]);
  });

  it("reads the stored JSON list, or a list already parsed", () => {
    expect(parseInsertStyles('["system_flow","terminal_doc"]')).toEqual(["system_flow", "terminal_doc"]);
    expect(parseInsertStyles(["system_flow"])).toEqual(["system_flow"]);
  });

  it("reads text that is not a list as undecided", () => {
    expect(parseInsertStyles("not json")).toBeNull();
    expect(parseInsertStyles('{"a":1}')).toBeNull();
  });
});

describe("insertsRowText", () => {
  it("says None was chosen, whatever the agent decided", () => {
    expect(insertsRowText(video({ insert_mode: "none", insert_styles: '["system_flow"]' }), PACK_STYLES))
      .toBe("None (turned off for this video)");
  });

  it("says the main style takes none, Auto's pick included", () => {
    expect(insertsRowText(video({ visual_style: "cartoon_3d" }), PACK_STYLES))
      .toBe("None (Cartoon 3D takes no inserts)");
    expect(insertsRowText(video({ visual_style: "auto", resolved_renderer: "cartoon_3d" }), PACK_STYLES))
      .toBe("None (Cartoon 3D takes no inserts)");
  });

  it("reads Auto before the topic is approved and Not decided yet after", () => {
    expect(insertsRowText(video({ status: "TOPIC_PROPOSED" }), PACK_STYLES)).toBe("Auto");
    expect(insertsRowText(video({ status: "TOPIC_APPROVED" }), PACK_STYLES)).toBe("Not decided yet");
  });

  it("reads a decided empty list as None", () => {
    expect(insertsRowText(video({ insert_styles: "[]" }), PACK_STYLES)).toBe("None");
  });

  it("names the insert styles, and what the scene config holds of them", () => {
    expect(insertsRowText(video({ insert_styles: '["system_flow","terminal_doc"]' }), PACK_STYLES))
      .toBe("System Flow, Terminal Doc");
    expect(insertsRowText(video({ insert_styles: '["system_flow"]',
                                  insert_summary: { count: 2, seconds: 12.6, styles: ["system_flow"] } }), PACK_STYLES))
      .toBe("System Flow · 2 inserts, 13 s");
    expect(insertsRowText(video({ insert_styles: '["system_flow"]',
                                  insert_summary: { count: 1, seconds: 7, styles: ["system_flow"] } }), PACK_STYLES))
      .toBe("System Flow · 1 insert, 7 s");
    expect(insertsRowText(video({ insert_styles: '["system_flow"]',
                                  insert_summary: { count: 0, seconds: 0, styles: [] } }), PACK_STYLES))
      .toBe("System Flow");
  });
});
