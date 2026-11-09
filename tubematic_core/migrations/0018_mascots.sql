-- 0018 — mascots: an optional on-screen character that reacts to the narration.
--
-- A mascot is a library entry (`mascots`) with immutable numbered versions
-- (`mascot_versions`): a video pins the version it was authored against, so
-- approving a changed mascot never alters a video already in flight. Everything
-- is OFF by default: the three new columns default to '' / 0, so no existing
-- project, video or setting changes behaviour by upgrading.
--
-- status: PENDING, BUILDING, IN_REVIEW, READY, FAILED. A mascot is pickable
-- only once approved_version > 0 and it is not archived.
CREATE TABLE IF NOT EXISTS mascots (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL DEFAULT '',
    description      TEXT NOT NULL DEFAULT '',
    builtin          INTEGER NOT NULL DEFAULT 0,
    based_on         TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'PENDING',
    approved_version INTEGER NOT NULL DEFAULT 0,
    agent_id         TEXT NOT NULL DEFAULT '',
    agent_model      TEXT NOT NULL DEFAULT '',
    agent_effort     TEXT NOT NULL DEFAULT '',
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    sheet_renders    INTEGER NOT NULL DEFAULT 0,
    error            TEXT NOT NULL DEFAULT '',
    archived         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mascot_versions (
    mascot_id      TEXT NOT NULL REFERENCES mascots(id),
    version        INTEGER NOT NULL,
    code           TEXT NOT NULL DEFAULT '',
    change_request TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT '',
    approved_at    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (mascot_id, version)
);

-- '' = no mascot. The project column seeds new videos; the video columns pin
-- the mascot and the version a video was authored against.
ALTER TABLE projects ADD COLUMN default_mascot_id TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN mascot_id TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN mascot_version INTEGER NOT NULL DEFAULT 0;

-- The shipped mascot, Tubi. Its row is seeded here, but its drawing code is
-- NOT: builtin code lives in versioned repo files
-- (renderer/remotion/mascot-builtin/<id>/v<N>/mascot.js), immutable per
-- version, so a release can ship a new version without touching the database.
-- code stays '' for a builtin and mascots.code_for reads the file instead.
-- Every value is inline: a shipped migration must do the same thing forever,
-- so it never reads a file that a later release may change.
INSERT OR IGNORE INTO mascots (id, name, description, builtin, status, approved_version, created_at, updated_at)
VALUES ('tubi', 'Tubi',
        'The Tubematic mascot: a small retro terminal whose screen is its face.',
        1, 'READY', 1, '2026-11-08T00:00:00Z', '2026-11-08T00:00:00Z');

INSERT OR IGNORE INTO mascot_versions (mascot_id, version, code, created_at, approved_at)
VALUES ('tubi', 1, '', '2026-11-08T00:00:00Z', '2026-11-08T00:00:00Z');
