"""The shipped builtin mascot, Tubi, version 1.

Migration 0018 seeds a READY `tubi` row approved at version 1 and stores no
code for it: code_for reads renderer/remotion/mascot-builtin/tubi/v1/mascot.js
instead. If that file (or one of the three model sheets the dashboard shows
for it) went missing, every install's default mascot would break at render
time, so the files are pinned here against a really migrated database.
"""
import pathlib
import re
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import mascots  # noqa: E402

REMOTION = ROOT / "renderer" / "remotion"


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def test_the_v1_directory_has_the_code_and_the_three_sheets():
    d = mascots.builtin_dir(REMOTION, "tubi", 1)
    assert (d / "mascot.js").is_file()
    for sheet in mascots.SHEETS:
        f = d / f"{sheet}.jpg"     # the Flask route serves a builtin's sheets as .jpg
        assert f.is_file() and f.stat().st_size > 0, f
        assert f.read_bytes()[:3] == b"\xff\xd8\xff", f"{f} is not a JPEG"


def test_code_for_reads_tubi_v1_on_a_migrated_db(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    approved = con.execute("SELECT approved_version FROM mascots WHERE id = 'tubi'").fetchone()[0]
    code = mascots.code_for(con, REMOTION, "tubi", approved)
    con.close()
    assert code.strip()
    assert code == (REMOTION / "mascot-builtin" / "tubi" / "v1" / "mascot.js").read_text(encoding="utf-8")


def test_mascot_js_registers_itself_and_every_face_carries_bx():
    code = (REMOTION / "mascot-builtin" / "tubi" / "v1" / "mascot.js").read_text(encoding="utf-8")
    assert re.search(r"^window\.MASCOT = tubi;", code, re.M)
    assert "window.MASCOT_COLS" in code
    # blush() reads F.bx: a face record without it makes every blush NaN, silently.
    faces = re.findall(r"face: \{[^}]*\}", code)
    assert faces, "no face records found"
    assert all("bx:" in f for f in faces), faces
    # never talks, never fetches, names no other character
    assert not re.search(r"mouthAt|['\"]talk['\"]", code)
    assert not re.search(r"https?://|fetch\(|XMLHttpRequest", code)
    assert not re.search(r"clawd|anthropic", code, re.I)
