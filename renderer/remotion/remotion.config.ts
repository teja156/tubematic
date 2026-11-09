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

// The CPU default. A working OpenGL renderer is required for @remotion/three
// (WebGL) in headless Chromium, and without a GPU "angle" fails to acquire a
// WebGL context ("GL_VENDOR = Disabled") — "swangle" (software
// ANGLE/SwiftShader) is Remotion's recommended renderer for GPU-less machines.
//
// When an NVIDIA GPU is configured and its probe has passed, the render
// worker overrides this on the command line (CLI flags win over this file)
// with the GPU flags in renderer/api/render_agent.py::_gl_args. Change the GPU path
// there, not here.
Config.setChromiumOpenGlRenderer("swangle");

// Tailwind v4 webpack integration.
Config.overrideWebpackConfig(enableTailwind);
