# Settings internals

What each setting means to a person running Tubematic, and when to change it, is in the user
guide's [Settings](../user-guide/05-settings.md). Here you will find how settings are stored, read,
masked and checked, every key with its type and bounds, the other rows that share the table, and
how to add a key.

---

## Storage and reads

Every setting is a row in the `settings` table (`key TEXT PRIMARY KEY`, `value TEXT NOT NULL`), so
every value is stored as a string. `SETTINGS_SPEC` in `renderer/api/pipeline.py` declares each
key's type and default. The types are `bool`, `int`, `str`, `secret`, `json_list`, `voice_list` and
`lexicon`. `pipeline.py::_coerce_setting` turns a raw value into its typed form and into the string
that is stored, and raises on a value outside the key's bounds.

- `pipeline.py::_read_all_settings` coerces every declared key and uses the spec default for a key
  with no row. A new key's default therefore applies to an upgraded install with nothing written
  for it. A stored value that fails coercion reads as the default too.
- `POST /settings` (`pipeline.py::post_settings`) rejects any undeclared key with `400`, coerces
  every value, and then writes. One bad value changes nothing.
- `str` and `secret` values are stripped of surrounding whitespace before they are stored.
- No process caches a setting. The API, the MCP server and the worker read the database on each
  use, so no key needs a restart. `log_retention_days` is the one key with a delay
  ([Logs](#logs)).
- A renderer reads no settings. `render_timeout_secs`, `render_stall_timeout_secs` and
  `watermark_enabled` arrive with each claim, read at that moment, so a change applies from the
  next claim.

### The default-voice invariant is enforced on read

If the stored `elevenlabs_voice_id` is not on the `elevenlabs_voices` roster, `_read_all_settings`
returns it as `""`. `post_settings` does not check the pair. The roster can fall back to `[]` by
itself when a stored list fails coercion, and a write-time check would then reject the next
unrelated settings save with an error about voices. Do not add one.

### The default mascot is checked on read and on write

`default_mascot_id` names a row in `mascots`, which `_coerce_setting` cannot see because it has no
database connection. The two checks live elsewhere:

- `_read_all_settings` returns `""` when the mascot is archived or was never approved.
- `post_settings` refuses a changed value that is not a pickable mascot. It also refuses any
  changed value while no renderer's GPU is `working`
  (`tubematic_core/mascots.py::mascot_gpu_error`, the rule and wording a pick on a video uses).

`post_settings` checks the value only when it changes. Refusing a re-sent stored value would block
every unrelated save once the mascot is archived or the GPU is gone. `""` passes.

### Derived: `pronunciation_mode`

`pronunciation_mode` is not stored, and posting it is an unknown-key error. It belongs to a voice's
model, so `GET /settings` does not return it.
`tubematic_core/voice_models.py::pronunciation_mode_for_model` computes it wherever a video's model
is known, and the MCP `get_video` tool reports it per video:

- `ipa` for `eleven_v3` and `eleven_v4`
- `phoneme` for a model that supports phoneme tags
- `respell` otherwise

It is derived because a model that supports more markup only adds capability, which leaves a human
nothing to choose. See [Scripting and Voice](08-scripting-and-voice.md#pronunciation).

---

## Key reference

Every key in `SETTINGS_SPEC`, grouped as on the dashboard's **Settings** page. The Bounds column
is what `_coerce_setting` enforces. It also refuses a negative value for every `int` key.

### Pipeline control

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `pipeline_paused` | bool | `false` | | `scripts/poll.py`, which then starts no pipeline or research session. The worker's Auto Pilot pass and voicing-stall check |

Sessions already running finish, script profiles are still built, and human approvals still work.

### AI review

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `gemini_review_enabled` | bool | `false` | | The worker's review step (`render_results.py`). When false, or while no `gemini_api_key` is stored, a successful render goes to `VIDEO_READY` |
| `ai_review_model` | str | `gemini-2.5-flash` | One of `AI_REVIEW_MODELS`: `gemini-2.5-flash`, `gemini-3.5-flash`, `gemini-3.6-flash` | The review step |
| `ai_review_fps` | int | `10` | 1 to 24 | The review step, as the frame sampling rate sent to Gemini. See [Cost](21-ai-review.md#cost) |
| `ai_review_max_loops` | int | `1` | 1 to 2 | The review step, as the number of revision rounds the reviewer may force |

`ai_review_model` is an allowlist because the review needs a measured tokens-per-frame figure for
each model.

### Rendering

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `render_timeout_secs` | int | `10800` | At least 60 | The render gateway, which sends it with each claim. The ceiling on one render |
| `render_stall_timeout_secs` | int | `600` | At least 60 | The render gateway, with each claim. How long the render's progress counter may stand still before the renderer stops the render |
| `max_render_retries` | int | `1` | | `render_results.py`. Caps `videos.render_fail_count` |
| `text_layout_audit_enabled` | bool | `true` | | The MCP `validate_job` tool. Switches off the advisory text-overlap and safe-zone audit |
| `default_mascot_id` | str | `""` | `""` or a pickable mascot. See [above](#the-default-mascot-is-checked-on-read-and-on-write) | Video creation, in the API and the MCP server, when the domain has no default of its own |
| `watermark_enabled` | bool | `true` | | The render gateway, with each claim. The renderer passes it to the composition |

- `render_timeout_secs` detects a render that will not end. Three hours covers a three-minute Short
  on the CPU with headroom. `render_stall_timeout_secs` catches a hung render sooner, whatever the
  video's length, because Remotion reports every frame it renders and encodes.
- `max_render_retries` counts failed renders, stalls, timeouts, and renders lost to a renderer
  restart or an expired lease. `ai_review_max_loops` is a separate cap, so allowing one review
  round does not reduce the render-retry budget.
- `watermark_enabled` is a setting and has no `scene-config.json` key, because the agent writes
  that file and has no tool that writes settings. See
  [Watermark](09-remotion-project.md#watermark).

Two rendering choices are made on the host and have no settings key. A container's GPU is fixed
when the container is created, so `python3 onboard.py --step gpu` chooses it
([GPU rendering](../user-guide/10-gpu-rendering.md)). Letting renderers on other machines connect
publishes a port, which `python3 onboard.py --step renderers` does
([Remote renderers](../user-guide/11-remote-renderers.md)).

### Scheduling

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `max_concurrent_agent_sessions` | int | `3` | 1 to 10 | `scripts/poll.py`, on every pass. Pipeline sessions run at once, one video each |
| `agent_session_timeout_secs` | int | `5400` | At least 60 | `scripts/poll.py`. Wall clock for one agent session, its model and effort retries included, before its process group is stopped |

Research and script-profile sessions run beside the pipeline sessions and outside the limit. The
dashboard shows the timeout in minutes. See [The Poller](13-the-poller.md).

### Logs

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `log_retention_days` | int | `14` | 1 to 365 | Each service's log maintenance pass (`tubematic_core/logging.py::prune_logs`) |

Each service prunes its own log files when it starts and at each daily rollover, so a change takes
effect at the next pass. `0` is refused because it would delete the file the service is writing.

### Video retention

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `retention_days` | int | `7` | 0 to 365. `0` disables the sweep | The worker's hourly retention sweep |
| `unpublished_retention_days` | int | `0` | 0 to 365. `0` disables the sweep | The same sweep |

- `retention_days` sweeps `PUBLISHED` videos, dated from the latest successful publication's
  `published_at`.
- `unpublished_retention_days` sweeps `FAILED` and `TOPIC_REJECTED` videos, dated from
  `updated_at`. It defaults to off because a failed video is paid-for output someone may still want
  to inspect.
- The sweep touches no other status.
- `GET /retention/backlog` reports how many failed and rejected videos exist and how much disk they
  hold.

See [The Worker](12-the-worker.md).

### Research

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `max_curriculum_per_run` | int | `2` | | `scripts/poll.py`, in the research prompt |
| `max_trending_per_run` | int | `2` | | `scripts/poll.py`, in the research prompt |
| `max_mining_per_run` | int | `2` | | `scripts/poll.py`, and the MCP `mine_youtube_topics` tool, which enforces it. `0` turns mining off |
| `research_pending_cap` | int | `15` | | `scripts/poll.py`. No research starts once this many videos sit at `TOPIC_PROPOSED` |
| `max_research_runs_per_day` | int | `8` | | `scripts/poll.py`. A rolling 24-hour cap on research sessions |
| `trending_sources` | json_list | `["GitHub Trending", "Hacker News"]` | A list of strings. The contents are not checked | `scripts/poll.py`, in the research prompt |

The API reports `research_pending_cap` and `max_research_runs_per_day`, and `scripts/poll.py`
enforces them. `mine_youtube_topics` asks Gemini for no more topics than `max_mining_per_run` and
makes no more Gemini calls than that in one run
([MCP server](06-mcp-server.md#mine_youtube_topics)).

### Voice

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `elevenlabs_voices` | voice_list | `[]` | At most 10 entries of `{name, voice_id, model_id}`. Names and ids are unique and non-empty. `model_id` is a supported ElevenLabs model | Voice generation, voice previews, and every check of a video's or domain's voice |
| `elevenlabs_voice_id` | str | `""` | `""` or a roster voice. See [above](#the-default-voice-invariant-is-enforced-on-read) | Voice generation, for a video with no voice of its own |
| `pronunciation_lexicon` | lexicon | `[]` | At most 500 `{term, respell}` entries. `term` is unique. `respell` has no whitespace | The MCP `generate_voice` tool, when it builds the text to speak |

- Onboarding stores a starting roster on a new install
  ([The roster](08-scripting-and-voice.md#the-roster)).
- Each voice carries its own `model_id`, and no install-wide model key exists, because the model
  decides which pronunciation and pause markup a script may carry
  ([The model follows the voice](08-scripting-and-voice.md#the-model-follows-the-voice)).
- A video whose `voice_id` has left the roster fails before any ElevenLabs call. It does not fall
  back to the install default.
- A `respell` should be one plain word that spells the sound. See
  [Respelling and the lexicon](08-scripting-and-voice.md#respelling-and-the-lexicon).

### Images

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `image_model` | str | `gpt-image-2.5-flare` | One of `OPENAI_IMAGE_MODELS`: `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst` | The MCP `generate_image` tool |
| `character_model` | str | `gpt-image-2.5-flare` | The same list | The MCP `generate_character` tool, for the `illustrated` style's characters |

OpenAI is the only image provider, so both tools need `openai_api_key`.

- The two keys share one list, and `character_model` is checked against it. A character needs a
  transparent background, so every model in the list must support one. To add a model that cannot,
  give `character_model` its own list first.
- `character_model` is a setting so that a model a provider withdraws can be replaced from the
  dashboard.
- `scripts/probe_openai_images.py` checks a model for everything both tools rely on. It makes
  billed calls.
- OpenAI grants model access per project. A key from a project without access to the chosen model
  gets a `403`, which both tools turn into an error naming the model and the project.
  `GET /v1/models` can list a model the project cannot call, and OpenAI validates a request body
  before it checks access, so no free call checks access ahead of time.
- A character's first asset is a generation and every later pose is an edit that sends the
  reference image as input. An edit costs about three times the tokens of a generation (1834
  against 608 for a portrait, measured).

### Agent

No settings key selects an agent, a model or an effort level. Installed agents, the default agent
and each agent's models and `effort` are rows in the [`agents` table](03-database.md#agents),
written by `python3 onboard.py --install-agent <name>`. A video's own choices are
`videos.agent_model` and `videos.agent_effort`. Model names are probed against the installed CLI
at install time and are not kept in a catalog in the repo. See
[The Agent Layer](07-agent-layer.md#agents).

### User preferences

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `user_preferences` | str | `""` | At most 6000 characters (`MAX_USER_PREFERENCES_CHARS`). A NUL character is refused. Line breaks are kept | `scripts/poll.py` and the MCP `get_pipeline_status` tool |

- `scripts/poll.py` puts the text into every prompt it builds (pipeline, research and script
  profile) as a `USER PREFERENCES` block. An empty value adds no block.
- `get_pipeline_status` returns it as `user_preferences` for interactive sessions.
  [The Agent Layer](07-agent-layer.md#user-preferences) has the block's wording.
- The cap exists because `poll.py` passes the whole prompt to the agent CLI as one command-line
  argument, and Linux limits one argument to 128 KiB (`MAX_ARG_STRLEN`). A longer prompt fails
  every agent run with `E2BIG`. The cap is far below that because the text costs tokens on every
  session.
- `exec` refuses an argument that contains a NUL, so a stored one would fail every scheduled run.
- The API and the dashboard both count code points, as Python's `len()` does. The dashboard
  truncates input at the cap with `dashboard/lib/utils.ts::codePoints`. It does not use a
  textarea's `maxLength`, which counts UTF-16 units (two per emoji).

### Publishing

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `publishing_enabled` | bool | `false` | | The publish routes and the worker. When false, `VIDEO_APPROVED` is where a video ends |

With this key alone, every step of publishing is started by a human. See
[Publishing internals](14-publishing.md).

### Auto Pilot

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `auto_pilot_enabled` | bool | `false` | | The worker's Auto Pilot pass. On with no domain selected, it does nothing |
| `auto_pilot_gap_mins` | int | `240` | 0 to 10080 (a week) | The same pass. The shortest time between two posts on one account |
| `auto_pilot_max_in_flight` | int | `0` | 0 to 500. `0` means no limit | The same pass. See [The in-progress limit](14-publishing.md#the-in-progress-limit) |

**Settings → Auto Pilot** saves all three through `POST /autopilot`, together with the
`auto_pilot_config` row, behind a confirmation. `POST /settings` accepts them too, with no
confirmation.

### Notifications

| Key | Type | Default | Bounds | Read by |
|---|---|---|---|---|
| `discord_webhook_url` | secret | `""` | A Discord webhook URL, checked as described below | The worker's notification pass |
| `notify_topic_proposed` | bool | `false` | | The same pass. One message per research run |
| `notify_script_ready` | bool | `false` | | The same pass |
| `notify_video_ready` | bool | `false` | | The same pass |
| `notify_partially_published` | bool | `false` | | The same pass. Alerts when a publish failed on some accounts |
| `notify_failed` | bool | `false` | | The same pass. Alerts when a video reaches `FAILED` |
| `dashboard_base_url` | str | `""` | `""`, or a URL that starts with `http://` or `https://`. A trailing `/` is removed | The same pass, to build links. `""` means messages carry no links |

- A message needs both a webhook URL and an enabled trigger. The stuck-in-voicing alert is the
  exception: the worker sends it whenever a webhook URL is set
  ([Troubleshooting](../user-guide/08-troubleshooting.md#a-video-is-stuck-in-voicing)).
- `dashboard_base_url` has no default because a container cannot know the host name a person
  reaches the dashboard by.
- `post_settings` checks a webhook URL twice. `discord_notify.parse_webhook_url` checks its shape.
  `discord_notify.verify_webhook` then sends an unauthenticated `GET` to the URL, which returns the
  webhook object and posts no message. A definite rejection (`401 Invalid Webhook Token` or
  `404 Unknown Webhook`) refuses the save with `400`. A timeout, a DNS failure or a `5xx` stores
  the URL, so an outage at Discord cannot block a settings save.

[Notifications](02-pipeline.md#notifications) covers what triggers a message.

### Costs

`SETTINGS_SPEC` has no cost keys. Model prices are rows in `model_prices`. See
[How a call is priced](03-database.md#how-a-call-is-priced).

### Credentials

| Key | Type | Default | Read by |
|---|---|---|---|
| `elevenlabs_api_key` | secret | `""` | Voice generation and voice previews |
| `gemini_api_key` | secret | `""` | Topic mining and AI review. Optional |
| `openai_api_key` | secret | `""` | Scene images and `illustrated` characters. Required |
| `youtube_transcript_api_key` | secret | `""` | Transcript fetching for script profiles |
| `postforme_api_key` | secret | `""` | Publishing and analytics |

A `secret` value may not contain whitespace. While `gemini_api_key` is unset, mining is left out
of the active research modes and review is skipped. While `openai_api_key` is unset,
`generate_image` fails and `illustrated` is refused wherever a visual style is chosen.

---

## Undeclared rows

These keys live in the `settings` table outside `SETTINGS_SPEC`. `POST /settings` rejects them as
unknown, and `GET /settings` does not return them.

| Key | Written by | Shape |
|---|---|---|
| `active_strategies` | `POST /research/strategies`. Onboarding seeds `curriculum,trending,mining` | Comma-joined string |
| `publishing_accounts` | `POST /publishing/accounts` | JSON array of allowed account ids |
| `auto_pilot_config` | `POST /autopilot` | JSON object. `projects` maps a domain id to the account ids it posts to. `account_limits` maps an account id to its posts per day |
| `mining_youtube_urls` | `POST /research/mining-sources` and the MCP `set_mining_sources` tool | JSON array of at most 50 distinct `https://www.youtube.com/watch?v=<id>` URLs |
| `mining_url_cursor` | The MCP `mine_youtube_topics` tool | Integer as a string: the index of the URL the next run starts from |
| `research_run_timestamps` | `POST /research/record-run` | JSON array of ISO timestamps, pruned to 24 hours |
| `last_research_at` | The MCP `mark_research_done` tool | ISO timestamp |
| `last_metrics_poll_at` | The worker's hourly metrics pass | ISO timestamp |
| `last_price_sync_at` | The worker's weekly price sync, before it runs | ISO timestamp |
| `last_price_sync_ok_at` | The price sync, when it succeeds | ISO timestamp, shown on **Settings → Costs** |
| `last_price_sync_error` | The price sync | The last failure's message, or `""` after a success |
| `last_retention_sweep_at` | The worker's retention sweep, before it runs | ISO timestamp |
| `voicing_stall_paused_at` | The worker's voicing-stall check, on every pass while the pipeline is paused | ISO timestamp |
| `render_claim_hold_until` | `onboard.py --step gpu`, around its recreate of the built-in renderer | ISO timestamp (seconds, `Z`) |
| `render_gateway_address` | `onboard.py --step renderers` (`onboard/actions.py::apply_renderers`) | `host:port`, with an IPv6 host in brackets. `""` or no row means remote renderers are off |
| `mcp_port` | Onboarding's `install_config` step | Integer as a string |
| `poll_interval_mins` | Onboarding's `cron` step | Integer as a string |
| `admin_password_hash` | Onboarding's `auth` step and `onboard.py --set-password` | `scrypt$N$r$p$salt$hash` |

What reads them:

- `active_strategies` is read through `pipeline.py::_active_strategies` and
  `mcp/server.py::_active_strategies`, which leave out `mining` while no `gemini_api_key` is
  stored. The filter does not rewrite the row. A save made while there is no key keeps a stored
  `mining`, because the caller was shown only the filtered list, so a key added later brings
  mining back.
- A missing or malformed `auto_pilot_config` reads as no domain selected.
- Both writers of `mining_youtube_urls` refuse any entry that is not a YouTube video URL
  ([Mining sources](05-http-api.md#mining-sources)). `mining_url_cursor` makes runs rotate through
  the list.
- The worker flags a stalled voicing only when enough time has passed since the later of
  `voicing_stall_paused_at` and the video's own last change, so a long pause does not flag every
  video when it ends. The same check reads `poll_interval_mins`
  ([The Worker](12-the-worker.md)).
- The render gateway hands the built-in renderer no render until `render_claim_hold_until` has
  passed, and the step deletes the row when it is done
  ([The claim](11-rendering-and-review.md#the-claim)). Other renderers are not held.
- Every enrollment token carries `https://<render_gateway_address>`, and `GET /renderers` reports
  it as `remote_enabled` and `gateway_address`. It is undeclared because turning remote renderers
  on also publishes a port, which onboarding alone can do
  ([Remote-renderers override](16-infrastructure.md#remote-renderers-override)).
- Onboarding and `--install-agent` read `mcp_port` to build the MCP URL. `mcp_port` and
  `poll_interval_mins` have no route, because each feeds something onboarding generates (the MCP
  registration and the crontab line), and a dashboard edit would change neither.
- `POST /auth/login` is the one reader of `admin_password_hash`.

---

## How credentials are stored

Credentials are plain-text rows in the SQLite database. No `.env` file or service environment
holds them.

- A key changed on the dashboard applies to the next call, with no restart.
- `docker inspect` shows no key, because no service has an `env_file`.
- Onboarding can check a key with its provider as you type it.
- The database file holds every key. Treat `~/.tubematic-data/data/tubematic.db` and its backups
  as secrets.

The file cannot be hidden from the host user: WAL mode needs write access to the `-shm` file even
to read. `renderer/entrypoint.sh` restricts the file to the host user's group where it can (`0660`
plus setgid on the directory) and falls back to world-writable when the mount directory is owned
by root. Claude Code and OpenCode agents are denied reading the data directory. Codex's read-only
sandbox has no per-path rule ([Deployment](07-agent-layer.md#deployment)).

Each process reads a key from the settings table on every call. When the row is empty it uses the
matching environment variable (`OPENAI_API_KEY` for `openai_api_key`, and so on)
(`pipeline.py::_secret`). The test compose file supplies its dummy keys that way. A normal install
sets none.

### Masking

`pipeline.py::_mask_settings` masks `secret` keys in the response of `GET /settings` and of
`POST /settings`, which re-reads and returns everything. Internal callers read the raw values.

| Stored value | Mask |
|---|---|
| Empty | `""` |
| Four characters or fewer | One bullet per character |
| Longer | Eight bullets and the last four characters |

`post_settings` drops a posted secret that equals the current mask of a stored value. The
dashboard can therefore `GET` the settings, edit one field and `POST` the whole object back
without overwriting stored keys with bullets.

### Never log a key

- Send API keys as headers. HTTP client libraries put the request URL in their exception strings,
  and error text is stored in the `comments` table, which the dashboard displays. A key in a query
  parameter would end up there.
- Do not log or display OpenAI's `401` message. It echoes twelve characters of the submitted key.
- `discord_webhook_url` is `secret`-typed because the URL is the credential: anyone holding it can
  post to the channel. Its credential is in the URL path, so an HTTP client's request log prints
  it. Log redaction matches stored secret values and key-shaped patterns. The save-time probe runs
  before the value is stored, so `tubematic_core/logging.py` carries a pattern for the webhook
  path. `discord_notify.py` also installs a filter on the `httpx` logger, because the plain stdout
  handler is not redacted.

### Rejection signatures

Onboarding checks each key with its provider when you enter it (`onboard/api_keys.py`). A check
answers valid, invalid or unknown. Onboarding refuses a key on invalid alone. A timeout or an
unreachable provider says nothing about the key, so onboarding accepts it with a warning.

| Service | Probe | A bad key answers |
|---|---|---|
| ElevenLabs | `GET /v1/user`, `xi-api-key` | `401`, `{"detail": {"status": "invalid_api_key"}}` |
| Gemini | `GET /v1beta/models`, `x-goog-api-key` | `400`, with `error.details[].reason == "API_KEY_INVALID"` |
| OpenAI | `GET /v1/models`, `Authorization: Bearer` | `401`, `{"error": {"code": "invalid_api_key"}}` |
| youtube-transcript.io | `POST /api/transcripts`, `Authorization: Basic`, body `{"ids": []}` | `401`, plain text |
| postforme.dev | `GET /v1/social-accounts`, `Authorization: Bearer` | `401`, `{"error": {"code": "err:frontline:client:invalid_key"}}` |

- Gemini answers `400`. A shared "401 or 403 means invalid" rule would accept every bad Gemini key,
  so the check reads `error.details[].reason`.
- postforme answers `401` for a wrong key (`invalid_key`) and for a request with no
  `Authorization` header (`missing_credentials`). The second is a fault in the caller, so the
  check reads `error.code` and reports invalid for the first alone.
- youtube-transcript.io has no account endpoint. It rejects on authentication before it validates
  the body, so an empty `ids` list answers `401` for a bad token, fetches nothing and spends no
  transcript quota.

### A pasted key is checked before it is sent

`onboard/api_keys.py::resolve_secret` strips surrounding whitespace from a key and stores the
stripped value, so the key that is checked is the key that is saved.
`onboard/api_keys.py::malformed_reason` then refuses a key that contains anything outside
printable ASCII (a line break, a tab, a non-printable or non-ASCII character) before any request
is made, and reports it as a copy-and-paste error.

The check runs first because such a key fails on the wire in ways that look like something else:

- A line break raises `httpx.LocalProtocolError`, a subclass of `httpx.HTTPError`. The checker's
  transport handler would read it as an unreachable provider and accept the key.
- A non-ASCII character raises `UnicodeEncodeError`, which the handler does not catch.

Interior spaces pass this check. httpx sends them, and the provider rejects the key.

---

## Adding a setting

1. Add the key to `SETTINGS_SPEC` in `renderer/api/pipeline.py` with its type and default. Add a
   coercion branch to `_coerce_setting` if the type is new or the key has bounds.
2. Add it to the `Settings` type in `dashboard/lib/types.ts` and to a tab in
   `dashboard/app/settings/page.tsx`.
3. If onboarding should ask for it, add a `Field` to `onboard/config.py` and map it in
   `ENV_FIELD_TO_SETTING`.
4. Read it where it is used, on each call. Do not read it at import.
5. Add it to the [key reference](#key-reference) and to the user guide's
   [Settings](../user-guide/05-settings.md). Grep `docs/` for a stated key count and update it.

Several settings repeat their literal default in three to five places: the spec, the
`v.get(key, "<literal>")` fallback of an `apply_*` action, a consumer's own
`os.getenv(..., default)`, and sometimes a status endpoint. Most carry no "keep in sync" comment.
Grep for the value as well as the key before you change a default.
