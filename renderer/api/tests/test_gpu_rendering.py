"""GPU rendering in the worker and its two API routes (TMDEV-178).

The rule every test here protects: the GPU is used only after a probe, run
with a render's exact flags, showed Chromium's WebGL renderer string naming
the configured NVIDIA GPU. "The render finished" is never evidence — on the
wrong GL device it finishes too, just slowly. Anything short of that renders
on the CPU, and a broken GPU never fails a video.

Run from renderer/api/: pytest tests/test_gpu_rendering.py
"""
import json
import os
import signal
import sqlite3
import subprocess
import unittest.mock as mock

import pytest
from flask import Flask

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
import worker

NVIDIA = "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL ES 3.2)"
# Measured in this image (Plane TMDEV-178): the CPU default, and what an
# integrated GPU / Mesa reports. Each must be refused when a GPU is configured.
SWIFTSHADER = ("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), "
               "SwiftShader driver)")
INTEL = "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL ES 3.2)"
LLVMPIPE = "ANGLE (Mesa, llvmpipe (LLVM 15.0.6, 256 bits), OpenGL 4.5)"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = str(tmp_path / "test.db")
    pipeline._init_db(p)
    monkeypatch.setattr(worker, "DB_PATH", p)
    return p


@pytest.fixture(autouse=True)
def no_gpu(monkeypatch):
    """Every test starts unconfigured and unverified."""
    for var in ("TUBEMATIC_GPU_UUID", "TUBEMATIC_GPU_NAME", "TUBEMATIC_HOST_GPUS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(worker, "_gpu_verified", False)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-aaaa")
    monkeypatch.setenv("TUBEMATIC_GPU_NAME", "NVIDIA GeForce GTX 1650")
    monkeypatch.setenv("TUBEMATIC_HOST_GPUS", json.dumps(
        [{"index": 0, "uuid": "GPU-aaaa", "name": "NVIDIA GeForce GTX 1650",
          "memory_mib": 4096, "driver": "595.91.07"}]))


def _answer(renderer=None, webgl=True, error=None):
    """What the probe driver writes to its output file."""
    body = {"webgl": webgl}
    if renderer:
        body.update(renderer=renderer, vendor="Google Inc.")
    if error:
        body["error"] = error
    return body


def _popen(stdout="", stderr="", returncode=0):
    proc = mock.MagicMock()
    proc.pid = 4242
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    return proc


def _driver(answer, stderr=""):
    """A Popen stand-in for the probe driver: on communicate() it writes
    `answer` to the outputPath named in its JSON config, as the real one does.
    `answer=None` writes nothing (a driver that died)."""
    calls = []

    def factory(argv, **kw):
        calls.append((argv, kw))
        proc = _popen(stderr=stderr)

        def communicate(timeout=None):
            if answer is not None:
                with open(json.loads(argv[2])["outputPath"], "w") as f:
                    json.dump(answer, f)
            return "", stderr
        proc.communicate.side_effect = communicate
        return proc
    factory.calls = calls
    return factory


def _stored(db_path):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT value FROM settings WHERE key = ?",
                      (pipeline.GPU_PROBE_RESULT_KEY,)).fetchone()
    con.close()
    return json.loads(row[0]) if row else None


def _probe(db_path, answer, smi_ok=True, stderr=""):
    smi = mock.MagicMock(returncode=0, stdout="NVIDIA GeForce GTX 1650, 595.91.07, 4096\n", stderr="")
    if not smi_ok:
        smi = mock.MagicMock(returncode=9, stdout="", stderr="no devices")
    driver = _driver(answer, stderr=stderr)
    with mock.patch("subprocess.Popen", side_effect=driver), \
         mock.patch("subprocess.run", return_value=smi):
        result = worker._run_gpu_probe(reason="test")
    return result, driver


# ── The flags ────────────────────────────────────────────────────────────────

def test_the_cpu_path_adds_nothing_to_a_render():
    """remotion.config.ts's swangle applies, and a CPU render's command is what
    it always was. In particular no chrome-for-testing mode: new headless in
    software is about 5x slower (measured)."""
    assert worker._gl_args(False) == ([], {})


def test_the_gpu_path_is_all_the_settings_and_names_the_browser():
    argv, env = worker._gl_args(True)
    assert argv == ["--gl=angle-egl", "--chrome-mode=chrome-for-testing",
                    "--enable-multiprocess-on-linux", "--browser-executable=/usr/bin/chromium"]
    assert env == {"__EGL_VENDOR_LIBRARY_FILENAMES":
                   "/usr/share/glvnd/egl_vendor.d/10_nvidia.json"}


def test_the_browser_flag_is_the_one_remotion_reads():
    """--browser-executable-path, which renders have always passed, is not a
    Remotion CLI flag and is silently ignored — the GPU path must not rely on
    it (measured: Remotion downloaded its own browser instead)."""
    assert not any(a.startswith("--browser-executable-path") for a in worker._gl_args(True)[0])


def test_the_cpu_options_are_what_remotion_config_sets():
    """The probe driver uses the Node API, which ignores remotion.config.ts, so
    the CPU options spell out what the config gives a CPU render."""
    import pathlib
    config = (pathlib.Path(worker.__file__).resolve().parent.parent / "remotion"
              / "remotion.config.ts").read_text()
    assert f'setChromiumOpenGlRenderer("{worker.CPU_GL_OPTIONS["gl"]}")' in config


def test_unconfigured_never_renders_on_the_gpu(monkeypatch):
    monkeypatch.setattr(worker, "_gpu_verified", True)
    assert worker._render_on_gpu() is False


def test_configured_but_unprobed_renders_on_the_cpu(configured):
    assert worker._render_on_gpu() is False


def test_configured_and_verified_renders_on_the_gpu(configured, monkeypatch):
    monkeypatch.setattr(worker, "_gpu_verified", True)
    assert worker._render_on_gpu() is True


# ── Judging the renderer string ──────────────────────────────────────────────

def test_the_configured_nvidia_gpu_passes():
    assert worker._judge_probe({"webgl": True, "renderer": NVIDIA},
                               "NVIDIA GeForce GTX 1650") == (True, "")


@pytest.mark.parametrize("renderer", [SWIFTSHADER, INTEL, LLVMPIPE])
def test_any_other_device_fails_even_though_it_rendered(renderer):
    ok, why = worker._judge_probe({"webgl": True, "renderer": renderer},
                                  "NVIDIA GeForce GTX 1650")
    assert not ok and renderer in why


def test_a_different_nvidia_gpu_than_the_configured_one_fails():
    ok, why = worker._judge_probe({"webgl": True, "renderer": NVIDIA}, "NVIDIA GeForce RTX 4090")
    assert not ok and "RTX 4090" in why


def test_no_webgl_context_fails():
    """What GPU flags produce in a container that got no GPU (measured)."""
    ok, why = worker._judge_probe({"webgl": False, "error": "no context"}, "x")
    assert not ok and why == "no context"


def test_no_probe_answer_fails():
    assert worker._judge_probe(None, "x")[0] is False


# ── The probe ────────────────────────────────────────────────────────────────

def test_a_passing_probe_verifies_the_gpu_and_stores_the_result(db_path, configured):
    result, _ = _probe(db_path, _answer(NVIDIA))
    assert result["ok"] is True and worker._gpu_verified is True
    stored = _stored(db_path)
    assert stored["renderer"] == NVIDIA and stored["configured"] is True
    assert stored["smi"] == {"name": "NVIDIA GeForce GTX 1650", "driver": "595.91.07",
                             "memory_mib": 4096}
    assert [g["uuid"] for g in stored["host_gpus"]] == ["GPU-aaaa"]


def test_the_probe_runs_with_exactly_the_options_a_render_gets(db_path, configured):
    """Old headless passes a one-tab probe but fails a real multi-tab three.js
    render (measured) — a probe on different options proves nothing."""
    _, driver = _probe(db_path, _answer(NVIDIA))
    [(argv, kw)] = driver.calls
    assert argv[:2] == ["node", worker.GPU_PROBE_DRIVER]
    config = json.loads(argv[2])
    options, env = worker._gl_options(True)
    assert {k: config[k] for k in options} == options
    for key, value in env.items():
        assert kw["env"][key] == value


def test_the_probe_uses_its_own_entry_not_the_scene_bundle():
    """One broken agent-written scene breaks the main bundle; through it, that
    would read as a broken GPU."""
    import pathlib
    driver = (pathlib.Path(worker.__file__).resolve().parent.parent / "remotion"
              / worker.GPU_PROBE_DRIVER).read_text()
    assert '"src", "gpu-probe", "index.ts"' in driver
    assert "TUBEMATIC_GPU_PROBE" in driver


def test_the_driver_output_file_is_removed(db_path, configured, tmp_path):
    _, driver = _probe(db_path, _answer(NVIDIA))
    out = json.loads(driver.calls[0][0][2])["outputPath"]
    assert not os.path.exists(out)


@pytest.mark.parametrize("renderer", [SWIFTSHADER, INTEL, LLVMPIPE])
def test_a_probe_on_the_wrong_device_leaves_rendering_on_the_cpu(db_path, configured, renderer):
    result, _ = _probe(db_path, _answer(renderer))
    assert result["ok"] is False and worker._gpu_verified is False
    assert worker._render_on_gpu() is False
    assert _stored(db_path)["renderer"] == renderer


def test_a_failing_probe_withdraws_an_earlier_verification(db_path, configured, monkeypatch):
    """A GPU that broke after start (a driver update) must stop being used."""
    monkeypatch.setattr(worker, "_gpu_verified", True)
    _probe(db_path, None, stderr="Error: something went wrong")
    assert worker._gpu_verified is False


def test_unconfigured_probes_on_the_cpu_path_and_reports_what_it_got(db_path):
    """The dashboard's Test button on a CPU install shows SwiftShader."""
    result, driver = _probe(db_path, _answer(SWIFTSHADER))
    config = json.loads(driver.calls[0][0][2])
    assert config["gl"] == "swangle" and config["chromeMode"] == "headless-shell"
    assert "__EGL_VENDOR_LIBRARY_FILENAMES" not in driver.calls[0][1]["env"]
    assert result["configured"] is False and result["renderer"] == SWIFTSHADER
    assert result["error"] == ""
    assert worker._gpu_verified is False


def test_a_driver_that_dies_says_why(db_path, configured):
    result, _ = _probe(db_path, None, stderr="Error: Cannot find module '@remotion/bundler'")
    assert result["ok"] is False and "Cannot find module" in result["error"]


def test_a_render_error_inside_the_driver_is_reported(db_path):
    result, _ = _probe(db_path, _answer(webgl=False, error="the probe could not render: boom"))
    assert result["error"] == "the probe could not render: boom"


def test_a_probe_that_hangs_is_killed_with_its_whole_process_group(db_path, configured):
    proc = mock.MagicMock()
    proc.pid = 4242
    proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=180)
    with mock.patch("subprocess.Popen", return_value=proc), \
         mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=9, stdout="", stderr="")), \
         mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg") as killpg, \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        result = worker._run_gpu_probe(reason="test")
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    assert result["ok"] is False and "did not finish" in result["error"]


def test_a_probe_that_cannot_start_never_raises(db_path, configured):
    with mock.patch("subprocess.Popen", side_effect=FileNotFoundError("npx")):
        result = worker._run_gpu_probe(reason="test")
    assert result["ok"] is False and "could not run" in result["error"]
    assert _stored(db_path) is not None


# ── Requests from the dashboard ──────────────────────────────────────────────

def _request(db_path, at):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (pipeline.GPU_PROBE_REQUEST_KEY, at))
    con.commit()
    con.close()


def test_a_request_newer_than_the_last_probe_runs_one(db_path):
    _request(db_path, "2026-11-05T10:00:00.000002Z")
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                (pipeline.GPU_PROBE_RESULT_KEY, json.dumps({"at": "2026-11-05T10:00:00.000001Z"})))
    con.commit()
    con.close()
    with mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._sweep_gpu_probe()
    probe.assert_called_once()


def test_a_request_already_answered_runs_nothing(db_path):
    _request(db_path, "2026-11-05T10:00:00.000001Z")
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                (pipeline.GPU_PROBE_RESULT_KEY, json.dumps({"at": "2026-11-05T10:00:00.000002Z"})))
    con.commit()
    con.close()
    with mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._sweep_gpu_probe()
    probe.assert_not_called()


def test_no_request_runs_nothing(db_path):
    with mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._sweep_gpu_probe()
    probe.assert_not_called()


# ── The render ───────────────────────────────────────────────────────────────

def _job(tmp_path, monkeypatch, db_path):
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
    (job / "scene-config.json").write_text('{"scenes": []}')
    con = sqlite3.connect(db_path)
    # The columns only have to say each file was written; paths come from the id.
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
                "voice_file_path, timeline_path, scene_config_path, created_at, updated_at) "
                "VALUES ('vid-1', 'p', 't', 'manual', 8, 'RENDERING', 'a', 't', 's', "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()


def test_a_verified_gpu_render_gets_the_gpu_flags(db_path, configured, monkeypatch, tmp_path):
    _job(tmp_path, monkeypatch, db_path)
    monkeypatch.setattr(worker, "_gpu_verified", True)
    with mock.patch("subprocess.Popen", return_value=_popen()) as popen, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    assert "--gl=angle-egl" in popen.call_args.args[0]
    assert popen.call_args.kwargs["env"]["__EGL_VENDOR_LIBRARY_FILENAMES"].endswith("10_nvidia.json")


def test_an_unverified_gpu_render_gets_no_gpu_flags(db_path, configured, monkeypatch, tmp_path):
    _job(tmp_path, monkeypatch, db_path)
    with mock.patch("subprocess.Popen", return_value=_popen()) as popen, \
         mock.patch.object(worker, "_handle_render_success"):
        worker._stage_and_render("vid-1")
    argv = popen.call_args.args[0]
    assert not any(a.startswith(("--gl", "--chrome-mode")) for a in argv)
    assert "__EGL_VENDOR_LIBRARY_FILENAMES" not in popen.call_args.kwargs["env"]


def test_a_failed_gpu_render_retests_the_gpu(db_path, configured, monkeypatch, tmp_path):
    """So the next render falls back to the CPU if the GPU is what broke."""
    _job(tmp_path, monkeypatch, db_path)
    monkeypatch.setattr(worker, "_gpu_verified", True)
    with mock.patch("subprocess.Popen", return_value=_popen(stderr="boom", returncode=1)), \
         mock.patch.object(worker, "_handle_render_failure"), \
         mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._stage_and_render("vid-1")
    probe.assert_called_once()


def test_a_failed_cpu_render_does_not_probe(db_path, monkeypatch, tmp_path):
    _job(tmp_path, monkeypatch, db_path)
    with mock.patch("subprocess.Popen", return_value=_popen(stderr="boom", returncode=1)), \
         mock.patch.object(worker, "_handle_render_failure"), \
         mock.patch.object(worker, "_run_gpu_probe") as probe:
        worker._stage_and_render("vid-1")
    probe.assert_not_called()


# ── GET /render/gpu, POST /render/gpu/test ───────────────────────────────────

@pytest.fixture
def client(db_path):
    os.environ["TUBEMATIC_DB"] = db_path
    app = Flask(__name__)
    app.register_blueprint(pipeline.create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _store(db_path, key, value):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    con.commit()
    con.close()


def test_before_any_probe_the_status_is_unknown(client):
    body = client.get("/render/gpu").get_json()
    assert body["status"] == "unknown" and body["rendering_on"] == "cpu"
    assert body["probe"] is None and body["pending"] is False


@pytest.mark.parametrize("probe,status,on", [
    ({"configured": False, "ok": False, "renderer": SWIFTSHADER}, "not_configured", "cpu"),
    ({"configured": True, "ok": True, "renderer": NVIDIA}, "working", "gpu"),
    ({"configured": True, "ok": False, "renderer": INTEL}, "not_usable", "cpu"),
])
def test_the_status_follows_the_last_probe(client, db_path, probe, status, on):
    _store(db_path, pipeline.GPU_PROBE_RESULT_KEY, json.dumps({"at": "2026-11-05T10:00:00.0Z", **probe}))
    body = client.get("/render/gpu").get_json()
    assert body["status"] == status and body["rendering_on"] == on


def test_a_test_request_is_pending_until_a_newer_probe(client, db_path):
    _store(db_path, pipeline.GPU_PROBE_RESULT_KEY,
           json.dumps({"at": "2000-01-01T00:00:00.000000Z", "configured": False}))
    r = client.post("/render/gpu/test")
    assert r.status_code == 202
    assert r.get_json()["pending"] is True
    _store(db_path, pipeline.GPU_PROBE_RESULT_KEY,
           json.dumps({"at": "2999-01-01T00:00:00.000000Z", "configured": False}))
    assert client.get("/render/gpu").get_json()["pending"] is False


def test_a_pending_request_says_it_waits_for_a_render(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
                "created_at, updated_at) VALUES ('v', 'p', 't', 'manual', 8, 'RENDERING', "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    body = client.post("/render/gpu/test").get_json()
    assert body["pending"] is True and body["waiting_for_render"] is True


def test_the_two_processes_agree_on_the_row_names():
    """worker.py writes what pipeline.py reads; onboard/gpu.py reads it too."""
    assert worker.GPU_PROBE_RESULT_KEY == pipeline.GPU_PROBE_RESULT_KEY == "gpu_probe_result"
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[3] / "onboard" / "gpu.py").read_text()
    assert 'PROBE_RESULT_KEY = "gpu_probe_result"' in src
    # onboard.py --step gpu writes the hold that worker.py::_claim_next reads.
    assert pipeline.RENDER_CLAIM_HOLD_KEY == "render_claim_hold_until"
    assert 'RENDER_HOLD_KEY = "render_claim_hold_until"' in src


def test_a_malformed_driver_answer_is_no_answer(db_path, configured):
    result, _ = _probe(db_path, [1, 2])
    assert result["ok"] is False and result["error"].startswith("the probe produced no result")
