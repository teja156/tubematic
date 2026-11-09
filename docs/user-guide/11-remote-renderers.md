# Remote Renderers

How to let other machines render videos for your Tubematic install: turning the feature on, adding a
machine, keeping it on the right version, and taking it away again.

In this page the machine Tubematic is installed on — the one with the dashboard, the database and
your videos — is called **main**. A **remote renderer** is another machine that renders videos for
main and does nothing else.

**This is optional.** Out of the box main renders every video itself, with its built-in renderer,
and nothing on this page needs doing. Remote renderers are off until you turn them on, and turning
them on changes nothing else about how Tubematic works.

---

## When it helps

Rendering is the slow part of making a video: Chromium draws every frame, and on a CPU that can take
most of an hour for a long Short. A remote renderer helps when another machine can do that work
better or alongside main:

- **A bigger machine.** A box with more cores renders faster on the CPU, and main stays free for the
  dashboard and the agents.
- **A machine with an NVIDIA GPU**, when main has none. Cartoon 3D and mascots render on a GPU only
  (see [GPU rendering](10-gpu-rendering.md)), and a remote GPU renderer whose GPU test passed is
  enough to offer them.
- **More than one video at a time.** Each renderer renders one video at a time, so two renderers
  work through a queue twice as fast.

**Which renderer gets which video is decided by main**, every time a renderer asks for work. It
estimates when each renderer would finish the video — from how long that renderer took over its
recent renders, and what it is busy with now — and hands the video to the one that would finish
first, so a slow machine never takes a job a much faster one would finish sooner. A video that has
waited ten minutes goes to whichever renderer asks, so nothing waits for ever. **A Cartoon 3D or
mascot video only ever goes to a renderer whose GPU test passed.** The built-in renderer keeps
taking work alongside the remote ones; disable it on the dashboard if you want main to render
nothing. How the choice is made is in
[Rendering and Review — Which renderer gets which video](../developer/11-rendering-and-review.md#which-renderer-gets-which-video).

---

## How it works

A remote renderer is one Docker container, `tubematic-remote-renderer`, running the same image as
main's own renderer. It has no database, no copy of your video library and none of your API keys.
It reaches main over **HTTPS on one port (4443 by default)**, the *render gateway*, and through it
only:

1. asks for a video to render;
2. downloads that one video's files (its audio, timeline, scenes and images);
3. renders it, and uploads the finished mp4 to main;
4. reports how the render went, and every 30 seconds that it is still alive.

Main stores the video, runs the AI review and does everything else, exactly as it does for its own
renders. The renderer proves who it is with a credential main issued to it, and it trusts exactly
one certificate: main's own, which it checked when it was added (see
[Why nothing may sit in front of the port](#why-nothing-may-sit-in-front-of-the-port)).

---

## What you need

**On main:**

- Tubematic 2.1.0 or newer, installed and running.
- The `renderers` step run once (below), which publishes the gateway's port.

**On each remote renderer:**

- **Linux with Docker Engine**, usable by the user who runs the script (in the `docker` group, or
  with `sudo` — see [Running it with sudo](#running-it-with-sudo)). The published image is built for
  x86-64. Installing Docker on Ubuntu is covered in
  [Installing — Installing Docker on Ubuntu](02-installing.md#installing-docker-on-ubuntu).
- **Python 3.10 or newer**, to run the setup script. It uses nothing but the standard library.
- **For a GPU:** the NVIDIA driver and the NVIDIA Container Toolkit, set up exactly as for main in
  [GPU rendering — What you need](10-gpu-rendering.md#what-you-need) (steps 1 and 2; there is no
  onboarding step on a remote renderer — the script picks the GPU).
- **A network path to main** on the gateway's port: the renderer opens the connection, main never
  connects to it. Nothing needs to reach the renderer.
- **Internet access**, or another way to get the image: the script pulls
  `ghcr.io/teja156/tubematic-backend` at main's version.
- **The same Tubematic version as main.** The script sees to this: it asks main for its version and
  runs the image for exactly that version. A renderer on any other version is listed as
  **needs upgrade** and gets no work (see [Upgrading](#upgrading)).

---

## Turning remote renderers on

On main, from its install directory:

```bash
python3 onboard.py --step renderers
```

This step is **opt-in**: a full install never runs it, so remote renderers stay off until you do.
It asks two things:

1. **Remote renderers: On or Off.**
2. **The address renderers use to reach this machine** — an IP address or a DNS name the remote
   machines can resolve, optionally with `:port` (default **4443**). For example `192.168.1.20`,
   `render.example.lan:8443`, or an IPv6 address in brackets, `[2001:db8::20]`. Not `localhost`, a
   loopback, multicast or broadcast address, an IPv6 link-local address (`fe80::…`, which needs an
   interface name to dial), and no `http://` or `https://`. An IPv4 address written as IPv6
   (`[::ffff:127.0.0.1]`) is judged as the IPv4 address it is.

Then it:

- writes `~/.tubematic-data/compose.renderers.json`, a Compose file that publishes the gateway on
  that port on every network interface of main (every IPv6 interface too, when the address is IPv6).
  It lives with your data, so upgrades keep it;
- stores the address, which the dashboard puts into every enrollment token;
- recreates `tubematic-api` so the port opens. That takes a few seconds; a render in progress carries
  on;
- checks that the port answers with the gateway's own certificate. This is a check on main itself
  (`127.0.0.1`): it proves the port is published, not that the address reaches main from your
  renderer machines, and the step says so. The renderer's `install` is what tests the address, when
  it first connects;
- prints the firewall note below, and offers to print a first enrollment token. The default is no:
  the dashboard makes one whenever you need it (see [Adding a renderer](#adding-a-renderer)).

The file, the stored address and the running `tubematic-api` change together or not at all:

- **A post is uploading** (the upload runs inside `tubematic-api`, which a recreate would cut off):
  nothing is changed, and the step tells you to run it again once the upload has finished.
- **`docker compose up` fails** (another program holds the port, say): the step puts the previous
  file and address back, starts `tubematic-api` on them again, and fails with Docker's error.
- **The stack is stopped** (`python3 scripts/service.py stop`): the choice is saved and nothing is
  started — the port opens or closes the next time the whole stack starts
  (`python3 scripts/service.py start`).

Re-run it to change the address or the port, or choose **Off** to turn remote renderers off again:
that closes the port, and renderers already added stay listed on the dashboard, offline, until you
remove them. `python3 scripts/service.py status` (or `python3 upgrade.py --check`) prints whether
remote renderers are on and the address they use.

**Changing the address does not move renderers already added.** Each one keeps dialling the address
it was added with. Add them again (remove, then add with a new token) after a change.

### Allow the port through your firewall — from your renderers only

The gateway asks every caller for a credential and serves only TLS, but there is no reason for
anything but your renderers to reach it. Allow TCP on the port (4443 by default) into main **from
your renderer machines only**.

**A `ufw` rule alone does not do this.** Docker publishes ports with firewall rules of its own that
traffic meets before `ufw`'s, so a published port is reachable whatever `ufw` says. Restrict it in
one of two places instead:

- **Your network or cloud firewall** (a router, a security group), in front of main. The simplest.
- **Docker's `DOCKER-USER` chain** on main, which Docker consults before its own rules. For example,
  to drop connections to port 4443 from anywhere outside `198.51.100.0/24`:

  ```bash
  sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 4443 --ctdir ORIGINAL \
    ! -s 198.51.100.0/24 -j DROP
  ```

  Match on the *original* port with `conntrack` as above, because by the time a packet reaches
  `DOCKER-USER` its destination has already been rewritten to the container's. Rules added this way
  do not survive a reboot unless you save them (for example with `iptables-persistent`). See
  Docker's [Packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

**With an IPv6 address, the `iptables` rule above does not cover the IPv6 listener.** `iptables`
filters IPv4 only, and an IPv6 address makes main publish the port on `[::]` as well. Restrict both
families:

- **Simplest: a network or cloud firewall that filters IPv4 and IPv6**, in front of main.
- **On main:** Tubematic's Compose network is IPv4-only, and for that Docker hands the `[::]` port
  to its own proxy process on main, which accepts the connections as an ordinary program would. They
  therefore pass main's IPv6 `INPUT` chain, not `DOCKER-USER`, so filter them there. For example, to
  drop connections to port 4443 from anywhere outside `2001:db8:5::/64`:

  ```bash
  sudo ip6tables -I INPUT -p tcp --dport 4443 ! -s 2001:db8:5::/64 -j DROP
  ```

  Check afterwards, from a machine outside that range, that the port no longer answers
  (`nc -6 -vz <main's IPv6 address> 4443`): if your Docker daemon was set up differently (an
  IPv6-enabled network, or the userland proxy turned off), the packets are forwarded instead, and the
  rule belongs in `ip6tables`' `DOCKER-USER` chain, written like the IPv4 one above. Save it the
  same way (`iptables-persistent` saves IPv6 rules too, to `/etc/iptables/rules.v6`).

### Why nothing may sit in front of the port

**Never put a TLS-terminating proxy (Caddy, nginx, a load balancer, a tunnel that decrypts) in
front of the gateway's port.** The gateway uses a self-signed certificate made at install, and a
renderer trusts that one certificate and nothing else: the enrollment token carries its
fingerprint (a *pin*), and the renderer checks it before it sends anything. A proxy presents its own
certificate, the fingerprint does not match, and the renderer refuses to connect — by design, since
that is also exactly what an attacker in the middle would look like. Plain port forwarding (NAT, a
TCP-level forward) is fine: the renderer still talks TLS to the gateway itself. The dashboard's own
HTTPS proxy from [Remote Access](09-remote-access.md) is a different port and is unaffected.

Why the pin is the certificate and not a certificate authority is in
[HTTP API — TLS and the certificate pin](../developer/05-http-api.md#tls-and-the-certificate-pin).

---

## Adding a renderer

### 1 · Make an enrollment token

On the dashboard, open **Settings → Rendering**, press **Add renderer**, give the machine a name (it
is how the dashboard lists it, at most 60 characters) and press **Create token**. The dialog shows the
token, and the command to run on the renderer machine. The command does not contain the token: the
script asks for it.

**The token is shown once, works once and lasts one hour.** Closing the dialog forgets it; a token
that expired or was already used is refused, and you simply make another. Treat it as a password
until it is used: it carries a one-time secret that adds a renderer to your install.

**Add renderer** is greyed out, with the command to run, until remote renderers are turned on.

### 2 · Get the script onto the renderer machine

The script is `tubematic_remote_renderer.py`. It is one file, and the renderer machine needs no
Tubematic install. Either copy it from main's install directory, where every install has it under
`scripts/`:

```bash
# on main, from the install directory
scp scripts/tubematic_remote_renderer.py you@renderer-host:
```

or download it, with its checksum, from the release your main runs. Remote renderers arrive in
2.1.0:

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/v2.1.0/tubematic_remote_renderer.py
curl -LO https://github.com/teja156/tubematic/releases/download/v2.1.0/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing   # must say: tubematic_remote_renderer.py: OK
```

`CHECKSUMS.txt` also lists the release tarball; `--ignore-missing` skips it.

### 3 · Run it

On the renderer machine, run the command the dialog showed:

```bash
python3 tubematic_remote_renderer.py install
```

It asks for the enrollment token — paste the token from the dialog; nothing shows as you paste.
The token is never part of a command line: a command line can be read by every user of the machine
(`ps`) and is kept in your shell history, and the token stays usable for an hour. Then it:

1. checks that Docker works, and on a machine with an NVIDIA GPU that Docker has the `nvidia`
   runtime;
2. picks the GPU: the only one, or asks which when there are several (or renders on the CPU when
   there is none);
3. connects to main at the address in the token and **checks main's certificate against the token
   before sending anything**, then asks main for its version;
4. shows what it is about to do and asks you to confirm;
5. pulls `ghcr.io/teja156/tubematic-backend` at main's version (the image of whoever published the
   release) and starts the renderer with the token, waiting up to a minute for it to trade the token
   for its own credential, which it keeps in the `tubematic-renderer-state` Docker volume;
6. removes that first container and starts `tubematic-remote-renderer` again **without** the token
   — Docker keeps a container's environment in its configuration (`docker inspect` shows it), so
   the container left running must not hold it. That one restarts with Docker;
7. waits up to a minute for the renderer to connect, and says whether it did.

If the renderer does not enroll (main refuses the token, the container stops, or a minute passes),
`install` removes the container that held the token — and the state volume, unless an earlier
install left it — and tells you to run `install` again, with a new token if main said this one is
used or expired.

The renderer then appears on the dashboard and starts taking work. The token is never written to
disk.

| Option | Effect |
|---|---|
| `--token-stdin` | Read the token from one line of standard input instead of asking, for scripted installs: `install --token-stdin < token-file` |
| `--token TOKEN` | The token on the command line. Works, with a warning: avoid it, for the reasons above |
| `--gpu UUID` | Use this NVIDIA GPU (`nvidia-smi -L` lists the UUIDs). Needed on a machine with several GPUs when there is no terminal to ask in |
| `--no-gpu` | Render on the CPU even though the machine has a GPU |
| `--name NAME` | The name main lists it under, when the token was made without one (the dashboard's always has one, and that name wins). Defaults to the machine's host name |
| `--image TAG` | Run this image instead of main's published one; a local image is used without pulling. For a main running an unreleased build, which has no published image: build the backend image from the same checkout and pass its tag |
| `--yes` | Do not ask for confirmation |

The script's other commands:

| Command | What it does |
|---|---|
| `python3 tubematic_remote_renderer.py status` | The container's state and image, and its last 20 log lines |
| `python3 tubematic_remote_renderer.py upgrade` | Moves the renderer to main's current version — see [Upgrading](#upgrading) |
| `python3 tubematic_remote_renderer.py remove` | Takes the renderer off this machine — see [Removing a renderer](#removing-a-renderer) |

### Running it with sudo

The script keeps a small state file in the home directory of the user who runs it,
`~/.tubematic-remote-renderer.json` (main's address, its certificate fingerprint, the image and the
GPU choice — never the token or the credential). **Run under `sudo`, that is root's home**, so
`upgrade`, `remove` and `status` must then be run with `sudo` too, or they find no renderer. Adding
your user to the `docker` group avoids this.

---

## The Renderers panel

**Settings → Rendering** lists every renderer, the built-in one first, each on a card:

| Status | Meaning |
|---|---|
| **online** | Connected and ready for work |
| **busy** | Rendering; the card names the video |
| **offline** | Has not reported for two minutes; the card says when it was last seen. Switched off, its container stopped, or it cannot reach main |
| **disabled** | You disabled it; it takes no new work |
| **needs upgrade** | It runs a different Tubematic version from main and takes no work until it is upgraded. The card shows the command |
| **credential expired** | Its credential ran out; it can no longer reach main. Remove it and add it again |

Each card also shows the machine (CPUs and memory), each GPU with its memory and whether the GPU test
passed, what graphics device Chromium actually got, its version, its last error, and — for a remote
renderer — when its credential expires.

| Button | What it does |
|---|---|
| **Disable** / **Enable** | A disabled renderer takes no new work. The built-in renderer can be disabled too |
| **Rename** | Changes the name the dashboard shows |
| **Test GPU** | Shown only for a renderer with a GPU. Asks it to run its GPU test again; the answer appears within about a minute, or after the render it is busy with. What the test checks is in [GPU rendering — Checking it is used](10-gpu-rendering.md#checking-it-is-used) |
| **Remove** | Remote renderers only, after a confirmation. Its credential stops working at once and a render it was running goes back in the queue. The container on that machine keeps running until you remove it there too |

**Add renderer** is below the list, with the address remote renderers use.

The **Pipeline page** shows a red **NOTHING CAN RENDER** banner when videos are waiting to render and
no renderer is enabled, online and on main's version — for example when the only renderer is
disabled, or every remote one needs an upgrade. It links to Settings → Rendering.

---

## Upgrading

**After every upgrade of main, upgrade each remote renderer.** Main's version changes and the
renderers' does not, so they show **needs upgrade** and take no work until you run, on each renderer
machine:

```bash
python3 tubematic_remote_renderer.py upgrade
```

It asks main for its new version (checking main's certificate again), pulls that image and recreates
the container with the same name, GPU and saved credential — no new token is needed. A render it was
running is handed back to main and rendered again. Use the copy of the script from main's new
release or install directory, so the two stay matched. `upgrade.py` on main does not touch remote
renderers; it cannot reach them.

Meanwhile the built-in renderer, which `upgrade.py` upgrades with main, keeps rendering.

---

## Removing a renderer

Remove it in two places, in either order:

- **On the dashboard:** **Remove** on its card. Main stops accepting its credential at once.
- **On the machine:**

  ```bash
  python3 tubematic_remote_renderer.py remove
  ```

  It stops and deletes the container, then asks whether to delete its saved credential (the
  `tubematic-renderer-state` Docker volume) and the state file as well. Say yes unless you plan to
  start the same renderer again; installing again afterwards needs a new token. `--yes` deletes
  everything without asking.

Removing a renderer on main alone leaves its container trying to connect and being refused; removing
it on the machine alone leaves it listed on the dashboard as offline.

The uninstaller on main (`uninstall.py`) does not reach remote renderers either: remove each one on
its own machine.

---

## Credentials

Each remote renderer has its own credential, issued when it is added. **It lasts 30 days and is
replaced automatically while the renderer is online**: from its fifteenth day, main hands it a new
one, and the old one keeps working until the new one is first used, so a lost reply never locks a
renderer out. The card shows when the current one expires.

A renderer that stays offline long enough for its credential to run out — switched off for a month,
say — is listed as **credential expired** and cannot come back on its own. Remove it on both sides
and add it again with a new token.

Main's certificate never changes (rotating it would cut every renderer off), and
`onboard.py --rotate-tokens` leaves renderer credentials alone.

---

## What stays on main

- **Your videos.** A renderer downloads one video's files when it starts rendering it, uploads the
  finished mp4 to main, and deletes its copies when the render ends, however it ends. Nothing
  accumulates on the renderer.
- **The database and your API keys.** The renderer has neither; the gateway answers it with one
  video's files and the render settings that video needs.
- **The AI review** of every render, and everything after it.
- **The Cartoon 3D authoring stills.** The agent's preview stills are drawn by main's built-in
  renderer; a remote renderer renders finished videos only.

**Logs stay on each machine.** A remote renderer's log is in its own container on its own machine —
`python3 tubematic_remote_renderer.py status`, or `docker logs tubematic-remote-renderer` — and does
not appear on main's Logs page. Its last error does: it is on the renderer's card, and a render that
fails is reported in the video's comments like any other.

---

## Troubleshooting

Start with `python3 tubematic_remote_renderer.py status` on the renderer machine: its log says what
the renderer is doing. The lines that matter:

| The renderer's log says | Meaning, and what to do |
|---|---|
| `enrolled as renderer …` | Added to main. Good |
| `first heartbeat accepted by main …` | Connected and reporting; printed on every start. Good |
| `the gateway refused the enrollment (enrollment_invalid)` | The token was already used, expired (an hour), or made on another install. `install` has already removed the container; make a new token and run `install` again |
| `credential expired` | See [Credentials](#credentials): remove it on both sides and add it again |
| `this renderer needs upgrade` | Main runs another version. Run `upgrade` on this machine |
| `… presented a certificate … that is not the one the enrollment token pins …; nothing was sent to it` | Something other than main's gateway answers at that address: a wrong address, another service on that port, or a TLS-terminating proxy. See [Why nothing may sit in front of the port](#why-nothing-may-sit-in-front-of-the-port) |
| `heartbeat failed` or `the renderer cannot start` with a connection error, repeating | It cannot reach main. Check below |
| `heartbeat answered 401 unauthorized` | Main no longer knows it — it was removed on the dashboard. Remove it on this machine, or add it again |

**`install` or `upgrade` says it could not reach the render gateway.** Check, in order: that remote
renderers are on (`python3 scripts/service.py status` on main says so, with the address); that the
address in the token is one this machine can reach (`ping` the host, or `nc -vz <host> 4443`); and
that every firewall between the two — main's network or cloud firewall, `DOCKER-USER` on main, and
any outbound filter on the renderer's side — allows TCP to that port. On main, the `renderers` step's
own check (`python3 onboard.py --step renderers`, keeping the same address) confirms the port
answers locally.

**`install` says the machine answering is not your Tubematic main.** The certificate did not match
the token. The address is wrong, or a proxy that terminates TLS sits in front of the port. Nothing
was sent to it.

**`install` stops at the GPU.** "Docker has no `nvidia` runtime": install or configure the NVIDIA
Container Toolkit (`sudo nvidia-ctk runtime configure --runtime=docker`, then restart Docker), or
pass `--no-gpu`. "Several GPUs": pass `--gpu <UUID>`.

**`install` cannot pull the image.** The renderer needs to reach `ghcr.io`. A main running a build
with no published image (a development checkout) needs `--image`; see the options table above.

**A renderer is online but never renders.** It may simply not be the one that would finish first —
main hands work to the fastest renderer, and with a short queue a slower one waits. A Cartoon 3D or
mascot video goes only to a renderer whose GPU test passed: check the GPU line on its card, and see
[GPU rendering — Troubleshooting](10-gpu-rendering.md#troubleshooting) (the checks there apply to a
remote machine too, with `tubematic-remote-renderer` in place of `tubematic-renderer`).

**The Pipeline page says NOTHING CAN RENDER.** Every renderer is disabled, offline or on another
version. Open Settings → Rendering: enable one, start or upgrade one, or check that main's own
`tubematic-renderer` is running (`python3 scripts/service.py status`).

**A remote renderer went offline in the middle of a render.** Main notices when the renderer stops
reporting, and after five minutes puts the video back in the queue for another renderer. That counts
as one of the video's render retries.
