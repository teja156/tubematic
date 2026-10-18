"use client";

import { useState } from "react";

// The server's rule (tubematic_core/youtube.py), mirrored so the Add button
// only lights for a URL the API will store. Keep in sync: a URL this accepts
// and the server refuses comes back as a 400 shown under the list; one this
// refuses and the server would accept simply cannot be added from here.
// Scheme and host are case-insensitive there, so they are lowercased first.
const YT_ID = "[A-Za-z0-9_-]{11}";
const YT_TAIL = "[^\\s#]*";
const YT_FRAGMENT = "(?:#\\S*)?";
const YT_HOST = "https?://(?:www\\.|m\\.)?youtube\\.com/";
const YT_PATTERNS = [
  new RegExp(`^${YT_HOST}watch\\?(?:${YT_TAIL}&)?v=(${YT_ID})(?:&${YT_TAIL})?${YT_FRAGMENT}$`),
  new RegExp(`^${YT_HOST}(?:shorts|live)/(${YT_ID})(?:\\?${YT_TAIL})?${YT_FRAGMENT}$`),
  new RegExp(`^https?://youtu\\.be/(${YT_ID})(?:\\?${YT_TAIL})?${YT_FRAGMENT}$`),
];

/** https://www.youtube.com/watch?v=ID for an accepted YouTube video URL, else null. */
export function canonicalYouTubeUrl(raw: string): string | null {
  const text = raw.trim();
  if (!text || !/^[\x20-\x7e]+$/.test(text)) return null;
  const authority = /^[A-Za-z][A-Za-z0-9+.-]*:\/\/[^/?#]*/.exec(text);
  const normalised = authority
    ? authority[0].toLowerCase() + text.slice(authority[0].length)
    : text;
  for (const pattern of YT_PATTERNS) {
    const match = pattern.exec(normalised);
    if (match) return `https://www.youtube.com/watch?v=${match[1]}`;
  }
  return null;
}

interface MiningSourcesProps {
  urls: string[];
  saving: boolean;
  error: string | null;
  onChange: (next: string[]) => void;
}

export function MiningSources({ urls, saving, error, onChange }: MiningSourcesProps) {
  const [input, setInput] = useState("");

  const canonical = canonicalYouTubeUrl(input);

  function handleAdd() {
    if (!canonical || urls.includes(canonical)) return;
    setInput("");
    onChange([...urls, canonical]);
  }

  function handleRemove(url: string) {
    onChange(urls.filter((u) => u !== url));
  }

  const canAdd = canonical !== null && !urls.includes(canonical);

  return (
    <div data-testid="mining-sources-section">
      <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)", letterSpacing: "0.04em", marginBottom: 10 }}>
        YouTube URLs Gemini analyses for spin-off topics (mining strategy — off without a Gemini API key)
      </div>

      {/* URL list */}
      {urls.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
          {urls.map((url) => (
            <div
              key={url}
              data-testid="mining-url-item"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: "var(--panel)",
                border: "1px solid var(--border)",
                padding: "7px 10px",
                gap: 8,
              }}
            >
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-2)", wordBreak: "break-all" }}>
                {url}
              </span>
              <button
                onClick={() => handleRemove(url)}
                disabled={saving}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--mute)",
                  cursor: saving ? "not-allowed" : "pointer",
                  fontFamily: "var(--mono)",
                  fontSize: 14,
                  lineHeight: 1,
                  padding: "0 4px",
                  flexShrink: 0,
                }}
                aria-label={`Remove ${url}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {urls.length === 0 && (
        <div style={{
          fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.24em",
          color: "var(--mute)", textTransform: "uppercase", padding: "12px 0", marginBottom: 12,
        }}>
          — no sources configured —
        </div>
      )}

      {error && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--red)", letterSpacing: "0.08em", marginBottom: 12 }}>
          ✕ {error}
        </div>
      )}

      {/* Add input */}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          data-testid="mining-url-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); }}
          placeholder="https://youtu.be/..."
          style={{
            flex: 1,
            background: "var(--input-bg, var(--panel))",
            border: "1px solid var(--border)",
            color: "var(--ink)",
            fontFamily: "var(--mono)",
            fontSize: 11,
            padding: "7px 10px",
            outline: "none",
          }}
        />
        <button
          data-testid="mining-url-add"
          onClick={handleAdd}
          disabled={!canAdd || saving}
          style={{
            background: canAdd && !saving ? "var(--green, #4ade80)" : "var(--panel)",
            border: "1px solid var(--border)",
            color: canAdd && !saving ? "#000" : "var(--mute)",
            cursor: canAdd && !saving ? "pointer" : "not-allowed",
            fontFamily: "var(--mono)",
            fontSize: 11,
            fontWeight: 700,
            padding: "7px 14px",
            whiteSpace: "nowrap",
          }}
        >
          {saving ? "Saving…" : "Add"}
        </button>
      </div>
    </div>
  );
}
