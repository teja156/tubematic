"use client";

import { useState } from "react";
import { safeNext } from "@/lib/sessionCookie";

const mono = { fontFamily: "var(--mono)" } as const;

const inputStyle = {
  ...mono, fontSize: 12, width: "100%", padding: "8px 10px",
  background: "var(--panel)", border: "1px solid var(--border-2)", color: "var(--ink)",
} as const;

/**
 * The dashboard's one password (TMDEV-152). It is set on the host with
 * `python onboard.py --set-password`; there is no sign-up and no reset here.
 */
export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        // A full load, not a client-side push: the top bar and its pollers
        // mount fresh, now with a session.
        window.location.assign(safeNext(new URLSearchParams(window.location.search).get("next")));
        return;
      }
      const body = await res.json().catch(() => ({}));
      if (res.status === 401) setError("Wrong password.");
      else if (res.status === 429) {
        const wait = res.headers.get("Retry-After");
        setError(`Too many login attempts. Try again${wait ? ` in ${wait}s` : " later"}.`);
      } else setError(typeof body.error === "string" ? body.error : `Login failed (HTTP ${res.status}).`);
    } catch {
      setError("Could not reach the dashboard server.");
    }
    setBusy(false);
    setPassword("");
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "12vh" }}>
      <form
        onSubmit={submit}
        data-testid="login-form"
        style={{
          width: "100%", maxWidth: 360, display: "flex", flexDirection: "column", gap: 14,
          padding: 24, border: "1px solid var(--border-2)", background: "var(--panel)",
        }}
      >
        <div style={{ ...mono, fontWeight: 700, fontSize: 17, color: "var(--ink)", letterSpacing: "0.02em" }}>
          TUBEMATIC
        </div>
        <label style={{ ...mono, fontSize: 11, color: "var(--dim)", display: "flex", flexDirection: "column", gap: 6 }}>
          Password
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            data-testid="login-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={inputStyle}
          />
        </label>
        {error && (
          <div role="alert" data-testid="login-error" style={{ ...mono, fontSize: 11, color: "var(--red)" }}>
            {error}
          </div>
        )}
        <button
          type="submit"
          data-testid="login-submit"
          disabled={!password || busy}
          style={{
            ...mono, fontSize: 11, padding: "9px 14px",
            cursor: !password || busy ? "not-allowed" : "pointer",
            background: "transparent", border: "1px solid var(--amber)", color: "var(--amber)",
            textTransform: "uppercase", letterSpacing: "0.1em",
            opacity: !password || busy ? 0.5 : 1,
          }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div style={{ ...mono, fontSize: 10, color: "var(--mute)" }}>
          Forgot it? On the host: <span style={{ whiteSpace: "nowrap" }}>python onboard.py --set-password</span>
        </div>
      </form>
    </div>
  );
}
