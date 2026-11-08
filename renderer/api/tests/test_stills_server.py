"""The worker's stills server (TMDEV-179): the child process that renders the
MCP container's Cartoon 3D stills on this container's GL path. Started after
the startup probe, started again when it dies or when the GL path flips, and
never in a tight loop."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import worker  # noqa: E402


class _Proc:
    def __init__(self, argv, **kw):
        self.argv, self.kw, self.pid, self.returncode = argv, kw, 4242, None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def server(monkeypatch):
    started = []
    monkeypatch.setattr(worker, "STILLS_SERVER_PORT", 4455)
    monkeypatch.setattr(worker.subprocess, "Popen", lambda argv, **kw: started.append(_Proc(argv, **kw)) or started[-1])
    monkeypatch.setattr(worker.os, "killpg", lambda *a: None)
    monkeypatch.setattr(worker.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(worker, "_stills_proc", None)
    monkeypatch.setattr(worker, "_stills_on_gpu", None)
    monkeypatch.setattr(worker, "_stills_started_at", 0.0)
    monkeypatch.setattr(worker, "_gpu_verified", False)
    monkeypatch.delenv("TUBEMATIC_GPU_UUID", raising=False)
    return started


def _gpu(monkeypatch):
    monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-1")
    monkeypatch.setenv("TUBEMATIC_GPU_NAME", "NVIDIA Test")
    monkeypatch.setattr(worker, "_gpu_verified", True)


def test_the_cpu_argv_is_the_cpu_render_options_served_from_the_jobs_volume():
    argv, env = worker._stills_server_argv(on_gpu=False)
    assert argv[:2] == ["node", worker.STILLS_SERVER_SCRIPT]
    flags = dict(zip(argv[2::2], argv[3::2]))
    assert flags["--host"] == "0.0.0.0" and flags["--public"] == worker.JOBS_DIR
    assert flags["--gl"] == worker.CPU_GL_OPTIONS["gl"] and flags["--chrome-mode"] == worker.CPU_GL_OPTIONS["chromeMode"]
    assert "--browser-executable" not in flags and env == {}


def test_the_gpu_argv_is_the_gpu_render_options_and_their_environment():
    argv, env = worker._stills_server_argv(on_gpu=True)
    flags = dict(zip(argv[2::2], argv[3::2]))
    assert flags["--gl"] == "angle-egl" and flags["--chrome-mode"] == "chrome-for-testing"
    assert flags["--multiprocess"] == "1" and flags["--browser-executable"] == worker.CHROMIUM_BIN
    assert env == worker.GPU_GL_ENV


def test_it_starts_once_on_the_current_path_and_stays(server):
    worker._ensure_stills_server(now=100.0)
    worker._ensure_stills_server(now=101.0)
    assert len(server) == 1
    assert server[0].kw["cwd"] == str(worker.REMOTION_DIR) and server[0].kw["start_new_session"] is True
    assert "--gl" in server[0].argv and server[0].argv[server[0].argv.index("--gl") + 1] == "swangle"


def test_a_passing_probe_moves_it_onto_the_gpu(server, monkeypatch):
    worker._ensure_stills_server(now=100.0)
    _gpu(monkeypatch)
    worker._ensure_stills_server(now=101.0)
    assert len(server) == 2
    assert server[1].argv[server[1].argv.index("--gl") + 1] == "angle-egl"
    assert server[1].kw["env"]["__EGL_VENDOR_LIBRARY_FILENAMES"] == worker.GPU_GL_ENV["__EGL_VENDOR_LIBRARY_FILENAMES"]


def test_a_dead_server_is_started_again_after_the_retry_interval(server):
    worker._ensure_stills_server(now=100.0)
    server[0].returncode = 1
    worker._ensure_stills_server(now=110.0)         # too soon on the same path: no tight loop
    assert len(server) == 1
    worker._ensure_stills_server(now=100.0 + worker.STILLS_SERVER_RETRY_SECS)
    assert len(server) == 2


def test_no_port_means_no_server(server, monkeypatch):
    monkeypatch.setattr(worker, "STILLS_SERVER_PORT", 0)
    worker._ensure_stills_server(now=100.0)
    assert server == []


def test_a_server_that_cannot_start_never_raises(server, monkeypatch):
    def boom(*a, **k):
        raise OSError("no node")
    monkeypatch.setattr(worker.subprocess, "Popen", boom)
    worker._ensure_stills_server(now=100.0)
    assert worker._stills_proc is None
