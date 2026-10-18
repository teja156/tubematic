import { test, expect } from "@playwright/test";

test.describe("TopBar", () => {
  test("health indicator shows NOMINAL when API is running", async ({ page }) => {
    await page.goto("/");
    const healthStatus = page.getByTestId("health-status");
    await expect(healthStatus).toContainText("NOMINAL", { timeout: 15_000 });
  });

  test("Pipeline nav link routes to /", async ({ page }) => {
    await page.goto("/library");
    await page.getByRole("link", { name: "Pipeline" }).click();
    await expect(page).toHaveURL("/");
  });

  test("Library nav link routes to /library", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Library" }).click();
    await expect(page).toHaveURL("/library");
  });

  test("New Video nav link is visible and routes to /new-video", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("nav-new-video")).toBeVisible();
    await page.getByTestId("nav-new-video").click();
    await expect(page).toHaveURL(/\/new-video/);
  });

  test("Projects nav link is visible and routes to /projects", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("nav-projects")).toBeVisible();
    await page.getByTestId("nav-projects").click();
    await expect(page).toHaveURL(/\/projects/);
  });

  test("Profiles nav link is visible and routes to /script-profiles", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("nav-script-profiles")).toBeVisible();
    await page.getByTestId("nav-script-profiles").click();
    await expect(page).toHaveURL(/\/script-profiles/);
  });

  test("Settings nav link is visible and routes to /settings", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("nav-settings")).toBeVisible();
    await page.getByTestId("nav-settings").click();
    await expect(page).toHaveURL(/\/settings/);
  });

  // The value itself is not asserted: it comes from the VERSION file, so pinning
  // it here would fail on every release. The shape is what matters — that the
  // API served a real version and the bar rendered it rather than nothing. The
  // development branch's VERSION is the marker `develop` rather than a number.
  test("version badge shows the installed version", async ({ page }) => {
    await page.goto("/");
    const badge = page.getByTestId("version-badge");
    await expect(badge).toBeVisible({ timeout: 15_000 });
    await expect(badge).toHaveText(/^v(\d+\.\d+\.\d+|develop$)/);
  });

  // playwright.config.ts sets the browser's timezoneId to Asia/Tokyo — neither
  // UTC nor the test API's TZ (America/New_York, docker-compose.test.yml). If
  // this badge showed EST/EDT it would only prove the dashboard is using the
  // API-served zone, not the browser's own — that's the point of this test.
  test("timezone badge shows the API's host zone, not the browser's", async ({ page }) => {
    await page.goto("/");
    const badge = page.getByTestId("tz-badge");
    await expect(badge).toBeVisible();
    await expect(badge).not.toHaveText("UTC");
    await expect(badge).toHaveText(/EST|EDT/);
  });

  // The unwrapped single row needs about 1510px plus gutters. Below that it
  // used to squeeze its text onto several lines and make every page scroll
  // sideways; now the tabs drop to a second row (below 1640px). Measured after
  // the version badge has rendered, since it adds width.
  for (const width of [1024, 1280, 1600]) {
    test(`at ${width}px the bar wraps instead of scrolling the page`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await expect(page.getByTestId("version-badge")).toBeVisible();

      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      for (const id of ["nav-settings", "sign-out", "health-status"]) {
        const box = await page.getByTestId(id).boundingBox();
        expect(box, id).not.toBeNull();
        expect(box!.x + box!.width, id).toBeLessThanOrEqual(width);
      }
      // Two rows: the tabs sit below the brand row, and the header grew to hold them.
      const nav = await page.getByTestId("topbar-nav").boundingBox();
      const signOut = await page.getByTestId("sign-out").boundingBox();
      expect(nav!.y).toBeGreaterThan(signOut!.y + signOut!.height - 1);
      const header = await page.locator("header").boundingBox();
      expect(nav!.y + nav!.height).toBeLessThanOrEqual(header!.y + header!.height);
    });
  }

  // 1640 is the breakpoint itself: the narrowest one-row width.
  for (const width of [1640, 1920]) test(`at ${width}px the bar stays one row`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(page.getByTestId("version-badge")).toBeVisible();

    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    // Nothing squeezed onto a second line: the timezone, SYS and the active tab
    // each stay one line tall (the defect wrapped them onto two and three).
    for (const id of ["tz-badge", "health-status", "topbar-meta"]) {
      const box = await page.getByTestId(id).boundingBox();
      expect(box!.height, id).toBeLessThan(24);
    }
    const active = await page.getByRole("link", { name: /Pipeline/ }).boundingBox();
    expect(active!.height).toBeLessThan(40);   // one line is 32px, two ~49px
    const header = await page.locator("header").boundingBox();
    expect(header!.height).toBeLessThanOrEqual(57);
    const nav = await page.getByTestId("topbar-nav").boundingBox();
    const signOut = await page.getByTestId("sign-out").boundingBox();
    // Same row: their vertical extents overlap.
    expect(nav!.y).toBeLessThan(signOut!.y + signOut!.height);
    expect(signOut!.y).toBeLessThan(nav!.y + nav!.height);
  });
});
