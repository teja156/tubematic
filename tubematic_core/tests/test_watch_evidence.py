"""Learned routing's rule (TMDEV-217): what a domain's own watch figures say
about its formulas and openings, and the points formula routing adds for them.

The agent adds the points only to formulas that already fit the topic; that
judgement is the skill's and cannot run here. What CI holds is the rule
itself: which posts count, when a group is large enough to read, how a group
is compared with its account, how accounts are combined, when a pick is a
trial pick, and that an install with no evidence gets nothing at all.
"""
import json
import pathlib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import formulas as tf  # noqa: E402
from tubematic_core import watch  # noqa: E402

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
FRESH = (NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
A, B, C = list(tf.FORMULAS)[:3]
MIN = watch.WATCH_MIN_GROUP


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


@pytest.fixture
def con(tmp_path):
    path = tmp_path / "data" / "tubematic.db"
    path.parent.mkdir(parents=True)
    tdb.migrate(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    for pid in ("dom", "other"):
        c.execute("INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)", (pid, pid, OLD))
    yield c
    c.close()


_seq = {"n": 0}


def _post(con, formula, share, *, account="yt1", platform="youtube", hook="paradox",
          published=OLD, project="dom", video=None, raw=None):
    """One published video with one snapshot reporting `share` percent watched."""
    _seq["n"] += 1
    n = _seq["n"]
    video = video or f"v{n}"
    if not con.execute("SELECT 1 FROM videos WHERE id = ?", (video,)).fetchone():
        con.execute(
            "INSERT INTO videos (id, topic, status, project_id, formula_id, hook_type, "
            "duration_secs, created_at, updated_at) VALUES (?, 't', 'PUBLISHED', ?, ?, ?, 60, ?, ?)",
            (video, project, formula, hook, OLD, OLD))
    pub = f"p{n}"
    con.execute(
        "INSERT INTO video_publications (id, video_id, platform, social_account_id, status, "
        "published_at, created_at, updated_at) VALUES (?, ?, ?, ?, 'PUBLISHED', ?, ?, ?)",
        (pub, video, platform, account, published, OLD, OLD))
    if raw is None:
        raw = {"views": 100, "averageViewPercentage": share} if platform == "youtube" else {
            "views": 100, "ig_reels_avg_watch_time": share * 600}  # 60 s video: ms
    con.execute("INSERT INTO video_metrics (publication_id, fetched_at, raw_json) VALUES (?, ?, ?)",
                (pub, OLD, json.dumps(raw)))
    return video


def _many(con, formula, share, count, **kw):
    return [_post(con, formula, share, **kw) for _ in range(count)]


def _ev(con, project="dom"):
    return watch.domain_evidence(con, project, NOW)


# ── which posts count ────────────────────────────────────────────────────────

def test_no_published_videos_is_no_evidence(con):
    ev = _ev(con)
    assert ev["active"] is False and ev["formulas"] == {} and ev["openings"] == []


def test_a_group_under_the_minimum_does_not_count(con):
    _many(con, A, 60, MIN - 1)
    _many(con, B, 40, MIN)
    ev = _ev(con)
    assert A not in ev["formulas"]
    assert ev["formulas"][B]["standing"] in watch.STANDINGS
    assert ev["active"] is True
    on = watch.routing_learning(con, "dom", "new", True, NOW)
    assert on["formulas"][A]["standing"] == watch.THIN


def test_an_account_with_too_few_posts_in_the_domain_gives_no_evidence(con):
    _many(con, A, 60, MIN - 5)
    _many(con, B, 30, 4)
    ev = _ev(con)
    assert ev["active"] is False and ev["accounts"] == 0


def test_posts_younger_than_the_minimum_age_are_left_out(con):
    _many(con, A, 70, MIN, published=FRESH)
    _many(con, B, 40, MIN)
    ev = _ev(con)
    assert A not in ev["formulas"]
    on = watch.routing_learning(con, "dom", "new", True, NOW)
    assert on["formulas"][A] == {"points": 0, "standing": watch.THIN, "videos": 0, "accounts": 0}


def test_a_post_without_a_published_time_is_left_out(con):
    _many(con, A, 70, MIN, published="")
    assert _ev(con)["active"] is False


def test_a_platform_that_reports_no_share_adds_nothing(con):
    # TikTok's consumer connection reports counts only.
    _many(con, A, 0, MIN * 2, platform="tiktok", account="tt1",
          raw={"view_count": 100})
    assert _ev(con)["active"] is False


def test_other_domains_posts_do_not_count(con):
    _many(con, A, 70, MIN, project="other")
    assert _ev(con)["active"] is False
    assert _ev(con, "other")["active"] is True


def test_the_latest_snapshot_is_the_one_read(con):
    vids = _many(con, A, 10, MIN)
    _many(con, B, 50, MIN)
    for vid in vids:
        pub = con.execute("SELECT id FROM video_publications WHERE video_id = ?", (vid,)).fetchone()[0]
        con.execute("INSERT INTO video_metrics (publication_id, fetched_at, raw_json) VALUES (?, ?, ?)",
                    (pub, NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     json.dumps({"views": 100, "averageViewPercentage": 90})))
    assert _ev(con)["formulas"][A]["standing"] == "better"


# ── standing against the account's own middle value ─────────────────────────

def test_a_group_well_above_the_accounts_middle_is_better_and_well_below_is_worse(con):
    _many(con, A, 60, MIN)
    _many(con, B, 40, MIN)
    _many(con, C, 50, MIN)
    ev = _ev(con)
    assert ev["formulas"][A]["standing"] == "better"
    assert ev["formulas"][B]["standing"] == "worse"
    assert ev["formulas"][C]["standing"] == "even"
    assert ev["formulas"][A]["videos"] == MIN


def test_inside_the_margin_is_even(con):
    _many(con, A, 52, MIN)
    _many(con, B, 50, MIN)
    ev = _ev(con)
    assert ev["formulas"][A]["standing"] == ev["formulas"][B]["standing"] == "even"


def test_one_outlier_cannot_carry_a_group(con):
    # The middle value of A is 50 like B's; one video at 900% (a looped Short)
    # would lift a mean far above the margin.
    _many(con, A, 50, MIN - 1)
    _post(con, A, 900)
    _many(con, B, 50, MIN)
    assert _ev(con)["formulas"][A]["standing"] == "even"


def test_a_share_derived_from_seconds_counts_on_instagram(con):
    _many(con, A, 60, MIN, platform="instagram", account="ig1")
    _many(con, B, 40, MIN, platform="instagram", account="ig1")
    assert _ev(con)["formulas"][A]["standing"] == "better"


# ── several accounts ────────────────────────────────────────────────────────

def test_better_on_one_account_and_even_on_another_is_better(con):
    _many(con, A, 60, MIN, account="yt1")
    _many(con, B, 40, MIN, account="yt1")
    _many(con, A, 50, MIN, account="yt2")
    _many(con, B, 50, MIN, account="yt2")
    ev = _ev(con)
    assert ev["formulas"][A]["standing"] == "better"
    assert ev["accounts"] == 2
    assert ev["formulas"][A]["videos"] == 2 * MIN
    assert ev["formulas"][A]["accounts"] == 2


def test_the_record_counts_the_accounts_behind_the_formula_not_the_domains(con):
    _many(con, A, 60, MIN, account="yt1")
    _many(con, B, 40, MIN, account="yt1")
    _many(con, B, 50, MIN, account="yt2")   # A is not on yt2 at all
    on = watch.routing_learning(con, "dom", "new", True, NOW)
    assert on["accounts"] == 2
    assert json.loads(watch.evidence_record(on, A))["accounts"] == 1
    assert watch.candidate_learning(on, A) == {"points": 2, "standing": "better", "videos": MIN}


def test_accounts_that_disagree_are_mixed_and_add_no_points(con):
    _many(con, A, 60, MIN, account="yt1")
    _many(con, B, 40, MIN, account="yt1")
    _many(con, A, 40, MIN, account="yt2")
    _many(con, B, 60, MIN, account="yt2")
    ev = _ev(con)
    assert ev["formulas"][A]["standing"] == "mixed"
    assert watch.points("mixed", "learned") == 0


def test_one_video_posted_to_two_accounts_counts_once_in_videos(con):
    for _ in range(MIN):
        vid = _post(con, A, 60, account="yt1")
        _post(con, A, 60, account="yt2", video=vid)
    for _ in range(MIN):
        vid = _post(con, B, 40, account="yt1")
        _post(con, B, 40, account="yt2", video=vid)
    assert _ev(con)["formulas"][A]["videos"] == MIN


# ── openings ────────────────────────────────────────────────────────────────

def test_openings_are_ranked_better_first_and_only_counted_types_are_listed(con):
    _many(con, A, 60, MIN, hook="paradox")
    _many(con, A, 40, MIN, hook="problem")
    _many(con, A, 50, MIN - 1, hook="question")
    ops = _ev(con)["openings"]
    assert [o["type"] for o in ops] == ["paradox", "problem"]
    assert ops[0]["standing"] == "better" and ops[1]["standing"] == "worse"
    assert ops[0]["label"] == tf.HOOK_TYPES["paradox"]
    assert set(ops[0]) == {"type", "label", "standing", "videos"}


def test_a_script_with_no_recorded_formula_counts_toward_the_baseline_only(con):
    _many(con, "", 50, MIN)
    _many(con, A, 70, MIN)
    ev = _ev(con)
    assert "" not in ev["formulas"]
    assert ev["formulas"][A]["standing"] == "better"


# ── points and the trial pick ───────────────────────────────────────────────

def test_points_per_mode():
    assert watch.points("better", "learned") == 2
    assert watch.points("worse", "learned") == -1
    assert watch.points("even", "learned") == 0
    assert watch.points(watch.THIN, "learned") == 0
    assert watch.points(watch.THIN, "explore") == 2
    assert watch.points("better", "explore") == 0
    assert watch.points("worse", "explore") == 0


def _picked(con, n, project="dom"):
    for i in range(n):
        con.execute(
            "INSERT INTO videos (id, topic, status, project_id, formula_evidence, created_at, "
            "updated_at) VALUES (?, 't', 'SCRIPT_READY', ?, '{\"mode\": \"learned\"}', ?, ?)",
            (f"picked{project}{i}", project, OLD, OLD))


def test_every_fourth_pick_with_evidence_is_a_trial_pick(con):
    modes = []
    for n in range(9):
        modes.append(watch.learning_mode(con, "dom", "new"))
        con.execute(
            "INSERT INTO videos (id, topic, status, project_id, formula_evidence, created_at, "
            "updated_at) VALUES (?, 't', 'SCRIPT_READY', 'dom', '{}', ?, ?)", (f"pk{n}", OLD, OLD))
    assert modes == ["learned"] * 3 + ["explore"] + ["learned"] * 3 + ["explore"] + ["learned"]


def test_picks_made_without_evidence_and_the_video_itself_are_not_counted(con):
    con.execute("INSERT INTO videos (id, topic, status, project_id, created_at, updated_at) "
                "VALUES ('plain', 't', 'SCRIPT_READY', 'dom', ?, ?)", (OLD, OLD))
    _picked(con, 3, project="other")
    _picked(con, 3)
    assert watch.learning_mode(con, "dom", "new") == "explore"
    assert watch.learning_mode(con, "dom", "pickeddom0") == "learned"


# ── what formula routing receives ───────────────────────────────────────────

def test_disabled_or_no_evidence_gives_no_points_to_any_formula(con):
    _many(con, A, 60, MIN)
    _many(con, B, 40, MIN)
    off = watch.routing_learning(con, "dom", "new", False, NOW)
    assert off["active"] is False and off["formulas"] == {} and off["openings"] == []
    assert off["accounts"] == 0 and off["mode"] == ""
    assert watch.candidate_learning(off, A) == {"points": 0, "standing": "", "videos": 0}
    assert watch.evidence_record(off, A) == ""
    empty = watch.routing_learning(con, "other", "new", True, NOW)
    assert empty["active"] is False and watch.evidence_record(empty, A) == ""


def test_active_learning_gives_every_formula_its_points(con):
    _many(con, A, 60, MIN)
    _many(con, B, 40, MIN)
    on = watch.routing_learning(con, "dom", "new", True, NOW)
    assert on["active"] is True and on["mode"] == "learned"
    assert set(on["formulas"]) == set(tf.FORMULAS)
    assert on["formulas"][A] == {"points": 2, "standing": "better", "videos": MIN, "accounts": 1}
    assert on["formulas"][B]["points"] == -1
    assert on["formulas"][C] == {"points": 0, "standing": watch.THIN, "videos": 0, "accounts": 0}
    record = json.loads(watch.evidence_record(on, A))
    assert record == {"formula": A, "mode": "learned", "measure": "watched_pct",
                      "standing": "better", "points": 2, "videos": MIN, "accounts": 1,
                      "min_group": MIN}


def test_a_trial_pick_moves_the_points_to_thin_formulas(con):
    _many(con, A, 60, MIN)
    _many(con, B, 40, MIN)
    _picked(con, 3)
    on = watch.routing_learning(con, "dom", "new", True, NOW)
    assert on["mode"] == "explore"
    assert on["formulas"][A]["points"] == 0 and on["formulas"][B]["points"] == 0
    assert on["formulas"][C]["points"] == 2


# ── round-2 rules ───────────────────────────────────────────────────────────

def test_a_formula_this_version_dropped_does_not_switch_learning_on(con):
    _many(con, "a-formula-a-later-version-dropped", 60, MIN)
    _many(con, A, 40, MIN - 1)
    assert _ev(con)["active"] is False
    assert watch.routing_learning(con, "dom", "new", True, NOW)["active"] is False


def test_openings_reach_the_writer_before_any_formula_counts(con):
    # Opening types are few, so a type gathers enough videos long before a
    # formula does. No formula counts here, so no formula gets points.
    for i, formula in enumerate(list(tf.FORMULAS)[:8]):
        _many(con, formula, 60, 4, hook="question")
        _many(con, formula, 40, 4, hook="problem")
    on = watch.routing_learning(con, "dom", "new", True, NOW)
    assert on["active"] is False and on["formulas"] == {} and on["stamp"] == ""
    assert [o["type"] for o in on["openings"]] == ["question", "problem"]
    assert watch.evidence_record(on, A) == ""


def test_a_trial_pick_sets_the_opening_figures_aside_too(con):
    _many(con, A, 60, MIN, hook="question")
    _many(con, B, 40, MIN, hook="problem")
    assert watch.routing_learning(con, "dom", "new", True, NOW)["openings"]
    _picked(con, 3)
    trial = watch.routing_learning(con, "dom", "new", True, NOW)
    assert trial["mode"] == "explore" and trial["openings"] == []


def test_the_stamp_changes_with_the_mode_and_with_any_formulas_points(con):
    _many(con, A, 60, MIN)
    _many(con, B, 40, MIN)
    first = watch.routing_learning(con, "dom", "new", True, NOW)["stamp"]
    assert first.startswith("learned-")
    assert watch.routing_learning(con, "dom", "new", True, NOW)["stamp"] == first
    _many(con, C, 70, MIN)   # C now counts: its points change, and so do the others' standings
    second = watch.routing_learning(con, "dom", "new", True, NOW)["stamp"]
    assert second != first and second.startswith("learned-")
    _picked(con, 3)
    assert watch.routing_learning(con, "dom", "new", True, NOW)["stamp"].startswith("explore-")


def test_openings_follow_the_mode_stored_with_the_pick(con):
    _many(con, A, 60, MIN, hook="question")
    _many(con, B, 40, MIN, hook="problem")
    # The domain's count says learned; a pick made as a trial keeps its openings aside.
    held = watch.routing_learning(con, "dom", "new", True, NOW, pick_mode="explore")
    assert held["mode"] == "learned" and held["openings"] == []
    _picked(con, 3)
    # The count now says trial; a pick made as learned keeps its openings.
    kept = watch.routing_learning(con, "dom", "new", True, NOW, pick_mode="learned")
    assert kept["mode"] == "explore" and kept["openings"]


def test_the_mode_of_a_stored_record():
    assert watch.record_mode(json.dumps({"mode": "explore"})) == "explore"
    assert watch.record_mode(json.dumps({"mode": "learned"})) == "learned"
    for raw in ("", None, "{broken", "[]", json.dumps({"mode": "other"})):
        assert watch.record_mode(raw) == ""
