# Installing

`onboard.py` is the canonical way to install Tubematic. It is an interactive wizard that creates the
data directories, seeds the database, verifies your API keys against their providers, installs a
cron entry, and brings up the containers. The agent that does the work is installed afterwards, by
the same script with `--install-agent`.

There is no manual install path that is expected to work. Read this page, then run the wizard. If
you only want the shortest path to a first video, start at the [Quickstart](../quickstart.md) and
come back here when you need the detail.

---

## Two ways to install

Two install routes exist, and they never meet. **Installing from a release is the recommended
route**; building from source is the alternative for people who want to change Tubematic itself.

1. **Download a release tarball (recommended).** A release tarball is an **installer bundle, not a
   source distribution**: it ships `onboard.py`, `upgrade.py`, `uninstall.py`, the root guides and
   this documentation, the handful of host-only scripts onboarding and cron actually run, and the
   `onboard`/`tubematic_core` packages — deliberately **no** `renderer/`, `dashboard/` or `mcp/`
   source tree. Extract it and run the wizard from inside it, and it pulls the published container
   images instead of building anything. The images are public: there is nothing to log in to. A
   release is a version that has been through the full release pipeline, which is why it is the
   route to use unless you have a reason not to. It is also faster to install (nothing is built) and
   needs no Node.js.
2. **Clone and build from source (alternative).** `git clone` this repository, then run the wizard
   from inside it. Docker builds the `tubematic-api`/`tubematic-mcp`/`tubematic-renderer` image and
   the dashboard image locally, from the source trees in the checkout. Use it to work on Tubematic,
   or to run something not yet released — at the cost of a longer first install and of running
   whatever the branch you checked out holds.

There is exactly one compose file either way — the tarball carries only its own, already in release
form (images pinned to a version, ports bound to `127.0.0.1`) — so there is no second,
differently-named compose file and no `-f` flag to remember.

`onboard.py` auto-detects which one you're running by checking for `renderer/Dockerfile`: its
absence is what makes a directory a release install, since a tarball has nothing to build from. It
prints the mode it picked as the first line of output, and records it in `.onboard-state.json`, so a
later "why didn't my change get rebuilt?" can be answered without re-running the wizard. Override
either direction with `--install-mode dev` or `--install-mode release`.

The only things that actually differ between the two are **build vs. pull** at the two container
steps, and that Node.js/npx are not checked at all for a release install — every other step
(directories, the database, API keys and settings, MCP registration, cron) is identical. See the
note on each affected step below, and
[Development — Release tooling](../developer/17-development.md#release-tooling) for how a maintainer
builds the tarball in the first place. Moving an *existing* install to a newer version rather than
installing from scratch is a different procedure — see [Upgrading](07-upgrading.md).

---

## Prerequisites

Install these before running `onboard.py`:

| | Version | Check | Why |
|---|---|---|---|
| Linux host | — | — | The only supported platform. Cron, `flock`, `/proc` and bind-mounted volumes under `~` are all assumed |
| Docker + Compose v2 | — | `docker info`, `docker compose version` | All four services. The Docker daemon must be running |
| Python | 3.11+ | `python3 --version` | The wizard, the poller, host scripts |
| Node.js | **22.20 or newer** | `node --version` | The Remotion skills installer crashes on import below 22.20. Onboarding only *warns* when Node is older or missing, and the Remotion best-practices skill is then not installed; rendering itself runs in a container and is unaffected. Only checked for a **source** install — a release install builds nothing locally and skips this entirely |
| An AI agent CLI | Latest | `which claude` / `which codex` / `which opencode` | Claude Code, Codex, or OpenCode v2 (the `@opencode/cli` package). Needed for `--install-agent`, not for the main wizard; any number may be installed. Log it in first — `claude` once interactively, `codex login`, or `opencode auth login` |
| Disk | ~10 GB | `df -h ~` | Images, `node_modules`, and rendered video |

You will also need API keys. Two are **required** and onboarding will not finish without them:

| Service | Required | Used for | Where to get it |
|---|---|---|---|
| **ElevenLabs** | **yes** | Voicing. There is no fallback provider | elevenlabs.io → Profile → API Keys. The key must carry four permissions: **text-to-speech**, **voices (read)**, **projects (read)** and **pronunciation dictionaries (read)**. Optionally add **user (read)**: it lets the Analytics page show how much of your plan's monthly credit allowance is used |
| **OpenAI** | **yes** | Every scene image, and the Illustrated style's characters. OpenAI is the only image provider | platform.openai.com/api-keys |
| Gemini | no | The mining research strategy and AI review. Without it, mining is off and review is skipped | aistudio.google.com/app/apikey |
| youtube-transcript.io | no | Only for script profiles. Topic mining does not use it | youtube-transcript.io (it has a free tier) |
| postforme.dev | no | Only if you enable publishing | postforme.dev |

Image generation needs billing enabled on the OpenAI project your key belongs to. OpenAI also grants
model access **per project**, so that project must have access to the image model you pick;
onboarding cannot check that for free, so a key without it is refused when the first image is
generated, with an error naming the project and the model. A paid Gemini Advanced chat subscription
is a different product from the Gemini API and grants no API quota.

Publishing needs no YouTube OAuth credentials of your own. Social accounts are connected through
postforme.dev, which holds their tokens, so the only credential Tubematic stores for publishing is
the postforme key. If you enable publishing, connect each social account with the **Connect** buttons
on the dashboard's Socials page. They always grant the **`feeds`** permission as well as `posts`. An
account connected directly on postforme.dev gets `posts` alone by default, and then publishes
normally but reports no views, likes or comments — ever, and without any error saying so. Adding the
permission later means reconnecting the account. See
[Connecting accounts](06-publishing.md#connecting-accounts).

---

## Network exposure

Know what listens before you install. The Flask API (4000) and the MCP server (4100) are bound to
`127.0.0.1` and need a bearer token. The dashboard (3000) is password-protected, but it speaks
**plain HTTP**:

- **Release install:** the dashboard is bound to `127.0.0.1` as well, so only this machine reaches it.
- **Source install:** the development compose file publishes it on **all interfaces**, so anything that
  can reach this machine on port 3000 gets the login page.

Over plain HTTP the password and the session cookie cross the network readable, so treat a source
install's dashboard as trusted-LAN only. To use it from another machine, put HTTPS in front of it
(a reverse proxy such as Caddy or nginx, or a private network such as Tailscale). See
[Infrastructure — Using the dashboard from another machine](../developer/16-infrastructure.md#using-the-dashboard-from-another-machine).

---

## Install

**From a release (recommended).** Download a release's tarball and its checksum from the project's
GitHub Releases page, check it, extract it and run the wizard from inside the extracted directory:

```bash
curl -LO https://github.com/<owner>/<repo>/releases/download/v<version>/tubematic-v<version>.tar.gz
curl -LO https://github.com/<owner>/<repo>/releases/download/v<version>/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-v<version>.tar.gz
cd tubematic-v<version>
python3 onboard.py
```

**From source (alternative):**

```bash
git clone <repo-url> tubematic
cd tubematic
python3 onboard.py
```

**You do not need to create a virtualenv yourself.** The wizard bootstraps itself before it does
anything else: it creates `.venv` in the install directory (if missing), re-executes into it, and
installs the three packages it needs to run (`rich`, `questionary`, `httpx`). This happens even for
`--help`, and it is why the wizard works on a fresh clone with no prior setup. It matters beyond
convenience: Ubuntu and Debian mark the system Python as externally managed, so a bare `pip install`
fails outside a venv, and the cron entry is written with whichever interpreter ran the cron step —
so it has to be the venv the poller's dependencies were installed into. `upgrade.py` and
`scripts/service.py` bootstrap the same way. Run other host scripts with `.venv/bin/python` (or
activate `.venv` first).

The wizard requires a real terminal on both stdin and stdout. `--status`, `--steps`,
`--list-agents` and `--rotate-tokens` are the exceptions and are safe to run from a script.

### The ten steps

Each step's questions, if it has any, are asked right before that step's own action runs. The two
container steps are always last and ask nothing, so no prompt ever interleaves between builds.

| # | Step | What it does |
|---|---|---|
| 1 | `prerequisites` | Checks Docker is running, Compose v2, Python 3.11+ and — for a source install — Node and npx. The agent binary is checked later, by `--install-agent` |
| 2 | `python_deps` | Installs `scripts/requirements.txt` into `.venv` — in both modes, since the poller runs on the host either way |
| 3 | `directories` | Creates `~/.tubematic-data/{jobs,data,output_videos,scenes/generated,logs,backups}` |
| 4 | `database` | Creates the SQLite file, if needed, and runs any pending schema migrations |
| 5 | `auth` | Creates the three service tokens in `~/.tubematic-data/secrets/` (keeps any that exist) and asks for the dashboard password — twice, hidden, at least 12 characters — when none is set. It cannot be skipped |
| 6 | `install_config` | Stores the API keys (**each verified live** as it is typed), the publishing switch and whether AI review is on. Advanced-only: MCP port, render retry budget, pending-topic cap |
| 7 | `pipeline_settings` | Seeds the rest of the dashboard-editable settings. Asked by default: the ElevenLabs voice roster (each voice with the model it speaks with) and default voice, and the image model. Advanced-only: per-run topic caps, trending sources, the research run cap, the render timeout, log and video retention, the AI review model, sampling rate and loop cap, and Auto Pilot |
| 8 | `cron` | Asks for the poll interval (default 30 minutes) and writes one cron entry to your user crontab. See [Manual cron setup](#manual-cron-setup) |
| 9 | `renderer` | Builds one image and starts `tubematic-api`, `tubematic-mcp` and `tubematic-renderer` (release install: pulls the published image instead of building), waiting on the API's and MCP's healthchecks separately and confirming the worker container is running |
| 10 | `dashboard` | Builds and starts `tubematic-dashboard` (release install: pulls instead of building) |

Steps 3 and 4 must precede 9 and 10. If Compose starts first, Docker auto-creates the missing
bind-mount directories **as root**, which the containers can use but host-side tooling cannot. Step
5 must precede them too: Compose refuses to start a service whose token file is missing. A re-run
never changes the password; that is `--set-password`'s job. The tokens and the password are
explained in [Infrastructure — Authentication](../developer/16-infrastructure.md#authentication).

The agent is not one of the steps. It is installed afterwards, with its own command — see
[Install an agent](#install-an-agent). When the wizard finishes with no agent installed, it says so
and prints the next command.

Progress is tracked in `.onboard-state.json` in the install directory, so an interrupted run resumes.

### Questions

On a fresh machine the wizard asks only the questions it cannot answer with a sensible default: the
API keys, whether to publish and review, the voice roster, the image model, and the
cron interval. The rest are marked advanced and take their defaults, editable afterwards on the
dashboard's Settings page; `--full-questionnaire` asks every one.

Three answers are **required** and are re-asked until supplied: the ElevenLabs key, the OpenAI key,
and at least one voice in the roster. Onboarding exists to hand back an install that can actually
run, and none of those three has a fallback or a usable default — an empty voice roster, for
instance, makes the first voicing fail outright, and without the OpenAI key no scene image can be
drawn. The Gemini key is optional: without it, mining is off and AI review is skipped.
`--allow-skipping` lets those answers be left blank at the prompt, though the install configuration
step still refuses to finish without the OpenAI key.

**AI review is asked, and defaults to off.** It is experimental: it needs the Gemini key, and if the
review itself fails, the video reaches your review as if it had passed. See
[Rendering and review](../developer/11-rendering-and-review.md#ai-review).

**"Turn on Auto Pilot?" is one of the advanced ones, on purpose.** It is never asked by the default
questionnaire and defaults to off, and only an explicit yes turns it on. Even then nothing is
approved until a project is selected on the dashboard. Auto Pilot removes the human checkpoints for
the projects you select, so read [Publishing](06-publishing.md) before turning it on; the mechanism
is in [Auto Pilot](06-publishing.md#auto-pilot).

One question is conditional in a way worth knowing about: **"Enable publishing?" is asked first, and
the publishing key is asked only if you say yes.** Answering yes grows the question count for that
step rather than leaving a gap.

Skipping a question is identical to answering it with its default — every field is pre-filled from
current values before anything is asked.

### Flags

| Flag | Effect |
|---|---|
| `--help`, `-h` | Show usage and every flag |
| `--status` | Print which steps are done. Pipeable |
| `--steps` | Print every step and the questions it asks. Pipeable |
| `--step <key>` | (Re-)ask and (re-)apply one step only, regardless of whether it is done. Hyphens and underscores are interchangeable |
| `--force` | Re-run every step regardless of state |
| `--full-questionnaire` | Ask every field, including the advanced ones the minimal flow pre-fills. Combines with `--step` and `--install-agent` |
| `--dry-run` | Walk the whole flow writing nothing — no files, no containers built or started. Prerequisite failures become warnings, so you can preview on an unprepared machine |
| `--install-mode {dev,release}` | Override auto-detection of which install route you're running — see [Two ways to install](#two-ways-to-install) |
| `--allow-skipping` | Accept blanks for required fields |
| `--disable-verification` | Skip live key verification |
| `--install-agent <name>` | Install or update an agent instead of running the wizard. See [Install an agent](#install-an-agent) |
| `--uninstall-agent <name>` | Remove what an agent install deployed and mark the agent uninstalled. See [Uninstall an agent](#uninstall-an-agent) |
| `--list-agents` | List the supported agents and the installed ones, then exit. Pipeable |
| `--set-password` | Set or change the dashboard password. A change signs every browser out. Safe to run before an upgrade from 1.2.x |
| `--rotate-tokens` | Replace the three service tokens and restart the services that hold them. Waits for in-flight work; `--force` proceeds anyway |

Two notes on `--disable-verification`. It does **not** skip the local malformed-paste guard, which
protects what gets *stored* and is not a network check. And it records keys as `UNKNOWN`, never
`VALID`, so nothing downstream can mistake an unchecked key for a verified one.

`--allow-skipping` does not get an install past the OpenAI key: the install configuration step
still refuses to finish without one, since no scene image can be drawn. Both flags print a banner so
the relaxed state is visible rather than silent.

Flags are matched by simple membership, not `argparse`, so a **misspelled flag is silently ignored**
rather than reported.

### Key verification

Each key is probed against its provider the moment you type it. A key the service rejects is refused
and re-asked, so a typo can't be stored and resurface later as a paid call failing mid-pipeline. An
ambiguous answer (rate limit, server error, timeout, or no network at all) is recorded as unknown and
accepted, because refusing a good key because the provider was briefly unhappy would be worse — and
an offline install still completes.

Before any network call, a local guard rejects any character outside printable ASCII — which is what
catches the trailing newline from a terminal copy. Interior spaces are allowed through to the
provider.

The probes check for what Tubematic actually uses, not only that a key is real, and none of them
generates anything or spends anything:

- **ElevenLabs** keys are scoped at creation, so each of the four permissions in
  [Prerequisites](#prerequisites) is probed and any that are missing are named. The text-to-speech
  probe asks for a voice that cannot exist, so it never generates audio or spends a credit.
- **Gemini** is two-layered: an identity probe, then a capability probe for the model mining and
  review use. A capability probe that fails becomes a **warning on an otherwise valid key**, never a
  rejection — the key is optional, and review fails open, so this warning may be the only place a
  quota gap is ever mentioned.
- **OpenAI** is rejected if it cannot reach image generation, since everything it is used for is
  image generation. Whether its project may use a particular image model cannot be checked without
  paying for an image, so that shows up at the first `generate_image`.

How each provider signals a bad key, and the traps in reading those answers, are in
[Settings internals — Rejection signatures](../developer/04-settings.md#rejection-signatures).

---

## Install an agent

The wizard sets up the project, and at that point nothing runs: until an agent is installed, every
cron tick logs `No agent installed` and exits. Install the agent's CLI and log it in — `claude` once
interactively for Claude Code, `codex login` for Codex, `opencode auth login` for OpenCode — then:

```bash
python3 onboard.py --install-agent claude
python3 onboard.py --install-agent codex
python3 onboard.py --install-agent opencode
```

`claude`, `codex` and `opencode` are the supported agents, and any number may be installed at once.
For OpenCode this means the **v2** CLI, `@opencode/cli`; the older `opencode-ai` package is the 1.x
line and is not supported. The command runs in four stages.

1. **Preconditions.** A Tubematic database must exist — otherwise it tells you to run
   `python3 onboard.py` first, because the project is set up before its agents. The agent's binary
   must be in `PATH`, and its own status command (`claude auth status --json`,
   `codex login status`, `opencode auth list`) must report that it is logged in. That check is local
   and makes no model call. Cron runs the agent unattended, so a CLI that is not logged in would fail
   on every tick.
2. **Questions.** Install scope (`user` or `project`; **not asked for Codex**, which supports only
   `user` — see [The Agent Layer](../developer/07-agent-layer.md#agents)), the agent workspace (default
   `~/.tubematic-agent/<agent>`, which may overlap neither another agent's workspace nor the shared
   `~/.tubematic-agent/logs`), whether to wipe that workspace — asked only when it already exists, after a
   preview of what is in it — and the models.
3. **Models.** Enter one per prompt and press Enter on a blank line to finish. Autocomplete offers
   what the installed CLI knows about — for Claude Code the aliases `opus`, `sonnet`, `fable` and
   `haiku` plus its catalog IDs, for Codex its catalog slugs, for OpenCode the slugs
   `opencode models` lists (`anthropic/claude-sonnet-4-5`, and `openrouter/qwen/qwen3.8-27b` where
   the provider namespaces by vendor too) — but you can type any name. Each one is checked against
   the CLI before it is kept: an unknown model costs nothing, a valid one costs one tiny real call.
   **The first model is the agent's default.** At least one is required unless you pass
   `--allow-skipping`. Choosing between an alias and a full ID is covered in
   [The Agent Layer](../developer/07-agent-layer.md#models).
4. **Deploy.** Skills, the MCP registration, Remotion's skills and the logs directory — plus, for
   Claude Code and OpenCode, the slash commands, and for each of them its own permission mechanism:
   Claude Code's workspace allowlist and trust record, OpenCode's permission rules in the
   workspace's `opencode.json`. Codex needs neither, because its equivalent is `-s read-only` on
   argv. See [Deployment](../developer/07-agent-layer.md#deployment). Then the agent's row in the `agents`
   table.

   > **Log OpenCode in to a real provider.** Its free models are far too weak to drive this
   > pipeline. Log in with `opencode auth login`.

Where each agent's files land, by scope:

| Agent / scope | Skills and commands | MCP registration | When to use |
|---|---|---|---|
| **Claude Code, user** (recommended) | `~/.claude/skills/` and `~/.claude/commands/`, plus the skills in the agent workspace | User scope — available in every Claude Code session | Most users |
| **Claude Code, project** | `<workspace>/.claude/skills/` and `<workspace>/.claude/commands/` | Local to the agent workspace | Keeps Tubematic out of your global Claude Code config |
| **Codex** | `~/.codex/skills/` (no commands) | Global — Codex has no MCP scopes | The only Codex layout |
| **OpenCode, user** | `~/.config/opencode/skills/` and `~/.config/opencode/commands/` | Global — available in every OpenCode project | Most users |
| **OpenCode, project** | `<workspace>/.opencode/skills/` and `<workspace>/.opencode/commands/` | The workspace's own config | Keeps Tubematic out of your global OpenCode config |

Either way, cron runs the agent from its workspace, never from the install directory — the agent
only needs the MCP server and the HTTP API, not the source tree, the database or the video volumes.

The MCP server is registered at `http://localhost:4100/mcp`, with a small helper
(`scripts/mcp_auth_header.py`) that hands the CLI the server's token on every connection, so the
token itself never goes into the agent's config. The registration URL does not depend on where the
install directory lives.

`--dry-run` turns the preconditions into warnings, applies nothing, and never probes a model.
`--disable-verification` skips the login check and the model probes.

**Re-run the same command to update.** It is how you change an agent's models, redeploy skills after
editing them, and re-check the models after upgrading the CLI. Every answer is pre-filled from the
agent's row, and pressing Enter at the model prompt keeps the stored list while re-checking each
entry.

### Restart open agent sessions

Agent CLIs read their skills and the MCP server's tool list once, at session start. After an install
or an update, restart any agent session you have open. You never need one to run Tubematic — the
dashboard does everything and the scheduled pipeline starts the agent itself — but if you want to use
the tools interactively, open a session
the way the scope implies: anywhere for a user-scope install, from the workspace
(`cd ~/.tubematic-agent/claude && claude`, by default) for a project-scope one. Then check the tools
answer — ask the agent for the Tubematic pipeline status, or run `/tubematic-status` on Claude Code
or OpenCode. If the tools are missing, see
[Troubleshooting — The agent has no Tubematic tools](08-troubleshooting.md#the-agent-has-no-tubematic-tools).

Pick the default agent, each agent's share of new videos, and each agent's default model on the
dashboard's Settings → Agents tab. `python3 onboard.py --list-agents` prints the supported agents and
the installed ones, with their weights and models, without needing a terminal.

## Uninstall an agent

```bash
python3 onboard.py --uninstall-agent claude
```

After a confirmation it removes what that agent's install deployed — the Tubematic skills (and, for
Claude Code and OpenCode, the commands), from the home directory and the workspace for a `user`
install or from the workspace for a `project` one, and the `tubematic` MCP registration — then marks
the agent's row uninstalled. It keeps:

- **The workspace**, which may hold the agent's own working files. The poll logs are not in it —
  they live beside every workspace, in `~/.tubematic-agent/logs/`.
- **The row**, archived rather than deleted, so a video already assigned to the agent keeps
  resolving it. The poller logs and skips such a video every tick until the agent is re-installed;
  it is never handed to another agent.
- **Remotion's own skills**, which are not Tubematic's to remove.

The default agent cannot be uninstalled while another agent is installed — make another one the
default on the dashboard first. The last agent can go; after that every tick logs
`No agent installed`. `--install-agent` brings the same row back, weight and default flag included.
To remove the whole project instead, see [Uninstalling](#uninstalling).

---

## First video

Open `http://localhost:3000`, sign in with the password you set during onboarding, and go to the
**New Video** page. Enter a title and the topic and submit. The video is not scored and is filed
under **Manual Videos**; with **Automatically approve topic** left on, the next poll scripts it.
This works the same whichever agent you installed. See
[The Dashboard — New Video](04-dashboard.md#new-video).

An agent session is an optional alternative: `/tubematic-submit-new-job How DNS resolution works`
on Claude Code or OpenCode, or the same request in plain words on Codex, which has no slash
commands. That route scores the topic and files it into a matching project domain instead of
**Manual Videos** — see [Using Tubematic — Manual](03-using-tubematic.md#manual--make-a-video-about-x).

Then:

1. **Approve the script** on the dashboard. This is the money checkpoint; nothing has been spent yet.
2. The agent voices it, generates images, writes the scene components, validates, and queues a
   render.
3. The worker renders and the AI reviewer watches the result.
4. **Approve the video** at `VIDEO_READY`, after actually watching it.

The dashboard's **Pipeline** page shows where every video is. Day-to-day use is covered in
[Using Tubematic](03-using-tubematic.md).

---

## Verifying an install

```bash
python3 onboard.py --status                # which steps completed
TOKEN="Authorization: Bearer $(cat ~/.tubematic-data/secrets/api_token)"
curl -s localhost:4000/health                          # Flask → {"status":"ok"}
curl -s localhost:4100/health                          # the MCP server, a separate container
curl -s localhost:4000/render/health                   # Chromium inside the container
curl -s -H "$TOKEN" localhost:4000/pipeline/status     # the full readout
curl -s -H "$TOKEN" localhost:4000/agents              # the installed agents and their models
python3 scripts/service.py status          # version, schema, cron entry, all four containers
crontab -l | grep poll.py                  # exactly one line
.venv/bin/python scripts/poll.py --dry-run # what the next tick would do, without doing it
.venv/bin/python scripts/status.py         # videos, costs, disk usage
```

Then open `http://localhost:3000` and sign in. The version badge in the top bar reads the version
from the running API, so it shows what is actually serving.

If you also use an agent session, `/tubematic-dashboard-status` runs the container checks from
there, and `/tubematic-register-mcp` re-registers the MCP server if its tools have gone missing.

---

## Manual cron setup

If the cron step failed or you skipped it, add the entry yourself with `crontab -e`:

```cron
# Tubematic — managed by onboard.py — do not edit manually
*/30 * * * * <install-dir>/.venv/bin/python3 <install-dir>/scripts/poll.py >> ~/.tubematic-agent/logs/cron.log 2>&1
```

Use **absolute paths** — cron runs with a minimal `PATH` — and the install's own `.venv` interpreter,
which is the one the poller's dependencies were installed into. Create `~/.tubematic-agent/logs/`
first: the shell redirect, and the tick with it, fails if the directory is missing. Re-running
`python3 onboard.py --step cron` writes the same line for you and is the better fix.

The line names no agent; the poller asks the API which agent each video belongs to, so installing or
removing an agent never touches cron. The poll interval is baked into this line: changing it later
means re-running the cron step, because editing the stored setting alone does nothing. The interval
is how soon an idle install notices new work, not how often videos advance — while there is work,
the poller keeps running and starts each next stage as soon as the last one finishes. See
[The Poller](../developer/13-the-poller.md).

The poller's own log is `~/.tubematic-agent/logs/poll.log`. `cron.log` only catches output from
before logging starts (an import error, say), so **an empty `cron.log` is normal** and says nothing
about whether the poller is running.

---

## Where configuration lives

| | |
|---|---|
| **Settings and API keys** | Rows in `~/.tubematic-data/data/tubematic.db` |
| **Install-time answers** | The same table, seeded by onboarding |
| **Installed agents** | The `agents` table, written by `--install-agent` |
| **Service tokens and the session key** | `~/.tubematic-data/secrets/` |
| **The output-video path for Compose** | `docker-compose.override.yml`, generated by the `renderer` step. Compose interpolation cannot read SQLite, which is why that single value is materialised as a file |
| **Wizard progress** | `.onboard-state.json` in the install directory |

**There is no `.env` file.** Credentials live in the settings table so they can be rotated from
the dashboard without a restart and verified at the moment they are entered. No Compose service has
an `env_file`, so `docker inspect` exposes no keys.

Change a setting on the dashboard's Settings page, through `POST /settings`, or with
`vqa/edit_settings.py` (source checkout only). **No setting requires a restart** — every process
reads per use. API keys show as a mask on the dashboard, never in full, and a rotated key takes
effect on the next call. See [Settings](05-settings.md).

The one exception is `poll_interval_mins`, which is baked into the crontab line. Editing that row
does nothing until you re-run `python3 onboard.py --step cron`.

---

## Re-running onboarding

Completed steps are skipped automatically, so re-running the wizard is safe:

```bash
python3 onboard.py                       # skip done steps, run pending ones
python3 onboard.py --step install_config # re-ask and re-apply just that step
python3 onboard.py --step cron           # rewrite the cron line (after changing the poll interval)
python3 onboard.py --install-agent claude  # redeploy skills/commands, re-check models
python3 onboard.py --force               # re-run everything from scratch
python3 onboard.py --dry-run             # preview any of the above — nothing changes
```

Re-running a step re-seeds the settings it owns from your answers, which are pre-filled from the
current values.

---

## Upgrading

Moving to a newer version is `upgrade.py`, run from the version you are moving *to*. Everything
about it — what it checks, its flags, both routes, and rollback — is in [Upgrading](07-upgrading.md).

The two sections below are one-time migrations for installs that predate the versioned release
process. They are not the general upgrade path.

### Upgrading from a `.env` install

Tubematic used to keep configuration in a `.env` file. It now keeps everything — API keys included —
in the settings database, and the compose file no longer loads `.env` at all. **An existing install
breaks the moment its containers restart on the new code**, because the keys they used to receive as
environment variables are no longer being injected.

`.env` is not read anywhere, including by onboarding: it is not a fallback and not a migration
source. Upgrading means re-entering your keys once.

```bash
git pull

# Pipeline data now lives outside the checkout. Move it before onboarding,
# or onboarding starts from an empty tree and your video library is stranded.
mkdir -p ~/.tubematic-data
mv mounted/data mounted/jobs mounted/output_videos mounted/scenes ~/.tubematic-data/
rmdir mounted

python3 onboard.py
python3 onboard.py --install-agent claude
rm .env
```

The `renderer` step also recreates the Docker named volumes. It has to: Docker fixes a volume's bind
device when the volume is created, so editing `docker-compose.yml` does not move an existing one —
Compose notices and *prompts*, which onboarding (running non-interactively) answers with "no",
leaving the containers mounted on the old, now-moved tree. Onboarding detects the mismatch and
recreates them. **No data is lost**: these are bind volumes, so the files live at the device path and
only Docker's record is dropped.

`onboard.py` recognises a pre-migration install by itself: the old `env` step became
`install_config`, so it has never run and runs now, asking for the keys; and the cron line and both
container steps are marked for rebuild, because each is generated from configuration that has moved.

Re-entering rather than importing is deliberate: onboarding verifies every key against its provider
as you type it and refuses one the service rejects. An imported key would skip that check and fail
later, at first use, having already been stored.

### Upgrading from a version without `--install-agent`

Older versions set the agent up inside the main wizard (a `claude` step) and kept its scope,
workspace and binary in the settings table, plus one install-wide agent model. After rebuilding the
stack:

```bash
python3 onboard.py --install-agent claude   # pre-fills from the old rows, then deletes them
python3 onboard.py --step cron              # drops --agent-run-path / --agent-binary from the crontab
```

Until the first command runs, every tick logs `No agent installed`. The old install-wide model
setting is not carried over, so enter the models at the prompt. The old cron flags are ignored with a
warning in the meantime, so the second command is tidy-up rather than urgent.

---

## Install problems

Problems with a running install — nothing happening, renders, review, voice, the dashboard — are in
[Troubleshooting](08-troubleshooting.md). These are the ones you meet while installing.

> The `docker compose build --no-cache` commands below are for a **source** install. A release
> install has no source tree to rebuild from — use `docker compose pull <service>` instead, or
> `python3 upgrade.py` to pull and restart everything in order.

**`docker compose pull` fails on a release install.** The images are public, so this is not a login
problem: the wizard shows Docker's own reason. It is usually this machine not reaching `ghcr.io`
(a proxy or firewall), or a tarball whose version has no published images. Fix that, then re-run
the step: `python3 onboard.py --step renderer --force` (and `--step dashboard --force` if that pull
failed too).

**`tubematic-api` won't start.**

```bash
docker compose logs tubematic-api
docker compose build --no-cache tubematic-api
```

**`tubematic-mcp` or `tubematic-renderer` won't start.** Both run the `tubematic-api` image — there is
no separate build — so rebuild that one:

```bash
docker compose logs tubematic-mcp
docker compose logs tubematic-renderer
docker compose build --no-cache tubematic-api && python3 scripts/service.py start
```

**Port 4100 is not reachable, or the agent has no Tubematic tools.** Check `tubematic-mcp`, not
`tubematic-api`: they are separate containers, so a healthy Flask says nothing about whether the
agent's tools are reachable. See
[Troubleshooting — The agent has no Tubematic tools](08-troubleshooting.md#the-agent-has-no-tubematic-tools).

**Cron runs but nothing happens.** If `poll.log` says `No agent installed`, the project is set up but
no agent is: run `python3 onboard.py --install-agent <agent>`. For the other answers, see
[Troubleshooting — Nothing is happening](08-troubleshooting.md#nothing-is-happening).

**The agent binary is not found by cron.** `--install-agent` stores the absolute path of the binary it
found, and the poller re-checks that path before every run, so cron's minimal `PATH` does not matter.
If `poll.log` says the binary was not found — the CLI was moved or reinstalled somewhere else — re-run
`python3 onboard.py --install-agent <agent>`.

**Database errors ("no such table").** Re-run the database step; it is idempotent:
`python3 onboard.py --step database`.

**The dependency install fails.** Re-run it by hand with
`.venv/bin/python -m pip install -r scripts/requirements.txt`. The MCP server's own requirements are
installed inside its container, never on the host.

---

## Uninstalling

```bash
python3 uninstall.py
```

To remove one agent and keep the project, use [Uninstall an agent](#uninstall-an-agent) instead. To
go back to an older version rather than removing Tubematic, see
[Upgrading — Rollback policy](07-upgrading.md#rollback-policy).

Every step asks for confirmation before deleting anything, and every prompt **defaults to no**.
`--yes`, `-y` or `--force` confirms every step without asking. There is no `--help`; unrecognised
arguments are swallowed silently.

| Step | What it removes |
|---|---|
| 1 · Containers | `docker compose down` — stops and removes `tubematic-api`, `tubematic-mcp`, `tubematic-renderer` and `tubematic-dashboard` |
| 2 · Docker volumes | The named volumes. They are bind volumes, so the files in `~/.tubematic-data/` are untouched |
| 3 · Database | `~/.tubematic-data/data/tubematic.db` — all pipeline state and settings |
| 4 · Job files | `~/.tubematic-data/jobs/*` — each video's audio, timeline and scene config |
| 5 · Generated scenes | `~/.tubematic-data/scenes/generated/*` — the agent-written scene components |
| 6 · Agent integration | Each installed agent's skills, commands and MCP registration (and, for a project-scope Claude Code install, the agent workspace) |
| 7 · Cron | The Tubematic lines in your user crontab |
| 8 · Generated files | `docker-compose.override.yml`, and any leftover `.env` |
| 9 · Data root | Offers to delete `~/.tubematic-data/` outright — **including rendered videos** |

Step 6 reads Claude Code's install scope and workspace from its row in the `agents` table, falling
back to the settings rows an older install kept them in; if neither is there, it asks. It then sweeps
every other supported agent separately — Codex's `~/.codex/skills/` and global MCP registration,
OpenCode's skills, commands and MCP entry — since each keeps its files somewhere else. Each sweep
uses that agent's own recorded scope, read while the database still exists: a project-scope agent
keeps everything under its workspace, so looking in the user directories would find nothing and
leave the whole install behind. For the same reason the sweep ignores any config-root environment
override: the directories to clean are the ones a scheduled run uses, and cron never inherits one.
The sweeps are silent on a machine where the agent was never installed.

OpenCode has no `mcp remove` command, so its entry is edited out of your config file, leaving
everything else in it untouched — **including your comments**, because the edit is made on the text
rather than by rewriting the file. The result must still parse and differ from the original by
exactly that one entry, or the file is left alone and the change is reported for you to make by
hand. Tubematic's own config file inside the agent workspace is simply deleted; the installer
refuses a workspace that already holds an OpenCode config, so that file is never one of yours.

Step 9 is the only step that can remove your rendered videos, and it names how many are at stake in
the prompt itself. It exists because the data root sits outside the install directory: deleting the
repository does **not** remove it. Decline it and the step prunes whatever subdirectories are already
empty, then tells you the path so you can finish by hand.

### What is not removed

- **Rendered videos** in `~/.tubematic-data/output_videos/` — no individual step touches these; only
  step 9, which asks explicitly and defaults to no.
- **The service tokens** in `~/.tubematic-data/secrets/` — only step 9 removes them. Declining it,
  the step names their path; a reinstall creates new ones, so they are safe to delete by hand.
- **Docker images** — the built or pulled images stay cached, and a later install reuses them.
- **The install directory itself** — delete it by hand.

### Removing everything

```bash
# 1. Run the uninstaller and say yes to every step
python3 uninstall.py

# 2. Remove the images. tubematic-api, tubematic-mcp and tubematic-renderer share one.
# Source install (built locally):
docker rmi tubematic-renderer-image tubematic-tubematic-dashboard
# Release install (pulled) — check `docker images | grep tubematic` for the exact tags:
docker rmi ghcr.io/<owner>/tubematic-backend:<version> ghcr.io/<owner>/tubematic-dashboard:<version>

# 3. Remove any leftover volumes
docker volume ls -q | grep tubematic | xargs -r docker volume rm

# 4. Delete the install directory
cd .. && rm -rf tubematic
```

### Cleaning up without uninstalling

| To… | Run |
|---|---|
| Stop the containers, keeping everything | `python3 scripts/service.py stop` |
| Remove only the cron entry | `crontab -e`, and delete the `# Tubematic` comment and the `poll.py` line |
| Clear videos from the database (interactive: delete videos, reset statuses, or a full wipe) | `.venv/bin/python scripts/clear_db.py` — source checkout only |
| Reclaim job directories, keeping rendered videos and the database | `.venv/bin/python scripts/cleanup_jobs.py` — source checkout only. Published videos' files are already removed automatically after the retention period |

---

## Testing without touching your machine

`kasm_workspace/` builds a disposable browser-accessible desktop with Docker-in-Docker, where you can
run the entire onboarding flow from scratch as a new user would. `vqa/` builds a sibling environment
aimed at judging rendered video quality, with the setup pre-baked. Both are in a source checkout
only. See [Development](../developer/17-development.md#test-environments).
