"""Tests for the Cartoon 3D authoring tools (mcp/cartoon.py and the
cartoon_* tools of server.py), as far as Python can reach them.

The gates themselves are the renderer's Node command lines; what Python owns
is the plumbing a judge and the render depend on: where a video's verdicts
live, that a still's name can only ever be a file under that directory, that
a judge prompt names stills by the call that shows them and ends in the
record call the judge makes itself, and that the readiness check (the thing
validate_job and submit_render ask) composes the three gates and stops a
render on any of them. The command lines are stood in for by a stub `node`
on PATH that plays back a plan, so nothing here bundles or renders.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cartoon
import server

VID = "vid-cartoon"

CARTOON_CONFIG = {
    "totalFrames": 100, "fps": 30,
    "scenes": [{"type": "generated", "source": "installed", "src": "Cartoon3D", "startFrame": 0,
                "durationInFrames": 100, "props": {"world": {"name": "quay", "pieces": []}, "beats": [{"start": 0, "end": 99}]}}],
}
PLAIN_CONFIG = {"totalFrames": 100, "fps": 30, "scenes": [{"type": "generated", "src": "hero", "props": {}}]}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def fake_node(tmp_path, monkeypatch):
    """A stub `node` that plays back a plan keyed by command line ("gate",
    "gate --check", "beatgate --status", "qa-config", "still", ...): writes the
    files the plan names, prints its stdout, exits with its code, and logs
    every call. Returns (plan writer, remotion dir, call log path)."""
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
flags = [a for a in sys.argv[2:] if a.startswith("--")]
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
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ.get('PATH', '')}")
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


def _calls(log_file):
    return [json.loads(line) for line in log_file.read_text().splitlines()] if log_file.exists() else []


# ── The scene and the still names ──────────────────────────────────────────────

def test_a_cartoon_video_is_one_installed_scene():
    assert cartoon.is_cartoon(CARTOON_CONFIG)
    assert cartoon.cartoon_scene(CARTOON_CONFIG)["props"]["world"]["name"] == "quay"
    assert not cartoon.is_cartoon(PLAIN_CONFIG)
    assert not cartoon.is_cartoon([]) and not cartoon.is_cartoon({"scenes": "x"})


def test_a_still_is_a_plain_file_name_under_the_video(tmp_path):
    p = cartoon.still_file(tmp_path, VID, "beatgate", "beat03-f0184.png")
    assert p == tmp_path / VID / "cartoon" / "beatgate" / "beat03-f0184.png"
    for bad in ("../x.png", "a/b.png", "x.jpg", "", ".png", "x.png/"):
        with pytest.raises(cartoon.CartoonError):
            cartoon.still_file(tmp_path, VID, "beatgate", bad)
    with pytest.raises(cartoon.CartoonError, match="kind"):
        cartoon.still_file(tmp_path, VID, "secrets", "x.png")


def test_the_judge_prompt_names_stills_by_the_call_that_shows_them(tmp_path):
    base = cartoon.cartoon_dir(tmp_path, VID) / "gate"
    text = f"Look at these:\n- {base}/bollard-quarter.png\n- {base}/bollard-end.png\nWrite your answer as JSON only to the file named in your instructions:"
    out = cartoon._prompt_for_judge(text, tmp_path, VID, "gate", f'cartoon_gate_record("{VID}", "bollard", <your JSON>)')
    assert str(base) not in out
    assert f'still "bollard-quarter.png" (call cartoon_read_still("{VID}", "gate", "bollard-quarter.png"))' in out
    assert out.endswith(f'then call cartoon_gate_record("{VID}", "bollard", <your JSON>) with it yourself:')


# ── Readiness ──────────────────────────────────────────────────────────────────

def test_readiness_reports_every_gate_that_is_not_passed(fake_node, jobs):
    plan, remotion, log = fake_node
    plan({
        "gate --check": {"stdout": json.dumps({"unpassed": ["bollard", "belle"], "parts": {}}) + "\n", "code": 2},
        "beatgate --status": {"stdout": "some browser chatter\n" + json.dumps({"hash": "abc", "pass": False, "need": "a second judge", "judges": 1, "tie": [], "fails": [], "summary": "1 of 2 judges recorded", "beats": 1, "stills": [], "prompt": None}) + "\n", "code": 2},
        "qa-config": {"stdout": "=== quay === 2 findings (1 blocking)\n  [BLOCK] beat 0 f10 newsboy: inside - standing inside crate\n  [ADVISE] beat 0 f10 -: bare - only 1 solid things\n", "code": 2},
    })
    errors = cartoon.readiness(jobs, VID, remotion)
    assert len(errors) == 3
    assert "bollard, belle" in errors[0] and "cartoon_gate" in errors[0]
    assert "1 of 2 judges recorded" in errors[1] and "cartoon_beat_gate" in errors[1]
    assert "blocks 1 finding" in errors[2] and "standing inside crate" in errors[2]
    keys = [c["key"] for c in _calls(log)]
    assert keys == ["gate --check", "beatgate --status", "qa-config"]
    # the beat gate ran over the video's job directory, which the jobs volume serves as /public/<vid>/:
    # nothing staged, nothing copied
    status_call = _calls(log)[1]
    assert Path(status_call["argv"][1]) == jobs / VID
    assert not (remotion / "public" / f"cartoon-{VID}").exists()
    assert json.loads(status_call["env"]["BEAT_PROPS"])["sceneConfigPath"] == f"/public/{VID}/scene-config.json"
    assert status_call["env"]["CARTOON_PUBLIC_DIR"] == str(jobs)
    assert status_call["env"]["STILLS_SERVER"] is None   # no server configured: the tool renders locally
    assert status_call["env"]["REMOTION_ROOT"] == str(remotion)


def test_the_stills_server_is_handed_to_every_rendering_tool(fake_node, jobs, monkeypatch):
    """TUBEMATIC_STILLS_SERVER (the worker's server, on the GPU) reaches the
    command lines as STILLS_SERVER; the frame check, which renders nothing,
    never sees it."""
    plan, remotion, log = fake_node
    monkeypatch.setenv("TUBEMATIC_STILLS_SERVER", "http://tubematic-renderer:4455")
    plan({
        "still": {"stdout": json.dumps({"stills": [str(jobs / VID / "cartoon" / "stills" / "f0010.png")]})},
        "qa-config": {"stdout": "=== quay === 0 findings (0 blocking)\n"},
    })
    cartoon.stills(jobs, VID, remotion, [10])
    cartoon.qa(jobs, VID, remotion)
    still_call, qa_call = _calls(log)
    assert still_call["env"]["STILLS_SERVER"] == "http://tubematic-renderer:4455"
    assert still_call["env"]["CARTOON_PUBLIC_DIR"] == str(jobs)
    assert qa_call["env"]["STILLS_SERVER"] is None and qa_call["env"]["CARTOON_PUBLIC_DIR"] is None


def test_readiness_is_empty_when_every_gate_passes(fake_node, jobs):
    plan, remotion, _ = fake_node
    plan({
        "gate --check": {"stdout": json.dumps({"unpassed": [], "parts": {}})},
        "beatgate --status": {"stdout": json.dumps({"hash": "abc", "pass": True, "need": None, "judges": 2, "tie": [], "fails": [], "summary": "PASS", "beats": 1, "stills": []})},
        "qa-config": {"stdout": "=== quay === 1 findings (0 blocking)\n  [ADVISE] beat 0 f10 -: bare\n"},
    })
    assert cartoon.readiness(jobs, VID, remotion) == []


def test_readiness_refuses_a_video_that_is_not_cartoon_or_has_no_config(fake_node, jobs, tmp_path):
    _, remotion, _ = fake_node
    (jobs / VID / "scene-config.json").write_text(json.dumps(PLAIN_CONFIG))
    with pytest.raises(cartoon.CartoonError, match="not a Cartoon 3D video"):
        cartoon.readiness(jobs, VID, remotion)
    with pytest.raises(cartoon.CartoonError, match="write_scene_config"):
        cartoon.readiness(jobs, "vid-none", remotion)


def test_a_second_tool_for_the_same_video_is_refused_while_one_runs(fake_node, jobs):
    _, remotion, _ = fake_node
    with cartoon._Staged(jobs, VID, remotion):
        with pytest.raises(cartoon.CartoonError, match="still running"):
            with cartoon._Staged(jobs, VID, remotion):
                pass
    # and the busy mark is gone once the first finishes
    with cartoon._Staged(jobs, VID, remotion):
        pass


def test_stills_keep_their_files_and_cap_the_frames(fake_node, jobs):
    plan, remotion, log = fake_node
    out = cartoon.cartoon_dir(jobs, VID) / "stills"
    plan({"still": {"stdout": json.dumps({"stills": [str(out / "f0010.png"), str(out / "f0050.png")]}) + "\n",
                    "files": {str(out / "f0010.png"): "png", str(out / "f0050.png"): "png"}}})
    stills = cartoon.stills(jobs, VID, remotion, [10, 50])
    assert [p.name for p in stills] == ["f0010.png", "f0050.png"] and all(p.is_file() for p in stills)
    assert _calls(log)[0]["argv"][3:] == ["10", "50"]
    for bad in ([], list(range(7)), [-1], [1.5], [True]):
        with pytest.raises(cartoon.CartoonError):
            cartoon.stills(jobs, VID, remotion, bad)


def test_gate_state_reads_the_verdict_file_and_attaches_the_prompt(fake_node, jobs):
    plan, remotion, _ = fake_node
    outdir = cartoon.cartoon_dir(jobs, VID) / "gate"
    prompt = outdir / "bollard-judge-prompt.md"
    verdict = {"parts": {
        "bollard": {"pass": False, "attempts": [{"stage": "stills", "pass": False, "hash": "h1", "stills": [str(outdir / "bollard-quarter.png")], "prompt": str(prompt)}]},
        "crate2": {"pass": True, "attempts": [{"stage": "stills", "pass": False, "hash": "h2"}, {"stage": "judge", "pass": True, "hash": "h2", "seen": "a box", "answers": {"scale": {"ok": True, "why": "fine"}}}]},
        "blob": {"pass": False, "attempts": [{"stage": "spec", "pass": False, "hash": "h3", "errors": ["primitive 1 floats"]}]},
    }}
    plan({"gate": {"stdout": "", "code": 2, "files": {str(outdir / "verdict.json"): json.dumps(verdict),
                                                     str(prompt): f"Look at\n- {outdir}/bollard-quarter.png\nWrite it to the file named in your instructions:"}}})
    result = cartoon.gate(jobs, VID, remotion)
    assert result["passed"] is False
    parts = result["parts"]
    assert parts["bollard"]["status"] == "awaiting judge"
    assert f'cartoon_read_still("{VID}", "gate", "bollard-quarter.png")' in parts["bollard"]["judge_prompt"]
    assert f'cartoon_gate_record("{VID}", "bollard", <your JSON>)' in parts["bollard"]["judge_prompt"]
    assert parts["crate2"] == {"status": "pass", "attempts": 1, "errors": [], "stills": [], "answers": {"scale": {"ok": True, "why": "fine"}}, "seen": "a box"}
    assert parts["blob"]["status"] == "fail" and parts["blob"]["errors"] == ["primitive 1 floats"]
    assert "1 of 3 pass; 1 awaiting a judge" == result["summary"]


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


def test_validate_job_carries_the_readiness_errors(job_db, jobs, monkeypatch):
    job_db(VID)
    monkeypatch.setattr(cartoon, "readiness", lambda *a: ["Cartoon 3D parts without a judge's PASS: bollard"])
    monkeypatch.setattr("shutil.which", lambda name: None)   # no npx: the typecheck is skipped
    result = server.validate_job(VID)
    assert result["passed"] is False
    assert "Cartoon 3D parts without a judge's PASS: bollard" in result["errors"]


def test_validate_job_skips_the_text_layout_audit_for_a_cartoon_video(job_db, jobs, tmp_path, monkeypatch):
    """A painted canvas has no text rects to measure, and the audit's first frame
    on software GL exceeds Remotion's initial-render timeout (seen live): the
    gates are its checks, so the audit is not even started. A DOM video still
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
    (repo / "remotion" / "src" / "scenes" / "installed" / "Cartoon3D.tsx").write_text("export default () => null;")
    (repo / "remotion" / "src" / "scenes" / "generated" / "vid-plain").mkdir(parents=True)
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


def test_the_tools_are_offered_and_a_still_name_is_checked_before_any_path(through_mcp):
    import asyncio
    from fastmcp import Client

    async def go():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]
    names = asyncio.run(go())
    for n in ("cartoon_catalog", "cartoon_qa", "cartoon_still", "cartoon_read_still", "cartoon_gate",
              "cartoon_gate_record", "cartoon_beat_gate", "cartoon_beat_gate_record"):
        assert n in names
    result, _ = through_mcp("cartoon_read_still", video_id=VID, kind="gate", name="../../etc/passwd.png")
    assert "named like" in result["error"]
    result, _ = through_mcp("cartoon_read_still", video_id="../x", kind="gate", name="a.png")
    assert "error" in result
