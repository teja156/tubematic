"""The render watcher (TMDEV-179): Remotion's progress counters decide whether a
render is alive, and a Cartoon 3D video renders on the GPU or not at all.

A timeout here is a crash detector, not a budget: a render whose counter
stops advancing is killed in minutes whatever its length, and one that
advances is left alone for hours. The watcher is driven against real child
processes, since what it guards against (a pipe that fills, a line that
repeats) is process behaviour.

Requires the renderer/api deps (flask) — see renderer/api/requirements.txt.
Run from repo root: pytest renderer/api/tests/
"""
import io
import json
import sqlite3
import subprocess
import sys
from unittest import mock

import pytest

import pipeline
import worker


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = str(tmp_path / "test.db")
    pipeline._init_db(p)
    monkeypatch.setattr(worker, "DB_PATH", p)
    return p


@pytest.fixture(autouse=True)
def no_gpu(monkeypatch):
    """Every test starts unconfigured and unverified, as test_gpu_rendering does."""
    for var in ("TUBEMATIC_GPU_UUID", "TUBEMATIC_GPU_NAME", "TUBEMATIC_HOST_GPUS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(worker, "_gpu_verified", False)


# ── The counter ──────────────────────────────────────────────────────────────

def test_progress_reads_remotion_counters_and_nothing_else():
    assert worker._progress_of("Bundling 6%") == (0, 6)
    assert worker._progress_of("Bundling 100%") == (0, 100)
    assert worker._progress_of("Rendered 8/60") == (1, 8)
    assert worker._progress_of("[Tab 0] Encoded 17/60") == (2, 17)
    assert worker._progress_of("Getting composition") is None
    assert worker._progress_of("") is None


def test_phases_order_so_the_first_encoded_counts_as_progress():
    assert worker._progress_of("Encoded 0/60") > worker._progress_of("Rendered 60/60")
    assert worker._progress_of("Rendered 0/60") > worker._progress_of("Bundling 100%")


# ── The watcher, against real processes ────────────────────────────────────────

def _child(script: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-u", "-c", script], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(worker, "_POLL_SECS", 0.05)


def test_a_render_that_advances_is_left_alone(quick):
    proc = _child("import sys, time\n"
                  "for i in range(1, 6):\n"
                  "    print(f'Rendered {i}/5'); sys.stderr.write('chatter\\n'); time.sleep(0.15)\n"
                  "print('Encoded 5/5')")
    out, err, outcome = worker._wait_for_render(proc, timeout_secs=30, stall_secs=0.5)
    assert outcome == "exited" and proc.returncode == 0
    assert "Rendered 5/5" in out and "Encoded 5/5" in out
    assert err.count("chatter") == 5          # the second pipe was drained too


def test_a_render_whose_counter_stops_is_a_stall_even_if_it_keeps_printing(quick):
    proc = _child("import time\n"
                  "print('Rendered 8/60')\n"
                  "while True:\n"
                  "    print('Rendered 8/60'); time.sleep(0.1)")      # the real logs repeat a line
    out, _, outcome = worker._wait_for_render(proc, timeout_secs=30, stall_secs=0.6)
    assert outcome == "stall"
    assert out.count("Rendered 8/60") >= 2
    proc.kill(); proc.wait()


def test_the_ceiling_still_catches_a_render_that_crawls(quick):
    proc = _child("import time, itertools\n"
                  "for i in itertools.count(1):\n"
                  "    print(f'Rendered {i}/100000'); time.sleep(0.1)")
    _, _, outcome = worker._wait_for_render(proc, timeout_secs=0.7, stall_secs=30)
    assert outcome == "timeout"
    proc.kill(); proc.wait()


def test_a_big_stderr_cannot_deadlock_the_watcher(quick):
    proc = _child("import sys\n"
                  "sys.stderr.write('x' * 300000)\n"           # past any pipe buffer
                  "print('Rendered 1/1'); print('Encoded 1/1')")
    out, err, outcome = worker._wait_for_render(proc, timeout_secs=30, stall_secs=5)
    assert outcome == "exited" and len(err) == 300000 and "Encoded 1/1" in out


# ── A Cartoon 3D video needs the GPU ──────────────────────────────────────────

def _cartoon_job(tmp_path, monkeypatch, db_path, visual_style="cartoon_3d", cartoon_config=True):
    remotion_dir = tmp_path / "remotion"
    (remotion_dir / "public").mkdir(parents=True)
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(worker, "REMOTION_DIR", remotion_dir)
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(pipeline, "JOBS_DIR", tmp_path / "jobs")
    job = tmp_path / "jobs" / "vid-1"
    job.mkdir(parents=True)
    (job / "audio.mp3").write_bytes(b"x")
    (job / "timeline.json").write_text("{}")
    scenes = [{"src": "Cartoon3D", "source": "installed", "props": {}}] if cartoon_config else []
    (job / "scene-config.json").write_text(json.dumps({"scenes": scenes}))
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
                "voice_file_path, timeline_path, scene_config_path, visual_style, created_at, updated_at) "
                "VALUES ('vid-1', 'p', 't', 'manual', 8, 'RENDERING', 'a', 't', 's', ?, "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')", (visual_style,))
    con.commit()
    con.close()


def _video(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT status, render_fail_count FROM videos WHERE id = 'vid-1'").fetchone()
    comments = [r[0] for r in con.execute("SELECT content FROM comments WHERE video_id = 'vid-1'")]
    con.close()
    return dict(row), comments


def _store_probe(db_path, probe):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gpu_probe_result', ?)",
                (json.dumps(probe),))
    con.commit()
    con.close()


def _exited(stdout=""):
    proc = mock.MagicMock()
    proc.pid = 4242
    proc.args = ["npx", "remotion", "render"]
    proc.stdout = io.StringIO(stdout)
    proc.stderr = io.StringIO("")
    proc.poll.return_value = 0
    proc.returncode = 0
    return proc


def test_a_cartoon_video_without_a_working_gpu_fails_at_once_with_the_reason(db_path, monkeypatch, tmp_path):
    _cartoon_job(tmp_path, monkeypatch, db_path)
    _store_probe(db_path, {"configured": True, "ok": False, "error": "Chromium is rendering on another device: SwiftShader"})
    monkeypatch.setattr(worker, "_gpu_verified", False)
    with mock.patch("subprocess.Popen") as popen, mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._stage_and_render("vid-1")
    popen.assert_not_called()                 # no CPU fallback
    probe.assert_not_called()                 # the probe had answered: not_usable
    video, comments = _video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 0    # straight to FAILED, the retry counter untouched
    assert "renders on the GPU only" in comments[-1] and "not_usable" in comments[-1]
    assert "SwiftShader" in comments[-1] and "Test GPU" in comments[-1]


def test_an_unprobed_gpu_is_probed_before_judging(db_path, monkeypatch, tmp_path):
    """After every worker restart the probe has not run yet; a Cartoon 3D
    video claimed first triggers it rather than being failed on no evidence."""
    _cartoon_job(tmp_path, monkeypatch, db_path)
    monkeypatch.setattr(worker, "_gpu_verified", False)

    def probe(reason):
        _store_probe(db_path, {"configured": True, "ok": True})
        monkeypatch.setattr(worker, "_gpu_verified", True)
        return {}
    monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-1")
    with mock.patch("subprocess.Popen", return_value=_exited()) as popen, \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe) as ran, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    assert ran.call_args.kwargs["reason"] == "a Cartoon 3D video needs the GPU"
    argv = popen.call_args.args[0]
    assert "--concurrency=2" in argv and "--gl=angle-egl" in argv


def test_a_cartoon_scene_config_counts_even_under_auto(db_path, monkeypatch, tmp_path):
    """What renders is the written scene-config, so an auto video whose agent
    settled on a world is gated by the file, not only by the style column."""
    _cartoon_job(tmp_path, monkeypatch, db_path, visual_style="auto")
    _store_probe(db_path, {"configured": False, "ok": False})
    monkeypatch.setattr(worker, "_gpu_verified", False)
    with mock.patch("subprocess.Popen") as popen:
        worker._stage_and_render("vid-1")
    popen.assert_not_called()
    video, comments = _video(db_path)
    assert video["status"] == "FAILED" and "not_configured" in comments[-1]


def test_an_ordinary_video_renders_on_the_cpu_as_before(db_path, monkeypatch, tmp_path):
    _cartoon_job(tmp_path, monkeypatch, db_path, visual_style="auto", cartoon_config=False)
    monkeypatch.setattr(worker, "_gpu_verified", False)
    with mock.patch("subprocess.Popen", return_value=_exited()) as popen, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    argv = popen.call_args.args[0]
    assert "--concurrency=2" not in argv
    assert _video(db_path)[0]["status"] == "RENDERING"   # success handling was stubbed out


# ── The AI review's contract ───────────────────────────────────────────────────

def test_the_review_is_told_what_cartoon_3d_looks_like():
    import ai_review
    block = ai_review._register_block("dark", figures=True, line_art=False, cartoon_3d=True)
    assert "Cartoon 3D" in block and "ink outlines" in block and "depth-of-field" in block
    assert "DISCRETE" not in block           # the DOM figure clauses do not apply
    assert ai_review._register_block("dark", figures=True) == ai_review._register_block("dark", figures=True, cartoon_3d=False)
