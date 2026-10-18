# Tubematic — Installation

Tubematic installs on one Linux machine with Docker, Python 3.11+ and an AI agent CLI (Claude Code,
Codex or OpenCode). `onboard.py` is an interactive wizard that sets up the data directories and
database, verifies your API keys, writes the cron entry and starts the containers; the agent is
installed afterwards with `--install-agent`. Run both from inside an extracted release tarball —
the recommended route, which pulls ready-built images — or from a source checkout:

```bash
python3 onboard.py
python3 onboard.py --install-agent claude    # or: codex, opencode
```

- **New here?** [Quickstart](docs/quickstart.md) — requirements, costs, install and a first video.
- **The full guide:** [Installing](docs/user-guide/02-installing.md) —
  [prerequisites and API keys](docs/user-guide/02-installing.md#prerequisites),
  [network exposure](docs/user-guide/02-installing.md#network-exposure),
  [the wizard's steps and flags](docs/user-guide/02-installing.md#install),
  [installing an agent](docs/user-guide/02-installing.md#install-an-agent),
  [verifying an install](docs/user-guide/02-installing.md#verifying-an-install),
  [manual cron setup](docs/user-guide/02-installing.md#manual-cron-setup) and
  [install problems](docs/user-guide/02-installing.md#install-problems).
- **Moving to a newer version:** [Upgrading](docs/user-guide/07-upgrading.md).
- **Removing it:** [UNINSTALL.md](UNINSTALL.md).
