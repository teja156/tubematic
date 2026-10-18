"""Tests for vqa/reset_db.py — the destructive DB + artifact reset utility."""
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "vqa"))

from reset_db import _clear_dir_contents, main, reset_db  # noqa: E402


def _fake_make_seed_db(calls):
    """Records calls and writes a marker file instead of a real DB — keeps
    these tests independent of renderer/api/pipeline.py's schema."""
    def _fake(output_path):
        calls.append(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("fake-seeded-db")
    return _fake


def _populate(root: Path):
    for subdir, filename, content in [
        ("jobs/vid_old", "audio.mp3", "fake-audio"),
        ("output_videos/proj_vqa", "vid_old.mp4", "fake-mp4"),
        ("scenes/generated/vid_old", "Scene.tsx", "fake-scene"),
    ]:
        d = root / subdir
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text(content)


class TestClearDirContents:
    def test_removes_all_entries(self, tmp_path):
        d = tmp_path / "target"
        d.mkdir()
        (d / "a.txt").write_text("x")
        (d / "sub").mkdir()
        (d / "sub" / "b.txt").write_text("y")

        removed = _clear_dir_contents(d)

        assert set(removed) == {"a.txt", "sub"}
        assert list(d.iterdir()) == []
        assert d.exists()  # the directory itself survives, only contents go

    def test_missing_dir_is_a_noop(self, tmp_path):
        assert _clear_dir_contents(tmp_path / "does_not_exist") == []


class TestResetDb:
    def test_calls_make_seed_db_with_live_db_path(self, tmp_path):
        calls = []
        result = reset_db(tmp_path, make_seed_db=_fake_make_seed_db(calls))
        assert calls == [tmp_path / "data" / "tubematic.db"]
        assert result["db_path"] == tmp_path / "data" / "tubematic.db"
        assert (tmp_path / "data" / "tubematic.db").read_text() == "fake-seeded-db"

    def test_clears_associated_dirs_by_default(self, tmp_path):
        _populate(tmp_path)
        result = reset_db(tmp_path, make_seed_db=_fake_make_seed_db([]))

        assert not (tmp_path / "jobs" / "vid_old").exists()
        assert not (tmp_path / "output_videos" / "proj_vqa").exists()
        assert not (tmp_path / "scenes" / "generated" / "vid_old").exists()
        assert result["cleared"] == {
            "jobs": ["vid_old"],
            "output_videos": ["proj_vqa"],
            "scenes/generated": ["vid_old"],
        }

    def test_db_only_leaves_associated_dirs_untouched(self, tmp_path):
        _populate(tmp_path)
        result = reset_db(tmp_path, db_only=True, make_seed_db=_fake_make_seed_db([]))

        assert (tmp_path / "jobs" / "vid_old" / "audio.mp3").exists()
        assert (tmp_path / "output_videos" / "proj_vqa" / "vid_old.mp4").exists()
        assert (tmp_path / "scenes" / "generated" / "vid_old" / "Scene.tsx").exists()
        assert result["cleared"] == {}

    def test_overwrites_existing_db_content(self, tmp_path):
        db_path = tmp_path / "data" / "tubematic.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("stale-old-content")

        reset_db(tmp_path, make_seed_db=_fake_make_seed_db([]))

        assert db_path.read_text() == "fake-seeded-db"


class TestMainCli:
    def test_dry_run_without_yes_touches_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("reset_db._data_root", lambda: tmp_path)
        db_path = tmp_path / "data" / "tubematic.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("precious")

        main([])

        assert db_path.read_text() == "precious"
        out = capsys.readouterr().out
        assert "would DELETE" in out
        assert "--yes" in out

    def test_yes_flag_performs_reset_using_real_make_seed_db(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("reset_db._data_root", lambda: tmp_path)
        db_path = tmp_path / "data" / "tubematic.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("stale")

        main(["--yes"])

        con = sqlite3.connect(str(db_path))
        assert con.execute("SELECT id, status FROM projects").fetchall() == [("proj_vqa", "active")]
        con.close()
        out = capsys.readouterr().out
        assert "Reset" in out


class TestRootResolvesFromScriptLocation:
    """Same class as review_video.py / stage_script.py: the data root is the
    fixed ~/.tubematic-data (TMDEV-76), so a copy of this script resets the
    tree the containers actually write to — never one beside the script, and
    never one under whatever directory the process was launched from."""

    def test_isolated_copy_reads_its_own_tree_not_cwd(self, tmp_path):
        isolated = tmp_path / "isolated_tree"
        (isolated / "vqa").mkdir(parents=True)
        (isolated / "mcp").mkdir(parents=True)
        (isolated / "renderer" / "api").mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "vqa" / "reset_db.py", isolated / "vqa" / "reset_db.py")
        shutil.copy2(REPO_ROOT / "vqa" / "make_seed_db.py", isolated / "vqa" / "make_seed_db.py")
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "pipeline.py", isolated / "renderer" / "api" / "pipeline.py")
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "hosttz.py", isolated / "renderer" / "api" / "hosttz.py")
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "transcripts.py", isolated / "renderer" / "api" / "transcripts.py")
        # pipeline.py imports postforme at module level too (TMDEV-83) — any
        # isolated copy of pipeline.py has to bring every sibling it imports.
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "postforme.py", isolated / "renderer" / "api" / "postforme.py")
        # And discord_notify, imported at module level for the same reason
        # (TMDEV-5): POST /settings validates a webhook URL's shape with it.
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "discord_notify.py", isolated / "renderer" / "api" / "discord_notify.py")
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "metrics.py", isolated / "renderer" / "api" / "metrics.py")
        # metrics.py imports db — the first thing in this chain to do so, since
        # pipeline.py has its own _conn.
        shutil.copy2(REPO_ROOT / "renderer" / "api" / "db.py", isolated / "renderer" / "api" / "db.py")
        # The shared tubematic_core package. An isolated tree has to bring it
        # like any other import: in the container it arrives on PYTHONPATH
        # (/app/lib), which this reconstruction deliberately does not have.
        shutil.copytree(REPO_ROOT / "tubematic_core", isolated / "tubematic_core",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))

        # The data root is HOME-relative, so a throwaway HOME isolates it —
        # note it is deliberately NOT inside `isolated`, proving the script
        # does not read a tree beside itself either.
        fake_home = tmp_path / "home"
        db_path = fake_home / ".tubematic-data" / "data" / "tubematic.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("stale-marker-that-must-disappear")

        result = subprocess.run(
            [sys.executable, str(isolated / "vqa" / "reset_db.py"), "--yes"],
            cwd="/",  # deliberately not `isolated` — proves resolution isn't cwd-based
            capture_output=True,
            text=True,
            # PYTHONPATH mirrors the container, where the shared package sits at
            # /app/lib (renderer/Dockerfile). Pointed at the isolated root, not the
            # repo, so the test still proves nothing is read from outside this tree.
            env={"PATH": "/usr/bin:/bin", "HOME": str(fake_home),
                 "PYTHONPATH": str(isolated)},
        )

        assert result.returncode == 0, result.stderr
        content = db_path.read_bytes()
        assert content != b"stale-marker-that-must-disappear"
        con = sqlite3.connect(str(db_path))
        assert con.execute("SELECT id FROM projects").fetchall() == [("proj_vqa",)]
        con.close()
