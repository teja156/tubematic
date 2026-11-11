# HTTP API

The Pipeline API is a Flask app in `renderer/api/`. The dashboard calls it through its proxy, the
poller (`scripts/poll.py`) reads its work from it, and external tooling should use it too.

| | |
|---|---|
| Container | `tubematic-api` |
| Port | 4000 |
| Prefix | None. Every route is at the app root |
| Content type | JSON in, JSON out |
| Authentication | `Authorization: Bearer <api_token>` on every route except the two health probes |
| Code | `renderer/api/server.py`, `renderer/api/pipeline.py::create_pipeline_blueprint`, `renderer/api/api_auth.py` |

The same process serves the [render gateway](#the-render-gateway), a separate app on HTTPS port
4443 that only renderers call.

## Route index

### Health and login routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/health`](#health) | Liveness probe, no token |
| `GET` | [`/render/health`](#health) | Chromium check, no token |
| `POST` | [`/auth/login`](#post-authlogin) | Check the dashboard password |

### Video routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/stats`](#get-stats) | Count videos per status |
| `GET` | [`/videos`](#get-videos) | List videos, with filters |
| `GET` | [`/videos/actionable`](#get-videosactionable) | Videos waiting for a human |
| `GET` | [`/videos/workable`](#get-videosworkable) | Videos an agent may work |
| `GET` | [`/videos/<video_id>`](#get-videosvideo_id) | One video with its comments |
| `POST` | [`/videos`](#post-videos) | File a proposed topic |
| `POST` | [`/videos/manual`](#post-videosmanual) | Create a video by hand |
| `PATCH` | [`/videos/<video_id>`](#patch-videosvideo_id) | Change status and editable fields |
| `POST` | [`/videos/<video_id>/agent-outcome`](#post-videosvideo_idagent-outcome) | Report a finished agent session |
| `POST` | [`/videos/<video_id>/agent-retry`](#post-videosvideo_idagent-retry) | Release a stuck video |
| `POST` | [`/videos/<video_id>/switch-style`](#post-videosvideo_idswitch-style) | Take Auto's runner-up style at `SCRIPT_READY` |
| `POST` | [`/videos/<video_id>/comments`](#post-videosvideo_idcomments) | Add a comment |
| `DELETE` | [`/videos/<video_id>`](#delete-videosvideo_id) | Delete files, archive the row |
| `GET` | [`/retention/backlog`](#get-retentionbacklog) | Size of unpublished leftovers |
| `GET` | [`/storage`](#get-storage) | Disk space Tubematic uses |

### Project routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/projects`](#get-projects) | List domains |
| `POST` | [`/projects`](#post-projects) | Create or replace a domain |
| `POST` | [`/projects/<project_id>/status`](#post-projectsproject_idstatus) | Pause or resume a domain |

### Settings and voice routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/settings`](#get-settings) | Read every setting, masked |
| `POST` | [`/settings`](#post-settings) | Write a subset of settings |
| `POST` | [`/voices/<voice_id>/preview`](#post-voicesvoice_idpreview) | Generate or replay a sample |
| `GET` | [`/visual-styles`](#get-visual-styles) | Every visual style, and whether this install can make it |

### Research routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/research/strategies`](#research-modes) | Read active research modes |
| `POST` | [`/research/strategies`](#research-modes) | Set active research modes |
| `GET` | [`/research/mining-sources`](#mining-sources) | Read the mining URL list |
| `POST` | [`/research/mining-sources`](#mining-sources) | Replace the mining URL list |
| `POST` | [`/research/record-run`](#post-researchrecord-run) | Count a research run |

### Agent routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/agents`](#get-agents) | List installed agents |
| `PATCH` | [`/agents/<agent_id>`](#patch-agentsagent_id) | Set default, weight, model, effort |

### Script profile routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/script-profiles`](#reading-script-profiles) | List profiles |
| `GET` | [`/script-profiles/pending`](#reading-script-profiles) | Profiles waiting for an agent |
| `GET` | [`/script-profiles/<id>`](#reading-script-profiles) | One profile with its markdown |
| `POST` | [`/script-profiles`](#post-script-profiles) | Create from YouTube URLs |
| `DELETE` | [`/script-profiles/<id>`](#delete-script-profilesid) | Archive a profile |
| `POST` | [`/script-profiles/<id>/record-attempt`](#post-script-profilesidrecord-attempt) | Claim a build attempt |

### Mascot routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/mascots`](#reading-mascots) | List mascots |
| `GET` | [`/mascots/pending`](#reading-mascots) | Mascots waiting for an agent |
| `GET` | [`/mascots/<id>`](#reading-mascots) | One mascot with its versions |
| `GET` | [`/mascots/<id>/versions/<version>/sheets/<sheet>`](#reading-mascots) | One model-sheet image |
| `POST` | [`/mascots`](#post-mascots) | Request a new mascot |
| `POST` | [`/mascots/<id>/approve`](#post-mascotsidapprove) | Approve the draft version |
| `POST` | [`/mascots/<id>/request-changes`](#post-mascotsidrequest-changes) | Ask for a new draft |
| `POST` | [`/mascots/<id>/record-attempt`](#post-mascotsidrecord-attempt) | Claim a build attempt |
| `DELETE` | [`/mascots/<id>`](#delete-mascotsid) | Archive a mascot |

### Publishing and analytics routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/publishing/accounts`](#accounts) | List connected social accounts |
| `POST` | [`/publishing/accounts`](#accounts) | Replace the account allowlist |
| `POST` | [`/publishing/accounts/connect`](#accounts) | Get an account-connect URL |
| `GET` | [`/videos/<video_id>/publications`](#publications-and-prefill) | Where a video was posted |
| `POST` | [`/videos/<video_id>/publish-prefill`](#publications-and-prefill) | Starting title and description |
| `POST` | [`/videos/<video_id>/publish`](#post-videosvideo_idpublish) | Publish or schedule a video |
| `POST` | [`/videos/<video_id>/publish/retry`](#post-videosvideo_idpublishretry) | Recover a failed publish |
| `POST` | [`/videos/<video_id>/schedule/cancel`](#post-videosvideo_idschedulecancel) | Cancel a scheduled post |
| `GET` | [`/analytics`](#analytics) | Read stored performance figures |
| `POST` | [`/analytics/refresh`](#analytics) | Poll performance figures now |
| `GET` | [`/autopilot`](#auto-pilot) | Read the Auto Pilot configuration |
| `POST` | [`/autopilot`](#auto-pilot) | Replace the Auto Pilot configuration |

### Cost routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/videos/<video_id>/costs`](#get-videosvideo_idcosts) | One video's cost breakdown |
| `GET` | [`/usage/summary`](#get-usagesummary) | Spend over a date range |
| `POST` | [`/usage/agent-session`](#post-usageagent-session) | Record an agent session's usage |
| `GET` | [`/prices`](#prices) | Model rates and sync state |
| `POST` | [`/prices/sync`](#prices) | Run the price sync |
| `POST` | [`/prices/override`](#prices) | Set a manual rate |
| `DELETE` | [`/prices/override`](#prices) | Remove a manual rate |

### Renderer routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | [`/renderers`](#get-renderers) | List renderers and gateway address |
| `POST` | [`/renderers/enrollments`](#post-renderersenrollments) | Issue a one-time enrollment token |
| `PATCH` | [`/renderers/<id>`](#patch-renderersid) | Rename, enable or disable |
| `DELETE` | [`/renderers/<id>`](#delete-renderersid) | Remove a remote renderer |
| `POST` | [`/renderers/<id>/gpu-test`](#post-renderersidgpu-test) | Request a renderer GPU test |
| `GET` | [`/render/gpu`](#gpu-rendering) | Built-in renderer's GPU status |
| `POST` | [`/render/gpu/test`](#gpu-rendering) | Request the built-in GPU test |

### Pipeline control and log routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | [`/pipeline/pause`](#post-pipelinepause) | Pause or resume the pipeline |
| `GET` | [`/pipeline/status`](#get-pipelinestatus) | Counts, caps, version, time zone |
| `GET` | [`/logs`](#get-logs) | Read structured log records |

## Conventions

### Authentication

Every route except `GET /health` and `GET /render/health` needs the API token, the content of
`~/.tubematic-data/secrets/api_token`. A request without it, or with a wrong one, gets
`401 {"error": "unauthorized"}`, including a request for a path that does not exist.

```bash
curl -H "Authorization: Bearer $(cat ~/.tubematic-data/secrets/api_token)" http://localhost:4000/settings
```

`api_auth.py::install_auth` installs the check on the app, so it covers every blueprint and any
route added later. It exempts the two health routes by endpoint name (`OPEN_ENDPOINTS`), so a path
that starts with `/health` is not open. `server.py` raises at start when the token file is missing
or empty. Token creation and rotation are in [Infrastructure](16-infrastructure.md#authentication).

A renderer credential does not work on port 4000, and the API token does not work on the render
gateway.

### Requests and errors

- An error is `{"error": "<message>"}` with a 4xx or 5xx status. Some routes add fields, such as
  `current`, `expected`, `voice_conflict` or `failures`.
- Routes differ on unknown body keys. `PATCH /videos/<video_id>` drops them. `POST /settings` and
  `PATCH /agents/<agent_id>` answer `400`.
- An unhandled exception returns HTML (see [Known quirks](#known-quirks)).
- `pipeline.py::create_pipeline_blueprint` reads `TUBEMATIC_DB` once, when `server.py` builds the
  app, and uses that path for the life of the process.

### Archived videos

An archived video has had its files deleted and keeps its row (see
[Database](03-database.md#videos)). `/stats`, `/videos/actionable`, `/videos/workable` and the
counts in `/pipeline/status` leave archived videos out. `GET /videos` leaves them out unless asked.
`GET /videos/<video_id>` still serves one. `PATCH` and `agent-retry` answer `409` for one.

### Status sets

`pipeline.py` defines three sets that the routes refer to. `mcp/server.py` and
`dashboard/lib/types.ts` hold copies marked `# Keep in sync`. What each status means is in
[The Pipeline](02-pipeline.md#the-status-sets).

| Set | Members |
|---|---|
| `VALID_VIDEO_STATUSES` | Every value the `status` column may hold |
| `ACTIONABLE_STATUSES` | `TOPIC_PROPOSED`, `SCRIPT_READY`, `VIDEO_READY`: the human checkpoints |
| `WORKABLE_STATUSES` | `TOPIC_APPROVED`, `VOICING`, `VOICE_READY`, `REVISION_REQUESTED`: an agent may act unattended |

`VIDEO_APPROVED` is not workable, because publishing is not agent work.

### Time

The database stores timestamps in UTC and the dashboard displays them in the host's time zone.
The dashboard container has no `/etc/localtime` mount. It reads the zone from two fields of
`GET /pipeline/status`, which `renderer/api/hosttz.py` fills:

- `timezone` is an IANA name, resolved from `TZ`, then `/etc/timezone`, then the `/etc/localtime`
  symlink target, or `null` when all three fail. JavaScript's `Intl.DateTimeFormat` accepts it.
- `timezone_label` is a display string such as `EDT (UTC-04:00)`, computed without tzdata.
  `Intl.DateTimeFormat` throws on it.

## Health

| Route | Response |
|---|---|
| `GET /health` | `200 {"status": "ok"}` |
| `GET /render/health` | Runs `chromium --version`. `200 {"status": "ok", "chromium": "…"}`, or `500 {"status": "error", "detail": "…"}` on a non-zero exit |

A missing Chromium binary, or a run longer than the 10-second timeout, raises to Flask's HTML error
page.

## Dashboard login

### `POST /auth/login`

Checks the dashboard password for the dashboard's login route, which cannot read the database the
hash is stored in. The dashboard sets the session cookie itself on a `200`. Body:
`{"password": "…"}`.

| Status | Cause |
|---|---|
| `200` | `{"ok": true}` |
| `400` | `password` is absent, empty, a non-string or longer than 1024 characters. Refused before hashing |
| `401` | `{"error": "wrong password"}` |
| `429` | Locked after failed attempts, or another login check is running. `Retry-After` gives the wait |
| `503` | No password is set. Run `python3 onboard.py --set-password` |

`api_auth.py::LoginThrottle` holds the backoff in memory:

- The first five failures in a row are free. Each later failure locks login for `2^n` seconds, up
  to 15 minutes. The password is not checked while locked.
- A success resets the count, and so does an API restart.
- The backoff covers the whole install, because every login arrives from the dashboard container
  and a forwarded client address can be forged.
- One password check runs at a time. A login that arrives meanwhile gets `429` with
  `Retry-After: 1` and is not queued, because each scrypt check uses about 32 MiB.

## Videos

### `GET /stats`

`200 {"<STATUS>": <count>}` over every video that is not archived. `{}` for an empty database.

### `GET /videos`

Query parameters `status`, `project_id` and `strategy` are exact matches, combined with AND. Rows
are ordered `created_at DESC`. `archived=only` returns archived rows and `archived=include` returns
both. Any other value of `archived` is a `400`.

List responses clip `gemini_feedback` to 1200 characters and add a `gemini_feedback_truncated`
boolean. Each row also carries `effective_voice_id` and `voice_conflicts` (see
[`GET /videos/<video_id>`](#get-videosvideo_id)).

### `GET /videos/actionable`

Videos at a status in `ACTIONABLE_STATUSES`, oldest `updated_at` first, shaped like `GET /videos`.
The dashboard's Quick Actions list reads it.

### `GET /videos/workable`

Videos at a status in `WORKABLE_STATUSES`, oldest `updated_at` first, as `id`, `topic`, `status`,
`agent_model`, `agent_effort`, `agent_id` and `updated_at`. The poller starts one session per row
(see [The Poller](13-the-poller.md)). A video with `agent_stuck_at` set is left out until a human
acts on it.

### `GET /videos/<video_id>`

The full row plus `comments[]` in chronological order. `gemini_feedback` is not clipped.
`404 {"error": "Video not found"}`.

Three computed fields describe the voice:

| Field | On | Meaning |
|---|---|---|
| `effective_voice_id` | Lists and single videos | The video's `voice_id`, else the install default. `""` when neither is on the roster |
| `voice_conflicts` | Lists and single videos | `{voice_id: reason}` for each roster voice whose model cannot speak the stored script |
| `voice_info` | Single videos | The voice and model for the modal's read-only Voice rows |

`voice_conflicts` comes from the check that makes `PATCH` answer `409` for such a voice, so a
picker that disables these voices agrees with the server. It is empty at `TOPIC_PROPOSED`, because
approving the topic has the script written for the picked voice. See
[The model follows the voice](08-scripting-and-voice.md#the-model-follows-the-voice).

Every response that returns one video carries `voice_info`: this route, `PATCH`, `POST /videos`,
`POST /videos/manual` and `agent-retry`. The lists omit it, because it costs one ledger read per
row.

```json
{"voice_id": "a1", "name": "Adam", "model_id": "eleven_v3", "model_voiced": true}
```

- `voice_id` is the video's own voice, else the install default. It is kept when the voice has
  left the roster, and `name` is then `""`.
- `model_id` is the model of the video's latest voicing call, read from
  [`usage_events`](03-database.md#usage_events-usage_event_videos-and-model_prices), with
  `model_voiced` `true`. The ledger is the source because a voice's model can be edited in Settings
  after the video was voiced.
- At `TOPIC_PROPOSED`, `TOPIC_APPROVED`, `SCRIPT_READY` and `VOICING` the ledger is ignored,
  because a revision can switch the voice before the next voicing. `model_id` is then the voice's
  current roster model and `model_voiced` is `false`. The same applies when the ledger has no
  voicing row. `model_id` is `""` when neither is known.

### `POST /videos`

Files a topic at `TOPIC_PROPOSED`. Required: `topic`, `strategy`, `producibility_score`. Optional:
`id`, `project_id`, `title`, `voice_id`, `visual_style`.

| Status | Cause |
|---|---|
| `201` | The row, at `video_version` 1, plus `warning` if the title was clipped |
| `400` | A validation failure, listed below |
| `409` | `project_id` names a paused domain and `strategy` is not `manual`. See [Domain pause](02-pipeline.md#domain-pause) |
| `409` | `project_id` names a domain at its `topic_cap` and `strategy` is not `manual`. See [Topic cap](02-pipeline.md#topic-cap) |

`400` causes:

- A required field is missing: `{"error": "Missing fields: [...]"}`.
- `id` is not letters, digits, `_` and `-`, starts with `-`, or is longer than 128 characters. The
  id names the video's job directory.
- `project_id` names no domain, `title` is not a string, or `voice_id` is not on the roster.
- `visual_style` is not `auto` or a [style pack](10-scene-authoring.md#style-packs) id.
- `visual_style` is `illustrated`, `under_the_hood` or `case_file_story` and no OpenAI key is stored (the settings row
  or `OPENAI_API_KEY`).
- `visual_style` is `cartoon_3d` and the install-wide GPU `status` is not `working` (see
  [GPU rendering](#gpu-rendering)).

What the route fills in:

- A `title` over 70 characters is clipped at a word boundary, with a `warning`. The create is not
  refused, because a refused create during a research run would lose the topic.
- `agent_id` is dealt from the assignment deck (see [Assignment](07-agent-layer.md#assignment)). An
  `agent_id` in the body is ignored.
- With no `voice_id`, the video takes its domain's `default_voice_id` if that voice is on the
  roster, whatever its `strategy`. Otherwise `voice_id` is `""`, the install default. The voice is
  copied onto the row, so a later change to the domain's default does not change filed videos.
- With no `visual_style`, a `curriculum` video takes its domain's `default_visual_style`, and every
  other video starts at `auto`. An inherited `illustrated` or `cartoon_3d` is stored even when its
  condition does not hold. The approving `PATCH`, which carries `visual_style`, refuses it.
- A `curriculum` video takes its domain's `default_script_profile_id` while that profile is `READY`
  and not archived. Every other video starts with `""`. The route takes no `script_profile_id`.
- `mascot_id` is seeded from the domain's or the install's default mascot, whatever the `strategy`,
  while the GPU `status` is `working` and the style is not `cartoon_3d`
  (`pipeline.py::_seed_mascot`).

The route does not validate `strategy` or `producibility_score`. The MCP server's `create_video`
does.

### `POST /videos/manual`

The dashboard's **New Video** page. Required: `title` (at most 70 characters) and `topic`, both
non-blank. Optional: `approve` (boolean, default `true`), `agent_id`, `agent_model`,
`agent_effort`, `script_profile_id`, `visual_style`, `voice_id`.

`201` returns the row: `strategy` `manual`, `producibility_score` 0, in the domain `manual`, at
`TOPIC_APPROVED`, or at `TOPIC_PROPOSED` with `"approve": false`.

`400` causes:

- `title` or `topic` is missing or blank, `title` is over 70 characters, or `approve` is not a
  boolean.
- A pick is not a string. Only an absent or `null` pick means its default, so `false` and `0` are
  refused.
- A pick fails the rule the same field has on [`PATCH`](#field-rules): the agent, its model and
  effort, the script profile, the voice or the visual style.

How it differs from `POST /videos`:

- It refuses an over-long title, because a person at the form can shorten it.
- It keeps a picked `agent_id`. With none, the agent is dealt from the deck, so the configured
  weights apply. `agent_model` is checked against the agent the video ends up with, and a refused
  model rolls the deal back.
- The video is unscored (see [Where topics come from](02-pipeline.md#where-topics-come-from)).

The first request creates the domain `manual`, named **Manual Videos**, with `INSERT OR IGNORE`,
so a rename on the Projects page is kept. Nothing is written until every field has passed. With no
`voice_id`, the video takes the `manual` domain's `default_voice_id` when it has one on the roster.

### `PATCH /videos/<video_id>`

The main write path. The body may hold any of `status`, `title`, `script`, `video_version`,
`youtube_url`, `gemini_feedback`, `voice_id`, `agent_id`, `agent_model`, `agent_effort`,
`script_profile_id`, `visual_style`, `publish_title`, `publish_description` and `mascot_id`, plus
the optional guard `onlyIfCurrentStatus`.

```json
{"status": "TOPIC_APPROVED", "onlyIfCurrentStatus": "TOPIC_PROPOSED", "visual_style": "auto"}
```

Any other key is dropped, including `tts_text` and `resolved_visual_style`, which only the MCP
server writes. The four job-path columns are the exception: a body with `voice_file_path`,
`timeline_path`, `scene_config_path` or `video_path` gets `400` and nothing is applied, so a caller
that relies on one learns it at once (see [Database](03-database.md#videos)).

| Status | Cause |
|---|---|
| `200` | The updated row plus `comments[]` |
| `400` | A field fails its rule below, a job-path column is present, or the body has no updatable field (`No updatable fields provided`) |
| `404` | Video not found |
| `409` | The video is archived |
| `409` | `script_profile_id`, `visual_style` or `mascot_id` sent while the video is past `TOPIC_PROPOSED` |
| `409` | `agent_id`, `agent_model` or `agent_effort` sent while the video is not at a human checkpoint |
| `409` | An approving `PATCH` while the video's mascot is archived, or while a Cartoon 3D, Under the Hood or Case File Story video keeps a mascot |
| `409` | `{"error": "Status precondition failed", "current", "expected"}` |
| `409` | `{"error", "voice_conflict": true}`: the voice's model cannot speak the stored script |
| `409` | A model was written alone and the video's agent changed while the request was in flight |

#### Field rules

- `status` must be in `VALID_VIDEO_STATUSES`. The route enforces no transition graph, so a client
  can move a video from `TOPIC_PROPOSED` to `PUBLISHED`. The dashboard and the agent's skills hold
  the sequence. A body with `status` also resets `agent_no_progress_count` to 0 and clears
  `agent_stuck_at`.
- `title` must be a string of at most 70 characters. An update is refused where a create is
  clipped.
- `script` must come with both `publish_title` and `publish_description`. Each of those must be a
  non-blank string within its cap (100 and 2000 characters). MCP `update_video` applies the same
  rule (see [Publishing](14-publishing.md#schema)).
- `voice_id` must be on the roster, or `""` for the install default.
- `agent_id` must name a live agent. The video's current agent is accepted even when uninstalled.
  A change sets `agent_model` to `""` in the same `UPDATE`, unless the body also sets
  `agent_model`. `agent_effort` is kept, and the assignment deck is not touched.
- `agent_model` must be a string with no space and no leading `-`. A non-empty value must be one
  of the models of the agent the video will have: the body's `agent_id`, else the video's, else
  the default agent. That agent must be live. `""` means the agent's default model.
- `agent_effort` must be `low`, `medium`, `high`, `xhigh`, `max` or `""` (the agent's own
  `effort`). The levels are the same for every agent.
- `script_profile_id` must be a `READY` profile that is not archived, or `""` for none.
- `visual_style` must be `auto` or a [style pack](10-scene-authoring.md#style-packs) id.
  `illustrated`, `under_the_hood` and `case_file_story` need a stored OpenAI key and `cartoon_3d`
  needs a working GPU.
- `mascot_id` must be a string. A changed value must be a pickable mascot, needs a GPU `status` of
  `working`, and is refused on a video that will be `cartoon_3d`, `under_the_hood` or `case_file_story`. `""` clears
  the mascot.

#### Guards

- `onlyIfCurrentStatus` is part of the `UPDATE … WHERE id = ? AND status = ?` statement, so the
  check and the write are atomic. On a mismatch the route reads the row again and reports the
  current status. Use it for every status change. The dashboard does.
- `script_profile_id`, `visual_style` and `mascot_id` can be written at `TOPIC_PROPOSED` only. The
  three agent fields can be written at a status in `ACTIONABLE_STATUSES` only. Both checks read
  the status before the update, so the `PATCH` that approves a video can carry them. The reasons
  are in [Frozen choices](02-pipeline.md#frozen-choices).
- A write that carries a frozen field is bound to the status the check read, even without
  `onlyIfCurrentStatus`. If the video moved on meanwhile, the answer is
  `409 Status precondition failed` with `expected` set to that status.
- `agent_model` is checked for membership after the freeze check, so a late edit reads as frozen.
  A model sent without `agent_id` is written with `AND agent_id IS ?`, and a concurrent
  reassignment makes it `409`.
- The voice conflict check runs on every request that carries `voice_id`, including an approval
  that re-sends the video's own voice. That voice passes unless its model was changed in Settings
  after the script was written. The check is skipped at `TOPIC_PROPOSED`, and a voice written there
  is bound to that status.
- A `mascot_id` is checked only when it changes, so a client that echoes the stored value is not
  refused for a GPU that has gone since. A switch to `cartoon_3d`, `under_the_hood` or `case_file_story` clears the mascot in the same
  `UPDATE`, and a changed mascot resets `mascot_version` to 0.
- The approving `PATCH` (`TOPIC_PROPOSED` to `TOPIC_APPROVED`) is `409` when the video's mascot has
  been archived, or when the video is Cartoon 3D (by its style or by `resolved_renderer`) and keeps
  a mascot. The `UPDATE` repeats both checks in its `WHERE` clause
  (`tubematic_core/mascots.py::holds_pickable_sql`, `cartoon_mascot_clash_sql`), so an archive or a
  style write that commits in between also gets `409`.
- A `visual_style` different from the stored one clears the record of a style Auto picked
  (`style_pick`, `style_runner_up`, `style_reason`) and the renderer and canvas recorded for the old
  scenes. The same value again keeps them. The mascot checks of the same request judge the video
  by the renderer it will have after the write, so a changed style is not refused for a Cartoon 3D
  renderer it clears. A `status` of `TOPIC_PROPOSED` without a `visual_style`
  returns a style Auto picked to `auto` and clears the record, and on every `auto` video it clears
  the recorded renderer and canvas. Both are SQL fragments in `tubematic_core/visual_styles.py` that `update_video` and
  `set_video_status` also use.

### `POST /videos/<video_id>/switch-style`

Takes the runner-up of the style Auto picked ([How Auto picks a
style](10-scene-authoring.md#how-auto-picks-a-style)). No body. The video must be at
`SCRIPT_READY` and hold a `style_pick` and a `style_runner_up`. The new script is voiced when it is
approved, so on a video that reached `SCRIPT_READY` through a revision after it was voiced, voicing
is paid again.

The route runs as one write transaction (`BEGIN IMMEDIATE`) from its first read to its write, so an
approval, a second switch, a removed key or a GPU probe result waits for it. It clears
`resolved_renderer` and `resolved_visual_style`, which belong to the scenes the new script replaces,
and sets `visual_style` to the runner-up (`auto`
for `scenes`), swaps `style_pick` and `style_runner_up`, sets `style_reason` to say a person
switched it, and moves the video to `TOPIC_APPROVED`. It adds a `human` comment asking the agent to
rewrite the script for the new style. The agent's next session writes a new script, which replaces
the old one. A second switch goes back.

| Status | When |
|---|---|
| `200` | The switch landed. The body is the video |
| `404` | No such video |
| `409` | The video is archived, not at `SCRIPT_READY`, has no Auto pick or no runner-up, the runner-up is not a style any more or this install cannot make it (with the reason), or the video changed while the request was in flight |

### `POST /videos/<video_id>/agent-outcome`

The poller calls it after every pipeline session with
`{"start_status": "<STATUS>", "session_key": "<key>"}`. `session_key` is optional.

This route decides whether the session made progress, because the agent CLIs' exit codes do not
(see [The Poller](13-the-poller.md#success-is-read-from-the-database)). It runs one `UPDATE`:

- If the status differs from `start_status`, `agent_no_progress_count` resets to 0.
- If the status is unchanged, the count goes up by one. At 3 (`AGENT_NO_PROGRESS_CAP`) the route
  stamps `agent_stuck_at` and writes one `agent` comment that explains how to hand the video back.
- `updated_at` is not changed, because it orders the poller's queue and times a stalled `VOICING`.
- A report with the `session_key` of the last counted report (`agent_last_outcome_key`) changes
  nothing and answers `"replayed": true`. This covers a session that two poller processes report.
  A report with no key is counted each time.
- An archived video is reported as it stands and is not counted.

| Status | Cause |
|---|---|
| `200` | `{"status", "count", "stuck", "replayed"}` |
| `400` | `start_status` is missing or invalid, or `session_key` is not a string of 1 to 100 characters |
| `404` | Video not found |

### `POST /videos/<video_id>/agent-retry`

The dashboard's **Retry agent**. It resets `agent_no_progress_count` to 0 and clears
`agent_stuck_at` without changing the status, so the poller picks the video up on its next pass.
`200` with the row plus `comments[]`. `404` for an unknown video. `409` for an archived one.

### `POST /videos/<video_id>/comments`

Body `{author, content}`. `author` defaults to `"human"` and must be `"human"` or `"agent"`.
`201 {"ok": true}`. `400` for an empty `content` or a bad `author`. `404` for an unknown video.

The route does not check the video's status. The dashboard calls it from **Request Revision** (see
[Dashboard](15-dashboard.md#actions)). The MCP server, the worker and the render gateway write
their comments straight to SQLite.

### `DELETE /videos/<video_id>`

Deletes the video's rendered mp4 and its job directory, clears `video_path`, sets `archived_at` and
leaves a `human` comment. The API has no hard delete. The worker's retention sweep runs the same
operation (`pipeline.py::archive_video`).

| Status | Cause |
|---|---|
| `200` | `{"ok": true, "archived_at", "file_errors": []}`. A file that could not be removed is listed, and the row is archived anyway |
| `404` | Video not found |
| `409` | Already archived. The body carries `archived_at` |
| `409` | `{"error", "current"}`: the status is not in `DELETABLE_STATUSES` |

A video cannot be deleted at `VOICING`, `RENDER_QUEUED`, `RENDERING` or `PUBLISHING` (something is
working on it), at `SCHEDULED` (a post will go out), or at `VOICE_READY` or `REVISION_REQUESTED`.
An agent can hold a scene-work claim at the last two, and that claim exists only inside the MCP
process, so the API blocks both statuses for every video. The status check is part of the archiving
`UPDATE`, so it cannot race a render claim.

### `GET /retention/backlog`

What `unpublished_retention_days` would free: every `FAILED` and `TOPIC_REJECTED` video that is not
archived, whatever its age and whether or not the setting is on. Read-only.

```json
{"failed": {"count": 3, "bytes": 1073741824}, "rejected": {"count": 12, "bytes": 0}}
```

`bytes` is the rendered mp4 plus everything under the job directory. A missing or unreadable file
counts as 0. So does a job directory that is not a direct child of the jobs directory, because
video ids are supplied by callers. See [Video retention](04-settings.md#video-retention).

### `GET /storage`

How much disk Tubematic uses, for the disk figure in the dashboard's top bar. Read-only.

```json
{"data": {"measured_at": "2026-11-09T10:00:00Z", "total_bytes": 4400000000,
          "items": [{"key": "videos", "bytes": 3221225472}, {"key": "voice_previews", "bytes": 2097152},
                    {"key": "jobs", "bytes": 1073741824}, {"key": "scenes", "bytes": 5242880},
                    {"key": "database", "bytes": 41943040}, {"key": "mascots", "bytes": 0},
                    {"key": "backups", "bytes": 209715200}, {"key": "logs", "bytes": 62914560}]},
 "host": {"measured_at": "2026-11-09T09:40:12Z",
          "images": {"current_bytes": 5000000000, "old_bytes": 4500000000, "old_count": 2},
          "containers_bytes": 31457280, "build_cache_bytes": 2000000000, "install_bytes": 943718400},
 "total_bytes": 14875176000}
```

| Field | Notes |
|---|---|
| `data` | The API's own mounts, counted the way `du` counts: allocated blocks, a hardlinked file once, symlinks not followed, anything unreadable as 0. Voice previews are left out of `videos`, and mascot sheets out of `database` |
| `host` | The host's snapshot, `~/.tubematic-data/data/disk-usage.json`, read on each request. `null` until one is written, and when the file cannot be read. A figure inside it is `null` when Docker could not be read |
| `host.images.old_bytes` | The sum of each old image's unique size, which is what removing that image alone frees. With two or more old images it is a floor |
| `host.images.old_count` | How many old images there are |
| `total_bytes` | `data.total_bytes` plus the host's images, container layers and install folder. An `images` of `null` adds nothing. The build cache is left out |

- The walk behind `data` is cached for 60 seconds (`pipeline.py::STORAGE_CACHE_SECS`), so open tabs
  that poll the route share one walk of the jobs tree.
- No container has the Docker socket, so the API cannot measure images, the containers' writable
  layers or the install folder. The poller writes the snapshot about hourly, and `upgrade.py` and
  onboarding write it after they change images. See [The poller](13-the-poller.md#disk-usage).
- `old_bytes` is a floor with two or more old images because a layer that only old images share
  appears in none of their unique sizes, and Docker reports no per-layer size to add. `total_bytes`
  is then a floor too, and the dashboard shows both with "≥".
- The build cache stays out of the total because anything else built on the machine shares
  BuildKit's cache.
- Which images are old is decided by `tubematic_core/disk_usage.py::old_images`, the rule
  `upgrade.py` deletes by. See [Old images](16-infrastructure.md#old-images).

## Projects

A project is a domain. Each row carries two derived fields that are not stored: `topic_count`
(every video filed into it, archived and rejected included) and `expired`
(`topic_count >= topic_cap`). See [Topic cap](02-pipeline.md#topic-cap).

### `GET /projects`

Every domain, `created_at DESC`.

### `POST /projects`

Creates a domain or replaces one. `201` with the row. A rule that fails is a `400`.

The route writes every column on each call. A caller that changes one field must send the others
back, or they are reset. An omitted `status` is written as `active`, so clearing
`is_curriculum_seed` on a paused domain also resumes it.

| Field | Rule |
|---|---|
| `name` | Required |
| `id` | A string. Defaults to `proj_<hex>`. A new id must be letters, digits, `_` and `-`, not start with `-`, and be at most 128 characters |
| `description` | A string of at most 2000 code points. Absent or `null` stores `''` |
| `is_curriculum_seed` | Read as a boolean, default `false` |
| `status` | `active` or `paused`. `paused` needs `is_curriculum_seed` |
| `default_visual_style` | `auto`, a style pack id, or `''` for none |
| `default_voice_id` | A roster voice, or `''` for the install default |
| `default_script_profile_id` | A `READY` profile that is not archived, or `''` or `null` for none. Any other non-string, such as `false` or `0`, is refused |
| `default_mascot_id` | `''` (inherit the install default), `none` (no mascot), or a pickable mascot id |
| `topic_cap` | A whole number from 25 to 750. `true`, `"100"` and `100.5` are refused. Absent or `null` means 100 |

Five checks run only when the value changes, because the dashboard re-sends the whole domain on
every edit and a value that became invalid later must not block other edits:

- The `description` length.
- `default_visual_style`: `illustrated`, `under_the_hood` and `case_file_story` need a stored
  OpenAI key and `cartoon_3d` needs a working GPU.
- `default_voice_id` on the roster.
- `default_script_profile_id` being `READY`.
- `default_mascot_id` being pickable, with a working GPU.

The id of an existing domain is not checked, so a domain filed under an older id stays editable.
The id names the domain's output directory. A `topic_cap` below the domain's count is accepted and
expires the domain at once.

### `POST /projects/<project_id>/status`

Body `{status}`. `200` with the row, shaped like `GET /projects`. `400` for a value other than
`active` or `paused`. `404` for an unknown domain. `409` for `paused` on a domain that is not a
curriculum seed. See [Domain pause](02-pipeline.md#domain-pause).

## Settings

How settings are stored, typed and masked is in [Settings internals](04-settings.md). The keys are
`pipeline.py::SETTINGS_SPEC`.

### `GET /settings`

Every declared key, coerced to its type, with `secret` keys masked.

### `POST /settings`

Body: any subset of the declared keys. The response is the full settings object, masked like `GET`.

- An unknown key returns `400 {"error": "Unknown settings: [...]. Valid: [...]"}`.
- The write is atomic. Every value is coerced first (`pipeline.py::_coerce_setting`), and the first
  failure returns `400` with nothing written.
- A `secret` value equal to the mask of the stored value is dropped before coercion, so a client
  can `GET`, edit one field and `POST` the whole object back (see
  [Masking](04-settings.md#masking)). A mask-shaped string posted against an empty key is stored as
  sent.
- A changed `default_mascot_id` must be pickable and needs a working GPU, or the answer is `400`.
- A non-empty `discord_webhook_url` is probed with an unauthenticated `GET`, which sends no
  message. A definitive rejection returns `400`. An unreachable Discord stores the URL.

### `POST /voices/<voice_id>/preview`

Generates an ElevenLabs sample of a roster voice with that voice's own model, or replays a cached
one. An optional body `{"model_id": ...}` names another model, which lets the Settings page play a
model change before it is saved. A missing or non-JSON body is accepted.

| Status | Cause |
|---|---|
| `200` | `{path, cached, credits}`. `credits` is the plan credits the generation spent, 0 for a cache hit |
| `400` | `voice_id` does not match `[A-Za-z0-9_-]+` or is not on the roster, or `model_id` is not a supported model. No ElevenLabs call is made |
| `503` | No ElevenLabs key is configured |
| `502` | ElevenLabs rejected the request, or the call failed |

The cache file name is a hash of the voice id, the model and the sample text. A voice whose model
changes therefore gets a new sample, and the typed `voice_id` does not reach a file path. A cache
hit makes no outbound call.

A generated preview is recorded in the usage ledger with no video, with credits from ElevenLabs'
`character-cost` header. It appears in the Analytics page's Spend tab. See
[Voice previews](08-scripting-and-voice.md#voice-previews).

### `GET /visual-styles`

Returns `{"styles": [...]}`: `auto` first, then every [style pack](10-scene-authoring.md#style-packs)
in its pack order. Each entry has `id`, `label`, `experimental`, `canvas` (the canvas the style fixes,
or `null`), `needs` (`openai_key`, `gpu`), `mascot` (false when the style's videos take no mascot),
and `available` with `unavailable_reason` for this install
now: `needs an OpenAI key`, `needs a working GPU` or `GPU not tested yet`. The dashboard builds its
style pickers from it. The write routes still refuse an unavailable style themselves.

## Research

### Research modes

| Route | Behaviour |
|---|---|
| `GET /research/strategies` | `{"strategies": [...], "mining_available": bool}` from `settings.active_strategies` |
| `POST /research/strategies` | Body `{"strategies": [...]}`. Values must be `curriculum`, `trending` or `mining`, else `400`. Returns `{"strategies": [...]}` |

While no Gemini key is stored, `mining_available` is `false` and `GET` leaves `mining` out. The
stored row is not changed, so adding a key brings mining back. In that state a `POST` that contains
`mining` is a `400` and writes nothing. Any other `POST` keeps a stored `mining`, because the
caller saw the filtered list.

### Mining sources

| Route | Behaviour |
|---|---|
| `GET /research/mining-sources` | `{"youtube_urls": [...]}` |
| `POST /research/mining-sources` | Body `{"youtube_urls": [...]}`. Replaces the list. `[]` clears it. `200` with the stored list |

The API stores the mining sources and does not mine. Mining runs through the MCP server's
`mine_youtube_topics` (see [The MCP Server](06-mcp-server.md)).

Each stored URL becomes the `file_uri` of a paid Gemini request, so every entry is checked by
`tubematic_core/youtube.py::check_mining_sources`. This route and the MCP server's
`set_mining_sources` and `mine_youtube_topics` all call it.

- An entry must be a YouTube video URL: `youtube.com/watch?v=<id>`, `youtu.be/<id>`,
  `youtube.com/shorts/<id>` or `youtube.com/live/<id>`, with `www.` or `m.` allowed and an
  11-character id.
- Each is stored as `https://www.youtube.com/watch?v=<id>`. Two URLs for one video are stored once.
- `400` if the body's value is not a list, if any entry is not such a URL, or if more than 50
  distinct videos remain. The error names every bad entry and nothing is stored.

The limit of 50 bounds the list. `max_mining_per_run` bounds the Gemini calls of one run.

### `POST /research/record-run`

Appends the current time to the rolling 24-hour window and returns
`{research_runs_today, max_research_runs_per_day}`. It always succeeds.

The API reports the research caps and does not enforce them. `GET /pipeline/status` returns
`research_pending_cap` and `max_research_runs_per_day`, and `scripts/poll.py` compares the numbers
before it starts an agent (see [The Poller](13-the-poller.md)). The poller records a run before it
starts the agent, so a run that fails still counts against the cap.

## Agents

The installed coding agents (see [Database](03-database.md#agents) and
[The Agent Layer](07-agent-layer.md#agents)). `python3 onboard.py --install-agent <name>` on the
host creates a row and sets its binary, workspace and models, because it checks them against the
real CLI and no container has an agent binary. Over HTTP you can set four fields.

### `GET /agents`

Every row ordered by `created_at` then `id`, with `models` parsed to a list and `is_default` as a
boolean. Uninstalled rows are included, because the dashboard labels videos still pinned to one.
The poller reads this route on every pass.

### `PATCH /agents/<agent_id>`

Body: any of `is_default`, `weight`, `default_model` and `effort`. `200` with the updated row.
`404` for an unknown agent. `409` for an uninstalled one. `400` when the body is not a JSON object,
is empty, holds any other key (`models` included), or a field fails its rule:

- `is_default` must be `true`. It clears the flag on every other agent in the same transaction. To
  clear it, make another agent the default.
- `weight` must be an integer from 0 to 100. A boolean is refused.
- `default_model` must be one of the agent's installed `models`. It moves that model to the front
  of the list, because the default model is `models[0]` for the poller, the MCP server and the
  dashboard. Adding a model needs the host installer, which probes it against the CLI.
- `effort` must be `low`, `medium`, `high`, `xhigh` or `max`. Blank is refused.

The API has no `DELETE` for agents. `python3 onboard.py --uninstall-agent <name>` on the host sets
`archived_at`, clears `is_default` and removes the skills, commands and MCP registration, which the
API container cannot reach. The row stays, so videos pinned to the agent still resolve it. See
[Deployment](07-agent-layer.md#deployment).

## Script profiles

A script profile is a writing style built from YouTube transcripts (see
[Script profiles](08-scripting-and-voice.md#script-profiles)).

### Reading script profiles

| Route | Response |
|---|---|
| `GET /script-profiles` | Profiles that are not archived, newest first, without `markdown` and `corpus_summary` |
| `GET /script-profiles/pending` | Profiles at `PENDING` or `GENERATING`, oldest first. The poller reads it |
| `GET /script-profiles/<id>` | The full profile with its markdown. Serves archived profiles too, so a video that references one still resolves. `404` if unknown |

### `POST /script-profiles`

Body `{name, urls}`. The route fetches each transcript inside the request, one at a time, and
collects per-URL failures without stopping.

| Status | Cause |
|---|---|
| `201` | The profile at `PENDING`, plus `transcripts_fetched` and `failures[]` |
| `400` | `name` is empty, `urls` is not a non-empty list, or it holds more than 10 URLs |
| `400` | No transcript could be fetched: `{"error", "failures": [...]}`. No profile is created |
| `503` | No `youtube_transcript_api_key` is configured |

### `DELETE /script-profiles/<id>`

Sets `archived = 1` and deletes the profile's stored transcripts. The row is kept.
`200 {"ok": true, "archived": true}`. `404` if unknown.

### `POST /script-profiles/<id>/record-attempt`

The poller calls it before it starts a profile-building agent.

| Status | Body |
|---|---|
| `200` | `{id, status: "GENERATING", attempt_count}`: an attempt was claimed |
| `200` | `{id, status: "FAILED", attempt_count, error}`: `attempt_count` had reached its cap of 2, and the profile is now `FAILED` |
| `404` | Profile not found |
| `409` | `{id, status, attempt_count}`: the profile is already `READY` or `FAILED` |

### Transcripts

`renderer/api/transcripts.py` fetches from `https://www.youtube-transcript.io/api/transcripts`.

- The key is sent raw in an `Authorization: Basic <key>` header, without base64 encoding.
- Each request carries one video id.
- `extract_video_id` accepts `youtu.be/`, `?v=` and `&v=`, `/shorts/`, `/embed/` and a bare
  11-character id.
- The text is read from `data[0].tracks[*].transcript`, then from a flat `transcript` field, and
  joined into one string. An unrecognised response yields `""`.
- The client has no rate limiting, retry or backoff. The service publishes a limit of 5 requests
  per 10 seconds, and one `POST /script-profiles` makes up to 10 calls in a row.

## Mascots

A mascot is a library entry whose drawing code an agent writes and a human approves. Creating one
inserts version 1, and each request for changes inserts a new draft version. The draft is the
highest version without `approved_at` above the approved one. An approved version does not change.
A mascot is pickable once a version is approved and until it is archived, so a failed or pending
revision does not remove the working version.

A video's mascot is set through [`PATCH /videos/<video_id>`](#patch-videosvideo_id). The install
default is the setting `default_mascot_id`, and a domain's default is `default_mascot_id` on
[`POST /projects`](#post-projects).

### Reading mascots

| Route | Response |
|---|---|
| `GET /mascots` | Mascots that are not archived, built-ins first |
| `GET /mascots/pending` | `PENDING` and `BUILDING` mascots, oldest first, each with the draft's `change_request`. The poller reads it |
| `GET /mascots/<id>` | One mascot plus `versions` (without their code). Serves archived mascots. `404` if unknown |
| `GET /mascots/<id>/versions/<version>/sheets/<sheet>` | The sheet image. `<sheet>` is `turn`, `feels` or `act` |

Each mascot carries `pickable`, `draft_version` and `sheets`. `sheets` has `approved` and `draft`,
each `null` or the API-relative URLs of the sheet files that exist.

A built-in mascot's sheet is a JPEG from its shipped files. Any other is a PNG from the data
directory. The route answers `404` for a missing file and for a symlink.

### `POST /mascots`

Body `{description, name, surprise?, agent_id?, agent_model?, agent_effort?, based_on?}`. `201`
with the mascot at `PENDING`. A rule that fails is a `400`.

- `name` is required and at most 60 characters. With `surprise: true` it defaults to "Surprise
  mascot".
- `description` is required unless `surprise` is true, and is at most 2000 characters.
- The agent picks are checked as on [`POST /videos/manual`](#post-videosmanual).
- `based_on` must be a pickable mascot. The `INSERT` repeats that check, and answers `409` with
  nothing created when the mascot was archived meanwhile.
- The id is a slug of the name. If another create takes the slug first, the route tries the next
  suffix, `pipeline.py::MASCOT_SLUG_ATTEMPTS` times, then answers `409`.

### `POST /mascots/<id>/approve`

Publishes the draft version and sets `READY`. `200` with the mascot. `404` for an unknown or
archived mascot. `409` when the mascot is not `IN_REVIEW`, when the draft has no code, or when one
of its three sheets has not been rendered.

### `POST /mascots/<id>/request-changes`

Body `{comment}`, required, at most 2000 characters. Adds a draft version and sets `PENDING` with a
new attempt budget. `200` with the mascot.

| Status | Cause |
|---|---|
| `400` | `comment` is missing or too long, or the mascot is built-in. For a variation, create a mascot with `based_on` |
| `404` | Unknown or archived |
| `409` | The mascot is not `IN_REVIEW`, `READY` or `FAILED`, which means an agent is working on it |

### `POST /mascots/<id>/record-attempt`

The poller calls it before it starts a mascot-building agent, and starts no session on a `409`.

| Status | Body |
|---|---|
| `200` | `{id, status: "BUILDING", attempt_count, draft_version}`. The sheet-render count is reset |
| `200` | `{id, status: "FAILED", attempt_count, error}`: the attempts had reached `mascots.py::MAX_MASCOT_ATTEMPTS` (2). The error names an approved version still in use |
| `404` | Unknown or archived |
| `409` | `{id, status, attempt_count}`: the mascot is not `PENDING` or `BUILDING` |

### `DELETE /mascots/<id>`

Sets `archived = 1`. A built-in mascot can be archived too. The row is kept.
`200 {"ok": true, "archived": true}`. `404` if unknown.

The three lifecycle routes above write with an `UPDATE` bound to the status they read and to
`archived = 0`. An archive or another change that commits after the route read the mascot wins, and
the route answers `409`.

## Publishing and analytics

These routes publish an approved video now or at a scheduled time, cancel a scheduled post, recover
a video that failed while publishing, read performance figures and configure Auto Pilot. What each
one does internally is in [Publishing internals](14-publishing.md#http-routes).

The routes that reach postforme, and `POST /publishing/accounts`, answer `503` when
`publishing_enabled` is false or no `postforme_api_key` is stored. The check runs before any
outbound call. `GET /videos/<video_id>/publications`, `publish-prefill`, `GET /analytics` and the
two `/autopilot` routes have no such check.

### Accounts

| Route | Behaviour |
|---|---|
| `GET /publishing/accounts` | A list: postforme's live accounts reconciled against the allowlist. `502` if postforme cannot be reached |
| `POST /publishing/accounts` | Body `{account_ids: [...]}`. Replaces the allowlist. `200 {account_ids}`. `400` unless it is a list of strings |
| `POST /publishing/accounts/connect` | Body `{platform}`. `200 {platform, url}`: a postforme consent URL that requests `posts` and `feeds`. Stores nothing |

An account carries:

| Field | Meaning |
|---|---|
| `id`, `platform`, `username`, `profile_photo_url`, `status` | From postforme. No other postforme field is passed on |
| `allowed` | The id is on the allowlist |
| `available` | postforme lists the account. An allowlisted id it does not list is returned with `available: false` and `status: "disconnected"` |
| `analytics` | `true`, `false` or `null`. `false` only where postforme rejects a feed read. Probed for allowlisted accounts only |

`?feeds=0` skips the feed probe, and every `analytics` is then `null`. What the value means is in
[What the Socials badges mean](14-publishing.md#what-the-socials-badges-mean).

For `connect`, `platform` must be `youtube`, `instagram`, `tiktok` or `facebook`, else `400` before
any outbound call. `502` when postforme fails (the body carries its message) or its answer holds no
`https` URL.

### Publications and prefill

`GET /videos/<video_id>/publications` returns the video's publication rows, ordered by platform:
`id`, `video_id`, `platform`, `social_account_id`, `status`, `post_url`, `error`, `published_at`,
`created_at`, `updated_at`.

`POST /videos/<video_id>/publish-prefill` is a read that calls no model. It returns
`{title, description, duration_secs, youtube_short, youtube_shorts_max_secs}`. `title` and
`description` are the stored `publish_title` and `publish_description`, or the video's own title
and topic when nothing is stored. `youtube_short` is `null` when the duration cannot be read. `404`
for an unknown video.

### `POST /videos/<video_id>/publish`

Body: `account_ids` (required, non-empty list), `title`, `description`, `privacy` (an object keyed
by platform) and an optional `schedule: {local: "YYYY-MM-DDTHH:MM", timezone: "<IANA>"}`. A blank
`title` falls back to the video's title or topic.

| Status | Cause |
|---|---|
| `201` | `{status, postforme_post_id, scheduled_at, scheduled_timezone, publications}`. `status` is `SCHEDULED` or `PUBLISHING` |
| `400` | A malformed body, an account off the allowlist, no rendered mp4, an unsupported privacy value, or a bad schedule |
| `404` | Video not found |
| `409` | The video is archived or not at `VIDEO_APPROVED`, or a concurrent request took the claim |
| `502` | postforme rejected the request or could not be reached. With `"reconciling": true`, the post may exist and the video stays `PUBLISHING` |

A schedule is bad when its zone is unknown, its time is malformed or falls in an hour the clocks
skip, or it is less than 5 minutes or more than 365 days ahead.

### `POST /videos/<video_id>/publish/retry`

No body. Accepts a `FAILED` video that has publication rows.

| Status | Cause |
|---|---|
| `200` | `{outcome, status}`. `reconciling`: a live post exists and the video is back at `PUBLISHING`. `republish`: none exists and the video is back at `VIDEO_APPROVED` |
| `404` | Video not found |
| `409` | Archived, not `FAILED`, `FAILED` without publication rows, or a concurrent retry took the claim |
| `502` | postforme could not be asked. Nothing changes |

### `POST /videos/<video_id>/schedule/cancel`

No body. Deletes the post at postforme and returns the video to `VIDEO_APPROVED`.

| Status | Cause |
|---|---|
| `200` | `{"status": "VIDEO_APPROVED"}` |
| `404` | Video not found |
| `409` | Not `SCHEDULED`, postforme has started sending the post, or the video changed status meanwhile |
| `502` | postforme failed, answered `success: false`, or still lists a post it could not find. The post is still scheduled, and the cancel can be tried again |

### Analytics

`GET /analytics` is served from local snapshots and does not call postforme. The optional query
parameters `platform` and `social_account_id` filter every part of the response.

| Field | Meaning |
|---|---|
| `totals` | `views`, `likes`, `comments`, `shares`, `publications`, `videos` |
| `by_platform` | The four metrics summed per platform. An unreported metric adds 0 |
| `publications` | Each published row with its latest `views`, `likes`, `comments`, `shares` (null when unreported), `fetched_at` and the video's `title` |
| `by_month` | `[{month: "YYYY-MM", views}]`: views gained in each of the last 12 months, oldest first. Months before any snapshot are left out. A figure can be negative |
| `timezone` | The zone the months were cut in (the host's, or `UTC`) |

`POST /analytics/refresh` captures metrics for every account now and returns
`{accounts, snapshots, errors}`.

### Auto Pilot

`GET /autopilot` returns:

| Field | Meaning |
|---|---|
| `enabled`, `gap_mins` | `auto_pilot_enabled` and `auto_pilot_gap_mins` |
| `max_in_flight` | `auto_pilot_max_in_flight`. 0 means no limit |
| `in_flight` | Videos in progress, as the [in-progress limit](14-publishing.md#the-in-progress-limit) counts them |
| `projects` | `{project_id: [account_id, …]}`. A domain that is a key is on Auto Pilot. Its list may be empty |
| `account_limits` | `{account_id: posts per day}`, for accounts that have been set |
| `default_daily_limit` | What an account with no entry gets |
| `waiting` | `{project_id: {status: count}}` for videos at `TOPIC_PROPOSED`, `SCRIPT_READY`, `VIDEO_READY` and `VIDEO_APPROVED`. The dashboard's confirmation counts from it |

`POST /autopilot` requires `enabled`, `gap_mins`, `projects` and `account_limits`, and returns the
same document as `GET`. `max_in_flight` is optional, and the stored limit is kept without it. The
body is validated whole and written whole.

`400` causes:

- `enabled` is not a boolean.
- `gap_mins` is outside 0 to 10080, or `max_in_flight` is outside 0 to 500.
- `projects` is not a map of project id to a list of account ids, or names a domain that does not
  exist.
- An account newly added to a domain is not on the allowlist.
- A daily number is not a whole number from 0 to 50.

## Costs

The read side of the usage ledger and the price table behind it. Every dollar figure is an API
list price and ignores subscriptions and plan credits. ElevenLabs is reported in plan credits.
Where rates come from is in [Settings](../user-guide/05-settings.md#costs).

### `GET /videos/<video_id>/costs`

`{has_usage, lines, agent, total_usd, credits, unpriced_calls}`.

- `lines` groups calls that are not agent sessions by service, model and operation. Each has
  `calls`, `cost_usd` (`null` when none were priced), `credits`, `unpriced_calls` and `estimated`.
- `agent` is `null` or `{models, share_usd, session_total_usd, shared, estimated, sessions[]}`.
  Each session carries `stage`, `batch_size`, `total_usd` and this video's `share_usd`.
- `total_usd` adds the agent share and leaves out the rest of a shared session.

### `GET /usage/summary`

Spend for a range. Send one of three forms:

| Form | Meaning |
|---|---|
| `?preset=today`, `week` or `month` | Resolved by the API, ending today in the host time zone. A week starts on Monday |
| `?from=YYYY-MM-DD&to=YYYY-MM-DD` | Inclusive days in the host time zone |
| `?since=<ISO timestamp>` | Open-ended. Defaults to the start of the current UTC month |

For the first two forms the response echoes `from`, `to`, `until` and the `timezone` the days were
cut in (`UTC` when the host zone cannot be named or loaded). `until` is exclusive. Each end is
converted at its own local midnight, so a range across a DST switch is not off by an hour. The
dashboard sends presets by name, because its copy of the host zone is UTC until it loads.

Response fields: `since`, `until`, `total_usd`, `videos`, `research`, `agent_other`, `other`,
`video_count`, `unpriced_calls`, `voice_credits`, `preview_credits`, `estimated` and
`elevenlabs_pool`. `elevenlabs_pool` is `{tier, used, limit, resets_at_unix}`, or `null` when the
key lacks the optional `user_read` permission or the call fails.

`400` causes: more than one form, an unknown `preset`, a `from` without a `to` or the reverse, a
date that is not a real `YYYY-MM-DD` day, `from` after `to`, a malformed `since`, or a range whose
UTC boundaries a datetime cannot hold (such as `to=9999-12-31`).

### `POST /usage/agent-session`

How an agent session's usage reaches the ledger. The poller has no database access, so it parses
each session's JSON output and posts it here (see [The Poller](13-the-poller.md)).

```json
{"session_id": "…", "operation": "agent_pipeline", "agent": "claude",
 "videos": [{"video_id": "vid_abc", "stage": "TOPIC_APPROVED"}],
 "events": [{"service": "…", "model": "…", "units": {}, "raw": {},
             "reported_cost_usd": 0.12, "estimated": false}]}
```

- `operation` must be `agent_pipeline`, `agent_research`, `agent_profile`, `agent_mascot` or
  `agent_unscoped`.
- Every event is recorded against every listed video. The poller lists one video for a pipeline
  session, with `stage` set to the status the session started at.
- `200 {recorded, events}`. A `recorded` below `events` means some events were not recorded.
- `400` for an unknown `operation`, a missing `session_id`, or an `events` value that is not a list
  of 1 to 50 entries.
- The write is idempotent per `session_id` and event position. A payload resent after a timeout
  records nothing twice and still counts those events as `recorded`.

Every other paid call is written to the ledger by the process that made it.

### Prices

| Route | Behaviour |
|---|---|
| `GET /prices` | `{models, unpriced, unit_kinds, last_sync_attempt_at, last_sync_ok_at, last_sync_error}` |
| `POST /prices/sync` | Runs the price sync now. `200 {ok, updated, rejected, missing, error}` |
| `POST /prices/override` | Body `{service, model, rates: {unit_kind: usd_per_token}}`. `200 {ok, repriced}` |
| `DELETE /prices/override?service=&model=` | Drops a manual rate. `200 {"ok": true}`. `400` without both parameters |

- Each entry in `models` has `service`, `model`, `rates` (USD per token), `source` (`manual`,
  `openrouter`, `litellm`, `built-in` or `null`), `tiered` and `effective_from`.
- `unpriced` lists models with unpriced calls and how many.
- A failed sync is a `200` with `ok: false` and keeps every existing price.
- A sync does not overwrite a manual rate. Setting one prices that model's unpriced calls, and
  calls that already have a price keep it. Without one the model uses its synced or built-in rate.
- `POST /prices/override` answers `400` for a missing name, an unknown unit kind, a rate that is
  not positive, an empty `rates`, or `service: "elevenlabs"`.

## Renderers

The routes behind the dashboard's Renderers panel (**Settings → Rendering**). They cover every
machine that renders, the built-in renderer included, and they use the API token. How renderers
are scheduled and added is in [GPU and Remote Renderers](20-gpu-and-remote-renderers.md).

### `GET /renderers`

`200 {"remote_enabled", "gateway_address", "renderers": [...]}`.

- `gateway_address` is the settings row `render_gateway_address`, as `host:port`. Only
  `python3 onboard.py --step renderers` writes it. `remote_enabled` is whether it holds an address.
- `renderers` holds every renderer that is not removed, the built-in one first. The route creates
  the built-in row again if it is missing.

Each entry is `tubematic_core/renderers.py::renderer_states` plus the fields
`pipeline.py::renderer_list` adds. No credential hash is returned.

| Field | Meaning |
|---|---|
| `id`, `name`, `builtin`, `enabled` | `id` is `builtin` for the built-in renderer and `r_<hex>` for an enrolled one |
| `online` | A heartbeat arrived within the last 120 seconds |
| `state`, `current_video_id`, `current_video_title` | `idle` or `rendering` as last reported, and that video's title (its topic when it has none) |
| `version`, `needs_upgrade` | The version last reported. A version other than the main install's sets `needs_upgrade`, and that renderer claims nothing |
| `gpu_verified`, `gpu_probed`, `gpu_configured`, `gpu_error` | From its last GPU probe: whether it passed, whether one exists, whether a GPU was configured, and why it failed |
| `gpu` | `null` before the first probe, else `{ok, configured, error, renderer, name, at}`. `renderer` is the WebGL renderer string Chromium reported |
| `probe_pending`, `waiting_for_render` | A test was requested and no probe has started since. `waiting_for_render` adds that the renderer is rendering, which it finishes first |
| `compute`, `host` | As reported: `{cpus, memory_bytes, gpus: [{name, uuid, memory_mb}]}` and the renderer's host name |
| `last_heartbeat_at`, `last_error`, `created_at` | As stored |
| `credential_expires_at` | `''` for the built-in renderer, whose credential does not expire |

### `POST /renderers/enrollments`

Issues a one-time [enrollment token](19-render-gateway.md#enrollment), valid for one hour. Body
`{"name"}`, optional: 1 to 60 characters after trimming. Blank or absent means no name.

| Status | Cause |
|---|---|
| `201` | `{"token", "expires_at", "command"}` |
| `400` | The body is not an object, or `name` is not a string of 1 to 60 characters |
| `409` | `{"error": "remote_renderers_off"}`: no gateway address is stored |
| `503` | `{"error": "gateway_certificate_missing"}`: the pin cannot be computed |

The token appears in this response only. The database keeps the hash of its secret. `command` is
`python3 tubematic_remote_renderer.py install` and does not contain the token: the script asks for
it with a hidden prompt, because a command line is visible to other users of the machine and is
kept in shell history.

### `PATCH /renderers/<id>`

Body with `enabled` (a boolean), `name` (1 to 60 characters), or both. `200` with the updated
renderer. `400` for a body with neither, or a bad value. `404 not_found` for an unknown or removed
id. A disabled renderer still sends heartbeats and claims nothing. The built-in renderer can be
disabled.

### `DELETE /renderers/<id>`

`200 {"id", "removed_at"}`. Sets `removed_at` and clears both credential hashes, so the renderer's
next heartbeat gets `401`. The worker's lease sweep re-queues a render it held once the lease runs
out. `409 {"error": "builtin"}` for the built-in renderer. `404 not_found`.

### `POST /renderers/<id>/gpu-test`

Stamps the renderer's `gpu_probe_requested_at`. Its next heartbeat reply carries `probe_now`, and
it tests between renders. `202` with the renderer, `probe_pending: true`. The result arrives in a
later `GET /renderers`. `404 not_found`.

### GPU rendering

The API container has no GPU. Each renderer tests its own and reports the result through the
render gateway, which stores it on the renderer's row (see
[The GPU test](20-gpu-and-remote-renderers.md#the-gpu-test)).

| Route | Response |
|---|---|
| `GET /render/gpu` | `200` with the fields below |
| `POST /render/gpu/test` | The built-in renderer's form of `POST /renderers/<id>/gpu-test`. `202` with the same body, `pending: true` |

| Field | Meaning |
|---|---|
| `status` | Install-wide, across every renderer: `working`, `unknown`, `not_usable` or `not_configured` |
| `rendering_on` | `gpu` when the built-in renderer's own last test passed, else `cpu` |
| `configured`, `gpu` | Whether the built-in renderer was given a GPU, and its `{uuid, name}` |
| `host_gpus` | Each NVIDIA GPU the host had when onboarding's `gpu` step ran: `index`, `uuid`, `name`, `memory_mib`, `driver` |
| `probe` | The built-in renderer's stored probe, or `null` |
| `requested_at`, `pending` | The last test request, and whether no probe has started since |
| `waiting_for_render` | `pending`, and the built-in renderer holds a render it has not uploaded |

`status` is computed by `tubematic_core/renderers.py::gpu_status`:

- `working`: an enabled renderer's GPU test passed.
- `unknown`: no test has passed and an enabled renderer has not tested yet.
- `not_usable`: a GPU is configured and its test failed, so renders use the CPU.
- `not_configured`: none of the above.

Every field except `status` describes the built-in renderer, the one renderer that onboarding's
`gpu` step configures. `status` is the aggregate because the Cartoon 3D and mascot checks read it,
and a check on the built-in renderer alone would refuse a style that another renderer can render.

## Pipeline control

### `POST /pipeline/pause`

Body `{"paused": <bool>}`. `200 {"paused": …}`. `400` unless `paused` is a boolean.

### `GET /pipeline/status`

The poller reads it to decide what to start, and the dashboard reads it on load.

| Field | Meaning |
|---|---|
| `paused` | The `pipeline_paused` setting |
| `video_counts`, `workable_count`, `proposed_count` | Counts per status, the sum over `WORKABLE_STATUSES`, and the count at `TOPIC_PROPOSED` |
| `active_strategies`, `mining_available` | The active research modes. `mining` is left out while no Gemini key is stored |
| `research_pending_cap`, `max_research_runs_per_day` | The two caps the poller compares against |
| `research_runs_today`, `research_window_resets_at`, `last_research_at` | The rolling 24-hour run window and the last completed research |
| `pending_script_profiles`, `pending_mascots` | How many wait for an agent |
| `timezone`, `timezone_label` | See [Time](#time) |
| `version` | The installed version, from `tubematic_core/version.py::version` |
| `github_repo` | `tubematic_core.version.GITHUB_REPO`, for the dashboard's [update check](15-dashboard.md#update-check) |

The poller builds its research prompt from `active_strategies`, so a run is not told to mine
without a key.

## Logs

### `GET /logs`

Structured log records, newest first. The dashboard has no log mount and no Docker socket, so this
route is its only access to the logs.

| Parameter | Default | Notes |
|---|---|---|
| `service` | all | `api`, `mcp`, `worker`, `renderer` or `poll`. Any other value is a `400` |
| `level` | all | A minimum: `warning` also returns errors. An unknown level is a `400` |
| `video_id` | none | Exact match |
| `profile_id` | none | Exact match |
| `q` | none | Case-insensitive substring, matched against the whole record |
| `limit` | 200 | 1 to 2000. A non-integer or out-of-range value is a `400` |

```json
{
  "records": [
    {"ts": "2026-09-06T14:20:10Z", "service": "renderer", "level": "info",
     "message": "render complete", "video_id": "vid_abc"}
  ],
  "count": 1,
  "limit": 200,
  "services": ["api", "mcp", "worker", "renderer", "poll"],
  "levels": ["debug", "info", "warning", "error"]
}
```

- `services` and `levels` are echoed so a client can build its filter lists from the response.
- A record carries `video_id`, `profile_id` and `request_id` when the writer had them.
- With no `service`, the route reads every service's files. The video modal's Logs tab sends
  `GET /logs?video_id=…`, because one video's records are spread over all of them.
- A file name is built from an allowlisted service name and a date, so nothing from the request
  reaches a path. A malformed line is skipped, because a file being appended to can end in half a
  line.
- The route deletes no file. Retention is the writers' job (see
  [The log files](16-infrastructure.md#the-log-files)).

## The render gateway

The gateway is a second Flask app in the same process, on HTTPS port 4443 under `/v1`. Renderers
use it to claim a video, download its files, upload the mp4 and report the result. It accepts
renderer credentials only. Its routes, TLS pin, enrollment tokens, credentials and limits are in
[The Render Gateway](19-render-gateway.md).

## Code layout

- `renderer/api/server.py` builds the app, registers the pipeline and login blueprints, installs
  the token check and starts the render gateway in a thread.
- `renderer/api/db.py` provides `conn()`, `set_status()`, `update_fields()` and `add_comment()`,
  with WAL mode, foreign keys on and a `sqlite3.Row` factory. The worker, the render gateway and
  `render_results.py` use it. `pipeline.py` defines its own connection helper.
- The API stores and returns the path columns as opaque strings and no code reads a location from
  them (see [Database](03-database.md#videos)). The dashboard builds a video's `/stream/…` URL from
  its ids (`dashboard/lib/utils.ts::videoStreamUrl`) and converts the `/output_videos/…` path from
  the voice preview route with `videoToStreamUrl`.

## Known quirks

| Behaviour | Detail |
|---|---|
| An empty research-mode list is stored as empty | `POST /research/strategies` with `[]` stores `""`, which reads back as `[]`, so the poller skips research. The three-mode default applies only when the row is absent |
| Unhandled exceptions return HTML | No JSON error handler is registered. A malformed body, a foreign-key violation or a corrupt stored settings value produces Werkzeug's HTML page in place of `{"error": …}` |
| The freeze rule tests presence | `{"script_profile_id": ""}` on a video past `TOPIC_PROPOSED` returns `409`, although `""` is a legal value. So does `agent_id` set to the video's own agent between checkpoints |
| `openai_api_key` is checked for presence only | The API checks that a key is stored before it accepts `illustrated`. A revoked key is found later, when the MCP server's `generate_image` or `generate_character` uses it |
