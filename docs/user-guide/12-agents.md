# Agents

An agent is the AI coding tool that writes the scripts and scenes. Tubematic drives three of them:
Claude Code, Codex and OpenCode. You install at least one, and Tubematic starts it on a schedule.
You do not have to open an agent session yourself.

---

## Supported agents

| Agent | Command | Log in with | Slash commands |
|---|---|---|---|
| Claude Code | `claude` | Run `claude` once and follow the prompts | Yes |
| Codex | `codex` | `codex login` | No |
| OpenCode v2 | `opencode` | `opencode auth login` | Yes |

OpenCode means the v2 CLI, the `@opencode/cli` package. The older `opencode-ai` package is not
supported. Log OpenCode in to a paid provider: its free models are too weak to write a video.

You can install any number of agents side by side.

## Install an agent

Install the agent's CLI, log it in, then run this from the install directory:

```bash
python3 onboard.py --install-agent claude     # or: codex, opencode
```

The command first checks that Tubematic is installed, that the CLI is on your `PATH`, and that the
CLI is logged in. Then it asks:

| Question | Notes |
|---|---|
| Install scope | `user` puts Tubematic's skills in your home directory, so every session of that agent has them. `project` keeps them inside the agent's workspace. Codex supports `user` only and is not asked |
| Workspace | The directory scheduled runs start from. Default `~/.tubematic-agent/<agent>`. Each agent needs its own |
| Wipe the workspace | Asked only when the workspace exists, after showing what is in it |
| Models | Enter one per prompt and press Enter on an empty line to finish. The first one is the agent's default |

The command checks each model with the CLI before it keeps it. An unknown model costs nothing. A
valid one costs one very small call. You can type any model name; the suggestions come from what the
installed CLI knows.

After the questions it copies Tubematic's skills and slash commands into place, registers
Tubematic's tools with the CLI (at `http://localhost:4100/mcp`), installs the Remotion skill, and sets up what the agent may do
without asking, so a scheduled run does not stop at a permission prompt.

The Remotion skill needs Node.js 22.20 or newer. Without it the command warns that it skipped the
Remotion skills and finishes, and the agent writes scenes without them. Install Node and run the
command again.

If you had an agent session open, restart it. An agent reads its skills and tools once, when a
session starts.

### Where the files go

| Agent and scope | Skills and commands | Tools registered |
|---|---|---|
| Claude Code, `user` | `~/.claude/skills/` and `~/.claude/commands/`, and the skills again in the workspace | For every Claude Code session |
| Claude Code, `project` | `<workspace>/.claude/` | For the workspace only |
| Codex | `~/.codex/skills/` | For every Codex session |
| OpenCode, `user` | `~/.config/opencode/skills/` and `~/.config/opencode/commands/` | For every OpenCode project |
| OpenCode, `project` | `<workspace>/.opencode/` | For the workspace only |

Scheduled runs start from the agent's workspace. The agent reaches Tubematic only through its tools,
so it needs neither the install directory nor the database.

## Update an agent

Run the same command again. Do this to:

- change the agent's models,
- copy skills into place again after you edit one,
- check the models again after you upgrade the CLI.

Each question shows the stored answer. Press Enter at the model prompt to keep the stored list; the
command checks each model again.

## Choose which agent makes a video

Tubematic gives each new video to an agent by share. Set the shares on **Settings → Agents**, where
you also set:

- the default agent,
- each agent's default model,
- each agent's effort level: `low`, `medium`, `high` (the default), `xhigh` or `max`.

You cannot add or remove a model on that tab, because the dashboard has no CLI to check one with.
Use `--install-agent` for that.

To change one video's agent, model or effort, use the pickers on the video at Topic Proposed, Script
Ready or Video Ready. Picking a different agent resets the model to that agent's default.

`python3 onboard.py --list-agents` prints the supported agents and the installed ones, with their
shares and models.

## Uninstall an agent

```bash
python3 onboard.py --uninstall-agent claude
```

After you confirm, the command removes Tubematic's skills, commands and tool registration for that
agent. It keeps:

- the workspace, which may hold the agent's own files,
- the agent's record, so videos already assigned to it still name it,
- the Remotion skill, which other projects may use.

A video assigned to an uninstalled agent waits. Tubematic does not hand it to another agent. Install
the agent again, or pick another agent on the video.

You cannot uninstall the default agent while another agent is installed. Make another one the
default on **Settings → Agents** first.

To remove Tubematic altogether, see [Uninstalling](02-installing.md#uninstalling).

---

## Running an agent session yourself

This is optional. Everything below has an equivalent on the dashboard.

Open the agent from its workspace:

```bash
cd ~/.tubematic-agent/claude && claude
```

Claude Code and OpenCode have these slash commands:

| Command | What it does | On the dashboard |
|---|---|---|
| `/tubematic` | Lists the commands | |
| `/tubematic-status` | Shows videos by stage, spend and container health | **Pipeline** page |
| `/tubematic-submit-new-job <topic>` | Scores a topic and creates a video from it | **New Video** page |
| `/tubematic-add-topic <domain>` | Adds a domain for curriculum research | **Topics** page |
| `/tubematic-pause-domain <id>` | Stops research in one domain | **Pause topic generation** on the domain's row |
| `/tubematic-resume-domain <id>` | Resumes it | The same button |
| `/tubematic-list-strategies` | Shows the research modes that are on | **Topics** page |
| `/tubematic-set-strategy <modes>` | Turns research modes on or off | The toggles on the **Topics** page |
| `/tubematic-pause` | Pauses the pipeline | The switch above the tabs on **Settings** |
| `/tubematic-resume` | Resumes it | The same switch |
| `/tubematic-dashboard-status` | Checks the containers are running | `python3 scripts/service.py status` |
| `/tubematic-register-mcp` | Registers Tubematic's tools with the agent again | See [Troubleshooting](08-troubleshooting.md#the-agent-has-no-tubematic-tools) |

Codex has no slash commands. Ask in plain words, for example "show the Tubematic pipeline status".
It has the same tools and skills.

`/tubematic-submit-new-job` differs from the New Video page in two ways. The agent scores the topic
first and declines one that scores below 5, with advice on how to reframe it. It also files the
video in a matching domain, where the New Video page files it under **Manual Videos**.

### Getting help from the agent

Each agent has a troubleshooting skill that walks through a problem with you and drafts a bug
report. It runs only when you ask for it by name:

| Agent | How to start it |
|---|---|
| Claude Code | `/tubematic-troubleshooting` |
| Codex | `$tubematic-troubleshooting` |
| OpenCode | "Use the tubematic-troubleshooting skill." |

See [Reporting a bug](08-troubleshooting.md#reporting-a-bug).

How agents are deployed and driven is in [The Agent Layer](../developer/07-agent-layer.md).
