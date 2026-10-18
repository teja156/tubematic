import { test, expect } from "@playwright/test";
import { TEST_PASSWORD } from "../fixtures/seed";

// Dashboard sign-in (TMDEV-152). Every other spec starts signed in from the
// state global-setup saves; this one starts signed out on purpose.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Signing in", () => {
  test("a page without a session goes to /login and comes back after signing in", async ({ page }) => {
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/login\?next=%2Fsettings$/);
    await page.getByTestId("login-password").fill(TEST_PASSWORD);
    await page.getByTestId("login-submit").click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByTestId("sign-out")).toBeVisible();
  });

  test("a wrong password is refused and says so", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-password").fill("not the password");
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("login-error")).toHaveText("Wrong password.");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("signing out ends the session for the API as well as the pages", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-password").fill(TEST_PASSWORD);
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("sign-out")).toBeVisible();
    expect((await page.request.get("/api/proxy/settings")).status()).toBe(200);

    await page.getByTestId("sign-out").click();
    await expect(page).toHaveURL(/\/login$/);
    expect((await page.request.get("/api/proxy/settings")).status()).toBe(401);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("the API proxy and the media route refuse a request with no session", async ({ request }) => {
    expect((await request.get("/api/proxy/settings")).status()).toBe(401);
    expect((await request.post("/api/proxy/settings", { data: {} })).status()).toBe(401);
    expect((await request.get("/stream/any.mp4")).status()).toBe(401);
  });

  test("a forged cookie is refused by the API proxy", async ({ page, context }) => {
    await context.addCookies([{ name: "tm_session", value: "forged.token.value",
                                domain: "localhost", path: "/" }]);
    // Middleware only checks the cookie is present, so the page loads ...
    await page.goto("/settings");
    // ... but the data behind it does not, and the page is sent to /login.
    expect((await page.request.get("/api/proxy/settings")).status()).toBe(401);
    await expect(page).toHaveURL(/\/login/, { timeout: 40_000 });
  });

  test("the login page has no top bar and fits at 1024px", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/login");
    await expect(page.getByTestId("login-form")).toBeVisible();
    await expect(page.locator("header")).toHaveCount(0);
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(1024);
  });
});
