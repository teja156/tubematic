"""Watch figures in Analytics (TMDEV-212): how long people watched a post.

Four layers, each with its own section: the mapping from a platform's stored
payload (postforme.extract_retention), the rows of GET /analytics and
GET /videos/<id>/publications, the grouped view GET /analytics/watch-time, and
the worker storing a published video's length before its files are deleted.

The payload shapes here are the platforms' real key names with made-up numbers.

Run from renderer/api/: pytest tests/test_watch_time.py
"""
import json
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
import postforme
import worker

_FMT = "%Y-%m-%dT%H:%M:%SZ"

YOUTUBE = {"views": 200, "likes": 9, "comments": 2, "shares": 4, "engagedViews": 120,
           "averageViewDuration": 31, "averageViewPercentage": 41.5,
           "estimatedMinutesWatched": 103, "subscribersGained": 1}
INSTAGRAM = {"views": 500, "likes": 30, "comments": 3, "shares": 6, "reach": 410, "saved": 12,
             "ig_reels_avg_watch_time": 23500, "ig_reels_video_view_total_time": 9000000,
             "total_interactions": 51}
FACEBOOK = {"video_views": 90, "media_views": 140, "reactions_total": 7, "comments": 1,
            "shares": 2, "reach": 130, "video_avg_time_watched": 12000, "video_length": 60000}
TIKTOK = {"view_count": 800, "like_count": 40, "comment_count": 5, "share_count": 9}

NOTHING = dict.fromkeys(postforme.RETENTION_KEYS)


def _ago(days: float) -> str:
    return time.strftime(_FMT, time.gmtime(time.time() - days * 86400))


# ── the mapping ──────────────────────────────────────────────────────────────

def test_youtube_reports_seconds_share_and_stayed_to_watch():
    """Seconds and percent come straight through. Stayed to watch is engaged
    views over views, which YouTube alone reports. No reach, no saves."""
    assert postforme.extract_retention("youtube", YOUTUBE) == {
        "avg_watch_secs": 31, "watched_pct": 41.5, "stayed_pct": 60.0,
        "engaged_views": 120, "reach": None, "saves": None}


def test_instagram_reports_milliseconds_and_no_share_of_its_own():
    """ig_reels_avg_watch_time is milliseconds. Instagram gives no percentage
    and no video length, so without the video's own length the share is blank."""
    assert postforme.extract_retention("instagram", INSTAGRAM) == {
        "avg_watch_secs": 23.5, "watched_pct": None, "stayed_pct": None,
        "engaged_views": None, "reach": 410, "saves": 12}


def test_instagram_share_is_seconds_over_the_videos_own_length():
    out = postforme.extract_retention("instagram", INSTAGRAM, duration_secs=94.0)
    assert out["watched_pct"] == 25.0


def test_facebook_carries_its_own_video_length():
    """Both figures are milliseconds, and the share needs nothing from us."""
    assert postforme.extract_retention("facebook", FACEBOOK) == {
        "avg_watch_secs": 12, "watched_pct": 20.0, "stayed_pct": None,
        "engaged_views": None, "reach": 130, "saves": None}


def test_a_platforms_own_share_wins_over_one_worked_out_from_the_length():
    """YouTube's percentage is its own measurement. A stored length that
    disagrees (a re-render, a rounding) must not replace it."""
    assert postforme.extract_retention("youtube", YOUTUBE, duration_secs=10)["watched_pct"] == 41.5


def test_tiktok_reports_no_watch_figure_at_all():
    """Its consumer connection returns four counts and nothing else."""
    assert postforme.extract_retention("tiktok", TIKTOK, duration_secs=60) == NOTHING


def test_an_unknown_platform_and_a_missing_payload_report_nothing():
    assert postforme.extract_retention("mastodon", YOUTUBE) == NOTHING
    assert postforme.extract_retention("youtube", None) == NOTHING
    assert postforme.extract_retention("youtube", ["not", "a", "dict"]) == NOTHING


def test_no_views_means_no_stayed_figure_rather_than_zero():
    """0 of 0 is not 0%: nothing was measured."""
    raw = dict(YOUTUBE, views=0, engagedViews=0)
    assert postforme.extract_retention("youtube", raw)["stayed_pct"] is None
    assert postforme.extract_retention("youtube", {"engagedViews": 5})["stayed_pct"] is None


def test_a_reported_zero_count_stays_a_zero():
    """Nobody saved it is a reading; "not reported" is not."""
    out = postforme.extract_retention("instagram", dict(INSTAGRAM, saved=0, reach=0))
    assert out["saves"] == 0 and out["reach"] == 0
    assert postforme.extract_retention("youtube", dict(YOUTUBE, engagedViews=0))["engaged_views"] == 0


@pytest.mark.parametrize("platform, raw", [
    ("youtube", dict(YOUTUBE, views=0, engagedViews=0, averageViewDuration=0, averageViewPercentage=0)),
    ("youtube", dict(YOUTUBE, averageViewDuration=0, averageViewPercentage=0.0)),
    ("instagram", dict(INSTAGRAM, ig_reels_avg_watch_time=0)),
    ("facebook", dict(FACEBOOK, video_avg_time_watched=0)),
])
def test_an_average_of_no_seconds_is_not_a_reading(platform, raw):
    """A platform sends 0 for a post it has not measured yet. Nobody watches
    for no time, and a 0 would enter a group's median as a video that held
    nobody. So an average of 0 seconds, and a 0 share, are not reported."""
    out = postforme.extract_retention(platform, raw, duration_secs=60)
    assert (out["avg_watch_secs"], out["watched_pct"]) == (None, None)


@pytest.mark.parametrize("length", [None, 20, 60, 90])
def test_an_average_that_rounds_to_no_seconds_is_not_a_reading_either(length):
    """30 ms is 0.0 s to one decimal. The rule is applied to what the page
    shows, so it never shows 0 s for a post nobody measured, and the answer
    does not depend on how long the video happens to be."""
    out = postforme.extract_retention("instagram", dict(INSTAGRAM, ig_reels_avg_watch_time=30),
                                      duration_secs=length)
    assert (out["avg_watch_secs"], out["watched_pct"]) == (None, None)


def test_a_reported_share_of_zero_counts_as_no_share():
    """So it gets the same stand-in an absent share gets. Otherwise the same
    video would show a share or a dash depending on whether the platform sent
    a 0 or left the key out."""
    raw = dict(YOUTUBE, averageViewDuration=12, averageViewPercentage=0)
    assert postforme.extract_retention("youtube", raw, duration_secs=30)["watched_pct"] == 40.0
    assert postforme.extract_retention("youtube", raw)["watched_pct"] is None


def test_real_seconds_whose_share_rounds_to_nothing_keep_the_seconds():
    out = postforme.extract_retention("instagram", dict(INSTAGRAM, ig_reels_avg_watch_time=200),
                                      duration_secs=4000)
    assert (out["avg_watch_secs"], out["watched_pct"]) == (0.2, None)


def test_whole_seconds_that_come_to_zero_beside_a_real_share_are_kept():
    """YouTube reports whole seconds. A Short watched for under a second on
    average reads 0 with a real percentage, and that is a measurement."""
    out = postforme.extract_retention(
        "youtube", dict(YOUTUBE, averageViewDuration=0, averageViewPercentage=4.2))
    assert (out["avg_watch_secs"], out["watched_pct"]) == (0, 4.2)


def test_no_engaged_views_of_some_views_is_a_reading():
    """Views and engaged views come from one YouTube report, so when there are
    views the 0 was measured. With no views nothing was (the test above)."""
    out = postforme.extract_retention("youtube", dict(YOUTUBE, views=3, engagedViews=0))
    assert out["stayed_pct"] == 0.0


@pytest.mark.parametrize("platform, raw, duration", [
    ("youtube", dict(YOUTUBE, views=5e-324), None),
    ("instagram", INSTAGRAM, 1e-300),
    ("facebook", dict(FACEBOOK, video_length=1e-300), None),
])
def test_a_division_by_a_vanishing_number_is_not_a_figure(platform, raw, duration):
    """It comes out infinite, and an infinity in the answer is not JSON: the
    browser could not read the page's data at all."""
    out = postforme.extract_retention(platform, raw, duration_secs=duration)
    assert json.loads(json.dumps(out, allow_nan=False)) == out
    assert out["watched_pct"] is None or out["watched_pct"] < 1000
    assert out["stayed_pct"] is None or out["stayed_pct"] <= 100


@pytest.mark.parametrize("key, blank", [
    ("averageViewDuration", "avg_watch_secs"), ("averageViewPercentage", "watched_pct"),
    ("engagedViews", "stayed_pct"), ("views", "stayed_pct")])
def test_an_absurdly_large_value_is_not_a_reading_and_does_not_raise(key, blank):
    """An integer too large for a float cannot be divided. One damaged
    snapshot must not take the Analytics page down with it."""
    out = postforme.extract_retention("youtube", dict(YOUTUBE, **{key: 10 ** 400}))
    assert out[blank] is None
    assert postforme.extract_retention("instagram", dict(INSTAGRAM, reach=1e308))["reach"] is None


def test_the_stored_length_stands_in_wherever_a_payload_has_seconds_and_no_share():
    """Always the case on Instagram. Also a YouTube or Facebook payload that
    came without its own share or length."""
    raw = {k: v for k, v in YOUTUBE.items() if k != "averageViewPercentage"}
    assert postforme.extract_retention("youtube", raw, duration_secs=62)["watched_pct"] == 50.0
    raw = {k: v for k, v in FACEBOOK.items() if k != "video_length"}
    assert postforme.extract_retention("facebook", raw, duration_secs=48)["watched_pct"] == 25.0


def test_a_share_above_one_hundred_is_kept():
    """A looping Short is watched more than once. Clamping would hide that."""
    raw = dict(YOUTUBE, averageViewPercentage=134.2)
    assert postforme.extract_retention("youtube", raw)["watched_pct"] == 134.2
    assert postforme.extract_retention(
        "instagram", INSTAGRAM, duration_secs=20)["watched_pct"] == 117.5


@pytest.mark.parametrize("bad", ["31", True, -4, None, [31], float("nan")])
def test_a_value_that_is_not_a_reading_is_not_reported(bad):
    raw = dict(YOUTUBE, averageViewDuration=bad, averageViewPercentage=bad, engagedViews=bad)
    out = postforme.extract_retention("youtube", raw)
    assert (out["avg_watch_secs"], out["watched_pct"], out["stayed_pct"]) == (None, None, None)


def test_a_zero_length_cannot_divide():
    assert postforme.extract_retention("instagram", INSTAGRAM, duration_secs=0)["watched_pct"] is None
    raw = dict(FACEBOOK, video_length=0)
    assert postforme.extract_retention("facebook", raw)["watched_pct"] is None


# ── fixtures for the routes and the worker ───────────────────────────────────

@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    out, jobs = tmp_path / "output_videos", tmp_path / "jobs"
    out.mkdir()
    jobs.mkdir()
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)
    monkeypatch.setattr(pipeline, "JOBS_DIR", jobs)
    monkeypatch.setattr(worker, "DB_PATH", db)
    pipeline._init_db(db)
    return SimpleNamespace(db=db, out=out, jobs=jobs)


@pytest.fixture
def client(env):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(pipeline.create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sql(env, query, params=()):
    con = sqlite3.connect(env.db)
    con.execute(query, params)
    con.commit()
    con.close()


def _one(env, query, params=()):
    con = sqlite3.connect(env.db)
    row = con.execute(query, params).fetchone()
    con.close()
    return row[0] if row else None


def _video(env, vid, *, project="proj-1", style="auto", profile="", script="one two three",
           duration=None, archived_at=None, status="PUBLISHED"):
    _sql(env, "INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?, ?, 'now')",
         (project, f"Domain {project}"))
    _sql(env,
         "INSERT INTO videos (id, project_id, topic, title, status, visual_style,"
         " script_profile_id, script, duration_secs, archived_at, created_at, updated_at)"
         " VALUES (?, ?, 'T', ?, ?, ?, ?, ?, ?, ?, 'now', 'now')",
         (vid, project, f"Title {vid}", status, style, profile, script, duration, archived_at))


def _post(env, vid, platform, account, raw=None, *, status="PUBLISHED", published_at=None,
          fetched_at="2026-02-01T00:00:00Z"):
    """One publication of `vid`, with one snapshot when `raw` is given."""
    pub = f"pub-{vid}-{account}"
    _sql(env,
         "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
         " postforme_post_id, status, post_url, published_at, created_at, updated_at)"
         " VALUES (?, ?, ?, ?, 'sp', ?, 'https://post', ?, 'now', 'now')",
         (pub, vid, platform, account, status, published_at or _ago(1)))
    if raw is not None:
        common = postforme.extract_metrics(platform, raw)
        _sql(env,
             "INSERT INTO video_metrics (publication_id, fetched_at, views, likes, comments,"
             " shares, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
             (pub, fetched_at, common["views"], common["likes"], common["comments"],
              common["shares"], json.dumps(raw)))
    return pub


def _timeline(env, vid, seconds):
    job = env.jobs / vid
    job.mkdir(parents=True, exist_ok=True)
    (job / "timeline.json").write_text(json.dumps({"audioDurationSeconds": seconds}))


def _row_of(data, pub):
    return next(p for p in data["publications"] if p["id"] == pub)


# ── GET /analytics and GET /videos/<id>/publications ─────────────────────────

def test_analytics_rows_carry_the_watch_figures_of_each_platform(client, env):
    _video(env, "vid_a", duration=94.0)
    yt = _post(env, "vid_a", "youtube", "spc_yt", YOUTUBE)
    ig = _post(env, "vid_a", "instagram", "spc_ig", INSTAGRAM)
    data = json.loads(client.get("/analytics").data)
    youtube, instagram = _row_of(data, yt), _row_of(data, ig)
    assert (youtube["avg_watch_secs"], youtube["watched_pct"], youtube["stayed_pct"]) == (31, 41.5, 60.0)
    assert (youtube["reach"], youtube["saves"]) == (None, None)
    assert (instagram["avg_watch_secs"], instagram["watched_pct"]) == (23.5, 25.0)
    assert (instagram["stayed_pct"], instagram["reach"], instagram["saves"]) == (None, 410, 12)


def test_the_figures_come_from_the_latest_snapshot(client, env):
    """Each snapshot is a cumulative reading, so the newest one is the answer
    and an older one is history."""
    _video(env, "vid_a")
    pub = _post(env, "vid_a", "youtube", "spc_yt", dict(YOUTUBE, averageViewDuration=10),
                fetched_at="2026-01-01T00:00:00Z")
    _sql(env, "INSERT INTO video_metrics (publication_id, fetched_at, views, raw_json)"
              " VALUES (?, '2026-03-01T00:00:00Z', 200, ?)", (pub, json.dumps(YOUTUBE)))
    data = json.loads(client.get("/analytics").data)
    assert _row_of(data, pub)["avg_watch_secs"] == 31


def test_snapshots_taken_before_this_feature_are_read_as_they_are(client, env):
    """Nothing was copied into columns, so there is nothing to backfill: a
    snapshot stored by any earlier version already holds the payload."""
    _video(env, "vid_a")
    pub = _post(env, "vid_a", "youtube", "spc_yt", YOUTUBE, fetched_at="2025-06-01T00:00:00Z")
    assert _row_of(json.loads(client.get("/analytics").data), pub)["watched_pct"] == 41.5


def test_an_instagram_post_of_a_video_with_no_stored_length_has_no_share(client, env):
    """Its files were deleted before the length was kept. The seconds are
    still reported; the share is blank, never a guess."""
    _video(env, "vid_old", duration=None, archived_at=_ago(30))
    pub = _post(env, "vid_old", "instagram", "spc_ig", INSTAGRAM)
    row = _row_of(json.loads(client.get("/analytics").data), pub)
    assert (row["avg_watch_secs"], row["watched_pct"]) == (23.5, None)


def test_a_post_with_no_snapshot_or_an_empty_payload_reports_nothing(client, env):
    """An account connected without the analytics permission answers with an
    empty metrics object. That is "not reported" in every column, not zeros."""
    _video(env, "vid_a")
    unpolled = _post(env, "vid_a", "youtube", "spc_yt")
    empty = _post(env, "vid_a", "instagram", "spc_ig", {})
    data = json.loads(client.get("/analytics").data)
    for pub in (unpolled, empty):
        row = _row_of(data, pub)
        assert {k: row[k] for k in postforme.RETENTION_KEYS} == NOTHING


def test_a_payload_that_does_not_parse_reports_nothing_and_breaks_nothing(client, env):
    _video(env, "vid_a")
    pub = _post(env, "vid_a", "youtube", "spc_yt", YOUTUBE)
    _sql(env, "UPDATE video_metrics SET raw_json = 'not json'")
    row = _row_of(json.loads(client.get("/analytics").data), pub)
    assert row["views"] == 200 and row["avg_watch_secs"] is None


def test_watch_figures_are_not_added_to_the_totals(client, env):
    """Views add up across platforms. A watched second on one platform and on
    another are different measurements, so nothing here is summed."""
    _video(env, "vid_a")
    _post(env, "vid_a", "youtube", "spc_yt", YOUTUBE)
    data = json.loads(client.get("/analytics").data)
    assert set(data["totals"]) == {"views", "likes", "comments", "shares", "videos", "publications"}
    assert set(data["by_platform"]["youtube"]) == {"views", "likes", "comments", "shares"}


def test_a_videos_publications_carry_counts_and_watch_figures(client, env):
    """The video window shows how each post is doing from this one request."""
    _video(env, "vid_a", duration=94.0)
    _post(env, "vid_a", "instagram", "spc_ig", INSTAGRAM)
    _post(env, "vid_a", "tiktok", "spc_tt", TIKTOK)
    _post(env, "vid_a", "youtube", "spc_yt")
    rows = {r["platform"]: r for r in json.loads(client.get("/videos/vid_a/publications").data)}
    assert rows["instagram"]["views"] == 500 and rows["instagram"]["watched_pct"] == 25.0
    assert rows["instagram"]["fetched_at"] == "2026-02-01T00:00:00Z"
    assert rows["tiktok"]["views"] == 800 and rows["tiktok"]["avg_watch_secs"] is None
    assert rows["youtube"]["views"] is None and rows["youtube"]["fetched_at"] is None


def test_a_failed_target_is_still_listed_for_its_video(client, env):
    """The video window is where a failed target is read, so the snapshot join
    must not drop it."""
    _video(env, "vid_a")
    _post(env, "vid_a", "youtube", "spc_yt", status="FAILED")
    rows = json.loads(client.get("/videos/vid_a/publications").data)
    assert [r["status"] for r in rows] == ["FAILED"]


# ── GET /analytics/watch-time ────────────────────────────────────────────────

def _dimension(data, dim):
    return {g["label"]: g for g in next(d for d in data["dimensions"] if d["id"] == dim)["groups"]}


def _watch(client, account="spc_yt"):
    return json.loads(client.get(f"/analytics/watch-time?social_account_id={account}").data)


def test_with_no_account_named_the_one_with_the_most_posts_is_answered(client, env):
    """Figures from two accounts are never put in one group, so there is no
    all-accounts view. The page opens on the account with the most to show and
    lists the rest to pick from."""
    for i in range(2):
        _video(env, f"vid_{i}")
        _post(env, f"vid_{i}", "instagram", "spc_ig", INSTAGRAM)
    _post(env, "vid_0", "youtube", "spc_yt", YOUTUBE)
    data = json.loads(client.get("/analytics/watch-time").data)
    assert (data["social_account_id"], data["platform"], data["videos"]) == ("spc_ig", "instagram", 2)
    assert data["accounts"] == [{"id": "spc_ig", "platform": "instagram", "videos": 2},
                                {"id": "spc_yt", "platform": "youtube", "videos": 1}]


def test_nothing_published_answers_with_no_accounts_and_empty_groups(client, env):
    data = json.loads(client.get("/analytics/watch-time").data)
    assert data["accounts"] == [] and data["social_account_id"] == "" and data["videos"] == 0
    assert all(d["groups"] == [] for d in data["dimensions"])


def test_only_the_asked_account_is_grouped(client, env):
    _video(env, "vid_a", duration=94.0)
    _post(env, "vid_a", "youtube", "spc_yt", YOUTUBE)
    _post(env, "vid_a", "instagram", "spc_ig", INSTAGRAM)
    data = _watch(client, "spc_ig")
    assert (data["platform"], data["videos"]) == ("instagram", 1)
    group = _dimension(data, "domain")["Domain proj-1"]
    assert group["avg_watch_secs"] == {"median": 23.5, "n": 1}
    assert group["stayed_pct"] == {"median": None, "n": 0}


def test_an_account_with_no_posts_answers_with_empty_groups(client, env):
    data = _watch(client, "spc_nobody")
    assert data["videos"] == 0 and data["platform"] == ""
    assert all(d["groups"] == [] for d in data["dimensions"])
    assert [d["id"] for d in data["dimensions"]] == [
        "visual_style", "script_profile", "domain", "script_length"]


def test_a_groups_figure_is_the_median_of_its_videos(client, env):
    """One video with many times the usual watch time must not set the figure
    for its whole group, which a mean would let it do."""
    for i, secs in enumerate((10, 20, 300)):
        _video(env, f"vid_{i}")
        _post(env, f"vid_{i}", "youtube", "spc_yt", dict(YOUTUBE, averageViewDuration=secs))
    group = _dimension(_watch(client), "domain")["Domain proj-1"]
    assert group["videos"] == 3
    assert group["avg_watch_secs"] == {"median": 20, "n": 3}


def test_an_even_group_takes_the_middle_of_the_two_central_videos(client, env):
    for i, secs in enumerate((10, 20, 30, 300)):
        _video(env, f"vid_{i}")
        _post(env, f"vid_{i}", "youtube", "spc_yt", dict(YOUTUBE, averageViewDuration=secs))
    assert _dimension(_watch(client), "domain")["Domain proj-1"]["avg_watch_secs"]["median"] == 25


def test_videos_counts_every_post_and_n_counts_the_ones_that_report(client, env):
    """An Instagram group where only some videos have a stored length: every
    post is in the group, and the share is the median of the ones that have it."""
    _video(env, "vid_new", duration=94.0)
    _video(env, "vid_old", duration=None)
    _video(env, "vid_unpolled", duration=94.0)
    _post(env, "vid_new", "instagram", "spc_ig", INSTAGRAM)
    _post(env, "vid_old", "instagram", "spc_ig", INSTAGRAM)
    _post(env, "vid_unpolled", "instagram", "spc_ig")
    group = _dimension(_watch(client, "spc_ig"), "domain")["Domain proj-1"]
    assert group["videos"] == 3
    assert group["avg_watch_secs"]["n"] == 2
    assert group["watched_pct"] == {"median": 25.0, "n": 1}


def test_grouping_by_visual_style_uses_the_packs_label(client, env):
    """A style id that is a pack shows its label. "auto" that never became a
    pack is the mixed scene system, and so is a blank from an old row."""
    for vid, style in (("vid_a", "system_flow"), ("vid_b", "auto"), ("vid_c", ""),
                       ("vid_d", "a_style_since_removed")):
        _video(env, vid, style=style)
        _post(env, vid, "youtube", "spc_yt", YOUTUBE)
    groups = _dimension(_watch(client), "visual_style")
    assert groups[pipeline.tvs.route_label("system_flow")]["videos"] == 1
    assert groups["Mixed scenes"]["videos"] == 2
    assert groups["a_style_since_removed"]["videos"] == 1


def test_a_video_auto_took_to_the_cartoon_3d_renderer_is_grouped_as_cartoon_3d(client, env):
    """Such a video keeps visual_style "auto" and records the renderer alone.
    It is a 3D video, and the tab exists to compare looks, so it must not sit
    with the mixed scenes."""
    _video(env, "vid_auto3d", style="auto")
    _video(env, "vid_forced3d", style="cartoon_3d")
    _video(env, "vid_mixed", style="auto")
    _sql(env, "UPDATE videos SET resolved_renderer = 'cartoon_3d' WHERE id = 'vid_auto3d'")
    _sql(env, "UPDATE videos SET resolved_renderer = 'dom' WHERE id = 'vid_mixed'")
    for vid in ("vid_auto3d", "vid_forced3d", "vid_mixed"):
        _post(env, vid, "youtube", "spc_yt", YOUTUBE)
    groups = _dimension(_watch(client), "visual_style")
    assert groups[pipeline.tvs.route_label("cartoon_3d")]["videos"] == 2
    assert groups["Mixed scenes"]["videos"] == 1


def test_grouping_by_script_profile_names_the_profile(client, env):
    _sql(env, "INSERT INTO script_profiles (id, name, status, created_at, updated_at)"
              " VALUES ('prof_1', 'Calm teacher', 'READY', 'now', 'now')")
    for vid, profile in (("vid_a", "prof_1"), ("vid_b", ""), ("vid_c", "prof_deleted")):
        _video(env, vid, profile=profile)
        _post(env, vid, "youtube", "spc_yt", YOUTUBE)
    groups = _dimension(_watch(client), "script_profile")
    assert set(groups) == {"Calm teacher", "No profile", "prof_deleted"}


def test_grouping_by_domain(client, env):
    for vid, project in (("vid_a", "p1"), ("vid_b", "p1"), ("vid_c", "p2")):
        _video(env, vid, project=project)
        _post(env, vid, "youtube", "spc_yt", YOUTUBE)
    groups = _dimension(_watch(client), "domain")
    assert {label: g["videos"] for label, g in groups.items()} == {"Domain p1": 2, "Domain p2": 1}


def test_script_length_groups_are_word_bands_in_order(client, env):
    """The bands come back shortest first whatever their sizes, since the
    question asked of them is whether length changes the figure."""
    lengths = {"vid_a": 320, "vid_b": 320, "vid_c": 120, "vid_d": 150, "vid_e": 249, "vid_f": 0}
    for vid, words in lengths.items():
        _video(env, vid, script=" ".join(["word"] * words))
        _post(env, vid, "youtube", "spc_yt", YOUTUBE)
    dim = next(d for d in _watch(client)["dimensions"] if d["id"] == "script_length")
    assert [(g["label"], g["videos"]) for g in dim["groups"]] == [
        ("Under 150 words", 1), ("150 to 199 words", 1), ("200 to 249 words", 1),
        ("300 words or more", 2), ("No script", 1)]


def test_script_words_leave_markup_out_and_keep_the_wrapped_word():
    script = ('Meet <respell as="Daymon">Daemon</respell>. <break time="0.5s" /> '
              'He [pause] says <ipa ph="təˈmeɪtoʊ">tomato</ipa>.')
    assert pipeline._script_words(script) == 5
    assert pipeline._script_words("") == 0 and pipeline._script_words(None) == 0


def test_a_stray_angle_bracket_in_the_words_does_not_swallow_the_script():
    """ "a < b" is not a tag. Paired with the ">" of a later tag it would take
    every word between them out of the count and put a long script in the
    shortest band."""
    script = "If a < b then we win. " + "word " * 200 + '<break time="1s"/> done [pause] now'
    assert pipeline._script_words(script) == 208
    assert pipeline._script_length_band(script)[1] == "200 to 249 words"


def test_larger_groups_come_first_where_there_is_no_natural_order(client, env):
    for i in range(3):
        _video(env, f"vid_big{i}", project="big")
        _post(env, f"vid_big{i}", "youtube", "spc_yt", YOUTUBE)
    _video(env, "vid_small", project="small")
    _post(env, "vid_small", "youtube", "spc_yt", YOUTUBE)
    dim = next(d for d in _watch(client)["dimensions"] if d["id"] == "domain")
    assert [g["label"] for g in dim["groups"]] == ["Domain big", "Domain small"]


def test_the_small_group_threshold_travels_with_the_answer(client, env):
    """The page marks groups under it. One constant, so the page and any other
    reader agree on what is too small to read."""
    assert _watch(client)["min_group"] == pipeline.WATCH_MIN_GROUP == 20


def test_a_failed_target_is_not_grouped(client, env):
    _video(env, "vid_a")
    _post(env, "vid_a", "youtube", "spc_yt", YOUTUBE, status="FAILED")
    assert _watch(client)["videos"] == 0


# ── the worker stores a published video's length ─────────────────────────────

def test_the_length_of_a_published_video_is_stored_from_its_timeline(env):
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig")
    _timeline(env, "vid_a", 94.25)
    assert pipeline.fill_video_durations(env.db) == 1
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.25
    assert pipeline.fill_video_durations(env.db) == 0


def test_a_video_with_no_timeline_stays_unknown_and_is_asked_again(env):
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig")
    assert pipeline.fill_video_durations(env.db) == 0
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") is None
    _timeline(env, "vid_a", 60)
    assert pipeline.fill_video_durations(env.db) == 1


def test_an_unpublished_or_archived_video_is_left_alone(env):
    """A video nobody published has no analytics to divide. An archived one
    has no files, and asking for them every hour would fail every hour."""
    _video(env, "vid_draft", status="VIDEO_READY")
    _timeline(env, "vid_draft", 60)
    _video(env, "vid_gone", archived_at=_ago(3))
    _post(env, "vid_gone", "instagram", "spc_ig")
    _timeline(env, "vid_gone", 60)
    assert pipeline.fill_video_durations(env.db) == 0


def test_a_stored_length_is_never_overwritten(env):
    _video(env, "vid_a", duration=94.0)
    _post(env, "vid_a", "instagram", "spc_ig")
    _timeline(env, "vid_a", 12)
    pipeline.fill_video_durations(env.db)
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.0


def test_one_unreadable_timeline_does_not_stop_the_others(env):
    """A timeline whose fps is not a number raises inside the reader. That
    video stays unknown; the ones after it still get their length."""
    for vid in ("vid_a", "vid_b"):
        _video(env, vid)
        _post(env, vid, "instagram", "spc_ig")
    job = env.jobs / "vid_a"
    job.mkdir()
    (job / "timeline.json").write_text(json.dumps({"totalFrames": 2700, "fps": "thirty"}))
    _timeline(env, "vid_b", 60)
    assert pipeline.fill_video_durations(env.db) == 1
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") is None
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_b'") == 60


@pytest.mark.parametrize("timeline", [
    '{"audioDurationSeconds": 1e999}', '{"totalFrames": 2700, "fps": 1e-320}',
    '{"audioDurationSeconds": 90000}'])
def test_a_length_that_is_not_a_length_is_never_stored(env, timeline):
    """1e999 parses to infinity. Stored, it would come back with every video
    as a value no browser can read, on every page that lists videos, until
    someone fixed the row by hand."""
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig")
    job = env.jobs / "vid_a"
    job.mkdir()
    (job / "timeline.json").write_text(timeline)
    assert pipeline.fill_video_durations(env.db) == 0
    assert pipeline.archive_video(env.db, "vid_a", {"PUBLISHED"}, "human", "x")["result"] == "archived"
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") is None


def test_refreshing_metrics_stores_lengths_like_the_hourly_pass(client, env, monkeypatch):
    """A post first read by the Refresh button would otherwise show
    Instagram's seconds with no share until the worker's next pass."""
    _sql(env, "INSERT OR REPLACE INTO settings VALUES ('publishing_enabled', 'true')")
    _sql(env, "INSERT OR REPLACE INTO settings VALUES ('postforme_api_key', 'pfm-key')")
    monkeypatch.setattr(pipeline.metrics_poll, "poll",
                        lambda *_a, **_k: {"accounts": 1, "snapshots": 1, "errors": 0})
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig", INSTAGRAM)
    _timeline(env, "vid_a", 94.0)
    assert client.post("/analytics/refresh").status_code == 200
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.0

    def boom(_db):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(pipeline, "fill_video_durations", boom)
    assert json.loads(client.post("/analytics/refresh").data)["snapshots"] == 1


def test_the_retention_sweep_stores_the_length_as_it_deletes_the_files(env, monkeypatch):
    """The trap this guards: archiving deletes timeline.json, the only other
    record of the length, and the analytics go on for as long as the post does."""
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig", published_at=_ago(30))
    _timeline(env, "vid_a", 94.0)
    worker._sweep_published(7)
    assert _one(env, "SELECT archived_at FROM videos WHERE id = 'vid_a'") is not None
    assert not (env.jobs / "vid_a").exists()
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.0


def test_deleting_a_video_from_the_dashboard_stores_its_length_too(client, env):
    """A person can delete a published video minutes after it went out, before
    any hourly pass, and with publishing switched off. The length is stored by
    the archive itself, so no route to deleting the files skips it."""
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig", INSTAGRAM)
    _timeline(env, "vid_a", 94.0)
    assert client.delete("/videos/vid_a").status_code == 200
    assert not (env.jobs / "vid_a").exists()
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.0
    row = json.loads(client.get("/analytics").data)["publications"][0]
    assert row["watched_pct"] == 25.0


def test_archiving_keeps_a_length_already_stored_and_survives_a_bad_timeline(env):
    _video(env, "vid_a", duration=94.0)
    _timeline(env, "vid_a", 12)
    _video(env, "vid_b")
    job = env.jobs / "vid_b"
    job.mkdir()
    (job / "timeline.json").write_text(json.dumps({"totalFrames": 2700, "fps": [30]}))
    for vid in ("vid_a", "vid_b"):
        assert pipeline.archive_video(env.db, vid, {"PUBLISHED"}, "human", "x")["result"] == "archived"
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.0
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_b'") is None


def test_the_hourly_metrics_pass_stores_lengths_too(env, monkeypatch):
    _video(env, "vid_a")
    _post(env, "vid_a", "instagram", "spc_ig")
    _timeline(env, "vid_a", 94.0)
    monkeypatch.setattr(worker, "_publishing_key", lambda: "key")
    monkeypatch.setattr(worker, "_metrics_due", lambda: True)
    monkeypatch.setattr(worker.metrics, "poll",
                        lambda *_a, **_k: {"accounts": 0, "snapshots": 0, "errors": 0})
    worker._poll_video_metrics()
    assert _one(env, "SELECT duration_secs FROM videos WHERE id = 'vid_a'") == 94.0


def test_a_failure_storing_lengths_does_not_stop_the_metrics_pass(env, monkeypatch):
    """The snapshots are a time series: a pass that is skipped is a reading
    lost. Storing lengths rides on that pass and must never cost it."""
    def boom(_db):
        raise sqlite3.OperationalError("database is locked")
    polled = []
    monkeypatch.setattr(pipeline, "fill_video_durations", boom)
    monkeypatch.setattr(worker, "_publishing_key", lambda: "key")
    monkeypatch.setattr(worker, "_metrics_due", lambda: True)
    monkeypatch.setattr(worker.metrics, "poll", lambda *_a, **_k: polled.append(1) or
                        {"accounts": 0, "snapshots": 0, "errors": 0})
    worker._poll_video_metrics()
    assert polled == [1]
