-- 0026 — the angle a topic gives its opening, recorded with the topic (TMDEV-214).
--
-- Research now files a topic only when it has an angle: one sentence saying
-- what the hook will use, the angle's kind, and a score for how strong it is.
-- The dashboard shows the three with the topic at Topic Proposed, a person can
-- edit the sentence and the kind there, and the script writer starts from the
-- formula the kind points to.
--
-- angle: the sentence, at most 300 characters, or '' = no angle. angle_kind: an
-- id from tubematic_core.angles.ANGLE_KINDS, or ''; always written together
-- with angle. angle_score: 0 to 10, where 0 = unscored (a person's own angle,
-- or none).
--
-- No backfill: '' is the right value for every existing row. A topic filed
-- before this migration has no angle on record and stays usable: the agent
-- adds one when it picks the video up, and nothing refuses a video for
-- lacking one.
ALTER TABLE videos ADD COLUMN angle TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN angle_kind TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN angle_score INTEGER NOT NULL DEFAULT 0;
