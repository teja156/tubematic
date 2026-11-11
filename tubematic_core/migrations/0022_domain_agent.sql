-- 0022 — a domain's agent, model and effort (TMDEV-207).
--
-- A domain can name the agent its new videos start on, with a model from that
-- agent's list and an effort level. The three values are copied into
-- videos.agent_id / agent_model / agent_effort when a video is filed into the
-- domain, the way default_voice_id is, and a human can still change them on
-- the video at a checkpoint.
--
-- '' on default_agent_id = Automatic: the video is dealt an agent by weight, as
-- before. '' on the model = that agent's own default; '' on the effort = that
-- agent's own level. No backfill: '' is the right value for every existing
-- domain, so no domain changes behaviour by upgrading.
--
-- 0021 belongs to another change that was in progress when this was written;
-- migrate() applies whatever schema_migrations lacks, so the order the two
-- arrive in does not matter.
ALTER TABLE projects ADD COLUMN default_agent_id TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN default_agent_model TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN default_agent_effort TEXT NOT NULL DEFAULT '';
