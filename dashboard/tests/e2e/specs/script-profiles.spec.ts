import { test, expect } from "@playwright/test";

/**
 * The create path is deliberately not exercised end-to-end: POST /script-profiles
 * makes a live youtube-transcript.io call, and the test stack has no real key.
 * What is worth covering here is that the page renders against the real API and
 * that its guard fires before any network call is made.
 */
test.describe("Script Profiles", () => {
  test("renders the create form against the live API", async ({ page }) => {
    await page.goto("/script-profiles");
    await expect(page.getByTestId("profile-name")).toBeVisible();
    await expect(page.getByTestId("profile-urls")).toBeVisible();
    await expect(page.getByTestId("profile-create")).toBeVisible();
  });

  test("refuses to submit without a name and a URL", async ({ page }) => {
    await page.goto("/script-profiles");
    await page.getByTestId("profile-create").click();
    await expect(page.getByTestId("profile-error")).toBeVisible();
  });

  // The one test here that stubs the API. A real profile cannot be created
  // (see above), and seeding one would break the empty-state test below.
  // The stubbed name is one unbroken token: its min-content width is the
  // whole string, which is what inflates a fixed-basis flex column that has
  // no minWidth. Underscores, not hyphens — a hyphen is a line-break
  // opportunity, and a hyphenated name passes against the unfixed page.
  // toBeVisible() cannot see a collapsed column, so assert geometry.
  test("a long unbroken profile name does not crush the detail pane", async ({ page }) => {
    const profile = {
      id: "sp-layout-probe",
      name: "a_very_long_profile_name_with_no_break_opportunity_".repeat(3),
      status: "READY",
      source_urls: ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
      error: "",
      attempt_count: 1,
      archived: false,
      created_at: "2026-09-26T00:00:00Z",
      updated_at: "2026-09-26T00:00:00Z",
    };
    await page.route("**/api/proxy/script-profiles", (route) =>
      route.fulfill({ json: [profile] }));
    await page.route(`**/api/proxy/script-profiles/${profile.id}`, (route) =>
      route.fulfill({ json: { ...profile, markdown: "# Style", corpus_summary: "Summary" } }));

    await page.goto("/script-profiles");
    await page.getByTestId(`profile-row-${profile.id}`).click();
    await expect(page.getByTestId("profile-detail")).toBeVisible();

    const row = await page.getByTestId(`profile-row-${profile.id}`).boundingBox();
    const detail = await page.getByTestId("profile-detail").boundingBox();
    const title = await page.getByTestId(`profile-row-${profile.id}`)
      .getByText(profile.name, { exact: true }).boundingBox();
    expect(row!.width).toBeLessThanOrEqual(360);
    expect(detail!.width).toBeGreaterThan(400);
    // With the column held at 340px, the name must wrap inside its row.
    expect(title!.x + title!.width).toBeLessThanOrEqual(row!.x + row!.width);
  });

  test("shows the empty state when no profiles exist", async ({ page }) => {
    await page.goto("/script-profiles");
    // The seed fixture creates videos and projects, never a script profile.
    await expect(page.getByText("— No profiles yet —")).toBeVisible();
  });
});
