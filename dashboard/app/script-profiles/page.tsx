"use client";

import { useEffect, useState } from "react";
import type { ScriptProfile, ScriptProfileStatus } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDate } from "@/lib/datetime";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const STATUS_ACCENT: Record<ScriptProfileStatus, string> = {
  PENDING:    "var(--dim)",
  GENERATING: "var(--amber)",
  READY:      "var(--green)",
  FAILED:     "var(--red)",
};

const STATUS_NOTE: Record<ScriptProfileStatus, string> = {
  PENDING:    "Queued — the next scheduled poll builds it.",
  GENERATING: "Being built now by an agent session.",
  READY:      "Selectable on any topic awaiting approval.",
  FAILED:     "Could not be built. Delete it and create a new one.",
};

const mono = { fontFamily: "var(--mono)" } as const;

export default function ScriptProfilesPage() {
  const { timeZone } = useTimeZone();
  const [profiles, setProfiles] = useState<ScriptProfile[]>([]);
  const [selected, setSelected] = useState<ScriptProfile | null>(null);
  const [name, setName] = useState("");
  const [urls, setUrls] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  function load() {
    apiFetch("/script-profiles")
      .then((r) => r.json())
      .then((data: ScriptProfile[]) => setProfiles(Array.isArray(data) ? data : []))
      .catch(() => {});
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5_000);
    return () => clearInterval(id);
  }, []);

  function open(profile: ScriptProfile) {
    // The list payload omits markdown and corpus_summary — fetch the full row.
    apiFetch(`/script-profiles/${profile.id}`)
      .then((r) => r.json())
      .then((full: ScriptProfile) => setSelected(full))
      .catch(() => setSelected(profile));
  }

  async function create() {
    const parsed = urls.split("\n").map((u) => u.trim()).filter(Boolean);
    if (!name.trim() || parsed.length === 0) {
      setError("A name and at least one YouTube URL are required.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const r = await apiFetch("/script-profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), urls: parsed }),
      });
      const data = await r.json();
      if (!r.ok) {
        setError(data?.error ?? "Could not create the profile.");
        return;
      }
      setName("");
      setUrls("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the profile.");
    } finally {
      setCreating(false);
    }
  }

  async function remove(profile: ScriptProfile) {
    if (!confirm(`Delete "${profile.name}"? Videos already using it keep it.`)) return;
    await apiFetch(`/script-profiles/${profile.id}`, { method: "DELETE" });
    if (selected?.id === profile.id) setSelected(null);
    load();
  }

  return (
    <>
      <SectionLabel
        label="Script Profiles"
        count={`${profiles.length} profile${profiles.length !== 1 ? "s" : ""}`}
      />

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* Left: create form + list. minWidth: 0 is what makes the 340px
            basis hold: without it a flex item grows to its min-content width,
            and a profile name with no spaces would crush the detail pane. */}
        <div style={{ flex: "0 0 340px", minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ border: "1px solid var(--border)", padding: "14px" }}>
            <div style={{
              ...mono, fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em",
              color: "var(--dim)", marginBottom: 10,
            }}>
              New profile
            </div>
            <input
              data-testid="profile-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name"
              style={{
                ...mono, fontSize: 12, width: "100%", padding: "8px 10px", marginBottom: 8,
                background: "var(--panel)", border: "1px solid var(--border-2)", color: "var(--ink)",
              }}
            />
            <textarea
              data-testid="profile-urls"
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              placeholder={"YouTube URLs, one per line"}
              rows={4}
              style={{
                ...mono, fontSize: 11, width: "100%", padding: "8px 10px", resize: "vertical",
                background: "var(--panel)", border: "1px solid var(--border-2)", color: "var(--ink)",
              }}
            />
            <div style={{ ...mono, fontSize: 10, color: "var(--dim)", margin: "8px 0", lineHeight: 1.5 }}>
              Their transcripts are analysed into a writing style. The transcripts are fetched now
              and the style is written on the next scheduled poll.
            </div>
            {error && (
              <div data-testid="profile-error" style={{ ...mono, fontSize: 10, color: "var(--red)", marginBottom: 8 }}>
                {error}
              </div>
            )}
            <button
              data-testid="profile-create"
              onClick={create}
              disabled={creating}
              style={{
                ...mono, fontSize: 11, width: "100%", padding: "8px 10px", cursor: "pointer",
                background: "transparent", border: "1px solid var(--amber)", color: "var(--amber)",
                textTransform: "uppercase", letterSpacing: "0.1em",
                opacity: creating ? 0.5 : 1,
              }}
            >
              {creating ? "Fetching transcripts…" : "Create"}
            </button>
          </div>

          {profiles.length === 0 ? (
            <div style={{
              ...mono, fontSize: 10, letterSpacing: "0.24em", color: "var(--mute)",
              textTransform: "uppercase", padding: "16px 0",
            }}>
              — No profiles yet —
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {profiles.map((p) => {
                const isSelected = selected?.id === p.id;
                return (
                  <div
                    key={p.id}
                    data-testid={`profile-row-${p.id}`}
                    onClick={() => open(p)}
                    style={{
                      padding: "12px 14px", cursor: "pointer", transition: "all .12s",
                      background: isSelected ? "var(--panel)" : "transparent",
                      border: `1px solid ${isSelected ? "var(--border-2)" : "var(--border)"}`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span style={{
                        ...mono, fontSize: 12, fontWeight: 700, minWidth: 0, overflowWrap: "anywhere",
                        color: isSelected ? "var(--amber)" : "var(--ink)",
                      }}>
                        {p.name}
                      </span>
                      <span style={{
                        ...mono, fontSize: 9, letterSpacing: "0.12em", padding: "2px 6px",
                        border: `1px solid ${STATUS_ACCENT[p.status]}`,
                        color: STATUS_ACCENT[p.status], textTransform: "uppercase",
                      }}>
                        {p.status}
                      </span>
                    </div>
                    <div style={{ ...mono, fontSize: 10, color: "var(--dim)", marginTop: 4 }}>
                      {p.source_urls.length} source{p.source_urls.length !== 1 ? "s" : ""}
                      {" · "}
                      {formatDate(p.created_at, timeZone)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: read-only detail */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!selected ? (
            <div style={{
              ...mono, fontSize: 10, letterSpacing: "0.24em", color: "var(--mute)",
              textTransform: "uppercase", padding: "24px 0",
            }}>
              — Select a profile —
            </div>
          ) : (
            <div data-testid="profile-detail" style={{ border: "1px solid var(--border)", padding: "18px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <span style={{ ...mono, fontSize: 14, fontWeight: 700, color: "var(--amber)" }}>
                  {selected.name}
                </span>
                <button
                  data-testid="profile-delete"
                  onClick={() => remove(selected)}
                  style={{
                    ...mono, fontSize: 10, padding: "5px 10px", cursor: "pointer",
                    background: "transparent", border: "1px solid var(--red)", color: "var(--red)",
                    textTransform: "uppercase", letterSpacing: "0.1em",
                  }}
                >
                  Delete
                </button>
              </div>

              <div style={{ ...mono, fontSize: 10, color: "var(--dim)", marginTop: 8, lineHeight: 1.6 }}>
                {STATUS_NOTE[selected.status]}
                {selected.error && (
                  <div data-testid="profile-detail-error" style={{ color: "var(--red)", marginTop: 4 }}>
                    {selected.error}
                  </div>
                )}
              </div>

              <Block title="Sources">
                {selected.source_urls.map((u) => (
                  <div key={u} style={{ ...mono, fontSize: 11, color: "var(--mute)" }}>{u}</div>
                ))}
              </Block>

              {selected.corpus_summary && (
                <Block title="Corpus summary">
                  <pre data-testid="profile-summary" style={preStyle}>{selected.corpus_summary}</pre>
                </Block>
              )}

              {selected.markdown && (
                <Block title="Style (read-only — profiles are immutable)">
                  <pre data-testid="profile-markdown" style={preStyle}>{selected.markdown}</pre>
                </Block>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const preStyle: React.CSSProperties = {
  fontFamily: "var(--mono)", fontSize: 11, lineHeight: 1.7, color: "var(--ink)",
  whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0,
  background: "var(--panel)", border: "1px solid var(--border)", padding: "12px 14px",
  maxHeight: 420, overflowY: "auto",
};

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 18 }}>
      <div style={{
        fontFamily: "var(--mono)", fontSize: 9, textTransform: "uppercase",
        letterSpacing: "0.14em", color: "var(--dim)", marginBottom: 8,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}
