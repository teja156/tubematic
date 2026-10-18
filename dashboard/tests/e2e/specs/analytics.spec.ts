import { test, expect } from "@playwright/test";

// The Analytics page's two tabs against the real API. The browser runs in
// Asia/Tokyo and the test API in America/New_York (playwright.config.ts), so
// "today" only matches New York's day if the preset was resolved in the host
// zone rather than the browser's own.

function dayIn(timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** 120 publications across two accounts, plus months — more rows than one
 *  page. The test stack cannot publish (no postforme), so /analytics is
 *  answered here; everything else is the real API. */
function manyPublications() {
  const publications = Array.from({ length: 120 }, (_, i) => ({
    id: `pub${i}`, video_id: `vid_${i}`,
    platform: i % 2 ? "youtube" : "instagram",
    social_account_id: i % 2 ? "spc_yt" : "spc_ig",
    status: "PUBLISHED", post_url: "", error: "",
    published_at: "2026-09-01T00:00:00Z", created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z", title: `Video ${i}`,
    views: 1000 - i, likes: 1, comments: 0, shares: 0, fetched_at: "2026-09-02T00:00:00Z",
  }));
  return {
    totals: { views: 1, likes: 1, comments: 0, shares: 0, videos: 120, publications: 120 },
    by_platform: { youtube: { views: 1 }, instagram: { views: 1 } },
    publications,
    by_month: [{ month: "2026-08", views: 500 }, { month: "2026-09", views: 800 }],
    timezone: "America/New_York",
  };
}

async function withManyPublications(page: import("@playwright/test").Page) {
  await page.route((url) => url.pathname === "/api/proxy/analytics", (route) =>
    route.fulfill({ json: manyPublications() }));
}

test.describe("Analytics", () => {
  test("graphs sit right of the table, which scrolls in its own box and loads as it goes",
    async ({ page }) => {
      await page.setViewportSize({ width: 1400, height: 900 });
      await withManyPublications(page);
      await page.goto("/analytics");
      const box = page.getByTestId("analytics-scroll");
      const rows = page.locator('[data-testid^="analytics-row-"]');
      await expect(rows).toHaveCount(50, { timeout: 15_000 });

      const table = (await box.boundingBox())!;
      for (const chart of ["chart-platform", "chart-account", "chart-month"]) {
        const b = (await page.getByTestId(chart).boundingBox())!;
        expect(b.x).toBeGreaterThanOrEqual(table.x + table.width);
      }

      // A wheel over the table scrolls the table, not the page. Measured from
      // after the hover, which may itself scroll the page to reach the box.
      await box.hover();
      const pageY = await page.evaluate(() => window.scrollY);
      await page.mouse.wheel(0, 300);
      await expect.poll(() => box.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
      expect(await page.evaluate(() => window.scrollY)).toBe(pageY);

      await box.evaluate((el) => { el.scrollTop = el.scrollHeight; });
      await expect(rows).toHaveCount(100);
      await box.evaluate((el) => { el.scrollTop = el.scrollHeight; });
      await expect(rows).toHaveCount(120);
      await expect(page.getByTestId("analytics-more")).toHaveCount(0);
    });

  test("clicking a platform bar filters the page by it", async ({ page }) => {
    await withManyPublications(page);
    await page.goto("/analytics");
    const bar = page.getByTestId("bar-platform-youtube");
    await expect(bar).toBeVisible({ timeout: 15_000 });
    const asked = page.waitForRequest((r) => r.url().includes("/api/proxy/analytics?platform=youtube"));
    await bar.click();
    await asked;
    await expect(page.getByTestId("filter-platform")).toHaveValue("youtube");
  });

  test("on a narrow screen the graphs stack between the filters and the table",
    async ({ page }) => {
      await page.setViewportSize({ width: 1000, height: 900 });
      await withManyPublications(page);
      await page.goto("/analytics");
      await expect(page.getByTestId("chart-month")).toBeVisible({ timeout: 15_000 });
      const filters = (await page.getByTestId("sort-by").boundingBox())!;
      const charts = (await page.getByTestId("chart-platform").boundingBox())!;
      const table = (await page.getByTestId("analytics-scroll").boundingBox())!;
      expect(charts.y).toBeGreaterThan(filters.y);
      expect(table.y).toBeGreaterThan(charts.y);
    });

  test("opens on Videos, with the sort menu beside the filters", async ({ page }) => {
    await page.goto("/analytics");
    await expect(page.getByTestId("sort-by")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("filter-account")).toBeVisible();
    await expect(page.getByTestId("spend-range")).toHaveCount(0);
  });

  test("Spend tab shows this month, then today, as host-zone days", async ({ page }) => {
    await page.goto("/analytics");
    await page.getByTestId("tab-spend").click();
    await expect(page.getByTestId("spend-total")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("spend-notes")).toContainText("Days are in America/New_York");

    const today = dayIn("America/New_York");
    await expect(page.getByText(`${today.slice(0, 8)}01 → ${today}`)).toBeVisible();

    await page.getByTestId("spend-range").selectOption("today");
    await expect(page.getByText(`${today} → ${today}`)).toBeVisible();
    await expect(page.getByTestId("spend-total")).toBeVisible();
  });

  test("a backwards custom range is flagged, not sent", async ({ page }) => {
    await page.goto("/analytics");
    await page.getByTestId("tab-spend").click();
    await expect(page.getByTestId("spend-total")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("spend-range").selectOption("custom");
    await page.getByTestId("spend-from").fill("2099-01-01");
    await expect(page.getByTestId("spend-range-problem")).toContainText("after the end");
    await expect(page.getByTestId("spend-total")).toHaveCount(0);
  });
});
