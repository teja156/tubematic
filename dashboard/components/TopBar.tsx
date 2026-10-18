"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useTimeZone } from "@/components/TimeZoneProvider";
import type { PipelineStatus } from "@/lib/types";

type ApiStatus = "unknown" | "ok" | "error";

function goToLogin() {
  const next = window.location.pathname + window.location.search;
  window.location.assign(next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`);
}

function SignOut() {
  return (
    <button
      type="button"
      data-testid="sign-out"
      onClick={async () => {
        try {
          await fetch("/api/auth/logout", { method: "POST" });
        } finally {
          window.location.assign("/login");
        }
      }}
      style={{
        fontFamily: "var(--mono)", fontSize: 11, color: "var(--dim)", background: "transparent",
        border: "none", padding: 0, cursor: "pointer", whiteSpace: "nowrap",
      }}
    >
      Sign out
    </button>
  );
}

function SysStatus() {
  const [status, setStatus] = useState<ApiStatus>("unknown");
  const [errorMsg, setErrorMsg] = useState("");
  const [tipVisible, setTipVisible] = useState(false);
  const tipRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    async function check() {
      try {
        const res = await fetch("/api/proxy/stats", { cache: "no-store" });
        if (res.status === 401) {
          // The session expired or was signed out elsewhere (a new password
          // signs every browser out). This poll runs on every page, so it is
          // the one place that notices.
          goToLogin();
          return;
        }
        if (res.ok) {
          setStatus("ok");
          setErrorMsg("");
        } else {
          setStatus("error");
          setErrorMsg(`API returned HTTP ${res.status}`);
        }
      } catch (e) {
        setStatus("error");
        setErrorMsg(e instanceof Error ? e.message : "Connection failed");
      }
    }
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  const dotColor =
    status === "ok" ? "var(--green)" :
    status === "error" ? "var(--red)" :
    "var(--mute)";

  const label =
    status === "ok" ? "NOMINAL" :
    status === "error" ? "ERROR" :
    "…";

  return (
    <span
      style={{ position: "relative", cursor: status === "error" ? "default" : undefined }}
      onMouseEnter={() => {
        if (status === "error") {
          if (tipRef.current) clearTimeout(tipRef.current);
          setTipVisible(true);
        }
      }}
      onMouseLeave={() => {
        tipRef.current = setTimeout(() => setTipVisible(false), 100);
      }}
    >
      SYS{" "}
      <span data-testid="health-status" style={{ color: dotColor }}>
        ● {label}
      </span>

      {tipVisible && errorMsg && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 10px)",
            background: "var(--panel)",
            border: "1px solid var(--red)",
            padding: "6px 12px",
            fontFamily: "var(--mono)",
            fontSize: 10,
            color: "var(--red)",
            letterSpacing: "0.08em",
            whiteSpace: "nowrap",
            zIndex: 200,
            boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
            pointerEvents: "none",
          }}
        >
          {errorMsg}
        </div>
      )}
    </span>
  );
}

function TimeZoneBadge() {
  const { timeZone, label } = useTimeZone();
  return (
    <span data-testid="tz-badge" title={timeZone}>
      {label}
    </span>
  );
}

/** The installed version, so a running install can say which one it is and a bug
 * report is unambiguous.
 *
 * It rides on /pipeline/status, which the API already serves the host timezone on
 * for the same reason: the dashboard deliberately has no env_file and no second
 * source of truth, and tubematic_core/version.py stays the one definition. The
 * dashboard image cannot read VERSION itself — its build context is dashboard/
 * only.
 *
 * Renders nothing when the value is missing, empty, or the fetch failed. No
 * "unknown", no fallback number: a wrong version in a bug report is worse than
 * none, and a dev checkout's VERSION is the next version being worked on rather
 * than one that was ever released, so there is no safe guess to make.
 *
 * **Polled, not fetched once.** "The version cannot change while the page is
 * open" is false in the one case this badge exists for: an upgrade restarts the
 * API under a page the user left open, and the documented way to confirm an
 * upgrade landed is to look here. A once-on-mount fetch would keep showing the
 * *old* version precisely then — the stale value the feature is meant to rule
 * out. The same effect covers a first load that raced the API's startup, which
 * would otherwise leave the badge blank until a manual reload.
 *
 * Clearing on failure is deliberate and follows from the same rule: during the
 * restart the last known version is a stale value, so it goes away and comes back
 * with whatever is now serving. SysStatus turns red over the same window, so the
 * bar reads consistently rather than showing a version beside a dead API.
 *
 * Declared at module scope, like every other component in this file. A component
 * declared inside another component's body gets a fresh function identity on
 * every render, so React treats it as a different component type and rebuilds its
 * DOM — which is exactly how the Settings SAVE button came to swallow its first
 * click (TMDEV-93). */
function VersionBadge() {
  const [version, setVersion] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch("/api/proxy/pipeline/status", { cache: "no-store" });
        if (!res.ok) {
          if (!cancelled) setVersion("");
          return;
        }
        const data: Partial<PipelineStatus> = await res.json();
        if (cancelled) return;
        setVersion(typeof data.version === "string" ? data.version : "");
      } catch {
        if (!cancelled) setVersion("");
      }
    }

    check();
    const id = setInterval(check, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (!version) return null;
  return <span data-testid="version-badge">v{version}</span>;
}

export function TopBar() {
  const pathname = usePathname();
  const isNewVideo = pathname.startsWith("/new-video");
  const isLibrary  = pathname.startsWith("/library");
  const isArchive  = pathname.startsWith("/archive");
  const isTopics   = pathname.startsWith("/topics");
  const isProjects = pathname.startsWith("/projects");
  const isProfiles = pathname.startsWith("/script-profiles");
  const isSocials  = pathname.startsWith("/socials");
  const isAnalytics = pathname.startsWith("/analytics");
  const isLogs     = pathname.startsWith("/logs");
  const isSettings = pathname.startsWith("/settings");

  // No chrome on the login page, and none of the pollers below: every one of
  // them would answer 401 there.
  if (pathname === "/login") return null;

  return (
    <header
      className="tm-topbar sticky top-0 z-50 border-b"
      style={{
        height: "var(--hd-height)",
        borderColor: "var(--border)",
      }}
    >
      {/* One row on a wide screen, two when it would not fit — the layout
          is in globals.css (.tm-topbar-*) because it needs a media query. */}
      <div
        className="tm-topbar-row mx-auto flex h-full items-center"
        style={{
          maxWidth: "1640px",
          paddingLeft: "var(--gutter)",
          paddingRight: "var(--gutter)",
          columnGap: "28px",
        }}
      >
        {/* Brand */}
        <div
          className="flex items-center"
          style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: 17, color: "var(--ink)", gap: 12, letterSpacing: "0.02em" }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo-mark.svg"
            alt="TubeMatic"
            width={36}
            height={36}
            style={{
              display: "block",
              flexShrink: 0,
              animation: "tm-pulse 2.4s ease-in-out infinite",
            }}
          />
          TUBEMATIC
        </div>

        {/* Divider */}
        <div className="tm-topbar-divider" style={{ width: 1, height: 18, background: "var(--border-2)", flexShrink: 0 }} />

        {/* Tabs */}
        <nav className="tm-topbar-nav" data-testid="topbar-nav" style={{ display: "flex", gap: 4, whiteSpace: "nowrap" }}>
          <Link
            href="/"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: pathname === "/" ? "var(--amber)" : "var(--dim)",
              background: pathname === "/" ? "var(--panel)" : "transparent",
              borderColor: pathname === "/" ? "var(--border-2)" : "transparent",
              boxShadow: pathname === "/" ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {pathname === "/" && <span style={{ opacity: 0.7 }}>▸ </span>}
            Pipeline
          </Link>
          <Link
            href="/new-video"
            data-testid="nav-new-video"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isNewVideo ? "var(--amber)" : "var(--dim)",
              background: isNewVideo ? "var(--panel)" : "transparent",
              borderColor: isNewVideo ? "var(--border-2)" : "transparent",
              boxShadow: isNewVideo ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
              // The only two-word tab; without this it wraps onto two lines
              // at 1280px, the bar already being close to full.
              whiteSpace: "nowrap",
            }}
          >
            {isNewVideo && <span style={{ opacity: 0.7 }}>▸ </span>}
            New Video
          </Link>
          <Link
            href="/library"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isLibrary ? "var(--amber)" : "var(--dim)",
              background: isLibrary ? "var(--panel)" : "transparent",
              borderColor: isLibrary ? "var(--border-2)" : "transparent",
              boxShadow: isLibrary ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isLibrary && <span style={{ opacity: 0.7 }}>▸ </span>}
            Library
          </Link>
          <Link
            href="/archive"
            data-testid="nav-archive"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isArchive ? "var(--amber)" : "var(--dim)",
              background: isArchive ? "var(--panel)" : "transparent",
              borderColor: isArchive ? "var(--border-2)" : "transparent",
              boxShadow: isArchive ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isArchive && <span style={{ opacity: 0.7 }}>▸ </span>}
            Archive
          </Link>
          <Link
            href="/topics"
            data-testid="nav-topics"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isTopics ? "var(--amber)" : "var(--dim)",
              background: isTopics ? "var(--panel)" : "transparent",
              borderColor: isTopics ? "var(--border-2)" : "transparent",
              boxShadow: isTopics ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isTopics && <span style={{ opacity: 0.7 }}>▸ </span>}
            Topics
          </Link>
          <Link
            href="/projects"
            data-testid="nav-projects"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isProjects ? "var(--amber)" : "var(--dim)",
              background: isProjects ? "var(--panel)" : "transparent",
              borderColor: isProjects ? "var(--border-2)" : "transparent",
              boxShadow: isProjects ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isProjects && <span style={{ opacity: 0.7 }}>▸ </span>}
            Projects
          </Link>
          <Link
            href="/script-profiles"
            data-testid="nav-script-profiles"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isProfiles ? "var(--amber)" : "var(--dim)",
              background: isProfiles ? "var(--panel)" : "transparent",
              borderColor: isProfiles ? "var(--border-2)" : "transparent",
              boxShadow: isProfiles ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isProfiles && <span style={{ opacity: 0.7 }}>▸ </span>}
            Profiles
          </Link>
          <Link
            href="/socials"
            data-testid="nav-socials"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isSocials ? "var(--amber)" : "var(--dim)",
              background: isSocials ? "var(--panel)" : "transparent",
              borderColor: isSocials ? "var(--border-2)" : "transparent",
              boxShadow: isSocials ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isSocials && <span style={{ opacity: 0.7 }}>▸ </span>}
            Socials
          </Link>
          <Link
            href="/analytics"
            data-testid="nav-analytics"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isAnalytics ? "var(--amber)" : "var(--dim)",
              background: isAnalytics ? "var(--panel)" : "transparent",
              borderColor: isAnalytics ? "var(--border-2)" : "transparent",
              boxShadow: isAnalytics ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isAnalytics && <span style={{ opacity: 0.7 }}>▸ </span>}
            Analytics
          </Link>
          <Link
            href="/logs"
            data-testid="nav-logs"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isLogs ? "var(--amber)" : "var(--dim)",
              background: isLogs ? "var(--panel)" : "transparent",
              borderColor: isLogs ? "var(--border-2)" : "transparent",
              boxShadow: isLogs ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isLogs && <span style={{ opacity: 0.7 }}>▸ </span>}
            Logs
          </Link>
          <Link
            href="/settings"
            data-testid="nav-settings"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              letterSpacing: "0.04em",
              padding: "6px 8px",
              border: "1px solid transparent",
              cursor: "pointer",
              transition: "color .12s, border-color .12s, background .12s",
              textDecoration: "none",
              color: isSettings ? "var(--amber)" : "var(--dim)",
              background: isSettings ? "var(--panel)" : "transparent",
              borderColor: isSettings ? "var(--border-2)" : "transparent",
              boxShadow: isSettings ? "inset 0 0 0 1px rgba(245,166,35,0.06)" : undefined,
            }}
          >
            {isSettings && <span style={{ opacity: 0.7 }}>▸ </span>}
            Settings
          </Link>
        </nav>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Right meta */}
        <div
          data-testid="topbar-meta"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 18,
            fontFamily: "var(--mono)",
            fontSize: 11,
            color: "var(--dim)",
            whiteSpace: "nowrap",
          }}
        >
          <VersionBadge />
          <TimeZoneBadge />
          <SysStatus />
          <SignOut />
          <span
            style={{
              display: "inline-block",
              width: 7,
              height: 12,
              background: "var(--amber)",
              marginLeft: 4,
              verticalAlign: "middle",
              animation: "tm-blink 1s steps(2) infinite",
            }}
          />
        </div>
      </div>
    </header>
  );
}
