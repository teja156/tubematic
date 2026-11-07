// A stills server: bundle the Remotion project ONCE, open ONE browser, then render any frame of any composition
// on request in a few seconds instead of the ~25 s a fresh `remotion still` costs (Chrome boot + bundle every time).
// The single biggest time cost of an authoring run was stills, by far.
//
//   node cartoon-tools/stills-server.mjs [--port 4455] [--gl angle-egl] [--chrome-mode chrome-for-testing]
//
// Requests: POST /still  {"composition": "Composition", "frame": 83, "props": {...}, "out": "/abs/path.png", "scale": 0.5}
//           POST /stills {"composition", "props", "frames": [83, 200], "outDir": "/abs/dir", "scale", "prefix": "f"}
//           GET  /health
// Responses: JSON {ok, out | outs, ms}. Public assets are served from the bundle, so files the request's props name
// under /public/<dir>/ must exist in public/ BEFORE the server starts, or be re-bundled with POST /rebundle.
// Browser console lines are collected per request and returned as `logs` (what `npx remotion still` never shows).
import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";

const arg = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : def;
};
const PORT = Number(arg("port", 4455));
const GL = arg("gl", "angle-egl");
const CHROME_MODE = arg("chrome-mode", "chrome-for-testing");
const ROOT = process.cwd();
const ENTRY = path.join(ROOT, "src/index.ts");
const chromiumOptions = { gl: GL, enableMultiProcessOnLinux: true, disableWebSecurity: false };

let serveUrl = null;
let browser = null;
let busy = Promise.resolve();

const rebundle = async () => {
  const t = Date.now();
  serveUrl = await bundle({ entryPoint: ENTRY, publicDir: path.join(ROOT, "public"), onProgress: () => {} });
  console.log(`[stills] bundled in ${Date.now() - t} ms: ${serveUrl}`);
};

const ensureBrowser = async () => {
  if (browser) return browser;
  browser = await openBrowser("chrome", { chromiumOptions, chromeMode: CHROME_MODE, logLevel: "error" });
  console.log(`[stills] browser open (${GL}, ${CHROME_MODE})`);
  return browser;
};

// a 1080x1920 frame of this look compresses to ~0.5-3 MB; a near-uniform frame (a lost WebGL context, a frame that
// never drew) is a few KB. Seen once in ~40 renders: retry it once with a fresh browser.
const MIN_PNG_BYTES = 40_000;
const one = async (composition, inputProps, frame, out, scale, attempt = 0) => {
  const logs = [];
  const comp = await selectComposition({ serveUrl, id: composition, inputProps, puppeteerInstance: await ensureBrowser(), chromiumOptions, chromeMode: CHROME_MODE, logLevel: "error" });
  await renderStill({
    composition: comp, serveUrl, output: out, frame, inputProps, scale, imageFormat: "png",
    puppeteerInstance: await ensureBrowser(), chromiumOptions, chromeMode: CHROME_MODE, logLevel: "error",
    onBrowserLog: (l) => logs.push(`${l.type}: ${l.text}`),
  });
  const bytes = fs.statSync(out).size;
  if (bytes < MIN_PNG_BYTES * Math.max(0.1, scale * scale) && attempt === 0) {
    console.log(`[stills] frame ${frame} came out near-empty (${bytes} bytes): retrying with a fresh browser`);
    try { await browser?.close(); } catch {}
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
    if (req.method === "GET" && req.url === "/health") return json(res, 200, { ok: true, bundled: !!serveUrl, browser: !!browser });
    if (req.method === "POST" && req.url === "/rebundle") { await (busy = busy.then(rebundle)); return json(res, 200, { ok: true }); }
    if (req.method === "POST" && (req.url === "/still" || req.url === "/stills")) {
      const b = await body(req);
      const t = Date.now();
      const scale = b.scale ?? 1;
      const comp = b.composition ?? "Composition";
      const props = b.props ?? {};
      const work = async () => {
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
server.listen(PORT, "127.0.0.1", () => console.log(`[stills] listening on http://127.0.0.1:${PORT}`));
const bye = async () => { try { await browser?.close(); } catch {} process.exit(0); };
process.on("SIGINT", bye);
process.on("SIGTERM", bye);
