"""The worker's segmented Cartoon 3D render (TMDEV-185): how a video is cut
into segments, which audio is muxed, and the render itself over a stub
Remotion and a stub ffmpeg.

One whole-video `remotion render` of a Cartoon 3D Short hung silently part
way on the GPU, so the worker renders segments of CARTOON_CHUNK_FRAMES frames,
each in a fresh process with the stall watcher, joins them without
re-encoding and muxes the soundtrack on: the synthesised mix when it is there
and at least as new as the voice, else the voice. Pins the segment plan, the
audio choice, that a stalled segment is tried again fresh and reported as
"hung" (requeued by the caller), that a failed segment is "failed", and the
ffmpeg commands.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pipeline  # noqa: E402
import worker  # noqa: E402


def test_the_segment_plan_tiles_the_video_and_folds_a_short_tail():
    assert worker._cartoon_chunks(0) == []
    assert worker._cartoon_chunks(10) == [(0, 9)]
    assert worker._cartoon_chunks(450) == [(0, 449)]
    assert worker._cartoon_chunks(900) == [(0, 449), (450, 899)]
    assert worker._cartoon_chunks(1000) == [(0, 449), (450, 999)]        # a 100-frame tail joins the segment before it
    assert worker._cartoon_chunks(1100) == [(0, 449), (450, 899), (900, 1099)]
    plan = worker._cartoon_chunks(3614)
    assert plan[0][0] == 0 and plan[-1][1] == 3613
    assert all(plan[i][1] + 1 == plan[i + 1][0] for i in range(len(plan) - 1))


def test_the_scene_config_marker_is_the_cartoon3d_props(tmp_path):
    p = tmp_path / "scene-config.json"
    p.write_text(json.dumps({"scenes": [{"src": "v/CartoonShort", "props": {"cartoon3d": {"beats": []}}}]}))
    assert worker._scene_config_is_cartoon3d(p)
    p.write_text(json.dumps({"scenes": [{"src": "Cartoon3D", "source": "installed", "props": {"world": {}}}]}))
    assert not worker._scene_config_is_cartoon3d(p)          # the data-driven marker of 2.0 is not one any more
    p.write_text(json.dumps({"scenes": [{"src": "v/intro", "props": {"cartoon3d": "yes"}}]}))
    assert not worker._scene_config_is_cartoon3d(p)
    p.write_text("not json")
    assert not worker._scene_config_is_cartoon3d(p)


def test_the_mix_is_muxed_only_when_it_is_at_least_as_new_as_the_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "JOBS_DIR", tmp_path / "jobs")
    job = tmp_path / "jobs" / "vid-1"
    job.mkdir(parents=True)
    voice = job / "audio.mp3"
    voice.write_bytes(b"v")
    assert worker._soundtrack_for("vid-1", voice) == voice                 # no mix
    mix = job / "cartoon" / "audio" / "mix" / "mix.wav"
    mix.parent.mkdir(parents=True)
    mix.write_bytes(b"m")
    os.utime(mix, (1_000, 1_000))
    os.utime(voice, (2_000, 2_000))
    assert worker._soundtrack_for("vid-1", voice) == voice                 # a re-voiced video: the old mix is stale
    os.utime(mix, (3_000, 3_000))
    assert worker._soundtrack_for("vid-1", voice) == mix


@pytest.fixture
def stubs(tmp_path, monkeypatch):
    """Popen renders a segment by writing its output file (or hangs / fails
    per the plan), subprocess.run stands in for ffmpeg; both are logged."""
    monkeypatch.setattr(pipeline, "JOBS_DIR", tmp_path / "jobs")
    (tmp_path / "jobs" / "vid-1").mkdir(parents=True)
    voice = tmp_path / "jobs" / "vid-1" / "audio.mp3"
    voice.write_bytes(b"v")
    monkeypatch.setattr(worker, "REMOTION_DIR", tmp_path / "remotion")
    # the frozen source every render is checked against: a one-file tree and its record
    from tubematic_core import jobfiles as tjobs
    generated = tmp_path / "generated"
    (generated / "vid-1").mkdir(parents=True)
    (generated / "vid-1" / "CartoonShort.tsx").write_text("export default () => null;")
    monkeypatch.setattr(worker, "GENERATED_DIR", generated)
    record = tmp_path / "jobs" / "vid-1" / "cartoon" / "source.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(generated / "vid-1"), "at": "now"}))
    calls = {"popen": [], "run": []}
    plan = {"fail_once": set(), "hang_always": set()}

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

    def popen(argv, **kw):
        calls["popen"].append(argv)
        return FakeProc(argv)

    def run(argv, **kw):
        calls["run"].append(argv)
        Path(argv[-1]).write_bytes(b"out")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(worker, "_kill_group_and_reap", lambda proc: calls.setdefault("killed", []).append(proc.args))
    # a stall is detected at once: the fake clock jumps past stall_secs on every look
    ticks = iter(range(0, 10_000, 100))
    monkeypatch.setattr(worker, "_clock", lambda: next(ticks))
    monkeypatch.setattr(worker, "_sleep", lambda s: None)
    return calls, plan, voice, tmp_path / "out" / "vid-1.mp4"


def test_a_segmented_render_joins_the_segments_and_muxes_the_voice(stubs):
    calls, _, voice, out = stubs
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), ["--gl=angle-egl"], {}, 6000, 60, 1000, voice)
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
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "ok" and detail == "1 segments, the synthesised soundtrack"
    assert str(mix) in calls["run"][1]


def test_a_failed_segment_is_tried_once_more_and_then_reported(stubs):
    calls, plan, voice, out = stubs
    plan["fail_once"].add("450-999")
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "ok"
    assert len(calls["popen"]) == 3          # segment two failed once and rendered on its second attempt
    plan["fail_once"].update({"0-449"})
    calls["popen"].clear()
    # a segment that fails twice (fail_once refills itself here) is the render's failure
    class AlwaysFail(set):
        def discard(self, x): pass
    plan["fail_once"] = AlwaysFail({"0-449"})
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "failed" and "frames 0-449" in detail and "shader failed" in detail
    assert len(calls["popen"]) == 2


def test_a_stalled_segment_is_killed_tried_again_and_reported_as_hung(stubs):
    calls, plan, voice, out = stubs
    plan["hang_always"].add("0-449")
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "hung" and detail == "frames 0-449: no progress for 60s"
    assert len(calls["popen"]) == 2 and len(calls["killed"]) == 2
    assert not calls["run"]                 # nothing joined, nothing muxed
    assert not (out.parent / ".vid-1.segments").exists()


def test_the_timeout_caps_the_whole_render_segments_and_retries_included(stubs):
    """render_timeout_secs is the ceiling on one whole render, as it is for an
    ordinary one: the fake clock advances 100 per look, so a 250 s ceiling is
    spent by the first segment and the second never starts."""
    calls, _, voice, out = stubs
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 250, 60, 1000, voice)
    assert outcome == "hung" and detail == "frames 450-999: the render ran past 250s in all"
    assert len(calls["popen"]) == 1 and not calls["run"]
    assert not (out.parent / ".vid-1.segments").exists() and not out.exists()


def test_a_render_that_cannot_run_is_a_failure_of_that_video(stubs, monkeypatch):
    calls, _, voice, out = stubs

    def no_npx(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", "npx")
    monkeypatch.setattr(subprocess, "Popen", no_npx)
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
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
    assert worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)[0] == "ok"

    (src / "sets" / "street.ts").write_text("export const STREET = 2;")
    calls["popen"].clear()
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "changed after the beat gate passed" in detail and not calls["popen"]

    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(src), "at": "now"}))
    (src / "evil.ts").symlink_to(src / "sets" / "street.ts")
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
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
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 1000, voice)
    assert outcome == "failed" and "changed after the beat gate passed" in detail and not out.exists()
    assert len(calls["popen"]) == 1               # the first segment rendered, the second was never started
    monkeypatch.setattr(subprocess, "Popen", real_popen)

    # no record, or a record that is not a plain file, is no render: only submit_render queues
    # a Cartoon 3D video and it always writes the record
    record.unlink()
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and detail.startswith("no record of the source that was queued")
    record.symlink_to(voice)
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "is a symlink" in detail
    record.unlink()
    record.write_text(json.dumps({"fingerprint": tjobs.source_fingerprint(src), "at": "now"}))
    assert worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)[0] == "ok"
    # a link planted as the `cartoon` directory itself would redirect the record: refused on the way
    import shutil as _shutil
    _shutil.move(record.parent, tmp_path / "elsewhere")
    record.parent.symlink_to(tmp_path / "elsewhere")
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "failed" and "symlink" in detail


def test_ffmpeg_spends_what_is_left_of_the_same_deadline(stubs, monkeypatch):
    """concat and mux get min(FFMPEG_TIMEOUT_SECS, what remains of
    render_timeout_secs), so the whole render, ffmpeg included, stays under
    the one ceiling; a deadline already spent is a hang, not a mux."""
    calls, _, voice, out = stubs
    timeouts = []
    real_run = subprocess.run

    def run(argv, **kw):
        timeouts.append(kw.get("timeout"))
        return real_run(argv, **kw)
    monkeypatch.setattr(subprocess, "run", run)
    # the fake clock advances 100 per look: of the 1000 s, 400 are left at the concat and 300 at the mux
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 1000, 60, 100, voice)
    assert outcome == "ok" and timeouts == [400, 300]
    timeouts.clear()
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 6000, 60, 100, voice)
    assert outcome == "ok" and timeouts == [worker.FFMPEG_TIMEOUT_SECS, worker.FFMPEG_TIMEOUT_SECS]
    timeouts.clear()
    outcome, detail = worker._render_cartoon("vid-1", "{}", str(out), [], {}, 450, 60, 100, voice)
    assert outcome == "hung" and detail == "joining the segments: the render ran past 450s in all" and not timeouts


def test_a_render_that_raises_is_that_videos_failure_not_the_workers_exit(monkeypatch):
    failures = []
    monkeypatch.setattr(worker, "_stage_and_render", mock.Mock(side_effect=OSError(28, "No space left on device")))
    monkeypatch.setattr(worker, "_handle_render_failure", lambda vid, msg, retry_status="REVISION_REQUESTED": failures.append((vid, msg, retry_status)))
    worker._render_claimed("vid-9")             # does not raise
    assert failures == [("vid-9", "The worker hit an error: [Errno 28] No space left on device", "RENDER_QUEUED")]
