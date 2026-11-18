"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ProfilesNav } from "@/components/ProfilesNav";
import { SectionLabel } from "@/components/SectionLabel";
import {
  type GalleryEntry, type InstalledStyle, type PendingInstall, MAX_UPLOAD_BYTES, fileToBase64, sourceLabel,
} from "@/lib/externalStyles";
import { previewUrls } from "@/lib/visualStyles";

// External visual styles (TMDEV-253): what is installed, what waits for a
// person's yes, the curated gallery, and the two ways to install from outside
// it. Installing always goes through the install screen (/styles/install/<id>).

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const mono = { fontFamily: "var(--mono)" } as const;
const inputStyle = {
  ...mono, fontSize: 12, width: "100%", padding: "8px 10px",
  background: "var(--panel)", border: "1px solid var(--border-2)", color: "var(--ink)",
} as const;

function btn(color: string, enabled = true): React.CSSProperties {
  return {
    ...mono, fontSize: 10, padding: "6px 12px", cursor: enabled ? "pointer" : "not-allowed",
    background: "transparent", border: `1px solid ${color}`, color,
    textTransform: "uppercase", letterSpacing: "0.1em", opacity: enabled ? 1 : 0.5,
  };
}

type Tab = "installed" | "gallery" | "file" | "repo";
const TABS: { id: Tab; label: string }[] = [
  { id: "installed", label: "Installed" },
  { id: "gallery", label: "Gallery" },
  { id: "file", label: "Install from file" },
  { id: "repo", label: "Install from repo URL" },
];

export default function StylesPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("installed");
  const [styles, setStyles] = useState<InstalledStyle[]>([]);
  const [pending, setPending] = useState<PendingInstall[]>([]);
  const [galleryUrl, setGalleryUrl] = useState("");
  const [gallery, setGallery] = useState<GalleryEntry[] | null>(null);
  const [galleryError, setGalleryError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [repoRef, setRepoRef] = useState("");
  const [urlDraft, setUrlDraft] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch("/external-styles")
      .then((r) => r.json())
      .then((d) => {
        setStyles(Array.isArray(d?.styles) ? d.styles : []);
        setPending(Array.isArray(d?.pending) ? d.pending : []);
        setGalleryUrl(typeof d?.gallery_url === "string" ? d.gallery_url : "");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (tab !== "gallery") return;
    setGallery(null);
    setGalleryError("");
    apiFetch("/external-styles/gallery")
      .then((r) => r.json())
      .then((d) => { setGallery(Array.isArray(d?.styles) ? d.styles : []); setGalleryError(d?.error ?? ""); })
      .catch(() => setGalleryError("The gallery could not be read."));
  }, [tab, galleryUrl]);

  async function send(path: string, init: RequestInit) {
    setBusy(true);
    setError("");
    try {
      const r = await apiFetch(path, init);
      const data = await r.json().catch(() => ({}));
      if (!r.ok) { setError(data?.error ?? "That did not work."); return null; }
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function stage(body: Record<string, unknown>) {
    const data = await send("/external-styles/pending", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (data?.id) router.push(`/styles/install/${data.id}`);
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) { setError("The zip is larger than 25 MB."); return; }
    const data = await fileToBase64(file);
    await stage({ kind: "zip", filename: file.name, data });
  }

  async function remove(s: InstalledStyle) {
    if (!window.confirm(`Remove ${s.label} (${s.id})? Its package is deleted from this install.`)) return;
    if (await send(`/external-styles/${s.id}`, { method: "DELETE" })) load();
  }

  async function setAuto(s: InstalledStyle, on: boolean) {
    const ids = styles.filter((x) => x.in_auto && x.id !== s.id).map((x) => x.id);
    const next = on ? [...ids, s.id] : ids;
    const ok = await send("/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ external_styles_in_auto: next }),
    });
    if (ok) load();
  }

  async function saveGalleryUrl() {
    const ok = await send("/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style_gallery_url: (urlDraft ?? "").trim() }),
    });
    if (ok) { setUrlDraft(null); load(); }
  }

  return (
    <main style={{ padding: "24px 32px", maxWidth: 1100 }}>
      <ProfilesNav />
      <h1 style={{ ...mono, fontSize: 16, margin: "0 0 6px" }}>External styles</h1>
      <p style={{ color: "var(--dim)", fontSize: 13, margin: "0 0 14px", maxWidth: 760 }}>
        Visual styles made outside this release: from the Tubematic gallery, a zip file or a git repository.
        A style package is code that runs when a video in it renders. Every install shows you its scan and asks
        for your dashboard password.
      </p>

      <nav data-testid="styles-tabs" style={{ display: "flex", gap: 6, marginBottom: 6 }}>
        {TABS.map((t) => (
          <button key={t.id} type="button" data-testid={`styles-tab-${t.id}`} onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? "page" : undefined}
            style={{ ...btn(tab === t.id ? "var(--amber)" : "var(--dim)") }}>
            {t.label}
          </button>
        ))}
      </nav>
      {error && <p role="alert" data-testid="styles-error" style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}

      {pending.length > 0 && (
        <>
          <SectionLabel label="Waiting for your review" count={String(pending.length)} />
          {pending.map((p) => (
            <div key={p.id} data-testid="pending-row" style={{ display: "flex", gap: 12, alignItems: "center",
              padding: "8px 0", borderBottom: "1px solid var(--border)", fontSize: 13 }}>
              <span style={{ flex: 1 }}>
                {p.label} <span style={{ ...mono, color: "var(--dim)" }}>{p.style_id} {p.version}</span>
                <span style={{ color: "var(--dim)" }}> · {sourceLabel(p.source, p.reviewed)}</span>
              </span>
              <Link href={`/styles/install/${p.id}`} style={btn("var(--amber)")}>Review</Link>
            </div>
          ))}
        </>
      )}

      {tab === "installed" && (
        <>
          <SectionLabel label="Installed" count={String(styles.length)} />
          {styles.length === 0 && <p style={{ color: "var(--dim)", fontSize: 13 }}>No external style is installed.</p>}
          {styles.map((s) => (
            <div key={s.id} data-testid="installed-row" style={{ display: "flex", gap: 14, padding: "10px 0",
              borderBottom: "1px solid var(--border)", alignItems: "flex-start" }}>
              <video src={previewUrls(s.id, true).video} poster={previewUrls(s.id, true).poster} muted loop
                autoPlay playsInline width={68} height={120} style={{ background: "#000", flexShrink: 0 }} />
              <div style={{ flex: 1, fontSize: 13 }}>
                <div>
                  <strong>{s.label}</strong>{" "}
                  <span data-testid="external-badge" style={{ ...mono, fontSize: 9, border: "1px solid var(--cyan, var(--amber))",
                    padding: "1px 4px", letterSpacing: "0.1em" }}>EXTERNAL</span>{" "}
                  {s.reviewed && <span data-testid="reviewed-badge" style={{ ...mono, fontSize: 9, color: "var(--green)",
                    border: "1px solid var(--green)", padding: "1px 4px", letterSpacing: "0.1em" }}>REVIEWED</span>}
                </div>
                <div style={{ ...mono, color: "var(--dim)", fontSize: 11 }}>
                  {s.id} · {s.version || "no version"} · {s.author || "unknown author"} · {sourceLabel(s.source, s.reviewed)}
                  {s.needs_gpu ? " · needs a GPU" : ""}
                </div>
                {!s.ok && (
                  <div data-testid="installed-reason" style={{ color: s.needs_review ? "var(--amber)" : "var(--red)", fontSize: 12 }}>
                    Unavailable: {s.reason}
                  </div>
                )}
                {(s.unfinished_videos > 0 || s.domains.length > 0) && (
                  <div style={{ color: "var(--dim)", fontSize: 12 }}>
                    In use by {s.unfinished_videos} unfinished video{s.unfinished_videos === 1 ? "" : "s"}
                    {s.domains.length ? ` and ${s.domains.map((d) => d.name).join(", ")}` : ""}
                  </div>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                {s.needs_review && (
                  <button type="button" disabled={busy} data-testid="review-installed" style={btn("var(--amber)", !busy)}
                    onClick={() => stage({ kind: "installed", id: s.id })}>Review</button>
                )}
                <label style={{ ...mono, fontSize: 11, display: "flex", gap: 6, alignItems: "center" }}
                  title="Auto may pick this style for a video once it is on">
                  <input type="checkbox" data-testid="auto-toggle" checked={s.in_auto} disabled={busy || !s.ok}
                    onChange={(e) => setAuto(s, e.target.checked)} />
                  Auto may pick it
                </label>
                <button type="button" disabled={busy} data-testid="remove-style" style={btn("var(--red)", !busy)}
                  onClick={() => remove(s)}>Remove</button>
              </div>
            </div>
          ))}
        </>
      )}

      {tab === "gallery" && (
        <>
          <SectionLabel label="Gallery" />
          <p style={{ color: "var(--dim)", fontSize: 13, maxWidth: 760 }}>
            The styles listed at the gallery address below. The Tubematic gallery&apos;s styles were reviewed by a
            person before they were published; a gallery at another address was not. Every download is checked
            against its gallery&apos;s checksum.
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "6px 0 14px", maxWidth: 760 }}>
            <input aria-label="Gallery address" data-testid="gallery-url" style={inputStyle}
              value={urlDraft ?? galleryUrl} placeholder="https://…/index.json"
              onChange={(e) => setUrlDraft(e.target.value)} />
            {urlDraft !== null && urlDraft !== galleryUrl && (
              <button type="button" style={btn("var(--amber)", !busy)} disabled={busy} onClick={saveGalleryUrl}>Save</button>
            )}
          </div>
          {galleryError && <p data-testid="gallery-error" style={{ color: "var(--dim)", fontSize: 13 }}>{galleryError}</p>}
          {gallery === null && !galleryError && <p style={{ color: "var(--dim)", fontSize: 13 }}>Loading…</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14 }}>
            {(gallery ?? []).map((g) => (
              <div key={g.id} data-testid="gallery-card" style={{ border: "1px solid var(--border)", padding: 10, fontSize: 13 }}>
                {g.preview_url && (
                  <video src={g.preview_url} poster={g.poster_url} muted loop autoPlay playsInline
                    style={{ width: "100%", aspectRatio: "9 / 16", background: "#000" }} />
                )}
                <strong>{g.name ?? g.id}</strong>
                <div style={{ ...mono, color: "var(--dim)", fontSize: 11 }}>{g.id} · {g.version} · {g.author}</div>
                {g.tagline && <p style={{ margin: "6px 0", color: "var(--dim)" }}>{g.tagline}</p>}
                {g.needs_gpu && <p style={{ margin: "6px 0", color: "var(--amber)", fontSize: 12 }}>Needs a GPU</p>}
                <button type="button" disabled={busy} style={btn("var(--amber)", !busy)} data-testid="gallery-install"
                  onClick={() => stage({ kind: "gallery", id: g.id })}>
                  {g.installed_version ? (g.installed_version === g.version ? "Reinstall" : `Update from ${g.installed_version}`) : "Install"}
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "file" && (
        <>
          <SectionLabel label="Install from file" />
          <p style={{ color: "var(--dim)", fontSize: 13, maxWidth: 760 }}>
            A zip of one style package (the folder with <code>style.json</code> at its top), up to 25 MB. Nothing
            is installed yet: the next screen shows what is inside.
          </p>
          <input type="file" accept=".zip,application/zip" data-testid="zip-input" disabled={busy}
            onChange={(e) => onFile(e.target.files?.[0])} />
        </>
      )}

      {tab === "repo" && (
        <>
          <SectionLabel label="Install from repo URL" />
          <p style={{ color: "var(--dim)", fontSize: 13, maxWidth: 760 }}>
            A git repository with the package at its root, over https, at a commit or a tag. A branch can change
            after you review it, so name a commit or a tag.
          </p>
          <div style={{ display: "grid", gap: 8, maxWidth: 640 }}>
            <input aria-label="Repository address" data-testid="repo-url" style={inputStyle} value={repoUrl}
              placeholder="https://github.com/someone/my-style" onChange={(e) => setRepoUrl(e.target.value)} />
            <input aria-label="Commit or tag" data-testid="repo-ref" style={inputStyle} value={repoRef}
              placeholder="v1.0.0 or a commit id" onChange={(e) => setRepoRef(e.target.value)} />
            <div>
              <button type="button" data-testid="repo-stage" disabled={busy || !repoUrl.trim() || !repoRef.trim()}
                style={btn("var(--amber)", !busy && !!repoUrl.trim() && !!repoRef.trim())}
                onClick={() => stage({ kind: "git", url: repoUrl.trim(), ref: repoRef.trim() })}>
                {busy ? "Fetching…" : "Fetch and review"}
              </button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
