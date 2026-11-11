import { test, expect } from "@playwright/test";

// The Analytics page's tabs against the real API. The browser runs in
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
    // YouTube reports all three watch figures; Instagram seconds only here.
    avg_watch_secs: 20 + (i % 30), watched_pct: i % 2 ? 40.5 + (i % 9) : null,
    stayed_pct: i % 2 ? 61.2 : null, reach: i % 2 ? null : 400, saves: i % 2 ? null : 3,
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

function watchGroup(key: string, label: string, videos: number, n = videos) {
  return {
    key, label, videos,
    avg_watch_secs: { median: 31.5, n }, watched_pct: { median: 41.5, n },
    stayed_pct: { median: 60.2, n },
  };
}

/** One account's watch figures with a readable group, a small one and a long
 *  label. Answered here for the same reason /analytics is. */
async function withWatchTime(page: import("@playwright/test").Page) {
  await page.route((url) => url.pathname === "/api/proxy/analytics/watch-time", (route) =>
    route.fulfill({ json: {
      accounts: [{ id: "spc_yt", platform: "youtube", videos: 60 },
                 { id: "spc_ig", platform: "instagram", videos: 60 }],
      social_account_id: "spc_yt", platform: "youtube", videos: 60, min_group: 20,
      dimensions: [
        { id: "visual_style", label: "Visual style", groups: [
          watchGroup("system_flow", "System Flow", 34),
          watchGroup("long", "A visual style whose label is much longer than the others", 20, 7),
          watchGroup("whiteboard", "Whiteboard", 6),
        ] },
        { id: "script_profile", label: "Script profile", groups: [watchGroup("", "No profile", 60)] },
        { id: "domain", label: "Domain", groups: [watchGroup("git", "Git", 60)] },
        { id: "script_length", label: "Script length",
          groups: [watchGroup("200", "200 to 249 words", 60)] },
      ],
    } }));
}

/** True when the page itself scrolls sideways: something is wider than the window. */
async function pageScrollsSideways(page: import("@playwright/test").Page) {
  return page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth);
}

test.describe("Analytics", () => {
  test("the Watch time tab is answered by the real API, which has nothing published",
    async ({ page }) => {
      await page.goto("/analytics");
      await page.getByTestId("tab-watch").click();
      await expect(page.getByTestId("watch-time-empty")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("watch-time-error")).toHaveCount(0);
    });

  for (const width of [1680, 1000]) {
    test(`at ${width}px the watch columns and the Watch time tab fit the page`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await withManyPublications(page);
      await withWatchTime(page);
      await page.goto("/analytics");

      // The list: ten columns. Where they do not fit, the table's own box
      // scrolls and the page does not.
      await expect(page.getByTestId("watched-pub1")).toHaveText("21 s", { timeout: 15_000 });
      await expect(page.getByTestId("watched-pct-pub1")).toHaveText("41.5%");
      await expect(page.getByTestId("watched-pct-pub0")).toHaveText("—");
      expect(await pageScrollsSideways(page)).toBe(false);
      if (width === 1680) {
        const box = page.getByTestId("analytics-scroll");
        expect(await box.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
      }

      await page.getByTestId("tab-watch").click();
      await expect(page.getByTestId("watch-group-system_flow")).toBeVisible();
      await expect(page.getByTestId("watch-small-whiteboard")).toHaveText("TOO FEW");
      await expect(page.getByTestId("watch-small-system_flow")).toHaveCount(0);
      // A figure only some of the group's videos report says how many.
      await expect(page.getByTestId("watch-watched_pct-long")).toContainText("(7 of 20, too few)");
      expect(await pageScrollsSideways(page)).toBe(false);

      await page.getByTestId("watch-group-by").selectOption("script_length");
      await expect(page.getByTestId("watch-group-200")).toContainText("200 to 249 words");
    });
  }


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
