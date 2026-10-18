"use client";

import { useCallback, useEffect, useState } from "react";
import type { SocialAccount } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  tiktok: "TikTok",
  facebook: "Facebook",
};

const mono = { fontFamily: "var(--mono)" } as const;

// The platforms Tubematic composes posts for (postforme.SUPPORTED_PLATFORMS).
// Keep in sync with renderer/api/postforme.py — the API refuses any other.
const CONNECT_PLATFORMS = ["youtube", "instagram", "tiktok", "facebook"] as const;

export default function SocialsPage() {
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [connecting, setConnecting] = useState("");
  const [connectError, setConnectError] = useState("");
  // The platform whose consent page is open, and its URL when the browser
  // blocked the tab and the user has to open it from a link instead.
  const [pending, setPending] = useState<{ platform: string; url: string } | null>(null);

  const load = useCallback(() => {
    setRefreshing(true);
    return apiFetch("/publishing/accounts")
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) {
          setError(data?.error ?? "Could not load accounts.");
          setAccounts([]);
        } else {
          setError("");
          setAccounts(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => setError("Could not reach the pipeline API."))
      .finally(() => { setLoaded(true); setRefreshing(false); });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(account: SocialAccount) {
    // Only ids are stored — platform and username are hydrated live on every
    // load, so persisting them would just be a second copy going stale.
    const next = accounts
      .filter((a) => (a.id === account.id ? !a.allowed : a.allowed))
      .map((a) => a.id);
    setSaving(true);
    try {
      const r = await apiFetch("/publishing/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_ids: next }),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => null);
        setError(data?.error ?? "Could not save.");
        return;
      }
      setAccounts((prev) =>
        prev.map((a) => (a.id === account.id ? { ...a, allowed: !a.allowed } : a)),
      );
    } finally {
      setSaving(false);
    }
  }

  async function connect(platform: string) {
    // Opened now, inside the click, because a popup blocker only allows
    // window.open during the user gesture — and the URL cannot be fetched in
    // advance: its `state` is single-use, so one is minted per click.
    const tab = window.open("", "_blank");
    if (tab) tab.opener = null;
    setConnecting(platform);
    setConnectError("");
    setPending(null);
    try {
      const r = await apiFetch("/publishing/accounts/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform }),
      });
      const data = await r.json().catch(() => null);
      if (!r.ok || typeof data?.url !== "string") {
        tab?.close();
        // postforme's own message: for a platform not enabled on the postforme
        // project it says where to enable it.
        setConnectError(data?.error ?? "Could not start connecting the account.");
        return;
      }
      if (tab) tab.location.href = data.url;
      setPending({ platform, url: tab ? "" : data.url });
    } catch {
      tab?.close();
      setConnectError("Could not reach the pipeline API.");
    } finally {
      setConnecting("");
    }
  }

  const groups = accounts.reduce<Record<string, SocialAccount[]>>((acc, a) => {
    const key = a.platform || "unknown";
    (acc[key] ??= []).push(a);
    return acc;
  }, {});

  return (
    <>
      <SectionLabel
        label="Socials"
        count={`${accounts.filter((a) => a.allowed).length} Enabled`}
      />

      <p style={{ ...mono, fontSize: 11, color: "var(--mute)", marginBottom: 20, maxWidth: 640 }}>
        Accounts connected to your postforme.dev project. Tick the ones Tubematic may publish to —
        this is an allowlist, not a mirror, so a personal account connected to the same project
        stays untouched unless you enable it here.
      </p>

      {error && (
        <div
          data-testid="socials-error"
          style={{
            ...mono, fontSize: 11, color: "var(--amber)", border: "1px solid var(--border)",
            background: "var(--panel)", padding: "12px 14px", marginBottom: 20, maxWidth: 640,
          }}
        >
          {error}
        </div>
      )}

      {loaded && !error && accounts.length === 0 && (
        <p data-testid="socials-empty" style={{ ...mono, fontSize: 11, color: "var(--dim)" }}>
          No accounts connected yet.
        </p>
      )}

      {Object.entries(groups).map(([platform, list]) => (
        <div key={platform} data-testid={`platform-group-${platform}`} style={{ marginBottom: 26 }}>
          <div
            style={{
              ...mono, fontSize: 10, color: "var(--mute)", textTransform: "uppercase",
              letterSpacing: "0.16em", marginBottom: 10,
            }}
          >
            {PLATFORM_LABEL[platform] ?? platform}
          </div>
          {list.map((account) => (
            <label
              key={account.id}
              data-testid={`account-row-${account.id}`}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                border: "1px solid var(--border)", background: "var(--panel)",
                marginBottom: 8, maxWidth: 640,
                cursor: account.available ? "pointer" : "not-allowed",
                opacity: account.available ? 1 : 0.55,
              }}
            >
              <input
                type="checkbox"
                data-testid={`account-toggle-${account.id}`}
                checked={account.allowed}
                // An account that is gone upstream can still be UNticked —
                // that is how a stale entry gets cleaned out of the allowlist.
                disabled={saving || (!account.available && !account.allowed)}
                onChange={() => toggle(account)}
              />
              <span style={{ ...mono, fontSize: 12, color: "var(--ink)" }}>
                @{account.username || account.id}
              </span>
              {!account.available && (
                <span
                  data-testid={`account-unavailable-${account.id}`}
                  style={{ ...mono, fontSize: 10, color: "var(--amber)" }}
                >
                  NOT CONNECTED
                </span>
              )}
              {account.analytics === false && (
                /* `feeds` is granted separately from posting, at connect time.
                   Without it an account publishes perfectly and produces no
                   metrics, forever, with nothing else ever saying so. */
                <span
                  data-testid={`account-no-analytics-${account.id}`}
                  style={{ ...mono, fontSize: 10, color: "var(--amber)" }}
                  title="This account can publish, but postforme cannot read its feed — reconnect it with the Connect button below, which grants the feeds permission."
                >
                  NO ANALYTICS
                </span>
              )}
              {account.available && account.status !== "connected" && (
                <span style={{ ...mono, fontSize: 10, color: "var(--amber)" }}>
                  {account.status.toUpperCase()}
                </span>
              )}
            </label>
          ))}
        </div>
      ))}

      <div data-testid="connect-accounts" style={{ marginBottom: 26, maxWidth: 640 }}>
        <div
          style={{
            ...mono, fontSize: 10, color: "var(--mute)", textTransform: "uppercase",
            letterSpacing: "0.16em", marginBottom: 10,
          }}
        >
          Connect an account
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {CONNECT_PLATFORMS.map((platform) => (
            <button
              key={platform}
              type="button"
              data-testid={`connect-${platform}`}
              onClick={() => connect(platform)}
              disabled={connecting !== ""}
              style={{
                ...mono, fontSize: 11, color: "var(--blue)",
                border: "1px solid var(--border)", background: "var(--panel)",
                padding: "9px 14px", cursor: connecting ? "default" : "pointer",
                opacity: connecting && connecting !== platform ? 0.5 : 1,
              }}
            >
              {connecting === platform ? "Opening…" : `Connect ${PLATFORM_LABEL[platform]}`}
            </button>
          ))}
        </div>
        {/* Not when it only repeats the page's error above: with publishing
            off or no key, the list and the connect fail with the same 503. */}
        {connectError && connectError !== error && (
          <div
            data-testid="connect-error"
            style={{
              ...mono, fontSize: 11, color: "var(--amber)", border: "1px solid var(--border)",
              background: "var(--panel)", padding: "12px 14px", marginTop: 10,
            }}
          >
            {connectError}
          </div>
        )}
        {pending && (
          <p data-testid="connect-pending" style={{ ...mono, fontSize: 11, color: "var(--ink)", marginTop: 10 }}>
            {pending.url ? (
              <>
                Your browser blocked the new tab —{" "}
                <a data-testid="connect-link" href={pending.url} target="_blank" rel="noopener noreferrer"
                   style={{ color: "var(--blue)" }}>
                  open the {PLATFORM_LABEL[pending.platform]} consent page
                </a>
                .{" "}
              </>
            ) : (
              <>The {PLATFORM_LABEL[pending.platform]} consent page is open in a new tab. </>
            )}
            Finish there — it ends on postforme.dev — then come back and press Refresh accounts
            list below. A new account arrives unticked.
          </p>
        )}
        <p style={{ ...mono, fontSize: 10, color: "var(--mute)", marginTop: 10 }}>
          Connecting here always grants the <strong>feeds</strong> permission as well as posts, so
          the account reports views, likes and comments. postforme grants posts alone by default,
          so an account connected directly on postforme.dev may publish normally but report no
          analytics at all; connect it again here to fix that — it stays the same account, still
          ticked, with its Auto Pilot settings. The permission is chosen when the account is
          connected and cannot be changed afterwards.
        </p>
      </div>

      {/* The list is fetched once on mount and never polled — it changes only
          when someone connects or disconnects an account at postforme, which
          finishes outside this app (a connect started above ends on
          postforme.dev's own page). A button is the honest affordance:
          a poll would spend an API call every few seconds waiting for an event
          that may never come. */}
      <button
        type="button"
        data-testid="refresh-accounts"
        onClick={() => load()}
        disabled={refreshing}
        style={{
          ...mono, fontSize: 11, color: "var(--blue)",
          border: "1px solid var(--border)", background: "var(--panel)",
          padding: "9px 14px", cursor: refreshing ? "default" : "pointer",
          opacity: refreshing ? 0.5 : 1,
        }}
      >
        {refreshing ? "Refreshing…" : "Refresh accounts list"}
      </button>
      <p style={{ ...mono, fontSize: 10, color: "var(--mute)", marginTop: 10, maxWidth: 640 }}>
        Re-reads the accounts connected to your postforme.dev API key. After connecting an
        account above, or connecting or disconnecting one on postforme.dev, refresh here to pick
        up the change.
      </p>
    </>
  );
}
