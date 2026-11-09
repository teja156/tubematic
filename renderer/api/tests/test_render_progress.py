"""The render watcher (TMDEV-179): Remotion's progress counters decide whether a
render is alive, and a Cartoon 3D or mascot video renders on the GPU or not at
all. A mascot video renders the mascot version it was written for.

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
    (job / "timeline.json").write_text(json.dumps({"totalFrames": 10, "fps": 30, "words": []}))
    scenes = ([{"type": "generated", "src": "vid-1/CartoonShort", "props": {"cartoon3d": {"beats": [{"start": 0, "end": 9, "shot": "x"}]}}}]
              if cartoon_config else [])
    (job / "scene-config.json").write_text(json.dumps({"scenes": scenes}))
    if cartoon_config:
        # the generated source and the record of it submit_render wrote: the worker renders that tree or nothing
        from tubematic_core import jobfiles as tjobs
        generated = tmp_path / "generated"
        (generated / "vid-1").mkdir(parents=True)
        (generated / "vid-1" / "CartoonShort.tsx").write_text("export default () => null;")
        monkeypatch.setattr(worker, "GENERATED_DIR", generated)
        (job / "cartoon").mkdir()
        (job / "cartoon" / "source.json").write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(generated / "vid-1"), "at": "now"}))
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
    # a fresh fake process per call: the segmented render starts one per attempt
    with mock.patch("subprocess.Popen", side_effect=lambda *a, **k: _exited()) as popen, \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe) as ran, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    assert ran.call_args_list[0].kwargs["reason"] == "a Cartoon 3D video needs the GPU"
    # the first segment of the segmented render (TMDEV-185), on the GPU flags, two tabs, video only
    argv = popen.call_args_list[0].args[0]
    assert "--concurrency=2" in argv and "--gl=angle-egl" in argv
    assert "--frames=0-9" in argv and "--muted" in argv


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


# ── A mascot video needs the GPU, and renders the version it was written for ─────

def _mascot_job(tmp_path, monkeypatch, db_path, mascot_version=1, versions=None, approved=1):
    """An ordinary (DOM) video with mascot `m1` pinned at `mascot_version`.
    `versions` maps a version number to its stored drawing code."""
    _cartoon_job(tmp_path, monkeypatch, db_path, visual_style="auto", cartoon_config=False)
    (tmp_path / "jobs" / "vid-1" / "scene-config.json").write_text(json.dumps(
        {"scenes": [], "mascot": [{"frame": 0, "on": True, "x": 0.5, "y": 0.9}]}))
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO mascots (id, name, status, approved_version) VALUES ('m1', 'M', 'READY', ?)", (approved,))
    for v, code in (versions if versions is not None else {1: "window.MASCOT = () => {}; // v1"}).items():
        con.execute("INSERT INTO mascot_versions (mascot_id, version, code) VALUES ('m1', ?, ?)", (v, code))
    con.execute("UPDATE videos SET mascot_id = 'm1', mascot_version = ? WHERE id = 'vid-1'", (mascot_version,))
    con.commit()
    con.close()


def _working_gpu(db_path, monkeypatch):
    _store_probe(db_path, {"configured": True, "ok": True})
    monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-1")
    monkeypatch.setattr(worker, "_gpu_verified", True)


def _props(popen):
    argv = popen.call_args.args[0]
    return json.loads(argv[argv.index("--props") + 1])


def test_a_mascot_video_without_a_working_gpu_fails_at_once_with_the_reason(db_path, monkeypatch, tmp_path):
    """The same policy as Cartoon 3D: a mascot on the CPU would take hours,
    so there is no fallback and no retry, and the comment says why."""
    _mascot_job(tmp_path, monkeypatch, db_path)
    _store_probe(db_path, {"configured": True, "ok": False, "error": "Chromium is rendering on another device: SwiftShader"})
    with mock.patch("subprocess.Popen") as popen, mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._stage_and_render("vid-1")
    popen.assert_not_called()
    probe.assert_not_called()
    video, comments = _video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 0
    assert "has a mascot, which renders on the GPU only" in comments[-1]
    assert "not_usable" in comments[-1] and "SwiftShader" in comments[-1] and "Test GPU" in comments[-1]
    assert "Cartoon 3D" not in comments[-1]


def test_a_mascot_video_on_an_unprobed_gpu_is_probed_before_judging(db_path, monkeypatch, tmp_path):
    _mascot_job(tmp_path, monkeypatch, db_path)

    def probe(reason):
        _store_probe(db_path, {"configured": False, "ok": False})
        return {}
    with mock.patch("subprocess.Popen") as popen, \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe) as ran:
        worker._stage_and_render("vid-1")
    assert ran.call_args.kwargs["reason"] == "a mascot video needs the GPU"
    popen.assert_not_called()
    video, comments = _video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 0
    assert "not_configured" in comments[-1]


def test_the_locked_mascot_version_is_staged_even_after_a_newer_one_is_approved(db_path, monkeypatch, tmp_path):
    """A video renders the drawing it was authored against: approving v2
    while the video is in flight must not change what it shows."""
    _mascot_job(tmp_path, monkeypatch, db_path, mascot_version=1, approved=2,
                versions={1: "window.MASCOT = () => {}; // v1", 2: "window.MASCOT = () => {}; // v2"})
    _working_gpu(db_path, monkeypatch)
    with mock.patch("subprocess.Popen", return_value=_exited()) as popen, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    staged = tmp_path / "remotion" / "public" / "vid-1" / "mascot.js"
    assert staged.read_text() == "window.MASCOT = () => {}; // v1"
    props = _props(popen)
    assert props["mascotPath"] == "/public/vid-1/mascot.js"
    assert "--gl=angle-egl" in popen.call_args.args[0]


def test_a_video_without_a_mascot_gets_no_mascot_path(db_path, monkeypatch, tmp_path):
    _cartoon_job(tmp_path, monkeypatch, db_path, visual_style="auto", cartoon_config=False)
    with mock.patch("subprocess.Popen", return_value=_exited()) as popen, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    assert "mascotPath" not in _props(popen)
    assert not (tmp_path / "remotion" / "public" / "vid-1" / "mascot.js").exists()


def test_a_mascot_with_no_pinned_version_fails_with_a_comment(db_path, monkeypatch, tmp_path):
    _mascot_job(tmp_path, monkeypatch, db_path, mascot_version=0)
    _working_gpu(db_path, monkeypatch)
    with mock.patch("subprocess.Popen") as popen:
        worker._stage_and_render("vid-1")
    popen.assert_not_called()
    video, comments = _video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 0
    assert "m1" in comments[-1] and "version" in comments[-1]


def test_a_mascot_version_with_no_code_fails_with_a_comment(db_path, monkeypatch, tmp_path):
    _mascot_job(tmp_path, monkeypatch, db_path, mascot_version=3)
    _working_gpu(db_path, monkeypatch)
    with mock.patch("subprocess.Popen") as popen:
        worker._stage_and_render("vid-1")
    popen.assert_not_called()
    video, comments = _video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 0
    assert "has no version 3" in comments[-1]


# ── A GPU-only video whose render fails: the GPU is tested before the agent is told ─

def _failed_proc():
    proc = _exited()
    proc.stderr = io.StringIO("Error: WebGL context lost\n")
    proc.returncode = 1
    return proc


def _probe_answers(db_path, monkeypatch, working):
    """A probe that records the video's status when it ran, then answers."""
    seen = []

    def probe(reason):
        seen.append((reason, _video(db_path)[0]["status"]))
        _store_probe(db_path, {"configured": True, "ok": working,
                               "error": "" if working else "Chromium is rendering on another device: SwiftShader"})
        monkeypatch.setattr(worker, "_gpu_verified", working)
        return {}
    return seen, probe


def _assert_failed_for_the_gpu(db_path, seen, what):
    assert seen and seen[0][1] == "RENDERING"          # tested before the status moved
    video, comments = _video(db_path)
    assert video["status"] == "FAILED"
    assert video["render_fail_count"] == 0             # no retry spent, no agent handed it
    assert f"{what}, which renders on the GPU only" in comments[-1]
    assert "not_usable" in comments[-1] and "SwiftShader" in comments[-1]
    assert "Test GPU" in comments[-1] and "--step gpu" in comments[-1]
    assert comments[-1].startswith("Render failed, moved to FAILED")
    assert len(comments) == 1


def test_a_mascot_render_that_fails_on_a_gpu_that_stopped_working_goes_straight_to_failed(db_path, monkeypatch, tmp_path):
    _mascot_job(tmp_path, monkeypatch, db_path)
    _working_gpu(db_path, monkeypatch)
    seen, probe = _probe_answers(db_path, monkeypatch, working=False)
    with mock.patch("subprocess.Popen", return_value=_failed_proc()), \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe), \
         mock.patch.object(worker, "_handle_render_failure") as handled:
        worker._stage_and_render("vid-1")
    handled.assert_not_called()
    assert seen[0][0] == "a render on the GPU failed"
    _assert_failed_for_the_gpu(db_path, seen, "has a mascot")


def test_a_mascot_render_that_hangs_on_a_gpu_that_stopped_working_goes_straight_to_failed(db_path, monkeypatch, tmp_path):
    _mascot_job(tmp_path, monkeypatch, db_path)
    _working_gpu(db_path, monkeypatch)
    seen, probe = _probe_answers(db_path, monkeypatch, working=False)
    with mock.patch("subprocess.Popen", return_value=_exited()), \
         mock.patch.object(worker, "_wait_for_render", return_value=("", "", "stall")), \
         mock.patch.object(worker, "_kill_group_and_reap"), \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe):
        worker._stage_and_render("vid-1")
    _assert_failed_for_the_gpu(db_path, seen, "has a mascot")


@pytest.mark.parametrize("outcome", ["failed", "hung"])
def test_a_cartoon_render_that_fails_on_a_gpu_that_stopped_working_goes_straight_to_failed(db_path, monkeypatch, tmp_path, outcome):
    _cartoon_job(tmp_path, monkeypatch, db_path)
    _working_gpu(db_path, monkeypatch)
    seen, probe = _probe_answers(db_path, monkeypatch, working=False)
    with mock.patch.object(worker, "_render_cartoon", return_value=(outcome, "segment 1 died")), \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe):
        worker._stage_and_render("vid-1")
    assert seen[0][0] == "a Cartoon 3D render on the GPU " + ("stalled" if outcome == "hung" else "failed")
    _assert_failed_for_the_gpu(db_path, seen, "is Cartoon 3D")


@pytest.mark.parametrize("kind", ["mascot", "cartoon"])
def test_a_gpu_only_render_failing_on_a_gpu_that_still_works_is_the_videos_own_failure(db_path, monkeypatch, tmp_path, kind):
    """The negative control: the GPU passed its re-test, so the failure goes the usual way."""
    (_mascot_job if kind == "mascot" else _cartoon_job)(tmp_path, monkeypatch, db_path)
    _working_gpu(db_path, monkeypatch)
    seen, probe = _probe_answers(db_path, monkeypatch, working=True)
    with mock.patch("subprocess.Popen", return_value=_failed_proc()), \
         mock.patch.object(worker, "_render_cartoon", return_value=("failed", "segment 1 died")), \
         mock.patch.object(worker, "_run_gpu_probe", side_effect=probe):
        worker._stage_and_render("vid-1")
    assert len(seen) == 1
    video, comments = _video(db_path)
    assert video["status"] == "REVISION_REQUESTED" and video["render_fail_count"] == 1
    assert comments[-1].startswith("Render failed:") and "GPU only" not in comments[-1]


# ── A Cartoon 3D video holding a mascot: refused, never silently dropped ─────────

def test_a_cartoon_video_that_holds_a_mascot_fails_rather_than_dropping_it(db_path, monkeypatch, tmp_path):
    from tubematic_core import mascots as tmascots
    _cartoon_job(tmp_path, monkeypatch, db_path)
    _working_gpu(db_path, monkeypatch)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET mascot_id = 'tubi', mascot_version = 1 WHERE id = 'vid-1'")
    con.commit()
    con.close()
    with mock.patch("subprocess.Popen") as popen, mock.patch.object(worker, "_render_cartoon") as cartoon:
        worker._stage_and_render("vid-1")
    popen.assert_not_called()
    cartoon.assert_not_called()
    video, comments = _video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 0
    assert tmascots.MASCOT_NOT_ON_CARTOON_3D in comments[-1] and "tubi" in comments[-1]


# ── The AI review's contract ───────────────────────────────────────────────────

def test_the_review_is_told_what_cartoon_3d_looks_like():
    import ai_review
    block = ai_review._register_block("dark", figures=True, line_art=False, cartoon_3d=True)
    assert "Cartoon 3D" in block and "ink outlines" in block and "depth-of-field" in block
    assert "DISCRETE" not in block           # the DOM figure clauses do not apply
    assert ai_review._register_block("dark", figures=True) == ai_review._register_block("dark", figures=True, cartoon_3d=False)
