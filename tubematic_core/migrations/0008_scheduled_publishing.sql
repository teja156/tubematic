-- 0008 — when a scheduled post goes out (TMDEV-133).
--
-- A video can be scheduled instead of published now: postforme holds the post
-- and sends it at scheduled_at, and the video waits in SCHEDULED until then.
--
-- scheduled_at is UTC ISO (…Z), the worker's due-time key. scheduled_timezone
-- is the IANA zone the human picked, kept only so the time can be shown back in
-- the zone it was chosen in — the dashboard's own zone may differ.
--
-- '' means "not scheduled". The status needs no migration: videos.status has no
-- CHECK constraint.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time, which refuses two statements at once.

ALTER TABLE videos ADD COLUMN scheduled_at TEXT NOT NULL DEFAULT '';

ALTER TABLE videos ADD COLUMN scheduled_timezone TEXT NOT NULL DEFAULT '';
