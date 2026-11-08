"""Tests for the Cartoon 3D authoring tools (mcp/cartoon.py and the
cartoon_* tools of server.py), as far as Python can reach them (TMDEV-185).

The beat gate and the stills are the renderer's Node command lines; what
Python owns is the plumbing a judge and the render depend on: where a video's
verdicts live, that a still's name can only ever be a file under that
directory, that the beat gate is run over the video's generated source tree
(the hash that keys its verdict), that a judge prompt names stills by the
call that shows them and ends in the record call the judge makes itself, that
the soundtrack is driven by a checked spec and lands where the worker muxes
it, and that the readiness check (the thing validate_job and submit_render
ask) stops a render without a source or without the judges' PASS. The command
lines are stood in for by a stub `node` on PATH that plays back a plan, so
nothing here bundles or renders.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cartoon
import server

VID = "vid-cartoon"

CARTOON_CONFIG = {
    "totalFrames": 100, "fps": 30,
    "scenes": [{"type": "generated", "src": f"{VID}/CartoonShort", "startFrame": 0, "durationInFrames": 100,
                "props": {"cartoon3d": {"beats": [{"start": 0, "end": 99, "shot": "the quay"}]}}}],
}
PLAIN_CONFIG = {"totalFrames": 100, "fps": 30, "scenes": [{"type": "generated", "src": "hero", "props": {}}]}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def fake_node(tmp_path, monkeypatch):
    """A stub `node` that plays back a plan keyed by command line ("beatgate",
    "beatgate --status", "beatgate --record", "still"): writes the files the
    plan names, prints its stdout, exits with its code, and logs every call.
    Returns (plan writer, remotion dir, call log path)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    plan_file = tmp_path / "plan.json"
    log_file = tmp_path / "calls.jsonl"
    (bin_dir / "node").write_text(f"""#!{sys.executable}
import json, os, sys
script = os.path.basename(sys.argv[1])
if script == "build.mjs":
    sys.exit(0)
plan = json.load(open({str(plan_file)!r}))
name = script[:-4]
flags = [a for a in sys.argv[2:] if a.startswith("--") and a != "--source"]
key = name + (" " + flags[0] if flags else "")
spec = plan.get(key) or plan.get(name) or {{}}
for path, content in (spec.get("files") or {{}}).items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(content)
with open({str(log_file)!r}, "a") as fh:
    fh.write(json.dumps({{"key": key, "argv": sys.argv[1:],
        "env": {{k: os.environ.get(k) for k in ("REMOTION_ROOT", "BEAT_PROPS", "CARTOON_BROWSER", "CARTOON_PUBLIC_DIR", "STILLS_SERVER")}}}}) + "\\n")
sys.stdout.write(spec.get("stdout", ""))
sys.exit(spec.get("code", 0))
""")
    (bin_dir / "node").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setattr(cartoon, "_built", set())
    remotion = tmp_path / "remotion"
    (remotion / "cartoon-tools").mkdir(parents=True)
    (remotion / "cartoon-tools" / "build.mjs").write_text("// stub")
    (remotion / "public").mkdir()

    def plan(spec: dict):
        plan_file.write_text(json.dumps(spec))

    plan({})
    return plan, remotion, log_file


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    """A jobs directory with this video's three job files; returns its path."""
    jobs_dir = tmp_path / "jobs"
    monkeypatch.setattr(server, "JOBS_DIR", jobs_dir)
    d = jobs_dir / VID
    d.mkdir(parents=True)
    (d / "scene-config.json").write_text(json.dumps(CARTOON_CONFIG))
    (d / "timeline.json").write_text(json.dumps({"totalFrames": 100, "fps": 30, "words": []}))
    (d / "audio.mp3").write_bytes(b"\x00" * 100)
    return jobs_dir


@pytest.fixture
def scenes(tmp_path, monkeypatch):
    """A generated scene tree with this video's CartoonShort and a module."""
    scenes_dir = tmp_path / "scenes" / "generated"
    monkeypatch.setattr(server, "SCENES_DIR", scenes_dir)
    (scenes_dir / VID).mkdir(parents=True)
    (scenes_dir / VID / "CartoonShort.tsx").write_text("export default () => null;")
    (scenes_dir / VID / "story.ts").write_text("export const TOTAL = 100;")
    return scenes_dir


def _calls(log_file):
    return [json.loads(line) for line in log_file.read_text().splitlines()] if log_file.exists() else []


# ── The scene and the still names ──────────────────────────────────────────────

def test_a_cartoon_video_is_one_generated_scene_whose_props_carry_the_beats():
    assert cartoon.is_cartoon(CARTOON_CONFIG)
    assert cartoon.cartoon_scene(CARTOON_CONFIG)["src"] == f"{VID}/CartoonShort"
    assert not cartoon.is_cartoon(PLAIN_CONFIG)
    assert not cartoon.is_cartoon({"scenes": [{"src": "x", "props": {"cartoon3d": "yes"}}]})
    assert not cartoon.is_cartoon({"scenes": [{"src": "x", "props": {"cartoon3d": {"beats": "none"}}}]})
    assert not cartoon.is_cartoon([]) and not cartoon.is_cartoon({"scenes": "x"})


def test_a_still_is_a_plain_file_name_under_the_video(tmp_path):
    p = cartoon.still_file(tmp_path, VID, "beatgate", "beat03-f0184.png")
    assert p == tmp_path / VID / "cartoon" / "beatgate" / "beat03-f0184.png"
    assert cartoon.still_file(tmp_path, VID, "stills", "f0460.png") == tmp_path / VID / "cartoon" / "stills" / "f0460.png"
    for bad in ("../x.png", "a/b.png", "x.jpg", "", ".png", "x.png/"):
        with pytest.raises(cartoon.CartoonError):
            cartoon.still_file(tmp_path, VID, "beatgate", bad)
    for kind in ("gate", "secrets", "audio"):      # the part gate is gone; nothing else is a still kind
        with pytest.raises(cartoon.CartoonError, match="kind"):
            cartoon.still_file(tmp_path, VID, kind, "x.png")


def test_the_judge_prompt_names_stills_by_the_call_that_shows_them(tmp_path):
    base = cartoon.cartoon_dir(tmp_path, VID) / "beatgate"
    text = f"Beat 0: frame: {base}/beat00-f0050.png\nBeat 1: frame: {base}/beat01-f0150.png\nWrite your answer as JSON only to the file named in your instructions:"
    out = cartoon._prompt_for_judge(text, tmp_path, VID, "beatgate", f'cartoon_beat_gate_record("{VID}", <your JSON>)')
    assert str(base) not in out
    assert f'still "beat00-f0050.png" (call cartoon_read_still("{VID}", "beatgate", "beat00-f0050.png"))' in out
    assert out.endswith(f'then call cartoon_beat_gate_record("{VID}", <your JSON>) with it yourself:')


# ── The beat gate over the video's source ───────────────────────────────────────

def test_the_beat_gate_runs_over_the_job_directory_and_the_video_source(fake_node, jobs, scenes, monkeypatch):
    plan, remotion, log = fake_node
    monkeypatch.setenv("TUBEMATIC_STILLS_SERVER", "http://tubematic-renderer:4455")
    status = json.dumps({"hash": "abc", "pass": False, "need": "two judges", "judges": 0, "tie": [], "fails": [], "summary": "no judge yet", "beats": 1,
                         "stills": [str(jobs / VID / "cartoon" / "beatgate" / "beat00-f0050.png")], "prompt": None})
    plan({"beatgate": {"stdout": "1 beat stills\n", "code": 2}, "beatgate --status": {"stdout": "chatter\n" + status + "\n", "code": 2}})
    result = cartoon.beat_gate(jobs, VID, remotion, scenes)
    assert result["passed"] is False and result["need"] == "two judges" and result["stills"] == ["beat00-f0050.png"]
    run, stat = _calls(log)
    assert run["key"] == "beatgate" and stat["key"] == "beatgate --status"
    # the job directory (the jobs volume is /public/), the verdict directory, and the SOURCE tree the hash is keyed by
    assert Path(run["argv"][1]) == jobs / VID
    assert Path(run["argv"][2]) == jobs / VID / "cartoon" / "beatgate"
    assert run["argv"][3:5] == ["--source", str(scenes / VID)]
    assert json.loads(run["env"]["BEAT_PROPS"])["sceneConfigPath"] == f"/public/{VID}/scene-config.json"
    assert run["env"]["CARTOON_PUBLIC_DIR"] == str(jobs)
    assert run["env"]["STILLS_SERVER"] == "http://tubematic-renderer:4455"   # the worker's server, on the GPU
    assert run["env"]["REMOTION_ROOT"] == str(remotion)
    assert not (remotion / "public" / VID).exists()   # nothing staged


def test_a_video_without_its_source_cannot_be_gated(fake_node, jobs, scenes):
    _, remotion, _ = fake_node
    (scenes / VID / "CartoonShort.tsx").unlink()
    with pytest.raises(cartoon.CartoonError, match="write_scene_file"):
        cartoon.beat_gate(jobs, VID, remotion, scenes)
    assert cartoon.readiness(jobs, VID, remotion, scenes) == [
        f"Cartoon 3D source: {VID} has no generated source yet: write {VID}/CartoonShort (and its modules) with write_scene_file first"]


# ── Readiness ──────────────────────────────────────────────────────────────────

def test_readiness_reports_an_open_beat_gate_and_nothing_when_it_passed(fake_node, jobs, scenes):
    plan, remotion, log = fake_node
    plan({"beatgate --status": {"stdout": json.dumps({"hash": "abc", "pass": False, "need": "a second judge", "judges": 1, "tie": [], "fails": [], "summary": "1 of 2 judges recorded", "beats": 1, "stills": [], "prompt": None}) + "\n", "code": 2}})
    errors = cartoon.readiness(jobs, VID, remotion, scenes)
    assert errors == ["Cartoon 3D beat gate: 1 of 2 judges recorded — call cartoon_beat_gate and have fresh judges answer"]
    assert [c["key"] for c in _calls(log)] == ["beatgate --status"]
    assert _calls(log)[0]["argv"][3:5] == ["--source", str(scenes / VID)]
    plan({"beatgate --status": {"stdout": json.dumps({"hash": "abc", "pass": True, "need": None, "judges": 2, "tie": [], "fails": [], "summary": "PASS", "beats": 1, "stills": []})}})
    assert cartoon.readiness(jobs, VID, remotion, scenes) == []


def test_readiness_refuses_a_video_that_is_not_cartoon_or_has_no_config(fake_node, jobs, scenes):
    _, remotion, _ = fake_node
    (jobs / VID / "scene-config.json").write_text(json.dumps(PLAIN_CONFIG))
    with pytest.raises(cartoon.CartoonError, match="not a Cartoon 3D video"):
        cartoon.readiness(jobs, VID, remotion, scenes)
    with pytest.raises(cartoon.CartoonError, match="write_scene_config"):
        cartoon.readiness(jobs, "vid-none", remotion, scenes)


def test_a_second_tool_for_the_same_video_is_refused_while_one_runs(fake_node, jobs):
    _, remotion, _ = fake_node
    with cartoon._Staged(jobs, VID, remotion):
        with pytest.raises(cartoon.CartoonError, match="still running"):
            with cartoon._Staged(jobs, VID, remotion):
                pass
    with cartoon._Staged(jobs, VID, remotion):
        pass


def test_a_recorder_waits_for_the_running_tool_instead_of_being_refused(fake_node, jobs, scenes):
    """Judges answer in parallel: two record calls for one video queue on the
    video's lock so both verdicts land (two writers of one verdict file keep
    only the last), and a record call behind a gate render waits for it."""
    import threading
    plan, remotion, log = fake_node
    plan({"beatgate --record": {"stdout": "yes beat 0: fine\n"},
          "beatgate --status": {"stdout": json.dumps({"hash": "abc", "pass": False, "need": "a second judge", "judges": 1, "tie": [], "fails": [], "summary": "1 of 2", "beats": 1, "stills": []}), "code": 2}})
    answers = {"beats": [{"beat": 0, "seen": "a quay", "shows": True, "why": "fine"}]}
    started = threading.Event()
    result = {}

    def record():
        started.set()
        result["r"] = cartoon.beat_gate_record(jobs, VID, remotion, scenes, answers)

    with cartoon._Staged(jobs, VID, remotion):          # a gate render holds the video
        t = threading.Thread(target=record); t.start()
        started.wait(5); t.join(0.5)
        assert t.is_alive() and not _calls(log)            # the recorder is waiting, not refused, not written
    t.join(10)
    assert result["r"]["recorded"] == ["yes beat 0: fine"] and result["r"]["need"] == "a second judge"
    assert [c["key"] for c in _calls(log)] == ["beatgate --record", "beatgate --status"]
    assert _calls(log)[0]["argv"][3:5] == ["--source", str(scenes / VID)]


def test_stills_keep_their_files_and_cap_the_frames(fake_node, jobs):
    plan, remotion, log = fake_node
    out = cartoon.cartoon_dir(jobs, VID) / "stills"
    plan({"still": {"stdout": json.dumps({"stills": [str(out / "f0010.png"), str(out / "f0050.png")]}) + "\n",
                    "files": {str(out / "f0010.png"): "png", str(out / "f0050.png"): "png"}}})
    stills = cartoon.stills(jobs, VID, remotion, [10, 50])
    assert [p.name for p in stills] == ["f0010.png", "f0050.png"] and all(p.is_file() for p in stills)
    assert _calls(log)[0]["argv"][3:] == ["10", "50"]
    assert _calls(log)[0]["env"]["CARTOON_PUBLIC_DIR"] == str(jobs)
    for bad in ([], list(range(7)), [-1], [1.5], [True]):
        with pytest.raises(cartoon.CartoonError):
            cartoon.stills(jobs, VID, remotion, bad)


# ── The kit source ───────────────────────────────────────────────────────────────

def test_the_kit_is_listed_without_its_tests_and_read_by_listed_path_only(tmp_path):
    remotion = tmp_path / "remotion"
    for rel in ("video.ts", "camera.ts", "camera.test.ts", "CartoonShort.tsx", "kit/cast.ts", "gate/stills.ts",
                "examples/chicago/story.ts", "examples/chicago/sets/street.ts"):
        p = remotion / "src" / "cartoon3d" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"// {rel}")
    assert cartoon.list_kit(remotion) == ["CartoonShort.tsx", "camera.ts", "examples/chicago/sets/street.ts",
                                          "examples/chicago/story.ts", "kit/cast.ts", "video.ts"]
    assert cartoon.read_kit(remotion, "kit/cast.ts") == "// kit/cast.ts"
    for bad in ("../server.py", "gate/stills.ts", "camera.test.ts", "kit/nothing.ts", "/etc/passwd", ""):
        with pytest.raises(cartoon.CartoonError):
            cartoon.read_kit(remotion, bad)


# ── The soundtrack ───────────────────────────────────────────────────────────────

GOOD_SPEC = {"music": {"tempo": 110, "key": "F", "sections": [{"name": "hook", "start": 0, "end": 3.3, "style": "tutti", "level": -9.5}]},
             "sfx": {"cues": [{"t": 0, "gen": "bed_day", "args": {"dur": 3.3}, "naive": -30, "kind": "bed"}, {"f": 40, "gen": "bell", "naive": -8}]}}


@pytest.mark.parametrize("spec, fragment", [
    ("music", "object with a 'music'"),
    ({}, "object with a 'music'"),
    ({"music": {"sections": []}}, "non-empty 'sections'"),
    ({"music": {"sections": [{"start": 0, "end": "x", "style": "tutti"}]}}, "sections[0]"),
    ({"sfx": {"cues": "bell"}}, "'cues' list"),
    ({"sfx": {"cues": [{"gen": "bell"}]}}, "cues[0]"),
    ({"sfx": {"cues": [{"t": 1}]}}, "cues[0]"),
])
def test_a_malformed_soundtrack_spec_is_refused_before_anything_runs(spec, fragment):
    import re
    with pytest.raises(cartoon.CartoonError, match=re.escape(fragment)):
        cartoon._check_spec(spec)
    cartoon._check_spec(GOOD_SPEC)


def test_the_soundtrack_resamples_the_voice_runs_the_engine_and_lands_where_the_worker_muxes(fake_node, jobs, tmp_path, monkeypatch):
    """ffmpeg and the engine are stubs: the voice is 'resampled' to voice.wav,
    mix.py sees the spec, the timeline and the voice, and writes mix.wav and
    cues.md under <cartoon>/audio/mix, newer than the voice."""
    _, remotion, _ = fake_node
    bin_dir = tmp_path / "bin"
    log = tmp_path / "audio-calls.jsonl"
    (bin_dir / "ffmpeg").write_text(f"#!{sys.executable}\nimport json, sys\nopen({str(log)!r}, 'a').write(json.dumps(['ffmpeg'] + sys.argv[1:]) + '\\n')\nopen(sys.argv[-1], 'wb').write(b'RIFF')\n")
    (bin_dir / "ffmpeg").chmod(0o755)
    audio_dir = remotion / "cartoon-tools" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "mix.py").write_text(f"""import json, os, sys
args = sys.argv[1:]
open({str(log)!r}, 'a').write(json.dumps(['mix.py'] + args) + '\\n')
out = args[args.index('--out') + 1]
os.makedirs(out, exist_ok=True)
spec = json.load(open(args[args.index('--spec') + 1]))
open(os.path.join(out, 'mix.wav'), 'wb').write(b'RIFF')
open(os.path.join(out, 'cues.md'), 'w').write('# cues\\n' + spec['sfx']['cues'][1]['gen'])
open(os.path.join(out, 'loudness.json'), 'w').write(json.dumps({{"lufs": -14.1}}))
print('mixed')
""")
    result = cartoon.soundtrack(jobs, VID, remotion, GOOD_SPEC)
    adir = jobs / VID / "cartoon" / "audio"
    assert Path(result["mix"]) == adir / "mix" / "mix.wav" == cartoon.mix_file(jobs, VID)
    assert result["cues"].endswith("bell") and result["loudness"] == {"lufs": -14.1} and result["log"] == "mixed"
    assert json.loads((adir / "audio-spec.json").read_text()) == GOOD_SPEC
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    assert calls[0][0] == "ffmpeg" and str(jobs / VID / "audio.mp3") in calls[0] and calls[0][-1] == str(adir / "voice.wav")
    assert "48000" in calls[0]
    assert calls[1][0] == "mix.py" and calls[1][calls[1].index("--timeline") + 1] == str(jobs / VID / "timeline.json")
    assert cartoon.mix_file(jobs, VID).stat().st_mtime >= (jobs / VID / "audio.mp3").stat().st_mtime


def test_a_failing_engine_is_reported_with_its_last_lines(fake_node, jobs, tmp_path):
    _, remotion, _ = fake_node
    (tmp_path / "bin" / "ffmpeg").write_text(f"#!{sys.executable}\nimport sys\nopen(sys.argv[-1], 'wb').write(b'RIFF')\n")
    (tmp_path / "bin" / "ffmpeg").chmod(0o755)
    audio_dir = remotion / "cartoon-tools" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "mix.py").write_text("import sys\nsys.stderr.write('ValueError: cue 3: unknown generator \\'kazoo\\'\\n')\nsys.exit(1)\n")
    with pytest.raises(cartoon.CartoonError, match="unknown generator 'kazoo'"):
        cartoon.soundtrack(jobs, VID, remotion, GOOD_SPEC)


# ── The tools, through the server ───────────────────────────────────────────────

@pytest.fixture
def job_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()

    def make_video(video_id, status="VOICE_READY"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, voice_file_path, timeline_path, "
                " scene_config_path, created_at, updated_at) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)",
                (video_id, "test topic", status, "audio.mp3", "timeline.json", "scene-config.json", _now(), _now()))
    return make_video


def test_submit_render_refuses_an_ungated_cartoon_video_and_queues_a_gated_one(job_db, jobs, monkeypatch):
    job_db(VID)
    monkeypatch.setattr(cartoon, "readiness", lambda *a: ["Cartoon 3D beat gate: no judge has answered yet"])
    result = server.submit_render(VID)
    assert result == {"error": "cartoon_not_ready", "errors": ["Cartoon 3D beat gate: no judge has answered yet"]}
    with server._conn() as con:
        assert con.execute("SELECT status FROM videos WHERE id = ?", (VID,)).fetchone()["status"] == "VOICE_READY"
    monkeypatch.setattr(cartoon, "readiness", lambda *a: [])
    assert server.submit_render(VID) == {"status": "queued", "video_id": VID}


def test_submit_render_does_not_ask_readiness_of_a_video_that_is_not_cartoon(job_db, jobs, monkeypatch):
    job_db("vid-plain")
    (jobs / "vid-plain").mkdir()
    (jobs / "vid-plain" / "scene-config.json").write_text(json.dumps(PLAIN_CONFIG))

    def boom(*a):
        raise AssertionError("readiness must not run for a non-Cartoon video")
    monkeypatch.setattr(cartoon, "readiness", boom)
    assert server.submit_render("vid-plain") == {"status": "queued", "video_id": "vid-plain"}


def test_validate_job_carries_the_readiness_errors_and_hands_over_the_scene_tree(job_db, jobs, scenes, monkeypatch):
    job_db(VID)
    seen = {}

    def readiness(jobs_dir, video_id, remotion_dir, scenes_dir):
        seen.update(jobs=jobs_dir, vid=video_id, scenes=scenes_dir)
        return ["Cartoon 3D beat gate: 1 of 2 judges recorded"]
    monkeypatch.setattr(cartoon, "readiness", readiness)
    monkeypatch.setattr("shutil.which", lambda name: None)   # no npx: the typecheck is skipped
    result = server.validate_job(VID)
    assert result["passed"] is False
    assert "Cartoon 3D beat gate: 1 of 2 judges recorded" in result["errors"]
    assert seen == {"jobs": jobs, "vid": VID, "scenes": scenes}


def test_validate_job_skips_the_text_layout_audit_for_a_cartoon_video(job_db, jobs, tmp_path, monkeypatch):
    """A painted canvas has no text rects to measure, and the audit's first frame
    on software GL exceeds Remotion's initial-render timeout (seen live): the
    beat gate is its check, so the audit is not even started. A DOM video still
    gets it."""
    import text_audit
    called = []
    monkeypatch.setattr(text_audit, "audit_text_layout", lambda *a, **k: called.append(1) or ["measured"])
    monkeypatch.setattr("shutil.which", lambda name: None)   # no npx: the typecheck is skipped
    monkeypatch.setattr(cartoon, "readiness", lambda *a: [])
    # a scene library the configs resolve against, and job files past the other checks
    repo = tmp_path / "repo"
    monkeypatch.setattr(server, "REPO_ROOT", repo)
    monkeypatch.setattr(server, "SCENES_DIR", repo / "remotion" / "src" / "scenes" / "generated")
    monkeypatch.setattr(server, "INSTALLED_DIR", repo / "remotion" / "src" / "scenes" / "installed")
    (repo / "remotion" / "src" / "scenes" / "installed").mkdir(parents=True)
    for vid in (VID, "vid-plain"):
        (repo / "remotion" / "src" / "scenes" / "generated" / vid).mkdir(parents=True)
    (repo / "remotion" / "src" / "scenes" / "generated" / VID / "CartoonShort.tsx").write_text("export default () => null;")
    (repo / "remotion" / "src" / "scenes" / "generated" / "vid-plain" / "hero.tsx").write_text("export default () => null;")
    timeline = json.dumps({"totalFrames": 100, "fps": 30, "audioDurationSeconds": 100 / 30, "words": []})
    plain = {"totalFrames": 100, "fps": 30, "scenes": [{"type": "generated", "src": "vid-plain/hero", "props": {}}]}
    for vid, config in ((VID, CARTOON_CONFIG), ("vid-plain", plain)):
        job_db(vid)
        (jobs / vid).mkdir(exist_ok=True)
        (jobs / vid / "scene-config.json").write_text(json.dumps(config))
        (jobs / vid / "timeline.json").write_text(timeline)
        (jobs / vid / "audio.mp3").write_bytes(b"\x00" * (60 * 1024))   # past the 50 KB floor

    result = server.validate_job(VID)
    assert result == {"passed": True, "errors": [], "warnings": []} and called == []

    result = server.validate_job("vid-plain")
    assert result["passed"] is True and result["warnings"] == ["measured"] and called == [1]


def test_the_tools_are_offered_the_old_gates_are_gone_and_a_still_name_is_checked_before_any_path(through_mcp):
    import asyncio
    from fastmcp import Client

    async def go():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]
    names = asyncio.run(go())
    for n in ("cartoon_kit_list", "cartoon_kit_read", "cartoon_still", "cartoon_read_still", "cartoon_beat_gate",
              "cartoon_beat_gate_record", "cartoon_soundtrack"):
        assert n in names
    for n in ("cartoon_catalog", "cartoon_qa", "cartoon_gate", "cartoon_gate_record"):
        assert n not in names
    result, _ = through_mcp("cartoon_read_still", video_id=VID, kind="beatgate", name="../../etc/passwd.png")
    assert "named like" in result["error"]
    result, _ = through_mcp("cartoon_read_still", video_id="../x", kind="beatgate", name="a.png")
    assert "error" in result
    result, _ = through_mcp("cartoon_kit_read", path="../../api/server.py")
    assert "error" in result
