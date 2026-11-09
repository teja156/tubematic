-- 0019 — renderers: the machines that render, and the leases they render under (TMDEV-189).
--
-- A renderer no longer reads the database. It talks to the API's render
-- gateway over HTTPS, so the API needs to know who may call it (`renderers`,
-- with a hashed, expiring credential per remote machine), how a new machine
-- proves it was invited (`renderer_enrollments`, one-time secrets, hashed),
-- and how long each machine takes per frame (`render_timings`, which the
-- claim-time scheduler estimates from).
--
-- The built-in renderer is a row like any other, so it takes exactly the path
-- a remote one does. Its credential is not stored here: the gateway compares
-- it with the builtin_renderer_token secret file on every request, so rotating
-- that file needs no row update and no restart.
--
-- videos gains the lease: which renderer holds a RENDERING video, until when,
-- when it started, and when its mp4 arrived. render_claim_id names one claim:
-- a fresh random id per claim, so a renderer whose lease ran out (and which
-- may even have claimed the same video again since) cannot upload or report
-- for the claim it lost; the bundle, the upload and the result all name it. A RENDERING row left by a
-- pre-upgrade renderer has renderer_id '' and an empty lease, which the
-- worker's lease sweep reads as expired, so it is re-queued like a restart.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time.

CREATE TABLE IF NOT EXISTS renderers (
    id                       TEXT PRIMARY KEY,           -- 'builtin' or 'r_<12 hex>'
    name                     TEXT NOT NULL,
    builtin                  INTEGER NOT NULL DEFAULT 0,
    enabled                  INTEGER NOT NULL DEFAULT 1,
    machine_id               TEXT NOT NULL DEFAULT '',
    host                     TEXT NOT NULL DEFAULT '',
    credential_hash          TEXT NOT NULL DEFAULT '',
    previous_credential_hash TEXT NOT NULL DEFAULT '',
    credential_issued_at     TEXT NOT NULL DEFAULT '',
    credential_expires_at    TEXT NOT NULL DEFAULT '',   -- '' = never
    version                  TEXT NOT NULL DEFAULT '',
    compute                  TEXT NOT NULL DEFAULT '{}', -- {"cpus","memory_bytes","gpus":[{"name","uuid","memory_mb"}]}
    gpu_probe                TEXT NOT NULL DEFAULT '',   -- last probe JSON, '' = none yet
    gpu_verified             INTEGER NOT NULL DEFAULT 0,
    gpu_probe_requested_at   TEXT NOT NULL DEFAULT '',
    last_heartbeat_at        TEXT NOT NULL DEFAULT '',
    state                    TEXT NOT NULL DEFAULT 'idle', -- reported: idle | rendering
    current_video_id         TEXT NOT NULL DEFAULT '',
    last_error               TEXT NOT NULL DEFAULT '',
    created_at               TEXT NOT NULL,
    removed_at               TEXT                        -- NULL = active
);

CREATE TABLE IF NOT EXISTS renderer_enrollments (
    secret_hash TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    renderer_id TEXT
);

CREATE TABLE IF NOT EXISTS render_timings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    renderer_id TEXT NOT NULL,
    kind        TEXT NOT NULL,                           -- 'dom' | 'cartoon_3d' | 'mascot'
    on_gpu      INTEGER NOT NULL,
    frames      INTEGER NOT NULL,
    seconds     REAL NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_render_timings_renderer ON render_timings (renderer_id, kind, id);

ALTER TABLE videos ADD COLUMN renderer_id TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN render_lease_until TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN render_started_at TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN render_uploaded_at TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN render_claim_id TEXT NOT NULL DEFAULT '';

-- The built-in renderer. Stamped with the time the migration ran (the same
-- UTC format every other timestamp uses); the API also re-creates this row at
-- startup if it is ever missing.
INSERT OR IGNORE INTO renderers (id, name, builtin, enabled, created_at)
VALUES ('builtin', 'Built-in renderer', 1, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
