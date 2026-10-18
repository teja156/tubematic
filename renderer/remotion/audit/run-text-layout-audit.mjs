#!/usr/bin/env node
//
// Text-layout audit driver (VQA-9).
//
// Renders a handful of already-chosen frames of the "TextLayoutAudit"
// composition WITHOUT producing any image, collects the measurement lines the
// TextLayoutProbe component prints, and writes one JSON document to the file
// named by the config's outputPath (NOT stdout — see the comment on `emit`).
//
// Called by mcp/text_audit.py. It computes NO policy: the frames to sample, and
// every threshold applied to the measurements, live on the Python side where
// pytest can cover them. Keep this file thin.
//
// Deliberately .mjs and outside src/: `npm run lint` is `eslint src && tsc`, and
// tsconfig.json has no allowJs, so nothing here is typechecked or linted. That
// is the point — a .ts driver would be compiled by the same `tsc --noEmit` that
// validate_job runs over the whole project on every video.
//
// Usage:
//   node audit/run-text-layout-audit.mjs '<json-config>'
// where <json-config> is:
//   {
//     "outputPath":      "/tmp/xxx.json",   // where the result document is written
//     "sceneConfigPath": "/public/<vid>/scene-config.json",
//     "timelinePath":    "/public/<vid>/timeline.json",
//     "audioPath":       "/public/<vid>/audio.mp3",
//     "passes": [{"scene": 0, "first": 45, "step": 101, "count": 5}, ...],
//     "browserExecutable": "/usr/bin/chromium"   // optional
//   }
//
// A pass is expressed as first/step/count rather than a frame list because that
// is exactly what Remotion samples: getFramesToRender keeps frames where
// (frame - frameRange[0]) % everyNthFrame === 0, i.e. frameRange[0] + k*step.
// Handing over an arbitrary list would mean guessing a step that reproduces it.

import { bundle } from "@remotion/bundler";
import { openBrowser, renderFrames, selectComposition } from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PROBE_LOG_PREFIX = "__TUBEMATIC_TEXT_AUDIT__";
const COMPOSITION_ID = "TextLayoutAudit";

const REMOTION_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ENTRY_POINT = path.join(REMOTION_ROOT, "src", "index.ts");

// The result goes to a FILE, never stdout. Remotion forwards every browser
// console line to its own stdout, and the probe communicates *through* console
// logs, so this driver's stdout is guaranteed to be full of
// "[Tab 0, ...] __TUBEMATIC_TEXT_AUDIT__{...}" lines. An earlier version wrote
// the JSON document to stdout and the Python side could never parse it. Don't
// move this back to stdout — the pollution is inherent, not incidental, and
// silencing it via logLevel would leave the channel one library change away
// from breaking again.
let outputPath = null;

const emit = (payload) => {
  const body = JSON.stringify(payload);
  if (!outputPath) {
    // No file to write to (bad/missing config) — stdout is the only channel
    // left, and the Python side falls back to reading it.
    process.stdout.write(body);
    return;
  }
  fs.writeFileSync(outputPath, body);
};

const fail = (message) => {
  emit({ passes: [], errors: [message] });
  process.exit(1);
};

const main = async () => {
  const raw = process.argv[2];
  if (!raw) {
    fail("run-text-layout-audit.mjs: missing JSON config argument");
  }

  let cfg;
  try {
    cfg = JSON.parse(raw);
  } catch (err) {
    fail(`run-text-layout-audit.mjs: config is not valid JSON: ${err.message}`);
  }

  if (!cfg.outputPath) {
    fail("run-text-layout-audit.mjs: config is missing outputPath");
  }
  outputPath = cfg.outputPath;

  const inputProps = {
    sceneConfigPath: cfg.sceneConfigPath,
    timelinePath: cfg.timelinePath,
    audioPath: cfg.audioPath,
  };

  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "tubematic-audit-bundle-"));
  let browser = null;
  const errors = [];
  const passes = [];

  try {
    // remotion.config.ts is NOT applied to the Node APIs (its own header says
    // so), so the Tailwind webpack override has to be passed explicitly here —
    // src/index.css is `@import "tailwindcss"`, and without this the audit would
    // compile a different page than the render does.
    //
    // symlinkPublicDir avoids copying the staged audio/images into the bundle;
    // this bundle is thrown away at the end of the call.
    const serveUrl = await bundle({
      entryPoint: ENTRY_POINT,
      outDir,
      webpackOverride: enableTailwind,
      symlinkPublicDir: true,
      onProgress: () => {},
    });

    const composition = await selectComposition({
      serveUrl,
      id: COMPOSITION_ID,
      inputProps,
      browserExecutable: cfg.browserExecutable ?? null,
    });

    // One browser for every pass. Also: gl "swangle" is set in
    // remotion.config.ts for the real render and is likewise NOT inherited here
    // — this container has no GPU, so "angle" fails to acquire a WebGL context
    // and any @remotion/three scene would behave differently in the audit than
    // in the render.
    browser = await openBrowser("chrome", {
      browserExecutable: cfg.browserExecutable ?? null,
      chromiumOptions: { gl: "swangle" },
    });

    for (const pass of cfg.passes ?? []) {
      const first = pass.first;
      const step = Math.max(1, pass.step ?? 1);
      const count = pass.count ?? 0;
      if (!Number.isInteger(first) || first < 0 || count < 1) {
        continue;
      }
      const last = first + step * (count - 1);
      // Keep only the LAST measurement per frame. The probe re-measures on every
      // commit, and a lazily-imported scene produces a second commit once its
      // module resolves — so the final line for a frame is the loaded one.
      const byFrame = new Map();
      const onBrowserLog = (log) => {
        for (const part of log.text.split("\n")) {
          const at = part.indexOf(PROBE_LOG_PREFIX);
          if (at === -1) {
            continue;
          }
          try {
            const parsed = JSON.parse(part.slice(at + PROBE_LOG_PREFIX.length));
            byFrame.set(parsed.frame, parsed);
          } catch {
            // A truncated console line is not worth failing the audit over;
            // a frame that never yields a parseable line simply goes missing
            // and the Python side reports the gap.
          }
        }
      };

      try {
        // frameRange spans only the frames we want and everyNthFrame thins it to
        // first + k*step. Both are honoured with imageFormat "none" and
        // outputDir null, which is what makes this cheap: no PNG is ever encoded
        // and nothing is written to disk.
        await renderFrames({
          serveUrl,
          composition,
          inputProps,
          imageFormat: "none",
          outputDir: null,
          frameRange: [first, last],
          everyNthFrame: step,
          concurrency: 1,
          muted: true,
          puppeteerInstance: browser,
          chromiumOptions: { gl: "swangle" },
          browserExecutable: cfg.browserExecutable ?? null,
          onBrowserLog,
          onStart: () => {},
          onFrameUpdate: () => {},
        });
      } catch (err) {
        errors.push(`scene ${pass.scene}: renderFrames failed: ${err.message}`);
      }

      passes.push({
        scene: pass.scene,
        requestedFrames: Array.from({ length: count }, (_, k) => first + step * k),
        frames: Array.from(byFrame.values()).sort((a, b) => a.frame - b.frame),
      });
    }
  } catch (err) {
    errors.push(`${err.message}`);
  } finally {
    if (browser) {
      try {
        await browser.close({ silent: true });
      } catch {
        // Closing a browser we're done with is best-effort.
      }
    }
    fs.rmSync(outDir, { recursive: true, force: true });
  }

  emit({ passes, errors });
};

main().catch((err) => {
  fail(`run-text-layout-audit.mjs: ${err?.stack ?? err}`);
});
