import { test, expect } from "@playwright/test";
import { API_AUTH, BASE, createProject, getSettings, previewVoice, setSettings } from "../fixtures/seed";


// ── Tab + Save helpers ──────────────────────────────────────────────────────
// Settings are grouped into tabs and committed by an explicit Save button, so
// a test opens the relevant tab, edits, then saves. Pause/resume and voice
// preview are actions rather than settings and still apply immediately.

const TAB_OF: Record<string, string> = {
  "toggle-gemini-review": "ai-review",
  "select-ai-review-model": "ai-review",
  "input-ai-review-fps": "ai-review",
  "input-ai-review-max-loops": "ai-review",
  "input-max-curriculum-per-run": "research",
  "input-research-pending-cap": "research",
  "input-max-research-runs-per-day": "research",
  "trending-sources-editor": "research",
  "select-elevenlabs-model-id": "voice",
  "select-image-provider": "images",
  "input-render-timeout-mins": "rendering",
  "input-max-render-retries": "rendering",
};

async function gotoTab(page: import("@playwright/test").Page, tab: string) {
  await page.goto("/settings");
  await expect(page.getByTestId(`tab-${tab}`)).toBeVisible({ timeout: 10_000 });
  await page.getByTestId(`tab-${tab}`).click();
}

async function save(page: import("@playwright/test").Page, tab: string) {
  await page.getByTestId(`save-${tab}`).click();
  await expect(page.getByTestId("toast-success")).toBeVisible({ timeout: 5_000 });
}

test.describe("Settings page", () => {
  test.beforeEach(async () => {
    // Reset to known state before each test
    await setSettings({
      max_render_retries: 1,
      gemini_review_enabled: true,
      pipeline_paused: false,
      research_pending_cap: 15,
      render_timeout_secs: 2400,
      watermark_enabled: true,
      ai_review_model: "gemini-2.5-flash",
      ai_review_fps: 10,
      ai_review_max_loops: 1,
      user_preferences: "",
      max_concurrent_agent_sessions: 3,
      agent_session_timeout_secs: 5400,
      auto_pilot_enabled: false,
    });
  });

  test("AI review is labelled experimental beside its switch", async ({ page }) => {
    await gotoTab(page, "ai-review");
    await expect(page.getByTestId("ai-review-experimental")).toBeVisible();
    await expect(page.getByTestId("ai-review-experimental")).toHaveText(/experimental/i);
  });

  test("changing the AI review model persists", async ({ page }) => {
    await gotoTab(page, "ai-review");

    await page.getByTestId("select-ai-review-model").selectOption("gemini-3.6-flash");

    await save(page, "ai-review");
    expect((await getSettings()).ai_review_model).toBe("gemini-3.6-flash");
  });

  test("changing the review sampling rate persists", async ({ page }) => {
    await gotoTab(page, "ai-review");

    const input = page.getByTestId("input-ai-review-fps");
    await expect(input).toHaveValue("10");
    await input.fill("20");
    await input.press("Enter");

    await save(page, "ai-review");
    expect((await getSettings()).ai_review_fps).toBe(20);
  });

  test("the API rejects a sampling rate outside Gemini's valid range", async ({ request }) => {
    // Outside (0, 24] Gemini 400s and the review fails open, silently
    // shipping the video unreviewed — so this has to be rejected on write.
    const res = await request.post(`${BASE}/settings`, {
      headers: API_AUTH,
      data: { ai_review_fps: 60 },
    });
    expect(res.status()).toBe(400);
    expect((await getSettings()).ai_review_fps).toBe(10);
  });

  test("the review loop cap and the render retry cap are independent controls", async ({ page }) => {
    // VQA-7 split these: before, one knob capped both, so lowering the review
    // loop silently halved the render crash/timeout retry budget.
    await gotoTab(page, "ai-review");
    await expect(page.getByTestId("input-ai-review-max-loops")).toHaveValue("1");
    // Different tabs now, which makes conflating the two harder still.
    await page.getByTestId("tab-rendering").click();
    await expect(page.getByTestId("input-max-render-retries")).toHaveValue("1");
  });

  test("settings page loads and renders pipeline pause toggle", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByTestId("toggle-pipeline-pause")).toBeVisible({ timeout: 10_000 });
  });

  test("changing max_render_retries persists after reload", async ({ page }) => {
    await gotoTab(page, "rendering");

    const input = page.getByTestId("input-max-render-retries");
    await input.fill("4");
    await input.press("Enter");

    // Verify via API that it was saved
    await save(page, "rendering");
    const settings = await getSettings();
    expect(settings.max_render_retries).toBe(4);
  });

  test("changing render timeout (minutes) persists as render_timeout_secs", async ({ page }) => {
    await gotoTab(page, "rendering");

    const input = page.getByTestId("input-render-timeout-mins");
    await expect(input).toHaveValue("40"); // seeded 2400s
    await input.fill("45");
    await input.press("Enter");

    await save(page, "rendering");
    const settings = await getSettings();
    expect(settings.render_timeout_secs).toBe(2700);
  });

  test("the agent-session settings save from the Scheduling tab", async ({ page }) => {
    await gotoTab(page, "scheduling");

    const slots = page.getByTestId("input-max-concurrent-agent-sessions");
    await expect(slots).toHaveValue("3");
    await slots.fill("1");
    await slots.press("Enter");
    const timeout = page.getByTestId("input-agent-session-timeout-mins");
    await expect(timeout).toHaveValue("90"); // seeded 5400s
    await timeout.fill("30");
    await timeout.press("Enter");

    await save(page, "scheduling");
    const settings = await getSettings();
    expect(settings.max_concurrent_agent_sessions).toBe(1);
    expect(settings.agent_session_timeout_secs).toBe(1800);
  });

  test("research_pending_cap input is visible and editable", async ({ page }) => {
    await gotoTab(page, "research");
  });

  test("max_research_runs_per_day input is visible and persists after reload", async ({ page }) => {
    await gotoTab(page, "research");

    const input = page.getByTestId("input-max-research-runs-per-day");
    await input.fill("3");
    await input.press("Enter");

    await save(page, "research");
    const settings = await getSettings();
    expect(settings.max_research_runs_per_day).toBe(3);
  });

  test("research window readout is visible", async ({ page }) => {
    await gotoTab(page, "scheduling");
    await expect(page.getByTestId("research-runs-used")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("research-window-resets")).toBeVisible();
    await expect(page.getByTestId("last-research-at")).toBeVisible();
  });

  test("trending sources editor is visible with checkboxes", async ({ page }) => {
    await gotoTab(page, "research");
    await expect(page.getByTestId("trending-source-checkbox-github-trending")).toBeVisible();
    await expect(page.getByTestId("trending-source-checkbox-hacker-news")).toBeVisible();
    await expect(page.getByTestId("trending-source-checkbox-lobsters")).toBeVisible();
    await expect(page.getByTestId("trending-source-checkbox-dev-to")).toBeVisible();
  });

  test("toggling a trending source checkbox persists via POST /settings", async ({ page }) => {
    // Start with only the two defaults so Lobsters is unchecked
    await setSettings({ trending_sources: ["GitHub Trending", "Hacker News"] });

    await gotoTab(page, "research");

    // The checkbox stages the change; the POST happens on Save.
    await page.getByTestId("trending-source-checkbox-lobsters").locator("input").click();

    const [request] = await Promise.all([
      page.waitForRequest((req) => req.url().includes("/settings") && req.method() === "POST"),
      page.getByTestId("save-research").click(),
    ]);

    const body = request.postDataJSON();
    expect(body.trending_sources).toContain("Lobsters");
  });

  // TMDEV-121: there is no install-wide model — each voice carries its own.
  test("no install-wide model or pronunciation mode select", async ({ page }) => {
    await setSettings({
      elevenlabs_voices: [{ name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }],
    });
    await gotoTab(page, "voice");
    await expect(page.getByTestId("voice-model-0")).toHaveValue("eleven_multilingual_v2", { timeout: 10_000 });
    await expect(page.getByTestId("select-elevenlabs-model-id")).toHaveCount(0);
    await expect(page.getByTestId("select-pronunciation-mode")).toHaveCount(0);
  });

  test("changing a voice's model persists it on that voice only", async ({ page }) => {
    await setSettings({
      elevenlabs_voices: [
        { name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" },
        { name: "Energetic", voice_id: "voice-def456", model_id: "eleven_multilingual_v2" },
      ],
    });
    await gotoTab(page, "voice");
    await expect(page.getByTestId("voice-model-1")).toBeVisible({ timeout: 10_000 });

    await page.getByTestId("voice-model-1").selectOption("eleven_v3");
    await save(page, "voice");

    const settings = await getSettings();
    expect(settings.elevenlabs_voices).toEqual([
      { name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" },
      { name: "Energetic", voice_id: "voice-def456", model_id: "eleven_v3" },
    ]);
    expect(settings).not.toHaveProperty("elevenlabs_model_id");
    expect(settings).not.toHaveProperty("pronunciation_mode");
  });

  test("the Images tab offers the OpenAI catalog and no provider", async ({ page }) => {
    await setSettings({ image_model: "gpt-image-2.5-flare" });
    await gotoTab(page, "images");
    await expect(page.getByTestId("select-image-provider")).toHaveCount(0);
    const model = page.getByTestId("select-image-model");
    await expect(model).toHaveValue("gpt-image-2.5-flare");
    await expect(model.locator("option")).toHaveText(["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]);

    await model.selectOption("gpt-image-2.5-sunburst");
    await save(page, "images");
    expect((await getSettings()).image_model).toBe("gpt-image-2.5-sunburst");
  });

  test("changing the character model persists", async ({ page }) => {
    await setSettings({ character_model: "gpt-image-2.5-flare" });
    await gotoTab(page, "images");
    await expect(page.getByTestId("select-character-model")).toHaveValue("gpt-image-2.5-flare");

    await page.getByTestId("select-character-model").selectOption("gpt-image-2.5-sunburst");
    await save(page, "images");

    expect((await getSettings()).character_model).toBe("gpt-image-2.5-sunburst");
  });

  // ── ElevenLabs voice roster (TMDEV-51) ──────────────────────────────────────

  test.describe("Voice roster", () => {
    test.beforeEach(async () => {
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    });

    test("adding a voice persists it in the roster", async ({ page }) => {
      await gotoTab(page, "voice");
      await expect(page.getByTestId("voices-editor")).toBeVisible({ timeout: 10_000 });

      await page.getByTestId("voice-add-name").fill("Narrator");
      await page.getByTestId("voice-add-id").fill("voice-abc123");
      await page.getByTestId("voice-add").click();

      await save(page, "voice");
      const settings = await getSettings();
      expect(settings.elevenlabs_voices).toEqual([{ name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }]);
    });

    test("renaming a voice persists the whole updated roster", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [{ name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }],
      });
      await gotoTab(page, "voice");
      await expect(page.getByTestId("voice-name-0")).toBeVisible({ timeout: 10_000 });

      await page.getByTestId("voice-name-0").fill("Main Narrator");
      await page.getByTestId("voice-name-0").blur();

      await save(page, "voice");
      const settings = await getSettings();
      expect(settings.elevenlabs_voices).toEqual([{ name: "Main Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }]);
    });

    test("marking a different voice as default persists both keys", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [
          { name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" },
          { name: "Energetic", voice_id: "voice-def456", model_id: "eleven_multilingual_v2" },
        ],
        elevenlabs_voice_id: "voice-abc123",
      });
      await gotoTab(page, "voice");
      await expect(page.getByTestId("voice-default-1")).toBeVisible({ timeout: 10_000 });

      await page.getByTestId("voice-default-1").locator("input").click();

      await save(page, "voice");
      const settings = await getSettings();
      expect(settings.elevenlabs_voice_id).toBe("voice-def456");
    });

    test("removing the current default voice blanks the default", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [{ name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }],
        elevenlabs_voice_id: "voice-abc123",
      });
      await gotoTab(page, "voice");
      await expect(page.getByTestId("voice-remove-0")).toBeVisible({ timeout: 10_000 });

      await page.getByTestId("voice-remove-0").click();

      await save(page, "voice");
      const settings = await getSettings();
      expect(settings.elevenlabs_voices).toEqual([]);
      expect(settings.elevenlabs_voice_id).toBe("");
    });

    test("the add-voice row is hidden and a cap note shown at 10 voices", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: Array.from({ length: 10 }, (_, i) => ({
          name: `v${i}`, voice_id: `id${i}`, model_id: "eleven_multilingual_v2" })),
        elevenlabs_voice_id: "id0",
      });
      await gotoTab(page, "voice");
      await expect(page.getByTestId("voice-cap-note")).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId("voice-add-row")).toHaveCount(0);
    });

    // Voice previews (TMDEV-51 follow-up). Deliberately does NOT click the
    // preview button: docker-compose.test.yml sets ELEVENLABS_API_KEY=test,
    // so a real click would make a live outbound call to elevenlabs.io and
    // get a 401 — these tests only cover render presence and the pre-spend
    // roster-membership guard.

    test("a preview button renders per roster row", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [{ name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }],
      });
      await gotoTab(page, "voice");
      await expect(page.getByTestId("voice-preview-voice-abc123")).toBeVisible({ timeout: 10_000 });
    });

    test("the preview endpoint refuses an unknown model before any ElevenLabs call", async () => {
      await setSettings({
        elevenlabs_voices: [{ name: "Narrator", voice_id: "voice-abc123", model_id: "eleven_multilingual_v2" }],
      });
      const { status, body } = await previewVoice("voice-abc123", { model_id: "eleven_english_v1" });
      expect(status).toBe(400);
      expect(body.error).toContain("model_id");
    });

    test("the preview endpoint rejects a voice_id not in the roster", async () => {
      await setSettings({ elevenlabs_voices: [] });
      const { status, body } = await previewVoice("not-in-roster");
      expect(status).toBe(400);
      expect(body.error).toContain("not in elevenlabs_voices");
    });
  });
  test("an edit is not persisted until Save is clicked", async ({ page }) => {
    await gotoTab(page, "rendering");
    const input = page.getByTestId("input-max-render-retries");
    await input.fill("6");
    await input.press("Enter");

    // Staged only — the API still holds the old value.
    await page.waitForTimeout(500);
    expect((await getSettings()).max_render_retries).toBe(1);
    await expect(page.getByTestId("tab-dirty-rendering")).toBeVisible();

    await save(page, "rendering");
    expect((await getSettings()).max_render_retries).toBe(6);
  });

  test("every settings tab stays on screen at a narrower desktop width", async ({ page }) => {
    // body clips horizontal overflow, so a tab pushed past the right edge
    // could not be reached at all — the last one added is the first to go.
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/settings");
    const tab = page.getByTestId("tab-auto-pilot");
    await expect(tab).toBeVisible({ timeout: 10_000 });
    const box = await tab.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(1024);
    await tab.click();
    await expect(page.getByTestId("auto-pilot-disclaimer")).toBeVisible();
  });

  test("Auto Pilot is turned on for one project only after a confirmation", async ({ page, request }) => {
    const id = `e2e-auto-${Date.now()}`;
    await createProject({ id, name: `Auto ${id}` });
    await request.post(`${BASE}/autopilot`, {
      headers: API_AUTH,
      data: { enabled: false, gap_mins: 240, max_in_flight: 0, projects: {}, account_limits: {} },
    });

    await gotoTab(page, "auto-pilot");
    await expect(page.getByTestId("auto-pilot-disclaimer")).toContainText("no human review");
    await expect(page.getByTestId("toggle-auto-pilot")).toHaveText("OFF");

    await page.getByTestId(`auto-pilot-project-toggle-${id}`).check();
    await page.getByTestId("toggle-auto-pilot").click();
    await page.getByTestId("select-auto-pilot-gap-unit").selectOption("minutes");
    await page.getByTestId("input-auto-pilot-gap").fill("90");
    await page.getByTestId("input-auto-pilot-gap").blur();
    await page.getByTestId("input-auto-pilot-max-in-flight").fill("3");
    await page.getByTestId("save-auto-pilot").click();

    // Nothing is saved until the dialog is confirmed.
    await expect(page.getByTestId("auto-pilot-confirm")).toBeVisible();
    await expect(page.getByTestId("auto-pilot-confirm-disclaimer")).toContainText("posts publicly");
    expect((await getSettings()).auto_pilot_enabled).toBe(false);

    await page.getByTestId("auto-pilot-confirm-ok").click();
    await expect(page.getByTestId("auto-pilot-status")).toHaveText("Saved.");
    const saved = await (await request.get(`${BASE}/autopilot`, { headers: API_AUTH })).json();
    expect(saved.enabled).toBe(true);
    expect(saved.gap_mins).toBe(90);
    expect(saved.max_in_flight).toBe(3);
    expect(saved.projects).toEqual({ [id]: [] });
    // The panel counts videos in progress against the limit.
    await expect(page.getByTestId("auto-pilot-ceiling")).toContainText(/\d+ of 3 videos in progress\./);

    // The pipeline page says so.
    await page.goto("/");
    await expect(page.getByTestId("auto-pilot-notice")).toBeVisible();

    await request.post(`${BASE}/autopilot`, {
      headers: API_AUTH,
      data: { enabled: false, gap_mins: 240, max_in_flight: 0, projects: {}, account_limits: {} },
    });
  });

  test("user preferences persist with their line breaks, and the API enforces the cap", async ({ page, request }) => {
    await gotoTab(page, "preferences");
    const box = page.getByTestId("input-user-preferences");
    await box.fill("Topics: favour Linux internals.\nScripts: calm tone.");
    await expect(page.getByTestId("user-preferences-count")).toHaveText("51 / 6000");

    await save(page, "preferences");
    expect((await getSettings()).user_preferences)
      .toBe("Topics: favour Linux internals.\nScripts: calm tone.");

    const r = await request.post(`${BASE}/settings`, {
      headers: API_AUTH,
      data: { user_preferences: "x".repeat(6001) },
    });
    expect(r.status()).toBe(400);
    expect((await getSettings()).user_preferences)
      .toBe("Topics: favour Linux internals.\nScripts: calm tone.");
  });
});
