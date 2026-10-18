import type { Video, Voice } from "@/lib/types";

// Voice pickers at the TOPIC_PROPOSED and SCRIPT_READY checkpoints (TMDEV-121,
// TMDEV-127). Each voice has its own ElevenLabs model, and a script's
// pronunciation and pause markup was written for its voice's model, so some
// voices cannot speak a given script. Which ones is decided by the API
// (video.voice_conflicts), with the same check that refuses such a voice with a
// 409 — this file only presents it. At TOPIC_PROPOSED the script is still to be
// written, so any voice goes: that is where a voice on another model is chosen.
//
// Both pickers hold `null` until the human picks, and show
// shownVoice(...) — recomputed every render, so it follows /settings when it
// arrives after the row mounted. Seeding a useState from the default instead
// froze "" when the videos answered first, and the row then showed the
// roster's first voice while sending "".

/** The option label: the voice's name and the model it speaks with. */
export function voiceLabel(v: Voice): string {
  return v.model_id ? `${v.name} · ${v.model_id}` : v.name;
}

/** Why this voice cannot speak the video's script, or "" when it can. */
export function voiceConflict(video: Pick<Video, "voice_conflicts">, voiceId: string): string {
  return video.voice_conflicts?.[voiceId] ?? "";
}

/** The voice a picker starts on: the video's own, else the install default. */
export function initialVoice(video: Pick<Video, "voice_id">, defaultVoiceId: string): string {
  return video.voice_id || defaultVoiceId;
}

/** The voice a picker shows: the human's pick, else the one the video starts on. */
export function shownVoice(
  picked: string | null, video: Pick<Video, "voice_id">, defaultVoiceId: string,
): string {
  return picked ?? initialVoice(video, defaultVoiceId);
}

/** Whether the shown voice has no option of its own — a voice since removed
 *  from the roster, or none at all. The picker then lists it first, disabled,
 *  so it never displays one voice while the video would be voiced with another. */
export function voiceMissing(voices: Voice[], voiceId: string): boolean {
  return !voices.some((v) => v.voice_id === voiceId);
}

/** What approve-topic carries for the voice: nothing unless the human picked
 *  one. An untouched picker must never pin the install default over the voice
 *  the video was seeded with (its project's), nor pin a default that may still
 *  change before the script is written — writing the script pins the voice. */
export function topicVoicePayload(picked: string | null): { voice_id?: string } {
  return picked === null ? {} : { voice_id: picked };
}
