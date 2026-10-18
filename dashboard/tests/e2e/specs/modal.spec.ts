import { test, expect } from "@playwright/test";
import { createVideo, patchVideo, addComment, getVideo, reportAgentOutcome, setSettings } from "../fixtures/seed";

test.describe("VideoModal", () => {
  let uid: string;

  test.beforeEach(() => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("clicking a Kanban card opens the modal with matching title", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Modal test video` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    // The heading, specifically. The topic now renders twice in the modal --
    // once here (the header falls back to `title || topic`, and a seeded video
    // has no short title) and once in the Topic tab's body -- so a plain
    // getByText is ambiguous and fails Playwright's strict mode.
    await expect(
      modal.getByRole("heading", { name: `[${uid}] Modal test video` }),
    ).toBeVisible();
  });

  test("Script tab hidden when script is empty", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] No script video` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("tab", { name: /Script/ })).not.toBeVisible();
  });

  test("Script tab visible when script has content", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Has script` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Hello world" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("tab", { name: /Script/ })).toBeVisible();
  });

  test("Comments tab always present", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Comments tab test` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("tab", { name: /Comments/ })).toBeVisible();
  });

  test("Comments tab is read-only — no compose box", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Read-only comments` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("tab", { name: /Comments/ }).click();

    await expect(modal.getByTestId("comments-readonly-note")).toBeVisible();
    await expect(modal.locator("textarea")).toHaveCount(0);
    await expect(modal.getByRole("button", { name: "Send" })).toHaveCount(0);
  });

  test("a revision comment appears in the Comments thread", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Revision comment thread` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Script content" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    const commentText = `Revision note [${uid}]`;
    await modal.getByRole("button", { name: "Request Revision" }).click();
    await page.getByPlaceholder("Describe what needs to change...").fill(commentText);
    await page.getByRole("button", { name: "Send Revision Request" }).click();
    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    // Reopen from the Revision Requested column and read the thread.
    const reopened = page.getByTestId("kanban-col-REVISION_REQUESTED").getByTestId(`kanban-card-${video.id}`);
    await expect(reopened).toBeVisible({ timeout: 10_000 });
    await reopened.click();
    await modal.getByRole("tab", { name: /Comments/ }).click();
    await expect(modal.getByText(commentText)).toBeVisible({ timeout: 5_000 });
  });

  test("comment survives modal close and reopen", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Comment persist test` });
    await addComment(video.id, { author: "human", content: `Seeded comment [${uid}]` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("tab", { name: /Comments/ }).click();
    await expect(modal.getByText(`Seeded comment [${uid}]`)).toBeVisible({ timeout: 5_000 });

    // Close modal (press Escape)
    await page.keyboard.press("Escape");
    await expect(modal).not.toBeVisible();

    // Reopen
    await card.click();
    await expect(modal).toBeVisible();
    await modal.getByRole("tab", { name: /Comments/ }).click();
    await expect(modal.getByText(`Seeded comment [${uid}]`)).toBeVisible({ timeout: 5_000 });
  });

  test("Approve Topic in modal triggers status transition and closes modal", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Approve via modal` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Approve Topic" }).click();

    // Modal should close
    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    // Card should appear in TOPIC_APPROVED column after polling
    const approvedCol = page.getByTestId("kanban-col-TOPIC_APPROVED");
    await expect(approvedCol.getByText(`[${uid}] Approve via modal`)).toBeVisible({ timeout: 10_000 });
  });

  test("Revise button opens ReviseDialog for SCRIPT_READY video", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Revise test` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Script content" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Request Revision" }).click();

    // ReviseDialog textarea should appear
    await expect(page.getByPlaceholder("Describe what needs to change...")).toBeVisible();
  });

  test("Submitting a SCRIPT_READY revision actually moves the video to REVISION_REQUESTED", async ({ page }) => {
    // Regression test for a bug found during the TMDEV-1 audit: this dialog used to
    // post the comment but never change status, silently stranding the video at
    // SCRIPT_READY forever.
    const video = await createVideo({ topic: `[${uid}] Revise script for real` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Script content" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Request Revision" }).click();
    await page.getByPlaceholder("Describe what needs to change...").fill("Rewrite the opening line");
    await page.getByRole("button", { name: "Send Revision Request" }).click();

    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    const revisionCol = page.getByTestId("kanban-col-REVISION_REQUESTED");
    await expect(revisionCol.getByText(`[${uid}] Revise script for real`)).toBeVisible({ timeout: 10_000 });
    const scriptReadyCol = page.getByTestId("kanban-col-SCRIPT_READY");
    await expect(scriptReadyCol.getByText(`[${uid}] Revise script for real`)).not.toBeVisible();
  });

  test("a stuck video shows STUCK on its card, and Retry agent hands it back", async ({ page }) => {
    // TMDEV-129: three poller sessions in a row that leave the video where
    // they found it flag it stuck. Driven through the real API route the
    // poller calls, so the dashboard reads the flag exactly as it would live.
    const video = await createVideo({ topic: `[${uid}] Stuck video` });
    await patchVideo(video.id, { status: "VOICE_READY" });
    for (let i = 0; i < 3; i++) await reportAgentOutcome(video.id, "VOICE_READY");

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId(`kanban-card-stuck-${video.id}`)).toBeVisible();
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("agent-stuck-banner")).toContainText("3 sessions in a row");
    await modal.getByRole("button", { name: "Retry agent" }).click();
    await expect(modal.getByTestId("agent-stuck-banner")).not.toBeVisible({ timeout: 5_000 });

    const after = await getVideo(video.id);
    expect(after.agent_stuck_at).toBeNull();
    expect(after.agent_no_progress_count).toBe(0);
    expect(after.status).toBe("VOICE_READY");
  });

  test("Details shows the voice and its model once the voice picker is gone", async ({ page }) => {
    // TMDEV-147: the list row the modal opens on carries no voice_info, only
    // the single-video fetch does, so this drives the real API and modal
    // together. Never voiced here, so the model is the voice's current setting.
    await setSettings({
      elevenlabs_voices: [{ name: "Narrator", voice_id: `${uid}-narrator`, model_id: "eleven_multilingual_v2" }],
      elevenlabs_voice_id: `${uid}-narrator`,
    });
    try {
      const video = await createVideo({ topic: `[${uid}] Voice details` });
      await patchVideo(video.id, { status: "VOICE_READY" });

      await page.goto("/");
      const card = page.getByTestId(`kanban-card-${video.id}`);
      await expect(card).toBeVisible({ timeout: 10_000 });
      await card.click();

      const modal = page.getByTestId("video-modal");
      await expect(modal.getByText("Voice model")).toBeVisible({ timeout: 10_000 });
      await expect(modal.getByText("Narrator", { exact: true })).toBeVisible();
      await expect(modal.getByText("eleven_multilingual_v2")).toBeVisible();
      await expect(modal.getByText("(current setting)")).toBeVisible();
    } finally {
      // Other specs assume an empty roster (no voice picker rendered).
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    }
  });
});
