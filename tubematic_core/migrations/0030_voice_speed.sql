-- 0030 — a video's own voice speed (TMDEV-227).
--
-- The agent picks a speed for each video with its script (0.9 to 1.25), and a
-- person may change it at Script Ready. It replaces the roster speed of every
-- voice in that video: native ElevenLabs speed on the v2 models, a
-- pitch-keeping stretch of the recording on eleven_v3 and eleven_v4.
--
-- NULL = the video has no speed of its own and each voice speaks at its roster
-- speed, which is how every video voiced before this migration was made. No
-- backfill: an existing or in-flight video voices exactly as it did.
ALTER TABLE videos ADD COLUMN voice_speed REAL;

-- The speed the audio was last made at, written by generate_voice: what the
-- video window shows once the video is voiced. A roster speed can be edited
-- after voicing, so the roster cannot say it. NULL = not voiced since this
-- migration (the window then shows no speed).
ALTER TABLE videos ADD COLUMN voiced_speed REAL;
