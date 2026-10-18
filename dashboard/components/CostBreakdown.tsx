"use client";

// A video's cost, per provider and per model, from the usage ledger (TMDEV-107).
//
// Every call belongs to at most one video and is shown as it was charged —
// agent sessions included, since the poller runs one session per video and
// stage (TMDEV-129). The rows behind the agent total, one per session labelled
// by the stage the video was at, are one click away. Sessions recorded before
// that change could cover a batch of videos; for those this video is shown its
// even share — "≈ $0.05 (of $0.15 · 1 session)" — and the share is what the
// total adds, since adding whole sessions would count one session once per
// video in its batch.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import type { CostLine, VideoCosts } from "@/lib/types";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDateTime } from "@/lib/datetime";
import {
  COST_DISCLAIMER, formatCredits, formatUsd, operationLabel, serviceLabel, stageLabel,
} from "@/lib/costs";

const heading: CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.14em",
  color: "var(--dim)",
  marginBottom: 10,
};

const row: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  gap: 12,
  padding: "6px 0",
  borderBottom: "1px solid var(--border)",
};

const value: CSSProperties = { fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink)",
                               textAlign: "right", whiteSpace: "nowrap" };
const detail: CSSProperties = { fontFamily: "var(--mono)", fontSize: 10, color: "var(--mute)" };
const toggle: CSSProperties = {
  fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase",
  padding: "2px 8px", border: "1px solid var(--border)", background: "var(--panel)",
  color: "var(--ink)", cursor: "pointer", marginTop: 4,
};

/** A /costs body, or null for anything else (an error page, a proxy failure). */
function asVideoCosts(data: unknown): VideoCosts | null {
  const d = data as VideoCosts | null;
  return d && typeof d === "object" && typeof d.has_usage === "boolean" && Array.isArray(d.lines)
    ? d : null;
}

function lineValue(line: CostLine): string {
  if (line.service === "elevenlabs") return `– · ${formatCredits(line.credits)}`;
  if (line.cost_usd === null) return "unpriced";
  const approx = line.estimated ? "≈ " : "";
  return `${approx}${formatUsd(line.cost_usd)}`;
}

export function CostBreakdown({ videoId, refreshKey }: { videoId: string; refreshKey?: string }) {
  const { timeZone } = useTimeZone();
  const [costs, setCosts] = useState<VideoCosts | null>(null);
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setExpanded(false);
  }, [videoId]);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    fetch(`/api/proxy/videos/${videoId}/costs`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: unknown) => {
        if (cancelled) return;
        const parsed = asVideoCosts(data);
        setCosts(parsed);
        setFailed(!parsed);
      })
      .catch(() => { if (!cancelled) { setCosts(null); setFailed(true); } });
    return () => { cancelled = true; };
  }, [videoId, refreshKey]);

  const agent = costs?.agent ?? null;
  const approxTotal = !!costs && (costs.lines.some((l) => l.estimated) ||
                                  !!agent && (agent.shared || agent.estimated));

  return (
    <div data-testid="cost-breakdown" style={{ padding: "14px 20px", borderTop: "1px solid var(--border)" }}>
      <div style={heading}>Cost</div>

      {failed && (
        <div data-testid="cost-error" style={{ fontSize: 12, color: "var(--dim)" }}>
          Could not load this video&apos;s costs.
        </div>
      )}

      {costs && !costs.has_usage && (
        <div data-testid="cost-none" style={{ fontSize: 12, color: "var(--dim)" }}>
          No usage recorded. Videos made before cost tracking have none.
        </div>
      )}

      {costs && costs.has_usage && (
        <>
          {costs.lines.map((line) => (
            <div key={`${line.service}/${line.model}/${line.operation}`} style={row}
                 data-testid={`cost-line-${line.service}-${line.operation}`}>
              <div>
                <div style={{ fontSize: 12, color: "var(--dim)" }}>{serviceLabel(line.service)}</div>
                <div style={detail}>
                  {line.model || "unknown model"} · {operationLabel(line.operation)}
                  {line.calls > 1 ? ` ×${line.calls}` : ""}
                </div>
              </div>
              <div style={value}>
                {lineValue(line)}
                {line.unpriced_calls > 0 && line.cost_usd !== null && (
                  <div style={detail}>+ {line.unpriced_calls} unpriced</div>
                )}
              </div>
            </div>
          ))}

          {agent && (
            <div style={{ ...row, flexDirection: "column", alignItems: "stretch" }}
                 data-testid="cost-agent">
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: "var(--dim)" }}>Agent</div>
                  {/* One unbreakable line per model: joined, the list wrapped after a
                      hyphen and the dangling "claude-" read as part of the value beside it.
                      A name too long to sit beside the value pushes the value below instead. */}
                  {agent.models.length ? agent.models.map((m) => (
                    <div key={m} style={{ ...detail, whiteSpace: "nowrap" }}
                         data-testid="cost-agent-model">{m}</div>
                  )) : <div style={detail}>unknown model</div>}
                </div>
                <div style={{ ...value, marginLeft: "auto" }} data-testid="cost-agent-value">
                  {agent.shared || agent.estimated ? "≈ " : ""}{formatUsd(agent.share_usd)}
                  {(agent.shared || agent.sessions.length > 1) && (
                    <div style={detail}>
                      {agent.shared ? `of ${formatUsd(agent.session_total_usd)} · ` : ""}
                      {agent.sessions.length} session{agent.sessions.length === 1 ? "" : "s"}
                    </div>
                  )}
                  <button type="button" style={toggle} data-testid="cost-agent-toggle"
                          aria-expanded={expanded} onClick={() => setExpanded((e) => !e)}>
                    {expanded ? "Hide sessions" : "Sessions ▸"}
                  </button>
                </div>
              </div>
              {expanded && (
                <div data-testid="cost-agent-sessions" style={{ marginTop: 8 }}>
                  {agent.sessions.map((s) => (
                    <div key={s.session_id} style={{ display: "flex", flexWrap: "wrap",
                                                     justifyContent: "space-between",
                                                     gap: 12, padding: "4px 0" }}>
                      <div>
                        <div style={{ fontSize: 11, color: "var(--ink)" }}>{stageLabel(s.stage)}</div>
                        <div style={detail}>{formatDateTime(s.created_at, timeZone)}</div>
                      </div>
                      <div style={{ ...value, fontSize: 11, marginLeft: "auto" }}>
                        {s.unpriced ? "unpriced" : s.batch_size > 1
                          ? `${formatUsd(s.total_usd)} ÷ ${s.batch_size} → ${formatUsd(s.share_usd)}`
                          : formatUsd(s.total_usd)}
                      </div>
                    </div>
                  ))}
                  {agent.shared && (
                    <div style={{ ...detail, marginTop: 4 }}>
                      ≈ marks an even split of a session shared by several videos, not a measurement.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                        paddingTop: 10, marginTop: 2 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink)" }}>Total</span>
            <span data-testid="cost-total"
                  style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 700, color: "var(--amber)" }}>
              {approxTotal ? "≈ " : ""}{formatUsd(costs.total_usd)}
            </span>
          </div>
          {(costs.unpriced_calls > 0 || costs.credits > 0) && (
            <div style={{ ...detail, textAlign: "right", marginTop: 2 }} data-testid="cost-total-extras">
              {[costs.unpriced_calls > 0 ? `+ ${costs.unpriced_calls} unpriced call${costs.unpriced_calls === 1 ? "" : "s"}` : "",
                costs.credits > 0 ? `+ ${formatCredits(costs.credits)}` : ""].filter(Boolean).join(" · ")}
            </div>
          )}
        </>
      )}

      <div data-testid="cost-disclaimer" style={{ ...detail, marginTop: 10, lineHeight: 1.5 }}>
        {COST_DISCLAIMER}
      </div>
    </div>
  );
}
