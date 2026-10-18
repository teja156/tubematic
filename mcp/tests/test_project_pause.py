"""Domain pause — seeds only, and enforced at filing (TMDEV-115).

Pausing used to write one word to projects.status that no code ever read
again; only prose asked the agent to honour it. Two invariants now live in
code instead:

  * create_video refuses a paused project_id for every strategy but "manual".
    An explicit human request outranks a pause; everything the agent sources
    on its own does not.
  * Only a curriculum seed can be paused. For any other domain the pause could
    never stop the subject being researched — the topic just went into another
    domain — so a paused non-seed is refused, and clearing the seed flag on a
    paused domain reactivates it rather than leaving a paused row with no
    control to change it.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    return tmp_path / "test.db"


def _project(pid, *, seed, status, name="Database internals"):
    """Insert directly, bypassing the rule — the only way to build the stray
    paused non-seed row an older install could still hold."""
    with server._conn() as con:
        con.execute(
            "INSERT INTO projects (id, name, is_curriculum_seed, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, name, int(seed), status, _now()),
        )
    return pid


def _status(pid):
    with server._conn() as con:
        return con.execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()[0]


def _video_count():
    with server._conn() as con:
        return con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]


# ── create_video refuses a paused domain ────────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining"])
def test_a_paused_domain_refuses_every_sourced_strategy(db, strategy):
    _project("db-internals", seed=True, status="paused")
    result = server.create_video("db-internals", "B-trees on disk", strategy, 7)
    assert "error" in result
    assert _video_count() == 0


def test_the_refusal_names_the_domain_and_says_it_is_paused(db):
    _project("db-internals", seed=True, status="paused", name="Database internals")
    err = server.create_video("db-internals", "B-trees on disk", "trending", 7)["error"]
    assert "Database internals" in err
    assert "db-internals" in err
    assert "paused" in err


def test_the_refusal_is_logged_as_a_warning_not_as_a_success(db, through_mcp):
    """A refusal is returned, not raised, so it used to log like a success.
    It is a WARNING — the agent was told no, nothing is broken."""
    _project("db-internals", seed=True, status="paused")
    out, (rec,) = through_mcp("create_video", project_id="db-internals", topic="B-trees on disk",
                              strategy="trending", producibility_score=7)
    assert "paused" in out["error"]
    assert (rec.levelname, rec.outcome) == ("WARNING", "error")
    assert "paused" in rec.getMessage()
    assert not hasattr(rec, "provider_service")


def test_the_refusal_tells_the_agent_to_skip_not_refile(db):
    """Refused on the direct path, an agent looks for a legal one; the error is
    where it reads what to do next."""
    _project("db-internals", seed=True, status="paused")
    err = server.create_video("db-internals", "B-trees on disk", "trending", 7)["error"]
    assert "skip" in err.lower()


def test_the_refusal_does_not_advertise_the_manual_exemption(db):
    """strategy is supplied by the agent. An error saying "manual gets through"
    is an instruction to relabel the candidate and walk past the pause."""
    _project("db-internals", seed=True, status="paused")
    err = server.create_video("db-internals", "B-trees on disk", "trending", 7)["error"]
    assert "manual" not in err.lower()


def test_a_manual_submission_is_accepted_into_a_paused_domain(db):
    _project("db-internals", seed=True, status="paused")
    result = server.create_video("db-internals", "B-trees on disk", "manual", 7)
    assert "error" not in result
    assert result["status"] == "TOPIC_PROPOSED"


def test_an_active_domain_is_unaffected(db):
    _project("db-internals", seed=True, status="active")
    result = server.create_video("db-internals", "B-trees on disk", "trending", 7)
    assert "error" not in result


def test_resuming_restores_filing_with_no_other_action(db):
    _project("db-internals", seed=True, status="paused")
    server.set_project_status("db-internals", "active")
    result = server.create_video("db-internals", "B-trees on disk", "trending", 7)
    assert "error" not in result


def test_a_stray_paused_non_seed_still_refuses(db):
    """The check reads status alone. Written as "a seed AND paused", a paused
    non-seed row that escaped the migration would slip through unnoticed."""
    _project("db-internals", seed=False, status="paused")
    result = server.create_video("db-internals", "B-trees on disk", "trending", 7)
    assert "error" in result


def test_videos_already_in_a_paused_domain_are_untouched(db):
    _project("db-internals", seed=True, status="active")
    vid = server.create_video("db-internals", "B-trees on disk", "curriculum", 7)["video_id"]
    server.set_project_status("db-internals", "paused")
    result = server.set_video_status(vid, "TOPIC_APPROVED")
    assert "error" not in result


# ── only a curriculum seed can be paused ────────────────────────────────────

def test_set_project_status_pauses_a_seed(db):
    _project("db-internals", seed=True, status="active")
    result = server.set_project_status("db-internals", "paused")
    assert result["status"] == "paused"


def test_set_project_status_refuses_to_pause_a_non_seed(db):
    _project("db-internals", seed=False, status="active")
    result = server.set_project_status("db-internals", "paused")
    assert "error" in result
    assert "curriculum seed" in result["error"]
    assert _status("db-internals") == "active"


def test_set_project_status_can_still_activate_a_stray_paused_non_seed(db):
    _project("db-internals", seed=False, status="paused")
    result = server.set_project_status("db-internals", "active")
    assert result["status"] == "active"


def test_upsert_refuses_a_new_paused_non_seed(db):
    result = server.upsert_project("db-internals", "Database internals", status="paused")
    assert "error" in result
    with server._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_upsert_refuses_to_pause_an_existing_non_seed(db):
    _project("db-internals", seed=False, status="active")
    result = server.upsert_project("db-internals", "Database internals", status="paused")
    assert "error" in result
    assert _status("db-internals") == "active"


def test_upsert_refuses_clearing_the_seed_while_pausing(db):
    _project("db-internals", seed=True, status="active")
    result = server.upsert_project("db-internals", "Database internals",
                                   is_curriculum_seed=False, status="paused")
    assert "error" in result


def test_upsert_can_create_a_paused_seed(db):
    row = server.upsert_project("db-internals", "Database internals",
                                is_curriculum_seed=True, status="paused")
    assert row["status"] == "paused"


def test_clearing_the_seed_on_a_paused_domain_reactivates_it(db):
    """Otherwise the row stays paused with no control anywhere to change it."""
    _project("db-internals", seed=True, status="paused")
    row = server.upsert_project("db-internals", "Database internals", is_curriculum_seed=False)
    assert row["is_curriculum_seed"] == 0
    assert row["status"] == "active"


def test_a_partial_upsert_leaves_a_paused_seed_paused(db):
    """The file-a-video command passes only id and name; that must not unpause."""
    _project("db-internals", seed=True, status="paused")
    row = server.upsert_project("db-internals", "Database internals")
    assert row["status"] == "paused"


def test_a_pause_landing_between_the_check_and_the_insert_still_refuses(db, monkeypatch):
    """The early SELECT runs outside any transaction, so a pause committed
    after it would otherwise be missed and the INSERT would still land. The
    INSERT itself must carry the check. _pick_agent_id runs in that window."""
    _project("db-internals", seed=True, status="active")
    real_pick = server._pick_agent_id

    def _pause_then_pick(con, *a, **kw):
        with server._conn() as other:
            other.execute("UPDATE projects SET status = 'paused' WHERE id = 'db-internals'")
        return real_pick(con, *a, **kw)

    monkeypatch.setattr(server, "_pick_agent_id", _pause_then_pick)
    result = server.create_video("db-internals", "B-trees on disk", "trending", 7)
    assert "error" in result
    assert "paused" in result["error"]
    assert _video_count() == 0


def test_a_manual_submission_is_not_caught_by_the_insert_guard(db, monkeypatch):
    _project("db-internals", seed=True, status="active")
    real_pick = server._pick_agent_id

    def _pause_then_pick(con, *a, **kw):
        with server._conn() as other:
            other.execute("UPDATE projects SET status = 'paused' WHERE id = 'db-internals'")
        return real_pick(con, *a, **kw)

    monkeypatch.setattr(server, "_pick_agent_id", _pause_then_pick)
    result = server.create_video("db-internals", "B-trees on disk", "manual", 7)
    assert "error" not in result
    assert _video_count() == 1


# ── mining into a paused domain ─────────────────────────────────────────────
# mine_youtube_topics files through create_video, so every topic would be
# refused anyway — but only after a paid Gemini call per URL. It refuses up
# front instead.

def test_mining_into_a_paused_domain_is_refused_before_any_gemini_call(db, monkeypatch):
    import httpx
    _project("db-internals", seed=True, status="paused")
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")

    def _no_call(*a, **kw):
        raise AssertionError("Gemini must not be called for a paused domain")

    monkeypatch.setattr(httpx, "Client", _no_call)
    result = server.mine_youtube_topics(project_id="db-internals",
                                        youtube_urls=["https://youtu.be/xxxxxxxxxxx"])
    assert "error" in result
    assert "paused" in result["error"]
    assert _video_count() == 0
