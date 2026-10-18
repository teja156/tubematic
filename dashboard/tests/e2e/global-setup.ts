import { execSync } from "child_process";
import path from "path";
import { request } from "@playwright/test";
import { TEST_PASSWORD } from "./fixtures/seed";

const REPO_ROOT = path.resolve(__dirname, "../../..");
const COMPOSE_FILE = path.join(REPO_ROOT, "docker-compose.test.yml");
// The signed-in browser state every spec starts from (playwright.config.ts).
export const STORAGE_STATE = path.join(__dirname, ".auth", "state.json");

async function waitForUrl(url: string, retries = 30, delayMs = 2000) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url);
      if (res.status < 500) return;
    } catch {}
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error(`Timed out waiting for ${url} after ${retries * delayMs}ms`);
}

async function globalSetup() {
  console.log("\n[E2E] Building and starting test containers…");
  execSync(`docker compose -f "${COMPOSE_FILE}" up -d --build --wait`, {
    cwd: REPO_ROOT,
    stdio: "inherit",
  });

  console.log("[E2E] Waiting for renderer health at http://localhost:4001/health…");
  await waitForUrl("http://localhost:4001/health");

  console.log("[E2E] Waiting for dashboard at http://localhost:3001…");
  await waitForUrl("http://localhost:3001");

  // The dashboard needs a password (TMDEV-152). Set it the way an operator
  // would, through the shared helper, in the API container that owns the DB.
  console.log("[E2E] Setting the test dashboard password…");
  execSync(
    `docker compose -f "${COMPOSE_FILE}" exec -T tubematic-api-test ` +
      "python3 -m tubematic_core.auth set-password --db /data/tubematic.db",
    { cwd: REPO_ROOT, input: `${TEST_PASSWORD}\n`, stdio: ["pipe", "inherit", "inherit"] },
  );

  // Sign in once through the real login route and keep the cookie, so every
  // spec starts signed in. auth.spec.ts opts out to test the signed-out path.
  const ctx = await request.newContext({ baseURL: "http://localhost:3001" });
  const res = await ctx.post("/api/auth/login", { data: { password: TEST_PASSWORD } });
  if (!res.ok()) throw new Error(`[E2E] Test login failed: HTTP ${res.status()} ${await res.text()}`);
  await ctx.storageState({ path: STORAGE_STATE });
  await ctx.dispose();

  console.log("[E2E] All services ready.\n");
}

export default globalSetup;
