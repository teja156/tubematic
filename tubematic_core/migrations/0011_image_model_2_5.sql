-- 0011 — gpt-image-2 leaves the image catalog (TMDEV-148).
--
-- OpenAI withdrew gpt-image-2's transparent-background preview, so it is no
-- longer offered for anything; the gpt-image-2.5 family replaces it. An install
-- whose scene images were set to it moves to gpt-image-2.5-flare, the new
-- default.
--
-- Load-bearing, not tidiness: the settings reader would coerce the unknown
-- model back to the Gemini default while image_provider stayed 'openai', and
-- the provider/model cross-check would then refuse EVERY later settings save,
-- whatever key it was for. Only that exact stored value is rewritten.

UPDATE settings SET value = 'gpt-image-2.5-flare'
WHERE key = 'image_model' AND value = 'gpt-image-2';
