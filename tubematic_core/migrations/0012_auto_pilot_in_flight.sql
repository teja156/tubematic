-- 0012 — Auto Pilot's ceiling becomes an in-progress limit (TMDEV-150).
--
-- auto_pilot_max_scheduled counted only posts waiting in SCHEDULED, so it
-- never held when scheduling was blocked and production ran unbounded. Its
-- replacement, auto_pilot_max_in_flight, counts every video past the paid gate
-- that has not published. The key is renamed rather than redefined in place,
-- so no name is left describing the old count.
--
-- The stored number is carried over verbatim. The new count includes
-- everything the old one did and more, so the same number only ever stops
-- Auto Pilot sooner: it can never cause a charge the old setting would not
-- have, and there is no principled factor to scale it by. 0 stays 0, no limit.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time.

INSERT OR IGNORE INTO settings (key, value)
SELECT 'auto_pilot_max_in_flight', value FROM settings
WHERE key = 'auto_pilot_max_scheduled';

DELETE FROM settings WHERE key = 'auto_pilot_max_scheduled';
