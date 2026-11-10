# `renderer/api/tests`

The suite covers the code under `renderer/api/`: the Flask pipeline API (`pipeline.py`), the render
gateway (`render_gateway.py`), the renderer (`render_agent.py`), the worker (`worker.py`), and the
postforme, Gemini and Discord clients. It needs `pytest` and the packages in
`renderer/api/requirements.txt`. Run it in its own `pytest` invocation: `renderer/api/tests` and
`scripts/tests` are both packages named `tests`, so the second one collected fails to import.

```bash
python -m pytest renderer/api/tests
```

Three containers run this code, and each entry names the one that acts. `tubematic-api` serves the
pipeline API and the render gateway. `tubematic-worker` runs `worker.py`. Both read and write the
database. `tubematic-renderer` runs `render_agent.py`, which has no database: it renders what the
gateway hands it and reports back. `render_results.py` holds the rules that move a video when a
render ends. The gateway and the worker call it.

Two helper modules serve several files. `render_client_env.py` wires the real renderer client to the
real gateway app over an httpx `WSGITransport`, with a migrated temporary database and a fake
Remotion process. `builtin_gpu.py` stores a GPU test result on the built-in renderer's row the way
the gateway stores one from a heartbeat.

## The pipeline API

### `test_pipeline.py`

Covers the blueprint in `pipeline.py`: most routes on [HTTP API](../05-http-api.md), the
`SETTINGS_SPEC` checks, and the helpers in `db.py`. The files after it cover single routes and rules
in more depth.

- Videos: the list, actionable and workable routes, guarded status changes, comments and titles.
  `VIDEO_APPROVED` stays out of `WORKABLE_STATUSES`, because
  [the agent cannot publish](../14-publishing.md#the-agent-cannot-publish) and the poller would
  start a paid session on every tick for a video the agent cannot move.
- Agents: the weighted deal (`_pick_agent_id` over [`agent_deck`](../03-database.md#agent_deck)),
  the `/agents` routes, and the per-video agent, model and effort picks with their
  [freeze outside a human checkpoint](../02-pipeline.md#the-agent-group).
- The poller's no-progress record,
  [`POST /videos/<id>/agent-outcome`](../05-http-api.md#post-videosvideo_idagent-outcome): the
  count, the stuck flag at `AGENT_NO_PROGRESS_CAP` and its release. A repeated `session_key` counts
  once, and the route does not write `updated_at`, which orders the poller's queue and times the
  stalled-voicing check.
- Settings: defaults, type and bound checks, saves that apply all keys or none, the voice roster,
  voice previews, the lexicon, the image models and the webhook probe on save. `user_preferences`
  has a length cap and a NUL check because the text travels to the agent as one command-line
  argument.
- Research: the research modes, [mining sources](../05-http-api.md#mining-sources) and run
  accounting. Mining is left out of the answers while no Gemini key is stored, and the stored list
  keeps it, so a key added later brings it back. No `POST /research/mine` route exists, because
  mining runs only through the MCP tool and its guards.
- [Script profiles](../05-http-api.md#script-profiles): the routes, archiving and the two-session
  cap of `record-attempt`.
- Publishing: accounts, publish, [scheduling](../14-publishing.md#scheduling-a-post)
  (`resolve_schedule`), [cancel](../14-publishing.md#post-videosidschedulecancel),
  [retry](../14-publishing.md#post-videosidpublishretry), the publish prefill and `GET /analytics`.
  A video is [claimed](../14-publishing.md#the-flow) before any postforme call, an ambiguous
  `create_post` failure keeps the claim, a request fills the post id on its own rows only, and a
  retry asks postforme first. Connecting an account requests `posts` and `feeds`
  [whatever the body says](../14-publishing.md#why-feeds-is-always-requested).
- Costs and logs: [`POST /usage/agent-session`](../05-http-api.md#post-usageagent-session) and its
  idempotency on `session_id`, the spend summary in host-timezone days, the price table, and
  [`GET /logs`](../05-http-api.md#get-logs) with the request log.
- `/pipeline/status` compares the version with `tubematic_core.version.version()`, so a second
  definition that drifts fails the test. `/stats` stays a map of status to count, because callers
  iterate it.
- Copies of shared rules: `_truncate_title`, the checkpoint freeze, `_pick_agent_id`,
  `WORKABLE_STATUSES` and the mining refusal are compared with `mcp/server.py`. `AGENT_EFFORTS` is
  read from all four copies as source text, and the model sets of
  `tubematic_core/voice_models.py` are compared with the dashboard's TypeScript copy. See
  [The hand-copied constants](../01-architecture.md#the-hand-copied-constants).
- Schema: `_init_db` brings an older database up to date and can run twice, and no process holds a
  `CREATE TABLE IF NOT EXISTS` of its own outside `tubematic_core/migrations/`.

Trap: `_read_all_settings` returns raw values for internal callers, and both `/settings` responses
[mask](../04-settings.md#masking) them. Masking the `GET` alone leaks a key on every save. The AI
review tests in this file mock `httpx.Client` whole and accept any request shape, so the request
itself is checked in `test_ai_review.py`.

### `test_job_paths.py`

Covers [ids that become paths](../03-database.md#ids-that-become-paths) and the four
[path columns](../03-database.md#path-columns), at the API.

- A new video or project id must be a plain path segment. An existing domain with an odd id (such as
  `node.js`) stays editable, because the dashboard re-sends the id on every save.
- `PATCH /videos/<id>` refuses each path column and applies nothing, including when a status change
  rides along.
- Archive, publish, the retention backlog and the publish dialog's duration derive the file from the
  ids. A planted `video_path` or `timeline_path`, a project id of `..` and a symlinked timeline are
  each ignored or refused.

Trap: a reader that trusts a path column lets one tampered row delete or upload another video's
render.

### `test_manual_submit.py`

Covers [`POST /videos/manual`](../05-http-api.md#post-videosmanual), the route behind the
dashboard's **New Video** page.

- Every submission is filed into the `manual` domain. The route creates it on first use as an active
  non-seed and does not overwrite it after someone renames it.
- A picked agent is kept, and a title over 70 characters is refused. `POST /videos` does the
  opposite on both counts: it deals the agent and clips the title.
- Picks are type-checked on the raw value, so `false` or `0` is refused and is not read as "use the
  default". A refused model returns the dealt card to the deck.

Trap: `_conn()` commits on exit, so a refusal that runs after the domain `INSERT` leaves an empty
`manual` domain behind on every bad submission. The tests that assert nothing was written guard the
order of the checks.

### `test_storage.py`

Covers [`GET /storage`](../05-http-api.md#get-storage), the dashboard's disk-usage figures.

- Each data folder is measured once. Voice previews and mascot sheets have their own lines and are
  not counted again under their parent folders.
- Without a readable host snapshot, `host` is `null` and the total is the data alone. The folder
  walk is cached, and the snapshot is read on each request.

Trap: the build cache is machine-wide, so it stays out of the total.

### `test_hosttz.py`

Covers `hosttz.host_timezone()`, the source of the timezone label in the dashboard.

- The IANA name comes from `TZ`, then `/etc/timezone`, then the `/etc/localtime` symlink. A value
  that is not an IANA name falls through to the next source, and the name is `None` when nothing
  resolves.

Trap: `timezone_label` comes from `datetime.now().astimezone()`, which reads glibc's cached zone. A
test that changes `TZ` must call `time.tzset()`, and the fixture restores the zone afterwards.

## Authentication and startup

### `test_api_auth.py`

Covers the API's bearer token (`api_auth.py`) and the dashboard's
[password login](../05-http-api.md#post-authlogin).

- Every route except the two health routes answers `401` without the right token. The sweep
  includes an unknown path, so a route added later is covered.
- The login needs the token too, refuses an oversized password before hashing it, and backs off
  install-wide after repeated failures. One password check runs at a time: a login that arrives
  while another is hashing gets `429` with `Retry-After: 1` and is not hashed.
- The password hash is absent from `GET /settings`, and `POST /settings` cannot write it.
  `server.py` refuses to start without the token file.

Trap: the check is installed on the app and exempts the health routes by endpoint name. A check on
the blueprint misses routes outside it, and a path-prefix exemption would open `/render/gpu` along
with `/render/health`. Without the single check slot, a burst of logins passes the backoff before
any failure is recorded, and each one hashes about 32 MiB.

### `test_secret_key_copies.py`

Covers the three lists of secret-typed settings keys: `SETTINGS_SPEC` in `pipeline.py`, and the
copies in `mcp/server.py` and `scripts/collect_diagnostics.py`.

- All three name the same keys. The copies are read with `ast`, so the test needs neither process's
  dependencies.

Trap: neither copy can import `pipeline.py`. A key missing from one is a credential that process
redacts by pattern only, or does not redact.

### `test_entrypoint.py`

Covers the permission steps of [`renderer/entrypoint.sh`](../16-infrastructure.md#rendererentrypointsh),
run as a subprocess against temporary directories.

- The shared logs directory ends up in the data directory's group with group read, write and search,
  plus setgid. The test starts from `0755` and from `0700`, where write without search is useless.
- A missing logs directory does not stop the container.

Trap: `poll.py` appends to the logs directory from cron as the host user. A logs directory left
root-owned keeps every poll entry off the dashboard's Logs page.

Needs: a non-root user. The file is skipped as root, and the fallback branch for a root-owned
directory has no test.

## Domain rules

The MCP server enforces these rules too, and `mcp/tests` holds its halves. `POST /projects` replaces
the whole row, and the dashboard re-sends every field on each save. The description limit and the
defaults for script profile, style, voice and mascot are therefore checked only when the value
changes. An unchanged value that has become invalid since still saves, because refusing it would
block every other edit to that domain.

### `test_project_pause.py`

Covers [domain pause](../02-pipeline.md#domain-pause) over HTTP.

- `POST /videos` refuses a paused domain with `409` for every research mode and accepts
  `strategy: manual`.
- Only a seed can be paused. `POST /projects` and `/projects/<id>/status` refuse a paused non-seed,
  and a non-seed that is already paused can still be activated.
- A pause that commits between the check and the `INSERT` still refuses, because
  `_DOMAIN_OPEN_GUARD` is part of the `INSERT`.
- The test executes the MCP server's copy of the shared block and compares the refusal messages,
  the guard, the topic-cap bounds and SQL, and the description limit.

Trap: `POST /videos` can be called without the MCP server, so a refusal in the MCP tool alone leaves
a second way to file into a paused domain. The agent can reach both, so both must give it the same
message.

### `test_topic_cap.py`

Covers the [topic cap](../02-pipeline.md#topic-cap) over HTTP.

- `POST /videos` refuses an expired domain for every research mode and accepts `manual`.
  `POST /videos/manual` files past the `manual` domain's cap, because the **New Video** page always
  files there.
- A topic committed between the check and the `INSERT` is still refused.
- `POST /projects` refuses a cap outside the bounds. A cap below the current count expires the
  domain at once.
- Mining at the cap is covered in `mcp/tests`, because mining runs only through the MCP tool.

### `test_project_description.py`

Covers a domain's description on `POST /projects`.

- A multi-line description is stored verbatim. The limit is `PROJECT_DESCRIPTION_MAX_CHARS`, counted
  in code points as the dashboard counts it.
- One character over is refused on a new domain and as a change to an existing one, and nothing is
  stored.

Trap: `test_an_unchanged_over_cap_description_still_saves_other_edits` plants a description longer
than the limit and re-sends it with another edit. It must save.

### `test_default_script_profile.py`

Covers a domain's default script profile.

- `POST /videos` seeds the default onto curriculum videos only. Trending, mining and manual videos,
  `POST /videos/manual` included, do not get it.
- A default archived since seeds nothing, and a later change does not reach videos already filed.
- `POST /projects` refuses a non-string, unknown, archived or not-`READY` profile when the default
  changes. The type check runs on the raw value, so `false`, `0` and `[]` are refused and are not
  read as "no default".

## Style, voice and mascot choices

### `test_visual_style.py`

Covers the visual style over HTTP and the style contract of the AI review prompt
(`ai_review._register_block`).

- `visual_style` is writable at `TOPIC_PROPOSED`, [frozen](../02-pipeline.md#the-topic-group) after
  it, and still accepted on the approving request that carries the status change. A domain's default
  style reaches curriculum videos only.
- `illustrated` needs an OpenAI key (a settings row or the environment). Without one it is refused
  on `PATCH`, on an explicit `POST /videos` and as a new domain default, with one shared message.
- The review prompt states the canvas and the figure clauses for the video's style. The contract
  rules out three false positives (flat art as low quality, a held pose as broken animation, a white
  frame as a blank frame) and still asks for a review of legibility, safe zones and sync.
  [The prompt's guard clauses](../21-ai-review.md#the-prompts-guard-clauses) explains each clause.
- The API and the MCP server use the same style rules: each of `pipeline.py`'s style names is the
  object `tubematic_core.visual_styles` holds, and `mcp/server.py` imports the same names from it.
  The GPU gate passes only `working` and gives `unknown` its own message.
- `GET /visual-styles` lists `auto` and every [style pack](../10-scene-authoring.md#style-packs),
  says why a style is unavailable on the install, and `system_flow` can be chosen with nothing
  configured.

Trap: a default inherited from the domain is kept and not rewritten when no OpenAI key is stored.
The approving `PATCH` refuses it, before any spend. An unknown canvas must produce no contract,
because a wrong contract tells the reviewer to accept defects.

### `test_voice_models.py`

Covers per-voice ElevenLabs models over HTTP.
[Keeping a script and its voice together](../08-scripting-and-voice.md#keeping-a-script-and-its-voice-together)
owns the rule.

- A voice change the stored script cannot use is refused with `409` at the checkpoint and changes
  nothing. A voice whose model was edited in Settings after scripting is caught at approval.
- Approving with the video's own, compatible voice is not refused.
- The video payload's `voice_conflicts` comes from the function the refusal uses, so the dashboard's
  greyed-out voices and the `409` agree.
- A domain's `default_voice_id` seeds every video filed into it on every creation path.
- At `TOPIC_PROPOSED` no voice conflicts, even with an old script stored, because approving has the
  script rewritten. The same row at `SCRIPT_READY` is refused.

Trap: a voice written under the `TOPIC_PROPOSED` waiver is bound to that status in its `UPDATE`. A
test moves the video to `SCRIPT_READY` mid-request, and the write must match no row. Without the
refusal, the result is a paid voicing that reads IPA aloud or drops a pronunciation.

### `test_video_voice_info.py`

Covers `voice_info`, the voice and model a single-video response reports for the read-only Voice
rows of the video modal.

- A voiced video reports the model the usage ledger recorded for its last voicing call.
- A video with no ledger row of its own reports the current setting. A voice that left the roster
  keeps its id with an empty name.
- A `PATCH` response carries the field. `GET /videos` does not, because it would cost a ledger query
  per row.

Trap: a voice's model can be edited in Settings after voicing, so reading the roster names a model
the audio was not made with. The ledger is ignored from `TOPIC_PROPOSED` through `VOICING`: a
revision may have switched the voice, and the old row would pair the new voice with the old model.

### `test_mascots_api.py`

Covers the mascot library over HTTP ([Mascots](../05-http-api.md#mascots)), the install and domain
defaults, the seeding of new videos and the per-video pick.

- The library is modelled in version rows: create inserts version 1 and each request for changes
  adds a draft. Approving needs code and all three sheets, and a failed revision leaves the approved
  version in use.
- Approve, request-changes and `record-attempt` each lose to an archive that commits after their
  read. Approve is bound to `IN_REVIEW`, so a request for changes that lands first is not
  overwritten. The sheet route refuses a symlink.
- A default or a pick must be pickable and needs a `working` GPU, checked when it changes. New
  videos are seeded from the domain default, then the install default, and get nothing without a
  working GPU or on a Cartoon 3D video.
- The per-video pick is frozen after `TOPIC_PROPOSED` and judged against the style the video will
  have after the same `PATCH`. A switch to Cartoon 3D clears the mascot and its `mascot_version`.

Trap: the approving `PATCH` refuses a mascot archived since it was seeded, and repeats the check in
its `UPDATE`, so an archive or a style write that commits between the check and the write still gets
`409`. No sequence of requests may leave a Cartoon 3D video holding a mascot, because
[the gateway refuses to hand it out](../11-rendering-and-review.md#refused-before-anything-renders).

## Publishing and Auto Pilot

### `test_postforme.py`

Covers `postforme.py`, [the postforme client](../14-publishing.md#the-client), at the wire level
through `httpx.MockTransport`.

- Every response the module returns is scrubbed of OAuth credentials, nested ones and error bodies
  included. The API key travels in a header and is redacted from errors.
- `create_upload_url` and `create_post` accept `201`. `create_post` sends `scheduled_at` only when
  given. An error carries postforme's own message, from a nested or a top-level `message`.
- The upload is streamed with a `Content-Length` and stops at its total time cap as a clean failure.
- Every field the per-platform builder emits is checked against the swagger-derived fixture
  `fixtures/postforme_platform_fields.json`.
- A post is found again by the video id stamped on it as `external_id`. A live post beats a newer
  dead one, and every page is checked before the answer is "none".

Trap: postforme nests the target account in the `create_post` response, with a live access token and
a refresh token that does not expire. Scrubbing happens inside the client because the publish path
stores errors and comments. `delete_post` raises on `200 {success:false}` and keeps the status of a
refusal, which is how the cancel route tells "already going out" (`400`) from "not found" (`404`).

### `test_worker.py`

Covers the worker's [publishing pass](../14-publishing.md#the-worker), its metrics pass and the
weekly price sync in `worker.py`.

- A video stays `PUBLISHING` until every target has reported. All succeeding gives `PUBLISHED`, a
  mix gives [`PARTIALLY_PUBLISHED`](../14-publishing.md#a-partial-publish), and none gives `FAILED`.
  A target that does not report is settled at `_PUBLISH_TIMEOUT_SECS`, measured from the
  publication.
- A publish whose rows have no post id yet is in flight and is left alone. An orphaned post is
  adopted by `external_id`, which restarts the deadline. A dead post under the same id is not
  adopted before the deadline, since it can belong to an earlier attempt. Expiry does not fail a
  video whose post id was filled in at the same moment.
- A `SCHEDULED` video is untouched until it is due, then watched with a fresh deadline.
- The metrics pass and the price sync run once per interval. The price sync is stamped before it
  runs, so a sync that fails does not run again twenty seconds later.
- The worker's loop calls no render step, and its `_setting` and `_truncate_comment` are identical
  to the copies in `render_results.py`.

Trap: Flask writes the publication rows at the claim with an empty post id. A worker pass that reads
"no post at postforme" as a failed publish fails a video that goes live seconds later, so
`test_a_worker_pass_during_the_upload_does_not_fail_the_publish` runs a real worker pass from inside
the upload. `test_a_publish_request_always_finishes_before_the_worker_deadline` keeps the upload cap
plus the per-operation timeouts under `_PUBLISH_TIMEOUT_SECS`, because a `create_post` that lands
after the deadline attaches a live post to the wrong attempt.

### `test_metrics.py`

Covers `metrics.poll`, the [metric snapshot pass](../14-publishing.md#capture).

- The pass costs one feed request per account, however many videos the account has.
- A feed entry is matched to a publication by postforme's post id, with `external_post_id` as a
  fallback. An entry with neither is skipped, and another account holder's post is ignored.
- Pagination follows the cursor and is bounded. One unreachable account does not stop the others.
- Snapshots append, and the whole platform payload is kept.

Trap: postforme's rate limit turns a request per publication into `429` answers that are caught and
skipped. `video_metrics` is a time series, so a skipped reading is lost and not fetched later.

### `test_auto_pilot.py`

Covers [Auto Pilot](../14-publishing.md#auto-pilot): the `/autopilot` routes and the worker's
`_sweep_auto_pilot`. Most tests check what Auto Pilot leaves alone, since it removes every human
checkpoint for the domains it covers.

- The routes: a malformed document writes nothing, and an account outside the Socials allowlist is
  refused. An account already stored for a domain does not block a save after it leaves the
  allowlist, so Auto Pilot can always be switched off.
- [Approval](../14-publishing.md#approval): each checkpoint moves on with a comment. An unselected
  domain, a paused pipeline and an archived video are left alone. An approval the dashboard would
  refuse is not made, is commented on once, and is made once the cause is fixed.
- [Posting](../14-publishing.md#posting): one public post to the domain's accounts, with the gap and
  the per-account daily number applied and one video started per pass. A video with nowhere to post
  makes no postforme request. A cancelled schedule sets `auto_pilot_hold`, so the post is not
  scheduled again on the next pass.
- [The in-progress limit](../14-publishing.md#the-in-progress-limit): what `pipeline.in_flight_count`
  includes, case by case. The limit holds back only `SCRIPT_READY → VOICING` and, while full, topic
  approvals. Finished videos are still approved and scheduled at the limit, and both routes refuse a
  value past `MAX_AUTO_PILOT_IN_FLIGHT`.

Trap: two cases keep the limit from closing for good. A voiced revision keeps its slot and passes
the gate at the limit without using room, so a full set of revisions cannot deadlock. A
`VIDEO_APPROVED` video with `auto_pilot_hold` set is not counted, because nothing in the dashboard
clears the hold.

### `test_autopilot_slot.py`

Covers `autopilot.next_slot`, the pure function that decides when Auto Pilot may post next.

- The gap holds against a post already scheduled ahead as well as one behind.
- A full day rolls to the next local midnight, cut in the host's zone, and stays correct across a
  daylight-saving change.
- A slot that frees one account is checked again against the others, because one post goes to all
  of them.
- When nothing is free inside the horizon, the function gives up and returns.

## The render gateway and the renderer

### `test_render_gateway.py`

Covers `render_gateway.py`, [the only API a renderer calls](../19-render-gateway.md). Most tests use
Flask's test client against a migrated temporary database. The time bounds, the connection cap and
one certificate test serve the app over real TLS on 127.0.0.1 and talk to it over raw sockets.

- Who may call: every route except `/v1/version` and `/v1/enroll` needs a renderer
  [credential](../19-render-gateway.md#credentials). The API's own `api_token` is refused. The
  built-in renderer's token is read from its secret file on each request, and a missing file fails
  closed. A rotated remote credential leaves the old one working until the new one is first used.
  [Enrollment](../19-render-gateway.md#enrollment) is single-use.
- [Claims](../11-rendering-and-review.md#the-claim): a renderer that is disabled, on another
  version, or has not reported a version gets nothing. A GPU-only video is offered only to a
  renderer whose GPU passed its test. The pre-render refusals move the claim on to the next video.
  Every location is derived from the ids, so a tampered row still bundles the video's own files.
- [The lease](../19-render-gateway.md#leases): the bundle, the upload and the result answer `403` to
  anyone but the holder of the claim named in `X-Render-Claim`. A renderer whose claim reply was
  lost gets the same video and claim id again, and two claims racing from one renderer cannot both
  win.
- The bundle is one uncompressed tar streamed in chunks. It holds no symlink, the Cartoon 3D mix
  only when it is not older than the voice, and `mascot.js` for a mascot video only.
- The upload streams into a temporary file in the gateway's own directory and is renamed into place.
  The tests cover the size, concurrency and free-space [limits](../19-render-gateway.md#limits), a
  claim lost while its upload streamed, and the sweep of temporary files older than
  `UPLOAD_ORPHAN_SECS`.
- Bounds on every request: the JSON body size, the time bounds (`JSON_BODY_SECS`,
  `REQUEST_HEAD_SECS`, `DRAIN_SECS`, the idle timeout), and the enrollment, per-renderer and
  connection caps. A protected route answers `401` without reading its body, and no route parses
  JSON with `request.get_json()`, which reads a body without a bound.
- Results and heartbeats: a success marks the render uploaded for the worker's review, and each
  failure outcome goes through `render_results.py`. A heartbeat stores the GPU test result,
  re-queues what a restarted renderer held, and extends the lease and builds the stop list by claim
  id, so a late heartbeat for an earlier claim cannot touch the claim that replaced it.
- Startup: with a missing or unusable TLS pair, or a port it cannot bind, the API
  [still serves without the gateway](../19-render-gateway.md#when-the-gateway-cannot-start).

Trap: a renderer's request is counted until its response is closed. A streamed bundle or an
undrained body outlives the route function, so releasing the count when the route returns lets one
renderer hold any number of bundles open. werkzeug answers a failed bind with `sys.exit(1)`, so
`make_gateway_server` catches `SystemExit` to keep the API up.

### `test_renderers_api.py`

Covers the dashboard's [renderer routes](../05-http-api.md#renderers) in `pipeline.py`: the list,
enrollment tokens, enable, rename, remove and the per-renderer GPU test.

- An enrollment token is refused with `409 remote_renderers_off` while remote renderers are off,
  because it would name an address nobody can reach. With them on, the token carries the gateway's
  address and certificate pin, and its secret is stored hashed.
- The built-in renderer can be disabled and cannot be removed (`409 builtin`). Removing another
  renderer clears both credential hashes.
- The address row, the host command and the default port are compared with
  `onboard/remote_renderers.py`.

Trap: no credential hash, current or previous, appears in the list or in a `PATCH` reply. The host
command shown with a token does not contain the token, because a command line is visible to every
user of the renderer machine.

### `test_render_agent.py`

Covers `render_agent.py`, [the renderer](../11-rendering-and-review.md#the-renderers-loop). Most
tests drive the real client against the real gateway through `render_client_env.py`, so the claim,
the bundle, the staged render, the upload, the result and the row the gateway leaves behind are one
path. One test runs enrollment and a heartbeat over real TLS.

- Start and heartbeats: nothing is claimed before the first heartbeat, which is the only one that
  says `started`. A heartbeat during a render reports it, which extends its lease. A renderer that
  needs an upgrade or is disabled keeps sending heartbeats and claims nothing.
- The timeouts and the watermark come from the claim and are not read from the agent-written
  `scene-config.json`. Only a mascot video gets its pinned version's code and the `mascotPath` prop.
- Each ending is reported with the text of the video's comment: Remotion's error,
  `Render stalled: no progress for …`, `Render timed out after …s`, or
  `The renderer hit an error: …`. The job directory and the staged public files are removed after
  every ending. A stop from the gateway kills the render and sends no result, and it must name the
  claim the heartbeat reported.
- [Uploads](../11-rendering-and-review.md#where-the-output-goes): `claim_lost` discards the render,
  a `413` or a `507` is reported as the render's error, and a busy gateway is tried again after
  `Retry-After` without using one of the `UPLOAD_ATTEMPTS`.
- The bundle: only the member names the gateway sends are unpacked. A member that could land outside
  the job directory, or a symlink, is refused before anything is written.
- A network error does not end the process. A failed heartbeat keeps `started` for the next one, and
  a lost lease discards the render.
- The GPU: a failed GPU render re-tests the GPU and sends the answer. A GPU-only video on a renderer
  whose GPU fails its test goes back to the queue.
- A remote renderer: enrollment checks the certificate pin before it sends anything and writes a
  state file only its owner can read. The log redacts the credential and carries the lines the host
  script watches for (`enrolled`, `first heartbeat`, `enrollment_invalid`). The built-in renderer
  compiles the shared scene tree the agent writes, so only a remote renderer stages and clears
  scenes.

Trap: after a hung render is killed, the reaper drains orphans without blocking and stops when the
stills server is the only child left. A blocking wait sits on that long-lived child and the render
is not reported. A rotated credential is saved before it is used, and a second heartbeat waits for
the save: the gateway would issue it another replacement, and the save that lands last could be one
the gateway refuses.

### `test_render_progress.py`

Covers `render_agent.py::_wait_for_render`, the watcher behind
[the two timeouts](../11-rendering-and-review.md#progress-and-the-two-timeouts), against real child
processes.

- A render that advances is left alone. One whose counter stops is a stall, including when it keeps
  printing the same line. One that crawls still hits the ceiling.
- A child that floods stderr cannot deadlock the watcher, because both pipes are drained on threads.
- One test checks that the AI review prompt describes the Cartoon 3D look.

Trap: Remotion's logs repeat lines such as `Rendered 8/60`, so the arrival of a line is no proof of
progress. The phase and the count must increase.

### `test_cartoon_render.py`

Covers `render_agent.py::_render_cartoon`, the
[segmented Cartoon 3D render](../11-rendering-and-review.md#segmented-cartoon-3d-renders), over a
fake Remotion and a fake ffmpeg.

- The segment plan tiles the video in `CARTOON_CHUNK_FRAMES` segments and folds a short tail into
  the segment before it.
- The synthesised mix is muxed only when it is at least as new as the voice. Otherwise the voice is.
- A failed segment is tried once more and then reported with Remotion's text. A stalled segment is
  killed, tried again and reported as `hung`. One ceiling covers the whole render, ffmpeg included.
- The generated source Remotion compiles must be the one `submit_render` froze. It is checked before
  every segment and before the mux.

Trap: both ffmpeg steps run as the job's own processes in a process group of their own. An ffmpeg
run started outside the job-aware spawn is not killed by a stop from the gateway or by the timeout.

### `test_stills_server.py`

Covers the renderer's [stills server](../11-rendering-and-review.md#the-stills-server)
(`_ensure_stills_server`).

- The CPU command is the CPU render options over the jobs volume. The GPU command is every GPU
  render option plus the EGL vendor variable.
- The server starts once on the current GL path, and a passing GPU test starts it again on the GPU.
- A dead server is started again only after `STILLS_SERVER_RETRY_SECS`, and a server that cannot
  start does not raise.
- Only the built-in renderer runs one, because it serves the shared jobs volume and a remote
  renderer has none.

### `test_gpu_rendering.py`

Covers GPU rendering in the renderer (`_gl_options`, `_judge_probe`, `_run_gpu_probe`) and the two
dashboard routes under [GPU rendering](../05-http-api.md#gpu-rendering).
[The GPU test](../20-gpu-and-remote-renderers.md#the-gpu-test) owns the mechanism.

- Flags: the CPU path adds nothing to a render, so `remotion.config.ts` applies. The GPU path is
  every GPU setting, with `--browser-executable` as the browser flag. The CPU options the test uses
  are compared with `remotion.config.ts`, because the Node driver does not read that file.
- An unconfigured, untested or failed GPU renders on the CPU. Only the configured NVIDIA GPU passes.
  SwiftShader, llvmpipe, an Intel GPU and another NVIDIA GPU all fail.
- The GPU test runs with the options and environment a render gets, through a driver with its own
  entry point, so a broken agent-written scene cannot read as a broken GPU. A failed test withdraws
  an earlier verification, a hung one has its process group killed, and none raises.
- Routes: `GET /render/gpu` is `unknown` before any test result and then follows the `renderers`
  table. A result left in a `gpu_probe_result` settings row is ignored. A Test request stamps the
  built-in renderer's row and is `pending` until a newer result. The two stamps are compared as
  strings, so both keep the microsecond format.
- The API and `onboard/gpu.py` agree on the `render_claim_hold_until` row and on where the built-in
  renderer's result is read.

Trap: a finished render is no evidence that the GPU was used, because a render on the wrong GL
device finishes too, more slowly. The test must read the WebGL renderer string. `status` on
`GET /render/gpu` is the install-wide answer every GPU gate reads: a status taken from the built-in
renderer alone would refuse a style another renderer can render.

## Render results and AI review

### `test_render_results.py`

Covers `render_results.py`. The render gateway calls its failure rules when a result arrives and
its re-queue when a restarted renderer sends its first heartbeat. The worker calls the review step
(`finish_render`) on its review thread and the re-queue from its lease sweep.

- The review step passes a style pack's review text (System Flow's) as `style_block`, and `""` for a
  style without one.
- The review step: the [routing](../21-ai-review.md#routing) of each outcome and the
  [fail-open](../21-ai-review.md#fail-open) path. Every outcome writes `videos.gemini_feedback`
  whole and a comment cut with a note, which is what makes a failing reviewer visible. Each review's
  usage is recorded against the video.
- The failure step counts a retry and fails the video past `max_render_retries`, which stays
  independent of `ai_review_max_loops`.
- A GPU-only video goes straight to `FAILED`, with no retry counted, only when the render ran on
  the GPU and the renderer's own re-test answered that
  [the GPU is gone](../20-gpu-and-remote-renderers.md#a-gpu-that-stops-working). The comment names
  every renderer and its GPU state.
- A failure routed with the gateway's renderer and claim id moves the video, counts the retry,
  comments and releases the claim in one transaction. A failure from another renderer, or from an
  earlier claim, changes nothing.
- A failed render's [page timeout](../11-rendering-and-review.md#status-transitions) is recognised
  from Remotion's real messages. The first one re-queues the video with no retry counted and a
  marking comment, and the second goes to `REVISION_REQUESTED` and counts, or to `FAILED` when an
  earlier failure already used the cap. Other failures, a stall or timeout outcome, a stale claim
  and a GPU that failed its re-test keep their own routes.
- `requeue_interrupted` re-queues with a retry counted and fails past the cap. It does not touch an
  uploaded render, and its `UPDATE` is guarded on the holder and on the lease.
- A blank settings row falls through to the environment, as it does in `pipeline.py`.
  `scene_config_is_cartoon3d` recognises a generated scene whose props carry a `cartoon3d` object.

Trap: the page-timeout retry must not count against `max_render_retries`. With the default cap of
1, a counted retry would send the second failure to `FAILED`, and a scene that hangs would never
reach the agent.

Trap: the review cap compares with `>`. With `>=`, a cap of 1 accepts the first review and allows no
revision round. The review past the cap still runs, so the stored feedback belongs to the render
that ships.

### `test_worker_render.py`

Covers the worker's render backstops and its review thread: `_sweep_render_leases`,
`_sweep_gpu_waits` and `_review_once`.

- An expired lease is re-queued with the renderer's name, and so is a render with no renderer that
  was in flight across an upgrade. A lease still held, an uploaded render and a video that left
  `RENDERING` are left alone.
- [Waiting for a GPU renderer](../20-gpu-and-remote-renderers.md#waiting-for-a-gpu-renderer): a
  GPU-only video fails at once when no renderer has a GPU, waits while a renderer has not run its
  GPU test, and waits `GPU_WAIT_SECS` for a GPU renderer that is offline, disabled or on another
  version before it fails with that renderer named.
- The review pass takes the oldest uploaded render through `finish_render`, one at a time. `main`
  starts the thread before its loop, and the thread survives a failing pass.

Trap: the lease sweep selects expired leases, and `requeue_interrupted` checks the holder and the
lease again in its `UPDATE`. A heartbeat that extends the lease between the two wins. Keep both
checks.

### `test_ai_review.py`

Covers `ai_review.py` at the wire level. `httpx.MockTransport` lets real `httpx.Request` objects
reach the assertions, so the method, path, headers and query string are checked.

- [The call](../21-ai-review.md#the-call): the resumable upload, the poll until `ACTIVE`, then
  `generateContent`. No request carries the key in its query string, and errors are redacted.
- The sampling rate travels as `video_metadata`, a sibling of `file_data`. It is capped, and it is
  lowered for a long video so the request fits the model's window.
- Every error path returns the fail-open shape and does not raise: a file that fails processing, a
  poll timeout, malformed findings, and a reply that parses to a JSON array.
- The prompt's [guard clauses](../21-ai-review.md#the-prompts-guard-clauses): captions, the
  watermark, the mascot, the figure clauses per style, redundant scene text as a suggestion, and the
  two script forms with the IPA sentence. The [mispronunciation bar](../21-ai-review.md#the-mispronunciation-bar)
  is checked by its wording.
- `usage` is returned on every path where Gemini answered `200`, including a reply that failed to
  parse, and on no path where it did not.
- A style pack's own review text replaces the canvas and figure blocks, and with no style text the
  contract is the same as before for every combination.

Trap: any finding sends the video back for a revision, so a clause removed from the prompt produces
a finding on every video it covered, and a round can cost a paid re-voice. An illustrated video gets
the discrete-motion clause without the line-art clause. `ai_review.py` does not read the database,
so it returns `usage` and `render_results.py::finish_render` records it, in the worker.

## The worker's other passes

### `test_notifications.py`

Covers the worker's [notification sweep](../12-the-worker.md#notifications),
`worker.py::_sweep_notifications`: which videos are announced, and when.

- Every trigger defaults to off, and each gates its own event. A video at a checkpoint is announced
  once. Topics are bundled into one message after `TOPIC_SETTLE_SECS`, and the settle window does
  not delay the other events.
- A video that returns to a checkpoint after a revision round is announced again.
  [What counts as announced](../12-the-worker.md#what-counts-as-announced) explains the marker.
- Videos parked while a trigger was off are not announced when it is switched on, and the migration
  backfill marks existing rows. A failed send leaves the marker, so the next tick retries.
- [Auto Pilot](../12-the-worker.md#auto-pilot-and-failed): a `VIDEO_READY` video that Auto Pilot
  will approve is not announced and its marker is left alone, so switching Auto Pilot off announces
  it. Auto Pilot does not hide a `FAILED` video, and the alert carries the agent comment written
  with that arrival or up to `FAILURE_REASON_WINDOW_SECS` before it.

Trap: keep `test_a_revision_round_notifies_again_with_no_sweep_in_between`. A marker keyed on the
status name alone passes a test that sweeps at each step and drops the second announcement when the
whole round happens between two sweeps. The sweep must not write `updated_at`, which orders the
render queue.

### `test_discord_notify.py`

Covers `discord_notify.py` at the wire level: URL validation, the probe run when the URL is saved,
sending, and the message builders. [Notifications](../04-settings.md#notifications) lists the
settings.

- Every URL form Discord hands out is accepted, and anything else is refused with a message that
  says where to find the URL.
- No error text carries the webhook token: a transport failure, an HTTP error and httpx's own
  request log line are each checked. The log filter leaves other httpx lines alone.
- The probe has three answers. A `401` or `404` is invalid, and a timeout or `5xx` is unknown. Only
  a positive rejection may refuse a settings save, or Settings cannot be saved while Discord is
  unreachable.
- A rate limit is retried once, and an absurd `Retry-After` is clamped.
- Every builder stays inside Discord's size limits with absurd input, because Discord answers `400`
  to an oversized embed and nothing reports the lost message. A topic with score 0 reads "unscored".

Trap: the webhook URL is a credential, and it sits in the request path. httpx puts the URL in its
log line and its exception text, and the worker stores exception text in comments.

### `test_voicing_stall.py`

Covers [the stalled-voicing check](../12-the-worker.md#the-stalled-voicing-check),
`worker.py::_sweep_stalled_voicing`.

- A video in `VOICING` for `VOICING_STALL_TICKS` poll intervals, read from `poll_interval_mins`,
  gets one comment, an `ERROR` log line and, with a webhook set, a Discord alert whatever the
  per-event toggles say.
- The check fires once per arrival, and again after a fresh arrival such as a re-voice.
- No other status and no archived video is flagged, and a video that moves between the select and
  the flag is not.
- Nothing fires while the pipeline is paused, or for three intervals after it resumes.
- A failed Discord send keeps the comment and is not retried. The sweep does not write `updated_at`.

Trap: a flag raised during a pause is a false alarm that uses up the arrival's one alert, so a real
stall later stays quiet. The check shares `notified_status` with the notification sweep, and a test
confirms that sweep announces nothing for a flagged video.

### `test_retention.py`

Covers `pipeline.archive_video` through its two callers, `DELETE /videos/<id>` and the worker's
[retention sweep](../12-the-worker.md#retention), and every query that leaves archived rows out.

- Delete: `DELETABLE_STATUSES` is compared with the dashboard's copy in
  `dashboard/lib/videoStatus.ts`. Statuses mid-process or under a claim are refused, and so is
  `SCHEDULED`, because postforme holds a post that will go out.
- Archived rows stay out of the list, workable and actionable routes, `/stats` and
  `/pipeline/status`. They are still served by id, cannot be patched or published, and keep their
  metrics.
- `retention_days` sweeps `PUBLISHED` videos only, timed from the latest successful publication. The
  pass is rate-limited by the `last_retention_sweep_at` row, and one failing video does not stop it.
- `unpublished_retention_days` archives old `FAILED` and `TOPIC_REJECTED` videos with their status
  kept, and reaches no other status. The two keys' passes are independent, and
  `test_a_video_that_is_not_published_is_never_swept` shows that the default of 0 changes nothing.
- [`GET /retention/backlog`](../05-http-api.md#get-retentionbacklog) reports counts and sizes per
  status, ignores the key and deletes nothing. It sizes only a direct child of the jobs directory.

Trap: an unpublished mp4 cost ElevenLabs credits and render time, and a sweep that takes it cannot
be undone. A `PARTIALLY_PUBLISHED` video keeps its file for the manual upload until someone marks it
published. The status and the age are checked again inside `archive_video`'s `UPDATE`, so a retry or
an edit that lands after the sweep's select keeps the video.

## Mascot source checks

Both files read source under `renderer/remotion/` as text, because that project's test runner has
no browser to run the mascot code in.

### `test_mascot_engine.py`

Covers the mascot engine under `renderer/remotion/public/mascot/`.

- The engine files exist, and the driver draws through the mascot's registered `window.MASCOT`.
- No engine file contains the name of Anthropic's mascot, Clawd, which Tubematic may not ship. The
  engine loads no web font, and `frame.html` holds no remote URL.
- The driver has no `talk` cue and no word-timed mouth, and the model sheets have no talking mouth.
- The licence files of p5.js, p5.brush and ClaudeAnimationBase are shipped and non-empty. The p5.js
  and p5.brush files name their upstream and copyright holder.

Trap: a render may have no network access, so a web font or a remote URL stalls it. The mascot
reacts to the narration and is not presented as its speaker, so nothing may animate speech.

### `test_mascot_layer.py`

Covers where [the mascot layer](../09-remotion-project.md#the-mascot-layer) enters a render, and the
argument checks of `mascot-tools/render-sheet.mjs`.

- `MascotLayer` sits over the scenes and under the captions in `CompositionBuilder`.
- The layer is drawn only when the `mascotPath` render prop and a non-empty `mascot` cue list are
  both present, and it reads no word timings.
- The `MascotSheet` sizes match what `sheet.js` draws. The sheet renderer uses its own entry point
  and software GL, and its in-page timeout stays below the limit `mcp/mascot_sheets.py` gives the
  whole command.
- `render-sheet.mjs` refuses a bad call with exit code 2 before it loads Remotion, and writes no
  PNG.

Trap: `mascotPath` comes from the renderer and is not read from `scene-config.json`, which the agent
writes. The text-audit composition names its props one by one: a spread would forward `mascotPath`
and start p5 inside a text measurement.

Needs: `node` on the `PATH` for the argument checks, which are skipped without it.
