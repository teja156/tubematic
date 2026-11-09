import { test, expect, request as pwRequest } from "@playwright/test";

/**
 * The Mascots page against the real API. A mascot is drawn by an agent session
 * on a scheduled poll, which the test stack does not run, so a created mascot
 * stays PENDING; what is checked here is the page, the Tubi builtin, the
 * request/response wiring and the shared Profiles tab.
 */
test.describe("Mascots", () => {
  test("lists the builtin Tubi and offers a variation instead of edits", async ({ page }) => {
    await page.goto("/mascots");
    const row = page.getByTestId("mascot-row-tubi");
    await expect(row).toBeVisible();
    await expect(row).toContainText("READY");
    await row.click();
    await expect(page.getByTestId("mascot-detail")).toBeVisible();
    await expect(page.getByTestId("mascot-variation")).toBeVisible();
    await expect(page.getByTestId("mascot-request-changes")).toHaveCount(0);
    await expect(page.getByTestId("mascot-approve")).toHaveCount(0);
  });

  test("a builtin's approved sheets load through the authenticated image route", async ({ page }) => {
    await page.goto("/mascots");
    await page.getByTestId("mascot-row-tubi").click();
    const sheet = page.getByTestId("mascot-sheet-approved-turn");
    await expect(sheet).toBeVisible();
    await expect.poll(async () => sheet.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  });

  test("the sheet route refuses anything but a sheet path, and needs a session", async ({ page, baseURL }) => {
    const bad = await page.request.get("/mascot-sheets/tubi/versions/1/sheets/evil");
    expect(bad.status()).toBe(404);
    // A context with no storage state carries no session cookie.
    const anon = await pwRequest.newContext({ baseURL, storageState: { cookies: [], origins: [] } });
    const res = await anon.get("/mascot-sheets/tubi/versions/1/sheets/turn", { maxRedirects: 0 });
    expect(res.status()).toBe(401);
    await anon.dispose();
  });

  test("creating a mascot files it as PENDING, and it can be archived", async ({ page }) => {
    // A unique name per run (and retry): the id is a slug of the name, so a
    // retried attempt must not collide with a mascot a failed one left behind.
    const name = `E2E Pip ${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    await page.goto("/mascots");
    await page.getByTestId("mascot-name").fill(name);
    await page.getByTestId("mascot-description").fill("a small round robot with a visor");
    const created = page.waitForResponse((r) => r.url().endsWith("/api/proxy/mascots") && r.request().method() === "POST");
    await page.getByTestId("mascot-create").click();
    const { id } = await (await created).json();
    const row = page.getByTestId(`mascot-row-${id}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText("PENDING");
    await expect(page.getByTestId("mascot-detail")).toContainText("Queued");
    // Nothing to review or change while it is queued.
    await expect(page.getByTestId("mascot-approve")).toHaveCount(0);
    await expect(page.getByTestId("mascot-request-changes")).toHaveCount(0);

    page.once("dialog", (d) => d.accept());
    await page.getByTestId("mascot-archive").click();
    await expect(row).toHaveCount(0);
  });

  test("Create without a description is refused before any request", async ({ page }) => {
    await page.goto("/mascots");
    await page.getByTestId("mascot-name").fill("No description");
    await page.getByTestId("mascot-create").click();
    await expect(page.getByTestId("mascot-error")).toBeVisible();
  });

  test("the sub-nav switches between Script profiles and Mascots, and the Profiles tab stays active", async ({ page }) => {
    await page.goto("/script-profiles");
    await expect(page.getByTestId("profiles-subnav")).toBeVisible();
    await page.getByTestId("profiles-subnav-mascots").click();
    await expect(page).toHaveURL(/\/mascots$/);
    await expect(page.getByTestId("profiles-subnav-mascots")).toHaveAttribute("aria-current", "page");
    // An active tab is coloured differently from an inactive one.
    const tab = page.getByTestId("nav-script-profiles");
    const active = await tab.evaluate((el) => getComputedStyle(el).color);
    const inactive = await page.getByTestId("nav-settings").evaluate((el) => getComputedStyle(el).color);
    expect(active).not.toBe(inactive);
    await page.getByTestId("profiles-subnav-script-profiles").click();
    await expect(page).toHaveURL(/\/script-profiles$/);
  });

  test("the top bar still fits on one row at 1640px with the Profiles tab active on /mascots", async ({ page }) => {
    await page.setViewportSize({ width: 1640, height: 900 });
    await page.goto("/mascots");
    const tab = await page.getByTestId("nav-script-profiles").boundingBox();
    expect(tab!.height).toBeLessThan(40);   // one line is ~32px, two ~49px
  });

  test("Settings opens on the Rendering tab from ?tab=rendering and offers the default mascot", async ({ page }) => {
    await page.goto("/settings?tab=rendering");
    await expect(page.getByTestId("select-default-mascot")).toBeVisible();
  });
});
