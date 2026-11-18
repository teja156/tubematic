// External visual styles (TMDEV-253): what the Styles page and the install
// screen show. The API (renderer/api/styles_api.py) is the authority; these
// are its shapes and the wording built from them.

export type InstallSource = {
  kind: "zip" | "git" | "gallery" | "incoming" | "installed";
  filename?: string; url?: string; ref?: string; commit?: string; gallery_id?: string;
  name?: string; installed?: string; sha256?: string; index?: string;
};

export type ScanFlag = { file: string; line: number; what: string };

export type Scan = {
  refusals: string[];
  flags: ScanFlag[];
  files: { path: string; bytes: number; lines?: number }[];
  imports: Record<string, number>;
  guide: string;
  fonts: string[];
};

export type PendingInstall = {
  id: string; style_id: string; label: string; version: string; author: string; licence: string;
  homepage: string; renderer: string; needs_gpu: boolean; source: InstallSource; reviewed: boolean;
  created_at: string; expires_at: string; fingerprint: string;
  check: { ok: boolean; reason: string };
  scan: Scan;
  replaces: { version: string; fingerprint: string } | null;
  audit: { verdict: "no_concerns" | "concerns" | "refuse"; notes: string; at: string } | null;
  in_use?: { videos: { id: string; status: string; title: string }[]; domains: { id: string; name: string }[] };
};

export type InstalledStyle = {
  id: string; label: string; ok: boolean; reason: string; needs_review: boolean; version: string;
  author: string; licence: string; homepage: string; renderer: string; needs_gpu: boolean;
  source: InstallSource | null; reviewed: boolean; installed_at: string; in_auto: boolean;
  unfinished_videos: number; domains: { id: string; name: string }[];
};

export type GalleryEntry = {
  id: string; name?: string; author?: string; tagline?: string; version?: string;
  preview_url?: string; poster_url?: string; archive_url?: string; installed_version?: string | null;
  needs_gpu?: boolean; renderer?: string;
};

/** `reviewed` is the API's word that the source is the curated Tubematic gallery; any other gallery
 * address is someone's own index and is named as such. */
export function sourceLabel(s: InstallSource | null | undefined, reviewed = false): string {
  if (!s) return "Copied into the styles folder by hand";
  switch (s.kind) {
    case "gallery": return reviewed
      ? `Tubematic gallery (${s.gallery_id ?? ""})`
      : `Gallery at ${s.index ?? "an unknown address"} (${s.gallery_id ?? ""}), not reviewed`;
    case "zip": return `Zip file ${s.filename ?? ""}`.trim();
    case "git": return `Git repository ${s.url ?? ""} at ${s.commit ? s.commit.slice(0, 12) : s.ref ?? ""}`;
    case "incoming": return `Handed over by an agent (${s.name ?? ""})`;
    case "installed": return "Already in the styles folder, waiting for review";
  }
}

/** Gallery packages were reviewed by the Tubematic maintainer; everything else was not. */
export function installWarning(p: Pick<PendingInstall, "reviewed">): { level: "reviewed" | "unreviewed"; text: string } {
  const base = "A style package is code. Once installed it runs in the renderer's browser on every video in "
    + "this style, and its guide is read by your agent. Tubematic does not sandbox it.";
  return p.reviewed
    ? { level: "reviewed", text: `${base} This package comes from the Tubematic gallery, where a person reviewed it before it was published.` }
    : { level: "unreviewed", text: `${base} Nobody has reviewed this package for you. Install it only if you trust where it came from, and read the scan and the code below first.` };
}

export const AUDIT_LABELS: Record<string, string> = {
  no_concerns: "No concerns", concerns: "Concerns", refuse: "Recommends not installing",
};

/** May the person press Install? Only for a package that passes its check and the scan's refusals. */
export function installBlocked(p: Pick<PendingInstall, "check" | "scan">): string {
  if (!p.check.ok) return `This package cannot be installed: ${p.check.reason}`;
  if (p.scan.refusals.length) return "The scan refused this package; it cannot be installed.";
  return "";
}

export function fileToBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result ?? "");
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error("could not read the file"));
    reader.readAsDataURL(file);
  });
}

export const MAX_UPLOAD_BYTES = 25_000_000;
