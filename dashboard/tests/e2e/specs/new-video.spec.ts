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

  test("a formula picked on the form is the video's formula choice", async ({ page }) => {
    await page.goto("/new-video");
    const title = `[${uid}] Formula submission`;
    await page.getByTestId("new-video-title").fill(title);
    await page.getByTestId("new-video-topic").fill(`${title}: the full brief, several sentences long.`);
    const formula = page.getByTestId("new-video-formula");
    await expect(formula).toHaveValue("");
    await expect(formula.locator("option", { hasText: "Incident File" })).toHaveCount(1);
    await formula.selectOption("incident-file");
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith("/videos/manual") && r.request().method() === "POST"),
      page.getByTestId("new-video-submit").click(),
    ]);
    expect(response.status()).toBe(201);
    const video = await getVideo((await response.json()).id) as unknown as Record<string, unknown>;
    expect(video.formula_choice).toBe("incident-file");
  });

  test("unchecking auto-approve lands it at Topic Proposed", async ({ page }) => {
    const id = await submit(page, `[${uid}] Proposed submission`, false);
    expect((await getVideo(id)).status).toBe("TOPIC_PROPOSED");
  });

  test("a submission needs no angle, and keeps one it is given", async ({ page }) => {
    const plain = await getVideo(await submit(page, `[${uid}] No angle`, false)) as unknown as Record<string, unknown>;
    expect(plain.angle).toBe("");
    expect(plain.angle_kind).toBe("");

    await page.goto("/new-video");
    await page.getByTestId("new-video-title").fill(`[${uid}] With an angle`);
    await page.getByTestId("new-video-topic").fill("How a backup job can succeed and save nothing.");
    await page.getByTestId("new-video-angle").fill("The backup reported success for a year while it copied an empty folder.");
    // A sentence needs its kind before the form will go.
    await expect(page.getByTestId("new-video-submit")).toBeDisabled();
    await page.getByTestId("new-video-angle-kind").selectOption("anomaly");
    await page.getByTestId("new-video-approve").uncheck();
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith("/videos/manual") && r.request().method() === "POST"),
      page.getByTestId("new-video-submit").click(),
    ]);
    expect(response.status()).toBe(201);
    const withAngle = await getVideo((await response.json()).id) as unknown as Record<string, unknown>;
    expect(withAngle.angle).toBe("The backup reported success for a year while it copied an empty folder.");
    expect(withAngle.angle_kind).toBe("anomaly");
    // A person's own angle is unscored.
    expect(withAngle.angle_score).toBe(0);
  });

  test("a title over 70 characters cannot be submitted", async ({ page }) => {
    await page.goto("/new-video");
    await page.getByTestId("new-video-title").fill("x".repeat(71));
    await page.getByTestId("new-video-topic").fill("A brief");
    await expect(page.getByTestId("new-video-submit")).toBeDisabled();
  });
});
