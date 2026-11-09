# GPU Rendering

How to let the renderer use an NVIDIA graphics card, how to tell whether it really is, and what
happens when it cannot.

**This is optional for every feature but two.** Without a GPU every video renders on the CPU, exactly
as before, and nothing on this page needs doing — except that the **Cartoon 3D (experimental)** visual style and **mascots (experimental)** cannot
be chosen. Cartoon 3D draws a 3D world for every frame, which takes about an hour per Short on a CPU,
and a mascot's drawing, a tenth of a second a frame on a GPU, is about thirty times slower on a CPU, which adds hours to a Short.
Both are offered only while the renderer's GPU is working. A video that has already been approved
with either, whose GPU then stops working, is not rendered on the CPU: it fails with a comment saying
why, and is created again once the GPU is back. **Only NVIDIA GPUs are supported.** Intel
and AMD GPUs, integrated or not, are never used.

---

## What it changes

Each frame of a video is drawn by Chromium inside the `tubematic-renderer` container. Without a GPU,
Chromium draws its graphics in software on the CPU. With one, it draws them on the card. Measured on
one machine (a 6-core Intel i5-8500 and a GeForce GTX 1650):

| | CPU | GPU |
|---|---|---|
| An ordinary 2D scene, 150 frames at 1080×1920 | 116 s | 35 s |
| A 3D scene (three.js), per frame | about 1.1 s | about 0.17 s |

The picture is the same either way: frames rendered both ways differ by less than one colour level
on average. The CPU is also freed up: on the GPU a render uses about one core instead of all of
them.

Rendering is the only thing the GPU is used for. The API, the MCP server, the agent and the
dashboard do not use it.

---

## What you need

1. **An NVIDIA GPU with its driver installed**, so that `nvidia-smi` lists it.
2. **The NVIDIA Container Toolkit**, so that Docker can hand the GPU to a container.
3. **The `gpu` onboarding step**, which picks the GPU and hands it to the renderer.

The steps below are for Ubuntu. On another distribution, follow its own instructions for the first
two.

### 1 · Install the NVIDIA driver

```bash
sudo ubuntu-drivers install
sudo reboot
nvidia-smi        # must list your GPU
```

**If `nvidia-smi` says it cannot communicate with the NVIDIA driver after the reboot, check Secure
Boot first.** With Secure Boot on, the kernel refuses a driver module signed with a key that was
never enrolled, and that looks exactly like having no GPU at all.

```bash
mokutil --sb-state     # "SecureBoot enabled" makes this the likely cause
```

Either enroll the key the driver was signed with (Ubuntu asks for a password while installing the
driver, then shows a blue *Enroll MOK* screen at the next boot — choose **Enroll MOK** and type that
password), or turn Secure Boot off in the machine's firmware settings.

### 2 · Install the NVIDIA Container Toolkit

These are NVIDIA's own instructions, from the
[Container Toolkit install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html):

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

sudo nvidia-ctk runtime configure --runtime=docker   # registers the `nvidia` runtime with Docker
sudo systemctl restart docker
```

Restarting Docker restarts any running containers, Tubematic's included.

Check that a container can see the GPU:

```bash
docker info | grep -i nvidia                              # the `nvidia` runtime is listed
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

### 3 · Pick the GPU

On a new install, the wizard's `gpu` step does this for you, right before the renderer is created
(see [The eleven steps](02-installing.md#the-eleven-steps)). On an install that is already running,
run it on its own from the install directory:

```bash
python3 onboard.py --step gpu
```

It lists every NVIDIA GPU on the machine, plus **None — render on the CPU**, and asks which one the
renderer gets. Then it:

- writes your choice to `~/.tubematic-data/compose.gpu.json`, a Compose file that hands that GPU to
  `tubematic-renderer` and nothing else. It lives with your data, not in the install directory, so
  upgrades keep it;
- recreates `tubematic-renderer` so the change takes effect. It never interrupts a render: it stops
  new renders from starting while it checks, and if one is already in progress (or a publish is
  uploading) it says so, and you apply the change afterwards with
  `python3 scripts/service.py start tubematic-renderer`. Until then, `service.py status` says the
  renderer is still on the previous choice.

The step asks nothing when there is no NVIDIA driver or no Container Toolkit: it says which is
missing and leaves rendering on the CPU. The one exception is a GPU chosen earlier whose toolkit has
since gone: then it offers to go back to the CPU (the default) or keep the choice while you reinstall
the toolkit, because Docker cannot start the renderer while the choice stands. Choosing **None**
removes the file and puts the renderer back on the CPU.

---

## Checking it is used

Open **Settings → Rendering** on the dashboard. The **GPU** section shows one of:

| Status | Meaning |
|---|---|
| **Rendering on the GPU** (green) | The renderer tested the GPU you chose and is using it |
| **GPU not usable — rendering on the CPU** (red) | A GPU is chosen, but the test showed Chromium could not use it. **Why** gives the reason. Videos still render, on the CPU |
| **Rendering on the CPU** | No GPU is chosen |
| **Not tested yet** | The renderer has never finished a test: a new install, or the first minute after upgrading from a version without GPU support |

**Chromium sees** is the graphics device Chromium actually got, read from inside a test frame: first
in plain words, then the exact string Chromium reports, which is the evidence. On the GPU it names
your card, for example `ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL ES
3.2)`. On the CPU it names SwiftShader, Chromium's software renderer — what Remotion calls `swangle`
(`ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) …), SwiftShader driver)`).

The renderer runs that test every time it starts. With a GPU chosen, **Test GPU** asks it to run it
again — after a driver update, say — and the answer usually appears within a minute, or after the
current render if one is in progress. Without a GPU there is no button: the answer cannot change
until you choose one, and choosing one recreates the renderer, which tests as it starts.

From a terminal, `python3 scripts/service.py status` (or `python3 upgrade.py --check`) prints the
same thing on its GPU line.

### Why "it rendered" is not proof

A render that finishes proves nothing about the GPU. If Chromium is given the wrong graphics device,
the render still works, only several times slower. So the renderer never trusts that a GPU works
because it was configured, or because a render finished. It uses the GPU **only** after a test frame
showed Chromium's graphics device to be the card you chose. Anything else, including another
graphics device or no device at all, means CPU rendering. A GPU that stops working therefore slows
rendering down, but never fails a video. How this works is in
[Rendering and Review](../developer/11-rendering-and-review.md#the-gl-renderer).

---

## Things that turn the GPU off

- **Starting containers with a bare `docker compose up`.** Tubematic's own commands read
  `compose.gpu.json`; a plain `docker compose up` does not, and it recreates the renderer without
  the GPU. Use `python3 scripts/service.py start` instead, which reads it. Rendering carries on, on
  the CPU. The dashboard cannot tell this apart from having chosen no GPU — the renderer was not told
  about one — so it shows **Rendering on the CPU**; `python3 scripts/service.py status` is what warns
  that a GPU is chosen but the renderer has not reported it.
- **A driver update.** Reboot after updating the NVIDIA driver; until then the driver and the
  libraries the container is given disagree, and the test fails. After a render on the GPU fails or
  times out, the renderer tests the GPU again, so the next render falls back to the CPU instead of
  failing the same way.
- **Taking the GPU out, or removing the Container Toolkit.** Docker then cannot start the renderer at
  all with `compose.gpu.json` in place. `python3 upgrade.py` checks for this before it stops anything,
  and refuses with the command that fixes it. Run `python3 onboard.py --step gpu` to pick another GPU
  or **None**.

---

## Troubleshooting

| What you see | Likely cause | Fix |
|---|---|---|
| The `gpu` step says no NVIDIA GPU was found | No driver, or the driver is not loaded | Step 1. Check Secure Boot |
| The `gpu` step says Docker has no `nvidia` runtime | The Container Toolkit is missing, or `nvidia-ctk runtime configure` was not run | Step 2, including the Docker restart |
| **Rendering on the CPU** although you chose a GPU (and `service.py status` warns about it) | The renderer was recreated without the GPU, usually by a bare `docker compose up` | `python3 scripts/service.py start tubematic-renderer` |
| Red, and **Why** says Chromium could not create a WebGL context | The container has the GPU but not its graphics libraries: a driver/library mismatch after a driver update, or an old Container Toolkit | Reboot after a driver update; update the Container Toolkit |
| Red, **Why** says Chromium could not create a WebGL context, and `docker exec tubematic-renderer ls /usr/share/glvnd/egl_vendor.d/` lists no `10_nvidia.json` | The Container Toolkit mounted the driver libraries but not the NVIDIA EGL vendor file, so Chromium fell back to Mesa. Seen with Docker running inside another container | Switch the toolkit to CDI mode: `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`, `sudo nvidia-ctk config --set nvidia-container-runtime.mode=cdi --in-place`, then `python3 scripts/service.py start tubematic-renderer` |
| Red, and **Chromium sees** names another device (Intel, Mesa, `llvmpipe`) | Chromium picked a different graphics device than the GPU | Report it with `python3 scripts/collect_diagnostics.py` (see [Troubleshooting](08-troubleshooting.md)) |
| `upgrade.py` refuses, naming `compose.gpu.json` | The chosen GPU or the Container Toolkit is gone | `python3 onboard.py --step gpu`, then upgrade again |

**Kasm Workspaces.** The Tubematic workspace image runs without a GPU attached, because an attached
GPU crash-loops its desktop (see [Installing in Kasm Workspaces](02-installing.md#installing-in-kasm-workspaces)).
GPU rendering needs Tubematic installed directly on a host.
