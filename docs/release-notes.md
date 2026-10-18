# 20 · Release Notes

What changed in each published release, newest first.

This page is the **single source** for release notes. It is not a copy of anything: the release
workflow extracts the section matching the version being published and uses it as the body of the
GitHub Release, so the notes are written once, reviewed in the same commit as the change they
describe, and published without anyone pasting them anywhere. A release whose section is missing or
still empty fails its pre-flight checks before a tag can be pushed.

It is also shipped inside the release tarball, so someone reading a downloaded copy can see what
they installed without going back to the web.

## How to write an entry

One `## vX.Y.Z` heading per published version, newest at the top, each with the four sections below.
Drop a section if it has nothing in it — an empty heading is noise, not structure.

- **Added** — capabilities that did not exist before.
- **Changed** — behaviour that already existed and now works differently. Say what the old behaviour
  was, or the reader cannot tell whether it affects them.
- **Fixed** — defects. Describe the symptom the user would have seen, not the internal cause: "the
  first click on SAVE in Settings did nothing" rather than "hoisted SaveBar to module scope".
- **Upgrade notes** — anything a person must *do*, or must know before deciding to upgrade. Manual
  steps, irreversible migrations, changed defaults that alter a running install, dropped
  configuration. **This is the section that matters most and the one most often left empty when it
  should not be.** If an upgrade is not safely reversible, say so here.

Write for someone who does not follow this repository. No ticket IDs, no commit SHAs, no file paths
unless the reader genuinely needs to touch that file. "Every install must re-enter its API keys"
is useful; "`apply_pipeline_settings` now writes an explicit subset" is not.

Versioning policy and the upgrade procedure itself live in [Upgrading](user-guide/07-upgrading.md),
and what a release consists of in [Releases](developer/18-releases.md). This page is only the log.

---

## v2.0.0

**A major release because it is not backward compatible**: the dashboard now needs a password, and
the API and the MCP server refuse any request without their token. Every part of Tubematic sends the
right credential by itself after the upgrade, but a script or tool of your own that talks to port
4000 or 4100 will be refused until it does too. It also makes an **OpenAI API key required** and a
Gemini key optional. Read **Upgrade notes** before upgrading — the upgrade will not start until a
dashboard password is set and an OpenAI key is stored.

### Added

- **The dashboard asks for a password.** Every page now needs a sign-in, and a sign-in lasts seven
  days. Before, anyone who could reach port 3000 — anyone on your network, on a development
  checkout — could change settings, approve paid work and publish. **Sign out** is at the right of
  the top bar. There is one password for the install, set on the host; there is no sign-up and no
  reset in the browser.
- **The API (port 4000) and the MCP server (port 4100) require a token on every request**, apart
  from their `/health` probes. Before, any program on the machine — or a web page in your browser,
  through DNS rebinding — could call them, and the MCP server can spend money on paid APIs and run
  code. Onboarding creates the tokens in `~/.tubematic-data/secrets/`, and every part of Tubematic
  that calls either server sends the right one automatically: the dashboard, the poller, and each
  installed agent, which reads the token from its file rather than keeping a copy.
- **Connect social accounts from the Socials page.** A **Connect** button for YouTube, Instagram,
  TikTok and Facebook opens the platform's consent page in a new tab. Finish there — it ends on
  postforme.dev — then come back and press **Refresh accounts list**. Accounts connected this way
  always grant the analytics permission (`feeds`). Before, accounts had to be connected on
  postforme.dev itself, where that permission is off by default, and such an account published
  normally while every view, like and comment stayed empty with no error saying why. A platform not
  enabled on your postforme project shows postforme's message saying where to enable it.
- `python onboard.py --set-password` sets or changes the dashboard password. Changing it signs every
  browser out.
- `python onboard.py --rotate-tokens` replaces all three tokens and restarts the services that use
  them. It waits for running work first, like an upgrade.
- After five wrong passwords in a row, the login makes you wait — 2 seconds, then 4, doubling up to
  15 minutes. Restarting the API clears the wait.
- `python upgrade.py --check` also reports the password, the tokens, whether the MCP server really
  refuses a request without its token, and whether each agent is registered to send it.
- **Every domain has a topic cap**: how many topics it may ever hold, from 25 to 750 and 100 by
  default, set in a new **Topic cap** field on each row of the Topics page. Beside it, "N filed"
  counts every topic the domain has had, deleted and rejected ones included. A domain that reaches
  its cap shows **EXPIRED**, and scheduled research files nothing more into it until you raise the
  cap. Topics you submit yourself — the New Video page or `/tubematic-submit-new-job` — still go
  through.
- **A redacted diagnostics report for bug reports.** `python3 scripts/collect_diagnostics.py`
  gathers the version, container state, agent and settings summary and the recent warnings from
  every log into one `report.md` in a new folder in your home directory. It first removes your
  stored API keys and tokens, anything shaped like a credential or cookie, emails, IP addresses,
  your host and user names, account and voice ids, and — unless you pass `--include-content` — your
  topics, scripts, comments and preferences. If a stored secret would still get through, it writes nothing. Read the
  report before posting it; the end of it lists what code cannot catch.
- **A troubleshooting skill**, `tubematic-troubleshooting`, walks through a problem with you, follows
  the troubleshooting guide, runs the diagnostics report and drafts a bug report in the issue form's
  layout. It never posts anything — filing is yours — and it only runs when you ask for it by name:
  `/tubematic-troubleshooting` in Claude Code, `$tubematic-troubleshooting` in Codex, or "use the
  tubematic-troubleshooting skill" in OpenCode. Scheduled runs never start it.

### Changed

- Onboarding has a new step, **Dashboard password and service tokens**, before the API keys. It asks
  for the password once; a re-run never changes it.
- **An OpenAI API key is now required, and a Gemini key is optional.** Every scene image is now
  drawn by OpenAI (`gpt-image-2.5-flare` by default, or `gpt-image-2.5-sunburst`); Gemini no longer
  draws images, and the image-provider choice is gone from onboarding, Settings → Images and the
  settings API. Onboarding asks for the OpenAI key until you give one, and accepts a blank Gemini key.
  OpenAI grants model access per project, so the key's project must be allowed to use the image
  model you pick — a key without it is refused at the first image, with an error naming the project
  and the model.
- **Scene images come in three shapes: 9:16, 1:1 and 16:9.** The agent was always told to leave the
  default 9:16; a request for any other ratio is now refused rather than drawn.
- **Mining needs a Gemini key, and is off without one.** With no Gemini key stored, the Topics page
  greys out the Mining toggle (hover it for why), scheduled research leaves mining out, and turning
  it on is refused. Add a key on Settings → API Keys and mining comes back as it was — no need to
  tick it again. An install whose only research mode was mining runs no research until then.
- **AI review is off by default on new installs, and labelled experimental** on Settings → AI Review.
  It needs a Gemini key, and if the review itself fails, the video still reaches your review as if
  it had passed — the note beside the switch says so.
- Rendered videos and voice previews are served only to a signed-in browser, and are no longer
  cached by anything shared between the browser and the server.
- **The GIF capability is removed**: the `write_gif_script` tool, the `GifFX` scene component and the
  `tubematic-gif-creator` skill. The tool ran any Python an agent wrote, inside the server that holds
  your API keys, and nothing in the pipeline depended on it. A `.gif` is no longer accepted as a
  scene image. The MCP server now has 38 tools.
- **Mining sources must be YouTube video links** — `watch?v=`, `youtu.be`, `shorts` or `live`. Each
  is stored as `https://www.youtube.com/watch?v=<id>`, so the same video entered two ways is listed
  once, and a list holds at most 50 videos. Saving a list that contains anything else is refused,
  and the dashboard shows which entries were wrong.
- **A mining run makes at most as many paid Gemini calls as the per-run mining limit allows**, and
  only one run happens at a time. Before, a run kept calling Gemini, one URL after another, until it
  had filed enough topics, however many URLs that took.
- **`POST /research/mine` is removed.** Nothing in Tubematic called it; mining runs through the
  agent's mining tool.
- **A new script profile must have the seven sections the profile builder writes**, stay under
  12,000 characters, and contain no links, HTML, code blocks or tool names. A profile that does not
  is refused, and the agent writes it again. Profiles are built from YouTube transcripts nobody vets,
  and a profile is read by every scripting session in its domain, so it is held to that shape and
  the agent treats it as style data, never as instructions.
- **Agents can no longer read Tubematic's data directory (`~/.tubematic-data`) with their own file
  tools** — on Claude Code and OpenCode. It holds the database with every API key and the service
  tokens; the agent reaches Tubematic only through its tools. Codex has no way to deny a path, so a
  Codex agent can still read it.
- **Comments an agent writes are always signed as the agent.** It can no longer post a comment that
  shows as written by a person.
- **The API refuses the four file-location fields of a video**: `PATCH /videos/<id>` answers `400` if
  the body carries `voice_file_path`, `timeline_path`, `scene_config_path` or `video_path`, and
  applies nothing else in it. Tubematic works out where each video's files are from its id instead.
- **A new video or domain id may hold only letters, digits, `_` and `-`**, up to 128 characters, and
  must not start with `-`. Existing videos and domains with other ids, longer ones included, keep
  working and stay editable. The one exception is a video whose id is so long (more than 251
  bytes) that its finished file's name would exceed what the filesystem allows: it is moved to
  `FAILED` with a comment saying why before rendering starts, instead of failing part-way through. A video
  filed under a domain that does not exist is now a `400`, not a `500`.
- **The dashboard refuses a change sent from another site** — including another app on the same
  host at a different port — and any change whose body is not JSON. The dashboard's framework is
  updated to Next.js 15.5.27.
- **The documentation is reorganised by who is reading it.** A new
  [Quickstart](quickstart.md) is the short path to a first video; the [user guide](README.md#user-guide)
  covers installing, using, the dashboard, settings, publishing, upgrading and troubleshooting; the
  [developer docs](README.md#developer-docs) cover how it all works. `INSTALL.md`, `USAGE.md` and `UNINSTALL.md`
  are now short pointers into the user guide, and the onboarding hints point there too. Links to the
  old `docs/NN-*.md` pages no longer resolve; start from [the docs index](README.md). A release
  download now carries the whole public documentation, not one page.
- **Installing from a release is the recommended route, and needs no login.** The release images
  on GitHub's container registry are public, so `docker login ghcr.io` is no longer a step; the
  install guide and Quickstart lead with the release tarball, with building from source as the
  alternative. A failed image pull now shows Docker's own reason (usually no route to `ghcr.io`)
  instead of telling you to log in.
- **The guides now treat the dashboard as the way to run Tubematic.** Creating videos, approving
  them, pausing and choosing what research looks for are all shown on the dashboard first; agent
  slash commands such as `/tubematic-submit-new-job` are described as an optional alternative, and
  the guide lists each one beside its dashboard equivalent.
- **A new domain's description on the Topics page is now a box you can write paragraphs in.** It
  was a single line, which is the wrong shape for the scope research works from. Drag its corner to
  make it taller. A description now holds at most 2000 characters, and a counter under the box
  shows how many you have used. The domain list still shows it on one line.

### Fixed

- **Some log lines could carry an ElevenLabs API key, a basic-auth password or a session cookie.**
  The services already removed every *stored* key by its value, but the poller's log has no stored
  values to match and relies on recognising a credential's shape — and that missed ElevenLabs' key
  shape, removed only the word "Basic" from a basic-auth header rather than the password after it,
  and did not recognise cookies. All three are removed now. The
  MCP server's logs also remove a stored Discord webhook by its value, as the API's already did. Log
  files written before the upgrade are not rewritten.
- **The dashboard's top bar did not fit on screens narrower than about 1640px.** Its tabs and the
  timezone squeezed onto two or three lines, and on 1280px and 1024px screens every page also
  scrolled sideways. On a narrower screen the page tabs now move to a second row under the logo and
  status, so the whole bar is visible without scrolling.
- **Research proposed topics a domain had already had.** Once a video was deleted, or removed by
  the retention sweep, its topic could be proposed again as if it were new — and under Auto Pilot
  approved and produced again. Research now checks a domain's whole history, deleted and rejected
  topics included, before proposing.
- **A video could be published only from the Pipeline board.** Opened from the Library or the
  Projects page, an approved video's window had no **Publish…** button, and a failed or scheduled
  one had no **Retry publishing** or **Cancel schedule**. They now appear wherever the window opens.
- **Several ways to make Tubematic read, copy, upload or delete files outside its own folders are
  closed.** A crafted id or file location could make it delete a file elsewhere on the machine, copy
  an arbitrary file into a render, publish or play another video's render, or delete another video's
  file when one was archived. A video's files are now always found from its own id, and every id that
  becomes part of a path is checked. This also makes a video whose stored location is a path on the
  host, rather than inside the containers, play in the dashboard again.
- **A symbolic link in the videos folder could let a signed-in browser read files outside it**,
  including the dashboard's own secrets. Videos and voice previews are now served only when the real
  file is inside the videos folder and is an `.mp4` or `.mp3`.
- **After a revision, the dashboard could keep playing the old render for up to an hour.** A
  re-rendered video replaces the file at the same address, and the browser was allowed to reuse
  its copy without asking. It now checks with the dashboard each time and downloads the video
  again only when it has changed.
- **Playing a large video could exhaust the dashboard's memory**, because each request read the
  whole file into memory first. Videos are now streamed. Seeking also behaves correctly in more
  cases, and an impossible range gets `416` instead of a server error.
- **Onboarding accepted a Node.js too old for the Remotion skills installer.** It checked only for
  Node 22, so 22.0 to 22.19 passed and the installer then crashed, leaving the Remotion
  best-practices skill out. It now warns below 22.20.
- **Uninstalling a user-level Claude Code install left four slash commands behind** in
  `~/.claude/commands/`: `/tubematic`, `/tubematic-add-topic`, `/tubematic-pause-domain` and
  `/tubematic-resume-domain`. The uninstaller now removes them with the rest, and also removes a
  skill an older release installed there. If you uninstalled before, delete those leftovers by hand.
- **The uninstaller's step counter read "Step 8/7" and "Step 9/7"**, and numbered each extra agent
  as if it were a later step. It now counts to 9, with every agent under step 6.
- **Documentation corrections.** The install guide now shows how to file a first video with a Codex
  agent (which has no slash commands), states that Linux is the supported host, and explains what
  the dashboard exposes on the network before you install. Several pages that disagreed with the code
  were corrected: the published image tags, database indexes and columns, the data directories and
  each container's mounts, a render log that does not exist, and the versioning policy.
- **The instructions for building a script profile described a way of doing it that no longer
  exists.** They told you to run an onboarding step, edit a list of URLs in a file and run a fetch
  script by hand, none of which are there any more — a profile is created on the dashboard's
  **Script Profiles** page and builds itself from there. The guide now describes that. Several
  places also said the youtube-transcript.io key was used for topic mining; it is not, and mining
  works without it.

### Upgrade notes

- **Set a dashboard password before you upgrade.** `upgrade.py` asks no questions, so it refuses to
  start until one exists. Run this from the **new** version's directory — the one you will run
  `upgrade.py` from; your current version has no such command. It is safe to run while the old
  version is still serving, because the old version ignores the stored password:
  ```bash
  python3 onboard.py --set-password
  ```
  Then run `python3 upgrade.py` from the same directory as usual. The upgrade creates the tokens
  itself.
- **Store an OpenAI API key before you upgrade.** Scene images now come only from OpenAI, so the
  upgrade refuses to start without a key rather than finishing and then failing every image. Add it
  on your current version's dashboard (Settings → API Keys), then run the upgrade.
- **If scene images were set to a Gemini model, they switch to `gpt-image-2.5-flare`** when the
  upgrade migrates the database — including `gemini-3-pro-image-preview`, which Google has shut
  down. Pick the other OpenAI model on Settings → Images if you prefer it.
- **AI review keeps the setting you had.** Only new installs start with it off. To turn it off, use
  the switch on Settings → AI Review.
- **Without a Gemini key, mining stops.** If you used mining, keep a Gemini key stored; if you
  remove it, mining is skipped until you add one back.
- **`upgrade.py --no-stop` is refused for this upgrade**, because old and new containers would
  refuse each other's calls while they were swapped one at a time, and old ones would keep looking
  for the retired image-provider setting. Run it without the flag.
- **Restart any open agent session** after the upgrade (Claude Code, Codex or OpenCode). The upgrade
  re-registers each installed agent so it sends the new token. If it could not re-register one — its
  program was missing, for instance — the upgrade still finishes, but it ends with an error naming
  that agent: run `python3 onboard.py --install-agent <agent>` for it.
- **Your own scripts and `curl` commands against port 4000 or 4100 now need the token**, or they get
  `401`. Send it as a header:
  ```bash
  curl -H "Authorization: Bearer $(cat ~/.tubematic-data/secrets/api_token)" localhost:4000/settings
  ```
  The MCP server's token is `~/.tubematic-data/secrets/mcp_token`. An MCP server you registered
  with an agent by hand, rather than through `onboard.py --install-agent`, must be re-registered
  through the installer.
- **Using the dashboard from another machine:** put HTTPS in front of it — a reverse proxy such as
  Caddy, or a private network such as Tailscale. It works over plain HTTP, but then the password
  crosses the network readable.
- **Moving the install directory** now also needs `python3 onboard.py --install-agent <agent>` for
  each agent, because each agent's registration names the install's helper script.
  `upgrade.py` does this for you when you upgrade into a new directory.
- **Social accounts you already connected keep working unchanged** — still listed on Socials, still
  ticked, still in Auto Pilot. Nothing is migrated. But they do not gain analytics by themselves: if
  the Analytics page shows `—` for an account's posts, connect that account again with the
  **Connect** button on Socials to grant the permission. Reconnecting keeps the same account, so it
  stays ticked and keeps its Auto Pilot settings — there is nothing to set up again.
- **Domains that already hold 100 or more topics get room to grow.** Every domain starts with a cap
  of 100, but one that already holds 100 or more topics gets its current count plus 100, up to 750,
  so research keeps filing into it after the upgrade. A domain already past 650 topics lands at 750,
  the maximum, and may show **EXPIRED** straight away. Check the Topics page after upgrading.
- **The upgrade refuses while a generated scene still imports the removed `GifFX` component**, in
  any spelling the renderer would resolve (comments between the words, escaped characters in the
  path, a path built from joined strings), or when a scene cannot be read or its import path cannot be decoded to tell, because the renderer compiles every generated scene together and that one
  file would make every render fail. An old import kept only as a note in a comment or a string
  does not block it. It lists the files: delete or fix them, then run the upgrade
  again. A scene-config that only
  names `GifFX` is a warning — that overlay is left out if the video is rendered again. The upgrade
  also removes the old `tubematic-gif-creator` skill from every installed agent.
- **Mining sources that are not YouTube video links are dropped** when the upgrade migrates the
  database, and duplicates are merged. Each dropped entry is logged as a warning by the API
  container (`docker compose logs tubematic-api`); the backup the upgrade takes still holds the old
  list. Check **Topics → Mining Sources** afterwards.
- **A script profile built before this release that does not meet those rules is no longer used**
  (most often because it lacks the seven expected sections): videos that pick it are scripted in the
  generic style instead. Build a new profile
  from the same channels to get the style back.
- **Scripts of your own that set a video's file paths over the API or the MCP server now get an
  error**, and so does anything that called `POST /research/mine`. Neither is needed any more.
- **A domain description is now limited to 2000 characters.** One you already have that is longer is
  kept, and the domain's other settings still save. Only changing it to another text over the
  limit is refused, from the dashboard, the API and the MCP server alike — so a script of your own
  that writes a longer description now gets an error.
- **Rolling back to 1.2.x means restoring the database backup** the upgrade took, because this
  release changes the database: 1.2.x's `upgrade.py` refuses to start otherwise. Restoring discards
  everything done since the upgrade; follow the rollback steps in the releases guide. The stored
  password and the token files need nothing — 1.2.x ignores them.

---

## v1.2.3

### Fixed

- **Auto Pilot kept producing videos it could not post.** When posting was blocked, it went on
  approving scripts and paying for their voice, render and review, so videos piled up at Video
  Approved without limit. Posting is blocked when no account is selected, publishing is off, an
  account's daily number is 0, or a post was cancelled. The limit only counted posts already
  scheduled, and in those cases there were none.
- **Approved videos sat at Video Approved while Auto Pilot was at its limit.** Reaching the limit
  stopped the scheduling as well as the approvals. So videos approved in the pass that reached it
  were stranded there, and nothing new was produced either.

### Changed

- **Settings → Auto Pilot → Most scheduled posts is now Most videos in progress**
  (`auto_pilot_max_scheduled` is renamed `auto_pilot_max_in_flight`).
  - **What it counts:** every video in an Auto Pilot project from the moment it is voiced until it
    publishes, plus every post waiting to go out. Posts you schedule by hand still count. Before,
    it counted only scheduled posts.
  - **What it stops:** at the limit, Auto Pilot stops voicing new scripts and approving topics. It
    keeps approving finished videos and scheduling them, so the backlog drains.
  - **It tops up:** each video that publishes lets one new script through.
  - **Revisions are not held back:** a video sent back for revision keeps its place and is
    re-voiced even when the limit is full.

### Upgrade notes

- **Your stored number carries over unchanged, and is now tighter.** It used to count only queued
  posts. It now counts every video in progress, so the same number lets fewer videos into
  production. **Raise it, and size it in days of posting.** At 5 posts a day, a limit of 5 is one
  day of cover, and any render retry or revision round will miss a post. 15 to 25 (three to five
  days) is a sane start. 0 still means no limit.
- On upgrade, an install already over its new limit voices no new scripts until enough videos have
  published. Finished videos keep being scheduled meanwhile, so posting does not stop.
- An open Settings tab from before the upgrade cannot change the limit until it is reloaded. Saving
  from it keeps the stored number.

## v1.2.2

### Added

- **Settings → Images → Character model** chooses which OpenAI model draws the Illustrated style's
  characters: `gpt-image-2.5-flare` (the default) or `gpt-image-2.5-sunburst`. Before, the model was
  fixed in the code, so a change on OpenAI's side could only be worked around by a new release.

### Fixed

- **Illustrated videos could not produce any character art.** Every character request failed with
  "Transparent background is not supported for this model", so no Illustrated video could get past
  its scene work. OpenAI withdrew transparent backgrounds from `gpt-image-2` in early October 2026.
  Characters now use the `gpt-image-2.5` models, which support them.
- When an OpenAI key belongs to a project that has not been granted the chosen image model, the
  error now names the model and the project and says what to change. Before, it was OpenAI's raw
  response.

### Changed

- **`gpt-image-2` is no longer offered**, for scene images either. The OpenAI image models are now
  `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst`, priced the same as `gpt-image-2`.

### Upgrade notes

- If your scene images were set to `gpt-image-2`, the upgrade switches them to
  `gpt-image-2.5-flare` automatically. Nothing to do.
- **OpenAI grants model access per project, not per account.** If your OpenAI key's project has not
  been granted the `gpt-image-2.5` models, Illustrated videos (and scene images, if you chose
  OpenAI for them) fail with an error naming the project. Fix it by giving that project access in
  your OpenAI organisation, or by entering a key from a project that has it under Settings → API
  Keys. Scene images can also be switched to Gemini. OpenAI's model list can show these models
  before your project can actually use them, so seeing them listed is not proof of access.
- Redeploy the agent skills (`python onboard.py --install-agent <agent>`) so the scene-writing
  guidance matches. There is no MCP signature change, so no reconnect is needed.

---

## v1.2.1

### Added

- **A ceiling on how far ahead Auto Pilot commits.** Before, Auto Pilot approved and scheduled
  everything that cleared the gap and the daily numbers. A busy day of research could therefore
  line up weeks of posts, and pay for the voice, images and agent sessions behind every one, before
  anyone looked. **Settings → Auto Pilot → Most scheduled posts** now sets how many posts may wait to
  go out. Once that many are waiting, Auto Pilot stops approving topics, scripts and videos, and
  stops scheduling. Each post that goes out lets one more through, so it never waits for the queue
  to empty. Posts you schedule by hand count towards it. While it is full, the tab says why Auto
  Pilot is idle, for example *"Paused — 10 of 10 scheduled posts pending"*. A post that is stuck
  never counts, so the ceiling cannot pause Auto Pilot for good.
- **A default script profile per domain.** On the Topics page, each domain row and the add-domain
  form now have a **Script profile** picker. A curriculum video filed into the domain arrives at the
  topic checkpoint with that profile already selected, so a series is written in one style without
  picking it on every topic. You can still pick another before approving. As with the domain's
  default visual style, trending, mining and manually submitted videos are unaffected. Changing the
  default does not touch videos already filed. A deleted profile is not applied.
- **The video's voice and voice model in its details.** A video's details panel used to list the
  agent, model and script profile, but not the voice. It now shows the **Voice** and the
  **Voice model** wherever the voice is not being picked. That covers videos in progress, the
  Library and the Archive. The model is the one the video was actually voiced with, even if the
  voice's model was changed in Settings afterwards. Before a video is voiced, the panel shows the
  voice's current model, marked *(current setting)*.

### Changed

- **The domain pickers on the Topics page are labelled.** Each domain row now has three dropdowns, so
  each one carries a caption above it: **Visual style**, **Default voice** and **Script profile**.
  Before, the two that existed had no caption at all, and only a hover tooltip told them apart.

### Fixed

- **A video holding a deleted script profile can now be approved.** If a video at the topic
  checkpoint held a profile that had since been deleted, its profile picker showed "No profile" but
  approving it was refused. When no profiles were left, the picker was hidden as well, so the
  video could not be approved at all. The picker now shows the deleted profile as unavailable and
  stays visible, so you can switch it to another profile or to none.
- **A proposed topic's Quick Actions row fits on one line on a wide screen.** The visual style
  picker was sized for its longest option, "Illustrated (needs an OpenAI key)", which pushed the
  **Revise** button onto a second line even at 1920px. The picker is now narrower. The status, score
  and date under each title are smaller too, and they break between items rather than mid-word
  ("TOPIC / PROPOSED") when the column is narrow. At narrower widths the row still wraps, because it
  carries eight controls.

### Upgrade notes

- The Auto Pilot ceiling starts at **0**, which means no limit, so Auto Pilot behaves exactly as
  it did in 1.2.0 until you set it. If you do set one, remember that posts you scheduled yourself
  fill it too.
- The database gains one column on upgrade (`projects.default_script_profile_id`, empty for every
  existing domain). It is applied automatically, and a backup is taken first as usual. Every domain
  starts with no default profile, so nothing changes until you pick one.
- If you drive Tubematic from an agent session, reconnect its MCP server after upgrading, because
  `upsert_project` gained a `default_script_profile_id` parameter. A session that is not reconnected
  keeps working but cannot set the new default.

---

## v1.2.0

### Added

- **Several videos advance at once.** The scheduled agent now works on up to three videos at the
  same time, each in its own session, and starts a video's next stage as soon as the last one
  finishes. Before, it ran a single session every poll interval (30 minutes by default), so a video
  needing four agent stages took about two hours to get through them and every other video waited
  its turn. Set the number of sessions on **Settings → Scheduling**; research and script-profile
  builds run beside them and do not count towards it.
- **A session timeout.** A session that runs longer than **Settings → Scheduling → Session timeout**
  (90 minutes by default) is stopped along with anything it started. Before, a hung session had no
  limit and held up all scheduled work until someone killed it.
- **STUCK videos and Retry agent.** A video that three sessions in a row fail to move is no longer
  retried endlessly. Its card shows **STUCK**, a comment says what happened, and the scheduled
  agent leaves it alone until you press **Retry agent** in its modal or change its status. It keeps
  its status: it is not marked failed.
- **A poller that stopped mid-session no longer loses track of its sessions.** If the poller dies —
  a reboot, an out-of-memory kill — the sessions it started keep running, and the next one takes
  them over instead of starting the same video a second time. It also records their costs when they
  finish.
- **Spend for any range of days.** Spend has moved to its own **Spend** tab on the Analytics page,
  with a range picker: Today, This week (from Monday), This month, or a custom start and end date.
  It used to show only the current month.
- **Schedule a post instead of publishing it now.** The Publish dialog has a **When** choice:
  **Publish now**, as before, or **Schedule**, with a timezone picker that defaults to your own, a
  date and time, and presets such as *Tomorrow 9:00*. The video uploads straight away and waits in a
  new **Scheduled** column on the Pipeline board (and a Scheduled filter in the Library), each card
  showing the date, time and timezone it goes out at; postforme sends it then. Until it goes out,
  **Cancel schedule** in the video's window takes it back to Video Approved with nothing posted. There
  is no reschedule: to change the time, cancel and schedule again. A scheduled time must be at least
  5 minutes and at most a year ahead, and a time that daylight saving skips is refused rather than
  moved by an hour.
- **Sort published videos by views, likes, comments or shares**, highest first, from the **Sort by**
  menu on the Analytics page. A video whose platform has not reported a figure sorts below one that
  reported zero.
- **Pick a video's voice when approving its topic.** The Quick Actions row and the video modal (on
  the Pipeline and Projects pages) now offer the voice picker at the topic checkpoint, each voice
  labelled with its ElevenLabs model. A script is written for its voice's model, so this is where to
  choose a voice on a different model: at script approval a switch between `eleven_v3` and any
  other model is almost always greyed out, because nearly every script carries that model's pause
  markup. Leaving the picker alone keeps the voice the video already has — its domain's default
  voice, or the install default. A topic sent back to this checkpoint by a revision can move to a
  voice on any model too, even while it still holds its old script, since approving the topic has
  the script rewritten anyway.
- **Asking for a voice on another model in a revision now works.** Request a revision at script
  approval naming the voice, and the agent rewrites the script for that voice's model and returns it
  for approval on the new voice. Before, the agent had no instructions for it and tried to change
  the voice on its own, which is refused.
- **Failed and rejected videos can clean up after themselves.** A new setting, **Settings →
  Retention → Delete failed and rejected videos after**, deletes a failed or rejected video's
  rendered file and working files that many days after it last changed, and moves it to the
  Archive. Before, only published videos were ever cleaned up, and a failed video kept its audio,
  images and any partial render until someone deleted it by hand. The same tab now shows how many
  failed and rejected videos there are and how much disk they hold.
- **Graphs on the Analytics page.** The Videos tab now has three graphs beside the table: views per
  platform, views per account, and views gained in each of the last 12 months (in the host's
  timezone). They follow the platform and account filters, and clicking a platform or account bar
  filters the page to it. The first month a post was tracked includes every view it had before
  then, so that month can look like a spike.
- **The Analytics video list scrolls on its own.** The table has its own scroll box with a header
  that stays in view, so a long list no longer scrolls the whole page. It shows 50 videos at a time
  and loads more as you scroll down.
- **Quick Actions is grouped by status and can be filtered.** The Pipeline page's Quick Actions
  inbox now lists Topic Proposed, then Script Ready, then Video Ready, each under its own heading,
  instead of mixing them by age. Within a status the oldest is still first. A row of pills above the
  list shows how many videos wait at each status, and clicking a pill hides or shows that status. The
  filter resets when the page is reloaded, so a forgotten filter cannot hide work waiting on you.
- **Auto Pilot: selected projects run with no human checkpoints.** On the new
  **Settings → Auto Pilot** tab you choose which projects are on it and which connected accounts
  each one posts to. For those projects Tubematic approves the topic, the script and the finished
  video itself, then posts the video. Two settings pace the posting: a daily number for each
  account under **Accounts** (1 by default; 0 means Auto Pilot never posts there), and one **Gap
  between publishes** (4 hours by default, set in minutes or hours) that keeps an account's posts
  apart. Posts you publish or schedule by hand count towards both. Projects you do not select keep
  every checkpoint, pausing the pipeline pauses Auto Pilot, and cancelling a scheduled post takes
  that video off it. It is off by default. **Before turning it on:** it approves with no human
  review; it spends ElevenLabs credits, image generation and agent sessions on every topic that
  research files, limited only by the research caps; it posts publicly to real accounts, including videos
  the AI review flagged, could not check or never ran on; and a published post cannot be taken
  back by Tubematic. Turning it on asks for confirmation and says how many waiting videos will be
  approved at once. A new install is asked about it only by `--full-questionnaire`.
- **Every video carries a "Made with tubematic.ai" watermark.** A small mark sits in the top-right
  corner for the whole video, the same size and place on every video. The agent cannot move or
  remove it. To render without it, switch off **Settings → Rendering → Watermark**.

### Changed

- **Quick Actions rows no longer wrap because of an "agent not installed" note.** When a video's
  agent cannot run it, the row now greys out its agent, model and effort controls instead, and the
  reason shows when you hover over them. The row's agent dropdown stays usable, so you can still
  move the video to an installed agent.
- **One session is one stage of one video.** A session used to take every video that shared an
  agent, model and effort level and carry each as far as it could, so a session that started at
  voicing also wrote the scenes. Each session now does one stage — scripting, voicing, scene work or
  a revision — and stops. A video's cost breakdown therefore shows what each stage cost, where it
  used to split a shared session evenly and label all of it with the stage it started at. Sessions
  recorded before this release keep their even split, and a voicing session from before it is
  labelled "Voicing & scene writing", because it also covered the scene work that followed.
- **Research runs at most once each time the poller starts**, still subject to the pending-topic cap
  and the daily run cap. Before, it was attempted once per poll interval.
- **Pausing lets running sessions finish.** A pause now stops new sessions from starting; any
  session already running completes. Pending script profiles are still built while paused, as
  before.
- **The scheduled agent no longer runs when the pipeline API cannot list the waiting videos.** It
  used to fall back to one session told to work on every waiting video, which could hand a video to
  the wrong agent.
- **`poll.log` names the session each line came from**, such as `[video=vid_…]` or `[research]`,
  since several sessions now write to it at once.
- **The Publish dialog opens straight away and costs nothing.** The agent now writes the publish
  title and description while it writes the script, and the dialog opens on them. Before, the first
  time the dialog opened for a video it waited on a Gemini call to suggest them, which cost money,
  could take up to 20 seconds, and fell back to the bare topic whenever Gemini failed. You can still
  edit both in the dialog before publishing.
- **The Analytics account filter names each account**, such as `mychannel (Instagram)`, instead
  of showing postforme's account id. An account postforme no longer lists, or any account while
  postforme cannot be reached, still shows its id with the platform.

### Fixed

- **The Quick Actions voice picker could show one voice and voice with another.** If the page's
  video list loaded before its settings, a video with no voice of its own showed the first voice on
  the roster, while approving sent none, so it was voiced with the install default. The picker now
  always shows the voice approval sends, and a voice that has left the roster is listed as itself
  instead of as a different one.

### Upgrade notes

- **Three sessions at once applies to your install straight away.** Each session is a paid agent
  run. If you are on a tight budget, set **Settings → Scheduling → Concurrent sessions** to 1 before
  or right after upgrading; one session at a time still gets through a video's stages faster than
  before, because the next stage no longer waits for the next poll interval.
- **Restart any agent session left open after upgrading.** `upgrade.py` redeploys every installed
  agent's skills and MCP registration itself, but a running session keeps the old tools until it
  restarts. If `upgrade.py` warned that an agent was **not redeployed**, or you upgraded without
  it, run `python onboard.py --install-agent <agent>` before the next scheduled session. An agent
  left on the old skills still works, but:
  - a session may look for more work after its stage is done, instead of stopping;
  - a revision asking for a voice on another model is not carried out;
  - an illustrated video can come out with no generated characters;
  - scripts it writes are refused for having no publish title and description. It usually recovers
    from the refusal's message, but may instead leave the video at Topic Approved with a comment
    saying why.
- **Sessions are now stopped after 90 minutes.** Before, a session had no time limit, and the
  setting does not exist until this version is installed. If your agent's sessions can take longer —
  a slow model, long scene work — pause the pipeline before upgrading (see below), leave it paused
  after the upgrade, raise **Settings → Scheduling → Session timeout**, and only then resume.
  Otherwise those sessions are stopped, and after three in a row that move a video nowhere it is
  marked STUCK.
- **Videos scripted before the upgrade have no publish title or description of their own.** Unless
  the dialog had already been opened for them, it opens on the video's title and topic instead —
  edit them there before publishing. A script or pronunciation revision on such a video writes a
  pair, as a new script does. On a project put on Auto Pilot nobody opens the dialog, so such a
  video is posted with its title and topic as the post's title and description.
- **Pause the pipeline before an upgrade or a `scripts/service.py stop`.** Both refuse to run
  while the scheduled poller is running, and the poller now keeps running between sessions while
  there is work. Paused, it exits as soon as its running sessions finish; then run the command
  again. `--force` goes ahead anyway.
- **Spend days now follow the host's timezone.** "This month" used to be the UTC month; it now
  starts at midnight on the 1st in the pipeline host's timezone, like every other date on the
  dashboard. If your host is not on UTC, figures near a month boundary can differ from what the
  previous version showed for the same month. The ElevenLabs credit tile still shows ElevenLabs'
  own billing period, whichever range is picked.
- **Videos rendered after the upgrade carry the watermark.** It is on by default. Switch it off
  under **Settings → Rendering → Watermark** before the next render if you do not want it. Videos
  already rendered are not changed, and a video picks up the current setting when it is re-rendered.
- **The failed-and-rejected cleanup is off until you turn it on.** Upgrading changes nothing. Once
  it is set, a failed video that gets archived can no longer be retried, and old rejected topics
  move from the board's Rejected column to the Archive.
- **Auto Pilot is off after upgrading, and does nothing until you switch it on and select a
  project.** The API, the render worker and the dashboard all need the new version for it to work,
  which a normal upgrade rebuilds. The Publishing tab's description now mentions Auto Pilot; with
  Auto Pilot off, publishing still happens only when you click.
- **The database gains new columns on `videos`** (the stuck flag and its counter, a scheduled
  post's time and timezone, and two Auto Pilot marks), added automatically on upgrade. The same
  step relabels the cost of every voicing session recorded before the upgrade as "Voicing & scene
  writing", because those sessions also did the scene work. As with any release that migrates the
  database, going back to 1.1.x means restoring the pre-upgrade backup — see Releases and
  Upgrades → Rollback policy.

---

## v1.1.2

### Fixed

- **The Projects page no longer squeezes a project's videos into a narrow strip.** If any project
  had a long description, the project list on the left grew to almost the full width of the page.
  Selecting a project then showed its videos in a column about 160px wide, with each card's status
  badge overlapping its title. The project list now keeps its fixed width. Long descriptions are cut
  off with an ellipsis, and long names wrap. The Script Profiles page had the same flaw, triggered by a profile name
  with no spaces, and is fixed too.

---

## v1.1.1

### Added

- **Exact pronunciation with IPA on `eleven_v3`.** For a voice on `eleven_v3`, the agent can
  now give a hard name or term an exact International Phonetic Alphabet transcription. Before, it
  had only respellings. The narration uses the transcription; the captions, the Script tab and the
  stored script still show the word as written, so viewers never see IPA on screen. ElevenLabs rates
  it at 80–90% consistent, so the occasional word can still come back from AI review as mispronounced.
  The IPA characters are billed like any other text. On any other model the tag is refused when the
  script is written and again before voicing, because those models read IPA out loud. The Settings
  voice model notes and onboarding reflect it.
- **Each voice now has its own ElevenLabs model.** In Settings → Voice, every voice in your roster
  has a model picker, so one install can narrate one domain on `eleven_v3` and another on
  `eleven_multilingual_v2`. The model decides which pronunciation and pause markup a script can use,
  so a script is now written for its own video's voice. The single install-wide model setting is gone.
- **Voice previews use that voice's model**, including a model you have just picked and not yet
  saved. After a model change, the next play is a fresh sample rather than the old one.
- **The preview button pauses.** It shows ❚❚ while a sample plays, and a second click stops it.
- **Domains have a default voice.** On the Topics page, each domain row (and the add-domain form)
  has a default-voice picker. Every new video filed into that domain starts with it, however it
  was sourced, and you can still change the voice per video. Changing a domain's default does not
  touch videos already filed there. The New Video page's "Default" option follows the Manual Videos
  domain's default voice.
- **A voice that cannot speak a script is refused at approval, before any charge.** At the script
  checkpoint, voices whose model cannot use the script's markup are shown but disabled, with the
  reason, and the API refuses them.

### Fixed

- **`eleven_english_v1` is no longer offered as a voice model.** ElevenLabs has retired it and now
  rejects every request for it, so an install set to it could not voice anything. It is gone from
  the model list in Settings, in onboarding, and from what the settings API accepts.
- **A mistyped pronunciation alphabet no longer deletes a word from the narration.** A phoneme tag
  whose `alphabet` was anything other than `cmu-arpabet` or `ipa` was voiced without complaint, but
  ElevenLabs quietly left the wrapped word out of the audio. The script is now refused when it is
  written, with a message saying why, and again before voicing.
- **Pause markup that ElevenLabs does not support is refused before you are charged.** A
  `<break time="…" />` longer than 3 seconds, or not written in seconds, used to be sent as-is.
  It is now refused when the script is written and again before voicing.
- **A video's cost panel no longer splits an agent model's name across two lines.** When a video
  was worked by more than one model, the Agent row listed them as one comma-separated line, which
  wrapped mid-name (`claude-opus-5, claude-` / `opus-5-5`), so the broken half read as part of the
  price beside it. Each model now sits whole on its own line.
- **The poll log and the dashboard's Logs page no longer carry each agent run's whole
  transcript.** Every run of Codex or OpenCode wrote its entire session into `poll.log` — each tool
  call's arguments and full results — tens of kilobytes per tick, burying the lines that mattered.
  A run now logs its closing message, a one-line list of the tools it called (with how many
  failed), and any error the agent's CLI reported. Its error output is cut to the last 4,000
  characters. The full session is still kept by the agent's own CLI, in its session history.
- **A failed image, voice or topic-mining call now shows up in the logs.** When Gemini, OpenAI or
  ElevenLabs refused a call (for example, a Gemini account whose prepayment credits had run out),
  the MCP log recorded it as an ordinary successful tool call. Nothing said what had failed, and
  every cron tick then started another billed agent session that hit the same wall. Such a call
  is now an `error` on the Logs page. It names the provider, model, HTTP status and the provider's
  reply, with credentials removed. A tool that turns the agent away before any paid call (a paused
  domain, a frozen field) is a `warning` instead, and every MCP log line carries an `outcome`
  field. The Troubleshooting chapter of the documentation explains what each level means.

### Upgrade notes

- **A script already waiting for approval that contains one of the refused values is stopped at
  voicing, with no charge.** Request a revision on it and the agent rewrites the markup.
- **Your voices keep the model your install was using.** The upgrade moves the old install-wide
  model onto every voice in your roster, so nothing you hear changes. If that model was the retired
  `eleven_english_v1`, the voices move to `eleven_multilingual_v2`. Set different models per voice
  in Settings → Voice afterwards if you want them.
- **This upgrade cannot be rolled back by reinstalling 1.1.0 alone.** 1.1.0 cannot read the new
  voice roster and would see no voices at all. To go back, restore the database backup the upgrade
  takes automatically before it migrates.
- **Reload any Settings page left open across the upgrade.** An old page still sends the retired
  model setting, and the save is refused with "Unknown settings".
- **Changing a voice's model can block approval of scripts already written for it.** A script at
  the checkpoint whose markup the new model cannot speak is refused at approval with the reason,
  and one already approved is stopped at voicing. Nothing is charged either way. Request a revision so the agent rewrites it for that voice, or change the
  model back.
- **Scripts and `vqa/edit_settings.py` calls that set `elevenlabs_model_id` need updating.** Set a
  model on each voice in `elevenlabs_voices` instead, as `{"name", "voice_id", "model_id"}`.
- **Redeploy the agent's skills and reconnect the MCP session.** The agent now reads each video's
  model from `get_video`, and `get_pipeline_status` no longer reports one. With old skills, the
  agent keeps looking for an install-wide model that is gone, and it never learns the IPA tag, so
  it keeps writing respellings for voices on `eleven_v3`.

## v1.1.0

### Added

- **A second visual style for your videos.** Until now every video came out the same way: a dark
  canvas with generated imagery and animated diagrams. There is now a **Stick Explainer** style —
  a white canvas, black line art, and simple figures that hold a pose and change in a single frame
  rather than moving continuously. It suits a walkthrough or a hypothetical, where the people on
  screen are roles ("the user", "an attacker") rather than anyone in particular.
- **A style picker on the topic card.** When you approve a topic you now choose its style
  alongside the script profile and the model: **Auto**, **Motion Graphics**, **Stick Explainer**
  or **Illustrated** (described below).
  The choice is fixed once the topic is approved, for the same reason the script profile is —
  the script itself is written differently depending on it, so changing it later would mean
  rewriting the script, not just re-rendering.
- **Auto, which decides for you.** Left on Auto, the pipeline looks at what the video is actually
  about and picks a style once, for the whole video. It then shows you which one it chose, marked
  as automatic, so you can tell at a glance why two videos look different. A video that comes back
  for revision is always re-rendered in the style it already has.
- **An Illustrated style, for videos built around a character.** Instead of hand-drawn line
  figures, the characters are generated artwork. Each one is drawn once and every later pose is
  produced from that first drawing, so the same person is recognisably the same person from scene to
  scene — which is the thing this style is for, and the thing generated pictures normally cannot do.
  The pipeline picks the look from the topic: simple cartoon figures for something playful, properly
  rendered illustration for something serious. It costs one image generation per pose, so it suits a
  video with a recurring character carrying a story rather than a walkthrough full of one-off roles.
  Requires an OpenAI API key — it is the only provider offering genuine transparent cut-outs, so
  there is no fallback. Without a key the option is greyed out and says why, on the topic card, in
  the video window and as a domain default, and a video left on Auto draws its characters as line
  art instead. With a key, it is used for these characters **even when image generation is set to
  Gemini** — an Illustrated video bills OpenAI whichever image provider you chose.
- **A default style per curriculum domain.** A domain on the Topics page can pin the style its
  scheduled curriculum videos start in, so a series looks consistent without choosing every time.
  Videos filed into that domain from trending, mining or a manual request are unaffected. Domains
  created before this release can be given a style directly on the Topics page.

- **Subtitles, on every video.** The narration is now burned into the video as captions, in sync
  with the voice, a few words at a time rather than a whole sentence at once — the word being
  spoken is highlighted and the rest of the phrase is dimmed. This is **on by default**, including
  for videos whose scenes were built before this release. The font, size, colour, position,
  background and how many words appear at once (between one and seven) are all adjustable per
  video, and the pipeline can turn them off for a video where they genuinely do not belong.

- **Choose how hard the agent thinks.** Alongside the model, you can now set an **effort level** —
  low, medium, high, extra high or max. Higher levels think longer and cost more; the default is
  **high**, because a run writes scripts and scene code you then have to review. Set it for the
  agent as a whole on **Settings → Agents**, and override it for a single video on the topic card
  when you approve it. A video you do not set explicitly just follows its agent, so changing the
  agent's level later moves those videos with it. Like the model, a per-video choice can be changed
  whenever the video comes back to you for review, and is fixed while the pipeline is working on it.
- **Codex can now run the pipeline.** OpenAI's Codex CLI can be installed as a pipeline agent
  alongside, or instead of, Claude Code:

  ```bash
  python onboard.py --install-agent codex
  ```

  Both agents can be installed at the same time, and each video is assigned to one of them the way
  it already was — the default agent and each agent's share of new videos are set on
  **Settings → Agents**. You can also move a single video to a different agent yourself — see the
  next entry. Codex installs at user scope only and puts its Tubematic skills in
  `~/.codex/skills/`. It does not get the `/tubematic-*` slash commands, because the Codex CLI has
  no custom-command mechanism; everything the scheduled pipeline does is unaffected, since that is
  driven by a prompt rather than by a command.
- **Choose which agent works on a video, every time it comes back to you.** A new video is still
  given an agent automatically, in the shares set on **Settings → Agents**. But now, whenever a video
  waits for you — a proposed topic, a finished script, a finished video — the review shows which
  agent it is on and lets you hand the next piece of work to a different one, along with its model
  and effort level. The choice goes with whatever you do next: approving the topic hands the script
  to that agent, approving the script hands it the scenes, and requesting a revision hands it the
  revision. Only installed agents are offered. Switching agent starts it on its own default model
  (the old model belongs to the other agent) and says so as you switch; the effort level is kept.
  While the pipeline is working on a video, its agent cannot be changed. Moving a video by hand does
  not affect how new videos are shared out.
- **OpenCode can now run the pipeline too.** OpenCode is the third supported agent, alongside
  Claude Code and Codex:

  ```bash
  python onboard.py --install-agent opencode
  ```

  Any number of agents can be installed at the same time, and each video is assigned to one of them
  as before — the default agent and each agent's share of new videos are set on
  **Settings → Agents**. OpenCode installs at either user or project scope, puts its Tubematic
  skills in `~/.config/opencode/skills/`, and **does** get the `/tubematic-*` slash commands.
  Its per-run effort level is applied as a model variant, so on **Settings → Agents** and the topic
  card it works exactly like the other agents'.

  This needs the OpenCode **v2** CLI — the `@opencode/cli` package. The older `opencode-ai` package
  is the 1.x line and is not supported.
- **Tell the agent your preferences once, for every video.** A new **Settings → Preferences** tab
  holds your standing instructions: topics to favour or avoid, the tone and audience of scripts,
  the look you want, and so on. Write them in one box, up to 6000 characters (a counter shows how
  many are left). The agent receives them on every run, clearly marked as yours, and applies only
  the parts that fit what it is doing at the time, so a note about script tone does not change
  which topics research picks. Preferences never override a human checkpoint: writing "approve my
  scripts" does not let the agent skip your approval. Leave the box empty and nothing changes.

- **What each video actually cost, per provider and per model.** Every paid call is now recorded
  with the usage the provider itself reported: each voice generation, each AI review (so a video
  reviewed twice shows two reviews), every image and character, topic mining, publish-title
  suggestions, and every agent session. The video's detail view lists them per provider and per
  model with a total. Figures are estimated at each provider's API list prices, and the dashboard
  says so beside every total: they do not reflect a subscription, plan credits or a discount.
  - **Agent sessions are shared.** One agent session usually works on several videos at once, so a
    video shows its even share next to the whole session's cost — "≈ $0.05 (of $0.15)". One click
    lists the sessions behind it, each labelled with what it was doing for that video (script
    writing, voicing and scene writing, scene writing, revision). Claude Code and OpenCode
    sessions use the cost the CLI itself reports; Codex sessions are priced from their token
    counts.
  - **A call with no known price is counted, never shown as $0.** It appears as "+ N unpriced
    calls" beside the total until a price is added for its model.
- **A spend card on the Analytics page.** It shows this month's total, split into videos, research
  and mining, and other agent runs. This is also where spend that belongs to no video appears:
  research sessions, topic mining and voice previews. If your ElevenLabs key has the `user_read`
  permission, the card also shows how much of this month's ElevenLabs credit allowance is used.
- **A Costs tab in Settings.** It lists the price of every model Tubematic pays per token, where
  that price came from, and when it last synced. Prices sync weekly on their own, and **Sync now**
  syncs immediately. You can override any price by hand, and a manual price is never changed by a
  sync. Adding a price for a model that had none fills in its earlier unpriced calls.
- **Submit a video from the dashboard.** A new **New Video** page, linked in the top bar, lets you
  request a video without opening an agent session. Give it a title (at most 70 characters) and a
  description of the topic. Optionally, choose the agent, model, effort level, script profile,
  visual style and voice. **Automatically approve topic** is ticked by default, so the video goes
  straight to scripting on the next scheduled run. Untick it to review the topic on the Pipeline page
  first. These videos are filed under a new **Manual Videos** domain, which appears the first time
  you use the page. They are not scored, and their cards show "—" where the score would be.
  The `/tubematic-submit-new-job` command works as before: it still scores the topic and files it
  under a matching domain.

### Changed

- **Videos now carry far less text on screen.** Because the narration is captioned automatically,
  scenes no longer write it out as well. Headlines that restated the sentence being spoken, titles
  announcing the topic, lower thirds and captions under pictures are gone; text now appears only
  where it carries information the voice and the captions do not — a number, a label on part of a
  diagram, a defined term, a command, a chart axis. The result is a less cluttered frame and, in
  places, better animation, because a beat that used to be a headline over a still picture now has
  to be shown rather than written.
- **The automatic quality review was taught about the captions**, both that they are intended —
  otherwise it would have sent back every single video as having duplicated text — and that a scene
  writing out the narration on top of them is now worth flagging.
- **Choosing Stick Explainer does not restrict what a video can contain.** Diagrams still appear,
  drawn as line art; a real place or a named person still gets a generated image, shown inside a
  framed panel rather than filling the screen. What the style fixes is the background colour and
  how a generic role is drawn.
- **The automatic quality review now knows which style it is looking at**, so it no longer treats
  deliberately simple line art, or a figure holding still, as a fault. Before this it would have
  sent such videos back for revision — and a revision re-voices the script, which costs money.
- **Every choice you make when approving a topic or a script is now labelled.** The script
  profile, visual style, agent, model, effort and voice dropdowns — on the Pipeline board's Quick
  Actions and in a video's detail window — each carry a caption, where before they were a row of
  unnamed dropdowns you could only tell apart by their contents.
- **A video stuck waiting to be voiced now tells you so.** A video that is approved but has not been
  voiced after three poll intervals gets a comment saying so, and an error in the renderer log. If a
  Discord webhook is set, it also sends an alert, even with every notification trigger turned off.
  Before, a video that kept failing to voice looked the same as one the agent had not reached yet.
- **The model and effort level can now be changed at every review, not only at the topic.** Before,
  both were fixed the moment the topic was approved. They now stay changeable whenever a video is
  waiting for you — at the script and the finished video too — and are fixed only while the
  pipeline is working on it. The script profile and visual style are still fixed at the topic,
  because the script itself is written to them.
- **Only curriculum seed domains can be paused now, and the control says what it does.** On the
  Topics page it reads **Pause topic generation** and appears only on seed domains. A pause stops
  topics being generated from a seed. Any other domain only receives topics found elsewhere, from
  trending or mining, so pausing it never stopped those topics. They were filed into a neighbouring
  domain instead. Pausing a non-seed domain is now refused rather than silently doing nothing. A
  topic you submit yourself is still accepted into a paused domain.

- **Voice cost is shown in ElevenLabs credits, not dollars.** It used to be a dollar estimate
  worked out from the script's character count at a fixed rate. That estimate was wrong in both
  directions: it left out pause tags, which ElevenLabs bills, and it ignored the half-price Flash
  and Turbo models. Voice usage is now the exact number of credits ElevenLabs reports deducting for
  each call. It is not converted to dollars because those credits come from a prepaid plan. Voice
  previews also record their credits now; before, the cost was shown once and then forgotten.
- **Agent runs keep their output in a machine-readable form.** Claude Code, Codex and OpenCode are
  now run in their JSON output modes so each run's usage can be recorded. Their full output still
  goes to the poller's log, so it looks different there than before.
- **The agent tool for recording costs by hand is gone.** No skill used it, and now that costs are
  recorded automatically it could only have counted the same spend twice.

### Fixed

- **An approved script is voiced without the agent asking again.** Sometimes the agent refused to
  voice a script you had already approved. It left a comment asking you to authorize the
  ElevenLabs charge, then did the same on every later run, so the video never moved. Approving the
  script is that authorization, and the agent's instructions now say so plainly. Approving a script
  is still the only way it gets voiced.

- **A visual style chosen from the Projects page is no longer discarded.** Opening a proposed
  topic from a project and picking a style there sent the approval without it, so the video was
  approved in whatever style it already had — and because the choice is frozen at approval, it
  could not be corrected afterwards. The same was true of the script profile and the model picked
  from that page. The Pipeline board was never affected.
- **Captions no longer linger through a deliberate pause.** A caption held until the next one
  began, which is right for the ordinary gap between clauses and wrong for a scripted pause: the
  previous words stayed on screen through a second or more of silence. They now clear shortly
  after the last word is spoken, while short gaps still carry across without flicker.
- **A domain's default style is no longer wiped by unrelated commands.** Converting an existing
  domain into a curriculum seed, or filing a video into it, silently reset the style — and could
  also blank the domain's description or clear its seed flag. Those commands now change only what
  they name.
- **Requesting a revision from the Library now works.** Asking for changes to a finished video from
  the Library page saved your comment but never sent the video back, so nothing happened and it
  stayed waiting for approval. It now goes back for revision, exactly as it does from the Pipeline
  board.
- **A refused approval or revision on the Library or Projects page is now reported.** If the video
  had moved on since the page last refreshed, those pages closed the window as though the action
  had worked while nothing changed. They now say why, as the Pipeline board always has.
- **A paused domain no longer receives new topics.** Nothing actually enforced a pause. Research
  runs were asked not to file into a paused domain, and could do so anyway without any error, so
  new proposals could turn up in a domain you had paused. Filing into a paused domain is now
  refused outright, whether the topic came from curriculum, trending or mining, and the research
  run skips the topic rather than moving it to another domain.

- **Voice credits could go unrecorded.** If ElevenLabs returned a successful response that could not
  be used, voice generation failed without recording the credits ElevenLabs had already charged.
  They are now recorded before the response is used.
- **An unusual reply from the AI reviewer could send a video back for revision.** A reply that
  parsed as something other than a review object crashed the review. The video then went to
  revision instead of the reviewer skipping the review as intended.
- **Uninstalling Tubematic left the GIF skill behind.** The uninstaller deleted every Tubematic
  skill except the one for making GIFs, which stayed in the agent's skills directory. It is now
  removed with the rest.
- **The install check could report an agent's skills as installed when they were not.** It only
  looked for a skills directory, which another installer also creates, so an agent whose own
  Tubematic skills had never been copied still passed. It now looks for the skills themselves.

### Upgrade notes

- **This release changes the database, and going back is not automatic.** Upgrading applies four
  migrations: the visual style, the effort level, the pause change and cost recording described
  below. A backup is taken automatically before they run. To return to 1.0.x afterwards you must
  restore that backup, which loses everything recorded since the upgrade. See
  [Rollback policy](user-guide/07-upgrading.md#rollback-policy).
- **Installing Codex needs the `codex` CLI on your `PATH` and already logged in** (`codex login`;
  `codex login status` should say you are logged in). The installer refuses to continue otherwise,
  on purpose — cron runs the agent unattended, so a logged-out CLI would fail silently on every
  tick. Nothing changes for an existing Claude Code install.
- **Installing OpenCode needs the `opencode` CLI on your `PATH` and logged in to a real provider**
  (`opencode auth login`), and the same refusal applies. Two things are specific to OpenCode and
  worth knowing before you install it:
  - **Log in to a provider you actually have.** OpenCode's free models are far too weak to drive
    this pipeline. (If a run fails with `OpenCode's free tier can only be used from within
    OpenCode`, that is its free tier objecting to the shell tool being denied — seen in OpenCode
    2.0.14 and not in 2.0.15.)
  - **Register the tool server through the installer, not by hand.** `opencode mcp add` on its own
    leaves OpenCode's Code Mode switched on, which hides Tubematic's tools behind a code sandbox
    the skills do not know about; the agent then reports that the tools do not exist. The installer
    turns it off for you.
  - **Your own OpenCode config is never edited by the installer.** Everything Tubematic needs
    goes into a file of its own inside the agent's workspace, so your settings, and any comments
    in them, are left alone. Uninstalling removes the one server entry `opencode mcp add` added,
    and keeps your comments while doing it.
  - **Point the agent at a directory of its own.** If the workspace you choose already contains
    an OpenCode project config, the install stops and says so rather than taking it over — pick
    another directory. The default, `~/.tubematic-agent/opencode`, is always fine.

  Nothing changes for an existing Claude Code or Codex install.
- **To use the Illustrated style, add an OpenAI API key** under Settings → API Keys; it applies
  at once, with no restart. It is needed even if image generation stays on Gemini. Without one the
  style simply cannot be picked, and nothing else changes.
- **Reconnect your agent's tool session after upgrading.** Tool signatures changed; until the
  session reconnects, the agent will not be able to record which style it chose, the slash
  command for submitting a job cannot set a video's effort level or hand it to a different agent,
  and an interactive session will not see your Preferences. Scheduled runs get them regardless.
- **Existing agents start at effort "high".** That is the new default, and it applies to installs
  that upgrade as well as to fresh ones — so if your runs were previously shorter and cheaper than
  they now are, this is why. Lower it on **Settings → Agents** if you would rather trade depth for
  cost. Videos already in the pipeline follow their agent unless you set one explicitly, which you
  can do whenever a video is waiting for your review.
- **An older agent CLI still works.** If the installed command-line tool is too old to accept an
  effort level, the pipeline notices, says so in its log, and runs without it rather than losing
  the tick. Re-running the agent installer warns about this while you are watching, instead of
  leaving you to find it in a 3am log.
- **Redeploy the agent's skills.** The skills are what teach the agent how to build the new style,
  and they are files that live alongside your agent rather than inside the running services —
  upgrading the services alone is not enough. If you upgrade the services and skip this, videos
  keep being produced in the original style, which is safe but means the new option does nothing.
  The fix for approved scripts that were never voiced is also in the skills, so it needs the same
  redeploy, as does applying your Preferences in interactive sessions.
- **Subtitles switch on for videos already in the pipeline.** A video rendered after the upgrade
  gets captions even if its scenes were planned before it. That is deliberate — it is the only way
  the default reaches work in flight — but a video whose scenes already carry their own on-screen
  text will show both until those scenes are rebuilt. If you have videos mid-pipeline you care
  about, re-render them after the skills are redeployed.
- **Paused domains that are not curriculum seeds become active on upgrade.** Pause now exists only
  on curriculum seeds, so any other domain you had paused is switched back to active: nothing would
  be able to change its status otherwise. This is a behaviour change only on paper. Those pauses
  never stopped the topics they were meant to stop. If you want fewer topics on a subject that is
  not a seed, reject the proposals, or turn trending or mining off on the Topics page. Paused seeds
  stay paused.
- **Videos already in the pipeline keep the style they were made in.** The upgrade marks every
  existing video as Motion Graphics rather than leaving it undecided, so nothing in flight changes
  appearance.
- **Check how your social accounts were connected if their analytics are empty.** Connecting an
  account for publishing and allowing its statistics to be read are two separate permissions, and
  the default grants only the first. An account connected that way publishes normally and reports
  no views, likes or comments at all — with no error, no warning, and no indication on the Socials
  page, because nothing upstream refuses the request; it simply comes back empty. If a platform's
  figures have always been blank, reconnect that account and grant the analytics permission as well.
  Nothing can be fixed for you, because the permission is part of the sign-in you performed, and
  only repeating it can change what was granted. Instagram additionally reports statistics only for
  Business and Creator accounts, never Personal ones. Setup and troubleshooting both now spell this
  out; past figures cannot be recovered, but everything from the reconnection onwards is recorded.
- **Costs start from this release.** Videos made before it show "No usage recorded". Their old
  voice estimates are not carried over, because they used a different, inaccurate method. From the
  upgrade on, every call is recorded.
- **To see your ElevenLabs credit allowance on the Analytics page, give your ElevenLabs API key the
  `user_read` permission** (elevenlabs.io → Profile → API Keys). This is optional: without it the
  card shows the credits Tubematic recorded, and nothing else changes.
- **Model prices come from public price lists.** Tubematic reads OpenRouter's model list first and
  LiteLLM's price file for models OpenRouter doesn't list. It checks once a week, in the
  background. An install that can't reach them keeps using the prices shipped with the release, or
  the last ones it synced. Neither list is the vendor's own, so check your invoices for exact
  figures, and correct any price you disagree with on Settings → Costs.

## v1.0.2

### Added

**The dashboard shows which version you are running.** The top bar now carries a version badge, next
to the timezone and the health indicator. It is the quickest way to confirm an upgrade landed, and
it makes a bug report unambiguous. The badge reads the version from the running API, so it reflects
what is actually serving rather than what is on disk.

You can leave the dashboard open across an upgrade and watch it change — there is no need to
reload the page. While the API is unreachable, including during the upgrade itself, the badge shows
nothing at all rather than the version from before, so it never tells you an upgrade landed when it
has not.

### Fixed

**Names could still be read aloud wrongly after being respelled to fix them.** Pronunciation
guidance taught a hyphenated respelling — `Day-mon` for "Daemon" — and the voice engine does not
speak those reliably, so the correction often did nothing. Because a mispronunciation sends the
video back for revision, and fixing one means re-voicing, a name that would not take a correction
could cost several charged re-voices in a row. A respelling is now written as one plain word
spelling the sound (`Daymon`), which is spoken correctly.

### Upgrade notes

- **Check any pronunciation entries you saved before upgrading.** Existing entries are left exactly
  as they are, so a hyphenated respelling saved earlier — `Day-mon` rather than `Daymon` — will keep
  mispronouncing until you edit it. Rewrite any respelling containing a hyphen as one plain word
  spelling the sound. Acronyms spelled out letter by letter, such as `S-Y-N`, are a different case
  and should be left alone. Nothing is rewritten for you, because only you can tell which of the two
  an entry was meant to be.

---

## v1.0.1

### Added

**Retry publishing.** A video that failed while it was being published now has a **Retry
publishing** button next to Delete. It checks postforme before doing anything, so it never posts a
video twice. If the video is already live, it is picked up where it is and settles to `PUBLISHED`
with its post links. If nothing went out, the video goes back to `VIDEO_APPROVED` and the Publish
dialog opens so you can choose the accounts again. A video that failed during rendering does not get
the button.

**`upgrade.py`: upgrading is one command.** Run `python3 upgrade.py` from the version you are
upgrading to. That is the checkout after `git checkout vX.Y.Z`, or the directory you extracted a new
release into. It asks no questions, so it works over a non-interactive SSH session or from a deploy
tool. Before, an upgrade meant several commands followed by the onboarding wizard, which refused to
run without a terminal and walked through every step again.

It does the steps in the order that keeps your data safe:
- It refuses to start while work is in flight: a render, a voicing, an agent run or a publish upload.
  It also refuses when the database was already upgraded by a newer version.
- It pulls or builds the new images while the old stack keeps serving.
- It stops the whole stack, so new code never changes the database while old code is still using it.
- It starts the stack again, rewrites the cron entry to use the new install, and redeploys your
  agent's skills.
- It reports the version, database schema, cron entry and container health.

`python3 upgrade.py --check` shows that report without changing anything. `--dry-run` shows the
plan, `--force` proceeds despite in-flight work, and `--no-stop` recreates containers one at a time.

**`scripts/service.py` to start, stop, restart and inspect the stack.** It has five commands:
`start`, `stop`, `restart`, `status` and `logs`. `start` creates missing data directories and
re-points Docker volumes whose data location has moved before starting anything. A bare
`docker compose up -d` does neither, and could come up on an empty data tree. `stop` and `restart`
refuse while work is in flight, as `upgrade.py` does, so a restart no longer kills a render and
marks the video failed.

### Changed

**A video upload during publishing now stops after 30 minutes.** Before, there was no overall limit.
A stopped upload fails cleanly: nothing is posted, and the video returns to `VIDEO_APPROVED` to be
published again. A typical upload takes about a minute.

### Fixed

**Publishing marked a video FAILED while it was still uploading, and it was posted anyway.** Any
upload that took longer than about twenty seconds, which is most real videos, could be marked
`FAILED` with the comment "Nothing was posted" while the upload was still running. The post then went
live on every account, but the dashboard still showed it as failed and offered only Delete. An
upload in progress is now left alone. A publish that genuinely dies part-way is still caught, after
up to an hour rather than straight away.

**The Logs page showed nothing from the scheduler.** On some installs the dashboard's Logs page had
entries from the API, MCP server and renderer but none from `poll`, the cron job that drives the
pipeline, and nothing said why. The poller runs as your user and could not write to
`~/.tubematic-data/logs` when that directory was owned by root. The API and MCP containers now make
the directory writable for your user every time they start. If the poller still cannot write there,
it says so in `~/.tubematic-agent/logs/poll.log` on every tick, and `python onboard.py` warns about
any data directory you cannot write.

**Secondary text on the dashboard was hard to read.** Hints, labels, section headings, empty-state
messages and intro paragraphs, such as the one at the top of the Socials page, were drawn in a grey
too close to the dark background. They are brighter now and meet the WCAG AA contrast minimum on
every background the dashboard uses. They still sit visibly below primary text.

### Upgrade notes

- The logs directory is repaired the first time the upgraded stack starts, so no manual step is
  needed. Scheduler ticks from before the upgrade are not added to the Logs page.
- A video that 1.0.0 wrongly marked `FAILED` while publishing can be recovered after upgrading: open
  it and press **Retry publishing**. The button appears only when publication records exist for the
  video, which is the case when the post actually went out. A video that 1.0.0 failed before any post
  existed has no records, so the button does not appear. Nothing was posted for it, so it is safe to
  return it to `VIDEO_APPROVED` and publish it normally:
  `curl -X PATCH http://127.0.0.1:4000/videos/<video_id> -H 'Content-Type: application/json' -d '{"status": "VIDEO_APPROVED", "onlyIfCurrentStatus": "FAILED"}'`
- Upgrade with `upgrade.py` from the new version's directory: after `git checkout v1.0.1` in a
  source checkout, or in the directory a new release tarball was extracted into. It is the new
  version's copy that runs, so it works even though 1.0.0 did not have it. On a release install,
  keep the old directory until it finishes: cron still points there until then, and `upgrade.py`
  names it as safe to remove afterwards.
- `upgrade.py` refuses while any video is `RENDERING` or `VOICING`, while an agent is running, or
  while a video is still uploading to be published. Wait for that work to finish and re-run, or pass
  `--force` to stop it anyway.
- Restart any open agent session after upgrading, so it picks up the redeployed skills.

---

## v1.0.0

The first published release. Everything below is what the software does today, rather than what
changed — there is no previous version to change from. Later entries will be much shorter.

### What it is

Tubematic turns a topic into a finished YouTube Short. It researches topics, writes a script, voices
it, generates imagery, animates that imagery in code, renders an mp4, has an AI watch the result for
defects, and publishes it — stopping at three points where a person has to say yes.

It is not a video editor and not a template filler. Every scene is a React component an AI agent
writes for that specific video, compiled and rendered by [Remotion](https://remotion.dev). Output is
1080×1920 at 30fps with a synthesised voiceover, word-timed captions, generated imagery and animated
diagrams.

### Added

**The pipeline.** Topics move through proposal → scripting → voicing → rendering → AI review →
publishing. Three human checkpoints are enforced, not advisory: a script cannot be voiced, a video
cannot be approved, and nothing can be published without a person acting. Two of those exist because
the next step spends money that cannot be refunded.

**Four ways topics arrive.** A curriculum built from your own project domains; trending sources
(GitHub Trending, Hacker News, Lobsters, Dev.to); mining your chosen YouTube channels for subjects
they have covered; and submitting one by hand. Each can be switched off independently, and both the
number of pending proposals and the number of research runs per day are capped.

**An agent layer over MCP.** 38 tools covering the database, voice synthesis, image generation,
GIF building, scene files and script profiles, plus six skills and twelve slash commands. The agent
never writes scene code or configuration directly — everything goes through a tool, so every change
is validated before it lands.

**Scripting with a house style.** Script profiles are built from transcripts of channels you point
at, capturing style only, and any video can be scripted in one of them. Pronunciation is handled by
a lexicon and inline respelling, with pause markup honoured by the voice model.

**Rendering and review.** Renders run in their own always-on container, so a crash or an
out-of-memory kill restarts only rendering. Finished videos are reviewed by Gemini watching the
actual mp4 — not reading the script — and anything it finds sends the video back for revision. A
text-layout audit measures captions in a real browser and reports overlaps and safe-zone violations
as warnings.

**Publishing and analytics.** Publishing to social platforms through postforme.dev, with per-video
metrics on a dashboard page. Publishing is deliberately human-only: no agent and no tool can do it.

**A dashboard.** Ten pages — pipeline, library, topics, projects, script profiles, socials,
analytics, archive, logs and settings — with 33 settings editable live — no restart needed
for any of them.

**Notifications.** Discord messages at each of the three human checkpoints, each independently
switchable.

**Operational groundwork.** Schema changes apply once, in order, tracked in the database, with an
automatic backup taken before any migration and a failed backup blocking the migration rather than
proceeding unprotected. Logs are structured JSON with secret redaction on two independent axes.
Published videos' output is swept after a retention window.

**Installation two ways.** Clone and build from source, or download a release tarball and pull
prebuilt images. One onboarding wizard covers both and detects which it is looking at.

### Upgrade notes

- **Nothing to upgrade from.** Later releases describe their upgrade path here, including anything
  that is not safely reversible.
- API keys live in the database rather than a file on disk. Onboarding asks for each one and
  verifies it against its provider as you type it, so a bad key is rejected at entry rather than at
  first use.
- Pipeline data lives in a fixed location under your home directory. It is deliberately not
  configurable.
