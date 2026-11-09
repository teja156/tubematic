"""The renderer client, render_agent.py: a renderer with no database that
does everything through the render gateway (TMDEV-189).

Most tests drive the real client against the real gateway app over an httpx
WSGITransport (render_client_env.py), so a claim, the bundle, the staged
render, the upload, the result and the row the gateway leaves behind are one
path, end to end. What they guard:

- the first heartbeat says `started` and comes before any claim (the gateway
  re-queues what a restarted renderer held), later ones do not;
- a renderer that needs an upgrade, or is disabled, keeps heartbeating and
  claims nothing;
- settings (timeouts, the watermark) come from the claim, never from the
  agent-written scene-config;
- each way a render ends is reported with the exact error text the video's
  comment has always carried, a hung render's whole process group is killed
  and reaped (never waiting on the stills server), and the job directory and
  the staged public files are gone afterwards, whatever happened;
- a stop from the gateway kills the render and no result is sent; a stop
  must name the claim the heartbeat reported, and a delayed heartbeat reply
  for an earlier claim never stops a newer claim of the same video;
- every job request names the claim (X-Render-Claim); an upload the gateway
  discards as claim_lost throws the render away, one over its size limit or
  refused for disk space is not retried, one the gateway cannot take yet
  (upload_in_progress, busy) is tried again after its Retry-After without
  spending a failure attempt, for up to UPLOAD_WAIT_SECS while the claim
  holds; a result's error is cut to fit the gateway's JSON limit;
- a bundle member that could land outside the job directory is refused;
- a network error never escapes: it is noted as last_error and retried;
- enrollment checks the certificate pin before sending anything, the state
  file is written atomically and readable by its owner only, a rotated
  credential is saved before it is used, and before another heartbeat can go
  out with the old one;
- httpx's per-request INFO lines are kept out of the renderer's log;
- one test runs the real gateway over real TLS: enrollment and a heartbeat
  through the pinned context, and a wrong pin that sends nothing.

Run from renderer/api/: pytest tests/test_render_agent.py
"""
import io
import json
import os
import signal
import sqlite3
import ssl
import stat
import tarfile
import threading
import unittest.mock as mock

import httpx
import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import render_agent
import render_gateway
from tubematic_core import auth as tauth
from tubematic_core import renderers

from .render_client_env import (BUILTIN_TOKEN, GATEWAY_URL, VERSION, FakeRemotion, finished_proc,
                                make_env)


@pytest.fixture
def env(tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def _fast_render_clock(monkeypatch):
    """The render watcher's clock jumps an hour per read and its sleep is a
    no-op, so a process that never ends is judged at once (a stall at the
    default settings) instead of being waited out."""
    tick = {"now": 0.0}

    def clock():
        tick["now"] += 3600.0
        return tick["now"]
    monkeypatch.setattr(render_agent, "_clock", clock)
    monkeypatch.setattr(render_agent, "_sleep", lambda _s: None)


def _render(env, remotion=None, **seed):
    """Seed a queued video, start the renderer, run one loop pass."""
    env.seed(**seed)
    env.start()
    remotion = remotion or FakeRemotion()
    with mock.patch("subprocess.Popen", side_effect=remotion):
        render_agent._loop_once()
    return remotion


def _hung(argv, **kw):
    proc = finished_proc(argv, stdout="")
    proc.poll.return_value = None
    proc.returncode = None
    return proc


def _results(env):
    return [r["json"] for r in env.rec.requests if r["path"].endswith("/result")]


# ── the whole path ────────────────────────────────────────────────────────────

def test_a_queued_video_is_rendered_uploaded_and_left_for_the_review(env):
    remotion = _render(env)
    [(argv, kw)] = remotion.calls
    assert argv[:4] == ["npx", "remotion", "render", "Composition"]
    assert kw["cwd"] == str(env.remotion) and kw["start_new_session"] is True
    assert not any(a.startswith(("--gl", "--chrome-mode")) for a in argv)     # no GPU: the CPU path, as before
    assert remotion.props() == {"sceneConfigPath": "/public/vid-1/scene-config.json",
                                "timelinePath": "/public/vid-1/timeline.json",
                                "audioPath": "/public/vid-1/audio.mp3", "watermark": True}
    v = env.video()
    assert v["status"] == "RENDERING" and v["render_uploaded_at"]       # the worker's review finishes it
    assert v["video_path"] == str(env.out / "proj-1" / "vid-1.mp4")
    assert (env.out / "proj-1" / "vid-1.mp4").read_bytes() == b"MP4DATA"
    [timing] = env.sql("SELECT renderer_id, kind, on_gpu, frames FROM render_timings")
    assert timing == {"renderer_id": "builtin", "kind": "dom", "on_gpu": 0, "frames": 90}
    [result] = _results(env)
    assert result["outcome"] == "success" and result["frames"] == 90 and result["seconds"] > 0
    assert env.rec.paths() == ["/v1/heartbeat", "/v1/claim", "/v1/jobs/vid-1/bundle",
                               "/v1/jobs/vid-1/output", "/v1/jobs/vid-1/result"]
    # every job request names the claim the video was handed out under
    jobs = [r for r in env.rec.requests if r["path"].startswith("/v1/jobs/")]
    assert len({r["claim"] for r in jobs}) == 1 and len(jobs[0]["claim"]) == 32


def test_the_job_is_staged_while_it_renders_and_gone_afterwards(env):
    job = env.seed()
    (job / "images").mkdir()
    (job / "images" / "skyline.png").write_bytes(b"PNG")
    seen = {}

    def look(argv, kw):
        staged = env.public / "vid-1"
        seen["public"] = sorted(str(p.relative_to(staged)) for p in staged.rglob("*"))
        seen["work"] = (env.render_tmp / "vid-1" / "audio.mp3").read_bytes()
    env.start()
    with mock.patch("subprocess.Popen", side_effect=FakeRemotion(on_start=look)):
        render_agent._loop_once()
    assert seen["public"] == ["audio.mp3", "images", "images/skyline.png", "scene-config.json", "timeline.json"]
    assert seen["work"] == b"AUDIO"
    assert not (env.public / "vid-1").exists() and not (env.render_tmp / "vid-1").exists()


def test_a_video_without_images_still_renders(env):
    def look(argv, kw):
        assert not (env.public / "vid-1" / "images").exists()
    _render(env, FakeRemotion(on_start=look))
    assert env.video()["render_uploaded_at"]


@pytest.mark.parametrize("vid", ["a.b", "Spaced Name", "x" * 129])
def test_a_legacy_video_id_still_renders(env, vid):
    _render(env, vid=vid)
    assert env.video(vid)["video_path"] == str(env.out / "proj-1" / f"{vid}.mp4")


def test_the_built_in_renderer_never_touches_the_shared_scene_tree(env):
    """The built-in renderer's generated tree is the volume the agent writes:
    it renders from it as it always did, and never clears or restages it."""
    (env.generated / "vid-1").mkdir()
    (env.generated / "vid-1" / "Intro.tsx").write_text("intro")
    (env.generated / "Other.tsx").write_text("another video's scene")
    _render(env, scenes=[{"type": "generated", "src": "vid-1/Intro"}])
    assert (env.generated / "vid-1" / "Intro.tsx").read_text() == "intro"
    assert (env.generated / "Other.tsx").read_text() == "another video's scene"


# ── the heartbeat ─────────────────────────────────────────────────────────────

def test_nothing_is_claimed_before_the_first_heartbeat(env):
    env.seed()
    assert render_agent._loop_once() == render_agent.POLL_INTERVAL_SECS
    assert env.rec.paths() == []


def test_the_first_heartbeat_says_started_and_requeues_what_was_held(env):
    env.seed(status="RENDERING", renderer_id="builtin")
    env.start()
    assert env.video()["status"] == "RENDER_QUEUED"
    assert env.comments() == ["Render interrupted by renderer restart — automatically re-queued."]
    env.start()
    first, second = env.rec.beats()
    assert first["started"] is True and second["started"] is False
    assert first["version"] == VERSION and first["state"] == "idle" and first["video_id"] == ""


def test_the_log_lines_the_remote_host_script_watches_for(env, caplog, monkeypatch):
    """scripts/tubematic_remote_renderer.py follows `docker logs` and matches
    these words: "first heartbeat", "enrolled", "enrollment_invalid"."""
    import logging
    caplog.set_level(logging.INFO, logger="render_agent")
    env.start()
    env.start()
    assert [r for r in caplog.records if "first heartbeat" in r.getMessage().lower()
            and r.levelno == logging.INFO and VERSION in r.getMessage()].__len__() == 1
    remote = _remote_env(env, monkeypatch)
    assert any("enrolled" in r.getMessage().lower() and r.levelno == logging.INFO for r in caplog.records)
    caplog.clear()
    with pytest.raises(render_agent.EnrollmentError):
        render_agent.enroll(remote.token, remote.state, {}, transport=env.rec)       # already used
    assert any("enrollment_invalid" in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)
    assert remote.credential not in caplog.text and remote.secret not in caplog.text


def test_a_heartbeat_carries_a_probe_once(env):
    with render_agent._st.lock:
        render_agent._st.pending_probe = {"at": "2026-01-01T00:00:00.000001Z", "configured": False, "ok": False}
    env.start()
    env.start()
    first, second = env.rec.beats()
    assert first["gpu_probe"]["at"] == "2026-01-01T00:00:00.000001Z" and "gpu_probe" not in second
    assert json.loads(env.renderer()["gpu_probe"])["at"] == "2026-01-01T00:00:00.000001Z"


def test_a_heartbeat_during_a_render_reports_it_and_extends_its_lease(env):
    env.seed()
    env.start()
    seen = {}

    def beat_mid_render(argv, kw):
        env.sql("UPDATE videos SET render_lease_until = '2000-01-01T00:00:00Z'")
        assert render_agent._beat()
        seen["beat"] = env.rec.beats()[-1]
        seen["lease"] = env.video()["render_lease_until"]
        seen["claim"] = env.video()["render_claim_id"]
    with mock.patch("subprocess.Popen", side_effect=FakeRemotion(on_start=beat_mid_render)):
        render_agent._loop_once()
    assert seen["beat"]["state"] == "rendering" and seen["beat"]["video_id"] == "vid-1"
    assert seen["beat"]["claim_id"] and seen["beat"]["claim_id"] == seen["claim"]
    assert seen["lease"] > "2026"


def test_the_built_in_token_is_read_on_every_request(env):
    """--rotate-tokens rewrites the secret file in place; both the gateway and
    the renderer read it per request, so the next heartbeat just works."""
    env.start()
    (env.secrets / "builtin_renderer_token").write_text("rotated-token")
    assert render_agent._beat() is True
    assert [r["auth"] for r in env.rec.requests] == [f"Bearer {BUILTIN_TOKEN}", "Bearer rotated-token"]


def test_a_renderer_that_needs_an_upgrade_heartbeats_and_claims_nothing(env, monkeypatch, caplog):
    env.seed()
    monkeypatch.setattr(render_agent, "current_version", lambda: "0.0.1")
    env.start()
    assert render_agent._loop_once() == render_agent.POLL_INTERVAL_SECS
    assert render_agent._st.needs_upgrade is True
    assert "/v1/claim" not in env.rec.paths() and env.video()["status"] == "RENDER_QUEUED"
    assert "needs upgrade" in caplog.text


def test_a_disabled_renderer_heartbeats_and_claims_nothing(env):
    env.seed()
    env.sql("UPDATE renderers SET enabled = 0 WHERE id = 'builtin'")
    env.start()
    render_agent._loop_once()
    assert "/v1/claim" not in env.rec.paths() and env.video()["status"] == "RENDER_QUEUED"


def test_a_claim_refused_as_disabled_stops_further_claims(env):
    env.seed()
    env.start()
    env.sql("UPDATE renderers SET enabled = 0 WHERE id = 'builtin'")
    render_agent._loop_once()
    render_agent._loop_once()
    assert env.rec.paths().count("/v1/claim") == 1 and render_agent._st.enabled is False


def test_probe_now_runs_the_probe_between_renders_and_reports_it(env, monkeypatch):
    env.start()
    env.sql("UPDATE renderers SET gpu_probe_requested_at = '2026-05-01T00:00:00.000000Z' WHERE id = 'builtin'")
    render_agent._beat()
    assert render_agent._st.probe_now is True
    probe = {"at": "2026-05-01T00:00:01.000000Z", "configured": False, "ok": False, "reason": "x"}
    monkeypatch.setattr(render_agent, "_run_gpu_probe", mock.Mock(return_value=probe))
    render_agent._loop_once()
    render_agent._run_gpu_probe.assert_called_once_with("requested from the dashboard")
    assert render_agent._st.probe_now is False
    r = env.renderer()
    assert json.loads(r["gpu_probe"])["at"] == probe["at"] and r["gpu_probe_requested_at"] == ""


# ── settings come from the claim ──────────────────────────────────────────────

def test_the_timeouts_come_from_the_claim(env):
    env.sql("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '900'), "
            "('render_stall_timeout_secs', '60')")
    seen = {}

    def watch(proc, timeout_secs, stall_secs):
        seen.update(timeout=timeout_secs, stall=stall_secs)
        return "", "", "exited"
    with mock.patch.object(render_agent, "_wait_for_render", side_effect=watch):
        _render(env)
    assert seen == {"timeout": 900, "stall": 60}


def test_the_watermark_comes_from_the_setting_not_the_scene_config(env):
    """Default on. The scene-config says the opposite and must not count: the
    agent writes that file."""
    job = env.seed()
    (job / "scene-config.json").write_text('{"scenes": [], "watermark": false}')
    env.start()
    remotion = FakeRemotion()
    with mock.patch("subprocess.Popen", side_effect=remotion):
        render_agent._loop_once()
    assert remotion.props()["watermark"] is True


def test_the_watermark_is_dropped_when_the_setting_is_off(env):
    env.sql("INSERT INTO settings (key, value) VALUES ('watermark_enabled', 'false')")
    assert _render(env).props()["watermark"] is False


# ── how a render ends ─────────────────────────────────────────────────────────

def test_a_failed_render_reports_remotions_error(env):
    _render(env, FakeRemotion(returncode=1, stderr="out of memory"))
    [result] = _results(env)
    assert result == {"outcome": "failed", "error": "out of memory", "on_gpu": False, "gpu_ok": None}
    assert env.video()["status"] == "REVISION_REQUESTED"
    assert env.comments() == ["Render failed: out of memory"]
    assert not (env.render_tmp / "vid-1").exists() and not (env.public / "vid-1").exists()


def test_a_stalled_render_is_killed_and_reported_stalled(env):
    with mock.patch("os.getpgid", return_value=4242), mock.patch("os.killpg") as killpg, \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        _render(env, remotion=_hung)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    assert _results(env)[0]["outcome"] == "stalled"
    assert env.video()["status"] == "RENDER_QUEUED" and env.video()["render_fail_count"] == 1
    assert env.comments() == ["Render failed: Render stalled: no progress for 600s"]


def test_a_render_past_the_ceiling_is_reported_timed_out(env):
    env.sql("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '1000'), "
            "('render_stall_timeout_secs', '50000')")
    with mock.patch("os.getpgid", return_value=4242), mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        _render(env, remotion=_hung)
    assert _results(env)[0]["outcome"] == "timeout"
    assert env.comments() == ["Render failed: Render timed out after 1000s"]


def test_a_hung_render_past_the_retry_cap_fails(env):
    with mock.patch("os.getpgid", return_value=4242), mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        _render(env, remotion=_hung, render_fail_count=2)
    assert env.video()["status"] == "FAILED" and env.video()["render_fail_count"] == 3


def test_a_hung_render_kills_its_whole_process_group_and_reaps_it(env):
    """TMDEV-57: subprocess.run's own timeout handling only kills the direct
    child, orphaning any Chromium/ffmpeg it spawned (confirmed live — they
    survived as <defunct> zombies competing with the next render attempt).
    Popen + start_new_session=True puts the whole tree in one process group,
    which this asserts gets killed and reaped, not just abandoned."""
    procs = []

    def popen(argv, **kw):
        procs.append(_hung(argv))
        return procs[-1]
    remotion = mock.Mock(side_effect=popen)
    with mock.patch("os.getpgid", return_value=4242) as getpgid, mock.patch("os.killpg") as killpg, \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        _render(env, remotion=remotion)
    assert remotion.call_args.kwargs["start_new_session"] is True
    getpgid.assert_called_once_with(4242)
    killpg.assert_called_once_with(4242, signal.SIGKILL)
    procs[0].wait.assert_called_once()


def test_a_hung_render_reaps_reparented_grandchildren(env):
    """TMDEV-57 follow-up, confirmed live: grandchildren (node, chrome-headless,
    ffmpeg, ...) reparent to this container's PID 1 — this same renderer
    process — the instant their parent dies. The reaper drains each in turn
    until none remain rather than giving up on the first not-ready check."""
    with mock.patch("os.getpgid", return_value=4242), mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=[(19, 0), (20, 0), ChildProcessError()]) as waitpid:
        _render(env, remotion=_hung)
    assert waitpid.call_args_list == [mock.call(-1, os.WNOHANG)] * 3


def test_a_hung_render_reap_never_waits_on_the_stills_server(env, monkeypatch):
    """The stills server (TMDEV-179) is a long-lived child of the renderer, so a
    blocking waitpid(-1) would sit on it forever after a timeout. The reaper
    drains non-blocking and stops as soon as no child but the stills server
    is left, polling only while an orphan of the killed group is still dying."""
    others = iter([{20}, set()])
    monkeypatch.setattr(render_agent, "_other_children", lambda: next(others, set()))
    monkeypatch.setattr(render_agent.time, "sleep", lambda s: None)
    with mock.patch("os.getpgid", return_value=4242), mock.patch("os.killpg"), \
         mock.patch("os.waitpid", side_effect=[(19, 0), (0, 0), (0, 0), (0, 0)]) as waitpid:
        _render(env, remotion=_hung)
    assert waitpid.call_args_list == [mock.call(-1, os.WNOHANG)] * 3
    assert env.video()["status"] == "RENDER_QUEUED"


def test_an_exception_in_the_render_is_this_videos_error_not_the_renderers_exit(env):
    def no_space(argv, **kw):
        raise OSError(28, "No space left on device")
    _render(env, remotion=no_space)
    [result] = _results(env)
    assert result["outcome"] == "error"
    assert result["error"] == "The renderer hit an error: [Errno 28] No space left on device"
    assert env.video()["status"] == "RENDER_QUEUED"
    assert render_agent._st.job is None and render_agent._st.last_error
    assert not (env.render_tmp / "vid-1").exists() and not (env.public / "vid-1").exists()


def test_a_bundle_the_gateway_cannot_build_is_reported_as_an_error(env):
    env.seed()

    def vanish(request):
        if request.url.path.endswith("/bundle"):
            (env.jobs / "vid-1" / "audio.mp3").unlink()
    env.rec.hook = vanish
    env.start()
    with mock.patch("subprocess.Popen") as popen:
        render_agent._loop_once()
    popen.assert_not_called()
    [result] = _results(env)
    assert result["outcome"] == "error" and "could not be fetched" in result["error"]
    assert env.video()["status"] == "RENDER_QUEUED"


def test_a_render_that_wrote_nothing_is_an_error(env):
    _render(env, FakeRemotion(output=None))
    assert _results(env)[0]["outcome"] == "error"
    assert "/v1/jobs/vid-1/output" not in env.rec.paths()


# ── a stop from the gateway ───────────────────────────────────────────────────

def test_a_stop_kills_the_render_and_no_result_is_sent(env):
    """A human moved the video while it rendered: the next heartbeat's stop
    list names it, the render's process group is killed (the same reaper a
    stall gets), and the render is thrown away without a result."""
    env.seed()
    env.start()
    killed = []
    proc_box = {}

    def popen(argv, **kw):
        proc = finished_proc(argv, stdout="")
        state = {"polls": 0}

        def poll():
            if killed:
                return -9
            state["polls"] += 1
            if state["polls"] == 2:
                env.sql("UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = 'vid-1'")
                assert render_agent._beat()          # what the heartbeat thread would do
                return -9 if killed else None
            return None
        proc.poll.side_effect = poll
        proc_box["proc"] = proc
        return proc
    with mock.patch("subprocess.Popen", side_effect=popen), mock.patch("os.getpgid", return_value=4242), \
         mock.patch("os.killpg", side_effect=lambda *a: killed.append(a)), \
         mock.patch("os.waitpid", side_effect=ChildProcessError):
        # a timeout the fake clock could reach is far away: only the stop ends this render
        env.sql("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '999999999'), "
                "('render_stall_timeout_secs', '999999999')")
        render_agent._loop_once()
    assert killed == [(4242, signal.SIGKILL)]
    assert _results(env) == [] and "/v1/jobs/vid-1/output" not in env.rec.paths()
    assert env.video()["status"] == "REVISION_REQUESTED" and env.comments() == []
    assert not (env.render_tmp / "vid-1").exists() and render_agent._st.job is None


def test_a_stopped_job_never_starts_a_render_process(env):
    job = render_agent._Job("vid-1")
    job.stopped = True
    render_agent._st.job = job
    with mock.patch("subprocess.Popen") as popen, pytest.raises(render_agent._Stopped):
        render_agent._spawn(["npx"])
    popen.assert_not_called()


def test_a_stop_for_a_video_it_is_not_rendering_is_ignored(env):
    env.start()
    env.seed("vid-1", status="RENDERING", renderer_id="builtin", render_claim_id="c-1")
    env.seed("vid-9", status="REVISION_REQUESTED", renderer_id="builtin", render_claim_id="c-9")  # a stale row
    job = render_agent._Job("vid-1", "c-1")
    render_agent._st.job = job
    assert render_agent._beat() is True
    assert job.stopped is False


@pytest.mark.parametrize("stop", [["vid-1"], [{"video_id": "vid-1"}], [{"video_id": "vid-1", "claim_id": "other"}],
                                  [{"video_id": "vid-2", "claim_id": "c-1"}]])
def test_a_stop_must_name_the_reported_claim(env, stop):
    env.start()
    job = render_agent._Job("vid-1", "c-1")
    render_agent._st.job = job
    env.rec.hook = lambda request: (httpx.Response(200, json={"enabled": True, "needs_upgrade": False,
                                                              "stop": stop})
                                    if request.url.path == "/v1/heartbeat" else None)
    assert render_agent._beat() is True
    assert job.stopped is False
    env.rec.hook = lambda request: httpx.Response(200, json={"stop": [{"video_id": "vid-1", "claim_id": "c-1"}]})
    assert render_agent._beat() is True
    assert job.stopped is True


@pytest.mark.parametrize("reclaimed_before_the_gateway_saw_it", [False, True])
def test_a_delayed_heartbeat_for_claim_a_never_stops_or_extends_claim_b(env, reclaimed_before_the_gateway_saw_it):
    """Claim A's heartbeat is slow. While it is in flight, A is re-queued and
    the same renderer claims the same video again as claim B and starts it.
    Whether the gateway handled A's heartbeat before or after B's claim, its
    reply is applied to A only: B is not stopped, and B's lease is not
    extended by A's heartbeat."""
    env.start()
    env.seed("vid-1", status="RENDERING", renderer_id="builtin", render_claim_id="claim-a",
             render_lease_until="2999-01-01T00:00:00Z")
    job_a = render_agent._Job("vid-1", "claim-a")
    render_agent._st.job = job_a
    jobs = {}

    def requeue_and_claim_b():
        import render_results
        assert render_results.requeue_interrupted("vid-1", "Render lost — automatically re-queued.",
                                                  renderer_id="builtin")
        reply = render_agent._client.send("POST", "/v1/claim", json_body={}).json()
        assert reply["video_id"] == "vid-1" and reply["claim_id"] != "claim-a"
        env.sql("UPDATE videos SET render_lease_until = '2000-01-01T00:00:00Z'")
        jobs["b"] = render_agent._Job("vid-1", reply["claim_id"])
        with render_agent._st.lock:
            render_agent._st.job = jobs["b"]

    def delayed(request):
        if request.url.path != "/v1/heartbeat" or jobs:
            return None
        env.rec.hook = None
        if reclaimed_before_the_gateway_saw_it:
            requeue_and_claim_b()
            return env.rec.inner.handle_request(request)
        env.sql("UPDATE videos SET status = 'RENDER_QUEUED', renderer_id = '' WHERE id = 'vid-1'")
        resp = env.rec.inner.handle_request(request)
        env.sql("UPDATE videos SET status = 'RENDERING', renderer_id = 'builtin' WHERE id = 'vid-1'")
        requeue_and_claim_b()
        return resp
    env.rec.hook = delayed
    assert render_agent._beat() is True
    beat = env.rec.beats()[-1]
    assert beat["video_id"] == "vid-1" and beat["claim_id"] == "claim-a"
    assert jobs["b"].stopped is False and render_agent._st.job is jobs["b"]
    assert job_a.stopped is True
    v = env.video()
    assert v["status"] == "RENDERING" and v["render_claim_id"] == jobs["b"].claim_id
    assert v["render_lease_until"] == "2000-01-01T00:00:00Z"
    # B's own heartbeat extends B's lease and stops nothing
    assert render_agent._beat() is True
    assert jobs["b"].stopped is False and env.video()["render_lease_until"] > "2026"


# ── the bundle's members ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "audio.mp3", "timeline.json", "scene-config.json", "mascot.js", "images/a.png", "images/sub/b.png",
    "cartoon/source.json", "cartoon/audio/mix/mix.wav", "scenes/vid-1/Intro.tsx", "scenes/vid-1/sets/street.ts",
    "scenes/_flat/Legacy.tsx"])
def test_the_members_the_gateway_sends_are_accepted(name):
    assert render_agent._bundle_parts(name, "vid-1") == name.split("/")


@pytest.mark.parametrize("name", [
    "../escape", "/etc/passwd", "images/../../x", "images/./a.png", "images//a.png", "a\\b", "",
    "images", "scenes/vid-2/Intro.tsx", "scenes/_flat/a/b.tsx", "scenes/_flat/x.ts", "notes.txt",
    "cartoon/other.json"])
def test_any_other_member_is_refused(name):
    with pytest.raises(render_agent._BundleRefused):
        render_agent._bundle_parts(name, "vid-1")


def _tar(members) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "sym":
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                tf.addfile(info)
            else:
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.mark.parametrize("bad", [("../../escaped.txt", b"x", "file"), ("images/link.png", b"", "sym")])
def test_a_bundle_with_a_member_outside_the_job_is_refused_before_anything_lands(env, bad):
    env.seed()
    good = [("audio.mp3", b"A", "file"), ("timeline.json", b"{}", "file"), ("scene-config.json", b"{}", "file")]
    body = _tar(good[:1] + [bad] + good[1:])

    def serve(request):
        if request.url.path.endswith("/bundle"):
            return httpx.Response(200, content=body, headers={"content-type": "application/x-tar"})
    env.rec.hook = serve
    env.start()
    with mock.patch("subprocess.Popen") as popen:
        render_agent._loop_once()
    popen.assert_not_called()
    assert not (env.tmp / "escaped.txt").exists() and not (env.render_tmp.parent / "escaped.txt").exists()
    [result] = _results(env)
    assert result["outcome"] == "error" and "bundle" in result["error"]
    assert not (env.render_tmp / "vid-1").exists()


# ── network errors ────────────────────────────────────────────────────────────

def _down(request):
    raise httpx.ConnectError("connection refused", request=request)


def test_a_heartbeat_that_cannot_reach_the_gateway_is_noted_and_retried(env):
    env.rec.hook = _down
    assert render_agent._beat() is False
    assert render_agent._st.started is True                     # the next one still says so
    assert "heartbeat failed" in render_agent._st.last_error
    env.rec.hook = None
    env.start()
    beat = env.rec.beats()[-1]
    assert beat["started"] is True and "heartbeat failed" in beat["last_error"]


def test_a_claim_that_cannot_reach_the_gateway_waits_and_retries(env):
    env.start()
    env.rec.hook = _down
    assert render_agent._loop_once() == render_agent.NETWORK_RETRY_SECS
    assert "claim failed" in render_agent._st.last_error
    env.rec.hook = None
    assert render_agent._loop_once() == render_agent.POLL_INTERVAL_SECS
    assert render_agent._st.last_error == ""


def test_an_upload_that_fails_once_is_tried_again(env):
    failures = []

    def flaky(request):
        if request.method == "PUT" and not failures:
            failures.append(1)
            raise httpx.WriteError("broken pipe", request=request)
    env.rec.hook = flaky
    _render(env)
    assert env.rec.paths("PUT") == ["/v1/jobs/vid-1/output"] * 2
    assert _results(env)[0]["outcome"] == "success" and env.video()["render_uploaded_at"]


def test_an_upload_that_keeps_failing_is_reported_as_an_error(env):
    def refuse(request):
        if request.method == "PUT":
            raise httpx.WriteError("broken pipe", request=request)
    env.rec.hook = refuse
    _render(env)
    assert len(env.rec.paths("PUT")) == render_agent.UPLOAD_ATTEMPTS
    [result] = _results(env)
    assert result["outcome"] == "error" and "could not be uploaded" in result["error"]
    assert env.video()["status"] == "RENDER_QUEUED"


def test_a_result_that_cannot_be_delivered_never_raises(env):
    def lose(request):
        if request.url.path.endswith("/result"):
            raise httpx.ReadTimeout("timed out", request=request)
    env.rec.hook = lose
    _render(env)
    assert len(_results(env)) == render_agent.RESULT_ATTEMPTS
    assert render_agent._st.job is None and "lease will expire" in render_agent._st.last_error


def test_a_claim_with_no_claim_id_is_not_rendered(env):
    env.seed()
    env.start()

    def old_reply(request):
        if request.url.path == "/v1/claim":
            return httpx.Response(200, json={"video_id": "vid-1", "kind": "dom"})
    env.rec.hook = old_reply
    with mock.patch("subprocess.Popen") as popen:
        render_agent._loop_once()
    popen.assert_not_called()
    assert not any(p.startswith("/v1/jobs/") for p in env.rec.paths())
    assert "no claim id" in render_agent._st.last_error and render_agent._st.job is None


def test_an_upload_discarded_as_claim_lost_throws_the_render_away(env):
    def lost(request):
        if request.method == "PUT":
            return httpx.Response(409, json={"error": "claim_lost"})
    env.rec.hook = lost
    _render(env)
    assert len(env.rec.paths("PUT")) == 1                # never retried
    assert _results(env) == [] and "claim was lost" in render_agent._st.last_error


@pytest.mark.parametrize("answer", [httpx.Response(409, json={"error": "upload_in_progress"}),
                                    httpx.Response(503, json={"error": "busy"}, headers={"Retry-After": "7"})])
def test_an_upload_the_gateway_cannot_take_yet_is_tried_again_after_a_pause(env, monkeypatch, answer):
    sleeps = []
    monkeypatch.setattr(render_agent.time, "sleep", lambda s: sleeps.append(s))
    answers = []

    def busy_once(request):
        if request.method == "PUT" and not answers:
            answers.append(1)
            return answer
    env.rec.hook = busy_once
    _render(env)
    assert env.rec.paths("PUT") == ["/v1/jobs/vid-1/output"] * 2
    assert _results(env)[0]["outcome"] == "success" and env.video()["render_uploaded_at"]
    assert sleeps and sleeps[0] == (7 if answer.status_code == 503 else 0)


def _fake_wait_clock(monkeypatch, on_sleep=None):
    """The upload's busy-wait clock, advanced only by its sleeps (recorded)."""
    clock = {"now": 1000.0, "sleeps": []}

    def sleep(s):
        clock["sleeps"].append(s)
        clock["now"] += s
        if on_sleep is not None:
            on_sleep(clock)
    monkeypatch.setattr(render_agent, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(render_agent.time, "sleep", sleep)
    return clock


def test_an_upload_waits_on_a_busy_gateway_long_past_its_failure_attempts(env, monkeypatch):
    """Every upload slot is taken (by the real gateway's admission, cap 0)
    for 15 minutes — far past the three failure attempts' ~20 s — then one
    frees: the finished render is uploaded and reported a success, never a
    failure."""
    monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 0)

    def free_a_slot(clock):
        if clock["now"] - 1000.0 >= 900:
            monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 4)
    clock = _fake_wait_clock(monkeypatch, free_a_slot)
    _render(env)
    puts = env.rec.paths("PUT")
    assert len(puts) > render_agent.UPLOAD_ATTEMPTS * 10
    assert all(s == render_gateway.BUSY_RETRY_AFTER_SECS for s in clock["sleeps"])   # its Retry-After
    [result] = _results(env)
    assert result["outcome"] == "success" and env.video()["render_uploaded_at"]


def test_an_upload_gives_up_on_a_busy_gateway_after_its_wait(env, monkeypatch):
    monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 0)

    def runaway(clock):
        if clock["now"] - 1000.0 > render_agent.UPLOAD_WAIT_SECS + 3600:
            raise AssertionError("the busy wait never ended")
    clock = _fake_wait_clock(monkeypatch, runaway)
    _render(env)
    assert render_agent.UPLOAD_WAIT_SECS <= sum(clock["sleeps"]) < render_agent.UPLOAD_WAIT_SECS + 60
    [result] = _results(env)
    assert result["outcome"] == "error" and "stayed busy (busy)" in result["error"]
    assert env.video()["status"] == "RENDER_QUEUED"


def test_a_stop_ends_the_wait_on_a_busy_gateway(env, monkeypatch):
    monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 0)

    def stop(clock):
        if len(clock["sleeps"]) == 5:
            render_agent._st.job.stopped = True
    _fake_wait_clock(monkeypatch, stop)
    _render(env)
    assert len(env.rec.paths("PUT")) == 5 and _results(env) == []


def test_busy_answers_do_not_spend_the_failure_attempts(env, monkeypatch):
    """Two busy answers, then network errors: the errors still get all three
    attempts."""
    answers = []

    def busy_then_down(request):
        if request.method == "PUT":
            answers.append(1)
            if len(answers) <= 2:
                return httpx.Response(503, json={"error": "busy"}, headers={"Retry-After": "1"})
            raise httpx.WriteError("broken pipe", request=request)
    env.rec.hook = busy_then_down
    _fake_wait_clock(monkeypatch)
    _render(env)
    assert len(env.rec.paths("PUT")) == 2 + render_agent.UPLOAD_ATTEMPTS
    [result] = _results(env)
    assert result["outcome"] == "error" and "could not be uploaded" in result["error"]


def test_an_upload_refused_for_disk_space_is_reported_as_an_error(env):
    def full(request):
        if request.method == "PUT":
            return httpx.Response(507, json={"error": "insufficient_storage"})
    env.rec.hook = full
    _render(env)
    assert len(env.rec.paths("PUT")) == 1                # not retried
    [result] = _results(env)
    assert result["outcome"] == "error" and "short of disk space" in result["error"]
    assert env.video()["status"] == "RENDER_QUEUED"


def test_a_long_render_error_is_cut_to_fit_the_gateways_json_limit(env):
    remotion = FakeRemotion(returncode=1, stderr="E" * 200_000)
    _render(env, remotion=remotion)
    [result] = _results(env)
    assert result["outcome"] == "failed" and result["error"] == "E" * render_agent.RESULT_ERROR_CHARS
    assert env.video()["status"] == "REVISION_REQUESTED"


def test_an_upload_over_the_gateways_limit_is_not_retried(env):
    def too_big(request):
        if request.method == "PUT":
            return httpx.Response(413, json={"error": "output_too_large", "limit": 3})
    env.rec.hook = too_big
    _render(env)
    assert len(env.rec.paths("PUT")) == 1
    [result] = _results(env)
    assert result["outcome"] == "error" and "larger than the gateway accepts" in result["error"]
    assert env.video()["status"] == "RENDER_QUEUED"


def test_a_lost_lease_discards_the_render(env):
    env.seed()
    env.start()

    def take_over(argv, kw):
        env.sql("UPDATE videos SET renderer_id = 'r_other'")
    with mock.patch("subprocess.Popen", side_effect=FakeRemotion(on_start=take_over)):
        render_agent._loop_once()
    assert _results(env) == []                          # the upload's 403 ended it
    assert not (env.out / "proj-1" / "vid-1.mp4").exists()


# ── the GPU ───────────────────────────────────────────────────────────────────

def _probe(ok):
    return {"at": "2026-06-01T00:00:00.000000Z", "configured": True, "ok": ok,
            "error": "" if ok else "Chromium is rendering on another device: SwiftShader"}


def _cartoon_source(env, vid="vid-1"):
    """The frozen source a Cartoon 3D render is checked against: a one-file
    tree in the shared generated dir and submit_render's record of it."""
    from tubematic_core import jobfiles as tjobs
    (env.generated / vid).mkdir(parents=True, exist_ok=True)
    (env.generated / vid / "CartoonShort.tsx").write_text("export default () => null;")
    record = env.jobs / vid / "cartoon" / "source.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(env.generated / vid), "at": "now"}))
    # the fast test clock spends an hour per look: a ceiling it cannot reach
    env.sql("INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '999999999')")


def test_a_failed_gpu_render_retests_the_gpu_and_reports_the_answer(env, monkeypatch):
    env.gpu(ok=True)
    _cartoon_source(env)
    probe = mock.Mock(return_value=_probe(False))
    monkeypatch.setattr(render_agent, "_run_gpu_probe", probe)
    remotion = _render(env, FakeRemotion(returncode=1, stderr="WebGL context lost"), visual_style="cartoon_3d")
    assert "--gl=angle-egl" in remotion.calls[0][0]
    probe.assert_called_once_with("a Cartoon 3D render on the GPU failed")
    [result] = _results(env)
    assert result["on_gpu"] is True and result["gpu_ok"] is False and result["gpu_probe"]["ok"] is False
    v = env.video()
    assert v["status"] == "FAILED" and v["render_fail_count"] == 0       # no retry can bring a GPU back
    assert env.renderer()["gpu_verified"] == 0


def test_a_failed_gpu_render_on_a_gpu_that_still_works_is_the_videos_own(env, monkeypatch):
    env.gpu(ok=True)
    _cartoon_source(env)
    monkeypatch.setattr(render_agent, "_run_gpu_probe", mock.Mock(return_value=_probe(True)))
    _render(env, FakeRemotion(returncode=1, stderr="TypeError in scene"), mascot_id="", visual_style="cartoon_3d")
    assert _results(env)[0]["gpu_ok"] is True
    assert env.video()["status"] == "REVISION_REQUESTED"


def test_a_failed_cpu_render_does_not_probe(env, monkeypatch):
    probe = mock.Mock()
    monkeypatch.setattr(render_agent, "_run_gpu_probe", probe)
    _render(env, FakeRemotion(returncode=1, stderr="boom"))
    probe.assert_not_called()
    assert _results(env)[0]["gpu_ok"] is None


def test_a_gpu_video_on_a_gpu_that_fails_its_test_now_goes_back_to_the_queue(env, monkeypatch):
    """The gateway believed this renderer's GPU (its last probe passed); the
    renderer re-tests a GPU it has not verified itself before rendering a
    GPU-only video, and if it fails the video is not rendered on the CPU: it
    goes back to the queue and this renderer gets no more GPU work."""
    env.gpu(ok=True)
    monkeypatch.setattr(render_agent, "_gpu_verified", False)
    probe = mock.Mock(side_effect=lambda reason: _probe(False))
    monkeypatch.setattr(render_agent, "_run_gpu_probe", probe)
    with mock.patch("subprocess.Popen") as popen:
        env.seed(visual_style="cartoon_3d")
        render_agent._loop_once()
    popen.assert_not_called()
    probe.assert_called_once_with("a Cartoon 3D video needs the GPU")
    [result] = _results(env)
    assert result["gpu_ok"] is False and "did not pass its test" in result["error"]
    assert env.video()["status"] == "RENDER_QUEUED" and env.renderer()["gpu_verified"] == 0


def test_a_mascot_video_gets_its_pinned_code_and_the_mascot_path(env):
    env.gpu(ok=True)
    env.sql("INSERT INTO mascots (id, name, status, approved_version) VALUES ('m1', 'M', 'READY', 2)")
    env.sql("INSERT INTO mascot_versions (mascot_id, version, code) VALUES ('m1', 1, 'v1 code'), ('m1', 2, 'v2')")
    seen = {}

    def look(argv, kw):
        seen["code"] = (env.public / "vid-1" / "mascot.js").read_text()
    remotion = _render(env, FakeRemotion(on_start=look), mascot_id="m1", mascot_version=1)
    assert remotion.props()["mascotPath"] == "/public/vid-1/mascot.js"
    assert seen["code"] == "v1 code"


def test_a_video_without_a_mascot_gets_no_mascot_path(env):
    assert "mascotPath" not in _render(env).props()


# ── a remote renderer ─────────────────────────────────────────────────────────

class _Remote:
    pass


def _remote_env(env, monkeypatch, tls_dir=None):
    """Enroll a remote renderer against env's gateway: a real certificate (its
    pin in the token), fetched by a stand-in for ssl.get_server_certificate."""
    r = _Remote()
    tls = tls_dir or env.tmp / "tls"
    tauth.ensure_secrets(tls)
    r.pem = tauth.read_secret(tauth.TLS_CERT_NAME, tls)
    r.pin = tauth.gateway_pin(tls)
    con = sqlite3.connect(env.db)
    r.secret, _ = renderers.create_enrollment(con, "")
    con.commit()
    con.close()
    r.token = renderers.encode_enrollment_token(GATEWAY_URL, r.secret, r.pin)
    r.state = env.tmp / "state" / "renderer.json"
    monkeypatch.setattr(render_agent, "_fetch_server_cert", lambda host, port: r.pem)
    r.identity = render_agent.enroll(r.token, r.state, {"cpus": 4}, transport=env.rec)
    r.credential = r.identity.credential()
    return r


def test_enrollment_saves_a_private_state_file_and_the_credential_works(env, monkeypatch):
    r = _remote_env(env, monkeypatch)
    data = json.loads(r.state.read_text())
    assert set(data) >= {"renderer_id", "credential", "credential_expires_at", "machine_id", "pin", "cert_pem",
                         "gateway_url"}
    assert data["pin"] == r.pin and data["cert_pem"] == r.pem and data["gateway_url"] == GATEWAY_URL
    assert stat.S_IMODE(os.stat(r.state).st_mode) == 0o600
    assert [p.name for p in r.state.parent.iterdir()] == ["renderer.json"]      # no temp file left
    row = env.renderer(data["renderer_id"])
    assert row["machine_id"] == data["machine_id"] and json.loads(row["compute"]) == {"cpus": 4}
    monkeypatch.setattr(render_agent, "_client", render_agent.GatewayClient(r.identity, transport=env.rec))
    assert render_agent._beat() is True
    assert env.renderer(data["renderer_id"])["last_heartbeat_at"]


def test_reenrolling_keeps_the_machine_and_its_row(env, monkeypatch):
    r = _remote_env(env, monkeypatch)
    first = json.loads(r.state.read_text())
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, "")
    con.commit()
    con.close()
    render_agent.enroll(renderers.encode_enrollment_token(GATEWAY_URL, secret, r.pin), r.state, {}, env.rec)
    second = json.loads(r.state.read_text())
    assert second["machine_id"] == first["machine_id"] and second["renderer_id"] == first["renderer_id"]
    assert second["credential"] != first["credential"]
    assert len(env.sql("SELECT id FROM renderers WHERE builtin = 0")) == 1


def test_a_wrong_pin_aborts_enrollment_before_anything_is_sent(env, monkeypatch):
    r = _remote_env(env, monkeypatch)
    other = env.tmp / "other-tls"
    tauth.ensure_secrets(other)
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, "")
    con.commit()
    con.close()
    token = renderers.encode_enrollment_token(GATEWAY_URL, secret, tauth.gateway_pin(other))
    before = len(env.rec.requests)
    with pytest.raises(render_agent.EnrollmentError, match="nothing was sent"):
        render_agent.enroll(token, env.tmp / "state2" / "renderer.json", {}, transport=env.rec)
    assert len(env.rec.requests) == before
    assert env.sql("SELECT used_at FROM renderer_enrollments WHERE secret_hash = ?",
                   (renderers.hash_secret(secret),))[0]["used_at"] is None
    assert r.state.is_file()


def test_a_rotated_credential_is_saved_before_it_is_used(env, monkeypatch):
    r = _remote_env(env, monkeypatch)
    rid = r.identity.renderer_id
    env.sql("UPDATE renderers SET credential_issued_at = '2020-01-01T00:00:00Z' WHERE id = ?", (rid,))
    monkeypatch.setattr(render_agent, "_client", render_agent.GatewayClient(r.identity, transport=env.rec))
    assert render_agent._beat() is True
    saved = json.loads(r.state.read_text())
    assert saved["credential"] != r.credential and r.identity.credential() == saved["credential"]
    assert stat.S_IMODE(os.stat(r.state).st_mode) == 0o600
    assert render_agent._beat() is True                    # the new one authenticates
    assert env.rec.requests[-1]["auth"] == f"Bearer {saved['credential']}"
    assert env.renderer(rid)["previous_credential_hash"] == ""


def test_a_heartbeat_waits_while_a_rotated_credential_is_being_saved(env, monkeypatch):
    """Heartbeat A receives a rotated credential C1 and is slow to save it.
    Heartbeat B must not go out with the old credential meanwhile: the gateway
    would issue C2 in C1's place, and if A's save of C1 landed last the
    renderer would keep a credential nothing accepts."""
    r = _remote_env(env, monkeypatch)
    rid = r.identity.renderer_id
    env.sql("UPDATE renderers SET credential_issued_at = '2020-01-01T00:00:00Z' WHERE id = ?", (rid,))
    monkeypatch.setattr(render_agent, "_client", render_agent.GatewayClient(r.identity, transport=env.rec))
    real_save = r.identity.save_rotated
    in_save, release = threading.Event(), threading.Event()

    def slow_first_save(credential, expires_at):
        if not in_save.is_set():
            in_save.set()
            assert release.wait(10)
        real_save(credential, expires_at)
    monkeypatch.setattr(r.identity, "save_rotated", slow_first_save)
    results = {}
    a = threading.Thread(target=lambda: results.update(a=render_agent._beat()))
    a.start()
    assert in_save.wait(10)
    sent = len(env.rec.beats())
    b = threading.Thread(target=lambda: results.update(b=render_agent._beat()))
    b.start()
    b.join(0.3)
    assert b.is_alive() and len(env.rec.beats()) == sent       # B waits for A's save
    release.set()
    a.join(10)
    b.join(10)
    assert results == {"a": True, "b": True}
    saved = json.loads(r.state.read_text())["credential"]
    assert r.identity.credential() == saved
    assert render_agent._beat() is True                         # what was kept is what the gateway accepts
    assert env.rec.requests[-1]["auth"] == f"Bearer {saved}"


def test_httpx_request_lines_stay_out_of_the_renderers_log():
    """A claim every 20 s and a heartbeat every 30 s: httpx's INFO line per
    request would be thousands of lines a day. Its warnings still show."""
    import logging
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("render_agent").level == logging.NOTSET     # its own INFO lines are untouched


def test_a_rotated_credential_that_cannot_be_saved_is_not_used(env, monkeypatch):
    r = _remote_env(env, monkeypatch)

    def full_disk(path, data):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(render_agent, "_write_state", full_disk)
    r.identity.save_rotated("new-credential", "2099-01-01T00:00:00Z")
    assert r.identity.credential() == r.credential


def test_an_expired_credential_is_noted(env, monkeypatch, caplog):
    r = _remote_env(env, monkeypatch)
    env.sql("UPDATE renderers SET credential_expires_at = '2020-01-01T00:00:00Z' WHERE id = ?",
            (r.identity.renderer_id,))
    monkeypatch.setattr(render_agent, "_client", render_agent.GatewayClient(r.identity, transport=env.rec))
    assert render_agent._beat() is False
    assert "credential expired" in render_agent._st.last_error and "credential expired" in caplog.text
    assert r.credential not in caplog.text


def test_a_remote_renderer_stages_the_bundles_scenes_and_clears_them(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, builtin=False)
    r = _remote_env(env, monkeypatch)
    monkeypatch.setattr(render_agent, "_client", render_agent.GatewayClient(r.identity, transport=env.rec))
    (env.generated / "vid-1" / "sets").mkdir(parents=True)
    (env.generated / "vid-1" / "Intro.tsx").write_text("intro")
    (env.generated / "vid-1" / "sets" / "street.ts").write_text("street")
    (env.generated / "Legacy.tsx").write_text("legacy")
    (env.client_generated / "Leftover.tsx").write_text("another job's scene")
    seen = {}

    def look(argv, kw):
        seen["tree"] = sorted(str(p.relative_to(env.client_generated)) for p in env.client_generated.rglob("*")
                              if p.is_file())
    env.seed(scenes=[{"type": "generated", "src": "vid-1/Intro"}, {"type": "generated", "src": "Legacy"}])
    render_agent._beat()
    with mock.patch("subprocess.Popen", side_effect=FakeRemotion(on_start=look)):
        render_agent._loop_once()
    assert seen["tree"] == ["Legacy.tsx", "vid-1/Intro.tsx", "vid-1/sets/street.ts"]
    assert list(env.client_generated.iterdir()) == []
    assert env.video()["render_uploaded_at"] and env.video()["video_path"].endswith("vid-1.mp4")


def test_load_identity(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, builtin=False)
    monkeypatch.setenv("TUBEMATIC_RENDERER_STATE", str(tmp_path / "state"))
    with pytest.raises(render_agent.EnrollmentError, match="not enrolled"):
        render_agent._load_identity({}, transport=env.rec)
    r = _remote_env(env, monkeypatch)
    assert r.state == tmp_path / "state" / "renderer.json"
    # the token it already redeemed is not redeemed again on a restart
    monkeypatch.setenv("TUBEMATIC_ENROLL_TOKEN", r.token)
    before = len(env.rec.requests)
    ident = render_agent._load_identity({}, transport=env.rec)
    assert isinstance(ident, render_agent.RemoteIdentity) and ident.credential() == r.credential
    assert len(env.rec.requests) == before
    # a damaged state file is refused rather than trusted
    data = json.loads(r.state.read_text())
    data["pin"] = "sha256:" + "0" * 64
    r.state.write_text(json.dumps(data))
    monkeypatch.delenv("TUBEMATIC_ENROLL_TOKEN")
    with pytest.raises(render_agent.EnrollmentError, match="damaged"):
        render_agent._load_identity({}, transport=env.rec)
    monkeypatch.setenv("TUBEMATIC_RENDERER_BUILTIN", "1")
    assert isinstance(render_agent._load_identity({}), render_agent.BuiltinIdentity)


# ── what the renderer reports about itself ────────────────────────────────────

def test_the_compute_report(monkeypatch):
    monkeypatch.setattr(render_agent.shutil, "which", lambda name: None)
    monkeypatch.setenv("TUBEMATIC_GPU_UUID", "GPU-aaaa")
    monkeypatch.setenv("TUBEMATIC_GPU_NAME", "NVIDIA GeForce GTX 1650")
    report = render_agent._compute_report()
    assert report["cpus"] == os.cpu_count() and report["memory_bytes"] > 0
    assert report["gpus"] == [{"name": "NVIDIA GeForce GTX 1650", "uuid": "GPU-aaaa", "memory_mb": None}]
    monkeypatch.setattr(render_agent.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    smi = mock.Mock(returncode=0, stdout="NVIDIA GeForce GTX 1650, GPU-aaaa, 4096\n", stderr="")
    with mock.patch("subprocess.run", return_value=smi):
        assert render_agent._compute_report()["gpus"] == [
            {"name": "NVIDIA GeForce GTX 1650", "uuid": "GPU-aaaa", "memory_mb": 4096}]


def test_the_pinned_context_trusts_one_certificate_and_no_host_name(tmp_path):
    tauth.ensure_secrets(tmp_path)
    ctx = render_agent.pinned_context(tauth.read_secret(tauth.TLS_CERT_NAME, tmp_path))
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is False
    assert len(ctx.get_ca_certs()) == 1


def test_the_log_redacts_the_renderers_own_credential(env):
    assert render_agent._log_secrets() == [BUILTIN_TOKEN]


# ── real TLS ──────────────────────────────────────────────────────────────────

def test_enrollment_and_a_heartbeat_over_real_tls(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, builtin=False)
    tls = tmp_path / "tls"
    tauth.ensure_secrets(tls)
    seen = []
    inner = env.app.wsgi_app

    def counting(environ, start_response):
        seen.append(environ["PATH_INFO"])
        return inner(environ, start_response)
    env.app.wsgi_app = counting
    server = render_gateway.make_gateway_server(env.app, "127.0.0.1", 0, secrets_dir=tls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"https://127.0.0.1:{server.server_port}"
        monkeypatch.setenv("TUBEMATIC_GATEWAY_URL", url)

        def token(pin):
            con = sqlite3.connect(env.db)
            secret, _ = renderers.create_enrollment(con, "")
            con.commit()
            con.close()
            return renderers.encode_enrollment_token(url, secret, pin)
        other = tmp_path / "other"
        tauth.ensure_secrets(other)
        with pytest.raises(render_agent.EnrollmentError, match="nothing was sent"):
            render_agent.enroll(token(tauth.gateway_pin(other)), tmp_path / "s1" / "renderer.json", {})
        assert seen == []
        identity = render_agent.enroll(token(tauth.gateway_pin(tls)), tmp_path / "s2" / "renderer.json", {})
        assert seen == ["/v1/enroll"]
        monkeypatch.setattr(render_agent, "_client", render_agent.GatewayClient(identity))
        assert render_agent._beat() is True
        assert seen == ["/v1/enroll", "/v1/heartbeat"]
        assert env.renderer(identity.renderer_id)["last_heartbeat_at"]
        # a client pinned to another certificate never gets an answer
        data = dict(identity.data, cert_pem=tauth.read_secret(tauth.TLS_CERT_NAME, other))
        stranger = render_agent.GatewayClient(render_agent.RemoteIdentity(tmp_path / "s3.json", data))
        with pytest.raises(render_agent.GatewayError):
            stranger.send("POST", "/v1/heartbeat", json_body={})
        assert seen == ["/v1/enroll", "/v1/heartbeat"]
    finally:
        server.shutdown()
        thread.join(5)
