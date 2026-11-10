# Release Notes

What each version of Tubematic adds, changes and fixes, and what you have to do when you upgrade to
it. The newest version is first. The first section can describe a version that is still in
development and has no download yet.
[Releases](https://github.com/teja156/tubematic/releases) lists the published versions.

To move an install to a newer version, follow [Upgrading](user-guide/07-upgrading.md).

---

## v2.2.0

2.2.0 adds two visual styles: System Flow, which turns a video into a diagram that builds itself
while the narrator explains a system, and Bean Explainer, a cartoon character that reacts to the
narration among everyday props.

### Upgrade notes

[Upgrading](https://docs.tubematic.ai/user-guide/upgrading) has the procedure. The points below
apply to this version.

After you upgrade:

1. Close and reopen any agent session you had open (Claude Code, Codex or OpenCode). The upgrade
   installs new skills for System Flow and Bean Explainer, and a session started before it does not
   have them.

If you go back to 2.1.x later:

- A video set to System Flow or Bean Explainer cannot render on 2.1.x. Finish it, or switch it to
  another style while it waits at its topic, before you go back.
- A domain whose default style is System Flow or Bean Explainer starts its new videos on Auto under
  2.1.x.

### Added

- The System Flow visual style. Each subject of the video is a diagram: components appear as line
  icons in boxes, dotted connectors draw between them, and points of light travel the connectors as
  the narration describes each step, with values such as an address or a status code shown beside
  them. It suits networking, protocols, system design, data pipelines and security flows. It needs no
  image generation and no GPU. Choose it for a topic, on the **New Video** page, or as a domain's
  default; Auto does not choose it. See
  [Visual Styles and Mascots](https://docs.tubematic.ai/user-guide/visual-styles-and-mascots#the-styles).
- The Bean Explainer visual style (experimental). A bald, big-headed cartoon character with a thick
  outline stands on one bright colour field and reacts to the narration pose by pose, while props
  from a fixed library of everyday objects (a phone, a browser bar, coins, a clock, a pill, a lock and
  about 35 more), short handwritten labels, reaction marks and red crosses build up beside it. In a
  list video each item gets a header and a coloured badge, and a strip of badges slides between
  items. It suits habits, health, money, behaviour and "every X explained" lists, and needs no image
  generation and no GPU. Choose it for a topic, on the **New Video** page, or as a domain's default;
  Auto does not choose it. See
  [Visual Styles and Mascots](https://docs.tubematic.ai/user-guide/visual-styles-and-mascots#the-styles).
- Captions can show the key word of a line in white on a red box. Bean Explainer videos use it.

---

## v2.1.1

2.1.1 fixes a fault that could use up a machine's memory and freeze it while agents prepared
videos.

### Upgrade notes

After you upgrade:

1. Upgrade each remote renderer, as after every upgrade of main. Until you do, it shows
   **needs upgrade** and gets no work. On each renderer machine, run:

   ```bash
   python3 tubematic_remote_renderer.py upgrade
   ```

   [Remote Renderers](https://docs.tubematic.ai/user-guide/remote-renderers#upgrading) has the
   details.

### Fixed

- The machine running Tubematic could run out of memory and stop responding, so that only a hard
  reboot brought it back. It happened while agents prepared several videos at once, and more often
  the more videos the install had made. Checking a video's scenes before a render now takes a few
  seconds and a few hundred megabytes, the check runs for one video at a time, and a check that runs
  out of time now stops everything it started.
- A render that timed out inside the browser, which happens on a machine short of memory, sent the
  video back to the agent to change scenes that were fine. The first such timeout now re-queues the
  render as it is, without counting it against **Max render retries**. A second one is handled like
  any other failed render.
- The built-in renderer held several hundred megabytes of memory while idle, on installs that never
  make a Cartoon 3D video. It now starts its preview-stills helper only when Cartoon 3D asks for a
  still, and lets the memory go after ten minutes without one.

---

## v2.1.0

2.1.0 adds rendering on an NVIDIA GPU, renderers on other machines, the Cartoon 3D visual style and
mascots. It also tells you when a post reached only some of your accounts. GPU rendering, remote
renderers, Cartoon 3D, mascots and the new alerts are off until you turn them on.

### Upgrade notes

[Upgrading](https://docs.tubematic.ai/user-guide/upgrading) has the procedure. The points below
apply to this version.

Before you upgrade:

1. Plan to run the upgrade without `--no-stop`. `python3 upgrade.py --no-stop` is refused for this
   upgrade, because the 2.0.x renderer would keep publishing beside the new worker container.
   Later upgrades accept the flag again.

   ```bash
   python3 upgrade.py
   ```

After you upgrade:

1. Restart every agent session you have open (Claude Code, Codex or OpenCode). The upgrade installs
   two new skills and registers the tool server again, with new tools. A session that was open
   keeps the old ones until you restart it.
2. If your renders take longer than 40 minutes, raise **Render timeout** on
   **Settings → Rendering** (`render_timeout_secs`). A new install starts at 180 minutes. An
   upgraded install keeps the value it has stored, which is 40 minutes unless you changed it.
3. To render on a GPU, install the NVIDIA driver and the NVIDIA Container Toolkit, then pick the
   GPU. See [GPU Rendering](https://docs.tubematic.ai/user-guide/gpu-rendering).

   ```bash
   python3 onboard.py --step gpu
   ```
4. To let other machines render, turn remote renderers on, then add each machine. See
   [Remote Renderers](https://docs.tubematic.ai/user-guide/remote-renderers).

   ```bash
   python3 onboard.py --step renderers
   ```
5. To receive the two new Discord alerts, switch on **A publish partly fails** and
   **A video fails** on **Settings → Notifications**. Both are off after the upgrade.

What the upgrade changes on your machine:

- It adds a fifth container, `tubematic-worker`, which starts with the others. Publishing, Auto
  Pilot, notifications and AI review log there: `python3 scripts/service.py logs tubematic-worker`.
  Rendering stays in the log of `tubematic-renderer`.
- It creates three files in `~/.tubematic-data/secrets/`: `builtin_renderer_token`,
  `render_tls_key` and `render_tls_cert`. Do not delete the key and the certificate. Every remote
  renderer trusts that certificate, and a new one cuts them all off.
  `python3 onboard.py --rotate-tokens` now replaces four tokens and leaves those two files alone.
- Once it has succeeded, it removes the 2.0.x Docker images and any older Tubematic images, and
  reports the space freed. If another container on the machine runs from an old Tubematic image,
  Docker keeps that image and the upgrade warns.
- A video that reached only some of its accounts before the upgrade stays Published. To find one,
  open a Published video's **Publishing Results** tab and look for a failed account.
- If you upgrade with `--force` while a video is rendering, the video goes back in the queue. That
  counts as one of its render retries.

To go back to 2.0.x, follow the
[rollback policy](https://docs.tubematic.ai/user-guide/upgrading#rollback-policy). Three steps are
specific to this version:

1. On each remote renderer machine, run `python3 tubematic_remote_renderer.py remove`. 2.0.x has no
   port for a remote renderer to connect to.
2. After you stop Tubematic, run `docker rm -f tubematic-worker`. 2.0.x does not know that
   container and would leave it running.
3. Restore the database backup that the upgrade took. 2.0.x refuses a newer database. Mascots you
   made since the upgrade are lost with the restore.

The new files in `~/.tubematic-data/secrets/` and a GPU choice can stay. 2.0.x ignores both and
renders on the CPU. When 2.0.x starts, a release install downloads its images again and a source
install rebuilds them.

### Added

#### GPU rendering

- Videos can render on an NVIDIA GPU. With the NVIDIA driver and the NVIDIA Container Toolkit
  installed, the new `gpu` onboarding step lists the machine's NVIDIA GPUs and gives the one you
  pick to the renderer. On a GeForce GTX 1650, an ordinary scene rendered about three times faster
  than on the CPU and a 3D scene about six times faster, with the same picture. Rendering on the
  CPU stays the default. Intel and AMD GPUs are not supported. See
  [GPU Rendering](https://docs.tubematic.ai/user-guide/gpu-rendering).
- The renderer tests the GPU before it uses it. When it starts, and when you press **Test GPU** on
  **Settings → Rendering**, it renders a test frame and reads which graphics device Chromium got. A
  video renders on the GPU only when that device is the GPU you chose. **Settings → Rendering**
  shows the GPU, whether the test passed, and the reason when it did not.
- A GPU that stops working slows ordinary videos down and does not fail them: they render on the
  CPU. Cartoon 3D and mascot videos render on a GPU only. Such a video fails, with a comment that
  says why, when no renderer has a working GPU, when the renderer with the working GPU stays
  unavailable for 30 minutes, or when the GPU stops working during the render. Create the video
  again once the GPU works.
- With a GPU chosen, start the containers with `python3 scripts/service.py start`. A bare
  `docker compose up` does not read the GPU choice and recreates the renderer without the GPU.
  Rendering then continues on the CPU, and `python3 scripts/service.py status` warns about it.
- `python3 upgrade.py` refuses to start while the chosen GPU or the NVIDIA Container Toolkit is
  missing. Run `python3 onboard.py --step gpu` to pick again or to go back to the CPU. Your choice
  is stored in `~/.tubematic-data/compose.gpu.json`, so upgrades keep it.

#### Cartoon 3D (experimental)

- Cartoon 3D is a new visual style: inked cartoon characters in a painted 3D world, with a camera
  that moves through it and a soundtrack of music and sound effects under the voice. The agent
  builds the set for the story and checks each shot against the narration before the video renders.
  Choose it when you approve a topic, or leave the style on **Auto** and let the agent choose it
  for a story that a place carries. See
  [Visual Styles and Mascots](https://docs.tubematic.ai/user-guide/visual-styles-and-mascots).
- Cartoon 3D needs a renderer with a working GPU. Until a GPU test passes, the style is greyed out
  on the dashboard and the API refuses it.
- Credits: the Cartoon 3D kit descends from
  [mromidev/claude-animated-shorts](https://github.com/mromidev/claude-animated-shorts) (MIT
  License, Copyright (c) 2026 Mr omi). The runner, cast, lights, world, toon shader, camera
  grammar and soundtrack engine are adapted from it, and each ported file names its origin in its
  header. That project's reference frames and sheets are not included.

#### Mascots (experimental)

- A mascot is a small watercolour-style character that walks on and off the screen and reacts to
  the narration: it looks surprised, has an idea, hops, glances at something. It does not narrate
  and does not lip-sync. Mascots are off by default, work with every visual style except Cartoon
  3D, and need a renderer with a working GPU. Until a GPU test passes, the mascot pickers are
  greyed out and the API refuses a new choice.
- Tubi, the Tubematic mascot, is built in: a small retro terminal whose screen is its face. You can
  pick Tubi without setting anything up. You cannot edit Tubi, and you can ask for a variation of
  it.
- A new **Mascots** page under **Profiles** makes your own. Describe a character or press
  **Surprise me**, and an agent draws it and renders three sheets for you to review: a turnaround,
  its ten emotions and a strip of poses. Approve it, or request changes with a comment. You can
  choose the agent, model and effort that draw it. While a changed version is drawn, videos keep
  the last approved version, and a video whose scenes are written stays on the version it was
  written for.
- Three places set a video's mascot: **Default mascot (experimental)** on **Settings → Rendering**,
  a default on each domain's row on the **Topics** page, and a picker on a topic that waits for
  approval. Each overrides the one before it. A domain can opt out with *None*. The choice is fixed
  once you approve the topic.
- Credits: the mascot engine descends from
  [JohnHeibel/ClaudeAnimationBase](https://github.com/JohnHeibel/ClaudeAnimationBase) (MIT License)
  and ships [p5.js](https://p5js.org/) (LGPL-2.1) and
  [p5.brush](https://github.com/acamposuribe/p5.brush) (MIT License), with their licenses beside
  them in the source. None of ClaudeAnimationBase's characters are included.

#### Remote renderers

- Other machines can render your videos. Turn remote renderers on once on the main install (the
  machine with the dashboard and the database) with `python3 onboard.py --step renderers`. Then add
  any number of other Linux machines that run Docker. Each renders one video at a time, beside the
  built-in renderer, and Tubematic gives each video to the renderer that would finish it first. See
  [Remote Renderers](https://docs.tubematic.ai/user-guide/remote-renderers).
- A Cartoon 3D or mascot video goes only to a renderer whose GPU test passed, so a GPU in another
  machine is enough for those two features.
- A remote renderer holds no database, no video library and none of your API keys. It downloads one
  video's files, renders it, uploads the result and deletes its copy. It connects over HTTPS and
  trusts only the certificate of your main install.
- `tubematic_remote_renderer.py` sets up a renderer on another machine and later upgrades or
  removes it. Every release has it as a download of its own, listed in `CHECKSUMS.txt`, and the
  release tarball has it in `scripts/`.
- **Settings → Rendering** has a **Renderers** panel. It lists every renderer, the built-in one
  first, with its status (online, busy, offline, disabled, needs upgrade or credential expired),
  its CPUs, memory and GPUs, its GPU test result and its last error. You can disable, rename and
  remove renderers and test each one's GPU.
- **Add renderer** on that panel gives you a one-time token, valid for one hour, and the command to
  run on the new machine. The script asks for the token, so the token stays out of that machine's
  process list and shell history. `--token-stdin` reads it from a pipe for a scripted install.
- The **Pipeline** page shows a **NOTHING CAN RENDER** banner, with a link to
  **Settings → Rendering**, when videos wait to render and no renderer can take them.
- Remote renderers connect to port 4443 on the main install by default. The port opens only when
  you run the `renderers` step, and it then listens on every network interface. Docker's published
  ports are not restricted by `ufw`, so allow the port through your network firewall
  [from your renderer machines only](https://docs.tubematic.ai/user-guide/remote-renderers#allow-the-port-through-your-firewall-from-your-renderers-only).
- After each upgrade of the main install, run `python3 tubematic_remote_renderer.py upgrade` on
  each renderer machine. Until you do, that renderer shows **needs upgrade** and takes no work.
- A remote renderer's credential lasts 30 days and renews itself while the renderer is online. A
  renderer that stays offline until the credential runs out shows **credential expired**. Remove it
  and add it again with a new token.

#### Publishing

- **Mark as published…** finishes a video that went out on only some of its accounts, which now
  stops at Partially Published (see Changed). The dialog says how many accounts the video reached and has a
  **Download video** link, so that you can post the video to the failed accounts yourself before
  you confirm. See
  [When a publish partly fails](https://docs.tubematic.ai/user-guide/publishing#when-a-publish-partly-fails).
- **Settings → Notifications** has two new Discord alerts. **A publish partly fails** names each
  account that failed with its error and links the posts that went out. **A video fails** says why
  a video became Failed, and offers **Retry publishing** when the failure happened while
  publishing.

#### Disk space

- The dashboard's top bar shows how much disk space Tubematic uses. Click the figure for a
  breakdown: finished videos, job files, backups, logs and the rest of your data, then the Docker
  images in use, old images, the containers' scratch space and the install folder. Your machine
  measures the Docker and install figures about once an hour and right after an upgrade, and the
  popup says how long ago. See
  [The disk figure](https://docs.tubematic.ai/user-guide/dashboard#the-disk-figure).
- `upgrade.py` removes the previous version's Docker images once the upgrade has succeeded. An
  upgrade that needs attention keeps them, and the next successful upgrade removes them.

### Changed

- A publish that fails on some accounts stops at the new status Partially Published. In 2.0.0 such
  a video showed as Published when one account succeeded, and nothing said that other accounts
  still needed the video. A Partially Published video sits in the Published column of the Pipeline
  board with a **PARTIAL** tag, has its own state in the Library, and waits for you. Tubematic
  keeps its video file until you mark it published, and an Auto Pilot video keeps its place in the
  in-progress limit until then.
- Publishing, Auto Pilot, notifications and AI review continue while a video renders. In 2.0.0
  they shared one loop with rendering, so during a render a scheduled post went out late, Auto
  Pilot approved nothing and Discord messages were held back. They now run in a container of their
  own, `tubematic-worker`, and `tubematic-renderer` only renders. An AI review also does not hold
  up the next render.
- A renderer that stops responding has its render put back in the queue after five minutes. A
  render interrupted by a restart of the renderer goes back in the queue at once, as in 2.0.0.
- A new install's **Render timeout** is 180 minutes. In 2.0.0 it was 40. An upgraded install keeps
  its stored value (see Upgrade notes).
- The documentation is reorganised. The quickstart and the user guide are shorter and use the
  dashboard's labels. Agents, visual styles and mascots, Auto Pilot and the command-line reference
  each have a page of their own. Uninstalling one agent is under Agents, the wizard's steps and
  flags are in the Command Reference, and Auto Pilot has left the Publishing page.

### Fixed

- A render that stops making progress is stopped after 10 minutes and tried again. In 2.0.0 a hung
  render ran until the render timeout, 40 minutes by default. The wait is the new
  **Render stall timeout** on **Settings → Rendering** (`render_stall_timeout_secs`, 600 seconds
  by default), and a change to it needs no restart. A long render that is still advancing is left
  alone.
- The renderer's container grew with every video it rendered, because it kept each video's audio,
  images and scene files until the container was recreated. It now deletes them when the render
  ends.

---

## v2.0.0

Tubematic 2.0.0 is the first public release.

Tubematic is a self-hosted pipeline that turns a topic into a finished YouTube Short. It researches
topics, writes a script, voices it, generates images, animates the scenes in code, renders an mp4
and can post it. It stops for your approval three times: at the topic, at the script and at the
finished video.

An AI coding agent does the writing: Claude Code, Codex or OpenCode. Every scene is a React
component that the agent writes for that one video, rendered with
[Remotion](https://remotion.dev). A video is 1080×1920 at 30 frames a second, with a synthesised
voiceover, word-timed captions, generated images and animated diagrams.

The source, the releases and the container images are public at
[github.com/teja156/tubematic](https://github.com/teja156/tubematic), under the Apache License 2.0.
The documentation is at [docs.tubematic.ai](https://docs.tubematic.ai/).

### What it does

#### Topics

- Topics arrive in four ways. Three are research modes that the agent runs on a schedule:
  curriculum (topics from the domains you describe), trending (GitHub Trending, Hacker News,
  Lobsters and Dev.to) and mining (subjects from YouTube videos you list, which needs a Gemini
  key). The fourth is your own: the **New Video** page, or `/tubematic-submit-new-job` in an agent
  session. See
  [Where topics come from](https://docs.tubematic.ai/user-guide/using-tubematic#where-topics-come-from).
- You limit how many topics arrive: a cap on waiting proposals, a cap on research runs a day, a
  pause on each domain, and a topic cap on each domain (25 to 750, 100 by default). A domain that
  reaches its cap shows **EXPIRED** and gets no more researched topics until you raise the cap.
- Research checks a domain's whole history, deleted and rejected topics included, before it
  proposes a topic.

#### Scripts and voice

- The agent writes each script, and you read it before it is voiced. Voicing spends ElevenLabs
  credits, so the script is the approval that guards the spend.
- A script profile teaches the agent the style of YouTube videos you choose. Pick a profile on a
  topic, or make it a domain's default. Building one needs a youtube-transcript.io key. See
  [Script profiles](https://docs.tubematic.ai/user-guide/using-tubematic#script-profiles).
- The voice list holds up to 10 ElevenLabs voices, each with its own model, and you can play a
  sample of each. A new install comes with two voices: Teja on Eleven v4, the default, and Adam on
  Eleven v3. A domain can have its own default voice. See
  [Settings](https://docs.tubematic.ai/user-guide/settings#voice).
- The agent writes pronunciation and pause markup for the model of the video's voice. Eleven v3
  and Eleven v4 take IPA pronunciations and `[pause]` tags.

#### Scenes and rendering

- Four visual styles: **Auto**, **Motion Graphics**, **Stick Explainer** and **Illustrated**. You
  choose one when you approve a topic, and a domain can set the style its curriculum topics arrive
  with.
- OpenAI draws every scene image, with `gpt-image-2.5-flare` by default or
  `gpt-image-2.5-sunburst`. Scene images come in three shapes: 9:16, 1:1 and 16:9.
- Rendering runs in a container of its own. Every video has captions timed to the words, and a
  small Tubematic mark that you can turn off.
- AI review (experimental, off by default) has Gemini watch the rendered video and sends it back
  to the agent with what it found. It needs a Gemini key.

#### The dashboard

- The dashboard is where you run Tubematic: the Pipeline board with the decisions that wait for
  you, New Video, Library, Archive, Topics, Projects, Script Profiles, Socials, Analytics, Logs and
  Settings. See [The Dashboard](https://docs.tubematic.ai/user-guide/dashboard).
- At each approval you approve or request a revision with a comment, and the agent reworks the
  script or the video. You can also reject a topic.
- The dashboard records what each video cost, by service. Dollar figures are API list prices, and
  ElevenLabs is recorded in credits.
- Settings apply without a restart. They include a preferences text that the agent receives on
  every run, and Discord messages when topics are proposed, a script is ready or a video is ready.
- Retention deletes a published video's files after 7 days by default, and can delete failed and
  rejected videos' files too.
- A banner tells you when a newer stable release is out, with links to its release notes and the
  upgrade guide.

#### Publishing

- You can post an approved video to YouTube, Instagram, TikTok and Facebook through
  [postforme.dev](https://postforme.dev), now or at a time you choose. Publishing is off by
  default. See [Publishing](https://docs.tubematic.ai/user-guide/publishing).
- **Connect** buttons on the **Socials** page open each platform's consent page. Accounts
  connected this way grant the analytics permission, and the **Analytics** page then shows each
  post's views, likes, comments and shares.
- Auto Pilot runs the domains you select with nobody approving: it approves each topic, script and
  video, then posts the video to the accounts you chose. It is off by default. See
  [Auto Pilot](https://docs.tubematic.ai/user-guide/auto-pilot).

#### Agents

- Tubematic drives Claude Code, Codex and OpenCode v2. You can install several side by side, give
  each a share of new videos, and choose the agent, model and effort for one video at an approval.
  See [Agents](https://docs.tubematic.ai/user-guide/agents).
- A scheduled job starts the agent when there is work, every 30 minutes by default. You do not
  have to open an agent session.
- The agent install denies Claude Code and OpenCode access to Tubematic's data directory with
  their own file tools. The agent works through Tubematic's tool server.
- The `tubematic-troubleshooting` skill walks through a problem with you and drafts a bug report.
  It runs only when you ask for it by name, and it posts nothing.

#### Security

- The dashboard asks for a password, and a sign-in lasts seven days. There is one password for the
  install. Set or change it with `python3 onboard.py --set-password`. After five wrong passwords
  in a row, the login makes you wait.
- The API (port 4000) and the tool server (port 4100) require a token on every request apart from
  their `/health` probes. Onboarding creates the tokens in `~/.tubematic-data/secrets/`, and every
  part of Tubematic sends the right one. `python3 onboard.py --rotate-tokens` replaces them.
- Your API keys are stored in the database on your machine, and the logs remove them.
- [Remote Access](https://docs.tubematic.ai/user-guide/remote-access) shows three ways to use the
  dashboard from another machine: Twingate, and HTTPS with Caddy or nginx.

#### Installing and maintaining

- Install from a release, which pulls ready-built public images with no registry login, or build
  from source. If you run Kasm Workspaces, you can
  [install Tubematic as a workspace](https://docs.tubematic.ai/user-guide/installing#installing-in-kasm-workspaces).
- `python3 upgrade.py` moves an install to a newer version. The new version backs up the database
  before it changes it. See [Upgrading](https://docs.tubematic.ai/user-guide/upgrading).
- `python3 scripts/collect_diagnostics.py` writes a redacted report for a bug report. It removes
  your stored keys and tokens, anything shaped like a credential, emails, IP addresses and your
  host and user names. It leaves out your topics, scripts and comments unless you pass
  `--include-content`. See
  [Reporting a bug](https://docs.tubematic.ai/user-guide/troubleshooting#reporting-a-bug).

### What you need

- A Linux machine with 2 CPU cores, 4 GB of memory and about 15 GB of free disk.
- Docker Engine 29 or newer with the Compose plugin, usable without `sudo`.
- Python 3.11 or newer with its `venv` module.
- Node.js 22.20 or newer, which the agent install uses to add a skill for writing scenes.
- One agent CLI, installed and logged in: Claude Code, Codex or OpenCode v2.
- An ElevenLabs API key and an OpenAI API key. The OpenAI key's project needs billing enabled and
  access to the image model you pick.
- Optional keys: Gemini for mining and AI review, youtube-transcript.io for script profiles, and
  postforme.dev for publishing.

Tubematic is free. Each video spends ElevenLabs credits, OpenAI image calls and your agent's model
usage.

### Install

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/v2.0.0/tubematic-v2.0.0.tar.gz
curl -LO https://github.com/teja156/tubematic/releases/download/v2.0.0/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-v2.0.0.tar.gz
cd tubematic-v2.0.0
python3 onboard.py
python3 onboard.py --install-agent claude    # or: codex, opencode
```

The [Quickstart](https://docs.tubematic.ai/quickstart) takes you from here to a first video.
[Installing](https://docs.tubematic.ai/user-guide/installing) covers each step.

### Known limitations

- Linux is the only supported host.
- Codex has no way to deny a path, so a Codex agent can read `~/.tubematic-data`, which holds the
  database with your API keys and the service tokens.
- If the AI review itself fails, the video reaches your approval as if it had passed.
- The dashboard asks GitHub's public releases API for new releases at most once every two hours
  while a page is open. It sends nothing about your install, and no setting turns the check off.
- The dashboard serves plain HTTP. If you open it from another machine without HTTPS or a private
  network in front, the password crosses the network readable.
- You cannot reset the password in the browser. Set it on the host with
  `python3 onboard.py --set-password`.
- A Tubematic session in Kasm Workspaces runs on UTC, so the times it shows are in UTC.
- A `[pause]` straight after the end of a sentence adds very little silence on Eleven v4. Scripts
  use `[long pause]` for a pause that has to be heard.

### Licences

Tubematic is under the Apache License 2.0. Rendering uses Remotion, which has its own licence: a
for-profit company with more than three employees needs a
[Remotion company licence](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md) to run
Tubematic.
