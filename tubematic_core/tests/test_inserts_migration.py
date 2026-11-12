"""The 0029 migration (TMDEV-224): insert columns, and moving what still holds
an insert style (System Flow, Terminal Doc) as its main one.

The cases that matter: a domain default moves to Auto; a video not yet voiced
goes back to Auto (one at Script Ready back to Topic Approved, with its style
and formula picks cleared and a comment saying why); a voiced or later video
keeps its style and finishes whole-video; every video past Topic Approved is
marked "no inserts", so a script written before inserts never gets one; and
nothing else moves.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


VIDEOS = [
    # id, status, visual_style, style_pick, archived
    ("sf_proposed", "TOPIC_PROPOSED", "system_flow", "", None),
    ("sf_approved", "TOPIC_APPROVED", "system_flow", "system_flow", None),
    ("td_script", "SCRIPT_READY", "terminal_doc", "terminal_doc", None),
    ("td_voiced", "VOICE_READY", "terminal_doc", "terminal_doc", None),
    ("sf_revision", "REVISION_REQUESTED", "system_flow", "", None),
    ("sf_scheduled", "SCHEDULED", "system_flow", "system_flow", None),
    ("td_archived", "SCRIPT_READY", "terminal_doc", "terminal_doc", "2026-01-02T00:00:00Z"),
    ("wb_script", "SCRIPT_READY", "whiteboard", "whiteboard", None),
    ("auto_approved", "TOPIC_APPROVED", "auto", "", None),
    ("mg_published", "PUBLISHED", "motion_graphics", "", None),
]


def _db_at_0028(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_to_0028"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 28:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    for pid, style in (("p_sf", "system_flow"), ("p_td", "terminal_doc"), ("p_wb", "whiteboard"),
                       ("p_none", "")):
        con.execute("INSERT INTO projects (id, name, default_visual_style, created_at) "
                    "VALUES (?, ?, ?, '2026-01-01T00:00:00Z')", (pid, pid, style))
    for vid, status, style, pick, archived in VIDEOS:
        con.execute(
            "INSERT INTO videos (id, topic, status, visual_style, style_pick, style_runner_up, "
            "style_reason, resolved_visual_style, resolved_renderer, formula_choice, formula_pick, "
            "formula_runner_up, formula_reason, agent_no_progress_count, archived_at, created_at, "
            "updated_at) VALUES (?, 't', ?, ?, ?, ?, ?, 'dark', 'dom', 'myth_buster', 'list', "
            "'story', 'why', 2, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, status, style, pick, "whiteboard" if pick else "", "because" if pick else "",
             archived))
    con.commit()
    con.close()
    return db


def _rows(db) -> dict:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out = {r["id"]: dict(r) for r in con.execute("SELECT * FROM videos")}
    con.close()
    return out


def _comments(db) -> dict:
    con = sqlite3.connect(db)
    out = {}
    for vid, author, content in con.execute("SELECT video_id, author, content FROM comments"):
        out.setdefault(vid, []).append((author, content))
    con.close()
    return out


def test_domain_defaults_in_an_insert_style_become_auto(tmp_path):
    db = _db_at_0028(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    got = dict(con.execute("SELECT id, default_visual_style FROM projects"))
    modes = {r[0] for r in con.execute("SELECT DISTINCT default_insert_mode FROM projects")}
    con.close()
    assert got == {"p_sf": "auto", "p_td": "auto", "p_wb": "whiteboard", "p_none": ""}
    assert modes == {"auto"}


def test_unvoiced_videos_in_an_insert_style_go_back_to_auto(tmp_path):
    db = _db_at_0028(tmp_path)
    tdb.migrate(db)
    rows = _rows(db)
    expect_status = {"sf_proposed": "TOPIC_PROPOSED", "sf_approved": "TOPIC_APPROVED",
                     "td_script": "TOPIC_APPROVED"}
    for vid, status in expect_status.items():
        row = rows[vid]
        assert row["status"] == status, vid
        assert row["visual_style"] == "auto", vid
        assert (row["style_pick"], row["style_runner_up"], row["style_reason"]) == ("", "", ""), vid
        assert (row["resolved_renderer"], row["resolved_visual_style"]) == ("", ""), vid
        assert (row["formula_pick"], row["formula_runner_up"], row["formula_reason"]) == ("", "", ""), vid
        # A person's formula choice is theirs, as on a style switch.
        assert row["formula_choice"] == "myth_buster", vid
        assert row["agent_no_progress_count"] == 0, vid
        assert row["insert_styles"] == "", vid
        assert row["updated_at"] != "2026-01-01T00:00:00Z", vid
    comments = _comments(db)
    for vid in expect_status:
        (author, content), = comments[vid]
        assert author == "human"
        assert "insert style" in content and "Auto" in content
    assert "new script" in comments["td_script"][0][1]


def test_voiced_and_later_videos_keep_their_style(tmp_path):
    db = _db_at_0028(tmp_path)
    tdb.migrate(db)
    rows = _rows(db)
    for vid in ("td_voiced", "sf_revision", "sf_scheduled", "td_archived"):
        before = next(v for v in VIDEOS if v[0] == vid)
        assert (rows[vid]["status"], rows[vid]["visual_style"]) == (before[1], before[2]), vid
        assert rows[vid]["resolved_renderer"] == "dom", vid
    assert set(_comments(db)) == {"sf_proposed", "sf_approved", "td_script"}


def test_scripts_written_before_inserts_never_get_any(tmp_path):
    db = _db_at_0028(tmp_path)
    tdb.migrate(db)
    rows = _rows(db)
    for vid, status, *_ in VIDEOS:
        expected = "" if status in ("TOPIC_PROPOSED", "TOPIC_APPROVED") or vid == "td_script" else "[]"
        assert rows[vid]["insert_styles"] == expected, vid
        assert rows[vid]["insert_mode"] == "auto", vid


def test_other_styles_are_untouched(tmp_path):
    db = _db_at_0028(tmp_path)
    tdb.migrate(db)
    rows = _rows(db)
    assert (rows["wb_script"]["status"], rows["wb_script"]["visual_style"],
            rows["wb_script"]["style_pick"], rows["wb_script"]["formula_pick"]) == (
        "SCRIPT_READY", "whiteboard", "whiteboard", "list")
    assert rows["auto_approved"]["updated_at"] == "2026-01-01T00:00:00Z"


def test_a_second_run_is_a_no_op(tmp_path):
    db = _db_at_0028(tmp_path)
    tdb.migrate(db)
    first = _rows(db)
    tdb.migrate(db)
    assert _rows(db) == first


def test_a_new_video_starts_undecided_with_inserts_on_auto(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    row = _rows(db)["new"]
    assert (row["insert_mode"], row["insert_styles"], row["insert_reason"]) == ("auto", "", "")
