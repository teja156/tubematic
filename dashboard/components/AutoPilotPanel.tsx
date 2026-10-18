"use client";

// Settings → Auto Pilot (TMDEV-139): which projects run with no human
// checkpoint, which accounts each posts to, and how fast.
//
// Self-contained like CostsPanel — it reads and writes /autopilot as one
// document and sits outside the settings form's Save/dirty machinery, so the
// switch can never be saved "on" over a project list that failed to save.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import type { Project, SocialAccount } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  AUTO_PILOT_DISCLAIMER, AUTO_PILOT_POLL_MS, MAX_AUTO_PILOT_DAILY, MAX_AUTO_PILOT_GAP_MINS, MAX_AUTO_PILOT_IN_FLIGHT,
  ceilingStatus, gapMins, needsConfirmation, newlyApproved, splitGap,
} from "@/lib/autoPilot";
import type { AutoPilotConfig, AutoPilotState, GapUnit } from "@/lib/autoPilot";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const mono = { fontFamily: "var(--mono)" } as const;
const note: CSSProperties = { ...mono, fontSize: 10, color: "var(--mute)", letterSpacing: "0.02em" };
const row: CSSProperties = {
  display: "flex", alignItems: "center", gap: 16, padding: "10px 0",
  borderBottom: "1px solid var(--border)",
};
const label: CSSProperties = { ...mono, fontSize: 12, color: "var(--ink-2)" };
const button: CSSProperties = {
  ...mono, fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", padding: "7px 16px",
  border: "1px solid var(--border-2)", background: "var(--panel)", color: "var(--ink)",
  cursor: "pointer",
};

function isState(body: unknown): body is AutoPilotState {
  const b = body as AutoPilotState | null;
  return !!b && typeof b.enabled === "boolean" && typeof b.gap_mins === "number"
    && typeof b.max_in_flight === "number" && typeof b.in_flight === "number"
    && !!b.projects && typeof b.projects === "object" && !Array.isArray(b.projects)
    && !!b.account_limits && typeof b.account_limits === "object";
}

export function Disclaimer({ testId }: { testId: string }) {
  return (
    <div
      data-testid={testId}
      role="note"
      style={{ border: "1px solid var(--amber)", padding: 12, margin: "10px 0 14px" }}
    >
      <div style={{ ...mono, fontSize: 11, fontWeight: 700, color: "var(--amber)",
                    letterSpacing: "0.06em", marginBottom: 6 }}>
        READ BEFORE TURNING THIS ON
      </div>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {AUTO_PILOT_DISCLAIMER.map((line) => (
          <li key={line} style={{ ...mono, fontSize: 11, lineHeight: 1.6, color: "var(--ink-2)" }}>
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AutoPilotPanel({ inputStyle }: { inputStyle: CSSProperties }) {
  const [saved, setSaved] = useState<AutoPilotState | null>(null);
  const [draft, setDraft] = useState<AutoPilotConfig | null>(null);
  const [gapUnit, setGapUnit] = useState<GapUnit>("hours");
  const [gapText, setGapText] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  // null = publishing is off or postforme is unreachable: no accounts to offer.
  const [accounts, setAccounts] = useState<SocialAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  function adopt(state: AutoPilotState) {
    setSaved(state);
    setDraft({ enabled: state.enabled, gap_mins: state.gap_mins,
               max_in_flight: state.max_in_flight,
               projects: state.projects, account_limits: state.account_limits });
    const gap = splitGap(state.gap_mins);
    setGapUnit(gap.unit);
    setGapText(String(gap.value));
  }

  useEffect(() => {
    (async () => {
      try {
        const [ap, pr, ac] = await Promise.all([
          apiFetch("/autopilot"), apiFetch("/projects"),
          apiFetch("/publishing/accounts?feeds=0"),
        ]);
        const state = await ap.json();
        // Shape-checked: a failed or mis-routed response must never be read as
        // "Auto Pilot is off and nothing is selected", then saved back.
        if (!ap.ok || !isState(state)) {
          setError((state && state.error) || `Could not load Auto Pilot (HTTP ${ap.status}).`);
          return;
        }
        adopt(state);
        const list = await pr.json();
        setProjects(Array.isArray(list) ? list : []);
        const accts = ac.ok ? await ac.json() : null;
        setAccounts(Array.isArray(accts)
          ? accts.filter((a: SocialAccount) => a.allowed && a.available) : null);
      } catch {
        setError("Could not load Auto Pilot.");
      }
    })();
  }, []);

  // The worker schedules and releases posts while this tab sits open. Only the
  // count is refreshed: the draft and the saved configuration it is compared
  // against are left alone, so unsaved edits stay unsaved and stay dirty.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const r = await apiFetch("/autopilot");
        const body = await r.json();
        if (r.ok && isState(body))
          setSaved((s) => (s ? { ...s, in_flight: body.in_flight } : s));
      } catch {
        // A missed refresh keeps the last count; the next one tries again.
      }
    }, AUTO_PILOT_POLL_MS);
    return () => clearInterval(id);
  }, []);

  if (error && !draft) {
    return <div data-testid="auto-pilot-error" style={{ ...mono, fontSize: 11, color: "var(--red)" }}>{error}</div>;
  }
  if (!draft || !saved) return null;

  const dirty = JSON.stringify(draft) !== JSON.stringify({
    enabled: saved.enabled, gap_mins: saved.gap_mins, max_in_flight: saved.max_in_flight,
    projects: saved.projects, account_limits: saved.account_limits,
  });
  const selected = Object.keys(draft.projects);
  const accountName = (a: SocialAccount) => `@${a.username || a.id} (${a.platform})`;

  function edit(partial: Partial<AutoPilotConfig>) {
    setMessage(null);
    setDraft((d) => (d ? { ...d, ...partial } : d));
  }

  function commitGap(text: string, unit: GapUnit) {
    const value = parseInt(text, 10);
    const mins = gapMins(value, unit);
    if (isNaN(value) || value < 0 || mins > MAX_AUTO_PILOT_GAP_MINS) {
      const gap = splitGap(draft!.gap_mins);
      setGapUnit(gap.unit);
      setGapText(String(gap.value));
      return;
    }
    edit({ gap_mins: mins });
  }

  function setCeiling(text: string) {
    const n = parseInt(text, 10);
    if (isNaN(n) || n < 0 || n > MAX_AUTO_PILOT_IN_FLIGHT) return;
    edit({ max_in_flight: n });
  }

  function toggleProject(pid: string) {
    const next = { ...draft!.projects };
    if (pid in next) delete next[pid];
    else next[pid] = [];
    edit({ projects: next });
  }

  function toggleAccount(pid: string, aid: string) {
    const current = draft!.projects[pid] ?? [];
    const next = current.includes(aid) ? current.filter((a) => a !== aid) : [...current, aid];
    edit({ projects: { ...draft!.projects, [pid]: next.sort() } });
  }

  function setLimit(aid: string, text: string) {
    const n = parseInt(text, 10);
    if (isNaN(n) || n < 0 || n > MAX_AUTO_PILOT_DAILY) return;
    edit({ account_limits: { ...draft!.account_limits, [aid]: n } });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await apiFetch("/autopilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok || !isState(body)) {
        setError(`Save failed — ${(body && body.error) || `HTTP ${r.status}`}`);
        return;
      }
      adopt(body);
      setMessage("Saved.");
    } catch {
      setError("Save failed — could not reach the API.");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  function requestSave() {
    if (needsConfirmation(saved!, draft!)) setConfirming(true);
    else save();
  }

  const approvedNow = newlyApproved(saved, draft);
  const ceiling = ceilingStatus(saved);

  return (
    <div data-testid="section-auto-pilot">
      <SectionLabel label="Auto Pilot" />
      <Disclaimer testId="auto-pilot-disclaimer" />

      <div style={row}>
        <div style={{ flex: 1 }}>
          <div style={label}>Auto Pilot</div>
          <div style={{ ...note, marginTop: 3 }}>
            For the projects selected below, topics, scripts and finished videos are approved
            automatically and the video is posted. Projects not selected still wait for you at
            every checkpoint. Pausing the pipeline pauses Auto Pilot.
          </div>
        </div>
        <button
          data-testid="toggle-auto-pilot"
          onClick={() => edit({ enabled: !draft.enabled })}
          style={{
            ...button,
            border: `1px solid ${draft.enabled ? "var(--amber)" : "var(--border)"}`,
            background: draft.enabled ? "var(--amber-soft)" : "var(--panel)",
            color: draft.enabled ? "var(--amber)" : "var(--mute)",
          }}
        >
          {draft.enabled ? "ON" : "OFF"}
        </button>
      </div>

      <div style={row}>
        <div style={{ flex: 1 }}>
          <div style={label}>Gap between publishes</div>
          <div style={{ ...note, marginTop: 3 }}>
            The shortest time between two posts on the same account. Posts made by hand count
            too. When an account has had its posts for the day, the next one goes out just
            after midnight unless this gap pushes it later, so a gap of 24 hours divided by
            the daily number keeps posts at a steady time of day.
          </div>
        </div>
        <input
          data-testid="input-auto-pilot-gap"
          type="number"
          min={0}
          value={gapText}
          onChange={(e) => setGapText(e.target.value)}
          onBlur={() => commitGap(gapText, gapUnit)}
          onKeyDown={(e) => { if (e.key === "Enter") commitGap(gapText, gapUnit); }}
          style={{ ...inputStyle, width: 80 }}
        />
        <select
          data-testid="select-auto-pilot-gap-unit"
          value={gapUnit}
          onChange={(e) => {
            const unit = e.target.value as GapUnit;
            setGapUnit(unit);
            commitGap(gapText, unit);
          }}
          style={{ ...inputStyle, width: 110 }}
        >
          <option value="minutes">minutes</option>
          <option value="hours">hours</option>
        </select>
      </div>

      <div style={row}>
        <div style={{ flex: 1 }}>
          <div style={label}>Most videos in progress</div>
          <div style={{ ...note, marginTop: 3 }}>
            Videos voiced and not yet published in Auto Pilot projects, plus every post waiting
            to go out (posts scheduled by hand count too). At the limit Auto Pilot stops voicing
            new scripts and approving topics; it keeps approving finished videos and scheduling
            posts, and each video that publishes lets one more through. Size it in days of
            posting: at 5 posts a day, 15 to 25. 0 means no limit.
          </div>
          {ceiling && (
            <div data-testid="auto-pilot-ceiling"
                 style={{ ...note, marginTop: 6,
                          color: ceiling.paused ? "var(--amber)" : "var(--dim)" }}>
              {ceiling.text}
            </div>
          )}
        </div>
        <input
          data-testid="input-auto-pilot-max-in-flight"
          type="number"
          min={0}
          max={MAX_AUTO_PILOT_IN_FLIGHT}
          value={draft.max_in_flight}
          onChange={(e) => setCeiling(e.target.value)}
          style={{ ...inputStyle, width: 80 }}
        />
      </div>

      <SectionLabel label="Projects" count={`${selected.length} on Auto Pilot`} />
      {accounts === null && (
        <div data-testid="auto-pilot-no-publishing" style={{ ...note, color: "var(--amber)", margin: "6px 0 10px" }}>
          Publishing is off or postforme could not be reached, so there are no accounts to
          choose. Selected projects are still approved automatically and then wait at Video
          Approved for you to publish.
        </div>
      )}
      {projects.length === 0 && <div style={note}>No projects yet.</div>}
      {projects.map((p) => {
        const on = p.id in draft.projects;
        const chosen = draft.projects[p.id] ?? [];
        // Chosen earlier, no longer offered: switched off on the Socials page,
        // disconnected, or publishing is off. Shown so it can be unticked —
        // hidden, it would ride along in every save with no way to remove it.
        const offered = new Set((accounts ?? []).map((a) => a.id));
        const stale = chosen.filter((id) => !offered.has(id));
        return (
          <div key={p.id} data-testid={`auto-pilot-project-${p.id}`}
               style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
            <label style={{ ...label, display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input
                data-testid={`auto-pilot-project-toggle-${p.id}`}
                type="checkbox"
                checked={on}
                onChange={() => toggleProject(p.id)}
              />
              <span style={{ overflowWrap: "anywhere" }}>{p.name}</span>
            </label>
            {on && (
              <div style={{ margin: "8px 0 0 26px" }}>
                <div style={{ ...note, marginBottom: 6 }}>
                  {accounts && accounts.length
                    ? "Post this project's videos to:"
                    : "No accounts available. Videos will wait at Video Approved."}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
                  {(accounts ?? []).map((a) => (
                    <label key={a.id} style={{ ...mono, fontSize: 11, color: "var(--dim)",
                                               display: "flex", alignItems: "center", gap: 6,
                                               cursor: "pointer" }}>
                      <input
                        data-testid={`auto-pilot-account-${p.id}-${a.id}`}
                        type="checkbox"
                        checked={chosen.includes(a.id)}
                        onChange={() => toggleAccount(p.id, a.id)}
                      />
                      {accountName(a)}
                    </label>
                  ))}
                  {stale.map((id) => (
                    <label key={id} style={{ ...mono, fontSize: 11, color: "var(--amber)",
                                             display: "flex", alignItems: "center", gap: 6,
                                             cursor: "pointer" }}>
                      <input
                        data-testid={`auto-pilot-stale-${p.id}-${id}`}
                        type="checkbox"
                        checked
                        onChange={() => toggleAccount(p.id, id)}
                      />
                      {id} (not available, so nothing is posted to it; untick to remove)
                    </label>
                  ))}
                </div>
                {accounts !== null && accounts.length > 0 && chosen.length === stale.length && (
                  <div data-testid={`auto-pilot-no-accounts-${p.id}`}
                       style={{ ...note, color: "var(--amber)", marginTop: 6 }}>
                    No usable account chosen: videos are approved automatically, then wait at
                    Video Approved for you to publish.
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {accounts !== null && accounts.length > 0 && (
        <>
          <SectionLabel label="Accounts" />
          {accounts.map((a) => (
            <div key={a.id} style={row}>
              <div style={{ flex: 1 }}>
                <div style={label}>{accountName(a)}</div>
                <div style={{ ...note, marginTop: 3 }}>
                  Auto post how many videos per day. 0 means Auto Pilot never posts here.
                </div>
              </div>
              <input
                data-testid={`auto-pilot-limit-${a.id}`}
                type="number"
                min={0}
                max={MAX_AUTO_PILOT_DAILY}
                value={draft.account_limits[a.id] ?? saved.default_daily_limit}
                onChange={(e) => setLimit(a.id, e.target.value)}
                style={{ ...inputStyle, width: 80 }}
              />
            </div>
          ))}
        </>
      )}

      {error && (
        <div data-testid="auto-pilot-error" style={{ ...mono, fontSize: 11, color: "var(--red)", marginTop: 10 }}>
          {error}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
        <button
          data-testid="save-auto-pilot"
          disabled={!dirty || busy}
          onClick={requestSave}
          style={{ ...button, color: "var(--blue)", opacity: !dirty || busy ? 0.5 : 1,
                   cursor: !dirty || busy ? "default" : "pointer" }}
        >
          {busy ? "SAVING…" : "SAVE"}
        </button>
        <span data-testid="auto-pilot-status" style={note}>
          {dirty ? "Unsaved changes" : message ?? "No changes"}
        </span>
      </div>

      <Dialog open={confirming} onOpenChange={(v) => !v && setConfirming(false)}>
        <DialogContent
          data-testid="auto-pilot-confirm"
          className="border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff]"
          style={{ maxWidth: 520 }}
        >
          <DialogHeader>
            <DialogTitle style={{ fontSize: 15, fontWeight: 600 }}>
              {saved.enabled ? "Add these projects to Auto Pilot?" : "Turn on Auto Pilot?"}
            </DialogTitle>
          </DialogHeader>
          <Disclaimer testId="auto-pilot-confirm-disclaimer" />
          <p data-testid="auto-pilot-confirm-count"
             style={{ fontSize: 13, lineHeight: 1.6, color: "var(--dim)", margin: 0 }}>
            {approvedNow > 0
              ? `${approvedNow} video${approvedNow === 1 ? " is" : "s are"} waiting at a checkpoint `
                + "in the selected projects and will be approved as soon as you confirm."
              : "Nothing is waiting at a checkpoint in the selected projects right now."}
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
            <button data-testid="auto-pilot-confirm-cancel" onClick={() => setConfirming(false)}
                    style={{ ...button, color: "var(--dim)" }}>
              Cancel
            </button>
            <button data-testid="auto-pilot-confirm-ok" disabled={busy} onClick={save}
                    style={{ ...button, border: "1px solid var(--amber)", color: "var(--amber)" }}>
              {saved.enabled ? "Add to Auto Pilot" : "Turn on Auto Pilot"}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
