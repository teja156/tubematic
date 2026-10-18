/**
 * The Analytics page's graphs (TMDEV-113).
 *
 * The same hazard as the page itself: a view count postforme never reported is
 * not a zero. A graph that draws "not reported" as an empty bar is claiming
 * nobody watched, so unreported entries get no bar and read "—".
 *
 * A bar is also a filter: clicking one selects that platform or account, and
 * clicking the selected one clears it.
 */
import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AnalyticsCharts } from "@/components/AnalyticsCharts";

function pub(id: string, platform: string, account: string, views: number | null) {
  return { id, platform, social_account_id: account, views };
}

const PUBS = [
  pub("p1", "youtube", "spc_yt", 100),
  pub("p2", "youtube", "spc_yt", 20),
  pub("p3", "instagram", "spc_ig", 500),
  pub("p4", "tiktok", "spc_tt", null),
];

function renderCharts(over: Partial<Parameters<typeof AnalyticsCharts>[0]> = {}) {
  const props = {
    publications: PUBS,
    byMonth: [{ month: "2026-08", views: 300 }, { month: "2026-09", views: 320 }],
    timeZone: "America/New_York",
    names: { spc_ig: { username: "demo_channel", platform: "instagram" } },
    platform: "",
    account: "",
    onPlatform: vi.fn(),
    onAccount: vi.fn(),
    ...over,
  };
  render(<AnalyticsCharts {...props} />);
  return props;
}

function barOrder(chart: string) {
  return within(screen.getByTestId(chart)).getAllByRole("button")
    .map((b) => b.getAttribute("data-key"));
}

describe("AnalyticsCharts", () => {
  it("draws views per platform, highest first, with unreported last", () => {
    renderCharts();
    expect(barOrder("chart-platform")).toEqual(["instagram", "youtube", "tiktok"]);
    const yt = screen.getByTestId("bar-platform-youtube");
    expect(yt).toHaveTextContent("YouTube");
    expect(yt).toHaveTextContent("120");
  });

  it("never draws an unreported count as a zero bar", () => {
    renderCharts();
    const tt = screen.getByTestId("bar-platform-tiktok");
    expect(tt).toHaveTextContent("—");
    expect(tt).not.toHaveTextContent("0");
    expect(within(tt).queryByTestId("bar-fill")).toBeNull();
  });

  it("scales each bar against the largest", () => {
    renderCharts();
    const width = (key: string) =>
      (within(screen.getByTestId(`bar-platform-${key}`)).getByTestId("bar-fill") as HTMLElement)
        .style.width;
    expect(width("instagram")).toBe("100%");
    expect(width("youtube")).toBe("24%");
  });

  it("names accounts, falling back to the id with the platform", () => {
    renderCharts();
    expect(screen.getByTestId("bar-account-spc_ig")).toHaveTextContent("demo_channel (Instagram)");
    expect(screen.getByTestId("bar-account-spc_yt")).toHaveTextContent("spc_yt (YouTube)");
  });

  it("filters by the clicked bar, and clears when the selected one is clicked", () => {
    const props = renderCharts({ platform: "youtube" });
    fireEvent.click(screen.getByTestId("bar-platform-instagram"));
    expect(props.onPlatform).toHaveBeenCalledWith("instagram");
    fireEvent.click(screen.getByTestId("bar-platform-youtube"));
    expect(props.onPlatform).toHaveBeenCalledWith("");
    expect(screen.getByTestId("bar-platform-youtube")).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByTestId("bar-account-spc_ig"));
    expect(props.onAccount).toHaveBeenCalledWith("spc_ig");
  });

  it("gives every bar its exact value on hover", () => {
    renderCharts({ publications: [pub("p1", "youtube", "spc_yt", 1234567)] });
    expect(screen.getByTestId("bar-platform-youtube"))
      .toHaveAttribute("title", expect.stringContaining("1,234,567 views"));
  });

  it("draws a column per month, with the exact figure on hover", () => {
    renderCharts();
    const cols = within(screen.getByTestId("chart-month")).getAllByTestId(/^month-\d/);
    expect(cols.map((c) => c.getAttribute("data-testid"))).toEqual(["month-2026-08", "month-2026-09"]);
    expect(screen.getByTestId("month-2026-09"))
      .toHaveAttribute("title", "September 2026: 320 views gained");
    expect(screen.getByTestId("chart-month")).toHaveTextContent("America/New_York");
  });

  it("keeps a month where views fell as its real negative figure, with no bar height", () => {
    renderCharts({ byMonth: [{ month: "2026-08", views: 300 }, { month: "2026-09", views: -10 }] });
    const col = screen.getByTestId("month-2026-09");
    expect(col).toHaveAttribute("title", "September 2026: -10 views gained");
    expect((within(col).getByTestId("month-fill") as HTMLElement).style.height).toBe("0%");
  });

  it("says so when there is nothing to draw", () => {
    renderCharts({ publications: [], byMonth: [] });
    for (const chart of ["chart-platform", "chart-account", "chart-month"]) {
      expect(screen.getByTestId(chart)).toHaveTextContent("No views reported yet");
    }
  });
});
