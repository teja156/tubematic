import type { Video, VideoStatus } from "@/lib/types";

// Statuses a video can be deleted from. Keep in sync with
// renderer/api/pipeline.py's DELETABLE_STATUSES, which is the real gate — this
// only decides whether the button is shown. Left out: the processing statuses
// (something is working on the video right now) and VOICE_READY /
// REVISION_REQUESTED, the two statuses an agent can hold a scene-work claim in.
export const DELETABLE_STATUSES: ReadonlySet<VideoStatus> = new Set<VideoStatus>([
  "TOPIC_PROPOSED",
  "TOPIC_APPROVED",
  "TOPIC_REJECTED",
  "SCRIPT_READY",
  "VIDEO_READY",
  "VIDEO_APPROVED",
  "PUBLISHED",
  "FAILED",
]);

export function canDelete(video: Pick<Video, "status" | "archived_at">): boolean {
  return !video.archived_at && DELETABLE_STATUSES.has(video.status);
}

// Whether to offer "Retry publishing". Keep in sync with renderer/api/pipeline.py's
// retry_publish, which is the real gate: a FAILED video with publication rows is
// one that failed while publishing, because the rows are written when a publish
// starts and a render failure never writes any.
export function canRetryPublish(
  video: Pick<Video, "status" | "archived_at">,
  publicationCount: number,
): boolean {
  return !video.archived_at && video.status === "FAILED" && publicationCount > 0;
}

// Whether the scheduled agent has given up on this video (TMDEV-129): too many
// sessions in a row left it where they found it, so the poller skips it until
// a human acts. The API is the gate; this only decides what the modal offers.
export function isAgentStuck(video: Pick<Video, "agent_stuck_at" | "archived_at">): boolean {
  return !video.archived_at && !!video.agent_stuck_at;
}

/** Hand a stuck video back to the scheduled agent. Throws with the API's reason. */
export async function retryAgent(id: string): Promise<void> {
  const res = await fetch(`/api/proxy/videos/${id}/agent-retry`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? "Retry agent failed.");
  }
}

/** DELETE the video's files and archive its row. Throws with the API's reason. */
export async function deleteVideo(id: string): Promise<void> {
  const res = await fetch(`/api/proxy/videos/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? "Failed to delete video");
  }
}

/** PATCH a video. Throws a message fit to show the human: a lost status race
 *  (the video moved since the page last polled) reads as a conflict, anything
 *  else in the API's own words — say, a picked agent that has since been
 *  uninstalled. Shared by every page that acts on a video, so none of them can
 *  treat a refused action as done. */
export async function patchVideo(id: string, body: Record<string, unknown>): Promise<void> {
  const res = await fetch(`/api/proxy/videos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) return;
  const err = await res.json().catch(() => ({}));
  if (res.status === 409 && err.error === "Status precondition failed") {
    throw new Error("Status conflict — action already taken");
  }
  throw new Error(err.error ?? "Failed to update video");
}
