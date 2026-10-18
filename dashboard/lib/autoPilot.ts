// Auto Pilot (TMDEV-139): the dashboard side of /autopilot.

import type { VideoStatus } from "@/lib/types";

/** The one disclaimer, worded once so the surfaces cannot drift apart. */
export const AUTO_PILOT_DISCLAIMER = [
  "Auto Pilot approves topics, scripts and finished videos with no human review.",
  "It spends money on every topic research files: ElevenLabs credits, image generation " +
    "and agent sessions. The pending-proposal cap no longer holds anything back, so only " +
    "the research caps and the in-progress limit bound how many videos are made.",
  "It posts publicly to real accounts, including videos the AI review flagged, could not " +
    "check, or never ran on.",
  "A published post cannot be taken back by Tubematic.",
] as const;

// Keep in sync with renderer/api/pipeline.py.
export const MAX_AUTO_PILOT_GAP_MINS = 7 * 24 * 60;
export const MAX_AUTO_PILOT_DAILY = 50;
export const MAX_AUTO_PILOT_IN_FLIGHT = 500;

/** How often the open panel re-reads the in-progress count: the worker's tick. */
export const AUTO_PILOT_POLL_MS = 20_000;

export interface AutoPilotConfig {
  enabled: boolean;
  gap_mins: number;
  /** Most videos in progress before Auto Pilot stops starting new ones (TMDEV-150); 0 = no limit. */
  max_in_flight: number;
  /** A project being a key puts it on Auto Pilot; its account list may be empty. */
  projects: Record<string, string[]>;
  account_limits: Record<string, number>;
}

export interface AutoPilotState extends AutoPilotConfig {
  default_daily_limit: number;
  /** Videos voiced and not published in Auto Pilot projects, plus every post waiting
   *  to go out at a future time, whoever scheduled it (pipeline.py::in_flight_count). */
  in_flight: number;
  /** Videos per project at each checkpoint and at VIDEO_APPROVED. */
  waiting: Record<string, Partial<Record<VideoStatus, number>>>;
}

export type GapUnit = "minutes" | "hours";

/** Whole hours read as hours; anything else stays in minutes. */
export function splitGap(mins: number): { value: number; unit: GapUnit } {
  return mins > 0 && mins % 60 === 0
    ? { value: mins / 60, unit: "hours" }
    : { value: mins, unit: "minutes" };
}

export function gapMins(value: number, unit: GapUnit): number {
  return unit === "hours" ? value * 60 : value;
}

/**
 * The count against the in-progress limit, or null with no limit. A full count
 * holds back new videos only while Auto Pilot is on, and then it must say so:
 * an Auto Pilot that starts nothing for no stated reason looks broken.
 */
export function ceilingStatus(state: AutoPilotState): { paused: boolean; text: string } | null {
  if (!state.max_in_flight) return null;
  const count = `${state.in_flight} of ${state.max_in_flight} videos in progress.`;
  return state.enabled && state.in_flight >= state.max_in_flight
    ? { paused: true,
        text: `Paused — ${count} Auto Pilot starts new videos again as these publish; ` +
              "finished videos are still approved and scheduled." }
    : { paused: false, text: count };
}

const CHECKPOINTS: VideoStatus[] = ["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"];

/** How many videos saving `next` would approve at once that `saved` would not. */
export function newlyApproved(saved: AutoPilotState, next: AutoPilotConfig): number {
  if (!next.enabled) return 0;
  let total = 0;
  for (const pid of Object.keys(next.projects)) {
    if (saved.enabled && pid in saved.projects) continue;
    for (const status of CHECKPOINTS) total += saved.waiting[pid]?.[status] ?? 0;
  }
  return total;
}

/** True when saving `next` widens what Auto Pilot acts on, so it must be confirmed. */
export function needsConfirmation(saved: AutoPilotState, next: AutoPilotConfig): boolean {
  if (!next.enabled) return false;
  if (!saved.enabled) return true;
  return Object.keys(next.projects).some((pid) => !(pid in saved.projects));
}
