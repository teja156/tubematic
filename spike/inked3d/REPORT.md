# Inked3D spike: report

A throwaway fit check for one possible new visual style: flat 2D characters standing in a lit, inked 3D world. The test piece is a silent, 27-second Carrington Event (1859) short. All characters, props and sets are original and drawn in code. None of the work touches the pipeline.

| Output | Path |
|---|---|
| Video, 1080×1920, 30 fps, 810 frames, H.264 yuv420p, +faststart, no audio | `spike/inked3d/video.mp4` |
| Contact sheet (24 frames, one every 34) | `spike/inked3d/contact-sheet.png` |
| Key stills: first, middle and last frame of every shot and glide | `spike/inked3d/stills/f*.png` |
| Shadow evidence (on / off / difference) | `spike/inked3d/stills/shadow-check-f100.png` |
| Proof of the WebGL backend | `spike/inked3d/stills/webgl-renderer-f512.png` |
| Benchmark and render logs | `spike/inked3d/logs/` |
| Code (reusable kit plus the scene) | `renderer/remotion/src/spike/inked3d/` (composition `Inked3DSpike`) |

The final video is full resolution (1080×1920), so no half-size fallback or extra full-res clip was needed.

## 1. Machine and software

| Item | Value |
|---|---|
| CPU | Intel Core i5-8500 @ 3.00 GHz (turbo 4.1 GHz), 6 cores / 6 threads, no SMT |
| RAM | 31 GiB (about 24 GiB free during renders) |
| GPU | None usable. `nvidia-smi` cannot reach a driver, so every number below is software rendering |
| OS | Ubuntu 24.04.4 LTS, kernel 6.17.0-29-generic |
| Node | v22.23.2 |
| Remotion | 4.0.465 (`@remotion/three` 4.0.465). three 0.172.0, @react-three/fiber 9.1.2, React 19.2.3 |
| Browser | Remotion's chrome-headless-shell, Chromium 149.0.7790.0 |
| GL flag | `--gl=swangle` on every render and still (also set in `remotion.config.ts`) |
| WebGL renderer string, read in the page via `WEBGL_debug_renderer_info` | `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)`, vendor `Google Inc. (Google)`, `WebGL 2.0 (OpenGL ES 3.0 Chromium)`, drawing buffer 1080×1920 |

How the renderer string was captured: Remotion did not forward the page's `console.log`/`console.warn` to the CLI here (tried at `--log=verbose`). The composition takes a `showGlInfo` prop that draws the string from the live R3F context over the frame. `stills/webgl-renderer-f512.png` is that overlay. The machine is shared with a running Kasm stack, so the timings below carry some noise from it (see §9).

## 2. Per-layer cost (step 3)

Representative frame: 520 (night, operator close-up, aurora, sparks, smouldering tape). Effects are switched on cumulatively through composition props (`shadows`, `ink`, `grade`, `dof`). Every run used `--gl=swangle`. Raw numbers are in `logs/layer-benchmark.txt`.

Two measurements were taken, because a single `remotion still` is mostly fixed start-up cost:
- **still, median of 3**: the wall time of `npx remotion still` from a pre-built bundle, as asked. It includes launching Chrome, loading the page, building the procedural textures and compiling the shaders, about 10 s of fixed cost.
- **marginal s/frame**: a 30-frame render (frames 520–549) at `--concurrency=1`, minus a 1-frame render, divided by 29. That removes the start-up and is the real per-frame cost of one tab.

| Layers on | still, median of 3 (s) | marginal s/frame, one tab | added by this layer (s/frame) |
|---|---|---|---|
| base scene (lit, textured, sky, no shadows, plain tonemap) | 10.62 | 0.60 | 0.60 |
| + shadows (2048² PCF directional map, cut-outs alpha-tested) | 11.52 | 0.72 | +0.12 |
| + ink (second scene pass for normals + edge shader) | 11.73 | 0.88 | +0.16 |
| + grade | 11.82 | 0.84 | ≈0 (within noise) |
| + depth of field (24-tap gather, full res) | 12.43 | 1.12 | +0.28 |

Reading it: the whole look costs about 1.9× the bare scene. DOF is the most expensive single layer, then ink (because it re-renders the scene for normals), then shadows. The grade is free, and its row came out slightly lower than the row above it. That is run-to-run noise on a shared machine.

**One tab is not one core.** SwiftShader is multithreaded. During the `--concurrency=1` range render the machine was 82% busy on average, about 4.9 of the 6 cores (`logs/range60-concurrency1-2.samples.txt`). So "s/frame for one tab" already spends most of the machine. The core-seconds figures in §3 account for that.

**This benchmark was run twice.** The first run (before a bug fix, see §6) was slower across the board (base 0.91 s/frame) while the host had a load average of 7–10 from other work. Its shadow row was also wrong, because shadows only updated on the first frame of each tab. The table above is the second run, after the fix, with the host quieter (load ≈ 6). The first run is kept in `logs/layer-benchmark-run1-before-shadow-fix.txt`.

## 3. Full render (step 4)

Command: `npx remotion render src/index.ts Inked3DSpike … --gl=swangle --crf=20` under `/usr/bin/time -v`, with a sampler recording every Chrome/Node/compositor process and machine-wide CPU every 2 s. Logs: `logs/full-render-2.*`.

| Item | Value |
|---|---|
| Frames | 810 (27.0 s at 30 fps), no hard cuts |
| Resolution | 1080×1920 (full) |
| Wall clock | **13:00.7** (780.7 s). This includes bundling (≈5 s) and per-tab start-up (each tab's first frame takes ≈14 s: page load, texture build, shader compile) |
| Concurrency | **3**, Remotion's default (half of the 6 cores) |
| Seconds per frame, overall | **0.96 s** wall |
| Seconds per frame, per tab | 2.89 s (0.96 × 3) |
| CPU utilisation | machine 91% busy on average = **5.46 of 6 cores** (sampler, 386 samples) |
| CPU cost per frame | **≈ 5.3 core-seconds** (0.96 s × 5.46 cores) |
| Peak memory | **≤ 4.6 GB** summed RSS of Chrome + Node + compositor (upper bound) |
| Output size | raw Remotion encode (CRF 20): 23.0 MB. Final `video.mp4` re-encoded with libx264 `-preset slow -crf 24 -pix_fmt yuv420p -movflags +faststart`, audio stripped: **12.2 MB** |
| Bundle time | 4.8 s uncached (`remotion bundle --bundle-cache=false`), 1.9 s cached |
| `--concurrency=1`, frames 480–539 | 79.0 s wall for 60 frames, ≈ **1.12 s/frame** after start-up. Machine 82% busy (4.91 cores), ≤ 2.7 GB |

Why `/usr/bin/time -v` alone is misleading here: it reports the `npx` process tree's own CPU time and peak RSS (17% CPU, 743 MB). That misses the Chrome GPU process, where SwiftShader does all the work. Use the sampler's machine-wide figures instead. Its peak memory is the summed RSS of every Chrome, Node and compositor process, which double-counts shared pages. So it is an upper bound.

**Concurrency barely helps on this CPU.** Remotion chose 3 tabs. At 3 tabs the render ran at 0.96 s/frame wall; at 1 tab it ran at 1.12 s/frame. Both saturate the machine, because SwiftShader already spreads one tab across most cores. The cost to plan around is therefore **≈ 5.3 CPU-core-seconds per 1080×1920 frame**, however the work is split.

### Extrapolation: a 90-second video (2700 frames) at full resolution

| Setting | Estimate |
|---|---|
| This machine, Remotion's default concurrency (3) | ≈ 43 minutes (2700 × 0.96 s + start-up) |
| This machine, `--concurrency=1` | ≈ 51 minutes (2700 × 1.12 s + start-up) |
| Same thing in CPU time | ≈ 4.0 core-hours |

Both include start-up and encoding at the measured rates. The renderer container has no GPU, so on a comparable 6-core host a 90 s Short occupies the whole machine for about 43 minutes. The render did not come near the 2-hour limit, so the final video is full resolution.

## 4. Measured visual checks

| Check | Target | Measured | How |
|---|---|---|---|
| Darkest pixel | clearly above 0, no pure black | min luma **12.9/255** (0.1th percentile 13.2) across the 19 key stills, with **0 pixels whose channels are all 0**. The encoded `video.mp4` is not as clean: H.264 4:2:0 chroma subsampling pushes 1–2 isolated pixels per frame (503 of 1.68 billion) to black where a dark ink line meets a saturated colour. The renderer never outputs them (see §6 and `logs/video-vs-stills.txt`) | Rec.709 luma over the PNG stills (`stills/`) and over every decoded frame of `video.mp4` |
| Ink-edge coverage | ≈75% of visible edges carry a line | **57–76% by line weight**, 29–63% by thresholded pixel count (frames 100, 360, 512, 760) | The composite shader has debug views: view 1 = the final ink mask (with the noise breakup and distance fade), view 2 = the same edges without the breakup. Coverage = mask 1 ÷ mask 2 |
| Camera moving | moving in most frames | **809 of 809 frame steps** move (> 1.5 mm or an FOV change) | `pathStats()` over the beat list (`logs/camera-stats.txt`) |
| Hard cuts | at most 1 | **0** | one continuous world, five beats joined by four glides |
| Glide easing | ease in/out over ≈20–25 frames | glides of 80, 55 and 50 frames ease in over 44/28/24 frames and out over 36/27/26. The last glide is 35 frames (17 in, 18 out), short of the target but very slow (peak 3 cm/frame) | per-frame camera speed from the same beat list |
| Lines survive DOF | in-focus character keeps its outlines | yes; see `stills/f715.png` and `f809.png` (character sharp, wall behind blurred) | DOF is a separate last pass over the already-inked image; it can soften background lines but not erase the subject's |
| Character shadows | cut-out shapes cast real shadows on the ground | yes. `stills/shadow-check-f100.png` diffs shadows on and off: the newsboy's round-headed silhouette falls on the boardwalk, and a long shadow crosses the cobbles | `customDepthMaterial` with the character texture and `alphaTest` |
| Night shadows not brown | purple / blue | darks at night are violet-red to blue (desk front ≈ hue 358, wall ≈ 297, sky 237). Some deep wood near the floor still reads warm (hue ≈ 25 before the final, stronger shadow tint; not re-measured after it) | sampled pixels on frame 512 |
| No props over faces | none | clean in all 19 stills. The battery lead crosses the operator's vest, never his face | visual check of every still |
| Camera inside geometry | never | no clipping in any still. The closest pass is the 300–330 glide, about 6 m from the store fronts | visual check, and positions checked with a projection script |

Coverage is below the brief's ~75% in the wide shots. That is a one-line tuning change (§6).

## 5. What is in the video

0–4 s: late afternoon. The street, the telegraph poles and sagging wires lead to the red TELEGRAPH office. The operator taps at his desk on the porch while a newsboy walks along the street, casting a long shadow. Slow push-in.
4–6 s: the camera glides up the nearest pole to the wires.
6–9 s: it travels along the wires toward the setting sun past the poles, trees, rocks and mesas. Dusk falls quickly.
9–11 s: a swoop down to a low angle. Night, the aurora overhead, the newsboy pointing at it.
11–15 s: a glide in to the desk. Sparks crackle from the key, arcs jump to the sounder, the paper tape smoulders, and the operator recoils (shock).
15–27 s: he unplugs the battery (three glass jar cells) and holds the lead up, and the key keeps clicking anyway, lit by the aurora alone. Slow push-in on his amazed face, with one blink.

Two original characters, each with expression swaps as texture states:
- **The operator**: green eyeshade, curly moustache, teal waistcoat, red garters. Poses tap, recoil, reach and hold. Expressions focus, smile, shock and amazed, plus blinks.
- **The newsboy**: purple flat cap, freckles, orange scarf, satchel. Two walk frames and a point pose. Expressions smile and awe, plus blinks.

Both bob slightly.

## 6. What worked, what looked off, cheapest fixes

**Worked**
- The core look reads well on a phone: saturated painted wood, dark violet plank gaps, cool shadows and comic outlines on 3D geometry. The flat characters sit convincingly in the lit set, and the warm-to-night-blue change is a strong storytelling device.
- The ink pass uses the second difference of 1/z. That is exactly zero on any plane, so grazing ground and walls never sprout false lines, and silhouettes get one clean line on the near side. No tuning was needed between shots.
- The cut-out shadows work, and the characters take the scene's light colour through a tinted emissive term, so they never go flat-black against a backlight.
- The camera beat system (drifts joined by Hermite glides whose end speeds match) gives continuous, motivated movement with zero cuts and no snapping.
- Everything is deterministic after the fix below. A sequential render matches single stills bit for bit (mean absolute difference 0.0 on the frames tested).

**A real bug found and fixed**

The first two full renders had frozen shadows. R3F's `configure()` runs on every React re-render of `<Canvas>` and reset `gl.shadowMap.enabled` to its `shadows` prop (unset, so false) after frame 1. Every later frame in a tab then reused that tab's first shadow map, so lighting drifted by up to a mean of 30/765 per pixel against the stills. It showed up as stray shadows on the desk front.

It was found by diffing the video against the stills, then pinned down with a per-frame debug overlay (`debugOverlay` prop): the shadow camera stayed at the first frame's position. The fix passes `shadows={{enabled, type}}` to the canvas and re-asserts `shadowMap.enabled` every frame in the pipeline.

**Any Remotion + R3F render that sets renderer state outside the Canvas props has this trap.** A Tubematic kit must own all renderer state in one place, and needs a test that diffs a sequential render against fresh stills.

**Looked off, with the cheapest fix for each**

| Issue | Cheapest fix |
|---|---|
| Ink coverage ~60% in wide shots against the ~75% target | Lower the breakup thresholds in the composite shader (`smoothstep(0.30, 0.42, …)` to about `0.22, 0.34`) |
| The cobbled street is busy in the wide shots, and the character shadows on it are low-contrast | A calmer cobble texture, or dirt with a few setts; shadows read best on planks |
| The aurora is rich purple/magenta rays with a thin green base; real red-over-green curtains would be more legible | Widen the green band and lower the ray contrast in `Sky.ts` |
| The 4–6 s glide frames (e.g. still 145) are mostly empty sky plus a building corner | Add a look-at via point on the wires, or extend the beat |
| The night office window is a flat, very saturated blue panel behind the operator in every close-up | Give it an interior (a dim lamp, curtains), or reflect the aurora |
| The operator's own shadow is hard to see: the key is in front of him and his shadow lands behind him | A light from the side, or a lit wall closer behind him |
| The last glide's ease is 17/18 frames | Start the final beat ~10 frames later |
| The web encode (4:2:0) clips 1–2 pixels per frame to pure black at ink-line/saturated-colour edges. The rendered frames bottom out at luma 12.9 | Raise the grade's `lift` floor to about 0.08, or soften the ink colour slightly. Alternatively keep a 4:4:4 master and accept the 4:2:0 delivery artefact |
| Hard alpha-test edges on the cut-outs alias slightly (no MSAA) | Alpha-to-coverage, or a 1-pixel dark fringe in the drawing |

## 7. What a Tubematic agent would need from a reusable kit

The code under `renderer/remotion/src/spike/inked3d/kit/` is already split along these lines:
- `InkPipeline` holds the render, normals, composite (ink + grade + signed circle of confusion) and DOF passes.
- `Cutout` is the character plane with states, a shadow and a tint.
- `Sky` holds the gradient, sun, stars and aurora.
- `cameraPath` holds the beats, glides, via points and stats.
- `textures` holds the procedural planks, clapboard, shingles, cobbles, dirt, stone blocks, bark, sign and foliage.
- `geometry` holds world-UV boxes, gables, roofs, catenary wires, telegraph poles, trees and rocks.

A production kit would expose roughly:
- `<InkedWorld timeOfDay={0..1 | keyframes} palette="sunset-to-night" shadows ink grade dof>`: owns all renderer state (see the bug above) and the effect order.
- Set pieces with a handful of props each:
  - `<Building x z width height style="clapboard|falseFront|gable" paint={hue} sign="TELEGRAPH" windows lit>`
  - `<PoleLine from to spacing wires={4} sag>`
  - `<Street kind="cobbles|dirt|boardwalk">`
  - `<Tree>` and `<Rock>` with seed and scale
  - `<Sky aurora={0..1} stars>`
- `<Character id="operator" at={[x,z]} state="tap:focus" blink={[frames]} bob tint>`, backed by a **character library**: each character a set of named pose and expression drawings (canvas or SVG). This is the expensive creative asset. An agent cannot be trusted to draw a consistent new character for every video, so it should pick from a library and only choose states.
- `<Camera beats={[{start,end,from:{pos,target,fov,focus},to:{…}}]}>` with glides generated automatically, plus a validator that refuses a pose inside geometry or a subject outside the frame. Hand-placing coordinates was the slowest part of this spike: a character ended up hidden behind a barrel, and another was cropped by the frame edge. Both were only caught by looking at stills or projecting points.
- Effects: `<Sparks at count intensity>`, `<Arc from to>`, `<Smoke at>`, `<Ember>` and a battery-lead style `<Cable from to plugged>`.

**Risks**
- **Render time.** About 5.3 CPU-core-seconds per frame, so roughly ≈ 43 minutes (2700 × 0.96 s + start-up) for a 90-second Short on a 6-core box with no GPU, against minutes for today's 2D scenes. The render-timeout settings and queue depth would need to change. A GPU renderer (`--gl=angle` on real hardware) would very likely be much faster, but that could not be measured here.
- **Camera clipping and framing.** Nothing stops an agent's camera from entering a wall or losing the subject. That needs automated checks: project the subject to screen, raycast from the camera.
- **Asset library.** The look depends on good characters and set dressing. Procedural sets are cheap to vary; characters are not.
- **Fragile determinism.** The bug in §6 shows how easily a stateful renderer drifts between tabs.
- **Memory.** Up to 4.6 GB summed RSS at 3 tabs. That is fine on this host and worth checking against the renderer container's limit.

## 8. Packages and assets

**Packages added: none.** Everything is built from what the renderer already ships: `three` 0.172.0, `@react-three/fiber` 9.1.2 and `@remotion/three` 4.0.465. The passes are hand-written `ShaderMaterial`s, not `EffectComposer`. Owning the pass order and the render-target formats (half-float colour + float depth texture) was simpler than bending the stock Sobel/Bokeh passes, which assume colour-only input. `package.json` and `package-lock.json` are unchanged.

**3D models and textures: none external.** Every texture is drawn on a canvas with a seeded PRNG, every mesh is built in code, and both characters are drawn in code. There are no CC0 or other third-party assets.

## 9. Honest limits

- **No GPU.** `--gl=angle` could not be compared because the machine has no working GPU driver. GPU speed-up is a guess, not a measurement.
- **Shared machine.** The host also runs a Kasm stack. The first benchmark (load average 7–10) was ~50% slower than the second (≈6). The numbers carry that noise, and a quiet machine could be somewhat faster.
- **Memory is an upper bound.** It is summed RSS of the Chrome, Node and compositor processes, and shared pages are counted more than once. `/usr/bin/time` cannot see the Chrome GPU process, so its own RSS and CPU% understate the cost badly.
- **Ink coverage is an estimate.** The baseline is the shader's own edge detector without the breakup. That is not a ground truth of "visible edges"; an artist might count edges the detector misses, such as texture-only edges.
- **The look has only been checked by me.** No human has watched it yet; the verdict on whether it is good enough is the owner's.
- **Final stills come from single-frame renders.** After the shadow fix, sequential renders matched them bit for bit on frames 360 and 380. Every one of the 19 stills matches the same frame of the full render to within codec noise (mean difference 5.6–12.4 out of 765, against 7.2 for codec-only error; `logs/video-vs-stills.txt`).
- **Not run inside the real renderer container** (Debian, its own Chrome and fonts). It was run on the host with the same Remotion and Chrome versions. The sign uses the generic `serif` font, so its typeface may differ there.
- **The shot timings are approximate:** the 27 s video is 810 frames, and beat boundaries are in `carrington/scene.ts` (`T` and `BEATS`).
