import { execSync } from "child_process";
import { readFileSync } from "fs";
import path from "path";
import { test, expect } from "@playwright/test";

// /stream through the real Next.js server, against the real output volume.
// The unit suite covers the cases; this proves the built route streams a
// byte-exact Range, revalidates with its ETag rather than letting the browser
// replay an old render, and that a symlink planted on the volume by another
// container cannot read the dashboard's own secrets (TMDEV-163, TMDEV-164).

const REPO_ROOT = path.resolve(__dirname, "../../../..");
const COMPOSE_FILE = path.join(REPO_ROOT, "docker-compose.test.yml");
const SIZE = 4096;
// The test stack's public session secret, which the dashboard container mounts.
const SESSION_SECRET = readFileSync(path.join(__dirname, "../secrets/session_secret"), "utf8").trim();
const EXPECTED = Buffer.from(Array.from({ length: SIZE }, (_, i) => i % 251));

// The API container mounts the output volume read-write, as in production;
// the dashboard's mount is read-only, so the files are planted from there.
// The link's target exists only in the dashboard container, which is the point.
const SEED = `
import os, shutil
d = "/output_videos/e2e-stream"
shutil.rmtree(d, ignore_errors=True)
os.makedirs(d)
with open(d + "/clip.mp4", "wb") as f:
    f.write(bytes(i % 251 for i in range(${SIZE})))
os.symlink("/run/secrets/session_secret", d + "/leak.mp4")
`;

test.describe("/stream", () => {
  test.beforeAll(() => {
    execSync(`docker compose -f "${COMPOSE_FILE}" exec -T tubematic-api-test python3 -`, {
      cwd: REPO_ROOT,
      input: SEED,
      stdio: ["pipe", "inherit", "inherit"],
    });
  });

  test("streams a byte-exact range and refuses a symlink to the session secret", async ({ request }) => {
    const ranged = await request.get("/stream/e2e-stream/clip.mp4", { headers: { Range: "bytes=100-199" } });
    expect(ranged.status()).toBe(206);
    expect(ranged.headers()["content-range"]).toBe(`bytes 100-199/${SIZE}`);
    expect(ranged.headers()["content-type"]).toBe("video/mp4");
    expect((await ranged.body()).equals(EXPECTED.subarray(100, 200))).toBe(true);
    expect(ranged.headers()["cache-control"]).toBe("private, no-cache");

    const etag = ranged.headers()["etag"];
    expect(etag).toMatch(/^"[^"]+"$/);
    const revalidated = await request.get("/stream/e2e-stream/clip.mp4", { headers: { "If-None-Match": etag } });
    expect(revalidated.status()).toBe(304);

    const leak = await request.get("/stream/e2e-stream/leak.mp4");
    expect(leak.status()).toBe(404);
    expect(await leak.text()).not.toContain(SESSION_SECRET);
  });
});
