import { test, expect } from "@playwright/test";
import { createVideo, deleteVideo, patchVideo } from "../fixtures/seed";

// Video retention / manual delete (TMDEV-84): a deleted video leaves the board
// and the Library, and shows up in the Archive with its record intact.
test.describe("Archive", () => {
  let uid: string;

  test.beforeEach(() => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("a deleted video moves from the Library to the Archive", async ({ page }) => {
    const v = await createVideo({ topic: `[${uid}] Deleted video` });
    await patchVideo(v.id, { status: "PUBLISHED" });
    await deleteVideo(v.id);

    await page.goto("/library");
    await page.getByRole("button", { name: /Published/ }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText(`[${uid}] Deleted video`)).not.toBeVisible();

    await page.getByTestId("nav-archive").click();
    await expect(page.getByTestId(`archive-row-${v.id}`)).toBeVisible();
    await expect(page.getByTestId(`archive-row-${v.id}`)).toContainText(`[${uid}] Deleted video`);
  });

  test("deleting from the modal archives the video", async ({ page }) => {
    const v = await createVideo({ topic: `[${uid}] Modal delete` });
    await patchVideo(v.id, { status: "VIDEO_READY" });

    await page.goto("/library");
    await page.getByText(`[${uid}] Modal delete`).click();
    await page.getByRole("button", { name: "Delete Video" }).click();
    await page.getByTestId("delete-dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await page.waitForTimeout(500);

    await page.goto("/archive");
    await expect(page.getByTestId(`archive-row-${v.id}`)).toBeVisible();
  });

  test("an archived video opens read-only, with no actions", async ({ page }) => {
    const v = await createVideo({ topic: `[${uid}] Read only` });
    await patchVideo(v.id, { status: "VIDEO_READY" });
    await deleteVideo(v.id);

    await page.goto("/archive");
    await page.getByTestId(`archive-row-${v.id}`).click();
    await expect(page.getByTestId("archived-badge")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve Video" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Delete Video" })).toHaveCount(0);
  });
});
