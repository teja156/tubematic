// ONE way to render the gates' stills, shared by the part gate and the beat gate: the stills server when one is up
// (cartoon-tools/stills-server.mjs, ~3 s a still), else the Remotion Node API with the project bundled ONCE and ONE browser
// for every still of the run. Before this each still was its own `npx remotion still` (a Chrome boot and a bundle
// each, ~25 s), which is what made a gate run slow and what a container without the CLI on PATH could not do.
//
// Env: GATE_GL, the flags the spike's scripts pass to `remotion still` (default "--gl=swangle", the no-GPU renderer;
// the host GPU recipe is "--gl=angle-egl --chrome-mode=chrome-for-testing --enable-multiprocess-on-linux");
// CARTOON_BROWSER, a Chromium executable to use instead of Remotion's downloaded one (the container's
// /usr/bin/chromium); STILLS_SERVER, the server's URL.
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export interface StillJob {
  composition: string;
  props: unknown;
  frame: number;
  out: string;
}

const flagsOf = () => {
  const flags = (process.env.GATE_GL ?? "--gl=swangle").split(/\s+/).filter(Boolean);
  const val = (k: string) => flags.find((f) => f.startsWith(`${k}=`))?.slice(k.length + 1);
  return {
    gl: (val("--gl") ?? "swangle") as "swangle" | "angle" | "angle-egl" | "egl" | "swiftshader" | "vulkan",
    chromeMode: (val("--chrome-mode") ?? "headless-shell") as "headless-shell" | "chrome-for-testing",
    multi: flags.includes("--enable-multiprocess-on-linux"),
    browserExecutable: process.env.CARTOON_BROWSER ?? null,
  };
};

/** the stills server, when it answers; false when there is none */
const viaServer = (jobs: StillJob[], scale: number): boolean => {
  const server = process.env.STILLS_SERVER;
  if (!server) return false;
  const curl = (route: string, body?: string) =>
    spawnSync("curl", ["-s", "--max-time", "600", ...(body ? ["-X", "POST", "-H", "content-type: application/json", "-d", body] : []), `${server}${route}`], { encoding: "utf8" });
  const h = curl("/health");
  if (h.status !== 0 || !/"ok":true/.test(h.stdout)) return false;
  curl("/rebundle", "{}"); // code parts and the staged scene-config change the bundle
  for (const j of jobs) {
    fs.mkdirSync(path.dirname(j.out), { recursive: true });
    const r = curl("/still", JSON.stringify({ composition: j.composition, props: j.props, frame: j.frame, out: j.out, scale }));
    if (r.status !== 0 || !/"ok":true/.test(r.stdout) || !fs.existsSync(j.out)) throw new Error(`stills server failed for ${j.out}: ${(r.stdout || r.stderr).slice(0, 300)}`);
  }
  return true;
};

/** renders every job; throws on the first failure */
export const renderStills = async (root: string, jobs: StillJob[], scale = 0.5): Promise<void> => {
  if (!jobs.length) return;
  if (viaServer(jobs, scale)) return;
  const { gl, chromeMode, multi, browserExecutable } = flagsOf();
  const chromiumOptions = { gl, enableMultiProcessOnLinux: multi };
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "cartoon-stills-bundle-"));
  let browser: Awaited<ReturnType<typeof openBrowser>> | null = null;
  try {
    // remotion.config.ts does not apply to the Node API: the Tailwind override and the public dir are passed here
    const serveUrl = await bundle({
      entryPoint: path.join(root, "src/index.ts"), outDir, publicDir: path.join(root, "public"),
      webpackOverride: enableTailwind, symlinkPublicDir: true, onProgress: () => {},
    });
    browser = await openBrowser("chrome", { chromiumOptions, chromeMode, browserExecutable, logLevel: "error" });
    // one selectComposition per distinct (composition, props)
    const groups = new Map<string, StillJob[]>();
    for (const j of jobs) {
      const k = `${j.composition}\n${JSON.stringify(j.props)}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(j);
    }
    for (const g of groups.values()) {
      // 120 s, not Remotion's 30 s: on software GL (the MCP container has no GPU) the composition's
      // first frame, with the post stack and the fonts and audio it waits for, has exceeded 30 s.
      const common = { serveUrl, inputProps: g[0].props as Record<string, unknown>, puppeteerInstance: browser, chromiumOptions, chromeMode, browserExecutable, logLevel: "error" as const, timeoutInMilliseconds: 120_000 };
      const composition = await selectComposition({ ...common, id: g[0].composition });
      for (const j of g) {
        fs.mkdirSync(path.dirname(j.out), { recursive: true });
        await renderStill({ ...common, composition, output: j.out, frame: j.frame, scale, imageFormat: "png" });
        if (!fs.existsSync(j.out)) throw new Error(`no still written for ${j.out}`);
      }
    }
  } finally {
    try { await browser?.close({ silent: true }); } catch { /* already gone */ }
    fs.rmSync(outDir, { recursive: true, force: true });
  }
};
