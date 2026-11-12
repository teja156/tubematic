# Remote Renderers

How to let other machines render videos for your Tubematic install: turning the feature on, adding a
machine, keeping it on the right version, and removing it.

Here, **main** is the machine Tubematic is installed on: the one with the dashboard, the database
and your videos. A **remote renderer** is another machine that renders videos for main and does
nothing else.

Remote renderers are optional, and off until you turn them on. Without them, main renders every
video with its built-in renderer. Turning them on changes nothing else.

---

## When it helps

Rendering is the slow part of making a video. On a CPU, a long Short can take most of an hour. A
remote renderer helps when:

- Another machine has more cores. It renders faster, and main stays free for the dashboard and the
  agents.
- Another machine has an NVIDIA GPU and main has none. Cartoon 3D and mascots render on a GPU only
  (see [GPU rendering](10-gpu-rendering.md)), and one remote renderer whose GPU test passed is
  enough to offer them.
- You want several videos rendered at once. Each renderer renders one video at a time.

Main gives each video to the renderer that would finish it first. A video that has waited ten
minutes goes to whichever renderer asks, and a Cartoon 3D or mascot video goes only to a renderer
whose GPU test passed. How main estimates this is in
[GPU and Remote Renderers](../developer/20-gpu-and-remote-renderers.md#which-renderer-gets-which-video).

The built-in renderer keeps taking work. Disable it on the dashboard if you want main to render
nothing.

To see which renderer made a video, open the video. Its Details list **Rendered by** (the
renderer's name, then GPU or CPU) and **Render time** for its last successful render. Videos
rendered before version 2.2.0 show neither.

---

## How it works

A remote renderer is one Docker container, `tubematic-remote-renderer`, running the same image as
main's own renderer. It has no database, no copy of your video library and none of your API keys.
It reaches main over HTTPS on one port (4443 by default), the render gateway, and uses it to:

1. ask for a video to render,
2. download that video's files (audio, timeline, scenes and images),
3. upload the finished mp4,
4. report how the render went, and every 30 seconds that it is still running.

Main stores the video, runs the AI review and does everything else, as for its own renders. The
renderer proves who it is with a credential main issued. It trusts one certificate, main's own,
which it checked when it was added (see
[Why nothing may sit in front of the port](#why-nothing-may-sit-in-front-of-the-port)).

---

## What you need

On main:

- Tubematic 2.1.0 or newer, installed and running.
- The `renderers` step, run once. See [Turning remote renderers on](#turning-remote-renderers-on).

On each remote renderer:

- Linux with Docker Engine, usable by the user who runs the script: in the `docker` group, or with
  `sudo` (see [Running it with sudo](#running-it-with-sudo)). The published image is built for
  x86-64. For Ubuntu, see [Installing Docker on Ubuntu](02-installing.md#installing-docker-on-ubuntu).
- Python 3.10 or newer. The setup script uses only the standard library.
- For a GPU, the NVIDIA driver and the NVIDIA Container Toolkit, set up as in steps 1 and 2 of
  [GPU rendering](10-gpu-rendering.md#what-you-need). The script picks the GPU.
- A network path to main on the gateway's port. The renderer opens every connection, so nothing
  needs to reach it.
- Internet access, or another way to get the image `ghcr.io/teja156/tubematic-backend` at main's
  version.

The script runs the image for main's version. A renderer on any other version is listed as
**needs upgrade** and gets no work (see [Upgrading](#upgrading)).

---

## Turning remote renderers on

On main, from its install directory:

```bash
python3 onboard.py --step renderers
```

A full install does not run this step. The step asks two things:

1. Whether remote renderers are on or off.
2. The address renderers use to reach this machine. Enter an IP address, or a DNS name the renderer
   machines can resolve, with `:port` for a port other than 4443. Examples are `192.168.1.20`,
   `render.example.lan:8443` and an IPv6 address in brackets, `[2001:db8::20]`. The step refuses
   `localhost`, a loopback, multicast, broadcast or IPv6 link-local (`fe80::…`) address, and a
   leading `http://` or `https://`.

Then it:

- Writes `~/.tubematic-data/compose.renderers.json`, a Compose file that publishes the gateway on
  that port on every network interface of main (IPv6 interfaces too, when the address is IPv6). The
  file is kept with your data, so upgrades keep it.
- Stores the address, which the dashboard puts into every enrollment token.
- Recreates `tubematic-api` so the port opens. This takes a few seconds, and a render in progress
  carries on.
- Checks on main itself (`127.0.0.1`) that the port answers with the gateway's certificate. Whether
  the address reaches main from a renderer machine is tested later, by the renderer's `install`.
- Prints a note about
  [the firewall](#allow-the-port-through-your-firewall-from-your-renderers-only) and offers a first
  enrollment token. The default is no, because the dashboard makes one whenever you need it.

In three cases you see something else:

- A post is uploading. The step changes nothing and tells you to run it again after the upload,
  because recreating `tubematic-api` would cut the upload off.
- `docker compose up` fails, for example because another program holds the port. The step fails
  with Docker's error and puts the earlier file, address and `tubematic-api` back.
- The stack is stopped. The step saves your choice and starts nothing. The port opens or closes the
  next time you run `python3 scripts/service.py start`.

Run the step again to change the address or the port, or to choose **Off**. Off closes the port, and
renderers already added stay on the dashboard as offline until you remove them.
`python3 scripts/service.py status` (or `python3 upgrade.py --check`) prints whether remote
renderers are on and their address.

A renderer keeps dialling the address it was added with. After you change the address, remove each
renderer and add it again with a new token.

### Allow the port through your firewall, from your renderers only

The gateway serves only TLS and asks every caller for a credential, and only your renderers need to
reach it. Allow TCP on the port (4443 by default) into main from your renderer machines only.

A `ufw` rule alone does not do this, because traffic meets Docker's own rules for published ports
before `ufw`'s. Restrict the port in one of two places:

- A network or cloud firewall (a router, a security group) in front of main. This is the simplest.
- Docker's `DOCKER-USER` chain on main, which Docker consults before its own rules. For example,
  to drop connections to port 4443 from outside `198.51.100.0/24`:

  ```bash
  sudo iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 4443 --ctdir ORIGINAL \
    ! -s 198.51.100.0/24 -j DROP
  ```

  Match the original port with `conntrack` as shown, because Docker rewrites a packet's destination
  before the packet reaches `DOCKER-USER`. Save the rule, for example with `iptables-persistent`, or
  a reboot removes it. See Docker's
  [Packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

#### With an IPv6 address

An IPv6 address makes main publish the port on `[::]` too, and `iptables` filters IPv4 only.
Restrict IPv6 as well:

- A network or cloud firewall that filters both IPv4 and IPv6 is the simplest.
- On main, use the IPv6 `INPUT` chain. Tubematic's Compose network is IPv4-only, so Docker's own
  proxy process accepts the `[::]` connections, and they pass `INPUT` and skip `DOCKER-USER`. For
  example, to drop connections to port 4443 from outside `2001:db8:5::/64`:

  ```bash
  sudo ip6tables -I INPUT -p tcp --dport 4443 ! -s 2001:db8:5::/64 -j DROP
  ```

  Then check from a machine outside that range that the port does not answer
  (`nc -6 -vz <main's IPv6 address> 4443`). If it answers, your Docker daemon forwards IPv6 packets
  (an IPv6-enabled network, or the userland proxy turned off), and the rule belongs in `ip6tables`'
  `DOCKER-USER` chain, written like the IPv4 rule. `iptables-persistent` saves IPv6 rules to
  `/etc/iptables/rules.v6`.

### Why nothing may sit in front of the port

Do not put a TLS-terminating proxy (Caddy, nginx, a load balancer, a tunnel that decrypts) in front
of the gateway's port. The gateway uses a self-signed certificate made at install, and the
enrollment token carries its fingerprint (a *pin*). A renderer checks the fingerprint before it
sends anything and trusts no other certificate. A proxy presents its own certificate, so the
renderer refuses to connect, as it would refuse an attacker in the middle.

Plain port forwarding (NAT, a TCP-level forward) is fine, because the renderer still talks TLS to
the gateway itself. The dashboard's HTTPS proxy from [Remote Access](09-remote-access.md) is on a
different port and is unaffected. Why the renderer pins the certificate and uses no certificate
authority is in [The Render Gateway](../developer/19-render-gateway.md#tls-and-the-certificate-pin).

---

## Adding a renderer

### 1 · Make an enrollment token

On the dashboard, open **Settings → Rendering** and press **Add renderer**. Enter a name for the
machine (at most 60 characters), which is how the dashboard lists it, and press **Create token**.
The dialog shows the token and the command to run on the renderer machine. The command does not
contain the token, because the script asks for it.

The token is shown once, works once and lasts one hour. If you close the dialog or the token
expires, make another. Treat it as a password until it is used, because it carries a one-time secret
that adds a renderer to your install.

Until remote renderers are turned on, **Add renderer** is greyed out and shows the command that
turns them on.

### 2 · Get the script onto the renderer machine

The script is `tubematic_remote_renderer.py`. It is one file, and the renderer machine needs no
Tubematic install. Get it in one of two ways.

#### Copy it from main

Every install has the script under `scripts/`. On main, from the install directory:

```bash
scp scripts/tubematic_remote_renderer.py you@renderer-host:
```

#### Download it from GitHub

On the renderer machine, download the script and its checksums from the release your main runs.
The first release with remote renderers is 2.1.0. Use `curl` or `wget`, whichever the machine has.

With `curl`:

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/v2.2.0/tubematic_remote_renderer.py
curl -LO https://github.com/teja156/tubematic/releases/download/v2.2.0/CHECKSUMS.txt
```

With `wget`:

```bash
wget https://github.com/teja156/tubematic/releases/download/v2.2.0/tubematic_remote_renderer.py
wget https://github.com/teja156/tubematic/releases/download/v2.2.0/CHECKSUMS.txt
```

Then check the download:

```bash
sha256sum -c CHECKSUMS.txt --ignore-missing   # must say: tubematic_remote_renderer.py: OK
```

`CHECKSUMS.txt` also lists the release tarball, and `--ignore-missing` skips it.

If your main runs a later version, put that version in place of `v2.2.0` in both addresses. The
dashboard's top bar shows the version.

### 3 · Run it

On the renderer machine, run the command the dialog showed:

```bash
python3 tubematic_remote_renderer.py install
```

It asks for the enrollment token. Paste it. Nothing shows as you paste. The script does not take the
token on the command line, where every user of the machine could read it (`ps`) and your shell
history would keep it. Then the script:

1. Checks that Docker works and, on a machine with an NVIDIA GPU, that Docker has the `nvidia`
   runtime.
2. Picks the GPU: the only one, or the one you choose when there are several. Without a GPU it
   renders on the CPU.
3. Connects to main at the address in the token, checks main's certificate against the token before
   it sends anything, and asks main for its version.
4. Shows what it is about to do and asks you to confirm.
5. Pulls the image at main's version, starts the renderer with the token, and waits up to a minute
   for it to enroll. The renderer saves the credential it gets in the `tubematic-renderer-state`
   Docker volume.
6. Starts `tubematic-remote-renderer` again without the token, because `docker inspect` shows a
   container's environment. This container starts again whenever Docker does.
7. Waits up to a minute for the renderer to connect, and says whether it did.

The renderer then appears on the dashboard and starts taking work. The script does not write the
token to disk.

If the renderer does not enroll (main refuses the token, the container stops, or a minute passes),
`install` removes the container that held the token, and the state volume unless an earlier install
left it. Run `install` again, with a new token if main said this one is used or expired.

| Option | Effect |
|---|---|
| `--token-stdin` | Reads the token from one line of standard input, for scripted installs: `install --token-stdin < token-file`. `--token <value>` is refused before anything is sent |
| `--gpu UUID` | Uses this NVIDIA GPU (`nvidia-smi -L` lists the UUIDs). Needed with several GPUs and no terminal to ask in |
| `--no-gpu` | Renders on the CPU on a machine that has a GPU |
| `--name NAME` | The name main lists the renderer under, when the token carries none. A dashboard token always carries one, and it wins. Defaults to the machine's host name |
| `--image TAG` | Runs this image in place of main's published one, without pulling when it is local. For a main on an unreleased build, build the backend image from the same checkout and pass its tag |
| `--yes` | Does not ask for confirmation |

The script's other commands:

| Command | What it does |
|---|---|
| `python3 tubematic_remote_renderer.py status` | Shows the container's state and image, and its last 20 log lines |
| `python3 tubematic_remote_renderer.py upgrade` | Moves the renderer to main's current version. See [Upgrading](#upgrading) |
| `python3 tubematic_remote_renderer.py remove` | Takes the renderer off this machine. See [Removing a renderer](#removing-a-renderer) |

### Running it with sudo

The script keeps a state file, `~/.tubematic-remote-renderer.json`, in the home directory of the
user who runs it. It holds main's address, its certificate fingerprint, the image and the GPU
choice, and no token or credential. Under `sudo` that directory is root's, so run `upgrade`,
`remove` and `status` with `sudo` too, or they find no renderer. Adding your user to the `docker`
group avoids this.

---

## The Renderers panel

**Settings → Rendering** lists every renderer on a card, the built-in one first.
[Settings](05-settings.md#renderers) explains each status and button. For a remote renderer:

- **offline** means it has not reported for two minutes. The machine is switched off, its container
  is stopped, or it cannot reach main. The card says when it was last seen.
- **needs upgrade** means it runs a different Tubematic version from main. The card shows the
  command to run.
- **credential expired** means its credential ran out and it cannot reach main. Remove it and add
  it again.
- The card also shows the renderer's version and when its credential expires.
- **Test GPU** asks it to run its GPU test again. The answer appears within about a minute, or after
  its current render. See [Checking it is used](10-gpu-rendering.md#checking-it-is-used).
- **Remove** asks you to confirm. The credential stops working at once, and a render in progress
  goes back in the queue. The container keeps running until you remove it on that machine too.

**Add renderer** is below the list, next to the address remote renderers use.

The Pipeline page shows a red **NOTHING CAN RENDER** banner when videos are waiting to render and no
renderer is enabled, online and on main's version. See
[Troubleshooting](08-troubleshooting.md#nothing-can-render).

---

## Upgrading

After every upgrade of main, upgrade each remote renderer. Until you do, it shows **needs upgrade**
and takes no work. On each renderer machine, run:

```bash
python3 tubematic_remote_renderer.py upgrade
```

It asks main for its new version (checking main's certificate again), pulls that image and recreates
the container with the same name, GPU and saved credential, so you need no new token. A render in
progress is handed back to main and rendered again. Use the script from main's new release or
install directory, so that it matches main.

`upgrade.py` on main cannot reach remote renderers. It upgrades the built-in renderer, which keeps
rendering in the meantime.

---

## Removing a renderer

Remove it in two places, in either order:

- On the dashboard, press **Remove** on its card. Main stops accepting its credential at once.
- On the machine, run:

  ```bash
  python3 tubematic_remote_renderer.py remove
  ```

  It stops and deletes the container, then asks whether to delete the saved credential (the
  `tubematic-renderer-state` Docker volume) and the state file. Say yes unless you plan to start the
  same renderer again. After a yes, installing again needs a new token. `--yes` deletes everything
  without asking.

A renderer removed on main only keeps trying to connect, and main refuses it. A renderer removed on
its machine only stays on the dashboard as offline. `uninstall.py` on main does not reach remote
renderers, so remove each one on its own machine.

---

## Credentials

Each remote renderer has its own credential, issued when it is added and valid for 30 days. While
the renderer is online, main replaces the credential automatically from its fifteenth day, and the
old one keeps working until the new one is first used. The card shows when the current one expires.
The details are in [The Render Gateway](../developer/19-render-gateway.md#credentials).

A renderer that stays offline until its credential runs out, for example one switched off for a
month, is listed as **credential expired** and cannot reconnect. Remove it on both sides and add it
again with a new token.

Main's certificate does not change, because a new one would cut every renderer off.
`onboard.py --rotate-tokens` leaves renderer credentials alone.

---

## What stays on main

- Your videos. A renderer holds one video's files while it renders, and deletes them when the render
  ends, whatever the result.
- The database and your API keys. The gateway gives a renderer one video's files and the render
  settings that video needs.
- The AI review of every render, and everything after it.
- The Cartoon 3D authoring stills. Main's built-in renderer draws the agent's preview stills. A
  remote renderer renders finished videos only.

A remote renderer's log stays on its own machine and does not appear on main's Logs page. Read it
with `python3 tubematic_remote_renderer.py status` or `docker logs tubematic-remote-renderer`. Its
last error is on its card, and a failed render is reported in the video's comments like any other.

---

## Troubleshooting

Start with `python3 tubematic_remote_renderer.py status` on the renderer machine. Its log says what
the renderer is doing:

| The renderer's log says | Meaning, and what to do |
|---|---|
| `enrolled as renderer …` | Added to main. Nothing to do |
| `first heartbeat accepted by main …` | Connected and reporting. Printed on every start |
| `the gateway refused the enrollment (enrollment_invalid)` | The token was already used, expired after its hour, or was made on another install. `install` has removed the container. Make a new token and run `install` again |
| `credential expired` | Remove the renderer on both sides and add it again. See [Credentials](#credentials) |
| `this renderer needs upgrade` | Main runs another version. Run `upgrade` on this machine |
| `… presented a certificate … that is not the one the enrollment token pins …; nothing was sent to it` | Something other than main's gateway answers at that address: a wrong address, another service on that port, or a TLS-terminating proxy. See [Why nothing may sit in front of the port](#why-nothing-may-sit-in-front-of-the-port) |
| `heartbeat failed` or `the renderer cannot start` with a connection error, repeating | It cannot reach main. Run the checks under [could not reach the render gateway](#install-or-upgrade-says-it-could-not-reach-the-render-gateway) |
| `heartbeat answered 401 unauthorized` | The renderer was removed on the dashboard. Remove it on this machine, or add it again |

### `install` or `upgrade` says it could not reach the render gateway

Check these in order:

1. Remote renderers are on. `python3 scripts/service.py status` on main says so, with the address.
2. The renderer machine can reach the address in the token. `ping` the host, or run
   `nc -vz <host> 4443`.
3. Every firewall between the two machines allows TCP to that port: main's network or cloud
   firewall, `DOCKER-USER` on main, and any outbound filter on the renderer's side.

To confirm that the port answers on main itself, run `python3 onboard.py --step renderers` there and
keep the same address.

### `install` says the machine answering is not your Tubematic main

The certificate did not match the token, so the script sent nothing to that machine. The address is
wrong, or a proxy that terminates TLS sits in front of the port.

### `install` stops at the GPU

If it says Docker has no `nvidia` runtime, install or configure the NVIDIA Container Toolkit
(`sudo nvidia-ctk runtime configure --runtime=docker`, then restart Docker), or pass `--no-gpu`. If
it says the machine has several GPUs, pass `--gpu <UUID>`.

### `install` cannot pull the image

The renderer machine needs to reach `ghcr.io`. If main runs a build with no published image (a
development checkout), pass `--image`. See the options under [Run it](#3--run-it).

### A renderer is online but never renders

Main gives each video to the renderer that would finish it first, so with a short queue a slower
renderer waits. A Cartoon 3D or mascot video also needs a renderer whose GPU test passed. Check the
GPU line on the card, and see [GPU rendering](10-gpu-rendering.md#troubleshooting). The checks there
apply to a remote machine too, with `tubematic-remote-renderer` in place of `tubematic-renderer`.

### A remote renderer went offline in the middle of a render

When the renderer stops reporting, main waits five minutes and then puts the video back in the queue
for another renderer. That counts as one of the video's render retries.
