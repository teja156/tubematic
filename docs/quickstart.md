# Quickstart

The short path from nothing to a first video. Each step links to the page with the full story;
[Installing](user-guide/02-installing.md) is the complete guide.

---

## What you need

- **A Linux machine.** Cron, `flock` and bind-mounted volumes under `~` are assumed; nothing else is
  supported.
- **Docker with Compose v2**, with the daemon running.
- **Python 3.11 or newer.**
- **An agent CLI, logged in:** Claude Code (`claude`), Codex (`codex`) or OpenCode v2 (`opencode`,
  the `@opencode/cli` package). It does the writing, so it needs a real model behind it.
- **Node.js 22.20 or newer** — only if you install from source. A release builds nothing locally.
- **About 10 GB of disk** for images and rendered video.
- **API keys:** ElevenLabs and OpenAI are required. Gemini (for topic mining and AI review),
  youtube-transcript.io (for script profiles only; topic mining does not use it) and postforme.dev (for publishing)
  are optional. OpenAI needs **billing enabled** on the key's project for image generation.

The full table, including which permissions the ElevenLabs key needs, is in
[Installing — Prerequisites](user-guide/02-installing.md#prerequisites).

## What it costs

Tubematic is free; the services it calls are not. Every video spends on:

- **ElevenLabs** — voicing, drawn from your plan's credits by script length. This is why a human
  approves every script before it is voiced.
- **OpenAI** — every scene image, and the Illustrated style's characters.
- **Gemini** — only if you store a Gemini key: topic mining, and AI review if you turn it on (it is
  off by default).
- **Your agent's model** — every script, scene and revision is an agent session billed by its own
  provider.

The dashboard records what each call cost: a per-video breakdown in the video's detail view, spend
that belongs to no video on Analytics → Spend, and the prices behind both on Settings → Costs. Every
figure is an API list price, and ElevenLabs is shown in credits. See
[Settings — Costs](user-guide/05-settings.md#costs).

## Where your data lives

Everything the pipeline produces — the database (which also holds your API keys), job files,
generated scenes and rendered videos — lives in `~/.tubematic-data/`, outside the install directory.
Deleting the install directory does not remove it.

## A note on the network

The API and the MCP server listen on `127.0.0.1` only. The dashboard on port 3000 is
password-protected but speaks plain HTTP, and a **source** install publishes it on every interface.
Treat it as trusted-LAN only, or put HTTPS in front of it before using it from another machine. See
[Installing — Network exposure](user-guide/02-installing.md#network-exposure).

---

## 1. Install

**From a release — recommended.** Download the newest release from the project's GitHub Releases
page, check it, and run the wizard from inside it. It pulls ready-built images; nothing is compiled
and there is nothing to log in to.

```bash
curl -LO https://github.com/<owner>/<repo>/releases/download/v<version>/tubematic-v<version>.tar.gz
curl -LO https://github.com/<owner>/<repo>/releases/download/v<version>/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-v<version>.tar.gz
cd tubematic-v<version>
python3 onboard.py
```

**From source — the alternative**, if you want to change Tubematic itself or run something not yet
released. It builds the images locally and needs Node.js 22.20 or newer:

```bash
git clone <repo-url> tubematic
cd tubematic
python3 onboard.py
```

The wizard creates its own virtualenv, asks for your API keys (checking each one with its provider
as you type it), a dashboard password, at least one ElevenLabs voice, and the image model, then
starts the containers. Every other setting takes a default you can change on the dashboard later.
See [Installing — Install](user-guide/02-installing.md#install).

## 2. Install an agent

Nothing runs until an agent is installed. Log the CLI in first, then:

```bash
python3 onboard.py --install-agent claude    # or: codex, opencode
```

It checks the CLI is logged in, asks which models to use (the first is the default), and deploys
Tubematic's skills and its MCP server registration. Restart any agent session you already had open.
See [Installing — Install an agent](user-guide/02-installing.md#install-an-agent).

## 3. Make a first video

Open `http://localhost:3000`, sign in, and go to **New Video**. Enter a title and a topic, and
submit. With **Automatically approve topic** left on, the video goes straight to scripting.

The dashboard is where you run Tubematic from: creating videos, approving them, pausing, choosing
what research looks for. You never have to open an agent session yourself — the scheduled pipeline
starts the agent for you. If you prefer an agent terminal, slash commands are an optional
alternative; see [Using Tubematic — Agent commands](user-guide/03-using-tubematic.md#agent-commands).

## 4. What happens next

The **Pipeline** page shows where every video is. A video stops at the points where you have to say
yes, and moves on its own in between:

1. **The script is written** by the next agent session. Cron starts the poller every 30 minutes by
   default when it is idle; once there is work it keeps running, and starts each next stage as soon
   as the last one finishes.
2. **You approve the script** (`SCRIPT_READY`). Nothing has been spent on voice yet.
3. **The agent voices it, generates images and writes the scenes.** This is the longest agent stage;
   how long depends on the model and the length of the video.
4. **The render worker renders it and the AI reviewer watches it.** The worker checks for queued
   renders every 20 seconds. A render takes minutes, and is cut off at 40 minutes by default. A review
   that finds defects sends the video back to the agent for one revision round by default.
5. **You watch it and approve it** (`VIDEO_READY`). Publishing, if you enabled it, is a separate step
   after that.

How to steer all of this — research modes, caps, pausing — is in
[Using Tubematic](user-guide/03-using-tubematic.md).

## When something goes wrong

- Check an install: [Installing — Verifying an install](user-guide/02-installing.md#verifying-an-install).
- Nothing moving, or an error you do not recognise: [Troubleshooting](user-guide/08-troubleshooting.md).
  The most common answer is a video waiting for you at a checkpoint.
- Remove it all: [Installing — Uninstalling](user-guide/02-installing.md#uninstalling).
