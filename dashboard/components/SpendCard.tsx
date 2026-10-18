"use client";

// Spend over a chosen range of days (TMDEV-107, TMDEV-130) — including what
// belongs to no video: research sessions, topic mining, the unscoped agent
// fallback, voice previews. The per-video breakdown lives in the video modal;
// this is the whole install. Lives on the Analytics page's Spend tab.

import { useEffect, useState } from "react";
import type { SpendSummary } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { COST_DISCLAIMER, formatCredits, formatUsd } from "@/lib/costs";

const mono = { fontFamily: "var(--mono)" } as const;

const tile = {
  border: "1px solid var(--border)", background: "var(--panel)", padding: "12px 18px",
  minWidth: 130,
} as const;

const tileLabel = {
  ...mono, fontSize: 9, color: "var(--mute)", letterSpacing: "0.16em",
  textTransform: "uppercase" as const,
};

function Tile({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div data-testid={`spend-${id}`} style={tile}>
      <div style={tileLabel}>{label}</div>
      <div style={{ ...mono, fontSize: 18, color: "var(--ink)", fontWeight: 700 }}>{children}</div>
    </div>
  );
}

// A preset is sent by name and resolved by the API in the host zone. The
// browser never works out which day "today" is: TimeZoneProvider falls back to
// UTC while (and if) the host zone is unknown, so a range derived here could
// name the wrong days. Custom days are the user's own and are sent as picked.
type Choice = "today" | "week" | "month" | "custom";

interface DayRange {
  from: string;
  to: string;
}

const CHOICES: { key: Choice; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
  { key: "custom", label: "Custom range" },
];

const control = {
  ...mono, fontSize: 11, background: "var(--panel)", color: "var(--ink)",
  border: "1px solid var(--border)", padding: "6px 10px",
} as const;

function rangeProblem(range: DayRange): string {
  if (!range.from || !range.to) return "Pick both a start and an end date.";
  if (range.from > range.to) return "The start date is after the end date.";
  return "";
}

export function SpendCard() {
  const [choice, setChoice] = useState<Choice>("month");
  const [custom, setCustom] = useState<DayRange>({ from: "", to: "" });
  const [spend, setSpend] = useState<SpendSummary | null>(null);
  const [error, setError] = useState("");

  const problem = choice === "custom" ? rangeProblem(custom) : "";
  const query = choice === "custom" ? `from=${custom.from}&to=${custom.to}` : `preset=${choice}`;

  useEffect(() => {
    if (problem) return;
    // A slower answer for the previous range must not overwrite this one.
    let stale = false;
    setSpend(null);
    setError("");
    fetch(`/api/proxy/usage/summary?${query}`, { cache: "no-store" })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
        if (typeof body?.total_usd !== "number") throw new Error("unexpected response");
        if (!stale) setSpend(body as SpendSummary);
      })
      .catch((e: Error) => { if (!stale) setError(e.message); });
    return () => { stale = true; };
  }, [query, problem]);

  function choose(next: Choice) {
    // Custom starts from the days that were showing, so it is an edit, not a blank.
    if (next === "custom" && choice !== "custom") {
      setCustom({ from: spend?.from ?? "", to: spend?.to ?? "" });
    }
    setChoice(next);
  }

  const pool = spend?.elevenlabs_pool ?? null;
  const approx = spend?.estimated ? "≈ " : "";

  return (
    <>
      <SectionLabel
        label="Spend"
        count={!problem && spend?.from && spend?.to ? `${spend.from} → ${spend.to}` : undefined}
      />
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
                    marginBottom: 16 }}>
        <select
          aria-label="Range" data-testid="spend-range" style={control}
          value={choice} onChange={(e) => choose(e.target.value as Choice)}
        >
          {CHOICES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        {choice === "custom" && (
          <>
            <input
              type="date" aria-label="From" data-testid="spend-from" style={control}
              value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })}
            />
            <span style={{ ...mono, fontSize: 11, color: "var(--mute)" }}>to</span>
            <input
              type="date" aria-label="To" data-testid="spend-to" style={control}
              value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })}
            />
          </>
        )}
      </div>
      {problem && (
        <p data-testid="spend-range-problem" style={{ ...mono, fontSize: 11, color: "var(--amber)" }}>
          {problem}
        </p>
      )}
      {error && (
        <p data-testid="spend-error" style={{ ...mono, fontSize: 11, color: "var(--amber)" }}>
          Could not load spend: {error}
        </p>
      )}
      {spend && !problem && (
        <>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <Tile id="total" label="Total">
              <span style={{ color: "var(--amber)" }}>{approx}{formatUsd(spend.total_usd)}</span>
            </Tile>
            <Tile id="videos" label={`Videos (${spend.video_count})`}>{formatUsd(spend.videos)}</Tile>
            <Tile id="research" label="Research & mining">{formatUsd(spend.research)}</Tile>
            <Tile id="agent-other" label="Other agent runs">
              {formatUsd(spend.agent_other + spend.other)}
            </Tile>
            <Tile id="credits" label={pool ? "ElevenLabs (billing period)" : "ElevenLabs"}>
              <span style={{ fontSize: 14 }}>
                {pool ? `${pool.used.toLocaleString("en-US")} / ${pool.limit.toLocaleString("en-US")}`
                      : formatCredits(spend.voice_credits + spend.preview_credits)}
              </span>
            </Tile>
          </div>
          <p data-testid="spend-notes" style={{ ...mono, fontSize: 10, color: "var(--mute)",
                                                marginTop: 10, maxWidth: 640, lineHeight: 1.6 }}>
            {spend.unpriced_calls > 0 && (
              <span data-testid="spend-unpriced" style={{ color: "var(--amber)" }}>
                + {spend.unpriced_calls} unpriced call{spend.unpriced_calls === 1 ? "" : "s"} not
                in the total — add a price for the model on Settings → Costs.{" "}
              </span>
            )}
            {spend.timezone ? `Days are in ${spend.timezone}. ` : ""}
            {pool
              ? `ElevenLabs shows the plan credits used this billing period (${pool.tier ?? "plan"}) `
                + "— ElevenLabs' own counter, which does not follow the range above; "
                + `${formatCredits(spend.voice_credits)} of voice and `
                + `${formatCredits(spend.preview_credits)} of previews were recorded in this range. `
              : ""}
            {"Other agent runs are script-profile builds and runs that could not be tied to a video. "}
            {COST_DISCLAIMER}
          </p>
        </>
      )}
    </>
  );
}
