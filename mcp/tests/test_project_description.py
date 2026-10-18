"""A domain's description through upsert_project (TMDEV-170).

The description is a multi-line scope statement the agent reads on every
research run, capped at PROJECT_DESCRIPTION_MAX_CHARS. The cap is checked only
when the description changes, so a longer one stored before the cap existed
is never refused when re-sent, and an omitted description is never checked.
The MCP mirror of renderer/api/tests/test_project_description.py.

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


def _stored(pid="db-internals"):
    with server._conn() as con:
        row = con.execute("SELECT description FROM projects WHERE id = ?", (pid,)).fetchone()
    return row["description"] if row else None


def _plant(text, pid="db-internals"):
    """Store a description directly, as one written before the cap would be."""
    with server._conn() as con:
        con.execute("UPDATE projects SET description = ? WHERE id = ?", (text, pid))


def _upsert(**fields):
    return server.upsert_project("db-internals", "Database internals", **fields)


def test_a_multi_line_description_is_stored_verbatim(db):
    text = "Storage engines and query planning.\n\nNot: ORMs or SQL tutorials."
    assert _upsert(description=text)["description"] == text
    assert _stored() == text


def test_the_cap_is_inclusive_and_counts_code_points(db):
    assert "error" not in _upsert(description="🐘" * 2000)
    assert _stored() == "🐘" * 2000


def test_one_past_the_cap_is_refused_on_create(db):
    out = _upsert(description="x" * 2001)
    assert out == {"error": "description must be at most 2000 characters, got 2001"}
    assert _stored() is None


def test_a_change_to_an_over_cap_description_is_refused(db):
    _upsert(description="short")
    assert "error" in _upsert(description="x" * 2001)
    assert _stored() == "short"


def test_an_unchanged_over_cap_description_is_not_refused(db):
    """The negative control: re-sending what is stored must never be refused."""
    _upsert(description="short")
    _plant("y" * 3000)
    out = _upsert(description="y" * 3000, default_visual_style="stick")
    assert "error" not in out
    assert out["default_visual_style"] == "stick"
    assert _stored() == "y" * 3000


def test_an_omitted_description_keeps_an_over_cap_one(db):
    _upsert(description="short")
    _plant("y" * 3000)
    out = _upsert(is_curriculum_seed=True)
    assert "error" not in out
    assert _stored() == "y" * 3000


def test_an_empty_description_clears_an_over_cap_one(db):
    _upsert(description="short")
    _plant("y" * 3000)
    assert "error" not in _upsert(description="")
    assert _stored() == ""
