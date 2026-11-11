-- 0021 — the video's last successful render: which renderer, and how long (TMDEV-206).
--
-- videos.renderer_id is the render lease, not a record: the render gateway
-- clears it the moment the mp4 arrives, and render_timings (the scheduler's
-- history) names no video. So nothing said which machine made a video or how
-- long it took. The gateway now writes these columns in the same statement
-- that accepts a successful result, and the next successful render overwrites
-- them; a failed or timed-out attempt leaves them alone.
--
-- last_render_renderer_name is the renderer's name at the time of the render,
-- so renaming or removing that renderer later does not rewrite the record.
-- last_render_seconds is the Remotion run as the renderer measured it (the same
-- figure render_timings keeps), not the time spent fetching the bundle or
-- uploading the mp4; 0 = not reported.
--
-- No backfill: '' / 0 is right for every existing row, since no earlier
-- version kept this, and the dashboard hides the rows when the id is ''.
ALTER TABLE videos ADD COLUMN last_render_renderer_id TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN last_render_renderer_name TEXT NOT NULL DEFAULT '';
ALTER TABLE videos ADD COLUMN last_render_on_gpu INTEGER NOT NULL DEFAULT 0;
ALTER TABLE videos ADD COLUMN last_render_seconds REAL NOT NULL DEFAULT 0;
