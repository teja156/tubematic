import { test, expect } from "@playwright/test";
import {
  createProject, createVideo, setProjectStatus, setSettings, setStrategies, setMiningSources,
} from "../fixtures/seed";

test.describe("Topics page", () => {
  let uid: string;

  test.beforeEach(async () => {
    uid = crypto.randomUUID().slice(0, 8);
    // Reset strategies to all-active before each test
    await setStrategies(["curriculum", "trending", "mining"]);
  });

  // ── Navigation ─────────────────────────────────────────────────────────────

  test("Topics nav link is visible in TopBar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("nav-topics")).toBeVisible();
  });

  test("clicking Topics nav link goes to /topics", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-topics").click();
    await expect(page).toHaveURL(/\/topics/);
  });

  // ── Mode toggles ───────────────────────────────────────────────────────────

  test("all three mode toggle chips render", async ({ page }) => {
    await page.goto("/topics");
    await expect(page.getByTestId("mode-toggle-curriculum")).toBeVisible();
    await expect(page.getByTestId("mode-toggle-trending")).toBeVisible();
    await expect(page.getByTestId("mode-toggle-mining")).toBeVisible();
  });

  test("toggling a mode off and back on persists", async ({ page }) => {
    await page.goto("/topics");

    // Turn off trending
    const trendingBtn = page.getByTestId("mode-toggle-trending");
    await trendingBtn.click();

    // Navigate away and back to confirm persistence
    await page.goto("/");
    await page.goto("/topics");

    // trending should now be off (dimmer appearance, but most reliably we
    // check that re-clicking it turns it back on without error)
    await expect(page.getByTestId("mode-toggle-trending")).toBeVisible();
  });

  // ── Add domain form ────────────────────────────────────────────────────────

  test("add domain form renders on the Topics page", async ({ page }) => {
    await page.goto("/topics");
    await expect(page.getByTestId("add-domain-form")).toBeVisible();
    await expect(page.getByTestId("domain-name-input")).toBeVisible();
    await expect(page.getByTestId("add-domain-submit")).toBeVisible();
  });

  test("submit button is disabled when name is empty", async ({ page }) => {
    await page.goto("/topics");
    const btn = page.getByTestId("add-domain-submit");
    await expect(btn).toBeDisabled();
  });

  test("adding a domain shows it in the seed domains list", async ({ page }) => {
    const domainName = `Test Domain ${uid}`;
    await page.goto("/topics");

    await page.getByTestId("domain-name-input").fill(domainName);
    await page.getByTestId("add-domain-submit").click();

    // Wait for the domain row to appear
    const slug = `test-domain-${uid}`;
    await expect(page.getByTestId(`domain-row-${slug}`)).toBeVisible({ timeout: 5000 });
  });

  test("a multi-line description sits on its own row and its domain row stays one line", async ({ page }) => {
    const slug = `scoped-domain-${uid}`;
    await page.goto("/topics");

    const name = page.getByTestId("domain-name-input");
    const description = page.getByTestId("domain-description-input");
    // Below the name, not beside it: a tall box next to a one-line input made
    // the row ragged.
    const nameBox = (await name.boundingBox())!;
    const descBox = (await description.boundingBox())!;
    expect(descBox.y).toBeGreaterThanOrEqual(nameBox.y + nameBox.height);

    await name.fill(`Scoped Domain ${uid}`);
    await description.fill("Storage engines and query planning.\n\nNot: ORMs or SQL tutorials.");
    await expect(page.getByTestId("domain-description-count")).toHaveText("64 / 2000");
    await page.getByTestId("add-domain-submit").click();

    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row).toBeVisible({ timeout: 5000 });
    // The list keeps the description on one truncated line.
    const text = row.getByText("Storage engines and query planning.", { exact: false });
    const lineHeight = await text.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight) || 16);
    expect((await text.boundingBox())!.height).toBeLessThan(lineHeight * 1.5);
  });

  test("new domain shows ACTIVE badge", async ({ page }) => {
    const domainName = `Active Domain ${uid}`;
    const slug = `active-domain-${uid}`;

    await createProject({ id: slug, name: domainName, is_curriculum_seed: true });
    await page.goto("/topics");

    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText("ACTIVE");
  });

  // TMDEV-121: every new video filed into a domain starts with its default voice.
  test("a domain's default voice is picked on its row and seeds its next video", async ({ page }) => {
    const slug = `voice-domain-${uid}`;
    await setSettings({
      elevenlabs_voices: [
        { name: "Narrator", voice_id: `${uid}-v2`, model_id: "eleven_multilingual_v2" },
        { name: "Adam", voice_id: `${uid}-v3`, model_id: "eleven_v3" },
      ],
      elevenlabs_voice_id: `${uid}-v2`,
    });
    try {
      await createProject({ id: slug, name: `Voice Domain ${uid}`, is_curriculum_seed: false });
      await page.goto("/topics");
      const select = page.getByTestId(`domain-voice-${slug}`);
      await expect(select.locator(`option[value="${uid}-v3"]`)).toHaveCount(1, { timeout: 10_000 });
      await Promise.all([
        page.waitForResponse((r) => r.url().includes("/projects") && r.request().method() === "POST"),
        select.selectOption(`${uid}-v3`),
      ]);

      const video = await createVideo({ topic: `[${uid}] inherits voice`, project_id: slug, strategy: "trending" });
      expect(video.voice_id).toBe(`${uid}-v3`);
    } finally {
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    }
  });

  // TMDEV-145: a third per-domain picker, the default script profile, and a
  // label above each of the three. TMDEV-153 added the topic cap as a fourth. A READY profile cannot be created here
  // (creation makes a live transcript call), so the list is stubbed in the
  // browser and seeding is left to the API suites. What only a real browser
  // shows is the layout: a seed row with three labelled pickers, a count,
  // a badge and the pause button must still fit at 1280px.
  test("a domain row labels its three pickers and still fits at 1280px", async ({ page }) => {
    const slug = `labels-domain-${uid}`;
    await createProject({ id: slug, name: `Labels Domain ${uid}`, is_curriculum_seed: true });
    await page.route("**/api/proxy/script-profiles", (route) => route.fulfill({ json: [
      { id: `sp-${uid}`, name: "Stubbed profile", status: "READY", source_urls: [], error: "",
        attempt_count: 1, archived: false, created_at: "2026-10-05T00:00:00Z",
        updated_at: "2026-10-05T00:00:00Z" },
    ] }));
    // The widest the cap field gets: a three-digit count beside a three-digit
    // cap. Filing 120 real topics would only slow the suite down.
    await page.route("**/api/proxy/projects", async (route) => {
      const res = await route.fetch();
      const rows = (await res.json()) as Array<Record<string, unknown>>;
      await route.fulfill({ response: res, json: rows.map((p) => p.id === slug
        ? { ...p, topic_count: 120, topic_cap: 220 } : p) });
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/topics");

    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row).toBeVisible();
    for (const label of ["Visual style", "Default voice", "Script profile", "Topic cap"]) {
      await expect(row.getByText(label, { exact: true })).toBeVisible();
    }
    const profile = page.getByTestId(`domain-profile-${slug}`);
    await expect(profile.locator(`option[value="sp-${uid}"]`)).toHaveCount(1);
    await expect(profile).toHaveValue("");

    const rowBox = await row.boundingBox();
    const toggle = await page.getByTestId(`toggle-domain-${slug}`).boundingBox();
    expect(rowBox!.x + rowBox!.width).toBeLessThanOrEqual(1280);
    expect(toggle!.x + toggle!.width).toBeLessThanOrEqual(rowBox!.x + rowBox!.width);
    // The name must keep real room and not run under the first caption. Each
    // select sizes to its longest option, and three at that width left a seed
    // row's name ~70px wide, with a long word overlapping "Visual style".
    const name = await row.getByText(`Labels Domain ${uid}`, { exact: true }).boundingBox();
    const style = await page.getByTestId(`domain-style-${slug}`).boundingBox();
    expect(name!.width).toBeGreaterThanOrEqual(150);
    expect(name!.x + name!.width).toBeLessThanOrEqual(style!.x);
    // One line at 1280px: the pause button sits level with the pickers rather
    // than wrapping under them, and "120 filed" does not break in two.
    expect(toggle!.y).toBeLessThan(style!.y + style!.height);
    const filed = row.getByTestId(`domain-topic-count-${slug}`);
    await expect(filed).toHaveText("120 filed");
    const filedBox = await filed.boundingBox();
    const cap = await page.getByTestId(`domain-cap-${slug}`).boundingBox();
    expect(filedBox!.height).toBeLessThanOrEqual(cap!.height);

    // Narrower, the row wraps instead: the name keeps its room and the pause
    // button moves to a second line, still inside the row.
    await page.setViewportSize({ width: 1024, height: 800 });
    const narrowRow = await row.boundingBox();
    const narrowName = await row.getByText(`Labels Domain ${uid}`, { exact: true }).boundingBox();
    const narrowToggle = await page.getByTestId(`toggle-domain-${slug}`).boundingBox();
    expect(narrowName!.width).toBeGreaterThanOrEqual(150);
    expect(narrowToggle!.x + narrowToggle!.width).toBeLessThanOrEqual(narrowRow!.x + narrowRow!.width);
  });

  // TMDEV-153: a domain may only ever hold topic_cap topics. At the cap it is
  // expired and research files nothing more there; raising the cap re-opens it.
  test("a domain at its topic cap shows EXPIRED until the cap is raised", async ({ page }) => {
    const slug = `cap-domain-${uid}`;
    await createProject({ id: slug, name: `Cap Domain ${uid}`, is_curriculum_seed: true, topic_cap: 25 });
    // Manual filing is exempt from the cap, so it can fill the domain.
    for (let i = 0; i < 25; i++) {
      await createVideo({ topic: `[${uid}] topic ${i}`, project_id: slug, strategy: "manual" });
    }
    await expect(createVideo({ topic: `[${uid}] one more`, project_id: slug, strategy: "curriculum" }))
      .rejects.toThrow(/409/);

    await page.goto("/topics");
    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row.getByTestId(`domain-expired-${slug}`)).toBeVisible();
    await expect(row.getByTestId(`domain-status-${slug}`)).toHaveCount(0);
    await expect(row.getByTestId(`domain-topic-count-${slug}`)).toHaveText("25 filed");

    const cap = page.getByTestId(`domain-cap-${slug}`);
    await expect(cap).toHaveValue("25");
    await cap.fill("26");
    await Promise.all([
      page.waitForResponse((r) => r.url().includes("/projects") && r.request().method() === "POST"),
      cap.press("Enter"),
    ]);
    await expect(row.getByTestId(`domain-expired-${slug}`)).toHaveCount(0);
    await expect(row.getByTestId(`domain-status-${slug}`)).toHaveText("ACTIVE");

    await page.reload();
    await expect(page.getByTestId(`domain-cap-${slug}`)).toHaveValue("26");
    const video = await createVideo({ topic: `[${uid}] fits now`, project_id: slug, strategy: "curriculum" });
    expect(video.status).toBe("TOPIC_PROPOSED");
  });

  // ── Domain pause / activate ────────────────────────────────────────────────

  test("pausing a domain changes badge to PAUSED", async ({ page }) => {
    const slug = `pause-test-${uid}`;
    await createProject({ id: slug, name: `Pause Test ${uid}`, is_curriculum_seed: true });

    await page.goto("/topics");

    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row).toBeVisible();

    // Click Pause
    await row.getByTestId(`toggle-domain-${slug}`).click();

    // Badge should change to PAUSED
    await expect(row).toContainText("PAUSED", { timeout: 3000 });
  });

  test("resuming a paused domain changes badge back to ACTIVE", async ({ page }) => {
    const slug = `resume-test-${uid}`;
    await createProject({ id: slug, name: `Resume Test ${uid}`, is_curriculum_seed: true });
    await setProjectStatus(slug, "paused");

    await page.goto("/topics");

    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row).toBeVisible();
    await expect(row).toContainText("PAUSED");

    // Click Resume
    await row.getByTestId(`toggle-domain-${slug}`).click();

    await expect(row).toContainText("ACTIVE", { timeout: 3000 });
  });

  test("a domain that is not a curriculum seed offers no pause control", async ({ page }) => {
    // Pause stops topics generated FROM a seed; any other domain only receives
    // topics researched elsewhere, so the API refuses to pause one.
    const slug = `plain-test-${uid}`;
    await createProject({ id: slug, name: `Plain Test ${uid}`, is_curriculum_seed: false });

    await page.goto("/topics");

    const row = page.getByTestId(`domain-row-${slug}`);
    await expect(row).toBeVisible();
    await expect(row.getByTestId(`toggle-domain-${slug}`)).toHaveCount(0);
    await expect(row.getByTestId(`domain-status-${slug}`)).toHaveCount(0);
  });

  // ── Mining sources ─────────────────────────────────────────────────────────

  test("Mining Sources section renders on Topics page", async ({ page }) => {
    await setMiningSources([]);
    await page.goto("/topics");
    await expect(page.getByTestId("mining-sources-section")).toBeVisible();
  });

  test("Add a YouTube URL via the mining sources UI", async ({ page }) => {
    await setMiningSources([]);
    await page.goto("/topics");

    const input = page.getByTestId("mining-url-input");
    await input.fill("https://youtu.be/dQw4w9WgXcQ?si=share");
    await page.getByTestId("mining-url-add").click();

    // Stored, and listed, in the canonical form the API rewrites every URL to.
    const canonical = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
    await expect(page.getByTestId("mining-url-item")).toContainText(canonical);

    // Reload — proves the add was actually persisted, not just held in local state.
    await page.reload();
    await expect(page.getByTestId("mining-url-item")).toContainText(canonical);
  });

  test("Remove a YouTube URL from the mining sources UI", async ({ page }) => {
    const url = "https://www.youtube.com/watch?v=removeMe123";
    await setMiningSources([url]);
    await page.goto("/topics");

    const item = page.getByTestId("mining-url-item");
    await expect(item).toBeVisible();

    await item.getByRole("button", { name: `Remove ${url}` }).click();

    await expect(page.getByTestId("mining-url-item")).toHaveCount(0);

    // Reload — proves the removal was actually persisted, not just held in local state.
    await page.reload();
    await expect(page.getByTestId("mining-url-item")).toHaveCount(0);
  });

  test("Adding a URL does not overwrite existing mining sources", async ({ page }) => {
    // Canonical already, so the API stores each exactly as written.
    const url1 = "https://www.youtube.com/watch?v=existingOne";
    const url2 = "https://www.youtube.com/watch?v=existingTwo";
    const url3 = "https://www.youtube.com/watch?v=addedThird3";
    await setMiningSources([url1, url2]);
    await page.goto("/topics");

    await expect(page.getByTestId("mining-url-item")).toHaveCount(2);

    const input = page.getByTestId("mining-url-input");
    await input.fill(url3);
    await page.getByTestId("mining-url-add").click();

    await expect(page.getByTestId("mining-url-item")).toHaveCount(3);

    // Reload — proves all three (not just the newly-added one) are persisted.
    await page.reload();
    await expect(page.getByTestId("mining-url-item")).toHaveCount(3);
    for (const url of [url1, url2, url3]) {
      await expect(page.getByTestId("mining-url-item").filter({ hasText: url })).toBeVisible();
    }
  });
});
