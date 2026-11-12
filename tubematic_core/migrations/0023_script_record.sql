-- 0023 — what a script was built on, recorded with the script (TMDEV-211).
--
-- The script-writing skill now picks a formula for each script, drafts three
-- openings and keeps one. update_video writes that choice in the same call as
-- the script, and runs advisory checks over the words. These columns hold the
-- result, so the dashboard can show it at Script Ready and later work can
-- group videos by formula and opening.
--
-- formula_id: an id from tubematic_core/formulas/, or '' = no formula on
-- record. hook_type: the type of the opening the writer kept, an id from
-- tubematic_core.formulas.HOOK_TYPES. hook_alternatives: JSON text, the three
-- drafted openings as [{type, text, kept, note?}]. script_warnings: JSON text,
-- the checks' findings for the stored script as [{id, message}].
--
-- No backfill: '' is the right value for every existing row. A script written
-- before this migration has no formula, and nothing reads these columns to
-- decide what happens to a video.
ALTER TABLE videos ADD COLUMN formula_id TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN hook_type TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN hook_alternatives TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN script_warnings TEXT NOT NULL DEFAULT '';
