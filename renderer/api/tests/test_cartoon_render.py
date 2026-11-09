"""The renderer's segmented Cartoon 3D render (TMDEV-185): how a video is cut
into segments, which audio is muxed, and the render itself over a stub
Remotion and a stub ffmpeg. The job directory is the renderer's own copy of
the job, unpacked from the gateway's bundle (TMDEV-189); the generated source
checked against submit_render's record is the tree Remotion compiles.

One whole-video `remotion render` of a Cartoon 3D Short hung silently part
way on the GPU, so the renderer renders segments of CARTOON_CHUNK_FRAMES frames,
each in a fresh process with the stall watcher, joins them without
re-encoding and muxes the soundtrack on: the synthesised mix when it is there
and at least as new as the voice, else the voice. Pins the segment plan, the
audio choice, that a stalled segment is tried again fresh and reported as
"hung" (requeued by the caller), that a failed segment is "failed", and the
ffmpeg commands — run like the segments, as the job's own process in a
process group of its own, so a stop from the gateway or the timeout kills them.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import render_agent  # noqa: E402

_REAL_POPEN = subprocess.Popen     # before any fixture stubs it
_REAL_KILL = render_agent._kill_group_and_reap


def test_the_segment_plan_tiles_the_video_and_folds_a_short_tail():
    assert render_agent._cartoon_chunks(0) == []
    assert render_agent._cartoon_chunks(10) == [(0, 9)]
    assert render_agent._cartoon_chunks(450) == [(0, 449)]
    assert render_agent._cartoon_chunks(900) == [(0, 449), (450, 899)]
    assert render_agent._cartoon_chunks(1000) == [(0, 449), (450, 999)]        # a 100-frame tail joins the segment before it
    assert render_agent._cartoon_chunks(1100) == [(0, 449), (450, 899), (900, 1099)]
    plan = render_agent._cartoon_chunks(3614)
    assert plan[0][0] == 0 and plan[-1][1] == 3613
    assert all(plan[i][1] + 1 == plan[i + 1][0] for i in range(len(plan) - 1))


def test_the_mix_is_muxed_only_when_it_is_at_least_as_new_as_the_voice(tmp_path):
    job = tmp_path / "jobs" / "vid-1"
    job.mkdir(parents=True)
    voice = job / "audio.mp3"
    voice.write_bytes(b"v")
    assert render_agent._soundtrack_for(job, voice) == voice                 # no mix
    mix = job / "cartoon" / "audio" / "mix" / "mix.wav"
    mix.parent.mkdir(parents=True)
    mix.write_bytes(b"m")
    os.utime(mix, (1_000, 1_000))
    os.utime(voice, (2_000, 2_000))
    assert render_agent._soundtrack_for(job, voice) == voice                 # a re-voiced video: the old mix is stale
    os.utime(mix, (3_000, 3_000))
    assert render_agent._soundtrack_for(job, voice) == mix


@pytest.fixture
def stubs(tmp_path, monkeypatch):
    """Popen renders a segment by writing its output file (or hangs / fails
    per the plan), or stands in for ffmpeg (its output written when it is
    communicated with, or a timeout per the plan); all are logged."""
    (tmp_path / "jobs" / "vid-1").mkdir(parents=True)
    voice = tmp_path / "jobs" / "vid-1" / "audio.mp3"
    voice.write_bytes(b"v")
    monkeypatch.setattr(render_agent, "REMOTION_DIR", tmp_path / "remotion")
    # the frozen source every render is checked against: a one-file tree and its record
    from tubematic_core import jobfiles as tjobs
    generated = tmp_path / "generated"
    (generated / "vid-1").mkdir(parents=True)
    (generated / "vid-1" / "CartoonShort.tsx").write_text("export default () => null;")
    monkeypatch.setattr(render_agent, "GENERATED_DIR", generated)
    record = tmp_path / "jobs" / "vid-1" / "cartoon" / "source.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(generated / "vid-1"), "at": "now"}))
    calls = {"popen": [], "run": [], "ffmpeg_kw": [], "timeouts": []}
    plan = {"fail_once": set(), "hang_always": set(), "ffmpeg_hangs": False}

    class FakeProc:
        def __init__(self, argv):
            import io
            self.args = argv
            self.pid = 4242
            frames = next(a for a in argv if a.startswith("--frames=")).split("=")[1]
            out = Path(argv[argv.index("Composition") + 1])
            self.hang = frames in plan["hang_always"]
            if frames in plan["fail_once"]:
                plan["fail_once"].discard(frames)
                self.returncode, text = 1, "Error: a shader failed to compile"
            elif self.hang:
                self.returncode, text = None, "Rendered 1/450"
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"mp4")
                self.returncode, text = 0, "Rendered 450/450\nEncoded 450/450"
            self.stdout = io.StringIO(text)
            self.stderr = io.StringIO("")

        def poll(self):
            return self.returncode

    class FakeFfmpeg:
        def __init__(self, argv):
            self.args = argv
            self.pid = 4343
            self.returncode = None

        def communicate(self, timeout=None):
            calls["timeouts"].append(timeout)
            if plan["ffmpeg_hangs"]:
                raise subprocess.TimeoutExpired(self.args, timeout)
            Path(self.args[-1]).write_bytes(b"out")
            self.returncode = 0
            return "", ""

        def poll(self):
            return self.returncode

    def popen(argv, **kw):
        if argv[0] == "ffmpeg":
            calls["run"].append(argv)
            calls["ffmpeg_kw"].append(kw)
            return FakeFfmpeg(argv)
        calls["popen"].append(argv)
        return FakeProc(argv)

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(render_agent, "_kill_group_and_reap", lambda proc: calls.setdefault("killed", []).append(proc.args))
    # a stall is detected at once: the fake clock jumps past stall_secs on every look
    ticks = iter(range(0, 10_000, 100))
    monkeypatch.setattr(render_agent, "_clock", lambda: next(ticks))
    monkeypatch.setattr(render_agent, "_sleep", lambda s: None)
    return calls, plan, voice, tmp_path / "out" / "vid-1.mp4"


def test_a_segmented_render_joins_the_segments_and_muxes_the_voice(stubs):
    calls, _, voice, out = stubs
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), ["--gl=angle-egl"], {}, 6000, 60, 1000, voice)
    assert outcome == "ok" and detail == "2 segments, the voice alone"
    assert [next(a for a in argv if a.startswith("--frames=")) for argv in calls["popen"]] == ["--frames=0-449", "--frames=450-999"]
    for argv in calls["popen"]:
        assert argv[:4] == ["npx", "remotion", "render", "Composition"] and "--muted" in argv and "--concurrency=2" in argv and "--gl=angle-egl" in argv
    concat, mux = calls["run"]
    assert concat[0] == "ffmpeg" and "concat" in concat and concat[-3:-1] == ["-c", "copy"]
    assert mux[0] == "ffmpeg" and str(voice) in mux and "-c:v" in mux and mux[mux.index("-c:a") + 1] == "aac" and mux[-1].endswith(".tmp.mp4")
    assert out.is_file() and not (out.parent / ".vid-1.segments").exists()   # the work directory is gone


def test_the_synthesised_mix_is_muxed_when_present(stubs):
    calls, _, voice, out = stubs
    mix = voice.parent / "cartoon" / "audio" / "mix" / "mix.wav"
    mix.parent.mkdir(parents=True)
    mix.write_bytes(b"m")
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "ok" and detail == "1 segments, the synthesised soundtrack"
    assert str(mix) in calls["run"][1]


def test_a_failed_segment_is_tried_once_more_and_then_reported(stubs):
    calls, plan, voice, out = stubs
    plan["fail_once"].add("450-999")
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "ok"
    assert len(calls["popen"]) == 3          # segment two failed once and rendered on its second attempt
    plan["fail_once"].update({"0-449"})
    calls["popen"].clear()
    # a segment that fails twice (fail_once refills itself here) is the render's failure
    class AlwaysFail(set):
        def discard(self, x): pass
    plan["fail_once"] = AlwaysFail({"0-449"})
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "failed" and "frames 0-449" in detail and "shader failed" in detail
    assert len(calls["popen"]) == 2


def test_a_stalled_segment_is_killed_tried_again_and_reported_as_hung(stubs):
    calls, plan, voice, out = stubs
    plan["hang_always"].add("0-449")
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "hung" and detail == "frames 0-449: no progress for 60s"
    assert len(calls["popen"]) == 2 and len(calls["killed"]) == 2
    assert not calls["run"]                 # nothing joined, nothing muxed
    assert not (out.parent / ".vid-1.segments").exists()


def test_the_timeout_caps_the_whole_render_segments_and_retries_included(stubs):
    """render_timeout_secs is the ceiling on one whole render, as it is for an
    ordinary one: the fake clock advances 100 per look, so a 250 s ceiling is
    spent by the first segment and the second never starts."""
    calls, _, voice, out = stubs
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 250, 60, 1000, voice)
    assert outcome == "hung" and detail == "frames 450-999: the render ran past 250s in all"
    assert len(calls["popen"]) == 1 and not calls["run"]
    assert not (out.parent / ".vid-1.segments").exists() and not out.exists()


def test_a_render_that_cannot_run_is_a_failure_of_that_video(stubs, monkeypatch):
    calls, _, voice, out = stubs

    def no_npx(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", "npx")
    monkeypatch.setattr(subprocess, "Popen", no_npx)
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and detail.startswith("the render could not be run: ") and "npx" in detail
    assert not (out.parent / ".vid-1.segments").exists()


def test_the_source_rendered_is_the_one_submit_render_froze(stubs, monkeypatch, tmp_path):
    """submit_render records the fingerprint of the gated source under the job;
    a tree that differs from it (edited after the gate, or with a symlink in it)
    is not rendered, before the first segment and again before the mux."""
    from tubematic_core import jobfiles as tjobs
    calls, _, voice, out = stubs
    generated = tmp_path / "generated"
    src = generated / "vid-1"
    (src / "sets").mkdir(parents=True)
    (src / "sets" / "street.ts").write_text("export const STREET = 1;")
    record = voice.parent / "cartoon" / "source.json"
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(src), "at": "now"}))
    assert render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)[0] == "ok"

    (src / "sets" / "street.ts").write_text("export const STREET = 2;")
    calls["popen"].clear()
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "changed after the beat gate passed" in detail and not calls["popen"]

    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(src), "at": "now"}))
    (src / "evil.ts").symlink_to(src / "sets" / "street.ts")
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "symlink" in detail

    # a source that changes under a running render is caught before the next segment bundles it
    (src / "evil.ts").unlink()
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(src), "at": "now"}))
    real_popen = subprocess.Popen

    def popen_and_edit(argv, **kw):
        (src / "sets" / "street.ts").write_text("export const STREET = 3;")
        return real_popen(argv, **kw)
    monkeypatch.setattr(subprocess, "Popen", popen_and_edit)
    calls["popen"].clear()
    out.unlink()
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "failed" and "changed after the beat gate passed" in detail and not out.exists()
    assert len(calls["popen"]) == 1               # the first segment rendered, the second was never started
    monkeypatch.setattr(subprocess, "Popen", real_popen)

    # no record, or a record that is not a plain file, is no render: only submit_render queues
    # a Cartoon 3D video and it always writes the record
    record.unlink()
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and detail.startswith("no record of the source that was queued")
    record.symlink_to(voice)
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "is a symlink" in detail
    record.unlink()
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(src), "at": "now"}))
    assert render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)[0] == "ok"
    # a link planted as the `cartoon` directory itself would redirect the record: refused on the way
    import shutil as _shutil
    _shutil.move(record.parent, tmp_path / "elsewhere")
    record.parent.symlink_to(tmp_path / "elsewhere")
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "symlink" in detail


def test_ffmpeg_spends_what_is_left_of_the_same_deadline(stubs, monkeypatch):
    """concat and mux get min(FFMPEG_TIMEOUT_SECS, what remains of
    render_timeout_secs), so the whole render, ffmpeg included, stays under
    the one ceiling; a deadline already spent is a hang, not a mux."""
    calls, _, voice, out = stubs
    timeouts = calls["timeouts"]
    # the fake clock advances 100 per look: of the 1000 s, 400 are left at the concat and 300 at the mux
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 1000, 60, 100, voice)
    assert outcome == "ok" and timeouts == [400, 300]
    timeouts.clear()
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "ok" and timeouts == [render_agent.FFMPEG_TIMEOUT_SECS, render_agent.FFMPEG_TIMEOUT_SECS]
    timeouts.clear()
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 450, 60, 100, voice)
    assert outcome == "hung" and detail == "joining the segments: the render ran past 450s in all" and not timeouts


# ── the ffmpeg steps are job processes ───────────────────────────────────────

def test_ffmpeg_runs_as_the_jobs_own_process_in_a_group_of_its_own(stubs, monkeypatch):
    """Registered on the job like a segment, so a stop from the gateway finds
    it, and in its own process group, so killing it reaps the whole step."""
    calls, _, voice, out = stubs
    monkeypatch.setattr(render_agent, "_st", render_agent._AgentState())
    job = render_agent._st.job = render_agent._Job("vid-1", "c-1")
    outcome, _ = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "ok" and len(calls["ffmpeg_kw"]) == 2
    assert all(kw["start_new_session"] is True and kw["stdout"] == subprocess.PIPE for kw in calls["ffmpeg_kw"])
    assert job.proc.args == calls["run"][-1]           # the mux was the job's live process


def test_a_stopped_job_never_starts_ffmpeg(stubs, monkeypatch):
    calls, _, voice, out = stubs
    monkeypatch.setattr(render_agent, "_st", render_agent._AgentState())
    job = render_agent._st.job = render_agent._Job("vid-1", "c-1")
    stub_popen = subprocess.Popen

    def stop_while_the_segment_renders(argv, **kw):
        job.stopped = True           # the stop lands mid-segment: _spawn then refuses the join
        return stub_popen(argv, **kw)
    monkeypatch.setattr(subprocess, "Popen", stop_while_the_segment_renders)
    with pytest.raises(render_agent._Stopped):
        render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert not calls["run"]


def test_an_ffmpeg_step_past_its_timeout_is_killed_and_reaped(stubs):
    calls, plan, voice, out = stubs
    plan["ffmpeg_hangs"] = True
    outcome, detail = render_agent._render_cartoon("vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and detail.startswith("ffmpeg did not finish")
    assert calls["killed"] == [calls["run"][0]]        # the join's group, killed and reaped
    assert not out.exists() and not (out.parent / ".vid-1.segments").exists()


def test_a_stop_during_a_blocked_ffmpeg_kills_it_promptly(stubs, monkeypatch, tmp_path):
    """A real (fake) ffmpeg that would block for a minute: a stop from the
    heartbeat thread kills its process group at once and the render returns,
    instead of the step running out its 900 s timeout."""
    calls, _, voice, out = stubs
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ffmpeg").write_text("#!/bin/sh\nexec sleep 60\n")
    (bin_dir / "ffmpeg").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(render_agent, "_kill_group_and_reap", _REAL_KILL)
    stub_popen = subprocess.Popen
    started = {}

    def popen(argv, **kw):
        if argv[0] == "ffmpeg":
            started["proc"] = _REAL_POPEN(argv, **kw)
            return started["proc"]
        return stub_popen(argv, **kw)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(render_agent, "_st", render_agent._AgentState())
    job = render_agent._st.job = render_agent._Job("vid-1", "c-1")
    result = {}
    t = threading.Thread(target=lambda: result.update(out=render_agent._render_cartoon(
        "vid-1", voice.parent, "{}", str(out), [], {}, 6000, 60, 100, voice)), daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while "proc" not in started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert "proc" in started and job.proc is started["proc"]
    t0 = time.monotonic()
    render_agent._stop_job(job)
    t.join(10)
    assert not t.is_alive() and time.monotonic() - t0 < 10
    assert started["proc"].returncode is not None      # killed, not left to run out its minute
    assert result["out"][0] == "failed" and job.stopped
