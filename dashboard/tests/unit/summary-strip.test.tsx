/**
 * Tests for SummaryStrip count aggregation logic.
 *
 * Critical regressions guarded here:
 *  1. Single-status tile (e.g. tile-01 = TOPIC_PROPOSED) shows the correct count
 *  2. Multi-status tile (tile-04 = "In Pipeline") correctly sums 7 pipeline statuses
 *     (SCRIPTING was removed — scripting is now folded into TOPIC_APPROVED;
 *     RENDER_QUEUED was added by TMDEV-32 — the render worker's durable queue signal)
 *  3. Missing stats keys are treated as 0 — no NaN or crash
 *  4. Adding a new pipeline status without updating tile-04's statuses array
 *     would leave the count wrong; this test documents the expected sum
 *  5. tile-06 (Failed) shows the FAILED count in its own tile
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SummaryStrip } from "@/components/SummaryStrip";
import type { Stats } from "@/lib/types";

describe("SummaryStrip", () => {
  it("shows correct count for a single-status tile (tile-01 = TOPIC_PROPOSED)", () => {
    const stats: Stats = { TOPIC_PROPOSED: 4 };
    render(<SummaryStrip stats={stats} />);
    expect(screen.getByTestId("tile-count-01").textContent).toBe("4");
  });

  it("shows 0 when a status is not present in stats", () => {
    render(<SummaryStrip stats={{}} />);
    expect(screen.getByTestId("tile-count-01").textContent).toBe("0");
    expect(screen.getByTestId("tile-count-05").textContent).toBe("0");
  });

  it("tile-04 (In Pipeline) sums all 8 pipeline statuses", () => {
    const stats: Stats = {
      TOPIC_APPROVED:  2,
      VOICING:         1,
      VOICE_READY:     2,
      RENDER_QUEUED:   3,
      RENDERING:       0,
      VIDEO_APPROVED:  1,
      SCHEDULED:       4,
      PUBLISHING:      0,
    };
    // 2 + 1 + 2 + 3 + 0 + 1 + 4 + 0 = 13
    render(<SummaryStrip stats={stats} />);
    expect(screen.getByTestId("tile-count-04").textContent).toBe("13");
  });

  it("tile-06 (Failed) shows the FAILED count", () => {
    const stats: Stats = { FAILED: 3 };
    render(<SummaryStrip stats={stats} />);
    expect(screen.getByTestId("tile-count-06").textContent).toBe("3");
  });

  it("tile-04 does not include TOPIC_PROPOSED, SCRIPT_READY, VIDEO_READY, or PUBLISHED", () => {
    const stats: Stats = {
      TOPIC_PROPOSED: 10,
      SCRIPT_READY:   10,
      VIDEO_READY:    10,
      PUBLISHED:      10,
      // nothing in the pipeline statuses
    };
    render(<SummaryStrip stats={stats} />);
    expect(screen.getByTestId("tile-count-04").textContent).toBe("0");
  });

  it("renders all six tiles regardless of stats content", () => {
    render(<SummaryStrip stats={{}} />);
    for (const id of ["01", "02", "03", "04", "05", "06"]) {
      expect(screen.getByTestId(`summary-tile-${id}`)).toBeTruthy();
    }
  });
});
