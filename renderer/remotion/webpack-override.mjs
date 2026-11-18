// The bundler override of every bundle that compiles the whole project (renders
// through remotion.config.ts, the stills server, the stills fallback, the text
// audit). TMDEV-252.
//
// - Tailwind v4 (src/index.css is `@import "tailwindcss"`).
// - `@tubematic/scene-api`: the names an external style package may import from
//   the image (src/sceneApi/v1.ts).
// - The composition's `import(\`./scenes/external/${src}.tsx\`)` is a webpack
//   context: every matching file under the folder compiles into the bundle. One
//   installed package that fails to compile would then break every render, so a
//   bundle compiles only the external style it was made for, and none for a
//   built-in style's video.
// - The generated-scene context the same way: a bundle made for one video
//   compiles that video's scenes and the legacy flat ones, so another video's
//   scene (a world video importing a package since removed) cannot break it.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { webpack } from "@remotion/bundler";
import { enableTailwind } from "@remotion/tailwind-v4";

// The Remotion project directory: this file's, or above it when esbuild has
// bundled this module into a command line under cartoon-tools/dist/. The
// Remotion CLI compiles remotion.config.ts (and this file with it) to CommonJS,
// where import.meta is empty; it runs the config from the project directory, so
// the search starts at the working directory there.
const findRoot = () => {
  const start = typeof import.meta.url === "string" ? path.dirname(fileURLToPath(import.meta.url)) : process.cwd();
  let dir = start;
  while (!fs.existsSync(path.join(dir, "src", "sceneApi", "v1.ts"))) {
    const up = path.dirname(dir);
    if (up === dir) return start;
    dir = up;
  }
  return dir;
};
const ROOT = findRoot();
export const SCENE_API_ALIAS = "@tubematic/scene-api";
// Keep in sync: tubematic_core/external_styles.py::ID_RE.
const ID_RE = /^ext_[a-z0-9_]{1,40}$/;
const NOTHING = /(?!)/;

export const externalContextRegExp = (style) => {
  if (!style) return NOTHING;
  if (!ID_RE.test(style)) throw new Error(`not an external style id: ${JSON.stringify(style)}`);
  return new RegExp(`^\\./${style}/.*\\.tsx$`);
};

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// The video's own namespaced scenes and the legacy flat files; null leaves the context whole.
export const generatedContextRegExp = (videoId) =>
  videoId ? new RegExp(`^\\./(${escapeRe(videoId)}/.*|[^/]+)\\.tsx$`) : null;

export const overrideFor = (style, videoId = "") => (config) => {
  const tailwind = enableTailwind(config);
  return {
    ...tailwind,
    resolve: {
      ...tailwind.resolve,
      alias: { ...(tailwind.resolve?.alias ?? {}), [SCENE_API_ALIAS]: path.join(ROOT, "src", "sceneApi", "v1.ts") },
    },
    plugins: [
      ...(tailwind.plugins ?? []),
      new webpack.ContextReplacementPlugin(/[\\/]scenes[\\/]external$/, externalContextRegExp(style)),
      ...(videoId ? [new webpack.ContextReplacementPlugin(/[\\/]scenes[\\/]generated$/, generatedContextRegExp(videoId))] : []),
    ],
  };
};

// The style and the video named by the environment, for the processes that bundle once per video.
export const overrideFromEnv = () =>
  overrideFor(process.env.TUBEMATIC_EXTERNAL_STYLE || "", process.env.TUBEMATIC_RENDER_VIDEO || "");
