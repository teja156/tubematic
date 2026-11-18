"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ProfilesNav } from "@/components/ProfilesNav";
import { SectionLabel } from "@/components/SectionLabel";
import {
  AUDIT_LABELS, type PendingInstall, installBlocked, installWarning, sourceLabel,
} from "@/lib/externalStyles";

// The install screen (TMDEV-253): everything a person should see before a
// style package's code runs on this install, and the one place an install is
// confirmed. The password is what tells the API a person, not an agent, said yes.

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const mono = { fontFamily: "var(--mono)" } as const;

function btn(color: string, enabled = true): React.CSSProperties {
  return {
    ...mono, fontSize: 10, padding: "6px 12px", cursor: enabled ? "pointer" : "not-allowed",
    background: "transparent", border: `1px solid ${color}`, color,
    textTransform: "uppercase", letterSpacing: "0.1em", opacity: enabled ? 1 : 0.5,
  };
}

export default function InstallScreen() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rec, setRec] = useState<PendingInstall | null>(null);
  const [loadError, setLoadError] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shown, setShown] = useState<{ path: string; text: string } | null>(null);

  useEffect(() => {
    apiFetch(`/external-styles/pending/${encodeURIComponent(id)}`)
      .then(async (r) => {
        const d = await r.json().catch(() => ({}));
        if (r.ok) setRec(d as PendingInstall); else setLoadError(d?.error ?? "This install is not waiting any more.");
      })
      .catch(() => setLoadError("The install could not be read."));
  }, [id]);

  async function show(path: string) {
    const r = await apiFetch(`/external-styles/pending/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`);
    const d = await r.json().catch(() => ({}));
    setShown(r.ok ? { path, text: d.text } : { path, text: d?.error ?? "This file cannot be shown." });
  }

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      const r = await apiFetch(`/external-styles/pending/${encodeURIComponent(id)}/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setError(d?.error ?? "The style was not installed."); return; }
      router.push("/styles");
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function discard() {
    setBusy(true);
    await apiFetch(`/external-styles/pending/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
    router.push("/styles");
  }

  if (loadError) {
    return (
      <main style={{ padding: "24px 32px" }}>
        <ProfilesNav />
        <p role="alert" data-testid="install-load-error" style={{ color: "var(--red)" }}>{loadError}</p>
        <Link href="/styles">Back to styles</Link>
      </main>
    );
  }
  if (!rec) return <main style={{ padding: "24px 32px" }}><ProfilesNav /><p>Loading…</p></main>;

  const warning = installWarning(rec);
  const blocked = installBlocked(rec);
  const inUse = rec.in_use?.videos.length ?? 0;

  return (
    <main style={{ padding: "24px 32px", maxWidth: 1100 }}>
      <ProfilesNav />
      <h1 style={{ ...mono, fontSize: 16, margin: "0 0 4px" }}>
        Install {rec.label}{" "}
        {rec.reviewed && <span data-testid="install-reviewed" style={{ ...mono, fontSize: 10, color: "var(--green)",
          border: "1px solid var(--green)", padding: "1px 5px", letterSpacing: "0.1em" }}>REVIEWED</span>}
      </h1>
      <div style={{ ...mono, color: "var(--dim)", fontSize: 12, lineHeight: 1.7 }}>
        <div>{rec.style_id} · version {rec.version || "?"} · by {rec.author || "unknown"} · licence {rec.licence || "?"}</div>
        <div>Source: {sourceLabel(rec.source)}</div>
        {rec.homepage && <div>Homepage: {rec.homepage}</div>}
        <div>Renderer: {rec.renderer === "cartoon_3d" ? "3D world (its own runner)" : "scene components"}
          {rec.needs_gpu ? " · needs a GPU" : ""}</div>
        <div>Fingerprint {rec.fingerprint} · waits until {rec.expires_at}</div>
      </div>

      <div data-testid="install-warning" data-level={warning.level} style={{ margin: "14px 0", padding: "10px 12px", fontSize: 13,
        border: `1px solid ${warning.level === "reviewed" ? "var(--amber)" : "var(--red)"}`,
        color: warning.level === "reviewed" ? "var(--ink)" : "var(--red)" }}>
        {warning.text}
      </div>

      {rec.replaces && (
        <p data-testid="install-replaces" style={{ fontSize: 13 }}>
          This replaces the installed version {rec.replaces.version || "(no version)"}
          {inUse ? `, which ${inUse} unfinished video${inUse === 1 ? " uses" : "s use"}: each one is looked at again before it renders` : ""}.
        </p>
      )}

      <SectionLabel label="Checks" />
      <p data-testid="install-check" style={{ fontSize: 13, color: rec.check.ok ? "var(--green)" : "var(--red)" }}>
        {rec.check.ok ? "The package passes Tubematic's package checks." : `Package check failed: ${rec.check.reason}`}
      </p>
      {rec.scan.refusals.map((r) => (
        <p key={r} data-testid="install-refusal" style={{ fontSize: 13, color: "var(--red)" }}>Refused: {r}</p>
      ))}
      {rec.scan.flags.length === 0 && rec.scan.refusals.length === 0 && (
        <p style={{ fontSize: 13, color: "var(--dim)" }}>The scan flagged nothing. A clean scan is not a review.</p>
      )}
      {rec.scan.flags.length > 0 && (
        <ul data-testid="install-flags" style={{ fontSize: 13, paddingLeft: 18 }}>
          {rec.scan.flags.map((f, i) => (
            <li key={i}><span style={mono}>{f.file}{f.line ? `:${f.line}` : ""}</span> {f.what}</li>
          ))}
        </ul>
      )}

      <SectionLabel label="Agent's audit" />
      {rec.audit ? (
        <div data-testid="install-audit" style={{ fontSize: 13 }}>
          <strong>{AUDIT_LABELS[rec.audit.verdict] ?? rec.audit.verdict}</strong>
          <span style={{ color: "var(--dim)" }}> (written by the agent that staged this package; it can be wrong)</span>
          <pre style={{ whiteSpace: "pre-wrap", ...mono, fontSize: 12 }}>{rec.audit.notes}</pre>
        </div>
      ) : (
        <p style={{ fontSize: 13, color: "var(--dim)" }}>No agent audited this package.</p>
      )}

      <SectionLabel label="Files" count={String(rec.scan.files.length)} />
      <table style={{ fontSize: 12, ...mono, borderCollapse: "collapse" }}>
        <tbody>
          {rec.scan.files.map((f) => (
            <tr key={f.path} data-testid="install-file">
              <td style={{ padding: "2px 12px 2px 0" }}>
                {f.lines !== undefined
                  ? <button type="button" onClick={() => show(f.path)} style={{ ...mono, background: "none", border: "none",
                      color: "var(--amber)", cursor: "pointer", padding: 0 }}>{f.path}</button>
                  : f.path}
              </td>
              <td style={{ padding: "2px 12px", color: "var(--dim)", textAlign: "right" }}>
                {f.lines !== undefined ? `${f.lines} lines` : ""}
              </td>
              <td style={{ padding: "2px 0", color: "var(--dim)", textAlign: "right" }}>{f.bytes.toLocaleString()} B</td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown && (
        <div data-testid="install-file-view" style={{ marginTop: 10 }}>
          <div style={{ ...mono, fontSize: 11, color: "var(--dim)" }}>{shown.path}</div>
          <pre style={{ ...mono, fontSize: 11, maxHeight: 420, overflow: "auto", background: "var(--panel)",
            padding: 10, whiteSpace: "pre" }}>{shown.text}</pre>
        </div>
      )}

      <SectionLabel label="Imports" />
      <p style={{ ...mono, fontSize: 12 }}>
        {Object.entries(rec.scan.imports).map(([k, n]) => `${k} (${n})`).join(" · ") || "none"}
      </p>

      <SectionLabel label="Guide the agent reads" />
      <pre data-testid="install-guide" style={{ ...mono, fontSize: 12, whiteSpace: "pre-wrap", maxHeight: 360,
        overflow: "auto", background: "var(--panel)", padding: 10 }}>{rec.scan.guide}</pre>
      <p style={{ fontSize: 12, color: "var(--dim)" }}>
        Your agent reads this as reference material. Tubematic&apos;s rules and checkpoints stay above it, but a guide
        can still try to mislead an agent: read it.
      </p>

      <SectionLabel label="Install" />
      {blocked ? (
        <p data-testid="install-blocked" style={{ color: "var(--red)", fontSize: 13 }}>{blocked}</p>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); if (password) confirm(); }}
          style={{ display: "flex", gap: 8, alignItems: "center", maxWidth: 560 }}>
          <input type="password" aria-label="Dashboard password" data-testid="install-password" autoComplete="current-password"
            placeholder="Your dashboard password" value={password} onChange={(e) => setPassword(e.target.value)}
            style={{ ...mono, fontSize: 12, flex: 1, padding: "8px 10px", background: "var(--panel)",
              border: "1px solid var(--border-2)", color: "var(--ink)" }} />
          <button type="submit" data-testid="install-confirm" disabled={busy || !password}
            style={btn("var(--amber)", !busy && !!password)}>{busy ? "Installing…" : "Install"}</button>
        </form>
      )}
      {error && <p role="alert" data-testid="install-error" style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}
      <p style={{ marginTop: 14 }}>
        <button type="button" data-testid="install-discard" disabled={busy} onClick={discard} style={btn("var(--dim)", !busy)}>
          Discard
        </button>
      </p>
    </main>
  );
}
