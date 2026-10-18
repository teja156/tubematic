import { test, expect } from "@playwright/test";
import { createProject, createVideo, patchVideo, getVideo, setSettings, BASE, API_AUTH } from "../fixtures/seed";

test.describe("Pipeline board", () => {
  let uid: string;

  test.beforeEach(() => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("Overview badge shows host-local time with an explicit zone, never bare UTC", async ({ page }) => {
    await page.goto("/");
    // playwright.config.ts sets the browser to Asia/Tokyo; docker-compose.test.yml
    // sets the API to America/New_York — neither is UTC, so this also proves the
    // badge switched off the old hand-rolled "Updated HH:MM:SS UTC" clock. Note the
    // zone *label* legitimately contains the substring "UTC" as part of its offset
    // notation (e.g. "EDT (UTC-04:00)") — the regression this guards against is the
    // old badge's bare " UTC" suffix with no offset, not the substring itself.
    const badge = page.getByText(/^Updated \d{2}:\d{2}:\d{2}/);
    await expect(badge).toBeVisible({ timeout: 15_000 });
    await expect(badge).not.toContainText(/\bUTC\b(?!-)/);
    await expect(badge).toContainText(/EST|EDT/);
  });

  test("all 14 column headers render on load (including side columns)", async ({ page }) => {
    await createVideo({ topic: `[${uid}] Init video`, status: "FAILED" });
    await page.goto("/");

    const columns = [
      "Topic Proposed", "Topic Approved", "Script Ready",
      "Voicing", "Voice Ready", "Rendering", "Video Ready",
      "Video Approved", "Scheduled", "Publishing", "Published",
      "Rejected", "Revision Requested", "Failed",
    ];
    for (const col of columns) {
      await expect(page.getByRole("heading", { name: col })).toBeVisible();
    }
  });

  test("summary strip tile counts match seeded data", async ({ page }) => {
    await createVideo({ topic: `[${uid}] Proposed A` });
    await createVideo({ topic: `[${uid}] Proposed B` });
    const v3 = await createVideo({ topic: `[${uid}] Voicing` });
    await patchVideo(v3.id, { status: "VOICING" });

    await page.goto("/");

    // tile-01 = Topics Awaiting (TOPIC_PROPOSED)
    const tile01 = page.getByTestId("summary-tile-01");
    await expect(tile01).toBeVisible();
    await expect(tile01.getByTestId("tile-count-01")).not.toBeEmpty();
  });

  test("TOPIC_PROPOSED card in ActionPane has Approve + Reject + Revise buttons", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Needs review` });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await expect(actionCard.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(actionCard.getByRole("button", { name: "Reject" })).toBeVisible();
    await expect(actionCard.getByRole("button", { name: "Revise" })).toBeVisible();
  });

  test("Approve topic moves card to TOPIC_APPROVED column", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Approve me` });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await actionCard.getByRole("button", { name: "Approve" }).click();

    // Card should disappear from ActionPane
    await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

    // Card should appear in TOPIC_APPROVED column after polling
    const approvedCol = page.getByTestId("kanban-col-TOPIC_APPROVED");
    await expect(approvedCol.getByText(`[${uid}] Approve me`)).toBeVisible({ timeout: 10_000 });
  });

  test("Reject topic moves card to Rejected column", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Reject me` });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await actionCard.getByRole("button", { name: "Reject" }).click();

    await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

    const rejectedCol = page.getByTestId("kanban-col-TOPIC_REJECTED");
    await expect(rejectedCol.getByText(`[${uid}] Reject me`)).toBeVisible({ timeout: 10_000 });
  });

  test("Revise video (mandatory comment via modal) moves card to Revision Requested column (not Rejected)", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Revise me` });
    await patchVideo(video.id, { status: "VIDEO_READY" });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    // Revise never fires immediately — a revision requires a comment, so it opens
    // the modal straight into the Request Revision dialog.
    await actionCard.getByRole("button", { name: "Revise" }).click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await page.getByPlaceholder("Describe what needs to change...").fill("Audio is too quiet");
    await page.getByRole("button", { name: "Send Revision Request" }).click();

    await expect(modal).not.toBeVisible({ timeout: 5_000 });
    await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

    // Must appear in the "Revision Requested" column, NOT the "Rejected" column
    const revisionCol = page.getByTestId("kanban-col-REVISION_REQUESTED");
    await expect(revisionCol.getByText(`[${uid}] Revise me`)).toBeVisible({ timeout: 10_000 });
    const rejectedCol = page.getByTestId("kanban-col-TOPIC_REJECTED");
    await expect(rejectedCol.getByText(`[${uid}] Revise me`)).not.toBeVisible();
  });

  test("Request Revision on a proposed topic (mandatory comment) moves card to Revision Requested, not Rejected", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Revise topic` });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await actionCard.getByRole("button", { name: "Revise" }).click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    // Revise lands straight in the Request Revision dialog — distinct from a flat
    // Reject, which needs no comment.
    await page.getByPlaceholder("Describe what needs to change...").fill("Needs a sharper hook");
    await page.getByRole("button", { name: "Send Revision Request" }).click();

    await expect(modal).not.toBeVisible({ timeout: 5_000 });
    await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

    const revisionCol = page.getByTestId("kanban-col-REVISION_REQUESTED");
    await expect(revisionCol.getByText(`[${uid}] Revise topic`)).toBeVisible({ timeout: 10_000 });
    const rejectedCol = page.getByTestId("kanban-col-TOPIC_REJECTED");
    await expect(rejectedCol.getByText(`[${uid}] Revise topic`)).not.toBeVisible();
  });

  test("SCRIPT_READY card in ActionPane shows Read + Approve + Revise buttons", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Script ready` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test script" });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await expect(actionCard.getByRole("button", { name: "Read" })).toBeVisible();
    await expect(actionCard.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(actionCard.getByRole("button", { name: "Revise" })).toBeVisible();
  });

  test("Approve script transitions card to VOICING column", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Script approve` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test" });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await actionCard.getByRole("button", { name: "Approve" }).click();

    await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

    const voicingCol = page.getByTestId("kanban-col-VOICING");
    await expect(voicingCol.getByText(`[${uid}] Script approve`)).toBeVisible({ timeout: 10_000 });
  });

  test.describe("SCRIPT_READY voice picker (TMDEV-51)", () => {
    test.afterEach(async () => {
      // Scoped to this block — other tests in this file assume an empty
      // roster (no picker rendered), so restore that before they run.
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    });

    test("selecting a non-default voice and approving persists it on the video", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [
          { name: "Narrator", voice_id: `${uid}-narrator`, model_id: "eleven_multilingual_v2" },
          { name: "Energetic", voice_id: `${uid}-energetic`, model_id: "eleven_multilingual_v2" },
        ],
        elevenlabs_voice_id: `${uid}-narrator`,
      });
      const video = await createVideo({ topic: `[${uid}] Script voice pick` });
      await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test" });

      await page.goto("/");

      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });

      const voiceSelect = actionCard.getByTestId(`voice-select-${video.id}`);
      await expect(voiceSelect).toBeVisible();
      await expect(voiceSelect).toHaveValue(`${uid}-narrator`); // pre-selected to the default

      await voiceSelect.selectOption(`${uid}-energetic`);
      await actionCard.getByRole("button", { name: "Approve" }).click();

      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

      const updated = await getVideo(video.id);
      expect(updated.status).toBe("VOICING");
      expect(updated.voice_id).toBe(`${uid}-energetic`);
    });

    test("approving without changing the selection uses the pre-selected default voice", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [{ name: "Narrator", voice_id: `${uid}-solo`, model_id: "eleven_multilingual_v2" }],
        elevenlabs_voice_id: `${uid}-solo`,
      });
      const video = await createVideo({ topic: `[${uid}] Script voice default` });
      await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test" });

      await page.goto("/");

      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      await actionCard.getByRole("button", { name: "Approve" }).click();

      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

      const updated = await getVideo(video.id);
      expect(updated.voice_id).toBe(`${uid}-solo`);
    });

    // TMDEV-121: the model follows the voice, and a script's markup follows the model.
    test("a voice that cannot speak the script is disabled, and the API refuses it", async ({ page }) => {
      await setSettings({
        elevenlabs_voices: [
          { name: "Narrator", voice_id: `${uid}-v2`, model_id: "eleven_multilingual_v2" },
          { name: "Adam", voice_id: `${uid}-v3`, model_id: "eleven_v3" },
        ],
        elevenlabs_voice_id: `${uid}-v2`,
      });
      const video = await createVideo({ topic: `[${uid}] Script IPA voice` });
      await patchVideo(video.id, {
        status: "SCRIPT_READY", voice_id: `${uid}-v3`,
        script: 'Say <ipa ph="ˈmædɪsən">Madison</ipa> now.',
      });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      const voiceSelect = actionCard.getByTestId(`voice-select-${video.id}`);
      await expect(voiceSelect).toHaveValue(`${uid}-v3`);
      // Playwright's toBeDisabled() reports a disabled <option> as enabled.
      await expect(voiceSelect.locator(`option[value="${uid}-v2"]`)).toHaveJSProperty("disabled", true);
      await expect(voiceSelect.locator(`option[value="${uid}-v3"]`)).toHaveJSProperty("disabled", false);

      const refused = await fetch(`${BASE}/videos/${video.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json", ...API_AUTH },
        body: JSON.stringify({ voice_id: `${uid}-v2` }),
      });
      expect(refused.status).toBe(409);

      // The negative control: approving with its own voice goes through.
      await actionCard.getByRole("button", { name: "Approve" }).click();
      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });
      const updated = await getVideo(video.id);
      expect(updated.status).toBe("VOICING");
      expect(updated.voice_id).toBe(`${uid}-v3`);
    });

    test("no voice select renders when the roster is empty", async ({ page }) => {
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
      const video = await createVideo({ topic: `[${uid}] Script no roster` });
      await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test" });

      await page.goto("/");

      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      await expect(actionCard.getByTestId(`voice-select-${video.id}`)).toHaveCount(0);
    });
  });

  // TMDEV-127: a script is written for its voice's model, so a voice on another
  // model is picked before the script exists.
  test.describe("TOPIC_PROPOSED voice picker", () => {
    test.afterEach(async () => {
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    });

    const roster = (uid: string) => ({
      elevenlabs_voices: [
        { name: "Narrator", voice_id: `${uid}-v2`, model_id: "eleven_multilingual_v2" },
        { name: "Adam", voice_id: `${uid}-v3`, model_id: "eleven_v3" },
      ],
      elevenlabs_voice_id: `${uid}-v2`,
    });

    test("picking a voice on another model and approving puts it on the video", async ({ page }) => {
      await setSettings(roster(uid));
      const video = await createVideo({ topic: `[${uid}] Topic voice pick` });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      const voiceSelect = actionCard.getByTestId(`voice-select-${video.id}`);
      await expect(voiceSelect).toHaveValue(`${uid}-v2`);
      await expect(voiceSelect.locator("option", { hasText: "Adam · eleven_v3" })).toHaveCount(1);

      await voiceSelect.selectOption(`${uid}-v3`);
      await actionCard.getByRole("button", { name: "Approve" }).click();
      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

      const updated = await getVideo(video.id);
      expect(updated.status).toBe("TOPIC_APPROVED");
      expect(updated.voice_id).toBe(`${uid}-v3`);
    });

    test("an untouched picker keeps the project's voice — never the install default", async ({ page }) => {
      await setSettings(roster(uid));
      const proj = await createProject({ name: `Voice proj ${uid}`, id: `voice-proj-${uid}`,
                                         default_voice_id: `${uid}-v3` });
      const video = await createVideo({ topic: `[${uid}] Topic voice seeded`,
                                        project_id: proj.id as string });
      expect(video.voice_id).toBe(`${uid}-v3`);

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      await expect(actionCard.getByTestId(`voice-select-${video.id}`)).toHaveValue(`${uid}-v3`);
      await actionCard.getByRole("button", { name: "Approve" }).click();
      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

      const updated = await getVideo(video.id);
      expect(updated.status).toBe("TOPIC_APPROVED");
      expect(updated.voice_id).toBe(`${uid}-v3`);
    });

    test("an old script left by a topic revision blocks no voice", async ({ page }) => {
      await setSettings(roster(uid));
      const video = await createVideo({ topic: `[${uid}] Topic stale script` });
      await patchVideo(video.id, { voice_id: `${uid}-v2`, script: 'A <break time="0.5s" /> B.' });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      const voiceSelect = actionCard.getByTestId(`voice-select-${video.id}`);
      // Playwright's toBeDisabled() reports a disabled <option> as enabled.
      await expect(voiceSelect.locator(`option[value="${uid}-v3"]`)).toHaveJSProperty("disabled", false);
      await voiceSelect.selectOption(`${uid}-v3`);
      await actionCard.getByRole("button", { name: "Approve" }).click();
      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });
      expect((await getVideo(video.id)).voice_id).toBe(`${uid}-v3`);
    });

    // The row does not wrap, and the voice picker is the widest thing added to
    // it — assert geometry, since a button pushed off-screen is still "visible".
    test("the row's buttons stay on screen at 1280px", async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await setSettings({
        elevenlabs_voices: [{ name: "A voice with a rather long display name",
                              voice_id: `${uid}-long`, model_id: "eleven_multilingual_v2" }],
        elevenlabs_voice_id: `${uid}-long`,
      });
      const video = await createVideo({ topic: `[${uid}] Topic row width` });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      await expect(actionCard.getByTestId(`voice-select-${video.id}`)).toBeVisible();
      for (const name of ["Approve", "Reject", "Revise"]) {
        const box = await actionCard.getByRole("button", { name }).boundingBox();
        expect(box!.x + box!.width).toBeLessThanOrEqual(1280);
      }
      // The title keeps its room: without a floor on its column, the controls
      // took their full width and crushed it to nothing.
      const title = await actionCard.getByTitle("Click to open").boundingBox();
      expect(title!.width).toBeGreaterThanOrEqual(200);
    });
  });

  test("VIDEO_READY card in ActionPane shows Watch + Approve + Revise buttons", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Video ready` });
    await patchVideo(video.id, { status: "VIDEO_READY" });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await expect(actionCard.getByRole("button", { name: "Watch" })).toBeVisible();
    await expect(actionCard.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(actionCard.getByRole("button", { name: "Revise" })).toBeVisible();
    // Approving is not publishing. Publishing is human-only and starts from
    // VIDEO_APPROVED, so no board action may offer it here -- this button used
    // to be labelled Publish, which implied the approval also shipped the video.
    await expect(actionCard.getByRole("button", { name: "Publish" })).toHaveCount(0);
  });

  test("Approve transitions VIDEO_READY card to VIDEO_APPROVED column", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Approve video` });
    await patchVideo(video.id, { status: "VIDEO_READY" });

    await page.goto("/");

    const actionCard = page.getByTestId(`action-card-${video.id}`);
    await expect(actionCard).toBeVisible({ timeout: 10_000 });
    await actionCard.getByRole("button", { name: "Approve" }).click();

    await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

    const approvedCol = page.getByTestId("kanban-col-VIDEO_APPROVED");
    await expect(approvedCol.getByText(`[${uid}] Approve video`)).toBeVisible({ timeout: 10_000 });
  });

  test("ActionPane groups by status and a status pill hides its cards across a poll", async ({ page }) => {
    const ready = await createVideo({ topic: `[${uid}] Filter ready` });
    await patchVideo(ready.id, { status: "VIDEO_READY" });
    const topic = await createVideo({ topic: `[${uid}] Filter topic` });

    await page.goto("/");
    const topicCard = page.getByTestId(`action-card-${topic.id}`);
    const readyCard = page.getByTestId(`action-card-${ready.id}`);
    await expect(readyCard).toBeVisible({ timeout: 10_000 });
    await expect(topicCard).toBeVisible();
    // Pipeline order, though the VIDEO_READY video is the older of the two.
    await expect(page.getByTestId("action-group-TOPIC_PROPOSED").locator("..").getByTestId(`action-card-${topic.id}`)).toHaveCount(1);
    expect((await topicCard.boundingBox())!.y).toBeLessThan((await readyCard.boundingBox())!.y);

    const pill = page.getByTestId("action-filter-VIDEO_READY");
    await pill.click();
    await expect(pill).toHaveAttribute("aria-pressed", "false");
    await expect(readyCard).toHaveCount(0);
    await expect(topicCard).toBeVisible();

    // The page refetches the inbox on a timer; the filter must survive it.
    await page.waitForResponse((r) => r.url().includes("/videos/actionable"), { timeout: 15_000 });
    await expect(readyCard).toHaveCount(0);

    await pill.click();
    await expect(readyCard).toBeVisible();
  });

  test("new video created via API appears on board within 10s (polling)", async ({ page }) => {
    await page.goto("/");
    // Wait for board to be stable
    await page.getByTestId("kanban-col-TOPIC_PROPOSED").waitFor();

    // Create video AFTER page load to test polling
    const video = await createVideo({ topic: `[${uid}] Late arrival` });

    // Should appear without manual refresh within 10s (board polls every 5s)
    const proposedCol = page.getByTestId("kanban-col-TOPIC_PROPOSED");
    await expect(proposedCol.getByText(`[${uid}] Late arrival`)).toBeVisible({ timeout: 12_000 });
    void video;
  });
  test.describe("visual style picker", () => {
    test("selecting a register and approving persists it, and it is then frozen", async ({ page }) => {
      const video = await createVideo({ topic: `[${uid}] Stick register pick` });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });

      const styleSelect = actionCard.getByTestId(`style-select-${video.id}`);
      await expect(styleSelect).toHaveValue("auto");
      await styleSelect.selectOption("stick");

      await actionCard.getByRole("button", { name: "Approve" }).click();
      await expect(actionCard).not.toBeVisible({ timeout: 5_000 });

      // Verified through the API, not the DOM: the point is that the choice
      // travelled in the same atomic request as the status change.
      const updated = await getVideo(video.id);
      expect(updated.status).toBe("TOPIC_APPROVED");
      expect(updated.visual_style).toBe("stick");

      // And is refused afterwards, by the server rather than by the UI.
      const res = await fetch(`${BASE}/videos/${video.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...API_AUTH },
        body: JSON.stringify({ visual_style: "motion_graphics" }),
      });
      expect(res.status).toBe(409);
      expect((await getVideo(video.id)).visual_style).toBe("stick");
    });

    test("Illustrated is disabled and refused with no OpenAI key, and offered once one is stored", async ({ page }) => {
      // The test stack supplies no OpenAI key, so this starts in the no-key
      // state an install without one is in. Cleared explicitly anyway, and
      // restored in finally, so no later spec inherits a key.
      await setSettings({ openai_api_key: "" });
      try {
        const video = await createVideo({ topic: `[${uid}] Illustrated needs a key` });

        await page.goto("/");
        const actionCard = page.getByTestId(`action-card-${video.id}`);
        await expect(actionCard).toBeVisible({ timeout: 10_000 });
        const illustrated = actionCard.getByTestId(`style-select-${video.id}`)
          .locator('option[value="illustrated"]');
        // The DOM property, not toBeDisabled(): Playwright reports a disabled
        // <option> inside an enabled <select> as enabled.
        await expect(illustrated).toHaveJSProperty("disabled", true);
        await expect(illustrated).toContainText("needs an OpenAI key");

        // The server refuses it too — the dashboard is not the only caller.
        const res = await fetch(`${BASE}/videos/${video.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...API_AUTH },
          body: JSON.stringify({ visual_style: "illustrated" }),
        });
        expect(res.status).toBe(400);
        expect((await res.json()).error).toContain("OpenAI API key not set");

        await setSettings({ openai_api_key: "sk-e2e-test" });
        await page.reload();
        await expect(page.getByTestId(`action-card-${video.id}`)
          .getByTestId(`style-select-${video.id}`)
          .locator('option[value="illustrated"]')).toHaveJSProperty("disabled", false, { timeout: 10_000 });
      } finally {
        await setSettings({ openai_api_key: "" });
      }
    });

    test("the frozen register is shown read-only once the picker is gone", async ({ page }) => {
      const video = await createVideo({
        topic: `[${uid}] Frozen register`,
        visual_style: "stick",
      });
      // SCRIPT_READY, not TOPIC_APPROVED: the action pane only lists videos at
      // a human checkpoint, so at TOPIC_APPROVED no card renders at all and an
      // assertion about it would pass even with the feature removed.
      await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test" });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });

      await expect(actionCard.getByTestId(`style-select-${video.id}`)).toHaveCount(0);
      await expect(page.getByTestId(`choices-${video.id}`)).toContainText("Stick Explainer");
    });

    test("Auto does not imply a register before one has been chosen", async ({ page }) => {
      // resolved_visual_style is written only by the agent, so the far side of
      // this — "Stick Explainer (auto)" — is covered by the unit tests. What
      // matters here is that the board says nothing misleading in the gap.
      const video = await createVideo({ topic: `[${uid}] Auto register` });
      await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Test" });

      await page.goto("/");
      const actionCard = page.getByTestId(`action-card-${video.id}`);
      await expect(actionCard).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId(`choices-${video.id}`)).toContainText("not yet chosen");
    });
  });
});
