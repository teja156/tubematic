-- 0020 — what Auto picked for a video's style, before its script (TMDEV-203).
--
-- Auto now decides at TOPIC_APPROVED, before the script is written, and may
-- pick any style pack. A pick is written into videos.visual_style itself, so
-- every reader of that column (the gates, the review prompt, the authoring
-- skill) sees the picked style with no change. These columns record that the
-- value came from Auto, the runner-up the dashboard offers as a switch, and the
-- one-sentence reason shown beside it.
--
-- style_pick: a pack id, 'scenes' (Auto kept the mixed scene system and left
-- visual_style at 'auto'), or '' = Auto has not decided. Written once by the
-- agent (choose_visual_style); reset to '' when the video goes back to
-- TOPIC_PROPOSED, since the topic it was decided on is about to change.
--
-- No backfill, unlike 0017: '' is the right value for every existing row. A
-- video scripted before this migration finishes the way Auto worked then (the
-- mixed scene system at VOICE_READY), and one not yet scripted is routed when
-- the agent next picks it up.
ALTER TABLE videos ADD COLUMN style_pick TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN style_runner_up TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN style_reason TEXT NOT NULL DEFAULT '';
