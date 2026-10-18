-- 0002 — the per-video visual style (TMDEV-101).
--
-- visual_style is the human's choice, made once at the topic checkpoint and
-- frozen after it, exactly like script_profile_id and agent_model.
-- resolved_visual_style is what the agent settled on when the choice was
-- 'auto', written once and never re-decided — a revision round that re-rolled
-- it would mix two registers' assets into one render.
-- projects.default_visual_style seeds the choice for curriculum-strategy
-- videos filed into that domain; '' means the project has no default.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time, which refuses two statements at once.

ALTER TABLE videos ADD COLUMN visual_style TEXT NOT NULL DEFAULT 'auto';

ALTER TABLE videos ADD COLUMN resolved_visual_style TEXT NOT NULL DEFAULT '';

ALTER TABLE projects ADD COLUMN default_visual_style TEXT NOT NULL DEFAULT '';

-- Load-bearing backfill, and the easy half to drop. ADD COLUMN applies its
-- DEFAULT to every EXISTING row too, so without this every video already in
-- flight would silently become 'auto' and be re-styled by the next agent run
-- that touches it. New rows are unaffected: none can exist before this
-- migration has committed.
UPDATE videos SET visual_style = 'motion_graphics';
