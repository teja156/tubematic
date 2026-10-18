-- 0003 — the agent effort level (TMDEV-106).
--
-- The Claude CLI takes `--effort <low|medium|high|xhigh|max>` alongside
-- `--model`, and both apply in -p mode. Effort is stored exactly the way the
-- model is: a per-agent default, overridable per video, frozen once the video
-- leaves TOPIC_PROPOSED.
--
-- videos.agent_effort '' means "use this video's agent's effort", the same way
-- a blank agent_model means "use the agent's models[0]".
-- agents.effort is the install-wide default, mirroring agents.models[0].
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time, which refuses two statements at once.

ALTER TABLE videos ADD COLUMN agent_effort TEXT NOT NULL DEFAULT '';

ALTER TABLE agents ADD COLUMN effort TEXT NOT NULL DEFAULT 'high';

-- NO BACKFILL, deliberately — and that is worth stating, because 0002's
-- trailing UPDATE makes one look mandatory. There, ADD COLUMN applying its
-- default to existing rows was the bug: 'auto' would have handed the agent
-- permission to re-style every video already in flight. Here both defaults are
-- exactly right for an existing row. A video that predates this migration has
-- no per-video pick and should follow its agent, which is what '' means; and
-- 'high' on every existing agent is precisely the requested default. An UPDATE
-- here could only write the value the column already holds.
