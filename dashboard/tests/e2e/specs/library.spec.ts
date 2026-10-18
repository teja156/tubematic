import { test, expect } from "@playwright/test";
import { createVideo, patchVideo } from "../fixtures/seed";

test.describe("Library page", () => {
  let uid: string;

  test.beforeEach(() => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("only library-eligible videos shown", async ({ page }) => {
    const v1 = await createVideo({ topic: `[${uid}] Published video` });
    await patchVideo(v1.id, { status: "PUBLISHED" });
    await createVideo({ topic: `[${uid}] Topic proposed video` });
    // second video stays TOPIC_PROPOSED — not library-eligible

    await page.goto("/library");
    await page.getByRole("button", { name: /Published/ }).click();
    await page.waitForTimeout(500);

    await expect(page.getByText(`[${uid}] Published video`)).toBeVisible();
    await expect(page.getByText(`[${uid}] Topic proposed video`)).not.toBeVisible();
  });

  test("strategy filter narrows results", async ({ page }) => {
    const v1 = await createVideo({ topic: `[${uid}] Curriculum video`, strategy: "curriculum" });
    await patchVideo(v1.id, { status: "PUBLISHED" });
    const v2 = await createVideo({ topic: `[${uid}] Trending video`, strategy: "trending" });
    await patchVideo(v2.id, { status: "PUBLISHED" });

    await page.goto("/library");
    await page.getByRole("button", { name: /Published/ }).click();
    await page.waitForTimeout(500);

    await page.getByTestId("strategy-select").selectOption("Curriculum");
    await page.waitForTimeout(300);

    await expect(page.getByText(`[${uid}] Curriculum video`)).toBeVisible();
    await expect(page.getByText(`[${uid}] Trending video`)).not.toBeVisible();
  });

  test("text search filters by topic", async ({ page }) => {
    const v1 = await createVideo({ topic: `[${uid}] Alpha topic` });
    await patchVideo(v1.id, { status: "PUBLISHED" });
    const v2 = await createVideo({ topic: `[${uid}] Beta topic` });
    await patchVideo(v2.id, { status: "PUBLISHED" });

    await page.goto("/library");
    await page.getByRole("button", { name: /Published/ }).click();
    await page.waitForTimeout(500);

    await page.getByTestId("search-input").fill(`Alpha`);
    await page.waitForTimeout(300);

    await expect(page.getByText(`[${uid}] Alpha topic`)).toBeVisible();
    await expect(page.getByText(`[${uid}] Beta topic`)).not.toBeVisible();
  });

  test("Highest Score sort orders correctly", async ({ page }) => {
    const v1 = await createVideo({ topic: `[${uid}] Score 3 video`, producibility_score: 3 });
    await patchVideo(v1.id, { status: "PUBLISHED" });
    const v2 = await createVideo({ topic: `[${uid}] Score 8 video`, producibility_score: 8 });
    await patchVideo(v2.id, { status: "PUBLISHED" });

    await page.goto("/library");
    await page.getByRole("button", { name: /Published/ }).click();
    await page.waitForTimeout(500);

    await page.getByTestId("sort-select").selectOption("Highest Score");
    await page.waitForTimeout(300);

    // The score-8 video must appear before score-3 in the grid
    const scoreEight = page.getByText(`[${uid}] Score 8 video`);
    const scoreThree = page.getByText(`[${uid}] Score 3 video`);
    await expect(scoreEight).toBeVisible();
    await expect(scoreThree).toBeVisible();

    const eightBox = await scoreEight.boundingBox();
    const threeBox = await scoreThree.boundingBox();
    expect(eightBox!.y).toBeLessThan(threeBox!.y);
  });
});
