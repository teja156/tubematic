# Tubematic: Installation

Tubematic installs on one Linux machine with Docker, Python 3.11 or newer and an AI agent CLI
(Claude Code, Codex or OpenCode). Run the wizard from this directory, then install an agent:

```bash
python3 onboard.py
python3 onboard.py --install-agent claude    # or: codex, opencode
```

- New here? Start with the [Quickstart](docs/quickstart.md).
- The full guide is [Installing](docs/user-guide/02-installing.md). It covers the
  [prerequisites and API keys](docs/user-guide/02-installing.md#prerequisites),
  [checking the install](docs/user-guide/02-installing.md#check-the-install),
  [network exposure](docs/user-guide/02-installing.md#network-exposure) and
  [install problems](docs/user-guide/02-installing.md#install-problems).
- Each step, question and flag of the wizard is in the
  [Command Reference](docs/user-guide/15-command-reference.md#onboardpy).
- Agents are covered in [Agents](docs/user-guide/12-agents.md).
- To move to a newer version, see [Upgrading](docs/user-guide/07-upgrading.md).
- To remove Tubematic, see [UNINSTALL.md](UNINSTALL.md).
