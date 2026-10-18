-- 0010 — a domain's default script profile (TMDEV-145).
--
-- The profile a domain's curriculum videos are seeded with when they are
-- created, like default_visual_style. '' means no default: the video starts
-- with no profile, the static skill's generic style.

ALTER TABLE projects ADD COLUMN default_script_profile_id TEXT NOT NULL DEFAULT '';
