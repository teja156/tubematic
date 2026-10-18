import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e/specs",
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  workers: 1,
  retries: 1,
  timeout: 30_000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3001",
    browserName: "chromium",
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // Deliberately neither UTC nor the test API's TZ (America/New_York, set in
    // docker-compose.test.yml) — an assertion that only passes when the browser
    // and the API happen to agree proves the dashboard used the API-served
    // zone, not the browser's own.
    timezoneId: "Asia/Tokyo",
    // Signed in (TMDEV-152): written by global-setup.ts after it logs in.
    storageState: "./tests/e2e/.auth/state.json",
  },
});
