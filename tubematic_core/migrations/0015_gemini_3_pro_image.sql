-- 0015 — gemini-3-pro-image-preview leaves the image catalog (TMDEV-166).
--
-- Google shut the preview down; gemini-3-pro-image is its replacement. An
-- install whose scene images were set to the preview moves to the GA model,
-- which keeps the pro-tier choice. Without this the settings reader would
-- quietly coerce the unknown value back to the Gemini default, a cheaper and
-- different model the user never picked. Only that exact stored value is
-- rewritten.

UPDATE settings SET value = 'gemini-3-pro-image'
WHERE key = 'image_model' AND value = 'gemini-3-pro-image-preview';
