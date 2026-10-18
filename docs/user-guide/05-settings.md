# Settings

Every runtime knob lives in the `settings` table as a string, and is coerced and validated on the
way in and out. There are **40 declared keys**, defined by `SETTINGS_SPEC` in
`renderer/api/pipeline.py`.

Three properties are worth stating once, because they explain a lot of the design:

- **No setting requires a restart.** The Flask API, the MCP server and the render worker all read
  the database per use, with no in-process cache. A write applies to the next read. Restarting is
  only ever a remedy for a wedged container.
- **The database is the source of truth after onboarding.** `onboard.py` seeds these rows; after
  that, the dashboard and the API own them. Re-running an onboarding step re-seeds.
- **The write is atomic.** `POST /settings` coerces every value before writing any of them. One bad
  value rejects the whole request and changes nothing.

Read and write them at [`GET` / `POST /settings`](../developer/05-http-api.md#settings), on the dashboard's
Settings page, or from a script with `vqa/edit_settings.py`. How they are stored, masked and
verified, the bookkeeping rows that share their table, and how to add one are on
[Settings internals](../developer/04-settings.md).

---

## Reference

### Pipeline control

| Key | Type | Default | Notes |
|---|---|---|---|
| `pipeline_paused` | bool | `false` | When true the cron poller starts no new pipeline or research session; sessions already running finish, and script profiles are still built. Human approvals still work |

### AI review

| Key | Type | Default | Notes |
|---|---|---|---|
| `gemini_review_enabled` | bool | `false` | Experimental. When false — the default — a successful render goes straight to `VIDEO_READY`. Also skipped while no `gemini_api_key` is stored |
| `ai_review_model` | str | `gemini-2.5-flash` | One of `gemini-2.5-flash`, `gemini-3.5-flash`, `gemini-3.6-flash` |
| `ai_review_fps` | int | `10` | Frame sampling rate sent to Gemini. 1–24. Drives token cost — see [Rendering and Review](../developer/11-rendering-and-review.md#cost) |
| `ai_review_max_loops` | int | `1` | Revision rounds the reviewer may force. 1–2 |

### Rendering

| Key | Type | Default | Notes |
|---|---|---|---|
| `render_timeout_secs` | int | `2400` | Wall clock for one Remotion render. Minimum 60 |
| `max_render_retries` | int | `1` | Render **crash and timeout** retries only. A worker restart mid-render counts as a failure |
| `text_layout_audit_enabled` | bool | `true` | Kill switch for the advisory text-overlap and safe-zone audit inside `validate_job` |
| `watermark_enabled` | bool | `true` | Burns the "Made with tubematic.ai" mark into every render. Read by the worker when a render starts, so it affects later renders only. **A setting rather than a `scene-config.json` key on purpose** — see [Watermark](../developer/09-remotion-project.md#watermark) |

### Scheduling

The cron poller's supervisor — see [The Poller](../developer/13-the-poller.md). Both are read on every
pass, so a change applies to the next session started.

| Key | Type | Default | Notes |
|---|---|---|---|
| `max_concurrent_agent_sessions` | int | `3` | Pipeline sessions run at once, one video each. 1–10. Research and script profiles run beside them, outside this limit. Each session is a paid agent run, so set 1 on a tight budget |
| `agent_session_timeout_secs` | int | `5400` | Wall clock for one agent session, its model/effort retries included, before its process group is killed. Minimum 60. The dashboard shows it in minutes |

The default of 3 applies to an upgraded install too: every key's default is merged in on read, so
nothing has to be written for it to take effect.

### Logs

| Key | Type | Default | Notes |
|---|---|---|---|
| `log_retention_days` | int | `14` | Days of structured JSONL logs to keep. 1–365 |

**This is the one key that does not apply on the next read.** Each service prunes its own files when
it starts and again at each daily rollover, so a change takes effect at the next pass — within a day,
without a restart, but not immediately. Everything else on this page applies to the very next read.

### Video retention

| Key | Type | Default | Notes |
|---|---|---|---|
| `retention_days` | int | `7` | Days after a video is **published** before its mp4 and job directory are deleted and the row archived. 0–365; **0 disables the sweep** |
| `unpublished_retention_days` | int | `0` | Days after a `FAILED` or `TOPIC_REJECTED` video last changed before the same happens to it. 0–365; **0, the default, disables it** |

Each key covers its own statuses and has its own clock. `retention_days` sweeps only `PUBLISHED`
videos, dated from the latest successful publication's `published_at`, not from when the video was
created. `unpublished_retention_days` sweeps only `FAILED` and `TOPIC_REJECTED` videos, dated from
`updated_at`, which is when they last moved. No other status is ever swept. The render worker applies
both hourly, so a change lands within the hour.

Unlike `log_retention_days`, both keys allow 0. For `retention_days`, the default would otherwise
fire on the first pass after an upgrade against every video published more than a week ago, so this
one key has to carry the opt-out. `unpublished_retention_days` defaults to off because a failed video
is paid-for output someone may still want to inspect. **Settings → Retention** shows how many failed
and rejected videos there are and how much disk they hold, so you can tell whether turning it on is
worth it. See [Rendering and Review](../developer/11-rendering-and-review.md#retention).

`max_render_retries` and `ai_review_max_loops` are deliberately **separate caps**. They used to be
one key, which meant allowing a single review round silently halved the render-retry budget a
long video needs.

### Research

| Key | Type | Default | Notes |
|---|---|---|---|
| `max_curriculum_per_run` | int | `2` | Topics one curriculum research run may propose |
| `max_trending_per_run` | int | `2` | Same, for trending |
| `max_mining_per_run` | int | `2` | Same, for mining — enforced by the mining tool itself, which asks Gemini for no more than this and makes no more Gemini calls than this in one run ([MCP server](../developer/06-mcp-server.md#gemini--mine_youtube_topics)). 0 turns mining off |
| `research_pending_cap` | int | `15` | Stop researching once this many videos sit at `TOPIC_PROPOSED` |
| `max_research_runs_per_day` | int | `8` | Rolling 24-hour cap on research agent invocations |
| `trending_sources` | list | `["GitHub Trending", "Hacker News"]` | Any list of strings. The API validates the shape, not the contents |

These caps are **reported by the API and enforced by `scripts/poll.py`**, not by the API itself.

### Voice

| Key | Type | Default | Notes |
|---|---|---|---|
| `elevenlabs_voices` | voice list | `[]` | Up to 5 entries of `{name, voice_id, model_id}`, names and ids unique and non-empty, `model_id` one of the supported ElevenLabs models — see [Scripting and Voice](../developer/08-scripting-and-voice.md#the-model-follows-the-voice) |
| `elevenlabs_voice_id` | str | `""` | The install default voice. Must be `""` or a member of the roster |
| `pronunciation_lexicon` | lexicon | `[]` | Up to 500 `{term, respell}` entries. `respell` must contain no whitespace and should be one plain word spelling the sound, never hyphen-separated — see [Scripting and voice](../developer/08-scripting-and-voice.md#respell-mode-the-default). `term` must be unique |

**Removing the default voice from the roster leaves the install with no default**, rather than
refusing the save: the default reads as `""` until you pick another. Why it works that way is on
[Settings internals](../developer/04-settings.md#the-default-voice-invariant-is-enforced-on-read).

A video that names a `voice_id` no longer on the roster **errors before spending money** rather than
silently falling back to the install default.

**There is no install-wide model.** Each voice carries its own `model_id`, because the model decides
which pronunciation and pause markup a script may carry, and a human choosing a voice is choosing
that too. An older install's single `elevenlabs_model_id` setting was moved onto every voice by
migration `0006` and deleted; posting it now is an unknown-key error. There is no pronunciation
setting either: which markup a script may use follows from its voice's model
([Settings internals](../developer/04-settings.md#derived-pronunciation_mode)).

### Images

| Key | Type | Default | Notes |
|---|---|---|---|
| `image_model` | str | `gpt-image-2.5-flare` | Scene images. One of `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst` |
| `character_model` | str | `gpt-image-2.5-flare` | The Illustrated style's characters. From the same list |

**OpenAI is the only image provider.** Scene images and the Illustrated style's characters both
come from OpenAI, so `openai_api_key` is required. Gemini drew scene images too until 2.0.0;
migration `0016` deleted the `image_provider` setting and moved any `image_model` that is not an
OpenAI model to `gpt-image-2.5-flare`. That migration is load-bearing: the MCP server reads
`image_model` raw, so an off-catalog value left behind would make every `generate_image` refuse.

**There are two model settings over one list on purpose.** Scene images and character cut-outs are
different jobs, and a character is worthless without a transparent background. So **every model in
the list must support a transparent background**, because `character_model` is checked against it.
That is why `gpt-image-2` is gone: OpenAI withdrew its transparent-background support in October
2026, which made every character request fail. Migration `0011` moved an install whose
`image_model` was `gpt-image-2` to `gpt-image-2.5-flare`. Adding a model that cannot draw a
transparent background means giving `character_model` its own list first. `character_model` is a
setting rather than a fixed value so that the next withdrawal can be worked around from the
dashboard, not by a release. `scripts/probe_openai_images.py` checks a model for everything both
image tools rely on (it makes real, billed calls).

**OpenAI grants model access per project, not per account.** A key from a project that has not been
granted the chosen model gets a `403`, which both image tools turn into an error naming the model
and the project. The model list (`GET /v1/models`) can show a model the project still cannot call,
and OpenAI validates a request body before it checks access, so there is no free way to check
access ahead of time. The first real call is where it shows up.

**What an illustrated video costs.** A character's first asset is a generation; every later pose is
an edit of it, and an edit sends the reference image as input. An edit costs about three times the
tokens of a generation (1834 against 608 for a portrait, measured), so a character sheet's cost is
mostly its later poses.

### Agent

There is **no agent setting**. Which agents are installed, which one is the default, and each one's
models live in the `agents` table, written by `python onboard.py --install-agent <name>` — see
[The Agent Layer](../developer/07-agent-layer.md#agents). An agent's default model is the first of its own
models.

The former install-wide `agent_model` key is gone: `POST /settings` rejects it as an unknown key,
and the baseline migration deletes any leftover row from an old install, once, on upgrade
([Database](../developer/03-database.md#migrations)).

The reasoning that kept that key free-text still holds, in a new place. Model names change faster
than this repo does, so there is still no hardcoded catalog. Instead, each model is probed against
the installed CLI when the agent is installed, and a model that stops working later is caught by the
poller from the agent's output — see [the agent layer](../developer/07-agent-layer.md#models).

A video's own model, `videos.agent_model`, is chosen at the topic checkpoint and must be one of its
agent's models.

**The agent's effort level is not a settings key either**, for the same reason: it lives on the
agent row (`agents.effort`, default `high`) and is overridable per video
(`videos.agent_effort`). See [the agent layer](../developer/07-agent-layer.md#effort).

### User preferences

| Key | Type | Default | Notes |
|---|---|---|---|
| `user_preferences` | str | `""` | Free text: the operator's standing preferences for every video. At most 6000 characters (`MAX_USER_PREFERENCES_CHARS`); surrounding whitespace is trimmed, line breaks are kept, and a NUL character is rejected. Not masked |

Edited on the dashboard's **Preferences** tab. The agent receives it on every run, and how depends on
how the run started:

- **Scheduled runs:** `scripts/poll.py` fences it into every prompt it builds (pipeline, research and
  script profile) as a `USER PREFERENCES` block.
- **Interactive sessions:** `get_pipeline_status()` returns it as `user_preferences`, and the skills
  and `/tubematic-submit-new-job` read it there.

See [the agent layer](../developer/07-agent-layer.md#user-preferences) for the block and its wording. Empty means
no block at all, so an install that never opens the tab sends exactly the prompts it did before.

**Why the cap.** `poll.py` passes the whole prompt to the agent CLI as one command-line argument, and
Linux limits a single argument to 128 KiB (`MAX_ARG_STRLEN`). Text past that would make every agent
run fail with `E2BIG`. 6000 is far below that limit because the text is paid for in tokens on every
tick. A NUL character is rejected for the same reason: `exec` refuses an argument that contains
one, so a stored NUL would fail every scheduled run until someone cleared the setting.

The tab's counter stops input at the cap and counts the way the API does, so an emoji is one
character, not two ([why that needed care](../developer/04-settings.md#user_preferences-counts-code-points)).

### Publishing

| Key | Type | Default | Notes |
|---|---|---|---|
| `publishing_enabled` | bool | `false` | Off by default, so an install with no publishing account behaves exactly as it did before the feature existed — `VIDEO_APPROVED` reads as terminal |

Named `publishing_enabled` rather than anything auto-sounding: with this key alone, every step of
publishing stays human-driven. See [Publishing](06-publishing.md).

### Auto Pilot

| Key | Type | Default | Notes |
|---|---|---|---|
| `auto_pilot_enabled` | bool | `false` | Lets the render worker approve every human checkpoint and post the video, for the projects selected on Settings → Auto Pilot. On with no project selected, it does nothing |
| `auto_pilot_gap_mins` | int | `240` | The shortest time between two posts on one account, in minutes. 0 to 10080 (a week). The dashboard takes minutes or hours |
| `auto_pilot_max_in_flight` | int | `0` | How many videos may be in progress before Auto Pilot stops voicing new scripts and approving topics: voiced and unpublished videos in Auto Pilot projects, plus every post waiting to go out, including posts scheduled by hand. Finished videos are still approved and scheduled. Size it in days of posting. 0 to 500; 0 means no limit. Was `auto_pilot_max_scheduled` before v1.2.3. See [Publishing → the in-progress limit](06-publishing.md#the-in-progress-limit) |

All three are edited on **Settings → Auto Pilot**, which saves them through `POST /autopilot` together
with the project list, behind a confirmation. `POST /settings` accepts them as well, with no
confirmation. Read [Auto Pilot](06-publishing.md#auto-pilot) before turning it on: it spends money
and posts publicly with no human review.

### Notifications

| Key | Type | Default | Notes |
|---|---|---|---|
| `discord_webhook_url` | secret | `""` | The channel webhook messages are posted to. `secret`-typed because the URL *is* the credential — anyone holding it can post to that channel |
| `notify_topic_proposed` | bool | `false` | Announce newly proposed topics, bundled one message per research run |
| `notify_script_ready` | bool | `false` | Announce a script waiting at its human checkpoint |
| `notify_video_ready` | bool | `false` | Announce a finished render waiting for sign-off |
| `dashboard_base_url` | str | `""` | Where the dashboard is reachable from wherever Discord is read, e.g. `http://192.168.1.20:3000`. Blank means messages carry no links |

Notifications are off in **two independent ways** — no webhook URL, and no trigger enabled — so an
install that never opens this tab behaves exactly as it did before the feature existed.

The one exception to the triggers is the **stuck-in-voicing alert**. It is sent whenever a webhook URL
is set, whatever the triggers say. The triggers choose which routine checkpoints are announced, and
a video that nothing is voicing is a stuck pipeline, not a checkpoint. See
[Troubleshooting](08-troubleshooting.md#voice).

`dashboard_base_url` has no default and none can be guessed: the container has no idea what
hostname a human reaches it by. A blank value omits links rather than emitting a broken one.

`POST /settings` checks a webhook URL twice: its shape, with a pure regex, and then its liveness,
with an unauthenticated `GET` on the URL that returns the webhook object and sends no message.
Only a definitive rejection (`401 Invalid Webhook Token`, `404 Unknown Webhook`) refuses the save —
a timeout, a DNS failure or a `5xx` stores the URL anyway, on the same tri-state rule the
[onboarding key checks](../developer/04-settings.md#rejection-signatures) follow. Refusing a save because Discord is having a
bad afternoon would make Settings un-saveable for a reason that has nothing to do with what was
typed.

See [Notifications](../developer/02-pipeline.md#notifications) for what triggers a message and when it arrives.

### Costs

There are no cost keys in `SETTINGS_SPEC`. What a call cost is computed from the usage the
provider reported and a table of model prices — see
[Database — `usage_events`](../developer/03-database.md#usage_events-usage_event_videos-and-model_prices) for
the ledger itself. This section is where those prices come from.

**Every figure is an API list price.** It does not reflect a subscription, plan credits or a
discount, and the dashboard says so beside every total. That is deliberate: an install cannot know
what its accounts actually pay, but it can price every call consistently, which is what comparing
videos, models and stages needs.

**How each provider is costed:**

| Provider | Recorded as | Priced from |
|---|---|---|
| Gemini (review, mining; scene images before 2.0.0) | Tokens from `usageMetadata` | The price table. The Gemini image models stay in the shipped price table so past image calls stay priced |
| OpenAI (images, characters) | Tokens from the response's `usage` | The price table |
| Codex sessions | Tokens from `codex exec --json` | The price table |
| Claude Code sessions | `modelUsage` from `claude -p --output-format json` | **Claude's own `costUSD`** (its list-price figure) |
| OpenCode sessions | Per-message tokens and `cost` from OpenCode's session API | **OpenCode's own `cost`** |
| ElevenLabs (voice, previews) | Plan credits, from the `character-cost` response header | **Never priced** — shown as credits |

**ElevenLabs is shown in credits, not dollars.** Installs are assumed to be on a subscription,
where every call draws from a prepaid monthly credit pool; a dollar figure would be an allocation of
the plan fee, not spend. The header is exact — it is the number of credits the pool actually lost,
with the model's discount already applied.

**Where a rate comes from, per model and never per field:**

1. A **manual** rate typed on the dashboard's Settings → Costs tab. Never touched by a sync.
2. The **synced** rate: OpenRouter's public model list (`/api/v1/models`) when it lists the model,
   LiteLLM's `model_prices_and_context_window.json` only when it does not. Today that makes the
   OpenAI image models the only LiteLLM ones. OpenRouter is preferred because every model uses one small
   set of fields, where LiteLLM's field names vary per model and have been dropped from an entry
   within months.
3. The **built-in snapshot**, `tubematic_core/prices_snapshot.json`, shipped with each release — so
   a fresh install prices correctly offline, before its first sync.
4. Otherwise the call is **unpriced**: its units are stored, its cost is `NULL` (never `0`), and it
   is counted beside every total. Adding a manual rate fills in that model's unpriced calls.

One model's rates always come from one source: mixing fields from two feeds would make a wrong
figure impossible to trace. Neither feed is authoritative — both are third parties reading the
vendors' pricing pages; the vendor's page is the authority when they disagree.

A rate the table lacks is handled by fixed rules: thinking tokens bill at the output rate (exact —
every provider bills them as output); audio or image input without its own rate falls back to the
input rate and is marked *estimated*; anything else missing makes the call unpriced. A model with
long-prompt price tiers is priced at its base rate and marked *estimated*, because usage arrives as
totals and the tier that applied is unknowable.

**The sync** runs weekly in the render worker (on the same settings-row throttle as the metrics
poll, so it survives restarts and never starves rendering) and on demand from Settings → Sync now.
Both feeds are fetched whole. It only touches models in use (the snapshot's list, anything already
recorded, and the installed Codex agent's models), never overwrites a manual rate, rejects a move of
more than 5× as upstream breakage, logs every change with its old and new value, and is
all-or-nothing: any failure keeps every existing price and records the error. **Prices are never
fetched at call time** — a render must not depend on GitHub or OpenRouter being up.

### Credentials

| Key | Type | Default | Consumer |
|---|---|---|---|
| `elevenlabs_api_key` | secret | `""` | Voice generation, voice previews |
| `gemini_api_key` | secret | `""` | Optional. Topic mining and AI review. Unset means mining is off — left out of the active strategies, and refused if switched on — and review is skipped |
| `openai_api_key` | secret | `""` | Required. Scene images and the Illustrated style's character cut-outs. Unset means `generate_image` fails and `illustrated` is refused wherever a style is chosen |
| `youtube_transcript_api_key` | secret | `""` | Script-profile transcript fetching |
| `postforme_api_key` | secret | `""` | Publishing and analytics |

**Keys are stored in the database, not in a file.** A key changed on Settings → API Keys applies
to the next call, with no restart. The dashboard and the API show only a mask — eight bullets and the
last four characters — and saving the page without retyping a key leaves it unchanged. The flip side
is that the database file, `~/.tubematic-data/data/tubematic.db`, holds every key in plain text:
treat it, and any backup of it, as a secret. Onboarding checks each key with its provider as you type
it and refuses one the provider rejects; a provider it cannot reach does not block you. See
[How credentials are stored](../developer/04-settings.md#how-credentials-are-stored).
