-- 0017 — which renderer `auto` settled on (TMDEV-179).
--
-- The Cartoon 3D style replaces the DOM scene system instead of restricting
-- it, and `auto` may now choose it. That choice has to be recorded before any
-- scene is authored, or a revision round could re-decide and flip a
-- half-authored video from a 3D world to CSS panels, discarding every scene.
-- Values: 'dom', 'cartoon_3d'; '' = auto has not settled yet. Written once by
-- the agent (update_video), never over HTTP.
--
-- The column holds a renderer, unlike its neighbour resolved_visual_style,
-- which holds the canvas auto settled on. Different axes, both write-once.
ALTER TABLE videos ADD COLUMN resolved_renderer TEXT NOT NULL DEFAULT '';

-- Load-bearing backfill, exactly as 0002's is. ADD COLUMN applies its DEFAULT
-- to every EXISTING row, so without this every in-flight video would read as
-- unresolved and the next revision round could decide a half-authored DOM
-- video is now Cartoon 3D and throw away every scene. Every video that exists
-- predates the style, so every one of them is 'dom' by construction.
UPDATE videos SET resolved_renderer = 'dom';
