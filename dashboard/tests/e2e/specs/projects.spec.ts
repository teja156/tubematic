import { test, expect } from "@playwright/test";
import { createProject, createVideo, getVideo, setSettings } from "../fixtures/seed";

test.describe("Projects page", () => {
  let uid: string;

  test.beforeEach(async () => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("seeded project appears in the project list", async ({ page }) => {
    const proj = await createProject({ name: `Test Project ${uid}`, id: `test-proj-${uid}` });
    const projId = proj.id as string;

    await page.goto("/projects");
    await expect(page.getByTestId(`project-row-${projId}`)).toBeVisible({ timeout: 10_000 });
  });

  test("clicking a project shows its videos", async ({ page }) => {
    const proj = await createProject({ name: `Video Project ${uid}`, id: `vid-proj-${uid}` });
    const projId = proj.id as string;
    const video = await createVideo({
      topic: `Test video topic ${uid}`,
      strategy: "curriculum",
      status: "TOPIC_PROPOSED",
      project_id: projId,
    });

    await page.goto("/projects");
    await expect(page.getByTestId(`project-row-${projId}`)).toBeVisible({ timeout: 10_000 });
    await page.getByTestId(`project-row-${projId}`).click();

    await expect(page.getByTestId(`project-video-${video.id}`)).toBeVisible({ timeout: 10_000 });
  });

  // toBeVisible() cannot see a collapsed column — a card squeezed to 160px
  // with its badge over its title is still "visible". The layout is the
  // feature here, so assert geometry. The description must be long: without
  // one the 340px column never inflates and the page cannot show the bug.
  // The name is one unbroken token (underscores — a hyphen is a line-break
  // opportunity): once the column holds its width, such a name must wrap
  // inside the row rather than paint over the count and the video pane.
  test("a long project description does not crush the video pane", async ({ page }) => {
    const name = `long_project_name_with_no_break_opportunity_${uid}_`.repeat(2);
    const proj = await createProject({
      name,
      id: `long-proj-${uid}`,
      description:
        "History from inside one unnamed life — a Roman legionary's day on the frontier, " +
        "a Chernobyl night-shift operator, a Pompeii household on the last morning.",
    });
    const projId = proj.id as string;
    const video = await createVideo({
      topic: `Long description video ${uid}`,
      strategy: "curriculum",
      status: "TOPIC_PROPOSED",
      project_id: projId,
    });

    await page.goto("/projects");
    await page.getByTestId(`project-row-${projId}`).click();
    await expect(page.getByTestId(`project-video-${video.id}`)).toBeVisible({ timeout: 10_000 });

    const row = await page.getByTestId(`project-row-${projId}`).boundingBox();
    const card = await page.getByTestId(`project-video-${video.id}`).boundingBox();
    const title = await page.getByTestId(`project-row-${projId}`)
      .getByText(name, { exact: true }).boundingBox();
    expect(row!.width).toBeLessThanOrEqual(360);
    expect(card!.width).toBeGreaterThan(400);
    expect(title!.x + title!.width).toBeLessThanOrEqual(row!.x + row!.width);
  });

  test("clicking a video opens the VideoModal", async ({ page }) => {
    const proj = await createProject({ name: `Modal Project ${uid}`, id: `modal-proj-${uid}` });
    const projId = proj.id as string;
    const video = await createVideo({
      topic: `Modal test video ${uid}`,
      strategy: "curriculum",
      status: "TOPIC_PROPOSED",
      project_id: projId,
    });

    await page.goto("/projects");
    await expect(page.getByTestId(`project-row-${projId}`)).toBeVisible({ timeout: 10_000 });
    await page.getByTestId(`project-row-${projId}`).click();
    await expect(page.getByTestId(`project-video-${video.id}`)).toBeVisible({ timeout: 10_000 });
    await page.getByTestId(`project-video-${video.id}`).click();

    // VideoModal should open
    await expect(page.getByTestId("video-modal")).toBeVisible({ timeout: 10_000 });
  });
  // TMDEV-127: the modal opened from a project gets the voice roster too, so a
  // voice on another model can be picked at the topic checkpoint from here.
  test("the video modal offers a voice at TOPIC_PROPOSED and approves with it", async ({ page }) => {
    await setSettings({
      elevenlabs_voices: [
        { name: "Narrator", voice_id: `${uid}-v2`, model_id: "eleven_multilingual_v2" },
        { name: "Adam", voice_id: `${uid}-v3`, model_id: "eleven_v3" },
      ],
      elevenlabs_voice_id: `${uid}-v2`,
    });
    try {
      const proj = await createProject({ name: `Voice modal ${uid}`, id: `voice-modal-${uid}` });
      const projId = proj.id as string;
      const video = await createVideo({ topic: `Voice modal topic ${uid}`, project_id: projId });

      await page.goto("/projects");
      await page.getByTestId(`project-row-${projId}`).click();
      await page.getByTestId(`project-video-${video.id}`).click();
      const modal = page.getByTestId("video-modal");
      await expect(modal).toBeVisible();
      const voiceSelect = modal.getByTestId("video-modal-voice-select");
      await expect(voiceSelect).toHaveValue(`${uid}-v2`);
      await voiceSelect.selectOption(`${uid}-v3`);
      await modal.getByRole("button", { name: "Approve Topic" }).click();
      await expect(modal).not.toBeVisible({ timeout: 5_000 });

      await expect.poll(async () => (await getVideo(video.id)).status).toBe("TOPIC_APPROVED");
      expect((await getVideo(video.id)).voice_id).toBe(`${uid}-v3`);
    } finally {
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    }
  });
});
