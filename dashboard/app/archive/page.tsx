"use client";

import { useEffect, useMemo, useState } from "react";
import type { Project, Video, VideoPublication } from "@/lib/types";
import { VideoModal } from "@/components/VideoModal";
import { SectionLabel } from "@/components/SectionLabel";
import { StatusBadge } from "@/components/StatusBadge";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDate } from "@/lib/datetime";
import { platformLabel } from "@/lib/platforms";

// Videos whose files were deleted — by a human, or by the retention sweep — and
// whose rows were archived. The record survives, and so do its publication
// links and analytics: those come from /analytics, which reads
// video_publications + video_metrics and is untouched by archiving.

type AnalyticsRow = VideoPublication & { views: number | null };

const NO_CACHE: RequestInit = { cache: "no-store" };
const mono = { fontFamily: "var(--mono)" } as const;

const th: React.CSSProperties = {
  ...mono,
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.14em",
  color: "var(--dim)",
  textAlign: "left",
  padding: "8px 12px",
  borderBottom: "1px solid var(--border)",
  fontWeight: 400,
};
const td: React.CSSProperties = {
  padding: "10px 12px",
  borderBottom: "1px solid var(--border)",
  fontSize: 13,
  color: "var(--ink)",
  verticalAlign: "middle",
};

/** Summed over platforms, the one aggregate /analytics itself treats as
 *  defensible. "—" when no platform reported one — not 0, which would invent a
 *  datapoint. */
function totalViews(rows: AnalyticsRow[]): string {
  const reported = rows.map((r) => r.views).filter((v): v is number => v !== null && v !== undefined);
  return reported.length ? reported.reduce((a, b) => a + b, 0).toLocaleString() : "—";
}

export default function ArchivePage() {
  const { timeZone } = useTimeZone();
  const [videos, setVideos] = useState<Video[]>([]);
  const [publications, setPublications] = useState<AnalyticsRow[]>([]);
  const [projects, setProjects] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Video | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/proxy/videos?archived=only", NO_CACHE)
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok || !Array.isArray(body)) throw new Error(body?.error ?? "Could not load the archive.");
        setVideos(body);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the archive."))
      .finally(() => setLoading(false));
    // Both of these only decorate rows, so a failure leaves the list readable.
    fetch("/api/proxy/analytics", NO_CACHE)
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => setPublications(Array.isArray(body?.publications) ? body.publications : []))
      .catch(() => {});
    fetch("/api/proxy/projects", NO_CACHE)
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: Project[]) =>
        setProjects(Object.fromEntries((Array.isArray(rows) ? rows : []).map((p) => [p.id, p.name]))))
      .catch(() => {});
  }, []);

  const byVideo = useMemo(() => {
    const m: Record<string, AnalyticsRow[]> = {};
    for (const p of publications) (m[p.video_id] ??= []).push(p);
    return m;
  }, [publications]);

  const sorted = useMemo(
    () => [...videos].sort((a, b) => (b.archived_at ?? "").localeCompare(a.archived_at ?? "")),
    [videos],
  );

  return (
    <>
      <SectionLabel label="Archive" count={`${videos.length} Archived`} />
      <p style={{ fontSize: 13, color: "var(--dim)", margin: "0 0 16px", lineHeight: 1.6 }}>
        Videos whose rendered file and working files were deleted — from the video&apos;s
        Delete action, or automatically once a published, failed or rejected video passes its
        retention period set in Settings. Their records, publication links and analytics are
        kept here.
      </p>

      {error && (
        <div style={{ ...mono, fontSize: 11, color: "var(--red)", marginBottom: 16 }}>{error}</div>
      )}

      {!loading && !error && sorted.length === 0 && (
        <div data-testid="archive-empty" style={{ ...mono, fontSize: 11, color: "var(--mute)", padding: "24px 0" }}>
          Nothing archived yet.
        </div>
      )}

      {sorted.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--panel)" }}>
            <thead>
              <tr>
                <th style={th}>Video</th>
                <th style={th}>Project</th>
                <th style={th}>Status</th>
                <th style={th}>Archived</th>
                <th style={{ ...th, textAlign: "right" }}>Views</th>
                <th style={th}>Links</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((v) => {
                const pubs = byVideo[v.id] ?? [];
                return (
                  <tr
                    key={v.id}
                    data-testid={`archive-row-${v.id}`}
                    onClick={() => setSelected(v)}
                    style={{ cursor: "pointer" }}
                  >
                    <td style={td}>{v.title || v.topic}</td>
                    <td style={{ ...td, color: "var(--dim)" }}>
                      {v.project_id ? projects[v.project_id] ?? v.project_id : "—"}
                    </td>
                    <td style={td}><StatusBadge status={v.status} /></td>
                    <td style={{ ...td, ...mono, fontSize: 11, color: "var(--dim)" }}>
                      {v.archived_at ? formatDate(v.archived_at, timeZone) : "—"}
                    </td>
                    <td style={{ ...td, ...mono, fontSize: 12, textAlign: "right" }}>{totalViews(pubs)}</td>
                    <td style={td}>
                      {pubs.filter((p) => p.post_url).map((p) => (
                        <a
                          key={p.id}
                          href={p.post_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          style={{ ...mono, fontSize: 11, color: "var(--cyan)", marginRight: 10 }}
                        >
                          {platformLabel(p.platform)} →
                        </a>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Read-only: an archived video offers no actions (the API would 409
          them all), so the modal never calls onAction here. */}
      <VideoModal video={selected} onClose={() => setSelected(null)} onAction={() => {}} />
    </>
  );
}
