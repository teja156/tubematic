-- 0007 — the poller's no-progress count and stuck flag (TMDEV-129).
--
-- The cron poller is a looping supervisor now, so a video the agent cannot
-- move forward would be re-dispatched every few minutes instead of once per
-- tick. After each session the supervisor asks the API whether the video's
-- status changed; an unchanged status increments agent_no_progress_count, and
-- at the cap (pipeline.AGENT_NO_PROGRESS_CAP) agent_stuck_at is stamped and
-- the poller stops dispatching the video until a human acts on it.
--
-- Persisted rather than held in the supervisor: the supervisor exits when it
-- runs out of work, and a count that reset with it would never reach the cap.
--
-- agent_stuck_at NULL means "not stuck". A human status change (PATCH
-- /videos/<id>) or the dashboard's Retry agent clears both columns.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time, which refuses two statements at once.

ALTER TABLE videos ADD COLUMN agent_no_progress_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE videos ADD COLUMN agent_stuck_at TEXT;

-- The key of the last session whose outcome was counted. A supervisor that dies
-- after its outcome report commits but before it deregisters the session leaves
-- its successor to report it again; the key makes that a no-op instead of a
-- second no-progress session. Only the last key is needed: a video has at most
-- one session at a time, and a successor finishes a dead session's bookkeeping
-- before the video can be dispatched again.
ALTER TABLE videos ADD COLUMN agent_last_outcome_key TEXT;

-- No backfill: every existing video starts with a clean record, which is what
-- both defaults already say.

-- The same poller change narrows what a VOICING-stage agent session means.
-- Before it, a session that started at VOICING voiced the script and carried
-- straight on into scene writing — VOICING is not a human checkpoint — so its
-- cost covered both. From here on a session does one stage and stops at
-- VOICE_READY. Every VOICING row that exists as this runs was written by the
-- old poller, so it is relabelled once, and the dashboard names it
-- "Voicing & scene writing" while a plain VOICING row reads "Voicing". Only
-- agent sessions carry a stage; no other usage row is touched.

UPDATE usage_event_videos SET stage = 'VOICING_WITH_SCENES' WHERE stage = 'VOICING';
