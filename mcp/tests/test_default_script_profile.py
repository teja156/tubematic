"""A domain's default script profile through MCP (TMDEV-145).

The MCP copy of renderer/api/tests/test_default_script_profile.py: the
default seeds curriculum videos only, a profile no longer READY seeds nothing,
and upsert_project checks a default only when it changes. Unlike POST
/projects, upsert_project is a partial update, so an omitted default is kept.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pytest

import server


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    return tmp_path / "test.db"


def _profile(pid, status="READY", archived=0):
    with server._conn() as con:
        con.execute(
            "INSERT INTO script_profiles (id, name, status, archived, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (pid, pid.title(), status, archived))


def _archive(pid):
    with server._conn() as con:
        con.execute("UPDATE script_profiles SET archived = 1 WHERE id = ?", (pid,))


def _stored(video_id):
    with server._conn() as con:
        return con.execute("SELECT script_profile_id FROM videos WHERE id = ?",
                           (video_id,)).fetchone()[0]


# ── upsert_project ───────────────────────────────────────────────────────────

def test_upsert_project_stores_a_default_profile(db):
    _profile("prof")
    row = server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    assert row["default_script_profile_id"] == "prof"


@pytest.mark.parametrize("status,archived", [("PENDING", 0), ("GENERATING", 0), ("READY", 1)])
def test_upsert_project_refuses_an_unusable_profile(db, status, archived):
    _profile("prof", status=status, archived=archived)
    result = server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    assert "not a READY script profile" in result["error"]


def test_an_omitted_default_is_kept(db):
    _profile("prof")
    server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    row = server.upsert_project("dom", "Renamed", is_curriculum_seed=True)
    assert row["default_script_profile_id"] == "prof"


def test_an_empty_default_clears_it(db):
    _profile("prof")
    server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    row = server.upsert_project("dom", "Domain", default_script_profile_id="")
    assert row["default_script_profile_id"] == ""


def test_re_sending_a_default_archived_since_is_accepted(db):
    _profile("prof")
    server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    _archive("prof")
    row = server.upsert_project("dom", "Renamed", default_script_profile_id="prof")
    assert row["name"] == "Renamed"


# ── seeding on create_video ──────────────────────────────────────────────────

def test_a_curriculum_video_starts_with_the_domain_profile(db):
    _profile("prof")
    server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    result = server.create_video("dom", "A topic", "curriculum", 7)
    assert result["script_profile_id"] == "prof"
    assert _stored(result["video_id"]) == "prof"


@pytest.mark.parametrize("strategy", ["trending", "mining", "manual"])
def test_other_strategies_do_not_inherit_it(db, strategy):
    _profile("prof")
    server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    result = server.create_video("dom", "A topic", strategy, 7)
    assert result["script_profile_id"] == ""
    assert _stored(result["video_id"]) == ""


def test_a_domain_without_a_default_seeds_no_profile(db):
    server.upsert_project("dom", "Domain")
    result = server.create_video("dom", "A topic", "curriculum", 7)
    assert _stored(result["video_id"]) == ""


def test_a_default_archived_since_seeds_nothing(db):
    _profile("prof")
    server.upsert_project("dom", "Domain", default_script_profile_id="prof")
    _archive("prof")
    result = server.create_video("dom", "A topic", "curriculum", 7)
    assert _stored(result["video_id"]) == ""
