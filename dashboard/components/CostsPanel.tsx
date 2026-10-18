"use client";

// Settings → Costs (TMDEV-107): the model prices every table-priced call is
// costed with, where each came from, and the controls to sync or correct them.
//
// Self-contained like AgentsPanel — it reads and writes its own routes and
// sits outside the settings form's Save/dirty machinery. Rates are shown and
// typed per million tokens (what every pricing page quotes) and stored per
// token.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import type { ModelPrice, PriceTable } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDateTime } from "@/lib/datetime";
import { COST_DISCLAIMER, perMillion, serviceLabel } from "@/lib/costs";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

async function errorDetail(r: Response): Promise<string> {
  const body = await r.json().catch(() => ({}));
  return (body && body.error) || `HTTP ${r.status}`;
}

const SOURCE_LABELS: Record<string, string> = {
  manual: "manual",
  openrouter: "OpenRouter",
  litellm: "LiteLLM",
  "built-in": "built-in",
};

// Offered first when a model has no rates yet — what nearly every call bills.
const COMMON_KINDS = ["input", "output", "cache_read", "output_image"];

const mono = { fontFamily: "var(--mono)" } as const;
const note = { ...mono, fontSize: 10, color: "var(--mute)", letterSpacing: "0.02em",
               marginBottom: 6 } as const;
const cell: CSSProperties = { padding: "6px 10px", verticalAlign: "top", textAlign: "left" };
const button: CSSProperties = {
  ...mono, fontSize: 10, color: "var(--blue)", background: "var(--panel)",
  border: "1px solid var(--border)", padding: "4px 10px", cursor: "pointer",
};

function rateSummary(rates: Record<string, number>): string {
  const kinds = Object.keys(rates);
  if (!kinds.length) return "—";
  return kinds.map((k) => `${k} $${+perMillion(rates[k]).toPrecision(4)}`).join(" · ");
}

function RateEditor({
  target, unitKinds, inputStyle, busy, onSave, onCancel,
}: {
  target: { service: string; model: string; rates: Record<string, number> };
  unitKinds: string[];
  inputStyle: CSSProperties;
  busy: boolean;
  onSave: (rates: Record<string, number>) => void;
  onCancel: () => void;
}) {
  const initialKinds = Object.keys(target.rates).length ? Object.keys(target.rates) : COMMON_KINDS;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(initialKinds.map((k) => [
      k, target.rates[k] !== undefined ? String(+perMillion(target.rates[k]).toPrecision(6)) : "",
    ])));
  const spare = unitKinds.filter((k) => !(k in values));

  function save() {
    const rates: Record<string, number> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v.trim() !== "") rates[k] = Number(v) / 1_000_000;
    }
    onSave(rates);
  }

  return (
    <div data-testid="price-editor" style={{ border: "1px solid var(--border)", padding: 12,
                                             margin: "8px 0", background: "var(--panel)" }}>
      <div style={{ ...note, marginBottom: 10 }}>
        {serviceLabel(target.service)} {target.model} — USD per million tokens. Leave a field blank
        to drop it. A manual rate is never changed by a sync.
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {Object.keys(values).map((k) => (
          <label key={k} style={{ ...mono, fontSize: 10, color: "var(--dim)" }}>
            {k}
            <input
              data-testid={`price-input-${k}`}
              value={values[k]}
              inputMode="decimal"
              onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
              style={{ ...inputStyle, width: 110, display: "block", marginTop: 4 }}
            />
          </label>
        ))}
        {spare.length > 0 && (
          <select
            data-testid="price-add-kind"
            value=""
            onChange={(e) => e.target.value && setValues((v) => ({ ...v, [e.target.value]: "" }))}
            style={{ ...inputStyle, width: 150, alignSelf: "flex-end" }}
          >
            <option value="">+ another rate…</option>
            {spare.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button type="button" data-testid="price-save" disabled={busy} style={button} onClick={save}>
          {busy ? "Saving…" : "Save manual rate"}
        </button>
        <button type="button" data-testid="price-cancel" style={{ ...button, color: "var(--dim)" }}
                onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export function CostsPanel({ inputStyle }: { inputStyle: CSSProperties }) {
  const { timeZone } = useTimeZone();
  const [table, setTable] = useState<PriceTable | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncNote, setSyncNote] = useState("");
  const [editing, setEditing] = useState<{ service: string; model: string;
                                           rates: Record<string, number> } | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const r = await apiFetch("/prices");
      if (!r.ok) { setLoadError(await errorDetail(r)); return; }
      setTable(await r.json());
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "unreachable");
    }
  }

  useEffect(() => { load(); }, []);

  async function syncNow() {
    setSyncing(true);
    setSyncNote("");
    try {
      const r = await apiFetch("/prices/sync", { method: "POST" });
      const body = await r.json().catch(() => ({}));
      setSyncNote(body.ok
        ? `Synced — ${body.updated?.length ?? 0} updated${body.rejected?.length
            ? `, ${body.rejected.length} rejected as implausible` : ""}.`
        : `Sync failed; existing prices kept. ${body.error ?? ""}`);
      await load();
    } catch (e) {
      setSyncNote(`Sync failed: ${e instanceof Error ? e.message : "unreachable"}`);
    } finally {
      setSyncing(false);
    }
  }

  async function saveManual(rates: Record<string, number>) {
    if (!editing) return;
    setBusy(true);
    setActionError("");
    try {
      const r = await apiFetch("/prices/override", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service: editing.service, model: editing.model, rates }),
      });
      if (!r.ok) { setActionError(await errorDetail(r)); return; }
      setEditing(null);
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "unreachable");
    } finally {
      setBusy(false);
    }
  }

  async function reset(m: ModelPrice) {
    setActionError("");
    const q = `service=${encodeURIComponent(m.service)}&model=${encodeURIComponent(m.model)}`;
    const r = await apiFetch(`/prices/override?${q}`, { method: "DELETE" }).catch(() => null);
    if (!r || !r.ok) { setActionError(r ? await errorDetail(r) : "unreachable"); return; }
    await load();
  }

  return (
    <div data-testid="section-costs">
      <SectionLabel label="Model prices" />
      <div style={note}>
        Gemini, OpenAI and Codex calls are priced from this table. Claude Code and OpenCode report
        their own list-price cost per session, and ElevenLabs is recorded in plan credits, so
        neither appears here.
      </div>
      <div style={note}>
        Rates come from OpenRouter&apos;s model list, or LiteLLM&apos;s price file for a model
        OpenRouter does not list, and sync weekly. A manual rate always wins and is never
        synced over.
      </div>
      <div style={{ ...note, marginBottom: 12 }}>{COST_DISCLAIMER}</div>

      {loadError && (
        <div data-testid="costs-error" style={{ ...mono, fontSize: 11, color: "var(--amber)" }}>
          Could not load prices: {loadError}
        </div>
      )}

      {table && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
                        marginBottom: 12 }}>
            <span data-testid="costs-last-sync" style={{ ...mono, fontSize: 11, color: "var(--dim)" }}>
              Last synced:{" "}
              {table.last_sync_ok_at ? formatDateTime(table.last_sync_ok_at, timeZone) : "never"}
            </span>
            <button type="button" data-testid="costs-sync-now" onClick={syncNow} disabled={syncing}
                    style={{ ...button, opacity: syncing ? 0.5 : 1 }}>
              {syncing ? "Syncing…" : "Sync now"}
            </button>
            {syncNote && <span data-testid="costs-sync-note" style={note}>{syncNote}</span>}
          </div>
          {table.last_sync_error && (
            <div data-testid="costs-sync-error" style={{ ...note, color: "var(--amber)" }}>
              The last sync failed, so the prices below are the last ones that synced:{" "}
              {table.last_sync_error}
            </div>
          )}

          {table.unpriced.length > 0 && (
            <div data-testid="costs-unpriced" style={{ border: "1px solid var(--amber)",
                                                        padding: 10, margin: "10px 0" }}>
              <div style={{ ...mono, fontSize: 11, color: "var(--amber)", marginBottom: 6 }}>
                Calls with no price — not in any total until a rate is added:
              </div>
              {table.unpriced.map((u) => (
                <div key={`${u.service}/${u.model}`}
                     style={{ display: "flex", alignItems: "center", gap: 10, padding: "3px 0" }}>
                  <span style={{ ...mono, fontSize: 11 }}>
                    {serviceLabel(u.service)} {u.model || "(unknown model)"} — {u.calls} call
                    {u.calls === 1 ? "" : "s"}
                  </span>
                  <button type="button" data-testid={`costs-add-${u.model}`} style={button}
                          onClick={() => setEditing({ service: u.service, model: u.model, rates: {} })}>
                    Add price
                  </button>
                </div>
              ))}
            </div>
          )}

          {actionError && (
            <div data-testid="costs-action-error" style={{ ...note, color: "var(--amber)" }}>
              {actionError}
            </div>
          )}
          {editing && (
            <RateEditor target={editing} unitKinds={table.unit_kinds} inputStyle={inputStyle}
                        busy={busy} onSave={saveManual} onCancel={() => setEditing(null)} />
          )}

          <div style={{ overflowX: "auto" }}>
            <table style={{ ...mono, fontSize: 11, borderCollapse: "collapse", minWidth: 640 }}>
              <thead>
                <tr style={{ color: "var(--mute)", fontSize: 9, textTransform: "uppercase",
                             letterSpacing: "0.12em" }}>
                  {["Model", "Source", "Rates ($ / M tokens)", "Since", ""].map((h) => (
                    <th key={h} style={cell}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.models.map((m) => (
                  <tr key={`${m.service}/${m.model}`} data-testid={`price-row-${m.model}`}
                      style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={cell}>
                      <div>{m.model}</div>
                      <div style={{ color: "var(--mute)", fontSize: 10 }}>{serviceLabel(m.service)}</div>
                    </td>
                    <td style={cell} data-testid={`price-source-${m.model}`}>
                      {m.source ? SOURCE_LABELS[m.source] ?? m.source : (
                        <span style={{ color: "var(--amber)" }}>no price</span>)}
                      {m.tiered && <div style={{ color: "var(--mute)", fontSize: 10 }}>tiered — estimated</div>}
                    </td>
                    <td style={{ ...cell, maxWidth: 360 }}>{rateSummary(m.rates)}</td>
                    <td style={cell}>
                      {m.effective_from ? formatDateTime(m.effective_from, timeZone) : "—"}
                    </td>
                    <td style={{ ...cell, whiteSpace: "nowrap" }}>
                      <button type="button" style={button} data-testid={`price-edit-${m.model}`}
                              onClick={() => setEditing({ service: m.service, model: m.model,
                                                          rates: m.rates })}>
                        {m.source === "manual" ? "Edit" : "Override"}
                      </button>
                      {m.source === "manual" && (
                        <button type="button" style={{ ...button, marginLeft: 6, color: "var(--dim)" }}
                                data-testid={`price-reset-${m.model}`} onClick={() => reset(m)}>
                          Reset
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
