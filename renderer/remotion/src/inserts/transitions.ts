/*
 * Insert scenes (TMDEV-224): how an insert goes in and out over its main
 * style, as pure functions of the frame.
 *
 * A video has one main style, drawn by its scene(s) across the whole video,
 * and may have a few short inserts from an insert style (System Flow,
 * Terminal Doc), drawn in a layer above the scenes and below the captions.
 * The main style names one transition for going into and out of an insert
 * (its pack's inserts.transition; write_scene_config copies it into
 * scene-config.json as `insertTransition`).
 *
 * - cut:  the insert appears and disappears on a frame.
 * - dip:  the main fades to the canvas colour, then the insert fades up; the
 *         same in reverse on the way out.
 * - push: the insert slides in from the right while the main slides out to
 *         the left, and back the other way out.
 * - wipe: the insert is revealed by an edge moving right to left, and
 *         uncovered the same way out.
 *
 * The transitions run just outside the insert's window: the way in over the n
 * frames before it, the way out over the n frames after it. So the insert's
 * whole window is fully on screen, and on the way out the main style is
 * already showing the picture it comes back to (its next cut sits on the
 * window's end; the validators keep the window itself quiet).
 *
 * While an insert fully covers the frame the main layer is hidden (not
 * unmounted: every main component is a pure function of the frame, so it
 * comes back on the picture it would have shown, and hiding it skips its
 * paint, which is most of a frame's cost in software GL).
 *
 * Keep in sync: tubematic_core/inserts.py (TRANSITIONS, TRANSITION_FRAMES).
 */

export type InsertTransition = "cut" | "dip" | "push" | "wipe";

export const TRANSITION_FRAMES: Record<InsertTransition, number> = { cut: 0, dip: 8, push: 12, wipe: 12 };

export type InsertWindow = { startFrame: number; durationInFrames: number };

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
// Ease in and out, so a slide or a wipe starts and lands softly.
const smooth = (t: number) => t * t * (3 - 2 * t);

export function transitionOf(name: string | undefined): InsertTransition {
  return name === "dip" || name === "push" || name === "wipe" ? name : "cut";
}

/**
 * How far into its transition an insert is at `local` (frames since the
 * insert's start), for a transition of `n` frames: 0 = not shown (before or
 * after), 1 = fully in. The whole window [0, duration) is fully in; the way in
 * runs over [-n, 0) and the way out over [duration, duration + n).
 */
export function insertProgress(local: number, duration: number, n: number): number {
  const k = Math.max(0, n);
  if (local < -k || local >= duration + k) return 0;
  if (local < 0) return clamp01((local + k + 1) / (k + 1));
  if (local >= duration) return clamp01((duration + k - local) / (k + 1));
  return 1;
}

/** The window an absolute frame falls in, with its progress, or null. */
export function activeInsert(frame: number, windows: InsertWindow[], transition: InsertTransition) {
  const n = TRANSITION_FRAMES[transition];
  for (let i = 0; i < windows.length; i++) {
    const w = windows[i];
    const local = frame - w.startFrame;
    if (local >= -n && local < w.durationInFrames + n) {
      const p = insertProgress(local, w.durationInFrames, n);
      return { index: i, local, progress: p };
    }
  }
  return null;
}

/** What the insert layer and the main layer look like at a progress. */
export type InsertLook = {
  // The insert's own layer.
  insertOpacity: number;
  insertShiftX: number; // pixels, push only
  insertClipLeft: number; // pixels of the insert hidden from the left, wipe only
  // The main layer under it.
  mainShiftX: number; // pixels, push only
  // A canvas-coloured veil over the main, dip only.
  veilOpacity: number;
  // Whether the insert covers the frame completely, so the main may skip painting.
  covers: boolean;
};

export function insertLook(transition: InsertTransition, progress: number, width = 1080): InsertLook {
  const none: InsertLook = { insertOpacity: 0, insertShiftX: 0, insertClipLeft: 0, mainShiftX: 0, veilOpacity: 0, covers: false };
  if (progress <= 0) return none;
  if (progress >= 1) return { ...none, insertOpacity: 1, covers: true };
  const p = smooth(progress);
  switch (transition) {
    case "dip":
      // First half: the main dims to the canvas. Second half: the insert fades up.
      return progress < 0.5
        ? { ...none, veilOpacity: clamp01(progress * 2) }
        : { ...none, veilOpacity: 1, insertOpacity: clamp01(progress * 2 - 1) };
    case "push":
      // In: the insert comes from the right, the main leaves to the left.
      // Out: the same move played backwards.
      return { ...none, insertOpacity: 1, insertShiftX: (1 - p) * width, mainShiftX: -p * width };
    case "wipe":
      return { ...none, insertOpacity: 1, insertClipLeft: (1 - p) * width };
    default:
      return { ...none, insertOpacity: 1, covers: true };
  }
}

/** The insert Sequence's frame the scene holds through the way in and its first
 *  frames: the frame on which its first element has settled (`lead` frames of
 *  way in, then `firstFrames` into the window, never past its last frame). The
 *  scene is frozen there while the Sequence's frame is below it, so an insert
 *  never shows an empty board (decided 2026-11-12). */
export function heldFrame(lead: number, firstFrames: unknown, durationInFrames: number): number {
  // A config written before firstFrames existed, or one edited by hand with a
  // value that is not a number, holds the first frame: never NaN, which
  // Remotion's Freeze refuses even while inactive.
  const n = Number(firstFrames ?? 0);
  const first = Number.isFinite(n) ? Math.max(0, Math.min(Math.floor(n), durationInFrames - 1)) : 0;
  return lead + first;
}
