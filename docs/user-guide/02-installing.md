# Installing

This page installs Tubematic on a Linux machine, installs an agent, and checks the result. For the
shortest path, use the [Quickstart](../quickstart.md).

You install with `onboard.py`, a wizard that asks a few questions and sets everything up. To move an
existing install to a newer version, see [Upgrading](07-upgrading.md).

---

## Ways to install

| Way | What happens | Choose it when |
|---|---|---|
| A release (recommended) | You download a release, and the wizard pulls ready-built images | You want to run Tubematic |
| From source | You clone the repository, and the wizard builds the images on your machine | You want to change Tubematic, or run something not yet released |
| [In Kasm Workspaces](#installing-in-kasm-workspaces) | A ready-made desktop session downloads a release and opens the wizard | You already run Kasm Workspaces |

The first two differ in one more way. A release install serves the dashboard to this machine only. A
source install serves it on every network interface. See [Network exposure](#network-exposure).

## Prerequisites

Install these before you run the wizard. The wizard checks for them and installs none of them.

| What | Version | Check it with |
|---|---|---|
| Linux | Any current distribution | `uname -s` |
| Docker Engine | 29 or newer, running, usable without `sudo` | `docker --version`, `docker info` |
| Docker Compose plugin | v2 or newer | `docker compose version` |
| Python | 3.11 or newer, with the `venv` module | `python3 --version`, `python3 -c "import ensurepip"` |
| Node.js | 22.20 or newer | `node --version` |
| An agent CLI | Current | `which claude`, `which codex` or `which opencode` |
| CPU | 2 cores. 4 or more render faster | `nproc` |
| Memory | 4 GB. 8 GB recommended | `free -g` |
| Disk | About 15 GB free | `df -h ~` |

Three notes on that table:

- `docker-compose` with a hyphen is an older tool and does not count. Tubematic needs
  `docker compose`.
- The wizard continues without Node.js and prints a warning. The agent then writes scenes without
  the Remotion skill that Node installs. Install Node first.
- An NVIDIA GPU is optional and makes rendering about three times faster. See
  [GPU Rendering](10-gpu-rendering.md).

On Ubuntu, [Preparing an Ubuntu machine](#preparing-an-ubuntu-machine) has the commands for Docker,
the `venv` module and Node.js.

### API keys

| Service | Needed | Used for | Where to get it |
|---|---|---|---|
| ElevenLabs | Yes | The voiceover | elevenlabs.io → Profile → API Keys |
| OpenAI | Yes | Scene images, and characters in the Illustrated style | platform.openai.com/api-keys |
| Gemini | No | Finding topics in YouTube videos, and AI review | aistudio.google.com/app/apikey |
| youtube-transcript.io | No | Script profiles | youtube-transcript.io |
| postforme.dev | No | Publishing | postforme.dev |

- The ElevenLabs key needs four permissions: text-to-speech, voices (read), projects (read) and
  pronunciation dictionaries (read). Add user (read) if you want the dashboard to show how much of
  your monthly credit is used.
- The OpenAI key's project needs billing enabled, and access to the image model you pick. OpenAI
  grants model access per project.
- A Gemini chat subscription does not include API access. You need a key from Google AI Studio.

You can add the optional keys later on **Settings → API Keys**.

---

## Install

From a release:

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/v2.0.0/tubematic-v2.0.0.tar.gz
curl -LO https://github.com/teja156/tubematic/releases/download/v2.0.0/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-v2.0.0.tar.gz
cd tubematic-v2.0.0
python3 onboard.py
```

From source:

```bash
git clone https://github.com/teja156/tubematic.git tubematic
cd tubematic
python3 onboard.py
```

The directory you run `onboard.py` from is the install directory. Every later command in these docs
runs from there.

The wizard creates its own Python environment in `.venv` and then works through eleven steps. It
asks for:

1. A dashboard password, twice. At least 12 characters.
2. Your API keys. It checks each key with its provider as you enter it, and asks again if the
   provider rejects one.
3. Whether to enable publishing. Answer no unless you have a postforme.dev key ready. You can turn
   it on later.
4. Whether to enable AI review. It is experimental and needs a Gemini key.
5. The image model.
6. The poll interval: how often Tubematic checks for work while idle. The default is 30 minutes.
7. Which GPU renders, if the machine has a usable NVIDIA GPU.

Press Enter to accept a default. After the last question the wizard pulls or builds the images and
starts five containers. A source install takes longer than a release install, because it builds
the images.

If the wizard stops part-way, run `python3 onboard.py` again. It skips the steps that finished.

The [Command Reference](15-command-reference.md#onboardpy) lists every step, question and flag.

## Install an agent

Tubematic does nothing until an agent is installed. Install the agent's CLI, log it in, and run:

```bash
python3 onboard.py --install-agent claude     # or: codex, opencode
```

It asks where to install, and which models the agent may use. The first model you enter is the
agent's default. [Agents](12-agents.md) explains each question and how to manage agents afterwards.

## Check the install

```bash
python3 scripts/service.py status
```

Each line should start with `✔`. A line that starts with `!` names what needs attention and the
command that fixes it.

Then open `http://localhost:3000` and sign in. The top bar shows the installed version, and
`SYS ● NOMINAL` when the dashboard can reach the rest of Tubematic.

Now make a video: follow [Create a video](../quickstart.md#3-create-a-video) in the Quickstart.

---

## Where things are

| What | Where |
|---|---|
| The database, including your settings and API keys | `~/.tubematic-data/data/tubematic.db` |
| Rendered videos | `~/.tubematic-data/output_videos/` |
| Each video's working files | `~/.tubematic-data/jobs/` |
| Scene code the agent wrote | `~/.tubematic-data/scenes/generated/` |
| Logs | `~/.tubematic-data/logs/`, and the poller's log at `~/.tubematic-agent/logs/poll.log` |
| The dashboard password and service tokens | `~/.tubematic-data/secrets/` |
| Each agent's workspace | `~/.tubematic-agent/<agent>/` |

The database holds your API keys in plain text. Treat it, and any copy of it, as a secret.

You change settings on the dashboard's **Settings** page, and they apply to the next piece of work
without a restart. A few things are set on the command line instead, such as the poll interval, the
GPU and the dashboard password. See the [Command Reference](15-command-reference.md#common-uses).

## Network exposure

| Port | What listens | Reachable from |
|---|---|---|
| 3000 | The dashboard, over plain HTTP, behind your password | This machine only on a release install. Every network interface on a source install |
| 4000, 4100 | The API and the tool server, each behind a token | This machine only |
| 4443 | The render gateway, for renderers on other machines | Closed unless you turn on [remote renderers](11-remote-renderers.md) |

Over plain HTTP your password crosses the network unencrypted. Use a source install's dashboard on a
network you trust, and see [Remote Access](09-remote-access.md) to reach the dashboard from another
machine safely.

---

## Install problems

Problems with a running install are in [Troubleshooting](08-troubleshooting.md).

### The wizard stops at `ensurepip is not available`

Python's `venv` module is missing its `pip` part. On Debian and Ubuntu it is a separate package:

```bash
sudo apt install -y python3-venv
python3 onboard.py
```

### `--install-agent` warns that the Remotion skills were skipped

Node.js is missing or older than 22.20. Install Node 22
([Node.js](#nodejs)), then run `python3 onboard.py --install-agent <agent>` again.

### The image pull fails on a release install

The images are public, so you do not need to log in. The wizard prints Docker's own reason. The
usual cause is that this machine cannot reach `ghcr.io`. Fix that, then run:

```bash
python3 onboard.py --step renderer --force
python3 onboard.py --step dashboard --force
```

### A container does not start

```bash
python3 scripts/service.py status
python3 scripts/service.py logs tubematic-api
```

`tubematic-api`, `tubematic-mcp`, `tubematic-worker` and `tubematic-renderer` run the same image. On
a source install, rebuild it with `python3 onboard.py --step renderer --force`.

### The wizard says Docker is installed but not running

Either the Docker service is stopped, or your user cannot use it. See
[Run Docker without sudo](#run-docker-without-sudo).

### A step fails

| The wizard says | Run |
|---|---|
| The dependency install failed | `.venv/bin/python -m pip install -r scripts/requirements.txt`, then `python3 onboard.py` |
| A database error, such as "no such table" | `python3 onboard.py --step database` |

### Nothing happens after the install

Read `~/.tubematic-agent/logs/poll.log`. `No agent installed` means you have not run
`--install-agent` yet. For anything else, see
[Troubleshooting](08-troubleshooting.md#nothing-is-happening).

---

## Installing in Kasm Workspaces

[Kasm Workspaces](https://kasmweb.com/) serves desktop sessions in a browser. If you run it, the
Tubematic workspace gives you a session with Docker, the three agent CLIs and every other
prerequisite already installed.

1. In the Kasm admin UI, open **Workspaces → Workspace Registry → Add new** and enter
   `https://registry.tejaswaroop.com/`.
2. Install the Tubematic workspace from that registry. Check three things in its settings first:
   - It runs privileged, because Tubematic's containers run inside the session.
   - It needs about 15 GB for its image and about 15 GB more inside the session.
   - Give it a **Persistent Profile Path**. Without one, your install and your videos are deleted
     when the session ends.
3. Launch a session. The launch form asks for the Tubematic version and the install method. Keep
   **Release (recommended)**.
4. A terminal named *Tubematic installer* opens in the session, downloads Tubematic into
   `~/tubematic-v<version>/` and starts the wizard. Answer its questions as described under
   [Install](#install).
5. When the wizard finishes, log your agent CLI in and
   [install an agent](#install-an-agent) from the same terminal.

If you close the terminal, the **Tubematic installer** icon on the desktop opens it again, as does
running `tubematic-installer` in any terminal. Its log is `~/.tubematic-workspace.log`.

Things that differ in a Kasm session:

- The workspace must not have a GPU attached, so [GPU rendering](10-gpu-rendering.md) is not
  available.
- The session's clock is UTC, so the dashboard shows times in UTC.
- When you launch again with a persistent profile, the session finds your install and leaves it as
  it is. If you pick a different version on the launch form, the session downloads nothing. To move
  to a new version, follow [Upgrading](07-upgrading.md) inside the session.

---

## Preparing an Ubuntu machine

These commands are for Ubuntu. On another distribution, install the same things with its own package
manager, then use the two Docker checks below, which are the same everywhere.

### Installing Docker on Ubuntu

Check what you have:

```bash
docker --version
docker compose version
```

| You see | Do this |
|---|---|
| Docker 29 or newer, and a Compose version | Skip to [Run Docker without sudo](#run-docker-without-sudo) |
| Docker 29 or newer, and `docker compose version` fails | Install the plugin: `sudo apt install -y docker-compose-plugin`. If apt cannot find it, use `sudo apt install -y docker-compose-v2` |
| `command not found`, or a version below 29 | Follow the steps below |

The steps install Docker from Docker's own repository, as in Docker's
[Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Ubuntu's own
`docker.io` package can be older than 29.

Remove Ubuntu's Docker packages, which conflict with Docker's. Your images, containers and volumes
stay:

```bash
sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc | cut -f1)
```

Add Docker's repository:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
```

Install Docker and the Compose plugin:

```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Docker starts now and at every boot. If it is not running, start it with
`sudo systemctl enable --now docker`.

#### Run Docker without sudo

Tubematic runs `docker` as your user, so your user must be in the `docker` group:

```bash
sudo usermod -aG docker $USER
```

Log out and back in for it to take effect. `newgrp docker` applies it to the current shell only.

Anyone in the `docker` group can become root on this machine. Add only the account that runs
Tubematic.

#### Check Docker

```bash
docker --version          # 29 or newer
docker compose version    # v2 or newer
docker run --rm hello-world
```

All three must work without `sudo`.

### Python's venv module

```bash
sudo apt install -y python3-venv
python3 -c "import ensurepip"      # prints nothing when it is installed
```

### Node.js

Ubuntu's own `nodejs` package can be too old. Ubuntu 24.04 ships version 18. Install Node 22 from
[NodeSource](https://github.com/nodesource/distributions):

```bash
sudo apt remove -y nodejs npm      # only if Ubuntu's nodejs is installed
sudo apt install -y curl ca-certificates
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node --version                     # v22.20 or newer
```

Avoid `nvm` on a server. It installs Node for interactive shells only, and scripts then find the
older system Node.

---

## Uninstalling

```bash
python3 uninstall.py
```

The uninstaller works through nine steps and asks before each one. It asks separately before it
deletes your database, your videos' working files and your rendered videos, and the answer to each
of those defaults to no. The [Command Reference](15-command-reference.md#uninstallpy) lists every
step and what the uninstaller leaves behind.

To finish removing Tubematic after the uninstaller:

```bash
docker images | grep tubematic      # then: docker rmi <each image>
cd .. && rm -rf <install directory>
```

To stop Tubematic and keep everything, run `python3 scripts/service.py stop`.

To remove one agent and keep Tubematic, see [Agents](12-agents.md#uninstall-an-agent).
