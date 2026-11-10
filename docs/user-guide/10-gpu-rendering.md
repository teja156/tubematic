# GPU Rendering

How to let the renderer use an NVIDIA graphics card, how to check that it does, and what happens
when it cannot.

A GPU is optional. Without one, every video renders on the CPU, and you need none of the steps
below. Two features need a GPU:

- The Cartoon 3D (experimental) visual style. It draws a 3D world for every frame, which takes about
  an hour per Short on a CPU.
- Mascots (experimental). Drawing a mascot takes about a tenth of a second per frame on a GPU. On a
  CPU it is about thirty times slower, which adds hours to a Short.

You can choose either one only while some renderer's GPU is working. That can be this machine's GPU
or a [remote renderer](11-remote-renderers.md)'s. Tubematic sends such a video only to a renderer
whose GPU test passed. If the GPU stops working after you approved such a video, the video does not
render on the CPU. It fails with a comment that says why. Create the video again once the GPU works.

Only NVIDIA GPUs are supported. Tubematic does not use Intel or AMD GPUs, integrated or separate.

The steps below set up the GPU of the machine Tubematic is installed on. To render on a GPU in
another machine, install the driver and the Container Toolkit there (steps 1 and 2), then follow
[Remote renderers](11-remote-renderers.md). Its setup script picks the GPU in place of step 3.

---

## What it changes

Chromium draws each frame of a video inside the `tubematic-renderer` container. Without a GPU,
Chromium draws its graphics in software on the CPU. With one, it draws them on the card. These
figures are from one machine (a 6-core Intel i5-8500 and a GeForce GTX 1650):

| | CPU | GPU |
|---|---|---|
| An ordinary 2D scene, 150 frames at 1080×1920 | 116 s | 35 s |
| A 3D scene (three.js), per frame | about 1.1 s | about 0.17 s |

The picture is the same either way. Frames rendered both ways differ by less than one colour level
on average. A GPU render also leaves the CPU free: it uses about one core, and a CPU render uses all
of them.

Only rendering uses the GPU. The API, the MCP server, the agent and the dashboard do not.

---

## What you need

1. An NVIDIA GPU with its driver installed, so that `nvidia-smi` lists it.
2. The NVIDIA Container Toolkit, so that Docker can hand the GPU to a container.
3. The `gpu` onboarding step, which picks the GPU and hands it to the renderer.

The steps below are for Ubuntu. On another distribution, follow its own instructions for the first
two.

### 1 · Install the NVIDIA driver

```bash
sudo ubuntu-drivers install
sudo reboot
nvidia-smi        # must list your GPU
```

If `nvidia-smi` says after the reboot that it cannot communicate with the NVIDIA driver, check
Secure Boot first. With Secure Boot on, the kernel refuses a driver module signed with a key that
was never enrolled, and the machine then looks as if it has no GPU.

```bash
mokutil --sb-state     # "SecureBoot enabled" makes this the likely cause
```

To fix it, enroll the key the driver was signed with, or turn Secure Boot off in the machine's
firmware settings. Ubuntu asks for a password while it installs the driver, and shows a blue Enroll
MOK screen at the next boot. To enroll the key, choose **Enroll MOK** on that screen and type the
password.

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

On a new install, the wizard's `gpu` step does this just before it creates the renderer (see
[Steps](15-command-reference.md#steps)). On an install that is already running, run the step by
name from the install directory:

```bash
python3 onboard.py --step gpu
```

It lists every NVIDIA GPU on the machine and a **None** option that renders on the CPU, and asks
which one the renderer gets. Then it:

- Writes your choice to `~/.tubematic-data/compose.gpu.json`, a Compose file that hands that GPU to
  `tubematic-renderer` and to no other container. The file is kept with your data, outside the
  install directory, so upgrades keep it.
- Recreates `tubematic-renderer` so the change takes effect. It does not interrupt a render. It
  stops new renders from starting while it checks. If a render is already in progress, it says so,
  and you apply the change afterwards with `python3 scripts/service.py start tubematic-renderer`.
  Until you do, `service.py status` says the renderer is still on the earlier choice.

If the machine has no NVIDIA driver or no Container Toolkit, the step asks nothing. It says which is
missing and leaves rendering on the CPU. There is one exception. If you chose a GPU earlier and the
toolkit has since been removed, Docker cannot start the renderer while that choice stands. The step
then offers to go back to the CPU (the default), or to keep the choice while you reinstall the
toolkit.

Choosing **None** removes the file and puts the renderer back on the CPU.

---

## Checking it is used

Open **Settings → Rendering** on the dashboard. The **Renderers** panel has a card for every
renderer, with this machine's built-in one first. The **GPU** line on a card names each GPU the
renderer sees, with its memory, and shows one of these:

| GPU line | Meaning |
|---|---|
| **✓ verified** (green) | The renderer tested the GPU you chose and is using it |
| A reason, in red | A GPU is chosen, and the test showed that Chromium could not use it. The line gives the reason. Videos still render, on the CPU |
| **not in use** (renders on the CPU) | The renderer sees the GPU, and you did not choose it |
| **None** (renders on the CPU) | No GPU is chosen, and the renderer sees none |
| **not tested yet** | The renderer has not finished a test. This is a new install, or the first minute after an upgrade |

The **Chromium sees** line shows the graphics device Chromium got, read from inside a test frame. It
gives the device in plain words, then the string Chromium reports. On the GPU the string names your
card, for example `ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL ES 3.2)`. On
the CPU it names SwiftShader, Chromium's software renderer.

The renderer runs that test every time it starts. On a renderer with a GPU, **Test GPU** on its card
asks it to run the test again, for example after a driver update. The answer usually appears within
a minute, or after the current render if one is in progress. Each renderer tests its own GPU, so
each card has its own button. A renderer without a GPU has no button. Its answer cannot change until
you choose a GPU, and choosing one recreates the renderer, which tests as it starts.

From a terminal, `python3 scripts/service.py status` (or `python3 upgrade.py --check`) prints the
same result on its GPU line.

### Why "it rendered" is not proof

A render that finishes proves nothing about the GPU. If Chromium gets the wrong graphics device, the
render still finishes and takes several times longer. The renderer therefore uses the GPU only after
a test frame showed that Chromium's graphics device is the card you chose. A configured GPU or a
finished render does not count as proof. Any other test result, including another graphics device or
no device, means CPU rendering.

A GPU that stops working therefore slows ordinary videos down and does not fail them. Cartoon 3D and
mascot videos are the exception, because they render on a GPU only. How the test works is in
[GPU and Remote Renderers](../developer/20-gpu-and-remote-renderers.md#the-gpu-test).

---

## Things that turn the GPU off

- A bare `docker compose up` recreates the renderer without the GPU. Tubematic's own commands read
  `compose.gpu.json`, and a plain `docker compose up` does not. Rendering carries on, on the CPU.
  Use `python3 scripts/service.py start`, which reads the file. The dashboard cannot tell this case
  from having chosen no GPU, because the renderer was not told about one, so its GPU line reads
  **None**. `python3 scripts/service.py status` warns that a GPU is chosen and the renderer has not
  reported it.
- A driver update makes the GPU test fail until you reboot. Until then, the driver and the libraries
  the container is given disagree. After a render on the GPU fails or times out, the renderer tests
  the GPU again, so the next render falls back to the CPU and does not fail the same way.
- Removing the GPU or the Container Toolkit stops Docker from starting the renderer while
  `compose.gpu.json` is in place. `python3 upgrade.py` checks for this before it stops anything, and
  refuses with the command that fixes it. Run `python3 onboard.py --step gpu` to pick another GPU or
  **None**.

---

## Troubleshooting

| What you see | Likely cause | Fix |
|---|---|---|
| The `gpu` step says no NVIDIA GPU was found | No driver, or the driver is not loaded | Step 1. Check Secure Boot |
| The `gpu` step says Docker has no `nvidia` runtime | The Container Toolkit is missing, or `nvidia-ctk runtime configure` was not run | Step 2, including the Docker restart |
| The GPU line reads **None** although you chose a GPU, and `service.py status` warns about it | The renderer was recreated without the GPU, usually by a bare `docker compose up` | `python3 scripts/service.py start tubematic-renderer` |
| Red, and the reason says Chromium could not create a WebGL context | The container has the GPU but not its graphics libraries: a driver/library mismatch after a driver update, or an old Container Toolkit | Reboot after a driver update; update the Container Toolkit |
| Red, the reason says Chromium could not create a WebGL context, and `docker exec tubematic-renderer ls /usr/share/glvnd/egl_vendor.d/` lists no `10_nvidia.json` | The Container Toolkit mounted the driver libraries but not the NVIDIA EGL vendor file, so Chromium fell back to Mesa. Seen with Docker running inside another container | Switch the toolkit to CDI mode: `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`, `sudo nvidia-ctk config --set nvidia-container-runtime.mode=cdi --in-place`, then `python3 scripts/service.py start tubematic-renderer` |
| Red, and **Chromium sees** names another device (Intel, Mesa, `llvmpipe`) | Chromium picked a different graphics device than the GPU | Report it with `python3 scripts/collect_diagnostics.py` (see [Troubleshooting](08-troubleshooting.md)) |
| `upgrade.py` refuses, naming `compose.gpu.json` | The chosen GPU or the Container Toolkit is gone | `python3 onboard.py --step gpu`, then upgrade again |

In Kasm Workspaces, the Tubematic workspace runs without a GPU attached, because an attached GPU
makes its desktop restart in a loop (see
[Installing in Kasm Workspaces](02-installing.md#installing-in-kasm-workspaces)). GPU rendering needs
Tubematic installed directly on a host.
