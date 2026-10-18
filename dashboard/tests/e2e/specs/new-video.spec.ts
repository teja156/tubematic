import { test, expect, type Page } from "@playwright/test";
import { getVideo } from "../fixtures/seed";

// The New Video page end to end (TMDEV-118): the form, the real
// POST /videos/manual, and the video showing on the Pipeline. The test stack
// has no agents installed, so the agent picker stays on Automatic — the path
// a submission takes when nobody picks an agent.

async function submit(page: Page, title: string, approve: boolean): Promise<string> {
  await page.goto("/new-video");
  await page.getByTestId("new-video-title").fill(title);
  await page.getByTestId("new-video-topic").fill(`${title}: the full brief, several sentences long.`);
  if (!approve) await page.getByTestId("new-video-approve").uncheck();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/videos/manual") && r.request().method() === "POST"),
    page.getByTestId("new-video-submit").click(),
  ]);
  expect(response.status()).toBe(201);
  await expect(page.getByTestId("new-video-success")).toBeVisible();
  return (await response.json()).id as string;
}

test.describe("New Video page", () => {
  let uid: string;

  test.beforeEach(() => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("a submission lands at Topic Approved, unscored, in Manual Videos", async ({ page }) => {
    const id = await submit(page, `[${uid}] Approved submission`, true);

    const video = await getVideo(id);
    expect(video.status).toBe("TOPIC_APPROVED");
    expect(video.project_id).toBe("manual");
    expect(video.strategy).toBe("manual");

    await page.goto("/");
    const card = page.getByTestId("kanban-col-TOPIC_APPROVED").getByTestId(`kanban-card-${id}`);
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText("—");
    await expect(card).not.toContainText("0/10");
  });

  test("unchecking auto-approve lands it at Topic Proposed", async ({ page }) => {
    const id = await submit(page, `[${uid}] Proposed submission`, false);
    expect((await getVideo(id)).status).toBe("TOPIC_PROPOSED");
  });

  test("a title over 70 characters cannot be submitted", async ({ page }) => {
    await page.goto("/new-video");
    await page.getByTestId("new-video-title").fill("x".repeat(71));
    await page.getByTestId("new-video-topic").fill("A brief");
    await expect(page.getByTestId("new-video-submit")).toBeDisabled();
  });
});
