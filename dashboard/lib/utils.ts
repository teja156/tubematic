import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Characters as the API counts them: Python's len() counts code points, while
 *  .length and a textarea's maxLength count UTF-16 units (two per emoji). */
export function codePoints(text: string): string[] {
  return Array.from(text);
}

/** A voice preview's /stream URL, from the path the API returns for it. Not
 *  for rendered videos: see videoStreamUrl. */
export function videoToStreamUrl(videoPath: string): string {
  return videoPath
    .replace(/^\/output_videos\//, "/stream/")
    .replace(/^mounted\/output_videos\//, "/stream/");
}

/** A rendered video's /stream URL, built from its own ids. The stored
 *  video_path is only a "rendered" marker and is never read for the location:
 *  a tampered or legacy row could name another video's file, and a legacy host
 *  path does not map to /stream at all. A blank project is "default_proj",
 *  where the worker renders it (keep in sync with
 *  tubematic_core/jobfiles.py::output_file). */
export function videoStreamUrl(video: { id: string; project_id: string | null }): string {
  const project = video.project_id || "default_proj";
  return `/stream/${encodeURIComponent(project)}/${encodeURIComponent(video.id)}.mp4`;
}

/** Whether a video carries a real producibility score. 0 means unscored: a
 *  video submitted from the New Video page has no agent to score it, and every
 *  other path drops a topic scoring below 5, so 0 cannot be a real score. */
export function isScored(score: number): boolean {
  return score > 0;
}

/** "7/10", or "—" for an unscored video. */
export function scoreLabel(score: number): string {
  return isScored(score) ? `${score}/10` : "—";
}
