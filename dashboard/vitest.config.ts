import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vitest/config";

// Pin the test-runner host to UTC, deliberately. Every timestamp formatter
// takes an explicit `timeZone` argument (see lib/datetime.ts) — running on a
// UTC host with UTC-vs-non-UTC assertions in the same test file proves the
// explicit argument is what's doing the work, not an implicit host default.
process.env.TZ = "UTC";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/unit/**/*.{test,spec}.{ts,tsx}"],
    env: { TZ: "UTC" },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
