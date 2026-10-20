# Troubleshooting

Symptoms, and where the cause usually is.

---

## Nothing is happening

```bash
curl -s -H "Authorization: Bearer $(cat ~/.tubematic-data/secrets/api_token)" \
  localhost:4000/pipeline/status | python3 -m json.tool
docker compose ps
crontab -l | grep poll.py
tail -50 ~/.tubematic-agent/logs/poll.log
```

| Check | Meaning |
|---|---|
| `"paused": true` | The pipeline is paused. Turn it back on with the switch above the tabs on **Settings** (or `/tubematic-resume` from an agent session) |
| `workable_count: 0` | Nothing for the agent to do. Every video is at a checkpoint or terminal |
| Videos at `TOPIC_PROPOSED`, `SCRIPT_READY` or `VIDEO_READY` | **Waiting for you.** This is the most common answer |
| No cron entry | `python onboard.py --step cron` |
| `poll.log` says "Cannot call the API without its token" | `~/.tubematic-data/secrets/api_token` is missing or empty, so the poller exits on every tick. `python onboard.py --step auth` creates it, and keeps any token that already exists |
| `poll.log` says "No agent installed" | The project is set up but no agent is. `python onboard.py --install-agent <agent>` |
| `poll.log` says a video "is assigned to agent …, which is uninstalled" (or "not installed") | That video is pinned to the agent and is skipped every tick, never rerouted. Re-install the agent with `python onboard.py --install-agent <name>` |
| A card shows **STUCK** | Three agent sessions in a row left the video at the status they found it at, so the poller stopped picking it up. Its comments, and the `[video=<id>]` lines in `poll.log`, say what the sessions did. Fix the cause, then press **Retry agent** in the video's modal, or change its status |
| `poll.log` says "A supervisor holds the poll lock but has not touched … — it may be hung" | The poller is still running but has stopped looping. Nothing is killed automatically, because a session may be mid-way through a paid call. Find it with `ps -ef \| grep poll.py` and stop it once its sessions are done |
| `poll.log` says "Session passed agent_session_timeout_secs" | A session ran longer than **Settings → Scheduling → Session timeout** and was stopped with everything it started. Raise the timeout if long scene work is being cut off |
| `poll.log` says "Agent rejected model" | The model no longer works for this CLI or account. The session re-ran with the CLI's own default; re-run `python onboard.py --install-agent <agent>` to re-check the model list |
| `--install-agent` refuses the workspace path because it "overlaps the poll logs directory" or another agent's workspace | Every agent needs a directory of its own, beside `~/.tubematic-agent/logs/` rather than around it — accept the offered default `~/.tubematic-agent/<agent>`. The old shared `~/.tubematic-agent` is refused on purpose: wiping it would delete the logs and any other agent's workspace |
| `--uninstall-agent` says the agent "is the default agent" | Make another agent the default on the dashboard's Settings → Agents tab first. The last installed agent can always be uninstalled |
| `poll.log` says "Ignoring --agent-run-path, --agent-binary" | The crontab predates per-video agents. Harmless; `python onboard.py --step cron` rewrites it |
| `poll.log` says "Already running" | A previous tick is still holding the lock |

**No new topics are appearing.** Research is gated by two independent caps that must both pass:
`proposed_count` below `research_pending_cap`, and `research_runs_today` below
`max_research_runs_per_day`. `GET /pipeline/status` reports all four numbers. Also check
`active_strategies` — mining is left out of it while no Gemini key is stored, and an install whose
only strategy was mining then runs no research at all — and whether the curriculum seed domain is
paused. A paused seed also refuses
trending and mining topics that match it; the agent skips those rather than filing them elsewhere.
A domain marked **EXPIRED** on the Topics page has reached its topic cap and is refused the same
way; raise the cap on its row (up to 750). See [Topic cap](../developer/02-pipeline.md#topic-cap).

---

## The agent has no Tubematic tools

Run `/tubematic-register-mcp`, then **restart the agent session** — tool schemas are read once at
session start.

If the tools exist but a signature is wrong, the container was rebuilt while your session was open.
Same fix.

If the agent's MCP status shows a `401`, or OpenCode says "needs authentication", its registration
is not sending the MCP token: it predates 2.0.0, the install was moved, or
`~/.tubematic-data/secrets/mcp_token` cannot be read. Re-running `python onboard.py --install-agent
<agent>` registers it correctly; `python upgrade.py --check` reports which agents are affected.

If registration itself fails, the MCP server is not up. Check **`tubematic-mcp`**, not
`tubematic-api` — they are separate containers, so a healthy Flask says nothing about whether the
tools are reachable:

```bash
docker compose ps
curl -fs http://localhost:4100/health
docker compose logs tubematic-mcp
```

## The agent has stale skills

Skills are markdown deployed when the agent is installed, not read from this repository at runtime.
Editing a skill file changes nothing until you redeploy, which is re-running the install:

```bash
python onboard.py --install-agent claude   # or: --install-agent codex / opencode
```

Then restart the session. For Claude Code under user scope, skills go to **both** `~/.claude/skills/`
and the agent workspace — if only one was updated, half the pipeline still sees the old version.
Codex has a single location, `~/.codex/skills/`, and OpenCode `~/.config/opencode/skills/`.
Whichever agents are installed, redeploy each one: a skill edit reaches only the agent whose
install you re-ran.

---

## Renders

**Nothing is being rendered.** Check the worker is running and read its log — render output goes
there and nowhere else:

```bash
docker compose ps tubematic-renderer
docker compose logs -f tubematic-renderer
```

**`validate_job` fails.**

| Error | Cause |
|---|---|
| `Cannot find module '../installed/…'` | Wrong import depth. Generated scenes are two levels down — use `../../` |
| A TypeScript error in a file you did not touch | The typecheck covers the **whole project**. A broken scene from any video blocks every render |
| Frame count mismatch | `scene-config.totalFrames` must equal `timeline.totalFrames`. Usually a re-voice that changed the audio length |
| An image path does not resolve | Image props must be `/public/<video_id>/images/…` and the file must exist |
| `missing job file(s)` | The named file is not in `/jobs/<video_id>/`, or its path column is still empty because that step never finished. The worker looks only there — it derives the location from the id and ignores the stored path, so host paths in the database are harmless. A script driving the MCP server from a host shell must write into the same jobs volume (`~/.tubematic-data/jobs`, the default outside a container) |
| `Render refused, moved to FAILED` | The video's id, or its project's id, cannot be used as a file path — for example a project id of `..`, which would put the render outside `/output_videos`. New ids are checked when created, so this means a row from before that check. No route changes a video's project, so the fix is an edit to the row in the database, or deleting the video |

**A video bounces between `RENDER_QUEUED` and `RENDERING`.** It is timing out. Raise
`render_timeout_secs`, or look for a scene doing something expensive — a full-bleed blur across
hundreds of frames is the classic case.

**A video reached `FAILED`.** `render_fail_count` exceeded `max_render_retries` (default 1, so the
*second* failure escalates). Read the comment thread for the captured error. Note that a container
restart mid-render counts as a failure, so two restarts across one video's life will escalate it.

**A scene renders as a flat dark rectangle.** Its dynamic import failed. `GeneratedScene` logs to the
console and continues rather than failing the render, so the video comes back with a silent gap.
`validate_job` is the layer that should have caught it — check whether it was run.

---

## AI review

**Every video passes review, always.** Review may be failing open. It is designed to, so that a
broken reviewer cannot wedge the pipeline — but that means an error looks like a pass. Search
`gemini_feedback` for the prefix `AI review did not run:`.

**A video loops on trivial suggestions.** Any finding routes to `REVISION_REQUESTED`, including a
suggestion with no must-fix item. `ai_review_max_loops` caps it; the review at the cap still runs but
is force-accepted.

**Review reports a mispronunciation on a word you deliberately respelled.** The reviewer is sent both
the authored script and the spoken `tts_text` precisely so this does not happen. If `tts_text` is
empty on the video, the comparison has nothing to work with.

**Gemini returns `429`.** Two different failures share that code:

- `limit: 0` in the body means **this project has no quota for this model** — not that you used it
  up. The accompanying "retry in N seconds" is misleading; retrying a zero ceiling never succeeds.
- *"Your prepayment credits are depleted"* is a real zero balance. The distinguishing symptom is that
  token counting and file listing keep returning `200` while generation and uploads return `429`.

The body that tells them apart is in the MCP log. Filter the Logs page to level `error`: the failed
`mine_youtube_topics` call's line quotes Gemini's reply. For AI review the reply is in the video's
review comment instead — review fails open, so the video still reaches `VIDEO_READY`. A paid chat
subscription is an unrelated product and grants no API quota.

**Every scene image fails.** Scene images come from OpenAI only, so check the OpenAI key first
(Settings → API Keys). An error naming a project and a model means the key's OpenAI project has no
access to that model — OpenAI grants model access per project; use a key from a project that has it,
or choose the other model under Settings → Images. While images keep failing, the poller retries the
video in a fresh agent session that fails the same way and is billed anyway, until three sessions in
a row have moved it nowhere and it is flagged STUCK. Act on the first failure you see.

---

## Voice

**`No default voice set`.** The roster is empty, or the stored default is not on it. Readers blank an
off-roster default rather than erroring, so this surfaces at generation time.

**A video errors instead of falling back to the default voice.** That is intentional. A video naming
a voice no longer on the roster errors *before* spending money rather than silently voicing in the
wrong voice.

**"This script can't be voiced with that voice", or a voice greyed out at approval.** The script's
pronunciation or pause markup was written for another model — for example an `<ipa>` tag, which only
`eleven_v3` and `eleven_v4` understand, against a voice on `eleven_multilingual_v2`. It also happens to the video's
own voice if that voice's model was changed in Settings after the script was written. Keep a voice
that can speak it, or request a revision so the agent rewrites the markup for the voice you want.
Nothing is charged. Next time, pick a voice on another model when approving the topic, before the
script is written for it. See [The model follows the voice](../developer/08-scripting-and-voice.md#the-model-follows-the-voice).

**`ELEVENLABS_API_KEY not set` from a host script.** Keys live in the settings table, not the
environment. A standalone script must read them from the database.

**A video has a "Stuck in VOICING" comment.** The render worker posts it when a video has sat in
`VOICING` for three poll intervals without being voiced. It also logs an error and, if a Discord
webhook is set, sends an alert. Every tick picks a `VOICING` video up, so a video still there means
something keeps failing. The poll log says what. There are three usual causes:

- `generate_voice` is erroring, for example because of a missing key or an off-roster voice. The
  agent comments the error on the video.
- The poller is not running. See [Nothing is happening](#nothing-is-happening).
- The agent is declining to voice a script the human already approved, which older skills could
  cause. See [The agent has stale skills](#the-agent-has-stale-skills).

Once the cause is fixed, the poller voices the video on its next pass — or, if three failed attempts
have flagged it STUCK, once you press **Retry agent**. The alert fires once each time a video
enters `VOICING`, not on every pass. It stays silent while the pipeline is paused, and for three
poll intervals after resuming, so a video approved during a pause gets a fair chance first.

**A pasted key is refused as malformed.** Onboarding checks every key before sending it, and refuses
one holding a character that cannot go in an HTTP header — a trailing newline or a non-ASCII
character picked up by a terminal copy, typically. The message names the problem; re-type or
re-copy the key.

---

## Dashboard

**"Upstream unreachable".** The proxy could not reach Flask. Check `tubematic-api` and `RENDERER_URL`.

**Video will not play.** The stream route serves only `.mp4` and `.mp3` files that really live
under `/output_videos`, and answers `404` for anything else: a path that escapes it, a file that is
not there, a symlink (or a symlinked directory) whose target is outside it, a directory, and any
other extension. The player asks for `/stream/<project_id>/<video id>.mp4` whatever `video_path`
says, so confirm a regular file exists at `/output_videos/<project_id>/<video id>.mp4` inside the
container (`default_proj` for a video with no domain), not a link to one elsewhere. A `416` means the browser asked for a byte range past
the end of the file, which usually means the file was replaced while it was open: reload the page.
A `401` instead means the session expired: sign in again.

**Forgot the dashboard password.** On the host: `python onboard.py --set-password`. It signs every
browser out.

**"Too many failed attempts" on the login page.** The install-wide backoff after five wrong
passwords, up to 15 minutes. Wait it out, or restart the API (`docker compose restart
tubematic-api`) to clear it.

**"The API refused the dashboard's token".** The dashboard and the API are using different
`api_token` values — usually after a rotation the API was not restarted for. `docker compose restart
tubematic-api tubematic-dashboard`.

**Timestamps look wrong.** The dashboard displays the **host's** timezone, fetched from
`GET /pipeline/status`, not the browser's. If it degraded to UTC, that endpoint failed or returned an
invalid zone.

**An action returns "Status conflict — action already taken".** Working as intended: the video moved
since the page last polled. Refresh.

**Approving or revising says an agent "is uninstalled, so no work can be handed to it".** The agent
picked for the video was uninstalled after the page loaded its agent list. Reload the page and pick
a live agent, or re-install that one with `python onboard.py --install-agent <agent>`.

---

## Remote access

Setting it up is covered in [Remote Access](09-remote-access.md).

**The login page loads over plain HTTP from another machine.** It works, but the password and the
cookie cross the network readable. On a source install, port 3000 is open on every interface. Put
Twingate or an HTTPS proxy in front, and bind the port to `127.0.0.1` — see
[Why it needs setting up](09-remote-access.md#why-it-needs-setting-up).

**Behind an HTTPS proxy, the `tm_session` cookie is not marked Secure.** The proxy is not sending
`X-Forwarded-Proto: https`. nginx never does unless told to; add
`proxy_set_header X-Forwarded-Proto $scheme;` ([nginx](09-remote-access.md#nginx)).

**Saves and approvals fail with `403 cross-site request refused`.** The browser did not mark the
request as coming from the dashboard's own page. Open the dashboard at the proxy's address itself,
not inside a frame or from another site's page, and check that nothing between the browser and the
proxy rewrites requests.

**The browser warns about the certificate (Caddy `tls internal`).** That device does not trust
Caddy's root certificate yet. Install it there — see
[On a private network](09-remote-access.md#on-a-private-network).

**Twingate connects, but the dashboard address does not load.** Check, in this order: the Connector
runs on the Tubematic host itself; a Docker Connector uses host networking; the Resource allows
TCP 3000; and you are opening the Resource's alias, not `127.0.0.1`. See
[Twingate](09-remote-access.md#twingate).

---

## Publishing

**The Publish button is not there.** Publishing is off by default. Enable `publishing_enabled` and
set `postforme_api_key`. The button only appears at `VIDEO_APPROVED`, never at `VIDEO_READY` —
approving a video and publishing it are two separate decisions.

**Every publishing route returns `503`.** Same cause: publishing disabled, or no key. Both are
checked before any outbound call.

**A publish returned `502` with `"reconciling": true`.** The post-creation call was ambiguous — it
may have succeeded after the response was lost. **Do not retry.** The video stays `PUBLISHING` and
the worker reconciles it by looking the post up by the video's own id: at once if the post exists,
or it fails the video after the one-hour publish deadline if it does not.

**A publish failed with "media upload took longer than 30 minutes".** The upload is capped so that a
publish request always finishes before the worker's one-hour publishing deadline. Nothing was
posted, and the video is back at `VIDEO_APPROVED`, so publish it again once the connection to the
storage host is faster.

**A video shows `FAILED` but it is live on the platforms.** Open it and press **Retry publishing**.
The server asks postforme first and never posts twice: a live post is adopted and the video settles
to `PUBLISHED` with its post links. If nothing is live, the video goes back to `VIDEO_APPROVED` and
the Publish dialog opens. The button is offered only for a video that failed while publishing, so a
render failure shows Delete only.

**A video reached `PUBLISHED` but one destination shows an error.** Working as intended. There is no
un-publish, so a video live anywhere genuinely is published. `FAILED` is reserved for the case where
every destination failed.

**A video is stuck at `PUBLISHING`.** The worker settles it on each tick, so check the worker is
running. After one hour, targets with no result are force-failed by the wall-clock backstop. A
publish whose upload is still running also shows `PUBLISHING`, and the worker deliberately leaves
it alone until that hour is up.

**A scheduled post is still `SCHEDULED` after its time.** The worker moves it to `PUBLISHING` on its
next tick once the time has passed, but only while publishing is enabled — with publishing off, or the
key removed, nothing is polled. postforme sends the post itself, so it goes out on time either way;
the video catches up when publishing is back on. postforme checks for due posts about every two
minutes, so a post a couple of minutes late is normal.

**Cancel schedule says the post can no longer be cancelled.** postforme has already started sending
it. The video settles to `PUBLISHED` or `FAILED` like any other publish.

**A schedule is refused.** The time must be at least 5 minutes and at most 365 days ahead, in the zone
picked in the dialog. A time the clocks skip for daylight saving (2:30 on a spring-forward night)
does not exist and is refused rather than shifted; pick another.

**Analytics are empty.** Metrics poll hourly, and only for videos with a `PUBLISHED` publication.
`POST /analytics/refresh` forces a pass now. An account showing `NO ANALYTICS` on the Socials page
lacks the feed permission upstream. A `—` means the platform did not report that metric; it is not
a zero.

**One platform's figures are `—` forever, and nothing says why.** This is almost always an account
connected to postforme **without the `feeds` permission**, which is postforme's default. The account
publishes perfectly; only analytics are missing. It is worth checking even when the Socials page
shows no `NO ANALYTICS` badge — on Instagram the feed request succeeds and simply returns empty
metrics, so there is no rejection for that badge to detect. A refresh will cheerfully report
snapshots captured, because rows *were* written; they just hold nothing. Confirm by asking postforme
for the account's feed with metrics expanded: if the posts come back and every `metrics` object is
empty, the grant is missing. Fixing it means reconnecting the account with `feeds` granted — see
[Connecting accounts](06-publishing.md#connecting-accounts). On Instagram, also confirm the account
is Business or Creator; insights do not exist on a Personal account.

---

## Notifications

**Nothing arrives at all.** Notifications need two things set, and both default to off: a
`discord_webhook_url` and at least one of the three triggers, all on Settings → Notifications. They
are also sent by the render worker, so that container has to be running.

**A message is late.** Expected. The sweep runs at the top of the worker's tick, so it lands within
a tick when the worker is idle and once the current render finishes when it is not.

**Topics announced in two messages instead of one.** The bundle is a debounce, not a guarantee. It
waits for the newest proposal to be still for a settle window; a research run that spaces its
proposals further apart than that produces two messages.

**Saving the webhook URL returned `400`.** Either the URL is not webhook-shaped, or Discord
answered `401 Invalid Webhook Token` / `404 Unknown Webhook` — the webhook was deleted or the token
is wrong. Recreate it in the channel's Integrations → Webhooks and paste the new URL. A timeout or a
`5xx` does *not* reject the save, so a `400` here means Discord actively said no.

**Messages arrive with no links.** `dashboard_base_url` is blank. There is no default to guess — the
container cannot know what address you reach it by.

**A checkpoint was announced twice.** Each *arrival* announces, so a video routed back to a
checkpoint after a revision round is announced again. That is deliberate. Editing a video in place
while it sits at a checkpoint — changing the script profile on a proposed topic, say — also counts
as a new arrival and re-announces that one video. A rare duplicate is the deliberate trade for never
silently missing a revision round.

**Nothing arrived for videos that were already waiting when I switched a trigger on.** Also
deliberate. Enabling a trigger starts announcing from that moment rather than replaying everything
parked while it was off.

**Nothing arrived, and the worker log shows a Discord failure.** The send is retried on the next
tick, because the marker that records what has been announced only advances on success. A persistent
failure means the webhook is gone — re-save the URL to have it checked.

---

## Data and disk

**The database seems empty after an upgrade.** Pipeline data lives at `~/.tubematic-data/`, outside
the checkout. If your install predates that move, its data is still in the old repository-relative
directory and must be moved across **before** onboarding runs, or you start from an empty tree.

**Compose comes up on an empty data tree.** The volumes' recorded device paths no longer match.
Compose prompts on a device change and answers "no" non-interactively. Start the stack with
`python3 scripts/service.py start`, which reconciles them, rather than a bare `docker compose up -d`.

**`entrypoint: … is root-owned — falling back to world-writable`.** Something created the data
directory before onboarding did — usually a bare `docker compose up`. Fix the ownership on the host.

**Disk filling up.** Rendered video and `node_modules` dominate. Measure with `df -h /`, not
`docker system df`, whose per-image sizes double-count shared layers. With the containerd
snapshotter, image layers are not under `/var/lib/docker` at all.

Published videos reclaim their own space: the
[retention sweep](../developer/11-rendering-and-review.md#retention) deletes their mp4 and job directory
`retention_days` after publishing. Failed and rejected videos keep theirs unless you set
`unpublished_retention_days`. **Settings → Retention** shows how much disk they hold.
`python scripts/cleanup_jobs.py` reclaims job directories by hand, for anything else. Leftover
`/tmp/tubematic-audit-bundle-*` directories inside the API container mean text audits have been
timing out. The render worker never cleans its own staging directory; recreating the container does.

**A video vanished from the board, or its player is gone.** It was archived: someone pressed Delete,
or the retention sweep removed its files: published more than `retention_days` ago, or failed or
rejected more than `unpublished_retention_days` ago. It is on the Archive page with its record, links
and analytics; its status is whatever it was before. The mp4 is not recoverable, and an archived
failed video can no longer be retried. Set the key to 0 to stop its sweep.

---

## Reading the trail

Every failure the pipeline handles leaves a comment on the video, and the AI review's full text is in
`videos.gemini_feedback`. Between those two, most questions answer themselves:

```bash
sqlite3 ~/.tubematic-data/data/tubematic.db \
  "SELECT created_at, author, content FROM comments WHERE video_id='vid_…' ORDER BY id;"
```

Or open the video on the dashboard, where the same thread is the Comments tab.

### Logs

Comments record what the pipeline *decided*. The structured logs record what it *did*, including the
paths that never reach a comment — a rejected MCP call, a request that 500'd, a cron tick that found
nothing.

Every service writes one JSONL file per day to `~/.tubematic-data/logs`, mounted `/logs` in the
containers:

```
api.2026-09-06.jsonl        Flask — one record per request, with a request_id
mcp.2026-09-06.jsonl        one record per tool call, with its duration and outcome
renderer.2026-09-06.jsonl   the render worker, tagged with video_id
poll.2026-09-06.jsonl       the cron poller, which runs on the host
```

Read them on the dashboard's **Logs** page — filter by service, by minimum level (`warning` also
shows errors), or by free text. A single video's trail is the **Logs tab inside the video modal**,
which spans every service rather than just the renderer.

From a shell, they are ordinary files:

```bash
grep '"level":"error"' ~/.tubematic-data/logs/*.jsonl | tail -20
```

**A tool call's level says whether it failed, and why.** Most MCP tools fail by *returning* an error
to the agent rather than crashing, so each call's one record carries an `outcome`, and its level
follows the cause:

| Level | `outcome` | Meaning |
|---|---|---|
| `error` | `error` | A paid provider call failed: ElevenLabs, Gemini or OpenAI answered with an error, sent a `200` with nothing usable in it, or never answered at all |
| `error` | `partial` | The tool finished, but a provider call inside it failed. Mining carries on past a failed video URL |
| `error` | `exception` | The tool itself crashed |
| `warning` | `error` | The tool refused before any paid call, e.g. a paused or expired domain, a frozen field or an empty prompt. This is the agent being told no, not something broken |
| `info` | `ok` | Success |

A provider failure's line names the provider, model, HTTP status (or "no response") and the
provider's reply, truncated and with credentials removed. For mining it also names the video URL.
The same details sit in the record's `provider_service`, `provider_model`, `provider_operation`,
`provider_status`, `provider_body` and `provider_detail` fields, for `jq`. Filtering the Logs page
to level `error` therefore shows the incidents, not the refusals. To see refusals as well, search
for `outcome`.

Three things worth knowing before you go looking:

- **Container stdout still works.** `docker compose logs -f tubematic-renderer` is unchanged; the
  JSONL files are an additional sink, not a replacement.
- **A missing file is not an error.** A service degrades to stdout-only if `/logs` is unwritable, so
  an empty Logs page for one service usually means that container is running from an image built
  before the mount existed. Rebuild it.
- **No `poll` entries, while everything else shows.** The poller runs from cron as your user, not
  as root in a container, so it needs write access to `~/.tubematic-data/logs`. If that directory is
  root-owned, every tick warns in `~/.tubematic-agent/logs/poll.log` with `Cannot write …`. Restart
  the stack, whose API and MCP containers make the directory group-writable for your user at
  startup, or run `sudo chown "$USER:$USER" ~/.tubematic-data/logs`. Entries appear from the next
  tick on; missed ticks are not filled in. `python onboard.py` also warns about any data directory
  you cannot write.
- **Retention deletes old files.** `log_retention_days` (default 14) is applied when a service starts
  and once a day after that — so unlike every other setting, a change takes effect at the next pass
  rather than the next read.

Credentials are stripped before anything is written, on two axes: known header and provider key
shapes, and the literal values stored in the settings table. That keeps a key out of a log file; it
does not make a log safe to publish. `poll.log` and container stdout are not redacted at all, and
none of them remove emails, paths or your own topics. To share logs, use the diagnostics report
below rather than the raw files.

---

## Reporting a bug

If something looks like a bug in Tubematic itself rather than a setting, a report with the version,
the container state and the log lines around the failure is what gets it fixed. Collect them with:

```bash
cd <your Tubematic install directory>
python3 scripts/collect_diagnostics.py --video vid_…   # --video is optional
```

It writes `report.md` to a new `~/tubematic-diagnostics-<time>/` directory, readable only by you,
and prints the path. Options:

- `--since <hours>` (default 24) for an older problem. It covers every log, the poller's dated
  older files included.
- `--lines <n>` (default 200), the most lines kept per log section.
- `--include-content` to add your topics, scripts, comments, preferences and lexicon, which are
  left out by default.
- `--out <dir>` to write somewhere else. It never writes inside `~/.tubematic-data` and never
  replaces an existing `report.md`.

It reads the install and never changes it: the database is opened read-only and nothing is sent
anywhere.

**What it removes, by code, before you see the report:**

- every API key, webhook URL and service token Tubematic has stored, and the password hash —
  matched by their real values, wherever they appear
- anything shaped like a key, a bearer or basic credential, or a cookie
- email addresses, IP addresses (except `127.0.0.1`), your host name, user name and home directory
- your postforme account ids, ElevenLabs voice ids (including voices since removed from your
  roster that a video or a domain still uses) and social handles, replaced by a short hash so lines about the same account still match
  up
- unless you pass `--include-content`, wherever a log quotes them exactly, whole or a line or
  sentence at a time (anything under 12 characters only as a whole word, so a short title does
  not cut into longer words, and anything under 4 characters not at all):
  - your videos' titles, topics, scripts, AI review feedback and publish titles and descriptions
  - the comments you wrote. Comments from Tubematic and the agent are kept: they carry the errors
    the report is for.
  - domain names, descriptions and ids (an id is usually a slug of the domain's subject)
  - your mining sources, your preferences and your pronunciation lexicon

If any stored secret survives all of that, the collector writes **nothing** and says so, without
showing the value. Please report that too, without the report.

**What it cannot remove** is anything it does not recognise: a credential in an unfamiliar shape,
a topic quoted in other words, or the name of a person or company. The report ends with a short
checklist — read it, and the report, before posting. GitHub issues are public.

**Filing it.** The end of the report gives the new-issue link and a ready `gh issue create` command.
The issue form asks for the same fields the report provides.

**Letting an agent help.** The `tubematic-troubleshooting` skill walks through a problem with you:
it asks what you see, follows this page, runs the collector (or asks you to), checks the report a
second time, and drafts the issue in the form's layout. It reads logs only through that report —
never the database, the secrets directory or a raw log file, since whatever an agent reads is sent to
its model provider. It never changes the pipeline without asking, and never posts anything — filing
is always yours. No agent can start it on its own, so a scheduled run never will. Ask for it by name:

| Agent | How |
|---|---|
| Claude Code | `/tubematic-troubleshooting` |
| Codex | `$tubematic-troubleshooting` |
| OpenCode | "Use the tubematic-troubleshooting skill." |

How the skill is kept explicit-only on each agent is in
[The agent layer](../developer/07-agent-layer.md#the-troubleshooting-skill).
