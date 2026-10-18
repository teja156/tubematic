/**
 * lib/voices.ts — the rules both voice pickers share (TMDEV-121, TMDEV-127).
 *
 * What these guard:
 *  - approve-topic carries a voice only when the human picked one, so an
 *    untouched picker never pins the install default over a project-seeded
 *    voice (topicVoicePayload);
 *  - the shown voice is derived from the pick and the video, not frozen at
 *    mount, so it follows a roster that answers late (shownVoice);
 *  - a shown voice with no option of its own is detected, so the picker can
 *    list it rather than display a different voice (voiceMissing).
 */
import { describe, expect, it } from "vitest";
import { shownVoice, topicVoicePayload, voiceMissing } from "@/lib/voices";

const ROSTER = [{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }];

describe("topicVoicePayload", () => {
  it("sends nothing for an untouched picker", () => {
    expect(topicVoicePayload(null)).toEqual({});
  });

  it("sends the picked voice", () => {
    expect(topicVoicePayload("abc123")).toEqual({ voice_id: "abc123" });
  });
});

describe("shownVoice", () => {
  it("a pick wins over the video's voice and the default", () => {
    expect(shownVoice("x", { voice_id: "own" }, "def")).toBe("x");
  });

  it("untouched, it is the video's own voice, else the install default", () => {
    expect(shownVoice(null, { voice_id: "own" }, "def")).toBe("own");
    expect(shownVoice(null, { voice_id: "" }, "def")).toBe("def");
  });
});

describe("voiceMissing", () => {
  it("is false for a roster voice and true for a stale or blank one", () => {
    expect(voiceMissing(ROSTER, "abc123")).toBe(false);
    expect(voiceMissing(ROSTER, "ghost")).toBe(true);
    expect(voiceMissing(ROSTER, "")).toBe(true);
  });
});
