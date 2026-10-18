"""Tests for vqa/review_video.py — the on-demand AI review script."""
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "vqa"))

from make_seed_db import make_seed_db  # noqa: E402
from review_video import review_video  # noqa: E402


def _seed_video(root: Path, video_id="vid_test123", *, status="VIDEO_READY",
                 video_path="/output_videos/proj_vqa/vid_test123.mp4",
                 scene_config_path="/jobs/vid_test123/scene-config.json",
                 script="", tts_text=""):
    """Build a minimal mounted/ tree + seed DB with one video row, plus
    on-disk stand-ins for whatever host files that row's paths translate to."""
    db_path = root / "data" / "tubematic.db"
    make_seed_db(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO videos (id, project_id, topic, status, video_path, scene_config_path, "
        "script, tts_text, created_at, updated_at) VALUES (?, 'proj_vqa', 'test topic', ?, ?, ?, "
        "?, ?, datetime('now'), datetime('now'))",
        (video_id, status, video_path, scene_config_path, script, tts_text),
    )
    con.commit()
    con.close()

    if video_path:
        host_video = root / "output_videos" / video_path[len("/output_videos/"):]
        host_video.parent.mkdir(parents=True, exist_ok=True)
        host_video.write_bytes(b"fake-mp4-bytes")
    if scene_config_path:
        host_config = root / "jobs" / scene_config_path[len("/jobs/"):]
        host_config.parent.mkdir(parents=True, exist_ok=True)
        host_config.write_text('{"totalFrames": 100, "fps": 30, "scenes": []}')

    return db_path


def _row(db_path: Path, video_id: str):
    con = sqlite3.connect(str(db_path))
    row = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    con.close()
    return row


class TestDerivedPaths:
    """The files are found from the id and project, never from the stored
    columns (TMDEV-162), which could once be pointed at any host file."""

    def test_a_planted_video_path_is_not_what_gets_reviewed(self, tmp_path):
        _seed_video(tmp_path)
        planted = tmp_path / "secret.mp4"
        planted.write_bytes(b"secret")
        db_path = tmp_path / "data" / "tubematic.db"
        con = sqlite3.connect(str(db_path))
        con.execute("UPDATE videos SET video_path = ? WHERE id = 'vid_test123'", (str(planted),))
        con.commit()
        con.close()
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured["video_path"] = video_path
            return {"feedback": "x"}

        review_video("vid_test123", tmp_path, run_review=fake_run)
        assert captured["video_path"] == str(
            tmp_path / "output_videos" / "proj_vqa" / "vid_test123.mp4")

    def test_output_videos_path_override_is_honored(self, tmp_path, monkeypatch):
        _seed_video(tmp_path)
        override = tmp_path / "elsewhere"
        (override / "proj_vqa").mkdir(parents=True)
        (override / "proj_vqa" / "vid_test123.mp4").write_bytes(b"mp4")
        monkeypatch.setenv("OUTPUT_VIDEOS_PATH", str(override))
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured["video_path"] = video_path
            return {"feedback": "x"}

        review_video("vid_test123", tmp_path, run_review=fake_run)
        assert captured["video_path"] == str(override / "proj_vqa" / "vid_test123.mp4")


class TestReviewVideo:
    def test_unknown_video_id_errors(self, tmp_path):
        _seed_video(tmp_path)
        with pytest.raises(SystemExit, match="No video found"):
            review_video("vid_does_not_exist", tmp_path)

    def test_unrendered_video_names_current_status(self, tmp_path):
        _seed_video(tmp_path, status="SCRIPT_READY", video_path="", scene_config_path="")
        with pytest.raises(SystemExit, match="not been rendered yet.*SCRIPT_READY"):
            review_video("vid_test123", tmp_path)

    def test_missing_scene_config_path_errors(self, tmp_path):
        _seed_video(tmp_path, status="RENDERING", video_path="", scene_config_path="")
        # video_path empty is checked first, so use a rendered video_path but
        # no scene_config_path to isolate this specific guard.
        db_path = tmp_path / "data" / "tubematic.db"
        con = sqlite3.connect(str(db_path))
        con.execute(
            "UPDATE videos SET video_path = '/output_videos/proj_vqa/vid_test123.mp4', "
            "status = 'VIDEO_READY' WHERE id = 'vid_test123'"
        )
        con.commit()
        con.close()
        with pytest.raises(SystemExit, match="no scene_config_path recorded"):
            review_video("vid_test123", tmp_path)

    def test_happy_path_calls_reviewer_with_host_paths_and_parsed_config(self, tmp_path):
        _seed_video(tmp_path)
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured["video_path"] = video_path
            captured["scene_config"] = scene_config
            return {"feedback": "fake feedback text"}

        feedback, review_path = review_video("vid_test123", tmp_path, run_review=fake_run)

        assert feedback == "fake feedback text"
        assert captured["video_path"] == str(
            tmp_path / "output_videos" / "proj_vqa" / "vid_test123.mp4"
        )
        assert captured["scene_config"] == {"totalFrames": 100, "fps": 30, "scenes": []}
        assert review_path == tmp_path / "jobs" / "vid_test123" / "ai_review.txt"

    def test_passes_script_and_tts_text_as_pronunciation_reference(self, tmp_path):
        # VQA-6: without these, the review has no ground truth for what was
        # said, and a deliberate <respell> substitution looks like a defect.
        _seed_video(tmp_path, script="Vhagar flew.", tts_text="Vah-gar flew.")
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured.update(kwargs)
            return {"feedback": "x"}

        review_video("vid_test123", tmp_path, run_review=fake_run)

        assert captured["script_text"] == "Vhagar flew."
        assert captured["tts_text"] == "Vah-gar flew."

    def test_passes_review_model_and_fps_from_the_settings_table(self, tmp_path):
        # VQA-7: /vqa-review must review on the same settings the pipeline
        # uses. If it didn't, every before/after comparison run through this
        # script -- which is the only way a prompt change can be evaluated at
        # all -- would be comparing two different configurations.
        db_path = _seed_video(tmp_path)
        con = sqlite3.connect(str(db_path))
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES "
                    "('ai_review_model', 'gemini-3.6-flash')")
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES "
                    "('ai_review_fps', '20')")
        con.commit()
        con.close()
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured.update(kwargs)
            return {"feedback": "x"}

        review_video("vid_test123", tmp_path, run_review=fake_run)

        assert captured["model"] == "gemini-3.6-flash"
        assert captured["fps"] == "20"

    def test_review_settings_fall_back_to_the_pipeline_defaults_when_unset(self, tmp_path):
        # make_seed_db deliberately seeds only the keys that differ from
        # SETTINGS_SPEC's defaults, so absent rows are the normal case here.
        # These fallbacks must match those defaults, or the VQA environment
        # would sample at 1 FPS while the pipeline it assesses samples at 10.
        _seed_video(tmp_path)
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured.update(kwargs)
            return {"feedback": "x"}

        review_video("vid_test123", tmp_path, run_review=fake_run)

        assert captured["model"] == "gemini-2.5-flash"
        assert captured["fps"] == "10"

    def test_unvoiced_reference_fields_pass_through_as_empty_strings(self, tmp_path):
        # A row voiced before tts_text was recorded has NULL/'' there; the
        # reviewer must still be called, with empty strings rather than None.
        _seed_video(tmp_path, script="", tts_text="")
        captured = {}

        def fake_run(video_path, scene_config, **kwargs):
            captured.update(kwargs)
            return {"feedback": "x"}

        review_video("vid_test123", tmp_path, run_review=fake_run)

        # Per-key rather than the whole kwargs dict, which also carries the
        # VQA-7 model/fps settings (covered by their own tests below).
        assert captured["script_text"] == ""
        assert captured["tts_text"] == ""

    def test_makes_no_db_writes(self, tmp_path):
        db_path = _seed_video(tmp_path)
        before = _row(db_path, "vid_test123")

        review_video("vid_test123", tmp_path, run_review=lambda vp, sc, **kw: {"feedback": "x"})

        after = _row(db_path, "vid_test123")
        assert before == after, "review_video must not mutate the videos row"

    def test_missing_video_file_on_disk_errors_clearly(self, tmp_path):
        _seed_video(tmp_path)
        host_video = tmp_path / "output_videos" / "proj_vqa" / "vid_test123.mp4"
        host_video.unlink()
        with pytest.raises(SystemExit, match="Rendered video not found on disk"):
            review_video("vid_test123", tmp_path)

    def test_writes_feedback_to_ai_review_file(self, tmp_path):
        _seed_video(tmp_path)
        _, review_path = review_video(
            "vid_test123", tmp_path, run_review=lambda vp, sc, **kw: {"feedback": "The pacing is great."}
        )
        assert review_path.read_text() == "The pacing is great.\n"

    def test_rerunning_overwrites_the_review_file(self, tmp_path):
        _seed_video(tmp_path)
        review_video("vid_test123", tmp_path, run_review=lambda vp, sc, **kw: {"feedback": "First review."})
        _, review_path = review_video(
            "vid_test123", tmp_path, run_review=lambda vp, sc, **kw: {"feedback": "Second review."}
        )
        content = review_path.read_text()
        assert content == "Second review.\n"
        assert "First review" not in content


class TestRootResolvesFromScriptLocation:
    """The data root is a fixed absolute path (~/.tubematic-data, TMDEV-76),
    so review_video.py reads the same tree the containers write to no matter
    where the script itself lives or where it was launched from. This pins
    that cwd is irrelevant — previously the root came from the script's own
    location, which is what made an /opt copy read the wrong tree."""

    def test_isolated_copy_reads_its_own_tree_not_cwd(self, tmp_path):
        # Mirror the real layout as a minimal, isolated copy: vqa/review_video.py
        # plus its real dependencies, renderer/api/ai_review.py (which has no
        # further intra-repo imports) and tubematic_core, under a tree with nothing else in common
        # with the actual checkout.
        isolated = tmp_path / "isolated_tree"
        (isolated / "vqa").mkdir(parents=True)
        (isolated / "renderer" / "api").mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "vqa" / "review_video.py", isolated / "vqa" / "review_video.py")
        # The shared package it derives the file paths with.
        shutil.copytree(REPO_ROOT / "tubematic_core", isolated / "tubematic_core",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
        shutil.copy2(
            REPO_ROOT / "renderer" / "api" / "ai_review.py",
            isolated / "renderer" / "api" / "ai_review.py",
        )

        # Seed under a throwaway HOME: the data root is ~/.tubematic-data now,
        # so that is where the script looks regardless of the tree it sits in.
        fake_home = tmp_path / "home"
        _seed_video(fake_home / ".tubematic-data")

        # No GEMINI_API_KEY in the environment or an isolated .env — run_ai_review
        # fails open on that ("Gemini API key not set") without ever making a
        # network call, which makes this a deterministic, offline test while
        # still proving the DB/file lookups resolved correctly.
        result = subprocess.run(
            [sys.executable, str(isolated / "vqa" / "review_video.py"), "vid_test123"],
            cwd="/",  # deliberately NOT isolated/ — proves resolution isn't cwd-based
            capture_output=True,
            text=True,
            # HOME points the fixed data root at the throwaway tree; no
            # GEMINI_API_KEY leaks in from the real environment.
            env={"PATH": "/usr/bin:/bin", "HOME": str(fake_home)},
        )

        assert result.returncode == 0, result.stderr
        # The key now comes from the settings table, and this isolated tree
        # seeds none — so the review still fails open with a clear message
        # rather than the old env-var name (TMDEV-73).
        assert "Gemini API key not set" in result.stdout

        # run_ai_review fails open (never raises) — its "feedback" field is
        # always populated, even on this error path, so the file gets
        # written the same as a real review. Confirms the write also lands in
        # the fixed data root rather than beside the script or under cwd.
        review_path = fake_home / ".tubematic-data" / "jobs" / "vid_test123" / "ai_review.txt"
        assert review_path.exists()
        assert "Gemini API key not set" in review_path.read_text()
        assert f"Written to: {review_path}" in result.stdout
