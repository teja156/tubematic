import { test, expect } from "@playwright/test";
import * as path from "node:path";
import { TEST_PASSWORD } from "../fixtures/seed";

/**
 * External styles (TMDEV-253) against the real API: a zip goes through the
 * install screen, which installs only with the dashboard password, and the
 * installed style is listed, tagged and removable. The fixture is a minimal
 * valid package (ext_e2e_cards).
 */
const ZIP = path.join(__dirname, "..", "fixtures", "ext_e2e_cards.zip");

test.describe("External styles", () => {
  test("a zip is staged, refused with a wrong password, installed with the right one, then removed", async ({ page }) => {
    await page.goto("/styles");
    await expect(page.getByTestId("profiles-subnav-styles")).toHaveAttribute("aria-current", "page");
    await page.getByTestId("styles-tab-file").click();
    await page.getByTestId("zip-input").setInputFiles(ZIP);

    await page.waitForURL(/\/styles\/install\/[0-9a-f]{16}$/);
    await expect(page.getByTestId("install-warning")).toHaveAttribute("data-level", "unreviewed");
    await expect(page.getByTestId("install-check")).toContainText("passes");
    await expect(page.getByTestId("install-guide")).toBeVisible();
    // the guide's scroll box has an edge and clears the note under it (its clipped last line ran into the note)
    const guide = await page.getByTestId("install-guide").boundingBox();
    const note = await page.getByTestId("install-guide-note").boundingBox();
    expect(guide && note && guide.y + guide.height + 6 <= note.y).toBe(true);
    expect(await page.getByTestId("install-guide").evaluate((el) => getComputedStyle(el).borderTopWidth)).toBe("1px");

    await page.getByTestId("install-password").fill("not the password");
    await page.getByTestId("install-confirm").click();
    await expect(page.getByTestId("install-error")).toContainText("wrong password");

    await page.getByTestId("install-password").fill(TEST_PASSWORD);
    await page.getByTestId("install-confirm").click();
    await page.waitForURL(/\/styles$/);
    const row = page.getByTestId("installed-row").filter({ hasText: "ext_e2e_cards" });
    await expect(row).toBeVisible();
    await expect(row.getByTestId("external-badge")).toBeVisible();

    const styles = await (await page.request.get("/api/proxy/visual-styles")).json();
    expect(styles.styles.some((s: { id: string; available: boolean }) => s.id === "ext_e2e_cards" && s.available)).toBe(true);

    // the same zip again is the same bytes: the screen says identical, not "replaces"
    await page.getByTestId("styles-tab-file").click();
    await page.getByTestId("zip-input").setInputFiles(ZIP);
    await page.waitForURL(/\/styles\/install\/[0-9a-f]{16}$/);
    const replaces = page.getByTestId("install-replaces");
    await expect(replaces).toHaveAttribute("data-identical", "true");
    await expect(replaces).toContainText("identical to the installed version");
    await page.getByTestId("install-discard").click();
    await page.waitForURL(/\/styles$/);

    page.once("dialog", (d) => d.accept());
    await row.getByTestId("remove-style").click();
    await expect(page.getByTestId("installed-row").filter({ hasText: "ext_e2e_cards" })).toHaveCount(0);
  });

  test("the install screen of an unknown install says it is not waiting", async ({ page }) => {
    await page.goto("/styles/install/0123456789abcdef");
    await expect(page.getByTestId("install-load-error")).toBeVisible();
  });
});
