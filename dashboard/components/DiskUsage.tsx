"use client";

import { useCallback, useEffect, useState } from "react";
import { Popover } from "@base-ui/react/popover";
import { formatBytes } from "@/lib/format";
import type { StorageUsage } from "@/lib/types";

/** How often the header figure refreshes. Disk use moves slowly, and the API
 * caches its walk for a minute anyway; opening the popup fetches afresh. */
export const DISK_USAGE_POLL_MS = 5 * 60_000;

const DATA_LABELS: Record<string, { label: string; note: string }> = {
  videos:         { label: "Finished videos", note: "Rendered MP4s, kept until retention removes them" },
  voice_previews: { label: "Voice previews",  note: "Cached voice samples from Settings" },
  jobs:           { label: "Job files",       note: "Per-video voice audio, scene images and timelines" },
  scenes:         { label: "Generated scenes", note: "Scene code the agent wrote for each video" },
  database:       { label: "Database",        note: "The pipeline database" },
  mascots:        { label: "Mascot sheets",   note: "Rendered mascot model sheets" },
  backups:        { label: "Backups",         note: "Database backups taken before migrations" },
  logs:           { label: "Logs",            note: "Service logs" },
};

function isStorage(body: unknown): body is StorageUsage {
  const b = body as StorageUsage | null;
  return !!b && typeof b === "object" && typeof b.total_bytes === "number"
    && !!b.data && Array.isArray(b.data.items);
}

function ago(iso: string, now: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const mins = Math.max(0, Math.floor((now - t) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

type Row = {
  key: string; label: string; note: string; bytes: number | null; counted: boolean;
  /** The figure is a floor: shown as "≥ 4.5 GB". */
  atLeast?: boolean;
};

function hostRows(host: NonNullable<StorageUsage["host"]>): Row[] {
  const images = host.images;
  const old = images?.old_count ?? 0;
  const rows: Row[] = [
    { key: "images_current", label: "Current images", counted: true,
      note: "The Docker images this install runs", bytes: images ? images.current_bytes : null },
    { key: "images_old", label: "Old images", counted: true,
      note: !images
        ? "Docker did not report image sizes at the last measurement"
        : old
          ? `${old} image${old === 1 ? "" : "s"} no longer used; the next upgrade removes them`
          : "None — upgrades remove the previous version's images",
      bytes: images ? images.old_bytes : null,
      // Each old image's figure leaves out layers it shares with another
      // image, so with two or more, layers only they share are missed.
      atLeast: old > 1 },
    { key: "containers", label: "Container scratch", counted: true,
      note: "Files the containers wrote inside themselves", bytes: host.containers_bytes },
    { key: "install", label: "Install folder", counted: true,
      note: "Tubematic's code with its Python and Node packages", bytes: host.install_bytes },
  ];
  if (host.build_cache_bytes) {
    rows.push({ key: "build_cache", label: "Docker build cache", counted: false,
      note: "Shared by everything built on this machine; not in the total",
      bytes: host.build_cache_bytes });
  }
  return rows;
}

function UsageRow({ row, max }: { row: Row; max: number }) {
  const known = typeof row.bytes === "number";
  const pct = known && max > 0 ? Math.max(1, Math.round(((row.bytes as number) / max) * 100)) : 0;
  return (
    <div data-testid={`disk-row-${row.key}`} style={{ padding: "6px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
        <span style={{ color: "var(--ink)" }}>{row.label}</span>
        <span style={{ color: row.counted ? "var(--ink)" : "var(--mute)" }}>
          {known ? `${row.atLeast ? "≥ " : ""}${formatBytes(row.bytes as number)}` : "unknown"}
        </span>
      </div>
      <div style={{ height: 3, background: "var(--border)", margin: "4px 0 3px" }}>
        <div style={{ width: `${pct}%`, height: "100%",
          background: row.counted ? "var(--amber)" : "var(--mute)" }} />
      </div>
      <div style={{ fontSize: 10, color: "var(--mute)", whiteSpace: "normal" }}>{row.note}</div>
    </div>
  );
}

function Section({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 10,
        letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--dim)",
        borderBottom: "1px solid var(--border)", paddingBottom: 4 }}>
        <span>{title}</span>
        {meta && <span style={{ textTransform: "none", letterSpacing: 0 }}>{meta}</span>}
      </div>
      {children}
    </div>
  );
}

/** Disk Tubematic uses, in the top bar, with a breakdown on click (TMDEV-192).
 *
 * The data folders are measured by the API; images, container layers and the
 * install folder by the host (no container can see Docker), which leaves a
 * snapshot the API passes on. Until that snapshot exists the figure is the data
 * alone, and the popup says the rest is not measured yet rather than showing a
 * smaller total as the whole.
 *
 * Renders nothing when the API answers with anything but the expected shape —
 * an older API during an upgrade, a 404, a network error. A wrong figure is
 * worse than none.
 *
 * Declared at module scope, like every top-bar component (see VersionBadge). */
export function DiskUsage() {
  const [usage, setUsage] = useState<StorageUsage | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async (signal?: { cancelled: boolean }) => {
    try {
      const res = await fetch("/api/proxy/storage", { cache: "no-store" });
      const body = res.ok ? await res.json() : null;
      if (signal?.cancelled) return;
      setUsage(isStorage(body) ? body : null);
      setNow(Date.now());
    } catch {
      if (!signal?.cancelled) setUsage(null);
    }
  }, []);

  useEffect(() => {
    const signal = { cancelled: false };
    load(signal);
    const id = setInterval(() => load(signal), DISK_USAGE_POLL_MS);
    return () => { signal.cancelled = true; clearInterval(id); };
  }, [load]);

  if (!usage) return null;

  const dataRows: Row[] = usage.data.items.map((i) => ({
    key: i.key, bytes: i.bytes, counted: true,
    label: DATA_LABELS[i.key]?.label ?? i.key,
    note: DATA_LABELS[i.key]?.note ?? "",
  }));
  const host = usage.host;
  const extra = host ? hostRows(host) : [];
  // The total includes the old-image figure, so when that is a floor (two or
  // more old images) the total is one too.
  const total = `${(host?.images?.old_count ?? 0) > 1 ? "≥ " : ""}${formatBytes(usage.total_bytes)}`;
  const max = Math.max(0, ...[...dataRows, ...extra].map((r) => r.bytes ?? 0));

  return (
    <Popover.Root onOpenChange={(open) => { if (open) load(); }}>
      <Popover.Trigger
        data-testid="disk-usage"
        title="Disk space Tubematic uses"
        style={{
          fontFamily: "var(--mono)", fontSize: 11, color: "var(--dim)", background: "transparent",
          border: "none", padding: 0, cursor: "pointer", whiteSpace: "nowrap",
        }}
      >
        <span aria-hidden style={{ marginRight: 5 }}>◔</span>
        {total}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={10} style={{ zIndex: 200 }}>
          <Popover.Popup
            data-testid="disk-usage-popup"
            style={{
              width: 340, maxWidth: "calc(100vw - 32px)", maxHeight: "calc(100vh - 120px)",
              overflowY: "auto", background: "var(--panel)", border: "1px solid var(--border-2)",
              padding: "12px 14px", fontFamily: "var(--mono)", fontSize: 11, color: "var(--dim)",
              boxShadow: "0 4px 16px rgba(0,0,0,0.5)", outline: "none",
            }}
          >
            <Popover.Title style={{ margin: 0, fontSize: 12, fontWeight: 400,
              color: "var(--amber)", display: "flex", justifyContent: "space-between" }}>
              <span>DISK USAGE</span>
              <span data-testid="disk-usage-total">{total}</span>
            </Popover.Title>
            <Section title="Your data" meta="live">
              {dataRows.map((r) => <UsageRow key={r.key} row={r} max={max} />)}
            </Section>
            <Section title="Docker & install"
              meta={host ? `measured ${ago(host.measured_at, now)}` : undefined}>
              {host
                ? extra.map((r) => <UsageRow key={r.key} row={r} max={max} />)
                : (
                  <p data-testid="disk-usage-unmeasured" style={{ margin: "8px 0 0", whiteSpace: "normal" }}>
                    Not measured yet — the poller measures images and the install folder
                    within the hour. Until then the total counts your data only.
                  </p>
                )}
            </Section>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
