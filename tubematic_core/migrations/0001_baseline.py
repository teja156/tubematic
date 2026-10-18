"""0001 — the baseline schema.

Every table, column, index and one-time fixup Tubematic accumulated before it
had a migration system. This is renderer/api/pipeline.py's _init_db as it stood
at ca1d702, merged with the one statement that existed only in mcp/server.py's
copy (the SCRIPTING recovery), and frozen.

Python rather than SQL, and it has to be: SQLite has no ADD COLUMN IF NOT
EXISTS, so the guarded ALTERs that let an old database converge cannot be
written in a .sql file. Every statement here is idempotent, which is what makes
this file work as both "create the schema" and "adopt whatever exists".

*** THIS FILE HAS SHIPPED. DO NOT EDIT IT. ***
New schema work means a new migration file. Editing this one silently diverges
every database that already applied it from every database that has not.

The one exception, made here: the CREATE TABLE block below used to run through
con.executescript(), copied verbatim from the original _init_db it was frozen
from. executescript() issues its own implicit COMMIT before running, which
silently released migrate()'s run-wide BEGIN IMMEDIATE at the very first
statement of the only migration that exists — docs/17-development.md already
warns migration authors against this, and this file shipped violating its own
rule. Fixed to use db._split_statements + con.execute, same as a .sql
migration, so the whole run stays one transaction. This is behaviour-
preserving: the same 12 statements, executed in the same order, just without
the implicit commit — not a schema change.
"""
from tubematic_core.db import _split_statements

_CREATE_TABLES = """
        CREATE TABLE IF NOT EXISTS projects (
            id                  TEXT    PRIMARY KEY,
            name                TEXT    NOT NULL,
            description         TEXT    NOT NULL DEFAULT '',
            is_curriculum_seed  INTEGER NOT NULL DEFAULT 0,
            status              TEXT    NOT NULL DEFAULT 'active',
            created_at          TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS videos (
            id                    TEXT PRIMARY KEY,
            project_id            TEXT REFERENCES projects(id),
            topic                 TEXT NOT NULL,
            strategy              TEXT NOT NULL DEFAULT 'manual',
            producibility_score   INTEGER NOT NULL DEFAULT 0,
            status                TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
            title                 TEXT NOT NULL DEFAULT '',
            script                TEXT NOT NULL DEFAULT '',
            voice_file_path       TEXT NOT NULL DEFAULT '',
            timeline_path         TEXT NOT NULL DEFAULT '',
            scene_config_path     TEXT NOT NULL DEFAULT '',
            video_path            TEXT NOT NULL DEFAULT '',
            video_version         INTEGER NOT NULL DEFAULT 1,
            gemini_feedback       TEXT NOT NULL DEFAULT '',
            youtube_url           TEXT NOT NULL DEFAULT '',
            voice_id              TEXT NOT NULL DEFAULT '',
            notified_status       TEXT NOT NULL DEFAULT '',
            tts_text              TEXT NOT NULL DEFAULT '',
            agent_model           TEXT NOT NULL DEFAULT '',
            agent_id              TEXT,
            cost_cents_elevenlabs INTEGER NOT NULL DEFAULT 0,
            cost_cents_gemini     INTEGER NOT NULL DEFAULT 0,
            cost_cents_claude     INTEGER NOT NULL DEFAULT 0,
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL
        );
        -- Installed coding agents (TMDEV-90). Written only by the host-side
        -- installer (python onboard.py --install-agent <name>), which validates
        -- binary and models against the real CLI; the API may change only
        -- is_default and weight. models is a JSON list and models[0] is the
        -- agent's default model. Archived, never deleted, so a video pinned to
        -- an agent always resolves. Keep in sync: mcp/server.py's _init_db and
        -- onboard/agent_install.py (pinned by test_pipeline.py's cross-copy test).
        CREATE TABLE IF NOT EXISTS agents (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            binary        TEXT NOT NULL,
            run_path      TEXT NOT NULL,
            install_scope TEXT NOT NULL DEFAULT 'user',
            models        TEXT NOT NULL DEFAULT '[]',
            is_default    INTEGER NOT NULL DEFAULT 0,
            weight        INTEGER NOT NULL DEFAULT 1,
            verified_at   TEXT NOT NULL DEFAULT '',
            archived_at   TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        -- The shuffled assignment deck _pick_agent_id deals new videos from:
        -- a single row. cards is a JSON list of agent ids still to deal;
        -- signature is the live [id, reduced weight] list it was built from,
        -- so any weight change or (un)install rebuilds it. Keep in sync:
        -- mcp/server.py's _init_db (pinned by test_pipeline.py's cross-copy test).
        CREATE TABLE IF NOT EXISTS agent_deck (
            id        INTEGER PRIMARY KEY CHECK (id = 1),
            signature TEXT NOT NULL,
            cards     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS comments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id   TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            author     TEXT NOT NULL CHECK (author IN ('human','agent')),
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS script_profiles (
            id             TEXT    PRIMARY KEY,
            name           TEXT    NOT NULL,
            status         TEXT    NOT NULL DEFAULT 'PENDING',
            markdown       TEXT    NOT NULL DEFAULT '',
            corpus_summary TEXT    NOT NULL DEFAULT '',
            source_urls    TEXT    NOT NULL DEFAULT '[]',
            error          TEXT    NOT NULL DEFAULT '',
            attempt_count  INTEGER NOT NULL DEFAULT 0,
            archived       INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT    NOT NULL,
            updated_at     TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS script_profile_transcripts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL REFERENCES script_profiles(id) ON DELETE CASCADE,
            source_url TEXT NOT NULL,
            youtube_id TEXT NOT NULL DEFAULT '',
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        -- Publishing (TMDEV-83). One row per (video, account) target, because
        -- publishing to four accounts where two succeed cannot be represented
        -- by a single videos.status — that column is *derived* from these rows.
        -- This also retires videos.youtube_url, which is left in place but no
        -- longer read: one TEXT column cannot hold four platform URLs.
        CREATE TABLE IF NOT EXISTS video_publications (
            id                TEXT PRIMARY KEY,
            video_id          TEXT NOT NULL REFERENCES videos(id),
            platform          TEXT NOT NULL,
            social_account_id TEXT NOT NULL,
            postforme_post_id TEXT NOT NULL DEFAULT '',
            status            TEXT NOT NULL DEFAULT 'PENDING',
            post_url          TEXT NOT NULL DEFAULT '',
            error             TEXT NOT NULL DEFAULT '',
            published_at      TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );
        -- Time series, not latest-only: metric history cannot be backfilled, and
        -- without it the analytics page can only show a number rather than a
        -- trend. views/likes/comments/shares are the common subset across
        -- platforms and are deliberately NULLable — "not reported" and
        -- "reported as zero" are different claims. raw_json keeps the whole
        -- per-platform payload, which is what makes Facebook's differently
        -- named metrics recoverable later.
        CREATE TABLE IF NOT EXISTS video_metrics (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_id TEXT NOT NULL REFERENCES video_publications(id) ON DELETE CASCADE,
            fetched_at     TEXT NOT NULL,
            views          INTEGER,
            likes          INTEGER,
            comments       INTEGER,
            shares         INTEGER,
            raw_json       TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_video_publications_video
            ON video_publications(video_id);
        CREATE INDEX IF NOT EXISTS idx_video_metrics_publication
            ON video_metrics(publication_id, fetched_at);
    """


def up(con) -> None:
    for statement in _split_statements(_CREATE_TABLES):
        con.execute(statement)
    # Migrate existing DBs that pre-date these columns.
    for col, ddl, table in [
        ("is_curriculum_seed", "INTEGER NOT NULL DEFAULT 0", "projects"),
        ("status",             "TEXT NOT NULL DEFAULT 'active'", "projects"),
        ("ai_review_count",    "INTEGER NOT NULL DEFAULT 0", "videos"),
        ("render_fail_count",  "INTEGER NOT NULL DEFAULT 0", "videos"),
        ("script_segments",    "TEXT", "videos"),
        ("voice_id",           "TEXT NOT NULL DEFAULT ''", "videos"),
        # VQA-6: the exact text sent to ElevenLabs (post-respell/lexicon
        # substitution) — written by generate_voice, read by the render
        # worker as the AI review's pronunciation reference.
        # Keep in sync: mcp/server.py's _init_db.
        ("tts_text",           "TEXT NOT NULL DEFAULT ''", "videos"),
        # TMDEV-73: per-video override for the cron agent's model. Blank means
        # the video's agent's own default, its models[0] (TMDEV-90 — this used
        # to be settings.agent_model). A non-blank value must be one of that
        # agent's installed models; see _agent_model_error.
        ("agent_model",        "TEXT NOT NULL DEFAULT ''", "videos"),
        # TMDEV-90: the agent this video is pinned to for life, picked at
        # creation by _pick_agent_id. NULL means "the default agent at dispatch
        # time" — rows from before agents existed, or created with none installed.
        # Keep in sync: mcp/server.py's _init_db.
        ("agent_id",           "TEXT", "videos"),
        # TMDEV-81: which script profile this video's script is written in.
        # Blank means "no profile" — the static script-writing skill falls back
        # to its own generic style section. Per-video only: no project tier and
        # no install-wide default.
        # Keep in sync: mcp/server.py's _init_db.
        ("script_profile_id",  "TEXT NOT NULL DEFAULT ''", "videos"),
        # TMDEV-83: the publish dialog's AI-suggested title/description, cached
        # here so reopening the dialog does not re-run a paid Gemini call. Not
        # the same thing as videos.title, which is the pipeline's own short
        # display name — these are what actually gets sent to the platforms,
        # and the human edits them before publishing.
        # Keep in sync: mcp/server.py's _init_db.
        ("publish_title",       "TEXT NOT NULL DEFAULT ''", "videos"),
        ("publish_description", "TEXT NOT NULL DEFAULT ''", "videos"),
        # TMDEV-84: when the video's files were deleted and the row archived.
        # A nullable column, not an ARCHIVED status — a status would overwrite
        # what the video actually was (published, failed, ...). NULL means live.
        # Keep in sync: mcp/server.py's _init_db.
        ("archived_at",         "TEXT", "videos"),
    ]:
        exists = con.execute(
            f"SELECT 1 FROM pragma_table_info('{table}') WHERE name = ?", (col,)
        ).fetchone()
        if not exists:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    # TMDEV-5: the arrival a Discord notification was last sent for, written as
    # "<status>@<updated_at>", so the render worker's sweep can tell a fresh
    # arrival at a checkpoint from a video that has simply been sitting at one.
    # Pairing the status with its timestamp is what makes a *second* arrival
    # (a revision round returning to SCRIPT_READY) distinguishable from the
    # first without any write site having to know notifications exist — see the
    # long note at worker.py's _ARRIVAL_SQL. A marker naming a status the video
    # has since left is simply never matched again, so nothing clears it.
    # Handled outside the generic loop above because it needs the one-time
    # backfill below.
    # Keep in sync: mcp/server.py's _init_db.
    has_notified = con.execute(
        "SELECT 1 FROM pragma_table_info('videos') WHERE name = 'notified_status'"
    ).fetchone()
    if not has_notified:
        con.execute("ALTER TABLE videos ADD COLUMN notified_status TEXT NOT NULL DEFAULT ''")
        # Mark every existing row's current arrival as already notified. Without
        # this, the first sweep after an upgrade would announce every video
        # parked at a checkpoint — possibly months of backlog, all at once.
        # Must match _ARRIVAL_SQL exactly; storing a bare status here would
        # match nothing and re-arm the very blast this prevents.
        con.execute("UPDATE videos SET notified_status = status || '@' || updated_at")
    # One-time rename: VIDEO_REVISION_REQUESTED → REVISION_REQUESTED
    con.execute("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE status = 'VIDEO_REVISION_REQUESTED'")
    # One-time rename: RENDER_READY → VOICE_READY (TMDEV-32 — the old name
    # meant "still needs scene authoring", the opposite of ready-to-render).
    con.execute("UPDATE videos SET status = 'VOICE_READY' WHERE status = 'RENDER_READY'")
    # Only mcp/server.py's copy had this one. The SCRIPTING status was removed
    # (scripting is instant); a stranded row falls back to TOPIC_APPROVED so the
    # agent retries it rather than sitting at a status nothing works.
    con.execute("UPDATE videos SET status = 'TOPIC_APPROVED' WHERE status = 'SCRIPTING'")
    # One-time rename: animatability_score → producibility_score (TMDEV-56 — the
    # old name predates image generation and described only SVG-diagram
    # suitability). Keep in sync: mcp/server.py's _init_db.
    has_old = con.execute(
        "SELECT 1 FROM pragma_table_info('videos') WHERE name = 'animatability_score'"
    ).fetchone()
    has_new = con.execute(
        "SELECT 1 FROM pragma_table_info('videos') WHERE name = 'producibility_score'"
    ).fetchone()
    if has_old and not has_new:
        con.execute("ALTER TABLE videos RENAME COLUMN animatability_score TO producibility_score")
    # One-time settings-key rename: max_feedback_loops → max_render_retries
    # (TMDEV-74). Copy-if-absent, never an unconditional copy: onboarding seeds
    # the settings table (step install_config) *before* this container is ever
    # built (step renderer), so on an upgrade both rows can be present and the
    # new one is the fresh answer — overwriting it with the stale row would
    # silently discard what the user just entered. The delete is unconditional
    # so the old key cannot linger and 400 the settings API as an unknown key.
    con.execute("""
        INSERT INTO settings (key, value)
        SELECT 'max_render_retries', value FROM settings WHERE key = 'max_feedback_loops'
          AND NOT EXISTS (SELECT 1 FROM settings WHERE key = 'max_render_retries')
    """)
    con.execute("DELETE FROM settings WHERE key = 'max_feedback_loops'")
    # One-way retirement of the agent_model settings key (TMDEV-90). The
    # per-video videos.agent_model column stays; the install-wide default is now
    # each agent's models[0] in the agents table. Deleted rather than left inert
    # so it cannot 400 the settings API as an unknown key.
    con.execute("DELETE FROM settings WHERE key = 'agent_model'")
