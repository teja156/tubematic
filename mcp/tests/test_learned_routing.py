"""Learned routing through the MCP surface (TMDEV-217): get_video's
formula_routing.learned and each candidate's learned points, and the record
choose_script_formula stores for the dashboard.

The rule itself is tested in tubematic_core/tests/test_watch_evidence.py. Here:
the points reach the router only where the setting and publishing are both on
and the domain has evidence; the record is computed by the server, never taken
from the agent; every fourth pick in a domain is a trial pick; a return to the
topic clears the record with the pick.

Run from repo root: pytest mcp/tests/
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import server
from tubematic_core import formulas as tf
from tubematic_core import watch

REASON = "A request moves through fixed stages, each handing on to the next."
# Every pick in these tests is in one domain, so a formula repeats.
REPEAT = "No other formula fits this topic."
GOOD, POOR, OTHER = "follow-the-flow", "paradox-mechanism-reframe", "scene-story"
OLD = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
MIN = watch.WATCH_MIN_GROUP


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _setting(key, value):
    with server._conn() as con:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    with server._conn() as con:
        for pid in ("dom", "empty"):
            con.execute("INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                        (pid, pid, _now()))
    _setting("publishing_enabled", "true")
    return tmp_path / "test.db"


def _published(formula, share, count, hook="paradox", project="dom"):
    """`count` published videos in `project`, each with one month-old snapshot."""
    with server._conn() as con:
        start = con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        for i in range(start, start + count):
            vid = f"pub{i}"
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, formula_id, hook_type, "
                "duration_secs, created_at, updated_at) VALUES (?, ?, 't', 'PUBLISHED', ?, ?, 60, "
                "?, ?)", (vid, project, formula, hook, OLD, OLD))
            con.execute(
                "INSERT INTO video_publications (id, video_id, platform, social_account_id, "
                "status, published_at, created_at, updated_at) VALUES (?, ?, 'youtube', 'yt1', "
                "'PUBLISHED', ?, ?, ?)", (f"p{vid}", vid, OLD, OLD, OLD))
            con.execute(
                "INSERT INTO video_metrics (publication_id, fetched_at, raw_json) VALUES (?, ?, ?)",
                (f"p{vid}", OLD, json.dumps({"views": 100, "averageViewPercentage": share})))


@pytest.fixture
def evidence(db):
    _published(GOOD, 60, MIN, hook="paradox")
    _published(POOR, 40, MIN, hook="problem")
    return db


def _video(vid="vid_1", status="TOPIC_APPROVED", project="dom", choice=""):
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, visual_style, style_pick, "
            "formula_choice, created_at, updated_at) VALUES (?, ?, 'a topic', ?, 'system_flow', "
            "'', ?, ?, ?)", (vid, project, status, choice, _now(), _now()))
    return vid


def _evidence(vid="vid_1"):
    with server._conn() as con:
        return con.execute("SELECT formula_evidence FROM videos WHERE id = ?",
                           (vid,)).fetchone()[0]


def _candidates(routing):
    return {c["id"]: c for c in routing["candidates"]}


# ── what the router reads ────────────────────────────────────────────────────

def test_candidates_carry_the_domains_points_and_the_writer_gets_the_openings(evidence):
    _video()
    routing = server.get_video("vid_1")["formula_routing"]
    learned = routing["learned"]
    assert learned["active"] is True and learned["mode"] == "learned"
    assert learned["measure"] == "watched_pct" and learned["min_group"] == MIN
    assert "formulas" not in learned
    assert [o["type"] for o in learned["openings"]] == ["paradox", "problem"]
    cands = _candidates(routing)
    assert cands[GOOD]["learned"] == {"points": 2, "standing": "better", "videos": MIN}
    assert cands[POOR]["learned"]["points"] == -1
    assert cands[OTHER]["learned"] == {"points": 0, "standing": watch.THIN, "videos": 0}
    assert set(cands) == set(tf.FORMULAS)


@pytest.mark.parametrize("key, value", [("learned_routing", "false"),
                                        ("publishing_enabled", "false")])
def test_learning_off_or_publishing_off_gives_no_points(evidence, key, value):
    _setting(key, value)
    _video()
    routing = server.get_video("vid_1")["formula_routing"]
    assert routing["learned"]["active"] is False
    assert all(c["learned"]["points"] == 0 for c in routing["candidates"])
    out = server.choose_script_formula("vid_1", GOOD, REASON)
    assert out["learned"] == {} and _evidence() == ""


def test_a_domain_with_no_evidence_routes_as_before(evidence):
    _video(project="empty")
    routing = server.get_video("vid_1")["formula_routing"]
    assert routing["learned"]["active"] is False and routing["learned"]["openings"] == []
    server.choose_script_formula("vid_1", GOOD, REASON)
    assert _evidence() == ""


def test_the_figures_are_not_read_where_nothing_is_picked_or_written(evidence):
    _video(status="SCRIPT_READY")
    assert server.get_video("vid_1")["formula_routing"]["learned"] == {"active": False}


# ── what the pick records ────────────────────────────────────────────────────

def test_the_pick_records_what_the_figures_said_about_it(evidence):
    _video()
    out = server.choose_script_formula("vid_1", GOOD, REASON, runner_up=OTHER)
    record = json.loads(_evidence())
    assert record == {"formula": GOOD, "mode": "learned", "measure": "watched_pct",
                      "standing": "better", "points": 2, "videos": MIN, "accounts": 1}
    assert out["learned"] == record


def test_a_pick_the_figures_do_not_favour_still_records_them(evidence):
    _video()
    server.choose_script_formula("vid_1", OTHER, REASON)
    assert json.loads(_evidence())["standing"] == watch.THIN


def test_with_a_persons_choice_the_record_is_about_autos_formula(evidence):
    _video(choice=OTHER)
    out = server.choose_script_formula("vid_1", GOOD, REASON)
    assert out["formula_pick"] == OTHER
    assert json.loads(_evidence())["formula"] == GOOD


def test_every_fourth_pick_in_the_domain_is_a_trial_pick(evidence):
    modes = []
    for n in range(5):
        vid = _video(f"v{n}")
        modes.append(server.get_video(vid)["formula_routing"]["learned"]["mode"])
        out = server.choose_script_formula(vid, OTHER, REASON, repeat_reason=REPEAT)
        assert "error" not in out
        assert json.loads(_evidence(vid))["mode"] == modes[-1]
    assert modes == ["learned", "learned", "learned", "explore", "learned"]
    vid = _video("v3b")
    assert server.get_video(vid)["formula_routing"]["learned"]["mode"] == "learned"


def test_a_trial_pick_gives_the_points_to_formulas_with_too_few_videos(evidence):
    for n in range(3):
        assert "error" not in server.choose_script_formula(_video(f"v{n}"), OTHER, REASON,
                                                           repeat_reason=REPEAT)
    _video()
    cands = _candidates(server.get_video("vid_1")["formula_routing"])
    assert cands[GOOD]["learned"]["points"] == 0
    assert cands[OTHER]["learned"]["points"] == 2


def test_a_return_to_the_topic_clears_the_record_with_the_pick(evidence):
    _video()
    server.choose_script_formula("vid_1", GOOD, REASON)
    assert _evidence() != ""
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'SCRIPT_READY' WHERE id = 'vid_1'")
    out = server.set_video_status("vid_1", "TOPIC_PROPOSED")
    assert "error" not in out
    assert _evidence() == ""
