-- 0013 — a cap on how many topics a domain may ever hold (TMDEV-153).
--
-- Research deduplicates against a domain's whole topic history, archived
-- videos included, so that history has to stay a bounded size. A domain whose
-- count of videos ever filed reaches topic_cap is expired: research files
-- nothing more into it until a human raises the cap. Expiry is derived on
-- every read, never stored.
--
-- 100 is the default. A domain already holding 100 or more topics would expire
-- the moment it was upgraded, so it gets 100 of headroom over what it holds,
-- up to the 750 maximum. Every video counts, archived and rejected included:
-- they are exactly what the history is for.
--
-- One statement per line group: db._split_statements feeds these to
-- con.execute() one at a time.

ALTER TABLE projects ADD COLUMN topic_cap INTEGER NOT NULL DEFAULT 100;

UPDATE projects
SET topic_cap = MIN(750, (SELECT COUNT(*) FROM videos v WHERE v.project_id = projects.id) + 100)
WHERE (SELECT COUNT(*) FROM videos v WHERE v.project_id = projects.id) >= 100;

-- The cap is checked by counting a domain's videos on every insert.
CREATE INDEX idx_videos_project_id ON videos(project_id);
