# Kasm Workspace — Tubematic testing environment (TMDEV-34)

> This is the **QA** environment: it bakes a worktree's source into the image. The published,
> installable workspace that downloads a release at launch is [`kasm_workspace/`](../kasm_workspace/README.md).

Builds a custom [Kasm Workspaces](https://kasmweb.com/) image that gives testers a disposable,
browser-accessible desktop with the Tubematic source pre-staged and Docker-in-Docker available, so
the full 4-container stack (`tubematic-api`, `tubematic-mcp`, `tubematic-renderer`,
`tubematic-dashboard`) can be brought up inside the session without touching the host machine.

Base image: `kasmweb/ubuntu-noble-dind:1.19.0-rolling-daily` (root-mode Docker-in-Docker).

**Why root mode, not rootless:** the rootless variant (`-dind-rootless`) was tried first but hit a
kernel-level nested-user-namespace failure (`newuidmap: write to uid_map failed: Operation not
permitted`) specific to this host's Ubuntu 24.04 + AppArmor combination, past the point where
`apparmor=unconfined` alone could unblock it. Root-mode DinD sidesteps the whole rootless
userns/`rootlesskit`/`newuidmap` chain — `dockerd` just runs as real root — at the cost of needing
the Kasm workspace launched with `"privileged": true`.

## Building the image

```bash
cd kasm_workspace_testing
./build.sh            # builds tubematic/tubematic-testing-env:latest
./build.sh 1.0.0       # custom tag
./build.sh --no-cache  # force a clean rebuild
./build.sh --worktree my-feature-branch  # skip the prompt, name the source tree
```

`build.sh` first asks **which git worktree to build into the image**, listing each one with its
branch, HEAD, path, and an `*uncommitted` marker (uncommitted work is baked in and can't be
recovered from the tag afterwards). Enter accepts the default — the worktree the script itself
lives in. Both the source and `dockerfile_tubematic_kasm` come from the chosen tree, so the image
is genuinely that branch rather than a mix of two.

`--worktree <path|branch|dirname>` picks non-interactively, and errors rather than guessing if the
value matches nothing or more than one worktree. With no TTY the prompt is skipped and the
script's own worktree is used, so existing scripted `./build.sh <tag>` calls are unaffected.
A **wrapper run from a terminal does inherit a TTY and will stop at the prompt** — the
outside-the-repo `~/scripts/tubematic_dev_env.sh install` is the known case. Pass
`--worktree <path>` from any wrapper that must run unattended.
Branches without a worktree are deliberately not offered — they could only be staged from their
committed tip, silently dropping uncommitted work.

`build.sh` stages a filtered copy of the repo (excluding `.env`, `mounted/`, `.git`,
`node_modules`, `.venv`, and other dev-session artifacts — the same list `prepare_for_install.sh`
cleans up for the local dev-env flow) into a scratch `build-context/` directory, then runs
`docker build`. The scratch directory is removed after the build.

**No secrets are baked into the image.** `.env` (ElevenLabs/Gemini API keys, etc.) is never copied
in — a tester enters those interactively when `onboard.py` runs inside the session.

## What the image does and doesn't do

The Kasm image build only *stages* the repo and installs the prerequisites
(`python3-pip`, `python3-venv`, `git`, `curl`; Docker CLI/daemon and Python are already in the
base). **It does not build the Tubematic Docker stack itself** — there is no Docker daemon
available during a Kasm image build (`dockerd` only starts once a session is running, via
`custom_startup.sh` → `supervisord` → the `dockerd` program block in
`/etc/supervisor/conf.d/dockerd.conf`), so `docker compose build` for
`tubematic-api`/`tubematic-mcp`/`tubematic-renderer`/`tubematic-dashboard` cannot happen at this
stage.

**Important:** never *overwrite* `$STARTUPDIR/custom_startup.sh` — that script is what launches
`supervisord` (which in turn autostarts `dockerd` and `cron`) on every session start. Replacing it
(as an earlier version of this file did, for a login hint) silently disables Docker-in-Docker
entirely.

The Dockerfile does make one **in-place, single-line** patch to it, which is a different thing and
is the only permitted kind of edit here. The base image's script starts `supervisord` as soon as
`/usr/bin/desktop_ready` returns, and that returns as soon as an `xfce4-session` PID exists —
mid-startup, not when the desktop is up. `supervisord` then starts `dockerd` through
`dockerd-entrypoint.sh`, which wraps it in `/usr/local/bin/dind`, and `dind` does:

```sh
if ! mountpoint -q /tmp; then mount -t tmpfs none /tmp; fi
```

That empty tmpfs hides `/tmp/.X11-unix/X1`, the dbus session socket, `.X1-lock` and
`/tmp/launch_selections.json`. `xfce4-session` loses its display and session bus and dies, taking
`xfwm4`, the panel and `xfdesktop` with it — while `Xvnc` survives, because it already holds its
file descriptors. **The symptom is a session that connects normally and shows a blank screen**, so
it reads as a network or client fault rather than a dead desktop. Whether it takes the whole
session or only `xfdesktop` (leaving the panel) is pure timing, which is why it had been seen in
two different shapes.

The patch inserts, immediately before the `supervisord` launch:

```sh
mountpoint -q /tmp || sudo mount --bind /tmp /tmp
```

Making `/tmp` a mountpoint first makes `dind`'s conditional false, so it skips the tmpfs. A
self-bind rather than mounting our own tmpfs early: the bind keeps the existing contents, where a
tmpfs would hide the same sockets — the same bug, moved earlier. It is a `sed` on the one anchor
line rather than a forked copy of the script, because a copy would silently pin an old version
across base-image upgrades; the `grep` guarding it **fails the build** if `kasmweb` ever changes
that line. Do not soften that into a warning — a skipped patch is invisible until a tester sees a
blank screen.

Instead, on first launch of a session from this image:

```bash
cd ~/tubematic
python3 onboard.py
```

runs interactively as usual — prompting for API keys, creating
`~/.tubematic-data/{jobs,data,output_videos,scenes/generated}`, and building/bringing up the
compose stack via the now-running nested Docker daemon.

`onboard.py` re-execs itself inside a `.venv` it creates at the repo root the first time it's run
outside one (Ubuntu Noble marks the system Python as externally-managed per PEP 668, so a bare
`pip install` fails without this) — no manual venv setup needed before running it.

## Caveats

- **Requires a privileged Kasm workspace.** Root-mode `dockerd` needs the session container launched
  with `"privileged": true` in the Docker Run Config Override (Kasm admin UI, editing this image).
  Without it, `dockerd` fails to start (can't create overlayfs mounts, network namespaces, etc.).
  This relaxes container isolation for sessions launched from this image specifically — acceptable
  for a disposable local testing environment, not something to do for a shared/production image.
- **`/tmp` is not a tmpfs in a session**, because of the `dind` patch above — it stays on the
  container's writable layer. Heavy `/tmp` writers (the text-layout audit's Remotion bundle, around
  17 MB a call) therefore consume disk rather than RAM.
- **First launch is slow.** Nested `npm ci`, Chromium, and ffmpeg installs run inside Docker-in-
  Docker. Expect the first `onboard.py` run (renderer image build especially) to take noticeably
  longer than on bare-metal Docker.
- **Resource sizing**: the stack's renderer needs `shm_size: 2gb` for Chromium, on top of the
  Node/Python/ffmpeg footprint of three containers. When registering this image as a Kasm workspace
  (`create_image`), size sessions generously — at least 4 cores / 6–8 GB memory — well above Kasm's
  small default allocation for lightweight desktop images.

## Registering / launching (not automated by this repo)

Registering the built image as a Kasm workspace (via the Kasm admin UI or API) and launching a
session from it is a separate, manual step — out of scope for `build.sh`, which only produces the
Docker image. Once registered, set `"privileged": true` in that image's Docker Run Config Override
(see Caveats above), then launch a session and follow the `onboard.py` steps above.

## Launch form: starting a session clean

`launch_config.json` and `kasm_post_run_root.sh` let a tester wipe the previous session's state
from the launch dialog instead of shelling in and deleting directories by hand. Two Yes/No
questions, both defaulting to **No**:

| Question | Deletes |
|---|---|
| Delete Tubematic Data? | `~/.tubematic-data` — the SQLite DB (all pipeline state **and** the stored API keys), every job directory, every generated scene, every rendered mp4 |
| Delete Tubematic Agent Directory | `~/.tubematic-agent` — every agent's workspace (`~/.tubematic-agent/<agent>/`, the sandbox cron runs it from, with its scoped tool allowlist) and the shared poll logs in `~/.tubematic-agent/logs/` |

Neither field is savable (`allow_saving: false`). Kasm can otherwise remember a user's launch-form
answers, and a remembered "Yes" would silently wipe the data root on *every* later launch.

### Wiring it up

Both halves are manual, like the rest of workspace registration:

1. Paste `launch_config.json` into the workspace's **Launch Config**. Its `file_mapping` block
   writes the tester's answers to `/tmp/launch_selections.json` inside the session.
2. Add `kasm_post_run_root.sh` as a **File Mapping** to `/dockerstartup/kasm_post_run_root.sh`,
   marked **executable**. Mapped files are root-owned with no execute bit by default, and an
   inert hook is indistinguishable from Kasm never invoking one.

The script overwrites one of the base image's own stub hooks — the root-context sibling of the
hook `vqa/kasm_post_run_user.sh` uses, invoked automatically after session start. It is mapped in
rather than baked into the image so it can be changed without a rebuild.

This only does something on a workspace with a **Persistent Profile Path**. Without one, `$HOME`
is fresh every session and there is nothing to delete.

### After a data wipe, re-run onboarding

**`python3 onboard.py` before starting the stack.** Nothing recreates `~/.tubematic-data` — the
hook deletes and stops. `docker-compose.yml` binds its four subdirectories by `device:` path, and
dockerd auto-creates a missing bind source **as root**: invisible to the containers, fatal to
host-side scripts, and unfixable by `mkdir -p`. Onboarding's `directories` step creates them owned
by the session user, which is the only clean way back. Re-entering the four API keys is part of
this — they lived in the database that was just deleted, and each is verified against its provider
as you type it, so there is no import shortcut.

Every decision the hook makes is logged to `~/.tubematic-launch-reset.log` (and to the container
log), including refusals — so "did my data actually get wiped?" has an answer after the fact.

### Logging the agents in

The image ships **all three** agent CLIs — Claude Code, Codex and OpenCode — but no credentials:
none is logged in by the build, and a session starts logged out. `--install-agent` refuses to
proceed against a logged-out CLI, deliberately, because cron runs unattended and a logged-out agent
fails silently on every tick.

```bash
claude                # once, interactively — or: claude auth login
codex login           # device/browser flow
codex login status    # prints "Logged in using ChatGPT" when it worked
opencode auth login   # pick a provider; `opencode auth list` shows what is stored

python3 onboard.py --install-agent claude
python3 onboard.py --install-agent codex
python3 onboard.py --install-agent opencode
```

Installing more than one is supported; the dashboard's Settings → Agents tab picks which is the
default and how new videos are shared between them.

Note that `opencode auth list` exits `0` whether or not anything is stored — read its output, not
its exit code. And log OpenCode in to a **real** provider — its free models are far too weak to
drive this pipeline.

## Local (non-Kasm) alternative

For testing that doesn't need Kasm at all, `~/scripts/tubematic_dev_env.sh` still supports the
original local flow under the `install-local` / `uninstall-local` subcommands (copies the repo to
an isolated local directory and runs `onboard.py`/`uninstall.py` directly on the host). See that
script's own usage text. Its default `install`/`uninstall` now target this Kasm image instead.
