"""The renderer's stills server (TMDEV-179): the child process that renders the
MCP container's Cartoon 3D stills on this container's GL path. Started after
the startup probe, started again when it dies or when the GL path flips, and
never in a tight loop. The built-in renderer only: it serves the shared /jobs
volume, which a remote renderer does not have."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render_agent  # noqa: E402


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
    monkeypatch.setattr(render_agent, "STILLS_SERVER_PORT", 4455)
    monkeypatch.setattr(render_agent.subprocess, "Popen", lambda argv, **kw: started.append(_Proc(argv, **kw)) or started[-1])
    monkeypatch.setattr(render_agent.os, "killpg", lambda *a: None)
    monkeypatch.setattr(render_agent.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(render_agent, "_stills_proc", None)
    monkeypatch.setattr(render_agent, "_stills_on_gpu", None)
    monkeypatch.setattr(render_agent, "_stills_started_at", 0.0)
    monkeypatch.setattr(render_agent, "_gpu_verified", False)
    monkeypatch.delenv("TUBEMATIC_GPU_UUID", raising=False)
    return started


def _gpu(monkeypatch):
    monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-1")
    monkeypatch.setenv("TUBEMATIC_GPU_NAME", "NVIDIA Test")
    monkeypatch.setattr(render_agent, "_gpu_verified", True)


def test_the_cpu_argv_is_the_cpu_render_options_served_from_the_jobs_volume():
    argv, env = render_agent._stills_server_argv(on_gpu=False)
    assert argv[:2] == ["node", render_agent.STILLS_SERVER_SCRIPT]
    flags = dict(zip(argv[2::2], argv[3::2]))
    assert flags["--host"] == "0.0.0.0" and flags["--public"] == render_agent.JOBS_DIR
    assert flags["--gl"] == render_agent.CPU_GL_OPTIONS["gl"] and flags["--chrome-mode"] == render_agent.CPU_GL_OPTIONS["chromeMode"]
    assert "--browser-executable" not in flags and env == {}


def test_the_gpu_argv_is_the_gpu_render_options_and_their_environment():
    argv, env = render_agent._stills_server_argv(on_gpu=True)
    flags = dict(zip(argv[2::2], argv[3::2]))
    assert flags["--gl"] == "angle-egl" and flags["--chrome-mode"] == "chrome-for-testing"
    assert flags["--multiprocess"] == "1" and flags["--browser-executable"] == render_agent.CHROMIUM_BIN
    assert env == render_agent.GPU_GL_ENV


def test_it_starts_once_on_the_current_path_and_stays(server):
    render_agent._ensure_stills_server(now=100.0)
    render_agent._ensure_stills_server(now=101.0)
    assert len(server) == 1
    assert server[0].kw["cwd"] == str(render_agent.REMOTION_DIR) and server[0].kw["start_new_session"] is True
    assert "--gl" in server[0].argv and server[0].argv[server[0].argv.index("--gl") + 1] == "swangle"


def test_a_passing_probe_moves_it_onto_the_gpu(server, monkeypatch):
    render_agent._ensure_stills_server(now=100.0)
    _gpu(monkeypatch)
    render_agent._ensure_stills_server(now=101.0)
    assert len(server) == 2
    assert server[1].argv[server[1].argv.index("--gl") + 1] == "angle-egl"
    assert server[1].kw["env"]["__EGL_VENDOR_LIBRARY_FILENAMES"] == render_agent.GPU_GL_ENV["__EGL_VENDOR_LIBRARY_FILENAMES"]


def test_a_dead_server_is_started_again_after_the_retry_interval(server):
    render_agent._ensure_stills_server(now=100.0)
    server[0].returncode = 1
    render_agent._ensure_stills_server(now=110.0)         # too soon on the same path: no tight loop
    assert len(server) == 1
    render_agent._ensure_stills_server(now=100.0 + render_agent.STILLS_SERVER_RETRY_SECS)
    assert len(server) == 2


def test_no_port_means_no_server(server, monkeypatch):
    monkeypatch.setattr(render_agent, "STILLS_SERVER_PORT", 0)
    render_agent._ensure_stills_server(now=100.0)
    assert server == []


def test_a_server_that_cannot_start_never_raises(server, monkeypatch):
    def boom(*a, **k):
        raise OSError("no node")
    monkeypatch.setattr(render_agent.subprocess, "Popen", boom)
    render_agent._ensure_stills_server(now=100.0)
    assert render_agent._stills_proc is None


@pytest.mark.parametrize("builtin, started", [("1", 1), ("", 0)])
def test_only_the_built_in_renderer_runs_one(server, monkeypatch, builtin, started):
    monkeypatch.setenv("TUBEMATIC_RENDERER_BUILTIN", builtin)
    monkeypatch.setattr(render_agent, "_st", render_agent._AgentState())   # not started: the pass claims nothing
    render_agent._loop_once()
    assert len(server) == started
