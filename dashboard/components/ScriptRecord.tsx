"use client";

import { useState } from "react";
import type { Video } from "@/lib/types";
import {
  formulaLabel,
  hasScriptRecord,
  hookTypeLabel,
  type ScriptFormulaNames,
} from "@/lib/scriptFormulas";

const caption: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.14em",
  color: "var(--dim)",
};

/** What the agent recorded with a video's script: the formula it follows, the
 *  three openings it drafted (the one in use marked) and the advisory checks'
 *  findings. Renders nothing for a script with no record, which is every
 *  script written before scripts recorded one.
 *
 *  names: the formula and hook type labels, or null while they load.
 *  onSwitchOpening: given at Script Ready only. Each opening not in use then
 *  gets a "Use this opening" button; it resolves to an error message, or ""
 *  when the video went back to its agent to be rewritten from that opening. */
export function ScriptRecord({ video, names, onSwitchOpening }: {
  video: Video;
  names: ScriptFormulaNames | null;
  onSwitchOpening?: (index: number) => Promise<string>;
}) {
  const [switching, setSwitching] = useState<number | null>(null);
  const [switchError, setSwitchError] = useState("");

  if (!hasScriptRecord(video)) return null;
  const formulaId = video.formula_id ?? "";
  const hooks = video.hook_alternatives ?? [];
  const warnings = video.script_warnings ?? [];

  const chooseOpening = async (index: number) => {
    if (!onSwitchOpening || switching !== null) return;
    if (!window.confirm("Use this opening? The script is discarded and the agent rewrites it from this opening, in the same formula.")) return;
    setSwitching(index);
    setSwitchError("");
    setSwitchError(await onSwitchOpening(index));
    setSwitching(null);
  };

  return (
    <div
      data-testid="script-record"
      style={{ border: "1px solid var(--border)", padding: "14px 16px", marginBottom: 18 }}
    >
      {formulaId !== "" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 28px", marginBottom: hooks.length ? 14 : 0 }}>
          <div>
            <div style={caption}>Formula</div>
            <div data-testid="script-formula" style={{ fontSize: 13, color: "var(--ink)", marginTop: 3 }}>
              {formulaLabel(formulaId, names)}
            </div>
          </div>
          {(video.hook_type ?? "") !== "" && (
            <div>
              <div style={caption}>Opening</div>
              <div data-testid="script-hook-type" style={{ fontSize: 13, color: "var(--ink)", marginTop: 3 }}>
                {hookTypeLabel(video.hook_type ?? "", names)}
              </div>
            </div>
          )}
        </div>
      )}

      {hooks.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ ...caption, marginBottom: 6 }}>Openings considered</div>
          {hooks.map((hook, i) => (
            <div
              key={i}
              data-testid={`script-hook-${i}`}
              data-kept={hook.kept ? "true" : "false"}
              style={{ padding: "6px 0", borderTop: i ? "1px solid var(--border)" : "none" }}
            >
              <div style={{ ...caption, color: hook.kept ? "var(--amber)" : "var(--dim)" }}>
                {hookTypeLabel(hook.type, names)}{hook.kept ? " · used" : ""}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.55, marginTop: 3,
                            color: hook.kept ? "var(--ink)" : "var(--ink-2)" }}>
                {hook.text}
              </div>
              {hook.note ? (
                <div style={{ fontSize: 11, lineHeight: 1.5, marginTop: 2, color: "var(--dim)", fontStyle: "italic" }}>
                  Not used: {hook.note}
                </div>
              ) : null}
              {onSwitchOpening && !hook.kept && (
                <button
                  type="button"
                  data-testid={`use-opening-${i}`}
                  disabled={switching !== null}
                  onClick={() => chooseOpening(i)}
                  style={{
                    ...caption, marginTop: 6, padding: "4px 10px", background: "transparent",
                    border: "1px solid var(--border)", color: "var(--ink-2)",
                    cursor: switching !== null ? "default" : "pointer",
                  }}
                >
                  {switching === i ? "Switching…" : "Use this opening"}
                </button>
              )}
            </div>
          ))}
          {switchError && (
            <p data-testid="switch-opening-error" className="font-mono text-[11px] text-amber-400" style={{ marginTop: 6 }}>
              {switchError}
            </p>
          )}
        </div>
      )}

      {warnings.length > 0 ? (
        <div data-testid="script-warnings" role="note" style={{ border: "1px solid var(--amber)", padding: 12 }}>
          <div style={{ ...caption, color: "var(--amber)", fontWeight: 700, marginBottom: 6 }}>
            Script warnings
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {warnings.map((w) => (
              <li
                key={w.id}
                data-testid={`script-warning-${w.id}`}
                style={{ fontSize: 12, lineHeight: 1.6, color: "var(--ink-2)" }}
              >
                {w.message}
              </li>
            ))}
          </ul>
          <div style={{ fontSize: 11, lineHeight: 1.5, marginTop: 8, color: "var(--dim)" }}>
            Automatic checks on the script&apos;s words. They are advice and do not block approval.
          </div>
        </div>
      ) : (
        <div data-testid="script-no-warnings" style={{ fontSize: 12, color: "var(--dim)" }}>
          The script checks raised no warnings.
        </div>
      )}
    </div>
  );
}
