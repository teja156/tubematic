-- 0025 — the script formula, chosen before the script (TMDEV-213).
--
-- A video's formula is decided once, after its visual style and before its
-- script: by Auto (the agent, through choose_script_formula), or by a person.
-- These columns hold the decision, so the script is written in it, the
-- dashboard can show why, and a person can switch at Script Ready.
--
-- videos.formula_choice: the formula a person chose for the video, an id from
-- tubematic_core/formulas/, or '' = Auto. Seeded from the domain's default
-- when the video is filed; writable at TOPIC_PROPOSED.
-- videos.formula_pick: the formula the script is to be written in. '' = not
-- decided yet. The person's choice when there is one, else Auto's.
-- videos.formula_runner_up: the formula that came second, offered as a switch
-- at Script Ready. On a video with a person's choice it is what Auto would
-- have picked, when that differs.
-- videos.formula_reason: one sentence on why, shown beside the pick.
-- projects.default_formula_id: the formula new videos in the domain take as
-- their formula_choice, or '' = Auto.
--
-- formula_id (0023) stays what the stored script follows; it is written with
-- the script and must equal formula_pick when a pick is on record.
--
-- No backfill: '' is the right value for every existing row. A video scripted
-- before this migration has no pick, and one waiting at TOPIC_APPROVED gets
-- its pick when its agent session reaches it.
ALTER TABLE videos ADD COLUMN formula_choice TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN formula_pick TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN formula_runner_up TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN formula_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN default_formula_id TEXT NOT NULL DEFAULT '';
