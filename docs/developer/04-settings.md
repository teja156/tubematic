# Settings internals

What each setting does, its default and when to change it is in
[Settings](../user-guide/05-settings.md). This page is how settings are stored, read, masked and
verified, the rows that live in the same table without being settings, and how to add one.

---

## Storage and reads

Every setting is a row in the `settings` table (`key TEXT PRIMARY KEY`, `value TEXT NOT NULL`), so
every value is a string. `SETTINGS_SPEC` in `renderer/api/pipeline.py` declares each key's type and
default; the types are `bool`, `int`, `str`, `secret`, `json_list`, `voice_list` and `lexicon`, and
`_coerce_setting` turns a raw value into its typed form and back into the string that is stored.

- **Reads merge in the defaults.** `pipeline.py::_read_all_settings` coerces every declared key,
  using the spec default for a key with no row. That is why a new key's default applies to an
  upgraded install with nothing written for it. A stored value that no longer coerces falls back to
  the default too, rather than failing the read.
- **Writes are all-or-nothing.** `POST /settings` (`pipeline.py::post_settings`) rejects any
  undeclared key, coerces every value, and only then writes. One bad value changes nothing.
- **Nothing caches a setting.** The Flask API, the MCP server and the render worker read the
  database per use, which is why no key needs a restart.

### The default-voice invariant is enforced on read

If the stored `elevenlabs_voice_id` is no longer on the `elevenlabs_voices` roster,
`_read_all_settings` blanks it. It is not rejected at write time on purpose: the roster can degrade
to `[]` on its own (a corrupt stored list falls back to its default), and a write-time cross-field
check would then reject the *next unrelated* settings save with an error about voices. Do not add
one to `post_settings`.

### Derived: `pronunciation_mode`

`pronunciation_mode` is **not stored and not writable** — posting it is an unknown-key error. It
belongs to a voice, not to the install, so `GET /settings` does not return it: it is computed from a
voice's model wherever a video's model is needed (`tubematic_core/voice_models.py::pronunciation_mode_for_model`;
the MCP `get_video` tool reports it per video) — `ipa` for `eleven_v3` and `eleven_v4`, `phoneme` for a model that
supports phoneme tags, `respell` otherwise.

It is derived rather than stored because enabling phoneme mode only ever *adds* capability. There
was never a real tradeoff for a human to choose, so exposing it as a choice would only create a way
to get it wrong.

### `user_preferences` counts code points

`MAX_USER_PREFERENCES_CHARS` (6000) is enforced by the API. The dashboard mirrors the constant for
its counter and truncates input at the cap. Both count **code points**, which is what Python's
`len()` counts. A textarea's `maxLength` was deliberately not used: it counts UTF-16 units, two per
emoji, so it would stop input well before the limit the API allows. Why the cap exists at all is on
the [settings reference](../user-guide/05-settings.md#user-preferences).

---

## Undeclared rows

These keys live in the `settings` table but outside `SETTINGS_SPEC`, so `POST /settings` rejects
them as unknown:

| Key | Written by | Shape |
|---|---|---|
| `active_strategies` | `POST /research/strategies` | Comma-joined string. Read through a filter that drops `mining` while no `gemini_api_key` is stored (`pipeline.py::_active_strategies`, `mcp/server.py::_active_strategies`); the filter never rewrites the row, and a save made while there is no key keeps a stored `mining` (the caller was only shown the filtered list), so a key added later brings mining back |
| `publishing_accounts` | `POST /publishing/accounts` | JSON array of allowed account ids |
| `auto_pilot_config` | `POST /autopilot` | JSON object: `projects` maps a project id to the account ids it posts to, `account_limits` maps an account id to its posts per day. A missing or malformed row reads as no project selected |
| `last_metrics_poll_at` | The render worker's hourly metrics pass | ISO timestamp |
| `last_price_sync_at` | The render worker's weekly price sync, stamped before it runs | ISO timestamp |
| `last_price_sync_ok_at` | The price sync, when it succeeds | ISO timestamp. Shown on Settings → Costs |
| `last_price_sync_error` | The price sync | The last failure's message, or `""` after a success |
| `mining_youtube_urls` | `POST /research/mining-sources`, or the MCP server's `set_mining_sources` | JSON array of YouTube video URLs, each `https://www.youtube.com/watch?v=<id>`, no repeats, at most 50. Both writers refuse any other entry ([HTTP API — Mining sources](05-http-api.md#mining-sources)) |
| `mining_url_cursor` | A mining run (the MCP server's `mine_youtube_topics`) | Integer as a string: the index of the URL the next run starts from, so runs rotate through the list |
| `last_retention_sweep_at` | The render worker's retention sweep, stamped before it runs | ISO timestamp |
| `voicing_stall_paused_at` | The render worker's voicing-stall check, on every pass while the pipeline is paused | ISO timestamp. A stall is flagged only once enough time has passed since the later of this and the video's own last change, so a long pause does not flag every video the moment it ends |
| `research_run_timestamps` | `POST /research/record-run` | JSON array of ISO timestamps, pruned to 24 hours |
| `last_research_at` | The MCP server's `mark_research_done` | ISO timestamp |
| `mcp_port` | Onboarding's `install_config` step | Integer as a string. Read back by onboarding and by `--install-agent` to build the MCP URL |
| `poll_interval_mins` | Onboarding's `cron` step | Integer as a string |
| `admin_password_hash` | Onboarding's `auth` step and `onboard.py --set-password` | `scrypt$N$r$p$salt$hash`. Read only by `POST /auth/login`. Never returned by `GET /settings`, and an install older than the login simply ignores it — which is what makes setting it before an upgrade safe |

`mcp_port` and `poll_interval_mins` have no route of their own on purpose: each feeds something only
onboarding regenerates — the MCP registration and the crontab line — so a dashboard edit would
silently do nothing.

Three more rows used to live here: `agent_binary`, `agent_run_path` and `install_scope`. They are
columns of an agent's row now. The first `--install-agent` run reads them once, as its pre-fill, and
then deletes them.

---

## How credentials are stored

Credentials are **plaintext rows in the SQLite database**, not environment variables and not a
`.env` file. That was a deliberate move, and it has consequences in both directions.

**What it buys:** rotating a key on the dashboard takes effect on the next call, with no restart and
no file edit. `docker inspect` no longer exposes any key, because no service has an `env_file`.
Onboarding can verify a key against its provider *at the moment it is typed*.

**What it costs:** the database file is now credential-bearing. It cannot be made unreadable to the
host user — WAL mode requires write access to the `-shm` sidecar even for readers. Treat
`~/.tubematic-data/data/tubematic.db` as a secret.

The same applies to `discord_webhook_url`, which is `secret`-typed for exactly this reason even
though it is a URL rather than a key. It needs one protection the API keys do not: its credential is
in the URL *path*, so an HTTP client's own request log prints it on every call, and the save-time
probe runs *before* the value is stored — meaning value-based log redaction has nothing to match at
the moment it is most likely to be logged. `tubematic_core.logging` carries a pattern for the
webhook path, and `discord_notify` installs a filter on the HTTP client's logger, because the
plain stdout handler is not redacted at all.

Each process reads keys from the settings table on every call, falling back to the matching
environment variable (`OPENAI_API_KEY` for `openai_api_key`, and so on) only when the row is empty
(`pipeline.py::_secret`). That fallback exists for scripts and tests — the test compose file
supplies its dummy keys that way; a normal install never sets one.

### Masking

`secret`-typed keys are masked at the API boundary (`pipeline.py::_mask_settings`) — on the `GET`
response **and on the `POST` response**, since `POST /settings` re-reads and returns everything. A
mask is eight bullet characters plus the last four characters of the value, all bullets for a value
of four characters or fewer, or the empty string if unset. Internal callers read the raw values;
only the route output is masked.

The masking round-trips: a posted secret whose value exactly equals the current mask is dropped
before the write. That is what lets the dashboard `GET`, edit one field, and `POST` the whole object
back without overwriting untouched keys with mask characters.

### Never log a key

Send API keys as **headers, never as URL query parameters**. HTTP client libraries embed the request
URL in their exception strings, and this pipeline persists error text into the `comments` table,
which the dashboard displays. That is exactly how a key has leaked before.

Provider error messages are not equally safe to surface, either. OpenAI's `401` echoes a masked
slice of the submitted key — twelve real characters. It is the one provider message that must never
be logged or displayed.

### Rejection signatures

Onboarding validates each key live at prompt time (`onboard/api_keys.py`). Each check answers one
of three things — valid, invalid, or unknown — and only a definitive rejection refuses the key: a
timeout or an unreachable provider proves nothing about the key, so it is accepted with a warning.
The signatures are not uniform, and the differences matter:

| Service | Probe | A bad key answers |
|---|---|---|
| ElevenLabs | `GET /v1/user`, `xi-api-key` | `401`, `{"detail": {"status": "invalid_api_key"}}` |
| Gemini | `GET /v1beta/models`, `x-goog-api-key` | **`400`**, with `error.details[].reason == "API_KEY_INVALID"` |
| OpenAI | `GET /v1/models`, `Authorization: Bearer` | `401`, `{"error": {"code": "invalid_api_key"}}` |
| youtube-transcript.io | `POST /api/transcripts`, `Authorization: Basic`, body `{"ids": []}` | `401`, plain text |
| postforme.dev | `GET /v1/social-accounts`, `Authorization: Bearer` | `401`, `{"error": {"code": "err:frontline:client:invalid_key"}}` |

**postforme answers `401` for two different things.** `invalid_key` means the key is wrong;
`missing_credentials` means no `Authorization` header was sent at all — which is *our* bug, so
reporting it as invalid would reject a good key on our own defect. Discriminate on `error.code`,
never on the status.

**Gemini answers `400`, not `401`.** A shared "401 or 403 means invalid" rule silently accepts every
bad Gemini key. Discriminate on `error.details[].reason`, never on the status code.

youtube-transcript.io has no account endpoint, so the transcript endpoint is the probe. It rejects
on auth *before* validating the body, so an empty `ids` list still returns `401` on a bad token
while fetching nothing and spending no transcript quota.

### A pasted key is checked before it is sent

Onboarding strips surrounding whitespace from a key, then refuses one that still contains anything
outside printable ASCII — a line break, a tab, a non-printable or non-ASCII character — **before any
request is made** (`onboard/api_keys.py::malformed_reason`). The answer says the key looks like a
copy-and-paste artefact and asks for it again.

The check exists because both ways such a key fails on the wire look like something else:

- A line break raises `httpx.LocalProtocolError`, which **subclasses `httpx.HTTPError`** — so the
  checker's routine transport handler would read it as "provider unreachable", report the key as
  unverified, and accept it.
- A non-ASCII character raises `UnicodeEncodeError`, which is **not an httpx exception at all** and
  would escape that handler and crash the wizard.

Neither is an unreachable provider; both are bad input, so they are reported as invalid. Interior
spaces are deliberately let through: httpx sends them, so the provider gets to reject them. The
stripping happens on the value that is **stored**, not only on the one that is probed
(`onboard/api_keys.py::resolve_secret`), so a key is never verified as one string and saved as
another.

---

## Adding a setting

1. Add the key to `SETTINGS_SPEC` in `renderer/api/pipeline.py` with its type and default, and add a
   coercion branch to `_coerce_setting` if the type is new.
2. Add it to the `Settings` type in `dashboard/lib/types.ts` and to a tab in
   `dashboard/app/settings/page.tsx`.
3. Add a `Field` to `onboard/config.py` if it should be asked at install time, and map it in
   `ENV_FIELD_TO_SETTING`.
4. Read it where it is consumed — per call, not at import.
5. Document it in the [settings reference](../user-guide/05-settings.md), and update the key count
   there and on [HTTP API](05-http-api.md#settings).

**Watch for duplicate defaults.** Several settings have their literal default repeated in three to
five places: the spec, an `apply_*` action's `v.get(key, "<literal>")` fallback, a consumer's own
`os.getenv(..., default)`, and sometimes a status endpoint. They mostly do not carry
"keep in sync" comments. Grep for the *value* as well as the key before you change one.
