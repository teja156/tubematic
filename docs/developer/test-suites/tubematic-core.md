# `tubematic_core/tests`

Covers `tubematic_core/` — the one Python package shared by every Tubematic process: schema
migrations (`db.py`), structured JSONL logging (`logging.py`), the canonical version string
(`version.py`), the spend ledger with its model prices (`usage.py`, `prices.py`), what each
ElevenLabs model can speak (`voice_models.py`), which YouTube URLs mining accepts (`youtube.py`),
and the rules for ids that become paths and where a video's files live (`ids.py`, `jobfiles.py`).
See [Database — Migrations](../03-database.md#migrations) and
[Architecture — Duplication](../01-architecture.md#duplication-is-intentional) for what each module
is and why it exists at all.

```bash
python -m pytest tubematic_core/tests
```

> **Deliberately no `__init__.py` here**, for the same reason `mcp/tests` and `vqa/tests` have none:
> `renderer/api/tests`, `onboard/tests` and `scripts/tests` each have one and therefore all claim the
> top-level package name `tests`, which is why they cannot be collected together in one pytest
> invocation. Staying `__init__.py`-free keeps this suite out of that collision.

Host-side tests here import `tubematic_core` directly from the repo root — nothing puts that
directory on `sys.path` automatically outside a container, where it arrives via `PYTHONPATH=/app/lib`
instead. Each test file inserts the repo root itself, at the top, before the import.

---

| File | Guards |
|---|---|
| `test_db.py` | Migration discovery and ordering, the `schema_migrations` tracking table, `connect()`'s WAL setup, and the whole `migrate()` run — atomicity, the write lock, and `assert_schema_current` |
| `test_baseline.py` | The `0001_baseline.py` migration: a fresh database gets every table and column, and two hand-written pre-migration databases converge without losing rows |
| `test_agent_effort.py` | The `0003` agent-effort migration — the two columns, and above all that it has **no backfill**, which is the mirror image of `0002`'s. A pre-`0003` video has no per-video pick to preserve, so writing anything but `''` would pin it to a level nobody chose and freeze it there at its next status change; an `UPDATE` added here "for symmetry with `0002`" is exactly what these tests catch. Also pins that an agent row created before the column existed ends up at `high`, which is what makes "an install that never touches the setting runs at high" true on the upgrade path rather than only on a fresh install |
| `test_visual_style.py` | The `0002` visual-style migration — the three columns, and above all its **backfill**: `ADD COLUMN ... DEFAULT 'auto'` applies its default to existing rows too, so without the trailing `UPDATE` every video already in flight would silently become `auto` and be re-styled by the next agent run that touched it. Dropping that one line leaves a migration that still adds the right columns and still passes any schema-only check |
| `test_pause_seeds_only.py` | The `0004` migration, which activates every paused **non-seed** domain. Pause now exists only on curriculum seeds and no screen offers a control for any other domain's status, so a non-seed paused by an older install would stay paused forever with nothing able to change it. It pins the other direction too: a paused **seed** is left alone, because a blanket `UPDATE` would unpause a domain the human paused on purpose. The database is built by migrating only as far as `0003` from a copied migrations directory, so the rows exist before `0004` runs |
| `test_usage_accounting.py` | The `0005` usage ledger and `usage.py`/`prices.py`'s pricing. The rule it exists for: **an unknown model is unpriced (`NULL`), never `$0`** — zero is indistinguishable from "this call was free" and would understate spend invisibly — and it is logged once per process, not once per call. Pins the rate ladder (manual beats synced beats the built-in snapshot, one source per model), the fallback rules (thinking bills at the output rate exactly; audio or image input without its own rate falls back to input and is marked estimated; any other missing rate makes the whole call unpriced rather than a silently partial sum), and that **editing a price never re-prices history** — only unpriced rows are filled in when a rate is added, which is why their units are kept. ElevenLabs rows are credits and never priced; reported costs (Claude, OpenCode) are stored as given. `record_usage` must return `None` and log when it cannot write — it never raises, because bookkeeping must not fail a video. The read side pins the video modal's arithmetic: a shared agent session is split evenly across its batch, and a video's total adds its **share**, never the whole session, which would count one session once per video. Also the Gemini and OpenAI usage-object normalisers (modalities, cached tokens split out, thinking tokens, image output) A billed call whose usage could not be read is recorded with no units, and **no units is unpriced, not $0** — pricing it as free would understate spend with nothing left to repair it from. An `event_key` makes a write idempotent: a second write under the same key returns the first row and adds nothing. The spend summary's `until` is an **exclusive** bound, applied to the video count as well as the dollars, so two adjacent ranges never count an event on their shared edge twice. `last_voice_model` returns the model of a video's **latest** voicing call. That call can be another video's, a voice preview (even one linked to the video) or another provider's call, and none of those counts. A video never voiced gives `None`, so the API can tell "voiced with" from "the current setting". |
| `test_prices_sync.py` | The unattended price sync. Source precedence is **per model**: when OpenRouter lists a model its rates are used even where LiteLLM disagrees, and LiteLLM is used only for a model OpenRouter lacks — a mix of fields from both would make a wrong figure untraceable. Zero rates are dropped rather than stored (a `$0` rate prices a paid call as free), `:batch` variants are ignored, and long-prompt tiers mark a model `tiered`. The safety rules each have a test: a manual row is never overwritten, a >5× move is rejected as upstream breakage, and **a failure keeps every existing price** — including a failure part-way through, which is why the sync runs inside a savepoint; without it, half the models could end up on new rates. A sync that newly prices a model fills in that model's unpriced calls |
| `test_voice_models.py` | `voice_models.py`, the one place the MCP server and the API learn what an ElevenLabs model can speak. `markup_conflict` decides whether a human may switch a scripted video to another voice, and both directions fail on a paid voicing: too strict blocks an approval for no reason, too loose voices markup the new model reads aloud or drops. So the negative controls carry as much weight as the refusals — a script with no markup fits every model, and a legacy flat script counts only `<ipa>`, because the flat voicing path strips pause markup itself. A `<phoneme>` tag conflicts with **any** model that cannot honour it, with no exemption for "the current model ignores it too": when a voice's model is edited in Settings, the edited model is both current and target, so an exemption keyed on it would wave the edit through and the only thing left standing before spend would be `generate_voice`'s own check. `phoneme_model_error` is the matching write-time check, which is what keeps approval with a video's own voice passing. `resolve_voice` pins two-level resolution (the video's voice, then the install default) and that a voice which has left the roster resolves to **nothing**, never a fallback, since spending against a voice nobody chose is worse than an error. `eleven_v4` must sit in every model set `eleven_v3` is in and in none it is not, because a probe showed it takes the same markup (IPA and bracketed pauses, no SSML). The pre-loaded `DEFAULT_VOICES` are pinned in order, with Teja as `DEFAULT_VOICE_ID`, and every entry must be on an offered model: one bad entry makes every roster reader drop the whole list, which would leave a new install with no voices |
| `test_youtube.py` | `youtube.py`, the one rule for what a mining URL may be. Every such URL becomes Gemini's `file_uri` on a paid call, so the refusals are the point: `file://`, loopback and link-local addresses, a look-alike host (`youtube.com.evil.com`), userinfo (`youtube.com@evil.com`), a port, a 10- or 12-character id, an embedded newline, tab or NUL, a non-ASCII character, an `/embed/` or channel URL, and a value that is not a string. Each is beside an accepted form — `watch?v=` (with `v` after other parameters too), `youtu.be` with a `?si=` tail, `shorts`, `live`, `m.` and an upper-case host — so a rule that refused everything fails too. Every accepted form comes back as `https://www.youtube.com/watch?v=<id>`. The list check refuses the whole list naming every bad entry (each quote clipped), deduplicates by video, and caps at 50 distinct videos, not 50 entries |
| `test_voice_models_migration.py` | The `0006` migration, which moves the model from one install-wide setting onto every roster voice. The rule it exists for: **an upgrade changes nothing a user can hear** — every voice comes out on the model the install was using, and a blank or retired stored model (`eleven_english_v1`) falls back to `eleven_multilingual_v2` rather than being carried onto voices nothing could voice with. It must never destroy a roster: the readers treat a malformed roster as empty, so a bad stamp would silently drop every voice, which is why a corrupt row is left exactly as it was. A voice that already carries a valid model keeps it, and a fresh database with no settings rows migrates cleanly |
| `test_agent_progress_migration.py` | The `0007` migration. Every existing video starts with a clean no-progress record, and every agent session recorded under the `VOICING` stage before the upgrade is relabelled `VOICING_WITH_SCENES`: the old poller carried a voicing session on into scene writing, and without the relabel the dashboard would present that spend as voicing alone. Other stages are untouched, and a `VOICING` row written after the upgrade keeps its stage |
| `test_scheduled_publishing_migration.py` | The `0008` migration. Every existing video comes out with `scheduled_at` and `scheduled_timezone` set to `''`, meaning "not scheduled" — the worker's due-time pass selects on `scheduled_at`, so any other value there would be read as a schedule |
| `test_auto_pilot_migration.py` | The `0009` migration. Every existing video comes out neither held nor blocked. A held video is one Auto Pilot refuses to post, so a stray non-zero default would silently exempt the whole existing library |
| `test_default_script_profile_migration.py` | The `0010` migration. A fresh database gets `projects.default_script_profile_id`, and every existing domain comes out with no default. A non-blank one would start writing a domain's curriculum videos in a style nobody picked for it |
| `test_image_model_migration.py` | The `0011` migration. A stored `image_model` of `gpt-image-2` moves to `gpt-image-2.5-flare`, and nothing else is rewritten: not another model, and not another key that happens to hold the same text. Without it the settings reader falls back to the Gemini default while the provider stays `openai`, and every later settings save is refused. These tests stop at `0011`, since `0016` later rewrites every non-OpenAI model and would mask what `0011` does |
| `test_gemini_3_pro_image_migration.py` | The `0015` migration. A stored `image_model` of `gemini-3-pro-image-preview`, which Google shut down, moves to its replacement `gemini-3-pro-image`, and nothing else is rewritten. Without it the settings reader would quietly fall back to the default flash model, a different and cheaper model the user never chose. These tests stop at `0015` for the same reason |
| `test_openai_only_images_migration.py` | The `0016` migration. Any stored `image_model` outside the OpenAI catalog — each Gemini model, and a hand-edited value — moves to `gpt-image-2.5-flare`, both OpenAI models are kept, and the `image_provider` row is deleted. A database that never stored either key gets nothing written, and other keys holding the same strings are untouched. Running it twice is a no-op. `NOT IN` the catalog rather than the Gemini names is the point: the MCP server reads `image_model` raw, so any off-catalog value would make every `generate_image` refuse |
| `test_auto_pilot_in_flight_migration.py` | The `0012` migration, which renames `auto_pilot_max_scheduled` to `auto_pilot_max_in_flight`. The stored number carries over **verbatim**, 0 included, so an install that never set a limit still has none, and the old row is gone. An install that never stored one gets no row. Verbatim because the new count includes everything the old one did, so the same number can only stop Auto Pilot sooner, never charge more |
| `test_topic_cap_migration.py` | The `0013` migration, which adds `projects.topic_cap` (default 100) and the `idx_videos_project_id` index. A domain at its cap is expired and takes no research topics, so the migration must never expire a domain that was filing before the upgrade: one already holding 100 or more gets its count plus 100, never above 750, and every video counts, archived and rejected included, because those are exactly what the dedup history is for. Each domain is counted on its own, and a second run is a no-op |
| `test_mining_sources_migration.py` | The `0014` migration, which brings a stored `mining_youtube_urls` list to the shape its writers now insist on. A YouTube video URL is rewritten to `https://www.youtube.com/watch?v=<id>`, a second spelling of the same video is kept once, and anything that is not a YouTube video URL is **dropped and logged** at `WARNING`, every dropped entry named, as is everything past 50 videos. Dropping rather than keeping is the point: the dashboard re-sends the whole list on every change and the writer refuses any list with a bad entry, so one leftover would make every later save fail. A value that is not a JSON list is cleared and logged, an empty list and a missing row are left alone, and a list with nothing to drop logs nothing |
| `test_auth.py` | `auth.py`, the service tokens and the admin password. The secrets directory is **0700 and its files 0644**: Compose mounts each file on its own, which bypasses the directory's permissions inside a container, and the dashboard runs as uid 1001, so a 0600 file would be unreadable there. `ensure_secrets` never replaces a secret (it refills an empty one). **Rotation keeps the inode**, because a bind mount pins the inode it was started with and an atomic rename would leave every running container on the old value. A missing or empty file raises rather than reading as an empty token, so every caller fails closed. A malformed stored hash never verifies and never raises, and the password hash is one bare `settings` row outside `SETTINGS_SPEC` |
| `test_backup.py` | `backup_db()` — the online-backup API, atomic filename reservation between concurrent callers, and failure handling |
| `test_ids_and_jobfiles.py` | `ids.py` and `jobfiles.py`, which every process uses to turn an id into a path. Each refusal sits beside a working control, because both failures are silent until they hit: a check too strict breaks a real id shape (`vid_<hex12>`, a UUID, `proj_<hex8>`, `manual`, a kebab slug), and one too loose is a path traversal (`../x`, an absolute path, a separator, a NUL, a non-string, 129 characters, a trailing newline — `re.match` with `$` accepts that last one, which is why the check is a `fullmatch`). The looser `is_component` is pinned separately: a legacy id with a dot or a space must stay usable at every filesystem use, for videos as well as projects, which is the whole reason there are two checks. It still refuses `.`, `..`, a separator, a NUL or other control character and a name over 255 bytes (counted in UTF-8, so 128 two-byte characters are refused), and the path helpers refuse the same video ids, while a legacy `a.b`, `Spaced Name` or 129-character id derives its job files, images and output, as a video id and as a project id. The 128-character cap is pinned as a creation rule only: it once leaked into `is_component` and moved every longer legacy video to `FAILED`. `job_file`, `images_dir` and `output_file` derive the fixed layout and refuse a symlink in any component below the root — including one that stays inside it, `vid_a` → `vid_b` or `proj_a` → `proj_b`, which containment alone passes and which would hand one video another's files (removing the per-component walk fails those two tests). `scene_file` (the namespaced form, and the legacy flat form for an empty `video_id`) and `image_file` refuse the same links and a name that is not one component. A symlinked root is allowed, since dev setups link the data directory, and a path that does not exist yet still derives, since writers ask for files they are about to create. `ignore_symlinks` keeps a link inside `images/` out of a `copytree`, which otherwise follows it. A name that gets a suffix must leave room for it: `output_file` and `scene_file` (both forms) refuse a 252-byte stem, whose `.mp4`/`.tsx` name would be 256 bytes, and create nothing, while a 251-byte stem's file is actually created — the controls write the file for real, because the bound being guarded is the filesystem's (`ENAMETOOLONG`), and a 252-byte id is still a valid job directory. Before, `is_component` passed the stem and the write failed part-way through a render or a tool |
| `test_logging.py` | The shared JSONL logging module — redaction, retention, cross-service reads, and the Werkzeug noise filter |
| `test_version.py` | `version()` — the single source every release script and running service reads — and the version rule: SemVer with an optional prerelease, never `+build` metadata, plus the development-branch marker `develop`, which `is_valid()` accepts and `is_release()` refuses. The real `VERSION` file is checked against `is_valid()`, so the suite passes on the development branch and on a release line alike. It also pins `GITHUB_REPO` to a bare lowercase `owner/name`: it is pasted into github.com URLs and `gh --repo`, and its owner is the default image namespace, which Docker refuses in upper case |

---

## What these encode

**The WAL-switch race is a regression pin, not a functional test.** `connect()`'s `_ensure_wal`
docstring records a measured failure rate — 4 threads racing `PRAGMA journal_mode=WAL` on a
brand-new file failed 17 times out of 100 with no retry. A single race in a test would therefore only
catch a reintroduced bug at roughly that same 17% rate, worse than a coin flip.
`test_concurrent_connect_against_a_new_file_does_not_race` runs the race 30 independent times against
30 separate fresh files instead, which drops the odds of a 17%-rate regression slipping through by
luck to under half a percent, while still finishing in well under a second — each race is only four
`connect()` calls against an empty file.

**A migration is stamped in the same transaction it runs in, and only if it commits.**
`test_a_failing_migration_is_not_stamped` and `test_a_failing_migration_rolls_back_the_whole_run`
both exist because the alternative — recording success before or outside the transaction — is the
one outcome worse than not migrating at all: a database that claims to be at a version it never
actually reached, with every later `migrate()` call trusting that lie and never trying again. The
rollback test specifically checks that a *later* migration's failure also undoes an *earlier* one
applied in the same run, which is the direct cost of one-transaction-per-run rather than
one-per-migration — a cost `db.py` accepts because per-migration commits would release the write
lock between migrations and reopen the exact race two concurrent `migrate()` calls exist to avoid.

**`test_concurrent_migrate_applies_once` is the safety argument for "every process calls
`migrate()`" made concrete.** Four threads call `migrate()` against the same brand-new database at
once; the assertion is that exactly one of them actually applies anything and the database ends at
the right version, not that all four somehow cooperate. That is what makes it safe for Flask, MCP,
the render worker, onboarding, `clear_db.py` and the VQA seed generator to each call `migrate()`
themselves with no coordination between them.

**A backup filename is reserved atomically, and the concurrency tests force the race rather than
hoping for it.** Two containers starting together genuinely do back up within the same one-second
stamp — that was observed on an ordinary restart, not theorised — so `backup_db` cannot prove a
name free and open it as a second step. The gap between those two moments is the whole defect:
both callers can observe the same name as absent, and if either then fails, its cleanup unlinks the
*other* caller's completed snapshot while that caller proceeds into the migration believing it has a
rollback point. `test_two_concurrent_backups_in_the_same_stamp_land_on_different_files` and
`test_a_failed_concurrent_backup_does_not_delete_a_winners_backup` are the two halves of that — the
second is the one that matters, because it is the one where data is lost rather than merely
duplicated. Both drive the race through a two-party barrier that blocks every "not yet taken" answer
until both threads have seen it, so the interleaving is reproduced on every run instead of on
scheduler luck; a bare thread race would pass most of the time against the broken code and read as
a flake when it did not. The reservation uses `os.O_CREAT | os.O_EXCL`, which is what lets the
failure-cleanup `unlink` be safe at all: the file was created by *this* call, not merely seen to be
absent by it. `test_backup_reservation_gives_up_after_too_many_collisions` bounds the retry loop so
a directory that can never yield a free name fails loudly rather than spinning.

**`backup_db()` is tested against a writer that is mid-transaction, not just an idle file.**
`test_backup_is_consistent_while_a_writer_holds_the_database` opens a second connection, starts a
write, leaves it uncommitted, and takes a backup while it is still open — then checks the backup
passes `PRAGMA integrity_check` and contains none of the uncommitted row. A plain file copy
(`shutil.copy`) taken at that exact moment would be torn: readable enough to look fine, and only
provably broken the day someone tries to restore it. This is the reason `backup_db()` uses SQLite's
own online backup API instead.

**The two fixture databases are hand-written, not generated from the current schema.** A fixture
built by asking today's code to create a database would converge trivially against today's
migrations and prove nothing about a real upgrade. `pre_agents.sql` and `pre_publishing.sql` are
typed out as they would have looked before this project had a migration system — `pre_publishing.sql`
is the older of the two: no `agents`/`agent_deck` tables, no `voice_id`, no `tts_text`, no
`notified_status`, and the pre-rename `animatability_score` column. Both carry rows sitting at
statuses this project has since retired or renamed (`SCRIPTING`, `VIDEO_REVISION_REQUESTED`,
`RENDER_READY`), which is what proves `0001_baseline.py`'s one-time status rewrites actually reach a
real old row rather than only a freshly-created one. `test_the_animatability_rename_carries_its_values`
and `test_a_user_set_setting_is_not_overwritten` are the same idea applied to a rename and to a
user-supplied value: migrating must never silently discard data that existed before the migration
system did.

**`test_logging.py`'s redaction tests exist on two independent axes because one alone misses real
leaks.** A *pattern* axis catches a labelled or provider-shaped secret (`Authorization: Bearer …`,
an `AIza…` literal, a URL query parameter) even when the value itself was never seen before; a
*value* axis catches a secret that was read from the settings table and is now appearing somewhere
with no recognisable shape at all, such as a webhook token embedded in a URL *path* rather than a
labelled field or query string — the shape neither pattern rule was written for.
`test_a_discord_webhook_token_is_redacted_from_the_path` is the regression pin for exactly that case,
because httpx logs the full request URL in its own log lines, and a webhook's credential lives in the
path, not a header. A short or empty stored secret is deliberately exempted
(`test_a_short_secret_is_ignored_rather_than_redacting_the_whole_line`) so an unset key does not turn
into a rule that redacts everything.
`test_elevenlabs_keys_basic_auth_and_cookies_are_redacted` pins three shapes the pattern axis
once missed: an ElevenLabs `sk_` key (the OpenAI rule wants a hyphen), the credential after
`Authorization: Basic` (the value group used to stop at the space and redact only the word "Basic"),
and `Cookie:`/`Set-Cookie:` headers. The cookie rule needs a header shape, not just the word, so
ordinary text about cookies is left alone.

**The value axis is only live once the secret provider has actually been called, and that turned out
to be the fragile part.** The formatter caches a resolved secret set for a minute so a rotated key
starts being redacted without a restart, and it marks "never fetched" with a sentinel rather than
with `0.0`. That distinction is the whole point:
`test_secrets_are_redacted_on_a_freshly_booted_machine` exists because `time.monotonic()` counts from
system boot, so on a machine that has just started it is a small number — and comparing it against a
`0.0` marker made "is the cache stale?" answer *no* for the first sixty seconds of uptime. The
provider was never called, and nothing was redacted, during exactly the window when startup failures
(a database that is not up yet, a key that fails validation) are being logged. Any machine with real
uptime hides it completely. The test pins an explicit small clock instead of hoping to run somewhere
freshly booted.

**Logging setup must never be able to take a process down.** `setup_json_logging` runs at import
time in every service, so `test_setup_on_a_missing_uncreatable_directory_returns_none_and_does_not_raise`
and its sibling for an existing-but-unwritable directory both pin the same outcome: degrade to
stdout-only, never raise. Host-side pytest has no `/logs` and cannot create one, which is exactly the
condition being guarded against, not just a test-environment inconvenience.

**`version()` never raises**, including when `TUBEMATIC_VERSION` is exported but blank — the common
shape of "a shell script sets a variable and forgets to fill it in" — which
`test_blank_env_override_is_ignored` pins against silently reporting `0.0.0` in a release. The
lookup rule is "the `VERSION` file beside the package directory," verified directly in
`test_version_file_sits_beside_the_package`, because that is the same relationship the Dockerfile's
`COPY VERSION /app/lib/VERSION` has to preserve for the in-container lookup to agree with the host.
