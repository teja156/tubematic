"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import type { UpdateInfo } from "@/lib/updateCheck";

const DISMISSED_KEY = "tubematic.update-dismissed";

// The server caches GitHub's answer for 2 hours, so this poll is cheap; it only
// decides how soon an open page notices a release the server has seen.
const POLL_MS = 10 * 60_000;

function readDismissed(): string | null {
  try {
    return window.localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

function writeDismissed(version: string) {
  try {
    window.localStorage.setItem(DISMISSED_KEY, version);
  } catch {
    // Storage blocked: the dismissal lasts for this page only.
  }
}

const linkStyle = { color: "var(--amber)", textDecoration: "underline", whiteSpace: "nowrap" } as const;

/** "A newer release is out" (TMDEV-114), under the top bar on every page.
 *
 * The server route decides; this only shows its answer. Dismissing remembers
 * the version in this browser, so the banner stays away until a release newer
 * than the dismissed one comes out. Any failure renders nothing.
 *
 * Declared at module scope, like the TopBar components (TMDEV-93). */
export function UpdateBanner() {
  const pathname = usePathname();
  const onLogin = pathname === "/login";
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);

  useEffect(() => {
    setDismissed(readDismissed());
  }, []);

  useEffect(() => {
    // No session on the login page, so the route would only answer 401.
    if (onLogin) return;
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch("/api/update-check", { cache: "no-store" });
        const data: UpdateInfo | null = res.ok ? await res.json() : null;
        if (!cancelled) setInfo(data);
      } catch {
        if (!cancelled) setInfo(null);
      }
    }

    check();
    const id = setInterval(check, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [onLogin]);

  if (onLogin || !info?.available || !info.latest || !info.current) return null;
  if (info.latest === dismissed) return null;
  const { release_url, upgrade_url } = info;
  if (!release_url?.startsWith("https://") || !upgrade_url?.startsWith("https://")) return null;

  return (
    <div
      data-testid="update-banner"
      role="status"
      style={{ background: "var(--amber-soft)", borderBottom: "1px solid var(--border)" }}
    >
      <div
        className="mx-auto flex items-center"
        style={{
          maxWidth: 1640,
          paddingLeft: "var(--gutter)",
          paddingRight: "var(--gutter)",
          paddingTop: 8,
          paddingBottom: 8,
          columnGap: 16,
          rowGap: 4,
          flexWrap: "wrap",
          fontFamily: "var(--mono)",
          fontSize: 12,
          color: "var(--ink)",
        }}
      >
        <span style={{ color: "var(--amber)", fontWeight: 700, letterSpacing: "0.08em" }}>UPDATE</span>
        <span>
          Tubematic v{info.latest} is available. This install is on v{info.current}.
        </span>
        <a data-testid="update-release-link" href={release_url} target="_blank" rel="noopener noreferrer" style={linkStyle}>
          Release notes
        </a>
        <a data-testid="update-guide-link" href={upgrade_url} target="_blank" rel="noopener noreferrer" style={linkStyle}>
          How to upgrade
        </a>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          data-testid="update-dismiss"
          aria-label={`Dismiss the v${info.latest} update notice`}
          title="Hide until a newer release"
          onClick={() => {
            writeDismissed(info.latest!);
            setDismissed(info.latest!);
          }}
          style={{
            background: "transparent", border: "none", padding: 0, cursor: "pointer",
            color: "var(--dim)", fontFamily: "var(--mono)", fontSize: 13,
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
