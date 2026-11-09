# GPU and Remote Renderers

A renderer draws on the CPU unless it has shown that Chromium reaches an NVIDIA GPU. An install can
also have several renderers: the built-in one, and remote renderers on other machines. This page
covers how a renderer tests and uses a GPU, what happens to a video that needs a GPU when none
works, and how the main install (the machine with the dashboard and the database) shares renders
among renderers.

One render from claim to result is on [Rendering and Review](11-rendering-and-review.md). The
gateway's routes, TLS and credentials are on [The Render Gateway](19-render-gateway.md). The two
sweeps that back rendering up are on [The Worker](12-the-worker.md). The operator's steps are in the
user guide: [GPU Rendering](../user-guide/10-gpu-rendering.md) and
[Remote Renderers](../user-guide/11-remote-renderers.md).

---

## The GL renderer

Chromium draws every frame, and WebGL (three.js scenes, and Chromium's own compositing) needs an
OpenGL implementation. A renderer picks one of two paths per render from its own
[GPU test](#the-gpu-test) (`render_agent.py::_render_on_gpu`).

The CPU path is the default: `renderer/remotion/remotion.config.ts` sets
`setChromiumOpenGlRenderer("swangle")`, ANGLE over SwiftShader, which works on any machine. The
render command gets no GL flag.

The GPU path adds five settings, from `render_agent.py::_gl_options` (`_gl_args` turns them into
flags):

| Setting | Why it is needed |
|---|---|
| `--browser-executable=/usr/bin/chromium` | The image's Debian Chromium reaches the GPU with nothing to download. Without the flag Remotion downloads its own Chrome for Testing (about 177 MB) on the first GPU render |
| `--gl=angle-egl` | Hardware OpenGL through EGL. The other values Remotion accepts get no context in the container or stay in software |
| `--chrome-mode=chrome-for-testing` | With a named browser this switches it to `--headless=new`. In the old headless mode one tab gets a GPU WebGL context but several at once fail (`BindToCurrentSequence failed`), so a multi-tab three.js render fails in every tab |
| `--enable-multiprocess-on-linux` | Remotion's default in 4.x, stated so that a changed default cannot put Chromium in `--single-process`, which disables its GPU process |
| `__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json` (environment) | Points libglvnd at NVIDIA's EGL. Without it EGL may load another vendor's (Mesa's is in the image), and the render succeeds on the wrong device |

The CPU path uses none of them, because the new headless mode in software is about five times
slower than the old one, measured on a 2D scene.

## The Compose override

`docker-compose.yml` reserves no GPU, because a device reservation Docker cannot satisfy stops the
container from being created. The `gpu` onboarding step (`python3 onboard.py --step gpu`,
`onboard/actions.py::apply_gpu`) writes `~/.tubematic-data/compose.gpu.json`. It gives
`tubematic-renderer` the device reservation, `NVIDIA_DRIVER_CAPABILITIES=graphics,utility`,
`TUBEMATIC_GPU_UUID` and `TUBEMATIC_GPU_NAME` (which tell the renderer a GPU is meant to be there),
and `TUBEMATIC_HOST_GPUS`. The file's contents and how Compose loads it are under
[GPU override](16-infrastructure.md#gpu-override). A hand-run `docker compose up` skips the file,
and the renderer then renders on the CPU.

`gpu.py::read_override` accepts only a file this module wrote. `upgrade.py` refuses before it stops
anything when `gpu.py::override_problems` finds that Docker cannot hand the GPU over.
`gpu.py::report_lines` gives `upgrade.py --check` and `python3 scripts/service.py status` the
override and the built-in renderer's last test, and warns when the running renderer still uses the
previous choice.

A new choice applies when the renderer container is recreated
(`actions.py::_recreate_renderer`). The step does not kill a render:

1. It takes a lock file beside the database, `.gpu-recreate.lock`. A second run that cannot take it
   defers, because the row below is shared and two runs would release each other's hold.
2. It writes the settings row `render_claim_hold_until` with a time ten minutes ahead
   (`gpu.py::RENDER_HOLD_SECS`). Until then the gateway claims nothing for the built-in renderer
   ([The claim](11-rendering-and-review.md#the-claim)).
3. It looks for a render in progress. If there is one it changes nothing and prints the command to
   apply the change later: `python3 scripts/service.py start tubematic-renderer`.
4. Otherwise it runs `up -d tubematic-renderer` and deletes the row.

The hold is written before the look because SQLite has one writer: a claim either committed before
the hold, and the look sees it, or meets the hold and does not happen. The time is a ceiling, so a
run that dies holding it delays renders by at most ten minutes. Remote renderers are not held,
because the step recreates only the built-in renderer.

## The GPU test

A configured GPU is not proof of a working one. A driver update, an old NVIDIA Container Toolkit or
a hand-run `docker compose up` leaves the container's GPU variables set while Chromium gets no GPU.
A render on the wrong GL device still succeeds, several times slower, so a finished render is no
evidence either.

`render_agent.py::_run_gpu_probe` renders one still of the `GpuProbe` composition through a Node
driver, `renderer/remotion/gpu-probe/run-gpu-probe.mjs`, with the options and environment
`_gl_options` gives a render. The composition creates a WebGL context, reads
`WEBGL_debug_renderer_info`'s unmasked renderer string and prints it on a tagged console line. The
driver catches the line through Remotion's `onBrowserLog` and writes it to a JSON file.

`_judge_probe` passes the test only if the string names NVIDIA and the configured GPU. SwiftShader,
Mesa (llvmpipe) and an integrated GPU fail. A renderer uses the GPU path only while its last test
passed. Otherwise it renders on the CPU, and no video fails for that reason.

- The test is a driver because `npx remotion still` does not pass on a still's console output.
- The answer goes to a file because Remotion fills stdout with page output.
- The Node API does not read `remotion.config.ts`, so the CPU options spell out `swangle`
  (`CPU_GL_OPTIONS`). A test pins them to the config file.
- The driver bundles its own entry point, `src/gpu-probe/index.ts`. The main entry bundles every
  agent-written scene, and one broken scene would fail the bundle and read as a broken GPU.
- The test does not raise. One that cannot start, times out (`GPU_PROBE_TIMEOUT_SECS`, 180, with the
  process-group kill a render gets) or writes no answer reports a failed result with the reason.

### When it runs

- At startup, before the first heartbeat and the first claim. No render runs on an untested GPU, and
  every container start (when a GPU change applies) leaves a fresh result.
- After a render on the GPU fails, stalls or times out, before the result is sent. See
  [A GPU that stops working](#a-gpu-that-stops-working).
- On request: `POST /renderers/<id>/gpu-test` (**Test GPU** on a renderer's card), or
  `POST /render/gpu/test` for the built-in renderer.
- On a renderer with no GPU configured, where it runs the CPU path and records what Chromium gets
  (SwiftShader).

A request stamps `renderers.gpu_probe_requested_at`. The next heartbeat reply says `probe_now` while
that stamp is newer than the start of the last test. Both stamps carry microseconds, because they
are compared as strings. The renderer tests between renders, so a request waits behind a render in
progress, and `GET /renderers` reports it as pending.

### Where the result goes

The renderer keeps the result until a heartbeat or a render result has carried it. The gateway
stores it as `renderers.gpu_probe` (`render_gateway.py::_store_probe`) and sets `gpu_verified` to
the result's `ok`. A render result with `gpu_ok: false` also clears `gpu_verified`.

The API container has no GPU, so every GPU gate reads the `renderers` table.
`tubematic_core/renderers.py::gpu_status` answers for the whole install:

| `status` | Meaning |
|---|---|
| `working` | Some enabled renderer's last test passed |
| `unknown` | None passed, and an enabled renderer has not tested yet |
| `not_usable` | An enabled renderer has a GPU configured and its test failed |
| `not_configured` | None of the above |

`pipeline.py::gpu_probe_status` reads one renderer's test with the same four values. The Cartoon 3D
and mascot gates in the API and the MCP server (`_cartoon3d_gpu_error`, `mascot_gpu_error`) read the
install-wide value, and only `working` passes. A gate that read the built-in
renderer alone would refuse a style another renderer can render. `unknown` has its own message,
because its fix is a test.

`GET /render/gpu` describes the built-in renderer in every field but `status`, because the `gpu`
step configures only that renderer. The dashboard's Renderers panel reads every renderer's test from
`GET /renderers` ([HTTP API](05-http-api.md#renderers)).

## Videos that render on the GPU only

A Cartoon 3D video and a video with a mascot render on the GPU only
(`renderers.py::requires_gpu`). This is a policy. The CPU path can draw them, but a mascot adds
about a tenth of a second to every frame, which in software turns a 90-second Short into hours. A
scene-config whose scene is a Cartoon 3D world counts as Cartoon 3D, so an `auto` video that
resolved to the style is GPU-only once its scene-config is written.

The dashboard, the API and the MCP server refuse the choice unless `gpu_status` is `working`. The
rest of this section applies to a video approved before the GPU stopped working.

### Waiting for a GPU renderer

The scheduler hands a GPU-only video only to a renderer whose last GPU test passed. A renderer is
GPU-capable (`renderers.py::gpu_capable`) when it is enabled, not removed and its last test passed,
whether or not it is online and whatever version it runs. The worker's GPU-wait sweep
(`worker.py::_sweep_gpu_waits`) bounds the wait:

| Situation | The queued video |
|---|---|
| A GPU-capable renderer is online and on the main install's version | Waits for it |
| No renderer is GPU-capable, and every enabled renderer has tested | Goes to `FAILED` at once |
| A GPU-capable renderer exists, but none is online and on the main install's version | Waits up to `GPU_WAIT_SECS` (30 minutes) from when it was queued, then goes to `FAILED` |
| No renderer is GPU-capable, and an enabled renderer has not tested yet | Waits the same 30 minutes, then goes to `FAILED` |

The last row covers the minutes after an upgrade or a renderer restart. The test runs at start and
arrives with the first heartbeat, so until then no renderer counts as GPU-capable on a machine whose
GPU works, and failing the queue would discard work the renderer is about to take.

This `FAILED` does not count against `max_render_retries` and is terminal. A requeue would fail the
same way, and `REVISION_REQUESTED` would hand the video to an agent that cannot repair a GPU. The
comment names every renderer and its state (`renderers.py::gpu_unavailable_reason`: "offline since
…", "needs upgrade", "disabled", "GPU test failed: …"). The human creates the video again once the
GPU works.

### A GPU that stops working

When a render on the GPU fails, stalls or times out, the renderer tests the GPU again before it
reports (`render_agent.py::_failure`) and sends the answer as `gpu_ok`. The gateway routes the
result in `render_results.py::after_render_failure`:

- The test failed and the video is GPU-only: the video goes to `FAILED` with the renderers' state
  and the render's error (`fail_without_gpu`). No retry and no agent session is spent.
- The test passed: the failure belongs to the video and takes the
  [usual path](11-rendering-and-review.md#status-transitions).
- The video is not GPU-only: it takes the usual path either way, and its retry can render on the
  CPU.

A renderer that claims a GPU-only video while its last test did not pass tests again first. If the
test still fails it reports an `error` with `gpu_ok: false`. The video is re-queued, which counts a
retry, and goes to another GPU renderer, or the GPU-wait sweep fails it.

### The mascot's code

A mascot video renders with the version pinned in `videos.mascot_version`, whatever the mascot's
current approved version is. The gateway reads that version's code
(`tubematic_core/mascots.py::code_for`) into the bundle as `mascot.js`. The renderer stages it as
`public/<video_id>/mascot.js` and passes `mascotPath` as a render prop
([the mascot layer](09-remotion-project.md#the-mascot-layer)).

Two cases send the video to `FAILED` at the claim:

- The version is `0` (not pinned) or has no code. The comment says the drawing code cannot be
  staged.
- A Cartoon 3D video also holds a mascot. The API and the MCP server refuse the pair, so only a row
  written another way reaches this. The comment carries `MASCOT_NOT_ON_CARTOON_3D`.

---

## Remote renderers

A remote renderer is `render_agent.py` in the same backend image, run as one container,
`tubematic-remote-renderer`, on another machine. Compared with the built-in renderer it has:

- no `/jobs` volume, and so no stills server
- no shared generated-scene volume, so it stages each job's scenes from the bundle
- no `builtin_renderer_token` secret, so it holds a credential issued at enrollment
- no copy of the gateway's certificate, so it learns it at enrollment and checks it against the
  token's pin

It has a state volume, `tubematic-renderer-state` at `/state` (`TUBEMATIC_RENDERER_STATE`), holding
`renderer.json` with mode 0600.

### The pull model

The main install does not connect to a renderer. Each renderer calls the gateway: a heartbeat every
30 seconds, and a claim every 20 seconds while idle. A renderer needs only an outbound connection to
one port, and the main install publishes only the gateway's port, which is opt-in
(`python3 onboard.py --step renderers`,
[Remote-renderers override](16-infrastructure.md#remote-renderers-override)). The gateway picks the
video, serves the files and decides what a result does. Each renderer runs one render at a time.

### Which renderer gets which video

The scheduler is `tubematic_core/renderers.py::pick_video`. For the renderer that is asking, it
walks the queue in order (`updated_at`, then `id`):

1. It skips a video the caller may not take: a GPU-only video goes only to a renderer whose last
   GPU test passed.
2. It estimates each eligible renderer's finish for the video: the time until that renderer is free
   (its estimate for the render it holds, minus the time already spent) plus its estimate for this
   video.
3. The caller gets the video if its own finish is within `FINISH_TOLERANCE` (1.25 times) of the
   best, or if the video has waited longer than `STARVATION_SECS` (600). Otherwise the scheduler
   moves to the next video.

A slow machine therefore leaves a job to a much faster one, and no video waits indefinitely for the
fast machine.

A renderer is eligible when it is enabled, not removed, on the main install's version, online (a
heartbeat within `ONLINE_SECS`, 120) and, for a GPU-only video, GPU-verified. The caller counts as
online and free, because it is calling and claims only when idle.

An estimate (`estimate_secs`) is the median seconds per frame of the renderer's last five renders of
the same kind (`TIMINGS_WINDOW`, from `render_timings`) times the video's frames. The median keeps
one stalled and retried render from making a machine look slow. With no timings of that kind the
renderer gets a prior: 0.25 seconds a frame on a verified GPU, or 1.5 seconds a frame scaled by its
core count around a four-core machine. A video whose frame count cannot be read is weighed as 2,700
frames (`DEFAULT_FRAMES`).

### Version mismatch

A renderer on a version other than the main install's gets no work. The heartbeat reply says
`needs_upgrade`, a claim answers `409 needs_upgrade`, and the dashboard's Renderers panel marks the
renderer as needing an upgrade. It keeps sending heartbeats and claims nothing until its operator
upgrades it. The versions must be equal, because the scenes an agent wrote import the components of
the main install's version, and another version would compile them against different ones.

### Scenes on a remote renderer

Remotion compiles every file under `src/scenes/generated/` into every render. The built-in renderer
mounts the shared volume the agent writes. A remote renderer has its own copy of that directory in
its image and stages the job's scenes from the bundle into it. It empties the directory before and
after every job (`render_agent.py::_clear_generated`), because a scene left from another job could
break the next render or appear in it. It refuses to empty a mounted directory, so it cannot clear a
shared tree.

### Leases, restarts and lost renderers

A claimed video is held by a lease: `videos.render_lease_until`, set to `LEASE_SECS` (300 seconds)
from the claim. A heartbeat from the renderer that holds it extends the lease by the same amount
while it reports that video and that claim id as the one being rendered. A renderer that went idle
does not keep a lease alive, and neither does a heartbeat for an earlier claim of the same video.

Every claim has its own random id, stored in `videos.render_claim_id`, and the renderer names it on
the bundle, the upload and the result. A renderer that lost its lease cannot touch the claim that
took the video over, even when it is the same renderer claiming again. A lease can run out while a
request is in flight, so the gateway checks the claim again when it renames an upload into place
(`409 claim_lost`) and inside the transaction that routes a failure result
(`render_results.py::_claim_guard`). The header and the status codes are under
[Leases](19-render-gateway.md#leases).

A held render can end without a result in three ways. Each goes through
`render_results.py::requeue_interrupted`: `render_fail_count` goes up by one, and the video returns
to `RENDER_QUEUED`, or goes to `FAILED` once the count passes `max_render_retries`.

| How | Who notices | Comment starts |
|---|---|---|
| The renderer's process restarted (it stopped, its container restarted, or `--step gpu` recreated it) | The gateway, at the renderer's first heartbeat, which carries `started: true` | "Render interrupted by renderer restart" |
| The renderer stopped sending heartbeats (a machine switched off, a lost network, or a renderer removed on the dashboard, whose heartbeats then get `401`) | The worker's lease sweep (`worker.py::_sweep_render_leases`), once the lease has run out | "Render lost: <renderer> stopped reporting" |
| The row is `RENDERING` with no renderer (a render in flight across an upgrade from a version without the gateway) | The worker's lease sweep | "Render interrupted by the upgrade" |

Under the cap the comment ends "automatically re-queued." Past it the comment gives the count and
the limit and ends "giving up."

A lost render counts as a failure, so that a render that kills its renderer every time (out of
memory, for example) reaches `FAILED`. With the default `max_render_retries` of 1, two interruptions
in one video's life move it there.

A video is re-queued only when its render is known to be gone:

- A restarted renderer says so in its first heartbeat and claims nothing until that heartbeat has
  gone through, so its renders are re-queued at once.
- A renderer that does not come back is detected by its silence, which the lease measures.
- A restart of the worker or the API says nothing about a running render, so neither re-queues
  anything at start.
- The lease sweep's `UPDATE` checks again that the lease is past, so a heartbeat that extended it
  after the sweep looked wins.
- An uploaded render is not re-queued. Once the mp4 has arrived the video belongs to the review.

The gateway can stop a render. The heartbeat reply's `stop` list names, as `{video_id, claim_id}`
pairs, every claim this renderer reports or holds that has lost its video: archived, moved by a
human, or re-queued after its lease ran out. The renderer kills that render's process group and
discards it without a result (`render_agent.py::_stop_job`). It applies a reply only to the job its
own request reported (the `_Job` the heartbeat thread read before sending). A delayed reply about an
earlier claim would otherwise stop the renderer's newer claim of the same video, and each render
lost that way counts towards `max_render_retries`.

### The remote container

`render_agent.py::_load_identity` decides who the renderer is. With `TUBEMATIC_RENDERER_BUILTIN`
unset it reads the state file:

- On the first start the file holds no credential and `TUBEMATIC_ENROLL_TOKEN` holds a token, so the
  renderer enrolls (`render_agent.py::enroll`; the steps are under
  [Enrollment](19-render-gateway.md#enrollment)). The state file then holds the credential, the
  certificate, the pin, the gateway URL, a `machine_id` and the hash of the token's secret
  (`enrolled_with`).
- On a later start with the same token still set (a container started by hand), the secret's hash
  matches `enrolled_with`, so the token is ignored and the saved credential is used.
- A different token enrolls the same machine again under the same `machine_id`. If that fails while
  a usable credential is saved, the renderer carries on with it.
- With neither a credential nor a token the renderer cannot start. It logs why and retries every
  `ENROLL_RETRY_SECS` (60).

`TUBEMATIC_GATEWAY_URL`, when set, overrides the saved address, and the host script sets it. The
credential's lifetime is under [Credentials](19-render-gateway.md#credentials).

The enrollment and every heartbeat carry the renderer's compute
(`render_agent.py::_compute_report`: CPU count, `MemTotal` and every GPU `nvidia-smi` lists in the
container), its version and its name (`TUBEMATIC_RENDERER_NAME`, else the container's host name).
The scheduler's prior reads that compute.

A rotated credential arrives in a heartbeat reply. The renderer writes it to the state file before
it uses it (`RemoteIdentity.save_rotated`), so a renderer that stops between the two does not hold a
credential the gateway has dropped. On `401 credential_expired` the renderer logs and reports
`credential expired: …` and needs a new enrollment.

A remote renderer has no `/logs` mount and writes no JSONL file for the dashboard's Logs page. Its
lines are in `docker logs tubematic-remote-renderer` on its own machine, and the main install sees
its `last_error` on its row in `renderers`.

### The host script

`scripts/tubematic_remote_renderer.py` is what an operator runs on the remote machine: `install`,
`upgrade`, `remove` and `status` ([Remote Renderers](../user-guide/11-remote-renderers.md)). It
uses the Python 3.10+ standard library only, because that machine has no checkout and nothing
installed but Docker, and a test fails the build if it imports anything else. It ships in the
release tarball's `scripts/` and as a release asset covered by `CHECKSUMS.txt`
([Releases](18-releases.md#what-a-release-consists-of)).

- The pin is checked before anything is sent. `fetch_pinned_cert` reads the certificate with
  `ssl.get_server_certificate` and compares its sha256 with the token's pin. Only then does the
  script read `GET /v1/version`, over a context that trusts that certificate alone. A wrong address,
  a proxy that terminates TLS or an impostor gets a TLS handshake and nothing else.
- The image is `ghcr.io/<owner>/tubematic-backend:<version>` at the main install's version, or the
  one given with `--image`. The owner is hardcoded from `tubematic_core.version.GITHUB_REPO` (the
  script cannot import it, and a test pins the two). The release workflow overwrites it with the
  owner that release pushed its images under, so a fork's renderers pull the fork's image.
- `upgrade` reads the version again, so a remote renderer follows the main install only when its
  operator runs `upgrade`.
- The container matches the composed renderer: the same command, `shm_size` 2g,
  `PUPPETEER_EXECUTABLE_PATH` and `--restart unless-stopped`. With a GPU it adds
  `--gpus device=<uuid>` and the environment the Compose override sets
  (`NVIDIA_DRIVER_CAPABILITIES=graphics,utility`, `TUBEMATIC_GPU_UUID`, `TUBEMATIC_GPU_NAME`,
  `TUBEMATIC_HOST_GPUS`). Tests pin each value against its source.
- The script's state file, `~/.tubematic-remote-renderer.json` (0600), holds the gateway URL, the
  pin, the image, the name and the GPU choice. `upgrade` recreates the container from it without a
  token and keeps the state volume, and with it the credential.

The token reaches neither a command line nor a file:

- The dashboard's command is a bare `install`. The script reads the token with `getpass`, or one
  line of stdin with `--token-stdin`. A command line is readable by every user of the machine
  (`ps`, `/proc/<pid>/cmdline`) and kept in shell history, and the token stays redeemable for an
  hour.
- `--token <value>` is refused before anything is sent. The option is declared so that argparse does
  not read it as an abbreviation of `--token-stdin`.
- `docker run` gets a bare `-e TUBEMATIC_ENROLL_TOKEN`, so Docker copies the value from the script's
  environment. Docker then stores it in the container's configuration (`docker inspect`).
- `install` therefore runs that first container with `--restart no` until the log shows the
  renderer has enrolled (`enroll_container`). It then removes the container and starts the real one
  from the same arguments without the token.
- Any other outcome (a refusal, a stopped container, no sign within 60 seconds, a failed
  `docker run`, Ctrl-C) removes the token-bearing container (`discard_enrollment`), and the state
  volume too unless an earlier install left it.

`install` and `upgrade` watch the container's log for up to 60 seconds for these words, which are a
contract between the two files (a comment in `render_agent.py` says so):

| Words in the log | Meaning |
|---|---|
| `enrolled`, `first heartbeat` | Connected. For `install`, the token-bearing container may now be replaced |
| `enrollment_invalid`, `credential expired` | Refused |
| `needs upgrade` | The renderer runs another version |
