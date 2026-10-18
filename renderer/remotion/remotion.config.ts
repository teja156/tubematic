/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import { Config } from "@remotion/cli/config";
import { enableTailwind } from '@remotion/tailwind-v4';

// PNG frames eliminate JPEG compression artifacts on gradients and flat colors.
Config.setVideoImageFormat("png");

// Overwrite existing output files without prompting.
Config.setOverwriteOutput(true);

// A working OpenGL renderer is required for @remotion/three (WebGL) to work in
// headless Chromium. This container has no GPU, so "angle" fails to acquire a
// WebGL context ("GL_VENDOR = Disabled") — "swangle" (software ANGLE/SwiftShader)
// is Remotion's recommended renderer for GPU-less machines. Has no downside for
// non-3D renders and should always be set.
Config.setChromiumOpenGlRenderer("swangle");

// Tailwind v4 webpack integration.
Config.overrideWebpackConfig(enableTailwind);
