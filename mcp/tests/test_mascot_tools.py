"""The mascot builder tools: get_mascot_job, render_mascot_sheets, submit_mascot.

The sheet renderer (a Node script on software GL) is faked: mascot_sheets.render_sheet
is replaced by a function that writes a real PNG, so what is tested is this server's
rules around it: which status each tool works in, the render cap, a changed code
invalidating the sheets rendered from the old one, and submit refusing until all
three sheets exist for the code as it now stands.
"""
import io
from datetime import datetime, timezone

import pytest

import mascot_sheets
import server
from tubematic_core import mascots as tmascots


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "data" / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    calls = []

    def fake_render(remotion_dir, code_file, sheet, out_png, timeout=1200):
        from PIL import Image
        calls.append({"sheet": sheet, "code": open(code_file).read()})
        Image.new("RGB", (2000, 1000), "white").save(out_png)

    monkeypatch.setattr(mascot_sheets, "render_sheet", fake_render)
    return calls


def _mascot(mid="moss", status="BUILDING", approved=0, versions=((1, "", "a tardigrade"),), **cols):
    """versions: (version, code, change_request); the highest above `approved` is the draft."""
    row = dict(id=mid, name="Moss", description="a tardigrade", status=status,
               approved_version=approved, created_at=_now(), updated_at=_now())
    row.update(cols)
    with server._conn() as con:
        con.execute(f"INSERT INTO mascots ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                    list(row.values()))
        for v, code, req in versions:
            con.execute("INSERT INTO mascot_versions (mascot_id, version, code, change_request, created_at, "
                        "approved_at) VALUES (?,?,?,?,?,?)",
                        (mid, v, code, req, _now(), _now() if v <= approved else ""))
    return mid


def _col(mid, col):
    with server._conn() as con:
        return con.execute(f"SELECT {col} FROM mascots WHERE id = ?", (mid,)).fetchone()[0]


def _draft_code(mid, v=1):
    with server._conn() as con:
        return con.execute("SELECT code FROM mascot_versions WHERE mascot_id=? AND version=?", (mid, v)).fetchone()[0]


def _sheet_path(mid, v, sheet):
    return tmascots.sheet_file(server.DB_FILE.parent, mid, v, sheet)


def _render(mid="moss", code="// moss v1", sheet="turn"):
    return server.render_mascot_sheets(mid, code, sheet)


# ── get_mascot_job ──────────────────────────────────────────────────────────

def test_a_new_mascot_job_carries_the_brief_and_the_cap(db):
    _mascot(status="BUILDING")
    job = server.get_mascot_job("moss")
    assert job["kind"] == "new" and job["mascot_id"] == "moss" and job["name"] == "Moss"
    assert job["description"] == "a tardigrade" and job["change_request"] == "a tardigrade"
    assert job["previous_code"] == "" and job["based_on_code"] == ""
    assert job["emotions"] == list(tmascots.EMOTIONS)
    assert job["renders_left"] == tmascots.MAX_SHEET_RENDERS_PER_ATTEMPT
    assert job["sheets"] == {"turn": False, "feels": False, "act": False}


def test_an_empty_brief_is_a_surprise(db):
    _mascot(description="", versions=((1, "", ""),))
    assert server.get_mascot_job("moss")["kind"] == "surprise"


def test_a_change_job_names_the_request_and_hands_over_the_approved_code(db):
    _mascot(approved=1, status="BUILDING", versions=((1, "// approved v1", "a tardigrade"), (2, "", "make it blue")))
    job = server.get_mascot_job("moss")
    assert job["kind"] == "change"
    assert job["change_request"] == "make it blue" and job["description"] == "a tardigrade"
    assert job["previous_code"] == "// approved v1"


def test_a_job_hands_over_the_code_of_the_mascot_it_is_based_on(db):
    _mascot("base", status="READY", approved=1, versions=((1, "// base code", "x"),))
    _mascot("kid", based_on="base")
    assert server.get_mascot_job("kid")["based_on_code"] == "// base code"


def test_a_job_on_a_builtin_base_reads_the_repo_file(db, tmp_path, monkeypatch):
    remotion = tmp_path / "rem"
    d = tmp_path / "rem" / "mascot-builtin" / "tubi" / "v1"
    d.mkdir(parents=True)
    (d / "mascot.js").write_text("// tubi code")
    monkeypatch.setattr(server, "_MASCOT_REMOTION", remotion)
    _mascot("kid", based_on="tubi")
    assert server.get_mascot_job("kid")["based_on_code"] == "// tubi code"


def test_the_job_reports_sheets_rendered_and_renders_left(db):
    _mascot()
    _render(sheet="turn")
    job = server.get_mascot_job("moss")
    assert job["sheets"] == {"turn": True, "feels": False, "act": False}
    assert job["renders_left"] == tmascots.MAX_SHEET_RENDERS_PER_ATTEMPT - 1


def test_an_unknown_mascot_and_a_mascot_with_no_draft_are_errors(db):
    assert "not found" in server.get_mascot_job("nope")["error"]
    _mascot("done", status="READY", approved=1, versions=((1, "// c", "x"),))
    assert "no change in progress" in server.get_mascot_job("done")["error"]


# ── render_mascot_sheets ────────────────────────────────────────────────────

def test_a_render_stores_the_code_the_sheet_and_the_count_and_returns_the_picture(db):
    _mascot()
    out = _render(code="// moss v1", sheet="feels")
    assert isinstance(out, list) and len(out) == 2
    import json
    meta = json.loads(out[0])
    assert meta["sheet"] == "feels" and meta["version"] == 1
    assert meta["renders_left"] == tmascots.MAX_SHEET_RENDERS_PER_ATTEMPT - 1
    assert meta["sheets"] == {"turn": False, "feels": True, "act": False}
    from PIL import Image
    assert max(Image.open(io.BytesIO(out[1].data)).size) <= server._READ_IMAGE_MAX_EDGE
    assert _draft_code("moss") == "// moss v1"
    assert _sheet_path("moss", 1, "feels").is_file()
    assert _col("moss", "sheet_renders") == 1
    assert db[0] == {"sheet": "feels", "code": "// moss v1"}


@pytest.mark.parametrize("status", ["PENDING", "IN_REVIEW", "READY", "FAILED"])
def test_rendering_works_only_while_building(db, status):
    _mascot(status=status)
    assert "BUILDING" in server.render_mascot_sheets("moss", "// c", "turn")["error"]
    assert db == [] and _draft_code("moss") == ""


def test_a_bad_sheet_name_or_empty_code_or_unknown_mascot_is_refused(db):
    _mascot()
    assert "sheet" in server.render_mascot_sheets("moss", "// c", "front")["error"]
    assert "code" in server.render_mascot_sheets("moss", "  ", "turn")["error"]
    assert "not found" in server.render_mascot_sheets("nope", "// c", "turn")["error"]
    assert db == []


def test_the_render_cap_refuses_the_next_render_and_runs_nothing(db):
    _mascot(sheet_renders=tmascots.MAX_SHEET_RENDERS_PER_ATTEMPT)
    err = _render()["error"]
    assert str(tmascots.MAX_SHEET_RENDERS_PER_ATTEMPT) in err
    assert db == [] and _draft_code("moss") == ""


def test_the_cap_counts_a_render_that_fails(db, monkeypatch):
    _mascot()

    def boom(*a, **k):
        raise mascot_sheets.MascotSheetError("the turn sheet failed to render (exit 1): ReferenceError: x")

    monkeypatch.setattr(mascot_sheets, "render_sheet", boom)
    assert "ReferenceError" in _render()["error"]
    assert _col("moss", "sheet_renders") == 1
    assert _draft_code("moss") == "// moss v1"            # the code is kept for the next try
    assert not _sheet_path("moss", 1, "turn").exists()


def test_a_change_renders_a_new_draft_and_never_touches_the_approved_version(db):
    _mascot(approved=1, versions=((1, "// approved v1", "a"), (2, "", "make it blue")))
    _render(code="// v2")
    assert _draft_code("moss", 2) == "// v2" and _draft_code("moss", 1) == "// approved v1"
    assert _sheet_path("moss", 2, "turn").is_file()


def test_changed_code_invalidates_the_sheets_rendered_from_the_old_code(db):
    _mascot()
    for s in ("turn", "feels", "act"):
        _render(code="// one", sheet=s)
    assert all(_sheet_path("moss", 1, s).is_file() for s in ("turn", "feels", "act"))
    _render(code="// two", sheet="turn")
    assert _sheet_path("moss", 1, "turn").is_file()
    assert not _sheet_path("moss", 1, "feels").exists() and not _sheet_path("moss", 1, "act").exists()


def test_unchanged_code_keeps_the_other_sheets(db):
    _mascot()
    _render(code="// one", sheet="turn")
    _render(code="// one", sheet="feels")
    assert _sheet_path("moss", 1, "turn").is_file() and _sheet_path("moss", 1, "feels").is_file()


# ── submit_mascot ───────────────────────────────────────────────────────────

def _all_sheets(code="// one"):
    for s in ("turn", "feels", "act"):
        _render(code=code, sheet=s)


def test_submit_needs_all_three_sheets(db):
    _mascot()
    _render(sheet="turn")
    err = server.submit_mascot("moss", "notes")["error"]
    assert "feels" in err and "act" in err and "turn" not in err
    assert _col("moss", "status") == "BUILDING"


def test_submit_refuses_sheets_made_from_older_code(db):
    _mascot()
    _all_sheets("// one")
    _render(code="// two", sheet="turn")
    err = server.submit_mascot("moss", "")["error"]
    assert "feels" in err and "act" in err
    assert _col("moss", "status") == "BUILDING"


def test_submit_moves_to_review_and_returns_the_notes(db):
    _mascot()
    _all_sheets()
    out = server.submit_mascot("moss", "kept the legs short")
    assert out == {"mascot_id": "moss", "status": "IN_REVIEW", "version": 1, "notes": "kept the legs short"}
    assert _col("moss", "status") == "IN_REVIEW"


@pytest.mark.parametrize("status", ["PENDING", "IN_REVIEW", "READY", "FAILED"])
def test_submit_works_only_while_building(db, status):
    _mascot(status=status)
    assert "BUILDING" in server.submit_mascot("moss", "")["error"]


def test_submit_loses_a_race_with_a_status_change(db, monkeypatch):
    _mascot()
    _all_sheets()
    real = server._mascot_missing_sheets

    def flip_then_check(*a, **k):
        with server._conn() as con:
            con.execute("UPDATE mascots SET status = 'FAILED' WHERE id = 'moss'")
        return real(*a, **k)

    monkeypatch.setattr(server, "_mascot_missing_sheets", flip_then_check)
    assert "BUILDING" in server.submit_mascot("moss", "")["error"]
    assert _col("moss", "status") == "FAILED"


def test_the_three_tools_are_offered(db):
    import asyncio
    from fastmcp import Client

    async def go():
        async with Client(server.mcp) as client:
            return {t.name for t in await client.list_tools()}

    assert {"get_mascot_job", "render_mascot_sheets", "submit_mascot"} <= asyncio.run(go())
