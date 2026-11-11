"use client";

// Both components are at module scope on purpose: declared inside a page they
// get a new identity on every render and React remounts them, which once ate
// the first click on a button beside a just-blurred field (TMDEV-93).

import type { SaveState } from "@/lib/saveStatus";
import { useSavesSummary } from "@/lib/saveStatus";

const mono: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 10.5,
  letterSpacing: "0.04em",
  lineHeight: 1.5,
};

/** The status beside one field: "Saving…", "✓ Saved" or "Not saved: <reason>".
 *  Renders an empty live region when there is nothing to say, so a screen
 *  reader still hears the outcome. `id` is for a field's aria-describedby;
 *  pass one only where it is unique on the page. */
export function SaveStatus({ status, testId, id }: { status?: SaveState; testId?: string; id?: string }) {
  let text = "";
  let color = "var(--mute)";
  if (status?.state === "saving") text = status.label ?? "Saving…";
  else if (status?.state === "saved") {
    text = "✓ Saved";
    color = "var(--green)";
  } else if (status?.state === "error") {
    text = `Not saved: ${status.message}`;
    color = "var(--red)";
  }
  return (
    <span
      id={id}
      data-testid={testId}
      data-state={status?.state ?? "idle"}
      role="status"
      aria-live="polite"
      style={{ ...mono, color, maxWidth: 320 }}
    >
      {text}
    </span>
  );
}

/** The page-wide line: all saved, saving, or how many changes were refused. */
export function SavesSummaryLine() {
  const { saving, errors } = useSavesSummary();
  let text = "All changes saved";
  let dot = "var(--green)";
  if (saving) {
    text = "Saving…";
    dot = "var(--amber)";
  } else if (errors) {
    text = `${errors} change${errors === 1 ? "" : "s"} not saved`;
    dot = "var(--red)";
  }
  return (
    // Not a live region: each field's own status is, and a second one here
    // would announce every save twice.
    <span
      data-testid="saves-summary"
      style={{
        ...mono, fontSize: 11, color: "var(--dim)", display: "inline-flex", alignItems: "center", gap: 8,
        border: "1px solid var(--border)", padding: "4px 10px", whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden="true" style={{ color: dot }}>●</span>
      {text}
    </span>
  );
}
