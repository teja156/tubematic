-- 0004 — pause exists only on curriculum seeds (TMDEV-115).
--
-- For a curriculum seed the domain is the SOURCE of its topics, so pausing it
-- stops generation at the root. For any other domain it is only where trending
-- or mining files a topic, so pausing it could never stop the subject being
-- researched — the topic simply went into another domain. Pause is therefore
-- refused on a non-seed from now on, and no screen offers a control for one.
--
-- That makes this backfill load-bearing: a non-seed row paused by an older
-- install would otherwise stay paused forever with nothing able to change it.
-- A paused seed is left alone — its pause still means something and is still
-- controllable.

UPDATE projects SET status = 'active' WHERE status = 'paused' AND is_curriculum_seed = 0;
