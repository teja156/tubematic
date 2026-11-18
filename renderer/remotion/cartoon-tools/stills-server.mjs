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
// An out or outDir must lie under <public>/<video>/cartoon/ or <video>/preview/ (out-path.mjs), or the request is answered 400 with
// nothing drawn: the port has no credential, and in production the public directory is the read-write /jobs volume.
// Responses: JSON {ok, out | outs, ms, logs}. Browser console lines are collected per request and returned as
// `logs` (what `npx remotion still` never shows).
//
// It starts empty: the first still bundles the project and opens the browser, and STILLS_IDLE_MS after the last
// request it closes the browser and deletes the bundle again. If that first bundle or the browser fails, it answers
// 503 with startFailed and exits, so the client renders the stills itself and the renderer starts the server again. The renderer runs this server on every install, but
// only Cartoon 3D authoring asks it for anything, and a bundle of every generated scene plus an idle Chromium held
// several hundred megabytes on installs that never use it.
import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { planRequest } from "./out-path.mjs";
import { syncMergedPublic } from "./merged-public.mjs";
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import { externalContextRegExp, overrideFor } from "../webpack-override.mjs";

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
// installed external style packages (TMDEV-252): a bundle compiles only the one its video uses
const EXTERNAL = path.join(ROOT, "src/scenes/external");
// what a render serves as /public/: the jobs volume plus the project's fonts, watermark and mascots (merged-public.mjs)
const MERGED_PUBLIC = fs.mkdtempSync(path.join(os.tmpdir(), "stills-public-"));
const syncPublic = () => syncMergedPublic(MERGED_PUBLIC, PUBLIC, path.join(ROOT, "public"));
const STILLS_IDLE_MS = 10 * 60 * 1000;

let serveUrl = null;
let bundledStamp = null;
let browser = null;
let busy = Promise.resolve();
let idleTimer = null;
let startFailed = null;

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

/** what a bundle for `style` and `video` compiled: the generated tree and the installed packages (a world
 * video's generated scene imports its package statically, with no style named) */
const sourceStamp = (style, video) => `${style}\n${video}\n${treeStamp(GENERATED)}\n${treeStamp(EXTERNAL)}`;

let bundledStyle = "";
let bundledVideo = "";

const rebundle = async (style = bundledStyle, video = bundledVideo) => {
  const t = Date.now();
  syncPublic();
  const stamp = sourceStamp(style, video);
  // remotion.config.ts does not apply to the Node API: the override and the public dir are passed here,
  // and the public dir is symlinked so files added under it later are served without another bundle
  const previous = serveUrl;
  serveUrl = await bundle({ entryPoint: ENTRY, publicDir: MERGED_PUBLIC, webpackOverride: overrideFor(style, video), symlinkPublicDir: true, onProgress: () => {} });
  bundledStamp = stamp;
  bundledStyle = style;
  bundledVideo = video;
  if (previous && previous !== serveUrl) fs.rmSync(previous, { recursive: true, force: true });
  console.log(`[stills] bundled in ${Date.now() - t} ms: ${serveUrl} (public ${PUBLIC})`);
};

/** bundle when there is none, or re-bundle when the source the request's style compiles changed since the
 * current bundle (the generated tree, or the request names another external style or its package changed) */
const freshen = async (style = "", video = "") => {
  syncPublic();   // a video filed since the last request is served too
  if (!serveUrl) {
    await rebundle(style, video);
  } else if (sourceStamp(style, video) !== bundledStamp) {
    console.log("[stills] source changed: re-bundling");
    await rebundle(style, video);
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

/** let go of the browser and the bundle; the next request builds them again */
const release = async () => {
  try { await browser?.close({ silent: true }); } catch { /* already gone */ }
  browser = null;
  if (serveUrl) fs.rmSync(serveUrl, { recursive: true, force: true });
  serveUrl = null;
  bundledStamp = null;
  console.log("[stills] idle: browser closed and bundle deleted");
};

/** (re)arm the idle timer. The release queues behind any request still running, and does nothing if a request
 *  came in since the timer was armed (one that ran longer than the idle time touches again when it ends). */
let lastUse = 0;
const touch = () => {
  lastUse = Date.now();
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    const idle = () => (Date.now() - lastUse >= STILLS_IDLE_MS ? release() : undefined);
    busy = busy.then(idle, idle);
  }, STILLS_IDLE_MS);
  idleTimer.unref();
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
      return json(res, 200, { ok: !startFailed, bundled: !!serveUrl, browser: !!browser, public: PUBLIC, gl: GL, chromeMode: CHROME_MODE });
    }
    if (req.method === "POST" && req.url === "/rebundle") { touch(); await (busy = busy.then(rebundle)); return json(res, 200, { ok: true }); }
    if (req.method === "POST" && (req.url === "/still" || req.url === "/stills")) {
      const b = await body(req);
      // every file goes under <public>/<video>/cartoon/ or preview/: checked before any bundle or browser, and the loop below
      // writes exactly the targets checked here
      const plan = planRequest(PUBLIC, req.url, b);
      if (plan.error) return json(res, 400, { ok: false, error: plan.error });
      const style = typeof b.externalStyle === "string" ? b.externalStyle : "";
      try { externalContextRegExp(style); } catch (e) { return json(res, 400, { ok: false, error: String(e.message ?? e) }); }
      // the video whose generated scenes the bundle compiles (the others cannot break it); "" compiles them all
      const video = typeof b.renderVideo === "string" ? b.renderVideo : "";
      if (video.includes("/") || video.length > 128) return json(res, 400, { ok: false, error: "renderVideo is not a video id" });
      const t = Date.now();
      const scale = b.scale ?? 1;
      const comp = b.composition ?? "Composition";
      const props = b.props ?? {};
      const work = async () => {
        try {
          await freshen(style, video);
          await ensureBrowser();
        } catch (e) {
          // With no bundle or no browser to fall back on, this server cannot draw anything: say so, and exit so the
          // renderer starts it again. The client renders the stills itself meanwhile, as when no server answers.
          if (!serveUrl || !browser) throw Object.assign(e instanceof Error ? e : new Error(String(e)), { startFailed: true });
          throw e;
        }
        // again now that the request has had its turn: renders are serialised, and a link planted while it waited
        // would otherwise go unchecked
        const again = planRequest(PUBLIC, req.url, b);
        if (again.error) throw Object.assign(new Error(again.error), { refused: true });
        const outs = [];
        const logs = [];
        for (const { frame, out } of again.targets) {
          fs.mkdirSync(path.dirname(out), { recursive: true });
          logs.push(...(await one(comp, props, frame, out, scale)));
          outs.push(out);
        }
        if (req.url === "/still") return { ok: true, out: outs[0], ms: Date.now() - t, logs };
        return { ok: true, outs, ms: Date.now() - t, logs };
      };
      // renders are serialised: one browser, one GPU
      const p = busy.then(work, work);
      busy = p.then(() => {}, () => {});
      touch();
      try {
        return json(res, 200, await p);
      } catch (e) {
        if (e?.refused) return json(res, 400, { ok: false, error: e.message });
        if (!e?.startFailed) throw e;
        startFailed = String(e?.message ?? e);
        console.log(`[stills] could not start (${startFailed}); exiting so the renderer starts it again`);
        json(res, 503, { ok: false, startFailed: true, error: startFailed });
        if (serveUrl) fs.rmSync(serveUrl, { recursive: true, force: true });
        fs.rmSync(MERGED_PUBLIC, { recursive: true, force: true });
        setTimeout(() => process.exit(1), 100);
        return;
      } finally {
        touch();
      }
    }
    json(res, 404, { ok: false, error: "unknown route" });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e?.message ?? e) });
  }
});

server.listen(PORT, HOST, () => console.log(`[stills] listening on http://${HOST}:${PORT}`));
const bye = async () => {
  try { await browser?.close({ silent: true }); } catch { /* already gone */ }
  fs.rmSync(MERGED_PUBLIC, { recursive: true, force: true });
  process.exit(0);
};
process.on("SIGINT", bye);
process.on("SIGTERM", bye);
