# Command Reference

Every command you run on the machine Tubematic is installed on. Run them from the install directory,
the one that holds `onboard.py`.

| Command | Use it to |
|---|---|
| [`python3 onboard.py`](#onboardpy) | Install, change install-time answers, manage agents, set the password |
| [`python3 scripts/service.py`](#scriptsservicepy) | Start, stop, restart and check the containers |
| [`python3 upgrade.py`](#upgradepy) | Move to a newer version |
| [`python3 uninstall.py`](#uninstallpy) | Remove Tubematic |
| [Other scripts](#other-scripts) | Check status, preview the next run, collect a bug report |

`onboard.py`, `upgrade.py` and `scripts/service.py` create a Python virtual environment in `.venv`
inside the install directory the first time you run one, and restart themselves inside it. You do
not create or activate it yourself.

---

## `onboard.py`

With no flags, `onboard.py` runs the install wizard. It needs a terminal, because it asks
questions. A step that already finished is skipped, so running it again is safe.

### Steps

| # | Key | What it does | Asks |
|---|---|---|---|
| 1 | `prerequisites` | Checks Docker, the Compose plugin, Python, Node.js and `npx` | Nothing |
| 2 | `python_deps` | Installs the scheduled poller's Python packages into `.venv` | Nothing |
| 3 | `directories` | Creates the folders under `~/.tubematic-data/` | Nothing |
| 4 | `database` | Creates the database, or updates an older one | Nothing |
| 5 | `auth` | Creates the service tokens and the render gateway's certificate in `~/.tubematic-data/secrets/` | The dashboard password, when none is set |
| 6 | `install_config` | Stores the API keys and the publishing and AI review switches | The keys and the two switches |
| 7 | `pipeline_settings` | Stores the rest of the settings | The image model |
| 8 | `cron` | Writes one entry to your crontab | The poll interval |
| 9 | `gpu` | Hands an NVIDIA GPU to the renderer, or none | Which GPU, when one is usable |
| 10 | `renderer` | Pulls or builds the backend image and starts four containers | Nothing |
| 11 | `dashboard` | Pulls or builds the dashboard image and starts it | Nothing |

One more step, `renderers`, is not part of an install. Run it by name to let other machines render
for this one. See [Remote Renderers](11-remote-renderers.md).

### Questions

The wizard asks these by default:

| Question | Default | Required |
|---|---|---|
| Dashboard password, twice | None. At least 12 characters | Yes |
| ElevenLabs API key | None | Yes |
| Gemini API key | None | No |
| OpenAI API key | None | Yes |
| youtube-transcript.io API key | None | No |
| Enable publishing to social platforms? | No | No |
| postforme.dev API key, asked when publishing is on | None | No |
| Enable Gemini defect review? (Experimental) | No | No |
| Image generation model | `gpt-image-2.5-flare` | No |
| Cron poll interval (minutes) | 30 | No |
| Render on (which GPU), asked when a GPU is usable | The first GPU | No |

Every other setting takes its default. `--full-questionnaire` asks those as well: the research
limits, the trending sources, the voices, the render timeout, how long logs and published videos
are kept, Auto Pilot, the AI review model and rounds, the render retries, the MCP port and the
pending-topic limit. You can change all but the MCP port on the dashboard later.

Pressing Enter on a question keeps the value shown.

### How keys are checked

The wizard sends each key to its provider as you enter it. None of these checks generates anything
or spends anything.

- A key the provider rejects is refused, and the wizard asks again.
- A key the wizard cannot check, because the provider is down or the machine is offline, is
  accepted.
- A key that contains a line break or a non-ASCII character is refused before it is sent. This
  catches a bad paste.
- For ElevenLabs, the wizard names any permission the key lacks.
- For Gemini, a key that is valid but has no quota for the review model is accepted with a warning.

The wizard cannot check whether your OpenAI project may use the image model you pick. If it may
not, the first image fails with an error that names the project and the model.

### Flags

| Flag | What it does |
|---|---|
| `--status` | Prints which steps are done |
| `--steps` | Prints every step and what it asks |
| `--step <key>` | Runs one step again, whether or not it is done |
| `--force` | Runs every install step again |
| `--full-questionnaire` | Asks every question. Works with `--step` and `--install-agent` |
| `--dry-run` | Asks the same questions and changes nothing |
| `--install-mode dev` or `release` | Overrides whether images are built or pulled |
| `--allow-skipping` | Lets you leave the ElevenLabs key blank. The OpenAI key is still required |
| `--disable-verification` | Stores keys without checking them with their providers |
| `--install-agent <name>` | Installs or updates an agent. See [Agents](12-agents.md) |
| `--uninstall-agent <name>` | Removes what an agent install put in place |
| `--list-agents` | Lists the supported agents and the installed ones |
| `--set-password` | Sets or changes the dashboard password. A change signs every browser out |
| `--rotate-tokens` | Replaces the service tokens and restarts the containers that hold them. Signs every browser out |
| `--help`, `-h` | Prints the flags |

`--status`, `--steps`, `--list-agents` and `--rotate-tokens` do not need a terminal, so you can run
them from a script.

A misspelled flag is ignored without an error. If a flag seems to do nothing, check its spelling.

### Common uses

```bash
python3 onboard.py --step install_config   # change an API key or the publishing switch
python3 onboard.py --step cron             # change the poll interval
python3 onboard.py --step gpu              # pick a GPU, or go back to the CPU
python3 onboard.py --set-password          # change the dashboard password
python3 onboard.py --install-agent claude  # update an agent's models and skills
```

### Manual cron setup

The `cron` step writes this entry for you. If it failed, add the entry yourself with `crontab -e`:

```cron
*/30 * * * * <install-dir>/.venv/bin/python3 <install-dir>/scripts/poll.py >> ~/.tubematic-agent/logs/cron.log 2>&1
```

- Use full paths. Cron runs with a minimal `PATH`.
- Create `~/.tubematic-agent/logs/` first. Without it the line fails before the poller starts.
- Keep one entry. The entry names no agent, so installing or removing an agent does not change it.

The poller writes its own log to `~/.tubematic-agent/logs/poll.log`. `cron.log` only catches output
from before the poller's logging starts, so an empty `cron.log` is normal.

The interval lives in this line. To change it, run `python3 onboard.py --step cron`.

---

## `scripts/service.py`

```bash
python3 scripts/service.py start   [service]
python3 scripts/service.py stop    [service] [--force]
python3 scripts/service.py restart [service] [--force]
python3 scripts/service.py status
python3 scripts/service.py logs    [service] [-f]
```

The services are `tubematic-api`, `tubematic-mcp`, `tubematic-worker`, `tubematic-renderer` and
`tubematic-dashboard`. Leave the service out to act on all five.

Use this script in place of `docker compose`. It reads the GPU and remote-renderer choices stored
with your data, which a bare `docker compose up` skips. A renderer started with a bare
`docker compose up` loses its GPU.

| Command | Notes |
|---|---|
| `start` | Creates any missing data folder, then starts the containers and waits until they are healthy |
| `stop`, `restart` | Refuse while a render, a voicing, an agent session or an upload is running, because stopping would lose that work. `--force` stops anyway |
| `status` | Prints the version, the database version, the cron entry, each container's state, what the renderer renders on, and whether remote renderers are on. Exits 0 when nothing needs attention |
| `logs` | Prints the last 200 lines of a container's output. `-f` keeps following |

`--dry-run` shows what a command would do and changes nothing.

The containers restart with Docker. After a reboot they come back when the Docker service starts,
unless you stopped them with `stop`.

---

## `upgrade.py`

[Upgrading](07-upgrading.md) has the procedure. The flags:

| Flag | What it does |
|---|---|
| `--check` | Reports the install's state and changes nothing |
| `--dry-run` | Shows each step it would take and changes nothing |
| `--force` | Goes ahead while work is running. That work is lost |
| `--no-stop` | Recreates the containers one at a time without stopping them all first. `upgrade.py` refuses it for an upgrade that needs a full stop |
| `--install-mode dev` or `release` | Overrides whether images are built or pulled |

---

## `uninstall.py`

```bash
python3 uninstall.py
```

It works through nine steps and asks before each one. `--yes` answers yes to every step.

| Step | Removes | Default answer |
|---|---|---|
| 1 | The five containers | Yes |
| 2 | The Docker volumes. Your files in `~/.tubematic-data/` stay | Yes |
| 3 | The database: every video's record, and your settings and API keys | No |
| 4 | Each video's working files: audio, timing and scene list | No |
| 5 | The scene code the agent wrote | No |
| 6 | Each agent's Tubematic skills, commands and tool registration | Yes |
| 7 | The cron entry | Yes |
| 8 | A leftover `docker-compose.override.yml` or `.env` from an old install | Yes for the first, no for the second |
| 9 | `~/.tubematic-data/` as a whole, including your rendered videos | No |

Step 9 is the only step that deletes rendered videos, and it says how many there are before it
asks.

The uninstaller leaves these in place:

- The install directory. Delete it yourself.
- The Docker images. Remove them with `docker rmi` if you want the disk back. `docker images | grep tubematic` lists them.
- Renderers on other machines. Run `python3 tubematic_remote_renderer.py remove` on each one.
- Anything under `~/.tubematic-data/` you chose to keep.

To remove one agent and keep Tubematic, use
[`--uninstall-agent`](12-agents.md#uninstall-an-agent).

---

## Other scripts

| Command | What it does |
|---|---|
| `python3 scripts/status.py` | Prints videos waiting for you, a count per status, recent videos, this month's spend and disk use |
| `python3 scripts/poll.py --dry-run` | Prints what the next scheduled run would start, and starts nothing |
| `python3 scripts/poll.py` | Starts a scheduled run now, without waiting for cron |
| `python3 scripts/collect_diagnostics.py` | Writes a redacted report for a bug report. See [Reporting a bug](08-troubleshooting.md#reporting-a-bug) |
| `python3 tubematic_remote_renderer.py` | Sets up and manages a renderer on another machine. See [Remote Renderers](11-remote-renderers.md) |

Two more scripts exist in a source checkout only. `scripts/cleanup_jobs.py` deletes videos' working
files, and `scripts/clear_db.py` deletes or resets videos in the database. Both show a menu and ask
before they delete.
