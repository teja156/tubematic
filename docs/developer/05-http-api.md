# HTTP API

The Pipeline API is a Flask app in `renderer/api/`. It is what the dashboard talks to (through its
proxy), what the cron poller queries, and what any external tooling should use.

| | |
|---|---|
| Container | `tubematic-api` |
| Port | **4000** |
| Prefix | none — every route is at the app root |
| Content type | JSON in, JSON out |
| Authentication | `Authorization: Bearer <api_token>` on every route but the two health probes |

**Every route needs the API token**, from `~/.tubematic-data/secrets/api_token`; without it, or with a
wrong one, the answer is `401 {"error": "unauthorized"}`. That includes a path that does not exist, so
a route added later is covered by default. From the host:

```bash
curl -H "Authorization: Bearer $(cat ~/.tubematic-data/secrets/api_token)" http://localhost:4000/settings
```

The check (`renderer/api/api_auth.py::install_auth`) is installed on the **app**, not the pipeline
blueprint, so it covers every blueprint, and it exempts the health routes **by endpoint name, never
by path prefix**, so `/healthz-anything` is not accidentally open. `server.py` refuses to start
without the token file rather than starting open. Where the token comes from and how it is rotated
are in [Infrastructure — Authentication](16-infrastructure.md#authentication).

`renderer/api/server.py` builds the app and registers the pipeline blueprint at import time.
`renderer/api/pipeline.py::create_pipeline_blueprint` reads `TUBEMATIC_DB` **once**, when the
blueprint is constructed, and closes over it for the life of the process.

---

## Health

These two are the only routes that need no token.

| Route | Response |
|---|---|
| `GET /health` | Always `200 {"status": "ok"}` |
| `GET /render/health` | Runs `chromium --version`. `200 {"status":"ok","chromium":"…"}`, or `500 {"status":"error","detail":"…"}` on a non-zero exit |

`GET /render/health` handles only the non-zero-exit case explicitly. A missing Chromium binary or a
process that outruns the 10-second timeout raises through to Flask's default HTML error page rather
than the JSON shape above.

---

## Dashboard login

### `POST /auth/login`

Checks the dashboard password for the dashboard's own login route, which cannot read the database
the hash lives in. It needs the API token like every other route; the dashboard sets the session
cookie itself on a `200`.

| Body | `{"password": "…"}` |
|---|---|
| `200` | `{"ok": true}` |
| `400` | Missing, empty, non-string, or longer than 1024 characters — refused before hashing, because scrypt is deliberately slow |
| `401` | `{"error": "wrong password"}` |
| `429` | Too many failed attempts; `Retry-After` says how long. After five failures in a row each attempt waits `2^n` seconds, up to 15 minutes, and the password is **not checked** while locked. A success resets it, and so does an API restart. Also `Retry-After: 1` when another login's check is still running: only one runs at a time |
| `503` | No password is set yet: `python onboard.py --set-password` |

The backoff is install-wide rather than per client: every login arrives from the dashboard
container, and a forwarded client address can be forged.

**Only one password check runs at a time**, and a login that finds one running is refused at once
rather than queued. A check that has passed the backoff hashes (about 32 MiB, deliberately slow)
before its result is recorded, so without this a burst of concurrent logins — reachable without a
session, through the dashboard's login page — would all pass the backoff and hash together. Refusing
instead of queueing keeps request threads from piling up as well as memory.

---

## Videos

**Archived videos** (files deleted, row kept — see [Database](03-database.md#videos)) are left out of
`/stats`, `GET /videos` by default, `/videos/actionable`, `/videos/workable` and `/pipeline/status`'s
counts, so they neither show on the board nor reach the agent or the research pending cap.
`GET /videos/<video_id>` still serves them.

### `GET /stats`
`200 {"<STATUS>": <count>}` across every non-archived video. `{}` on an empty database.

### `GET /videos`
Query params `status`, `project_id`, `strategy` — exact match, ANDed. Ordered `created_at DESC`.
`archived` is opt-in: omitted excludes archived rows, `archived=only` returns just those (the
Archive page), `archived=include` returns both. Any other value is a `400`.

`gemini_feedback` is clipped to 1200 characters in list responses, and a `gemini_feedback_truncated`
boolean is added. Fetch the single video to get the whole thing.

### `GET /videos/actionable`
Videos sitting at a human checkpoint — `TOPIC_PROPOSED`, `SCRIPT_READY`, `VIDEO_READY` — oldest
first. This is what the dashboard's Quick Actions inbox renders.

### `GET /videos/workable`
Videos the agent may act on autonomously, oldest first, projected to `id`, `topic`, `status`,
`agent_model`, `agent_effort`, `agent_id`, `updated_at`. Built for the cron poller, which starts one
session per video under that video's own agent, model and effort, oldest first — see
[The Poller](13-the-poller.md). A video flagged stuck (`agent_stuck_at` set) is left out:
the poller must not start a session for it until a human acts.

### `GET /videos/<video_id>`
Full row plus `comments[]` in chronological order. `gemini_feedback` is never clipped here.
`404 {"error": "Video not found"}`.

This route and `GET /videos` both add two computed fields. `effective_voice_id` is the voice the
video will be voiced with: its own `voice_id`, else the install default, or `""` when neither is on
the roster. `voice_conflicts` is `{voice_id: reason}` for every roster voice whose model cannot speak
the video's script. It is computed by the same check that makes `PATCH` refuse such a voice with a
`409`, so a picker that disables these voices can never disagree with the server. It is always empty
at `TOPIC_PROPOSED`, even when a topic revision left an old script stored, because approving the
topic has the script rewritten for whichever voice is picked. An unscripted video
has none. See [The model follows the voice](08-scripting-and-voice.md#the-model-follows-the-voice).

Every single-video response also carries `voice_info`, for the modal's read-only Voice rows. That
covers this route, `PATCH /videos/<id>`, `POST /videos`, `POST /videos/manual` and
`POST /videos/<id>/agent-retry`. `GET /videos` never carries it, because computing it reads the
usage ledger, and paying that on every row of every board refresh buys nothing the list shows.

```json
{"voice_id": "a1", "name": "Adam", "model_id": "eleven_v3", "model_voiced": true}
```

- **`voice_id`** is the video's own voice, else the install default. Unlike `effective_voice_id`
  it is kept when the voice has left the roster, so a removed voice still shows as its id.
- **`name`** is the roster name, or `""` when the voice is off the roster.
- **`model_id`** is the model the video's latest voicing call was sent with, read from
  [`usage_events`](03-database.md#usage_events-usage_event_videos-and-model_prices), and then
  `model_voiced` is `true`. It comes from the ledger, not the roster, because a voice's model can be
  edited in Settings after the video was voiced, and the roster would then name a model the audio
  was never made with. Before voicing, it is the voice's current roster model, with `model_voiced`
  `false`. The same applies to a video voiced before the ledger existed. It is `""` when neither is
  known.
- **Before voicing** means `TOPIC_PROPOSED`, `TOPIC_APPROVED`, `SCRIPT_READY` and `VOICING`. In these
  statuses an older ledger row is ignored: a revision can send a voiced video back to switch its
  voice, and the old row's model says nothing about the next voicing.

### `POST /videos`
Required: `topic`, `strategy`, `producibility_score`. Optional: `id`, `project_id`, `title`,
`voice_id`, `visual_style`.

| Status | Cause |
|---|---|
| `201` | Created at `TOPIC_PROPOSED`, `video_version` 1. Returns the row, plus `warning` if the title was clipped |
| `400` | `{"error": "Missing fields: [...]"}`; an `id` that is not letters, digits, `_` and `-` (not starting with `-`, at most 128 characters) — it names the video's job directory; a `project_id` that names no project; non-string `title`; `voice_id` not on the roster; `visual_style` not one of `auto` / `motion_graphics` / `stick` / `illustrated`; `visual_style` of `illustrated` while no OpenAI key is stored (the settings row, or `OPENAI_API_KEY`) |
| `409` | `project_id` names a paused domain and `strategy` is not `manual`. The error names the domain and says to skip the candidate. See [Domain pause](02-pipeline.md#domain-pause) |
| `409` | `project_id` names an expired domain (it holds `topic_cap` topics already) and `strategy` is not `manual`. The error names the domain, its count and its cap, and says to skip the candidate. See [Topic cap](02-pipeline.md#topic-cap) |

With no `voice_id` given, the video starts with its project's `default_voice_id`, whatever its
strategy, as long as that voice is still on the roster; otherwise it is left `""` (the install
default). The voice is **seeded** onto the row, not looked up later, so changing a project's default
never changes videos already filed there.

With no `visual_style` given, a `curriculum` video inherits its project's `default_visual_style`;
every other strategy starts at `auto`. An inherited `illustrated` is kept even with no OpenAI key —
a stored choice is never silently rewritten — and is refused instead by the approving `PATCH`, which
carries `visual_style`, at the topic checkpoint and before anything is spent.

A `curriculum` video likewise starts with its project's `default_script_profile_id`, while that
profile is still `READY` and not deleted; every other strategy, and a stale default, starts with
`script_profile_id` `""` (the generic style). `POST /videos` takes no `script_profile_id` of its own —
the profile is chosen at the topic checkpoint, where the seeded one is preselected.

An over-length `title` is **clipped** at a word boundary to 70 characters with a warning, not
rejected — a create is often mid-research-run and failing it would lose the topic.

The new video's `agent_id` is dealt from the shuffled assignment deck of live agents — see
[Assignment](07-agent-layer.md#assignment). An `agent_id` in the body is ignored.

`strategy` and `producibility_score` are **not validated by this route**; the MCP server's
`create_video` does validate them.

### `POST /videos/manual`
The dashboard's **New Video** page. Required: `title` (at most 70 characters) and `topic`, both
non-blank. Optional: `approve` (bool, default `true`), `agent_id`, `agent_model`, `agent_effort`,
`script_profile_id`, `visual_style` and `voice_id`.

| Status | Cause |
|---|---|
| `201` | Created at `TOPIC_APPROVED` (or `TOPIC_PROPOSED` with `"approve": false`), `strategy` `manual`, `producibility_score` 0, in the `manual` project. Returns the row |
| `400` | A missing or blank `title` or `topic`; a `title` over 70 characters; a non-boolean `approve`; a pick of the wrong type, such as `false` or `0` where a string is expected (only an absent or `null` pick means its default); an `agent_effort` outside `low`/`medium`/`high`/`xhigh`/`max`; an `agent_model` with a space or a leading `-`; an `agent_id` that is not a live agent; an `agent_model` not in that agent's model list; a `script_profile_id` that is not a READY profile; a `voice_id` not on the roster; an unknown `visual_style`, or `illustrated` with no OpenAI key stored |

It is a separate route from `POST /videos` because the two callers want opposite things. A research
run creates a video mid-run, where failing the create would lose the topic, so `POST /videos` clips
an over-long title and deals the agent whatever the body says. A person at the form can fix a long
title, and chose the agent on purpose. So this route **refuses** an over-long title and **keeps** a
picked `agent_id`. With no `agent_id`, the agent is dealt from the deck like any other new video, so
the configured weights still apply. `agent_model` is checked against whichever agent the video ends
up with. A refused model rolls the deal back, so a bad request never uses up a card.

Every video it creates goes into the project `manual`, named **Manual Videos**. That row is created
by the first request, with `INSERT OR IGNORE`, so renaming it on the Projects page sticks. Nothing is
written until every field has passed, so a refused request never leaves an empty domain behind. The
video is left unscored on purpose (see
[Where topics come from](02-pipeline.md#where-topics-come-from)). With no `voice_id`, the video gets
the `manual` project's `default_voice_id` if it has one on the roster, like any other new video in a
domain. That default can only be set once the domain exists, which is after the first manual video.

### `PATCH /videos/<video_id>`

The main write path. The body may contain any subset of:

`status` · `title` · `script` · `video_version` · `youtube_url` · `gemini_feedback` · `voice_id` ·
`agent_id` · `agent_model` · `agent_effort` · `script_profile_id` · `visual_style` ·
`publish_title` · `publish_description`

plus the optional guard `onlyIfCurrentStatus`. **Any other key is silently dropped**, including
`tts_text` and `resolved_visual_style` — both are written only by the MCP server. The four job-path
columns (`voice_file_path`, `timeline_path`, `scene_config_path`, `video_path`) are the exception:
sending any of them is a `400` and nothing in the request is applied, `status` included. They are
written only by the code that writes the files, and no reader uses them to find a file — see
[Path columns](03-database.md#videos). Refused rather than dropped, so a caller relying on one learns
it at once instead of getting a `200` for a write that never happened. That matters for
`resolved_visual_style` in particular: it records what the agent settled on at scene-config time,
and the dashboard has no business overwriting it.

| Status | Cause |
|---|---|
| `200` | Updated row plus `comments[]` |
| `400` | Any of `voice_file_path`, `timeline_path`, `scene_config_path`, `video_path` present, with nothing applied; unknown-only body (`No updatable fields provided`); `status` not one of the 15 valid values; non-string or over-70-character `title`; `agent_id` blank, non-string, unknown or uninstalled (unless it is the video's current agent); `agent_model` containing a space or leading `-`; `agent_model` not one of the video's agent's models, or that agent uninstalled or not installed; `voice_id` not on the roster; `script_profile_id` not a non-archived `READY` profile; `visual_style` not one of `auto` / `motion_graphics` / `stick` / `illustrated`; `visual_style` of `illustrated` while no OpenAI key is stored; `agent_effort` not one of `low` / `medium` / `high` / `xhigh` / `max` or blank; `script` without both `publish_title` and `publish_description`; either of those non-string, blank, or over its cap (100 / 2000) — the same rule as MCP `update_video`, see [Publishing](14-publishing.md#schema) |
| `404` | Video not found |
| `409` | The video is archived — an archived row is frozen, so a `PATCH` cannot move it back into the pipeline |
| `409` | `script_profile_id` or `visual_style` present while the video is past `TOPIC_PROPOSED` |
| `409` | `agent_id`, `agent_model` or `agent_effort` present while the video is not at a human checkpoint (`TOPIC_PROPOSED`, `SCRIPT_READY`, `VIDEO_READY`) |
| `409` | A model was written on its own and the video's agent changed while the request was in flight |
| `409` | `onlyIfCurrentStatus` did not match — `{"error": "Status precondition failed", "current", "expected"}`. The same shape, with `expected` set to the status the freeze was checked at, when a frozen field was sent and the video changed status mid-request |
| `409` | `voice_id` names a voice (or, as `""`, resolves to the install default) whose model cannot speak the stored script — `{"error", "voice_conflict": true}`, nothing changed. Checked on every request carrying `voice_id`, including an approval that re-sends the video's own voice. That voice passes by construction, because the script was checked against it when written. It is refused only if its model was changed in Settings after the script was written, which is better caught at the checkpoint than at a paid voicing. Never at `TOPIC_PROPOSED` (see `voice_conflicts` above); a voice written there is bound to that status, so it matches no row — `409 Status precondition failed` — if the video moved on mid-request |

**`agent_id` hands the video's next piece of work to another agent**. It must name a
live agent from `GET /agents`; the video's current agent is accepted as a no-op even if since
uninstalled. There is no blank — `NULL` ("the default at dispatch") is only ever the state a video is
created in. **A change clears `agent_model`** to `""` inside the same `UPDATE`, unless the body also
sets `agent_model`, which is then checked against the new agent. `agent_effort` is kept. The deal
(`agent_deck`) is untouched: an override neither takes nor returns a card.

**`agent_model` is checked in two stages.** Its shape is checked first. Then, *after* the freeze
check, a non-empty value must be one of the models of the agent the video will have once the request
lands — the body's `agent_id` if it has one, else the pinned `agent_id`, else the default agent —
and that agent must be live. The ordering means a late edit reads as `409` frozen rather than as a
model problem. `""` always passes and means the agent's default model. A model sent without
`agent_id` is written only if the video is still on the agent it was checked against — the `UPDATE`
carries `AND agent_id IS ?` — so a concurrent reassignment makes it `409` instead of pinning a model
the new agent lacks.

**`agent_effort` needs only one stage.** The five levels are the same for every agent, so
membership in them is the whole check — there is no per-agent list to consult, and no installed
agent is required. `""` means the agent's own `effort`.

Two behaviours are worth understanding before you build on this route.

**`onlyIfCurrentStatus` is a real compare-and-swap.** The guard is part of the
`UPDATE … WHERE id = ? AND status = ?` statement, not a separate read. On a mismatch a fresh
`SELECT` reports the actual current status, so the error is never stale. Use it for every
status-changing write; the dashboard does. A write carrying a frozen field is bound the same way
even without it: the `UPDATE` also requires the status the freeze was checked at, so a video that
moves on between the check and the write is refused rather than changed after it was handed on.

**Unlike `title`, an over-length title is rejected here rather than clipped** — an update is a
deliberate edit, so silently truncating it would be wrong.

**No transition graph is enforced.** `status` is validated against the set of legal values, not
against the state machine. Nothing at this layer stops a client from jumping `TOPIC_PROPOSED`
straight to `PUBLISHED`. Sequencing lives in the dashboard's UI and the agent's skills.

**A body carrying `status` also releases a stuck video**: it resets `agent_no_progress_count` to 0
and clears `agent_stuck_at`. A status change is a human acting on the video. A `PATCH` without
`status` — a rename, say — leaves both alone, because it is not a decision about why the agent could
not move the video.

### `POST /videos/<video_id>/agent-outcome`
Called by the cron poller after every pipeline session, with body
`{"start_status": "<STATUS>", "session_key": "<key>"}` — the status the session started at, and an
optional key naming the session. This route alone decides whether the session made progress,
because the agent CLIs' exit codes cannot be trusted to (see
[The Poller](13-the-poller.md#success-is-read-from-the-database)). One atomic `UPDATE`:

- **The status differs from `start_status`** — whoever changed it — so `agent_no_progress_count`
  resets to 0.
- **The status is unchanged**, so the count goes up by one. At 3 (`AGENT_NO_PROGRESS_CAP`),
  `agent_stuck_at` is stamped and a single `agent` comment explains what happened and how to hand
  the video back.

`updated_at` is never touched: it is the poller's queue order and the clock the render worker uses
to spot a video stalled in `VOICING`.

**A repeated `session_key` is not counted again.** The video keeps the key of the last outcome it
counted (`agent_last_outcome_key`), and a report carrying the same key changes nothing and answers
`"replayed": true`. That is a successor supervisor finishing a session whose supervisor died after
reporting it but before deregistering it; without the key, the replay would count a second session
without progress and could flag the video stuck early. One stored key is enough: a video has at
most one session at a time. A report with no key is counted every time.

| Status | Cause |
|---|---|
| `200` | `{"status", "count", "stuck", "replayed"}` — the video's status now, its no-progress count, whether it is stuck, and whether this report repeated an already-counted `session_key` |
| `400` | `start_status` missing or not one of the 15 valid values; `session_key` not a string of 1 to 100 characters |
| `404` | Video not found |

An archived video is reported as it stands and never counted.

### `POST /videos/<video_id>/agent-retry`
The dashboard's **Retry agent**: resets `agent_no_progress_count` to 0 and clears `agent_stuck_at`,
leaving the status alone, so the poller picks the video up on its next pass. `200` with the updated
row plus `comments[]`; `404` for an unknown video; `409` for an archived one.

### `POST /videos/<video_id>/comments`
Body `{author, content}`. `author` defaults to `"human"` and must be `"human"` or `"agent"`.
`201 {"ok": true}`, or `400` on an empty `content` or a bad author, `404` if the video is unknown.

The dashboard calls this only from **Request Revision** (see [Dashboard](15-dashboard.md#actions)),
but the route itself does not check the video's status. That is deliberate: it was never the only
way in. The agent's `add_comment` tool and the render worker write comments straight to SQLite, so
a status check here would restate the UI's rule without enforcing anything.

### `DELETE /videos/<video_id>`
Deletes the video's rendered mp4 and its job directory, clears `video_path`, and archives the row by
setting `archived_at`. **There is no hard delete** — this is the only meaning "delete" has, and it is
the same operation the render worker's retention sweep performs. A `human` comment is left on the
video.

| Status | Cause |
|---|---|
| `200` | `{"ok": true, "archived_at", "file_errors": []}`. A file that could not be removed is listed in `file_errors`; the row is archived regardless |
| `404` | Video not found |
| `409` | Already archived |
| `409` | The video is `VOICING`, `RENDER_QUEUED`, `RENDERING` or `PUBLISHING` (something is working on it), `SCHEDULED` (a post will go out), or `VOICE_READY` / `REVISION_REQUESTED` — `{"error", "current"}` |

The last two statuses are blocked because an agent can hold a scene-work claim there, and that claim
lives only inside the MCP process, out of Flask's sight. Blocking the statuses the claim can exist in
is stronger than reading the claim, and keeps this API free of any dependency on the MCP server being
up. The cost is that an *unclaimed* video at either status cannot be deleted.

The status check is part of the archiving `UPDATE`'s own `WHERE` clause, so it cannot race a render
claim or a status change.

### `GET /retention/backlog`
What `unpublished_retention_days` would free: every non-archived `FAILED` and `TOPIC_REJECTED` video,
whatever its age and whether or not the key is on, since its job is to show the opt-in is worth
turning on. Read-only.

```json
{"failed": {"count": 3, "bytes": 1073741824}, "rejected": {"count": 12, "bytes": 0}}
```

`bytes` is the rendered mp4 plus everything under the job directory. A missing or unreadable file
counts as 0 rather than failing the request. So does a job directory that is not a direct child of
the jobs directory: video ids are caller-supplied, and an id such as `.` would otherwise size the
whole tree, the same reason `DELETE` refuses to remove one. See [Retention](11-rendering-and-review.md#retention).

---

## Projects

| Route | Behaviour |
|---|---|
| `GET /projects` | All projects, `created_at DESC`. Each row also carries two derived fields, never stored: `topic_count` (every video ever filed into it, archived and rejected included) and `expired` (`topic_count >= topic_cap`). See [Topic cap](02-pipeline.md#topic-cap) |
| `POST /projects` | Upsert. Requires `name`; `description` must be a string (absent or `null` stores `''`) of at most 2000 characters, counted in code points, and the length is checked only when the description *changes*, so one stored longer before the limit existed still saves with every other edit; `id` defaults to `proj_<hex>`, must be a string, and a **new** one must be letters, digits, `_` and `-`, not starting with `-`, at most 128 characters, since it names the domain's output directory — an existing domain is not checked, so one filed earlier under an odd id stays editable; `status` must be `active` or `paused`, and `paused` is a `400` unless `is_curriculum_seed` is true; `default_visual_style` must be `auto` / `motion_graphics` / `stick` / `illustrated`, or `''` for none, and *changing* it to `illustrated` is a `400` while no OpenAI key is stored — re-sending an unchanged default is not, since every edit through this route re-sends it. `default_voice_id` must be on the roster, or `''` for the install default — again checked only when it *changes*, so a voice later removed from the roster does not block every other edit to the domain. `default_script_profile_id` must be a string naming a `READY`, undeleted script profile, or `''` (or `null`) for none — any other non-string, `false` and `0` included, is a `400` rather than read as none — checked only when it *changes*, on the same reasoning. `topic_cap` must be a whole number from 25 to 750 (`true`, `"100"` and `100.5` are `400`s); absent or `null` means the default, 100. A cap below the domain's count is accepted and expires it at once. `201` with the row, including `topic_count` and `expired`. **It is an upsert, so every column it is given is overwritten** — a caller changing one field must send the others back or they are blanked. Because an omitted `status` is written as `active`, clearing the seed flag on a paused domain also reactivates it |
| `POST /projects/<project_id>/status` | Body `{status}`. `400` on a bad value, `404` if unknown, `409` for `paused` on a domain that is not a curriculum seed, `200` with the updated row, shaped like `GET /projects`'s. See [Domain pause](02-pipeline.md#domain-pause) |

---

## Settings

### `GET /settings`
Returns all 40 declared keys, coerced to their types, with `secret` keys masked. See
[Settings](../user-guide/05-settings.md). There is no install-wide model or pronunciation mode: each voice in
`elevenlabs_voices` carries its own `model_id`.

### `POST /settings`
Body: any subset of the 40 keys.

- An unknown key returns `400 {"error": "Unknown settings: [...]. Valid: [...]"}`.
- **The whole write is atomic.** Every value is coerced first; the first failure returns `400` with
  that message and *nothing* is written.
- `image_model` and `character_model` must each be one of the OpenAI image models. `image_provider`
  is gone — OpenAI is the only image provider — so posting it is an unknown-key error.
- A non-empty `discord_webhook_url` is probed with an unauthenticated `GET` on the URL, which sends
  no message. Only a definitive rejection returns `400`; an unreachable Discord stores the URL. See
  [Notifications](../user-guide/05-settings.md#notifications).
- The response is the full settings object, masked exactly like `GET`.

**Masking round-trips safely.** A `secret` value in the request that exactly equals the current
mask of the stored value is dropped before coercion, so a dashboard can `GET`, edit one field, and
`POST` the whole object back without overwriting keys it never touched with mask characters. This
only works against a key that already has a value — a mask-shaped string posted against an empty key
is stored literally.

`pronunciation_mode` and the retired install-wide `elevenlabs_model_id` are not keys. Posting either
is an ordinary unknown-key `400`.

### `POST /voices/<voice_id>/preview`
Generates or replays a cached ElevenLabs sample of a roster voice, spoken with that voice's own
model. An optional body `{"model_id": ...}` names another model instead, which is how the Settings
page lets a human hear a model change before saving it. A missing or non-JSON body is fine.

| Status | Cause |
|---|---|
| `200` | `{path, cached, credits}` — ElevenLabs plan credits the generation spent; `0` for a cache hit |
| `400` | `voice_id` not matching `[A-Za-z0-9_-]+`, not on the roster, or a body `model_id` that is not a supported model — refused before any ElevenLabs call |
| `503` | No ElevenLabs key configured |
| `502` | ElevenLabs rejected the request or the call failed |

The cache key is a hash of `(voice_id, model_id, sample_text)`, so it invalidates itself when a
voice's model changes — the next play is a fresh sample — and it removes the human-typed `voice_id` as a path-traversal surface. A cache hit
costs nothing and makes no outbound call.

A generated preview is **recorded in the usage ledger with no video** — its credits come from
ElevenLabs' `character-cost` header, and it shows up in the Analytics page's Spend tab. Do not
invent a synthetic video id for it: spend that belongs to no video is a first-class case there.

---

## Agents

Installed coding agents — see [Database](03-database.md#agents) and
[The Agent Layer](07-agent-layer.md#agents). These routes are read-mostly. Rows are created, and
their binary, workspace and models changed, only by `python onboard.py --install-agent <name>` on
the host, which validates them against the real CLI. No container has an agent binary, so over
HTTP a human may only pick the default and set each agent's weight.

### `GET /agents`
Every row, archived included, ordered by `created_at` then `id`, with `models` parsed to a list and
`is_default` as a boolean. Archived rows are included because the dashboard still has to label a
video pinned to one. The poller reads this on every pass.

### `PATCH /agents/<agent_id>`
Body: any of `is_default`, `weight`, `default_model` and `effort`.

| Status | Cause |
|---|---|
| `200` | The updated row |
| `400` | Body not a JSON object, including a malformed one; an empty body; any other key, `models` included; `is_default` anything but `true` — `false` is refused with "make another agent the default instead"; `weight` not an integer from 0 to 100 (a boolean is refused); `default_model` not a string, or not one of the agent's installed `models`; `effort` not one of `low` / `medium` / `high` / `xhigh` / `max` (blank is refused here — it is meaningful on a *video*, where it means "follow the agent", but on the agent itself there is nothing to follow) |
| `404` | Agent not found |
| `409` | Agent is uninstalled |

Setting `is_default: true` clears it on every other agent in the same transaction, so only one agent
is ever the default. It cannot be cleared directly, because that would leave the choice to the
"oldest live agent" fallback rather than to a person.

**`default_model` reorders the list rather than adding a column.** An agent's default model is
`models[0]` everywhere — the poller, the MCP `agents` list, the dashboard — so picking one moves it
to the front. It must already be in the list: adding a model means probing it against the real CLI,
which only the host-side installer can do. **`effort` is a plain column**, for the opposite
reason: the levels come from the CLI rather than from what this install probed, so there is no list
to reorder and nothing to validate against.

**There is no `DELETE`.** Uninstalling is `python onboard.py --uninstall-agent <name>` on the host,
because it also removes the skills, commands and MCP registration the install deployed — none of
which the API container can reach. It sets `archived_at` and clears `is_default`, and never deletes
the row, so every video pinned to the agent keeps resolving it. See
[Deployment](07-agent-layer.md#deployment).

---

## Research

| Route | Behaviour |
|---|---|
| `GET /research/strategies` | `{"strategies": [...], "mining_available": bool}` from `settings.active_strategies`. While no Gemini key is stored, `mining_available` is `false` and `mining` is left out of `strategies`; the stored row is untouched, so adding a key brings mining back |
| `POST /research/strategies` | Body `{"strategies": [...]}`. Values must be `curriculum`, `trending` or `mining`. A list containing `mining` is refused with `400` while no Gemini key is stored, and nothing is written. Any other list saved while there is no key keeps a stored `mining`: the caller was only shown the filtered list, so storing it as sent would drop mining for good |
| `GET /research/mining-sources` | `{"youtube_urls": [...]}` |
| `POST /research/mining-sources` | Body `{"youtube_urls": [...]}`, replacing the whole list; `[]` clears it. Every entry must be a YouTube video URL — `youtube.com/watch?v=<id>`, `youtu.be/<id>`, `youtube.com/shorts/<id>` or `youtube.com/live/<id>` (`www.` and `m.` too), with an 11-character id. Each is stored as `https://www.youtube.com/watch?v=<id>`, two URLs for one video are stored once, and the stored list is returned: `200 {"youtube_urls": [...]}`. `400` if the body is not a list, if any entry is not such a URL (the error names every one, and nothing is stored), or if more than 50 distinct videos remain. See [Mining sources](#mining-sources) |
| `POST /research/record-run` | Appends *now* to the rolling 24-hour window. Returns `{research_runs_today, max_research_runs_per_day}` |

`POST /usage/agent-session` is how an agent run's usage reaches the ledger — the poller has no
database access, so it parses each run's JSON output and posts it here. Body
`{session_id, operation, agent, videos: [{video_id, stage}], events: [{service, model, units,
raw, reported_cost_usd, estimated}]}`; `operation` must be `agent_pipeline`, `agent_research`,
`agent_profile` or `agent_unscoped`. Every event is recorded against every listed video. The poller
lists exactly one video for a pipeline session; several videos, and `agent_unscoped`, appear only
in sessions recorded before it ran one video per session, and are still accepted. Returns
`200 {recorded, events}`, or `400` for an unknown operation, an empty `events` list or a missing
`session_id`. **Idempotent per `session_id` and event position:** a payload resent after a timeout
records nothing the first attempt already committed, and still counts those events as `recorded`.
A `200` with `recorded` below `events` means some events were not recorded. See
[The Poller](13-the-poller.md).

**The caps are reported here, not enforced here.** `research_pending_cap`,
`max_research_runs_per_day` and the three per-run caps are surfaced by `GET /pipeline/status`, but
no route in this API rejects a request for exceeding one. `POST /research/record-run` always
succeeds. Enforcement lives in `scripts/poll.py`, which compares the reported numbers before
invoking an agent — see [The Poller](13-the-poller.md).

**Runs are counted on attempt, not on completion.** The poller records the run *before* invoking the
agent. Completion-counting would fail open exactly when the cap matters: a crashed run would leave
the counter at zero and re-fire on every tick.

### Mining sources

**This API stores the mining sources; it never mines.** Mining runs only through the MCP server's
`mine_youtube_topics` ([MCP server](06-mcp-server.md#gemini--mine_youtube_topics)). There used to
be a `POST /research/mine` here that did the same Gemini work in-request. Nothing called it, and it
had neither of the two guards the MCP tool has — every URL checked before the first paid call, and
one run at a time — so it was removed rather than kept in step with a second copy.

**Why the URLs are checked at all.** Each stored URL is handed to Gemini as the `file_uri` of a
paid request. Before the check, any string reached it: `file://` paths, internal addresses and
look-alike hosts included. The rule lives in one place, `tubematic_core/youtube.py`, which this
route and the MCP server's `set_mining_sources` and `mine_youtube_topics` all call. Only the video
id is kept, so a URL's query string never reaches Gemini, and the dashboard's Mining Sources panel
mirrors the rule so its Add button lights only for a URL this route will store.

**The whole list is refused, never trimmed.** A list with one bad entry stores nothing, and the
error names every bad entry. Silently dropping one would leave the person who typed it believing it
is mined. The limit is 50 distinct videos; a run never makes more Gemini calls than
`max_mining_per_run` however long the list is, so the limit bounds the list, not the spend.

Lists stored before this check existed are cleaned by migration `0014`: each URL is rewritten to
the canonical form, repeats are dropped, and anything that is not a YouTube video URL is dropped
and logged — see [Database](03-database.md#settings).

---

## Script profiles

| Route | Behaviour |
|---|---|
| `GET /script-profiles` | Non-archived profiles, newest first, without `markdown`/`corpus_summary` |
| `GET /script-profiles/pending` | Profiles at `PENDING` or `GENERATING`, oldest first. Polled by cron |
| `GET /script-profiles/<id>` | Full profile including markdown. **Serves archived rows too**, so a video that referenced one still resolves |
| `POST /script-profiles` | Body `{name, urls}`. Creates the profile and fetches transcripts |
| `DELETE /script-profiles/<id>` | Sets `archived = 1` and deletes the profile's transcripts. Never a real delete |
| `POST /script-profiles/<id>/record-attempt` | Claims an attempt, or fails the profile once the cap is hit |

`POST /script-profiles` fetches every transcript **synchronously inside the request**, one at a
time, with no delay between calls. Per-URL failures are collected rather than aborting the batch.

| Status | Cause |
|---|---|
| `201` | Created at `PENDING`, plus `transcripts_fetched` and `failures[]` |
| `400` | Empty `name`; `urls` not a non-empty list; more than 10 URLs; **or zero transcripts fetched** — `{"error": "No transcripts could be fetched…", "failures": [...]}` |
| `503` | No `youtube_transcript_api_key` configured |

`record-attempt` returns `409` if the profile is already `READY` or `FAILED`. When `attempt_count`
has reached its cap of 2 it marks the profile `FAILED` and returns **`200`** with
`{"status": "FAILED"}` — that is a successful report of a terminal state, not an error.

---

## Costs

The read side of the usage ledger and the price table behind it. Every dollar figure is an **API
list price** and ignores subscriptions and plan credits; ElevenLabs is reported in plan credits and
never in dollars. See [Settings — Costs](../user-guide/05-settings.md#costs) for where rates come from.

| Route | Behaviour |
|---|---|
| `GET /videos/<video_id>/costs` | `{has_usage, lines, agent, total_usd, credits, unpriced_calls}`. `lines` groups non-agent calls by service, model and operation, each with `calls`, `cost_usd` (`null` when none were priced), `credits`, `unpriced_calls` and `estimated`. `agent` is `null` or `{models, share_usd, session_total_usd, shared, estimated, sessions[]}`, where each session carries its `stage`, `batch_size`, `total_usd` and this video's `share_usd`. `total_usd` adds the agent **share**, never whole sessions |
| `GET /usage/summary?preset=<today\|week\|month>`, `?from=<YYYY-MM-DD>&to=<YYYY-MM-DD>` or `?since=<ISO>` | Spend for a range. `preset` is resolved here, ending today in the host timezone (a week starts on Monday) — the dashboard sends presets by name because its own idea of the host zone is UTC until it loads. `from`/`to` are **inclusive days in the host timezone**, converted to a UTC `[since, until)` window, each end at its own local midnight so a range across a DST switch stays exact; for either form the response echoes `from`, `to`, `until` and the `timezone` the days were cut in (`UTC` when the host zone cannot be named or loaded). `since` alone is open-ended (default: the start of this UTC month) and is what other callers use. Fields: `since`, `until`, `total_usd`, `videos`, `research`, `agent_other`, `other`, `video_count`, `unpriced_calls`, `voice_credits`, `preview_credits`, `estimated`, and `elevenlabs_pool` — `{tier, used, limit, resets_at_unix}` from ElevenLabs, or `null` when the key lacks the optional `user_read` permission or the call fails. `400` for a malformed `since`, an unknown `preset`, a `from` without a `to` (or the reverse), a date that is not a real `YYYY-MM-DD` day, `from` after `to`, a range whose UTC boundaries a datetime cannot hold (`to=9999-12-31`, or year-1 midnight east of UTC), or more than one of `preset`, `from`/`to` and `since` |
| `GET /prices` | Every model in use with the rates that would price it now (`rates` in USD per token), their `source` (`manual`, `openrouter`, `litellm`, `built-in`, or `null` for none), `tiered` and `effective_from`; `unpriced` — models with unpriced calls and how many; `unit_kinds`; and the sync state `last_sync_attempt_at`, `last_sync_ok_at`, `last_sync_error` |
| `POST /prices/sync` | Runs the price sync now. Returns `{ok, updated, rejected, missing, error}` — a failure is a `200` with `ok: false`, and keeps every existing price |
| `POST /prices/override` | Body `{service, model, rates: {unit_kind: usd_per_token}}`. Sets a manual rate that no sync overwrites, and prices that model's unpriced calls — calls already priced keep the price they were charged. `200 {ok, repriced}`; `400` for a missing name, an unknown unit kind, a non-positive rate, or `service: "elevenlabs"` |
| `DELETE /prices/override?service=&model=` | Drops a manual rate. The model falls back to its synced or built-in rate |

Usage is **written** through `POST /usage/agent-session` (see [Research](#research)) and, for every
other call, directly by the process that made it.

---

## Publishing and analytics

Eleven further routes cover publishing an approved video now or at a scheduled time, cancelling a
scheduled post, recovering one that failed while publishing, reading performance back, and
configuring [Auto Pilot](14-publishing.md#auto-pilot). They are documented with the rest of that subsystem in
[Publishing](14-publishing.md#http-routes). Those that reach postforme return `503` when publishing
is disabled or unconfigured; the two `/autopilot` routes do not.

`GET /publishing/accounts` · `POST /publishing/accounts` · `POST /publishing/accounts/connect` ·
`GET /videos/<id>/publications` ·
`POST /videos/<id>/publish-prefill` · `POST /videos/<id>/publish` ·
`POST /videos/<id>/publish/retry` · `POST /videos/<id>/schedule/cancel` · `GET /analytics` ·
`POST /analytics/refresh` · `GET /autopilot` · `POST /autopilot`

---

## Pipeline control

### `POST /pipeline/pause`
Body `{"paused": <bool>}`, strictly a boolean. `200 {"paused": …}`.

### `GET /pipeline/status`
The system's single status readout. Returns:

`paused` · `workable_count` · `proposed_count` · `video_counts` · `last_research_at` ·
`active_strategies` · `mining_available` · `research_pending_cap` · `research_runs_today` ·
`max_research_runs_per_day` · `research_window_resets_at` · `timezone` · `timezone_label` ·
`pending_script_profiles` · `version`

`active_strategies` leaves `mining` out while no Gemini key is stored, and `mining_available` says
so; the scheduled poller builds its research prompt from this list, so a run is never told to mine
without a key. The two timezone fields come from `renderer/api/hosttz.py` and exist for the dashboard. See
[Time](#time) below. `version` is the installed version from `VERSION`, read through
`tubematic_core.version.version()`; the dashboard's version badge shows it.

---

## Status sets

Three sets drive routing. All three are duplicated in `mcp/server.py` and
`dashboard/lib/types.ts` and carry `# Keep in sync` comments.

```python
VALID_VIDEO_STATUSES = {           # 15 — everything a status column may hold
    "TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED", "SCRIPT_READY",
    "VOICING", "VOICE_READY", "RENDER_QUEUED", "RENDERING", "VIDEO_READY",
    "VIDEO_APPROVED", "REVISION_REQUESTED", "SCHEDULED", "PUBLISHING", "PUBLISHED",
    "FAILED",
}

ACTIONABLE_STATUSES = {            # 3 — a human decides (or Auto Pilot, per project)
    "TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY",
}

WORKABLE_STATUSES = [              # 4 — the agent may act unattended
    "TOPIC_APPROVED", "VOICING", "VOICE_READY",
    "REVISION_REQUESTED",
]

# VIDEO_APPROVED is deliberately absent: publishing is never agent work, so an
# agent woken for one of these videos would have nothing it is allowed to do.
```

---

## Logs

### `GET /logs`

Structured log records, newest first. This is the dashboard's only route to the logs — it has no
`/logs` mount and no Docker socket — so the endpoint is the whole of its access.

| Parameter | Default | Notes |
|---|---|---|
| `service` | all | One of `api`, `mcp`, `renderer`, `poll`. Anything else is a **400** |
| `level` | all | A **minimum**, not an exact match: `warning` also returns errors |
| `video_id` | — | Exact match |
| `profile_id` | — | Exact match |
| `q` | — | Case-insensitive substring, matched against the whole record |
| `limit` | 200 | 1–2000. Non-integer or out of range is a **400** |

```json
{
  "records": [
    {"ts": "2026-09-06T14:20:10Z", "service": "renderer", "level": "info",
     "message": "render complete", "video_id": "vid_abc"}
  ],
  "count": 1,
  "limit": 200,
  "services": ["api", "mcp", "renderer", "poll"],
  "levels": ["debug", "info", "warning", "error"]
}
```

`services` and `levels` are echoed so a client's filter lists are not a second copy of the server's
allowlist. Records carry `video_id`, `profile_id` and `request_id` only when the writer had them.

**`service` is optional on purpose.** One video's trail spans the renderer that rendered it, the MCP
tools that voiced and staged it, and the API calls that moved it between statuses, so
`GET /logs?video_id=…` — which is what the video modal's Logs tab issues — has to read all four.

Filenames are built from an allowlisted service name plus a date; nothing from the request reaches a
path. Malformed lines are skipped rather than failing the request, since a half-written final line is
normal in a file being appended to. Retention is a writer's concern: this endpoint reads whatever
files still exist and never deletes one. See [Settings](../user-guide/05-settings.md#logs) and
[Troubleshooting](../user-guide/08-troubleshooting.md#logs).

---

## Time

Timestamps are **stored in UTC and displayed in the host's local zone.** `updated_at` is the FIFO
ordering key for the render worker's atomic claim, and local time is non-monotonic across DST — a
mix of `Z` and offset-suffixed rows would also sort wrongly as text.

The dashboard container deliberately has **no** `/etc/localtime` mount, unlike the API and worker
containers. It learns the host zone over HTTP from `GET /pipeline/status`. A second source of truth
could disagree with the first, and mounting an env file into the Next.js process for one variable
would have leaked every API key into it.

`renderer/api/hosttz.py` resolves the zone from `TZ`, then `/etc/timezone`, then the
`/etc/localtime` symlink target, returning `None` if all three fail. It returns two values:

- `timezone` — an IANA name, safe to hand to JavaScript's `Intl.DateTimeFormat`.
- `timezone_label` — a human string like `EDT (UTC-04:00)`, computed without tzdata. **Display
  only.** Passing it to `Intl.DateTimeFormat` throws.

---

## Database access

`renderer/api/db.py` provides `conn()`, `set_status()`, `update_fields()` and `add_comment()`, with
WAL mode, foreign keys on, and a `sqlite3.Row` factory. It is used **exclusively by the render
worker**; `pipeline.py` defines its own equivalent connection helper rather than importing it.

Path columns hold **container-absolute** paths and this API stores and returns them as opaque
strings. Nothing reads a location back out of them. The dashboard builds a rendered video's
`/stream/…` URL from its ids (`dashboard/lib/utils.ts::videoStreamUrl`), and turns the
`/output_videos/…` path that `POST /voices/<voice_id>/preview` returns into one with
`dashboard/lib/utils.ts::videoToStreamUrl`.

Schema and migrations: [Database](03-database.md).

---

## Transcripts

`renderer/api/transcripts.py` fetches from `https://www.youtube-transcript.io/api/transcripts`.

- Auth is an `Authorization: Basic <key>` header. Note that this is the *scheme name* only — the key
  is sent raw, not base64-encoded credentials. That is what the service expects.
- One video id per request. The batch response shape is not verified against the live service, so
  the module deliberately never sends more than one.
- `extract_video_id` accepts `youtu.be/`, `?v=`/`&v=`, `/shorts/`, `/embed/` and a bare 11-character
  id.
- Responses are parsed from `data[0].tracks[*].transcript`, falling back to a flat `transcript`
  field, and joined into one string. Anything unrecognised yields `""`.
- **There is no client-side rate limiting, retry or backoff.** The service publishes a limit of
  5 requests per 10 seconds, and `POST /script-profiles` fires up to 10 sequential calls with no
  delay.

---

## Known quirks

Real behaviours that will surprise you. They are documented rather than hidden; each is a reasonable
first contribution.

| Behaviour | Detail |
|---|---|
| An empty strategy list is not the default | `POST /research/strategies` with `[]` stores `""`, which reads back as `[]` — no strategy active, so the scheduled poller skips research. The 3-strategy default only applies when the row is *absent* |
| Unhandled exceptions return HTML | No JSON error handler is registered, so a malformed body, a foreign-key violation, or a `JSONDecodeError` on a corrupt settings value produces Werkzeug's HTML page, not `{"error": …}` |
| The freeze rule keys on presence, not change | Sending `{"script_profile_id": ""}` against a video past `TOPIC_PROPOSED` returns `409`, even though `""` is otherwise always a legal value. Likewise `agent_id` set to the video's own agent between checkpoints |
| `openai_api_key` is read here only as present or absent | This API checks that a key exists before accepting the `illustrated` style; the key itself is used only by the MCP server's `generate_image` and `generate_character`. A key stored but since revoked is not caught here — probing the provider on every write would be worse than the late error |
