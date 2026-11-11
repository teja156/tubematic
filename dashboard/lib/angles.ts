import type { Video } from "@/lib/types";

/** One kind a topic's angle can be, as GET /angle-kinds returns it. The list
 *  comes from the API, so the dashboard holds no copy of it. */
export interface AngleKind {
  id: string;
  label: string;
  /** What a topic must hold for an angle of this kind. */
  means: string;
}

/** The longest an angle sentence may be. The API refuses a longer one; the
 *  editors count against this so the refusal is not the first the person hears. */
export const ANGLE_MAX_CHARS = 300;

/** An angle sentence as the API stores it: runs of whitespace collapsed to one
 *  space and the ends trimmed. The editors send this form and count it. */
export function cleanAngle(text: string): string {
  return text.trim().replace(/\s+/g, " ");
}

/** The sentence's length as the API counts it: code points of the stored
 *  form, so an emoji is one and a line break is one space. */
export function angleLength(text: string): number {
  return Array.from(cleanAngle(text)).length;
}

/** A kind's label, or its id with the underscores opened up when the list has
 *  not loaded or does not know it. The ids are the labels in lower case, so
 *  the fallback reads the same. */
export function angleKindLabel(id: string, kinds: AngleKind[] | null): string {
  return kinds?.find((k) => k.id === id)?.label ?? id.replace(/_/g, " ");
}

/** Whether a video has an angle. The sentence and the kind are stored
 *  together, so the sentence alone answers it. */
export function hasAngle(video: Pick<Video, "angle">): boolean {
  return (video.angle ?? "") !== "";
}

/** "7/10", or a dash for an angle nobody scored (a person's own, or none). */
export function angleScoreLabel(score: number | undefined): string {
  return score && score > 0 ? `${score}/10` : "—";
}

/** The kinds from the API, or null when it cannot be reached or answers with
 *  something else. Callers keep working without it: labels fall back to ids. */
export async function fetchAngleKinds(): Promise<AngleKind[] | null> {
  try {
    const r = await fetch("/api/proxy/angle-kinds", { cache: "no-store" });
    if (!r.ok) return null;
    const data = await r.json();
    return Array.isArray(data) && data.every((k) => typeof k?.id === "string" && typeof k?.label === "string")
      ? (data as AngleKind[])
      : null;
  } catch {
    return null;
  }
}
