-- 0009 — Auto Pilot's two per-video marks (TMDEV-139).
--
-- auto_pilot_hold is set when a human cancels a scheduled post. Without it the
-- video returns to VIDEO_APPROVED and Auto Pilot schedules it again on the next
-- worker tick, so a cancel could never stick.
--
-- auto_pilot_blocked holds "<status>@<updated_at>" once Auto Pilot has
-- commented that it cannot approve a video at a checkpoint. The worker ticks
-- every 20 seconds; the mark is what makes that comment appear once per
-- arrival rather than once per tick. '' means no such comment was written.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time, which refuses two statements at once.

ALTER TABLE videos ADD COLUMN auto_pilot_hold INTEGER NOT NULL DEFAULT 0;

ALTER TABLE videos ADD COLUMN auto_pilot_blocked TEXT NOT NULL DEFAULT '';
