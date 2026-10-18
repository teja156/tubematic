import { execSync } from "child_process";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../..");
const COMPOSE_FILE = path.join(REPO_ROOT, "docker-compose.test.yml");

async function globalTeardown() {
  console.log("\n[E2E] Tearing down test containers and volumes…");
  execSync(
    `docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans`,
    { cwd: REPO_ROOT, stdio: "inherit" }
  );
  console.log("[E2E] Teardown complete.\n");
}

export default globalTeardown;
