-- 0016 — OpenAI becomes the only image provider (TMDEV-165).
--
-- The image_provider setting and the Gemini image models are gone. Every
-- install's scene images now come from OpenAI, so a stored image_model that
-- is not an OpenAI catalog model moves to gpt-image-2.5-flare, the default,
-- and the retired image_provider row is deleted.
--
-- Load-bearing, not tidiness: the MCP server reads image_model raw, with no
-- coercion, so any off-catalog value left behind would make EVERY
-- generate_image call refuse. Hence NOT IN the catalog rather than a list of
-- the three Gemini names. The catalog is copied here as it stood at this
-- migration; migrations are immutable snapshots.
--
-- One-way: an older version reading this database finds no image_provider row,
-- falls back to 'gemini' while image_model holds an OpenAI model, and refuses
-- every settings save. Going back means restoring the pre-upgrade backup.

UPDATE settings SET value = 'gpt-image-2.5-flare'
WHERE key = 'image_model'
  AND value NOT IN ('gpt-image-2.5-flare', 'gpt-image-2.5-sunburst');

DELETE FROM settings WHERE key = 'image_provider';
