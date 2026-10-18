-- 0005 — per-call usage accounting (TMDEV-107).
--
-- Before this, the only cost on record was an ElevenLabs *estimate* summed into
-- videos.cost_cents_elevenlabs, and nothing could say which model a cent went
-- to. Three tables replace that:
--
-- usage_events: one row per billable call — append-only. The usage UNITS the
-- provider reported are kept exactly (plus its raw usage object), and the price
-- applied is snapshotted onto the row beside the computed cost. Units alone
-- would silently re-price history whenever a rate is edited; cents alone could
-- never be corrected. cost_usd is NULL, never 0, when no rate was known:
-- zero is indistinguishable from "this call was free", NULL is repairable.
--
-- usage_event_videos: which videos a call was for. Most calls are for one
-- video, some for none (research, voice previews) and an agent session for a
-- whole batch — so it is a link table, not a column. Deliberately NO foreign
-- key to videos: spend outlives a deleted video, and a shared session's ÷N
-- split must not shift when one of its videos is removed.
--
-- model_prices: synced (OpenRouter, else LiteLLM) and manual rates, per model
-- and unit kind. A manual row is never touched by a sync.
--
-- videos.cost_cents_* stay (0001 is immutable) but nothing reads or writes
-- them any more.
--
-- One statement per group: db._split_statements feeds these to con.execute()
-- one at a time, which refuses two statements at once.

CREATE TABLE usage_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    session_id     TEXT,
    service        TEXT NOT NULL,
    model          TEXT NOT NULL DEFAULT '',
    operation      TEXT NOT NULL,
    units          TEXT NOT NULL DEFAULT '{}',
    raw_usage      TEXT,
    request_id     TEXT,
    cost_usd       REAL,
    cost_basis     TEXT NOT NULL,
    price_snapshot TEXT,
    estimated      INTEGER NOT NULL DEFAULT 0,
    event_key      TEXT
);

CREATE INDEX idx_usage_events_created_at ON usage_events(created_at);

CREATE INDEX idx_usage_events_model ON usage_events(service, model);

-- Makes a replayed report idempotent: an agent session's usage arrives over
-- HTTP, and a client that timed out after the server committed must be able
-- to resend without doubling the spend. NULL for calls recorded in-process,
-- which never retry (SQLite lets a UNIQUE index hold any number of NULLs).
CREATE UNIQUE INDEX idx_usage_events_event_key ON usage_events(event_key);

CREATE TABLE usage_event_videos (
    event_id INTEGER NOT NULL REFERENCES usage_events(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    stage    TEXT,
    PRIMARY KEY (event_id, video_id)
);

CREATE INDEX idx_usage_event_videos_video_id ON usage_event_videos(video_id);

CREATE TABLE model_prices (
    service        TEXT NOT NULL,
    model          TEXT NOT NULL,
    unit_kind      TEXT NOT NULL,
    usd_per_unit   REAL NOT NULL,
    source         TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    user_override  INTEGER NOT NULL DEFAULT 0,
    tiered         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (service, model, unit_kind)
);
