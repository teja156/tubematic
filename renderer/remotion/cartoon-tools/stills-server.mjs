// The stills server: bundle the Remotion project ONCE, open ONE browser, then render any frame of any composition
// on request in a few seconds instead of the ~25 s a cold `remotion still` costs (Chrome boot + bundle every time).
// Stills were by far the biggest time cost of an authoring run.
//
// In production the renderer (renderer/api/render_agent.py) runs it inside tubematic-renderer, the one container with
// the GPU, with the same GL flags its renders get, and the MCP container's Cartoon 3D tools post their gate and
// preview stills to it over the Compose network (STILLS_SERVER in src/cartoon3d/probe2/gate/stills.ts). The public
// directory is the shared /jobs volume, served live through a symlink, so a video's scene-config, timeline and
// audio are reachable as /public/<vid>/... with nothing staged and nothing re-bundled.
//
//   node cartoon-tools/stills-server.mjs [--port 4455] [--host 127.0.0.1] [--public <dir>] [--gl angle-egl]
//        [--chrome-mode chrome-for-testing] [--multiprocess 1] [--browser-executable /usr/bin/chromium]
//
// Requests: POST /still  {"composition": "Composition", "frame": 83, "props": {...}, "out": "/abs/path.png", "scale": 0.5}
//           POST /stills {"composition", "props", "frames": [83, 200], "outDir": "/abs/dir", "scale", "prefix": "f"}
//           POST /rebundle                 (after the project's own source changes; public files need none)
// The generated source tree (src/scenes/generated/, the agent's per-video TypeScript) is bundled into the serve
// URL, so every request first compares a stamp of that tree (every file's path, size and mtime) with the one the
// current bundle was made from, and re-bundles when it differs: an edit to a video's code is seen by its next still
// (~20 s once), an unchanged tree costs a directory walk.
//           GET  /health                   {ok, bundled, browser, public, gl, chromeMode}
// Responses: JSON {ok, out | outs, ms, logs}. Browser console lines are collected per request and returned as
// `logs` (what `npx remotion still` never shows).
import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";

const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : def;
};
const PORT = Number(arg("port", 4455));
const HOST = arg("host", "127.0.0.1");
const GL = arg("gl", "angle-egl");
const CHROME_MODE = arg("chrome-mode", "chrome-for-testing");
const MULTI = arg("multiprocess", "1") !== "0";
const BROWSER = arg("browser-executable", null);
const ROOT = process.cwd();
const PUBLIC = path.resolve(arg("public", path.join(ROOT, "public")));
const ENTRY = path.join(ROOT, "src/index.ts");
// 120 s, not Remotion's 30 s: on software GL the composition's first frame has exceeded 30 s (stills.ts)
const TIMEOUT_MS = 120_000;
const chromiumOptions = { gl: GL, enableMultiProcessOnLinux: MULTI, disableWebSecurity: false };
const browserOptions = { chromiumOptions, chromeMode: CHROME_MODE, browserExecutable: BROWSER, logLevel: "error" };

const GENERATED = path.join(ROOT, "src/scenes/generated");

let serveUrl = null;
let bundledStamp = null;
let browser = null;
let busy = Promise.resolve();

/** a stamp of the generated source tree: every file's path, size and mtime, in a fixed order */
export const treeStamp = (dir) => {
  const rows = [];
  const walk = (d) => {
    let entries;
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile()) { try { const st = fs.statSync(p); rows.push(`${path.relative(dir, p)}:${st.size}:${st.mtimeMs}`); } catch { /* vanished */ } }
    }
  };
  walk(dir);
  return rows.join("\n");
};

const rebundle = async () => {
  const t = Date.now();
  const stamp = treeStamp(GENERATED);
  // remotion.config.ts does not apply to the Node API: the Tailwind override and the public dir are passed here,
  // and the public dir is symlinked so files added under it later are served without another bundle
  const previous = serveUrl;
  serveUrl = await bundle({ entryPoint: ENTRY, publicDir: PUBLIC, webpackOverride: enableTailwind, symlinkPublicDir: true, onProgress: () => {} });
  bundledStamp = stamp;
  if (previous && previous !== serveUrl) fs.rmSync(previous, { recursive: true, force: true });
  console.log(`[stills] bundled in ${Date.now() - t} ms: ${serveUrl} (public ${PUBLIC})`);
};

/** re-bundle when the generated source tree changed since the current bundle */
const freshen = async () => {
  if (treeStamp(GENERATED) !== bundledStamp) {
    console.log("[stills] generated source changed: re-bundling");
    await rebundle();
  }
};

const ensureBrowser = async () => {
  if (browser) return browser;
  browser = await openBrowser("chrome", browserOptions);
  console.log(`[stills] browser open (${GL}, ${CHROME_MODE}${BROWSER ? `, ${BROWSER}` : ""})`);
  return browser;
};

// a 1080x1920 frame of this look compresses to ~0.5-3 MB; a near-uniform frame (a lost WebGL context, a frame that
// never drew) is a few KB. Seen once in ~40 renders: retry it once with a fresh browser.
const MIN_PNG_BYTES = 40_000;
const one = async (composition, inputProps, frame, out, scale, attempt = 0) => {
  const logs = [];
  const common = { serveUrl, inputProps, puppeteerInstance: await ensureBrowser(), ...browserOptions, timeoutInMilliseconds: TIMEOUT_MS };
  const comp = await selectComposition({ ...common, id: composition });
  await renderStill({ ...common, composition: comp, output: out, frame, scale, imageFormat: "png", onBrowserLog: (l) => logs.push(`${l.type}: ${l.text}`) });
  const bytes = fs.statSync(out).size;
  if (bytes < MIN_PNG_BYTES * Math.max(0.1, scale * scale) && attempt === 0) {
    console.log(`[stills] frame ${frame} came out near-empty (${bytes} bytes): retrying with a fresh browser`);
    try { await browser?.close({ silent: true }); } catch { /* already gone */ }
    browser = null;
    return one(composition, inputProps, frame, out, scale, 1);
  }
  return logs;
};

const json = (res, code, body) => {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
};
const body = (req) => new Promise((resolve, reject) => {
  let s = "";
  req.on("data", (c) => (s += c));
  req.on("end", () => { try { resolve(s ? JSON.parse(s) : {}); } catch (e) { reject(e); } });
});

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/health") {
      return json(res, 200, { ok: true, bundled: !!serveUrl, browser: !!browser, public: PUBLIC, gl: GL, chromeMode: CHROME_MODE });
    }
    if (req.method === "POST" && req.url === "/rebundle") { await (busy = busy.then(rebundle)); return json(res, 200, { ok: true }); }
    if (req.method === "POST" && (req.url === "/still" || req.url === "/stills")) {
      const b = await body(req);
      const t = Date.now();
      const scale = b.scale ?? 1;
      const comp = b.composition ?? "Composition";
      const props = b.props ?? {};
      const work = async () => {
        await freshen();
        if (req.url === "/still") {
          fs.mkdirSync(path.dirname(b.out), { recursive: true });
          const logs = await one(comp, props, b.frame ?? 0, b.out, scale);
          return { ok: true, out: b.out, ms: Date.now() - t, logs };
        }
        fs.mkdirSync(b.outDir, { recursive: true });
        const outs = [];
        const logs = [];
        for (const f of b.frames) {
          const out = path.join(b.outDir, `${b.prefix ?? "f"}${String(f).padStart(4, "0")}.png`);
          logs.push(...(await one(comp, props, f, out, scale)));
          outs.push(out);
        }
        return { ok: true, outs, ms: Date.now() - t, logs };
      };
      // renders are serialised: one browser, one GPU
      const p = busy.then(work, work);
      busy = p.then(() => {}, () => {});
      return json(res, 200, await p);
    }
    json(res, 404, { ok: false, error: "unknown route" });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e?.message ?? e) });
  }
});

await rebundle();
await ensureBrowser();
server.listen(PORT, HOST, () => console.log(`[stills] listening on http://${HOST}:${PORT}`));
const bye = async () => { try { await browser?.close({ silent: true }); } catch { /* already gone */ } process.exit(0); };
process.on("SIGINT", bye);
process.on("SIGTERM", bye);
