"""Tests for the preview_frames tool (mcp/frame_preview.py and its server.py wrapper, TMDEV-241).

The frames are drawn by the renderer's `still` command line (the Cartoon 3D
tools' CLI, which renders the real Composition with any props); what Python
owns, and what these tests guard, is everything around it: which frames are
accepted, that the props equal the render's (watermark from the settings,
mascotPath for a video with a mascot, the mascot's pinned code
written beside the previews), that the pictures land only under
<video>/preview/, that a Cartoon 3D video is sent to its own tools, and that
a renderer too old to accept the folder is named as the cause. The command
line is stood in for by a stub `node` on PATH, so nothing here renders.

Run from repo root: pytest mcp/tests/
"""
import json
import os
import sys
from pathlib import Path

import pytest

import cartoon
import frame_preview as fp
import server

VID = "vid-preview"
PLAIN = {"totalFrames": 120, "fps": 30, "scenes": [{"type": "generated", "src": "hero", "props": {}}],
         "mascot": [{"frame": 0, "emotion": "happy", "on": True}]}
CARTOON = {"totalFrames": 120, "fps": 30, "scenes": [{"type": "generated", "src": f"{VID}/CartoonShort", "props": {
    "cartoon3d": {"beats": [{"start": 0, "end": 99, "shot": "the quay"}]}}}]}


@pytest.fixture
def fake_node(tmp_path, monkeypatch):
    """A stub `node` playing back the `still` command line: writes a PNG per
    requested frame into the out directory (unless the plan says to fail),
    logs the call. Returns (plan writer, remotion dir, call log path)."""
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
outdir, frames = sys.argv[3], sys.argv[4:]
with open({str(log_file)!r}, "a") as fh:
    fh.write(json.dumps({{"script": script, "argv": sys.argv[2:],
        "env": {{k: os.environ.get(k) for k in ("BEAT_PROPS", "CARTOON_PUBLIC_DIR", "STILLS_SERVER")}}}}) + "\\n")
if plan.get("code"):
    sys.stderr.write(plan.get("stderr", "boom"))
    sys.exit(plan["code"])
os.makedirs(outdir, exist_ok=True)
outs = []
for f in frames:
    p = os.path.join(outdir, "f%04d.png" % int(f))
    open(p, "wb").write(b"\\x89PNG fake")
    outs.append(p)
print("chatter")
print(json.dumps({{"stills": outs}}))
""")
    (bin_dir / "node").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setattr(cartoon, "_built", set())
    remotion = tmp_path / "remotion"
    (remotion / "cartoon-tools").mkdir(parents=True)
    (remotion / "cartoon-tools" / "build.mjs").write_text("// stub")

    def plan(spec: dict):
        plan_file.write_text(json.dumps(spec))

    plan({})
    return plan, remotion, log_file


@pytest.fixture
def jobs(tmp_path):
    jobs_dir = tmp_path / "jobs"
    d = jobs_dir / VID
    d.mkdir(parents=True)
    (d / "scene-config.json").write_text(json.dumps(PLAIN))
    (d / "timeline.json").write_text(json.dumps({"totalFrames": 120, "fps": 30, "words": []}))
    (d / "audio.mp3").write_bytes(b"\x00" * 100)
    return jobs_dir


def _calls(log_file):
    return [json.loads(line) for line in log_file.read_text().splitlines()] if log_file.exists() else []


def _preview(jobs, remotion, frames, **kw):
    kw.setdefault("watermark", True)
    kw.setdefault("mascot_code", None)
    return fp.preview(jobs, VID, remotion, frames, **kw)


# ── Which frames ────────────────────────────────────────────────────────────────

def test_frames_are_drawn_under_the_preview_folder_and_named_by_frame(fake_node, jobs):
    _, remotion, log = fake_node
    out = _preview(jobs, remotion, [0, 45, 119])
    assert [p.name for p in out] == ["f0000.png", "f0045.png", "f0119.png"]
    assert all(p.parent == jobs / VID / "preview" and p.is_file() for p in out)
    call = _calls(log)[0]
    assert call["script"] == "still.mjs"
    assert Path(call["argv"][0]) == jobs / VID and Path(call["argv"][1]) == jobs / VID / "preview"
    assert call["argv"][2:] == ["0", "45", "119"]


@pytest.mark.parametrize("frames", [[], list(range(7)), [-1], [1.5], ["3"], [True], [120], [5000], "3", None])
def test_a_bad_frame_list_is_refused_before_anything_runs(fake_node, jobs, frames):
    _, remotion, log = fake_node
    with pytest.raises(fp.PreviewError, match="frames|total"):
        _preview(jobs, remotion, frames)
    assert _calls(log) == []


def test_the_last_frame_of_the_video_is_allowed(fake_node, jobs):
    _, remotion, _ = fake_node
    assert [p.name for p in _preview(jobs, remotion, [119])] == ["f0119.png"]


def test_a_second_call_clears_the_first_calls_pictures(fake_node, jobs):
    _, remotion, _ = fake_node
    _preview(jobs, remotion, [10, 20])
    out = _preview(jobs, remotion, [30])
    assert sorted(p.name for p in (jobs / VID / "preview").iterdir() if p.suffix == ".png") == ["f0030.png"]
    assert [p.name for p in out] == ["f0030.png"]


# ── What the picture is of ─────────────────────────────────────────────────────

def test_the_props_are_the_renders(fake_node, jobs, monkeypatch):
    _, remotion, log = fake_node
    monkeypatch.setenv("TUBEMATIC_STILLS_SERVER", "http://tubematic-renderer:4455")
    _preview(jobs, remotion, [10], watermark=True)
    call = _calls(log)[0]
    props = json.loads(call["env"]["BEAT_PROPS"])
    assert props == {"sceneConfigPath": f"/public/{VID}/scene-config.json", "timelinePath": f"/public/{VID}/timeline.json",
                     "audioPath": f"/public/{VID}/audio.mp3", "watermark": True}
    assert call["env"]["STILLS_SERVER"] == "http://tubematic-renderer:4455"
    assert call["env"]["CARTOON_PUBLIC_DIR"] == str(jobs)


def test_the_watermark_follows_the_setting(fake_node, jobs):
    _, remotion, log = fake_node
    _preview(jobs, remotion, [10], watermark=False)
    assert json.loads(_calls(log)[0]["env"]["BEAT_PROPS"])["watermark"] is False


def test_a_mascot_video_gets_its_pinned_code_staged_and_named(fake_node, jobs):
    _, remotion, log = fake_node
    _preview(jobs, remotion, [10], mascot_code="export default {};")
    props = json.loads(_calls(log)[0]["env"]["BEAT_PROPS"])
    assert props["mascotPath"] == f"/public/{VID}/preview/mascot.js"
    assert (jobs / VID / "preview" / "mascot.js").read_text() == "export default {};"


def test_no_mascot_path_without_a_mascot(fake_node, jobs):
    _, remotion, log = fake_node
    _preview(jobs, remotion, [10], mascot_code=None)
    assert "mascotPath" not in json.loads(_calls(log)[0]["env"]["BEAT_PROPS"])


def test_a_mascot_file_is_never_written_through_a_planted_link(fake_node, jobs, tmp_path):
    _, remotion, _ = fake_node
    target = tmp_path / "victim.txt"
    target.write_text("keep")
    folder = jobs / VID / "preview"
    folder.mkdir()
    (folder / "mascot.js").symlink_to(target)
    _preview(jobs, remotion, [10], mascot_code="export default {};")
    assert target.read_text() == "keep"
    assert (folder / "mascot.js").read_text() == "export default {};" and not (folder / "mascot.js").is_symlink()


def test_a_mascot_name_taken_by_a_directory_is_a_refusal_not_a_crash(fake_node, jobs):
    _, remotion, log = fake_node
    (jobs / VID / "preview" / "mascot.js").mkdir(parents=True)
    with pytest.raises(fp.PreviewError, match="could not be staged"):
        _preview(jobs, remotion, [10], mascot_code="export default {};")
    assert _calls(log) == []


def test_a_symlinked_job_file_is_a_refusal_not_a_crash(fake_node, jobs, tmp_path):
    _, remotion, _ = fake_node
    real = tmp_path / "real.json"
    real.write_text(json.dumps(PLAIN))
    (jobs / VID / "scene-config.json").unlink()
    (jobs / VID / "scene-config.json").symlink_to(real)
    with pytest.raises(fp.PreviewError, match="symlink"):
        _preview(jobs, remotion, [10])


def test_a_stale_mascot_file_does_not_outlive_the_mascot(fake_node, jobs):
    _, remotion, _ = fake_node
    _preview(jobs, remotion, [10], mascot_code="export default {};")
    _preview(jobs, remotion, [10], mascot_code=None)
    assert not (jobs / VID / "preview" / "mascot.js").exists()


# ── Refusals ────────────────────────────────────────────────────────────────────

def test_a_cartoon_3d_video_is_sent_to_its_own_tools(fake_node, jobs):
    _, remotion, log = fake_node
    (jobs / VID / "scene-config.json").write_text(json.dumps(CARTOON))
    with pytest.raises(fp.PreviewError, match="cartoon_still"):
        _preview(jobs, remotion, [10])
    assert _calls(log) == []


def test_a_video_without_its_job_files_is_told_what_is_missing(fake_node, jobs):
    _, remotion, _ = fake_node
    (jobs / VID / "audio.mp3").unlink()
    with pytest.raises(fp.PreviewError, match="generate_voice"):
        _preview(jobs, remotion, [10])
    (jobs / VID / "scene-config.json").unlink()
    with pytest.raises(fp.PreviewError, match="write_scene_config"):
        _preview(jobs, remotion, [10])


def test_a_symlinked_preview_folder_is_refused(fake_node, jobs, tmp_path):
    _, remotion, _ = fake_node
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (jobs / VID / "preview").symlink_to(elsewhere)
    with pytest.raises(fp.PreviewError, match="symlink"):
        _preview(jobs, remotion, [10])
    assert list(elsewhere.iterdir()) == []


def test_one_preview_at_a_time_per_video(fake_node, jobs):
    _, remotion, log = fake_node
    lock = cartoon._lock_for(VID)
    assert lock.acquire(blocking=False)
    try:
        with pytest.raises(fp.PreviewError, match="still running"):
            _preview(jobs, remotion, [10])
    finally:
        lock.release()
    assert _calls(log) == []


# ── A renderer that fails ───────────────────────────────────────────────────────

def test_a_failed_render_reports_the_renderers_words(fake_node, jobs):
    plan, remotion, _ = fake_node
    plan({"code": 1, "stderr": "a scene threw: x is not defined"})
    with pytest.raises(fp.PreviewError, match="x is not defined"):
        _preview(jobs, remotion, [10])


def test_a_renderer_older_than_this_tool_is_named_as_the_cause(fake_node, jobs):
    plan, remotion, _ = fake_node
    plan({"code": 1, "stderr": "stills server failed for /jobs/vid/preview/f0010.png: "
                               '{"ok":false,"error":"/jobs/vid/preview/f0010.png is not under /jobs/<video>/cartoon"}'})
    with pytest.raises(fp.PreviewError, match="older than this tool"):
        _preview(jobs, remotion, [10])


# ── The record that submit_render asks for ─────────────────────────────────────

def test_a_drawn_preview_records_a_look_at_this_config(fake_node, jobs):
    _, remotion, _ = fake_node
    assert not fp.look_recorded(jobs, VID)
    _preview(jobs, remotion, [10])
    assert fp.look_recorded(jobs, VID)
    rec = json.loads((jobs / VID / "preview" / "record.json").read_text())
    assert rec["status"] == "ok" and rec["frames"] == [10]


def test_a_rewritten_config_or_timeline_needs_a_new_look(fake_node, jobs):
    _, remotion, _ = fake_node
    _preview(jobs, remotion, [10])
    (jobs / VID / "scene-config.json").write_text(json.dumps(dict(PLAIN, fps=31)))
    assert not fp.look_recorded(jobs, VID)
    _preview(jobs, remotion, [10])
    assert fp.look_recorded(jobs, VID)
    (jobs / VID / "timeline.json").write_text(json.dumps({"totalFrames": 121, "fps": 30, "words": []}))
    assert not fp.look_recorded(jobs, VID)


def test_a_tool_that_cannot_draw_records_that_it_could_not_and_lets_the_submit_through(fake_node, jobs):
    plan, remotion, _ = fake_node
    plan({"code": 1, "stderr": "chromium could not start"})
    with pytest.raises(fp.PreviewError):
        _preview(jobs, remotion, [10])
    rec = json.loads((jobs / VID / "preview" / "record.json").read_text())
    assert rec["status"] == "unavailable" and "chromium could not start" in rec["why"]
    assert fp.look_recorded(jobs, VID)


def test_a_refused_call_records_nothing(fake_node, jobs):
    _, remotion, _ = fake_node
    with pytest.raises(fp.PreviewError):
        _preview(jobs, remotion, [999])          # the caller's mistake, not the tool's
    assert not fp.look_recorded(jobs, VID)


def test_a_planted_or_damaged_record_is_no_look(fake_node, jobs, tmp_path):
    _, remotion, _ = fake_node
    folder = jobs / VID / "preview"
    folder.mkdir()
    (folder / "record.json").write_text("not json")
    assert not fp.look_recorded(jobs, VID)
    (folder / "record.json").write_text(json.dumps({"sha": "x", "status": "ok"}))
    assert not fp.look_recorded(jobs, VID)
    (folder / "record.json").unlink()
    elsewhere = tmp_path / "rec.json"
    _preview(jobs, remotion, [10])
    elsewhere.write_text((folder / "record.json").read_text())
    (folder / "record.json").unlink()
    (folder / "record.json").symlink_to(elsewhere)
    assert not fp.look_recorded(jobs, VID)       # a record read through a link is refused


def test_a_clean_call_keeps_the_record_of_the_look_before(fake_node, jobs):
    _, remotion, _ = fake_node
    _preview(jobs, remotion, [10])
    _preview(jobs, remotion, [20])
    assert json.loads((jobs / VID / "preview" / "record.json").read_text())["frames"] == [20]


# ── The MCP tool ────────────────────────────────────────────────────────────────

def test_the_tool_is_registered_and_refuses_what_it_cannot_draw(through_mcp):
    import asyncio
    from fastmcp import Client

    async def go():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]
    assert "preview_frames" in asyncio.run(go())
    result, _ = through_mcp("preview_frames", video_id="../x", frames=[1])
    assert "error" in result


# ── submit_render asks for the look ─────────────────────────────────────────────

@pytest.fixture
def queued_video(tmp_path, monkeypatch):
    """A VOICE_READY video with a plain scene-config, in a real (temporary) database and jobs directory."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    jobs_dir = tmp_path / "jobs"
    monkeypatch.setattr(server, "JOBS_DIR", jobs_dir)
    d = jobs_dir / VID
    d.mkdir(parents=True)
    (d / "scene-config.json").write_text(json.dumps(PLAIN))
    (d / "timeline.json").write_text(json.dumps({"totalFrames": 120, "fps": 30, "words": []}))
    (d / "audio.mp3").write_bytes(b"\x00" * 100)
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, voice_file_path, timeline_path, scene_config_path, "
            "created_at, updated_at) VALUES (?, NULL, 't', 'VOICE_READY', 'audio.mp3', 'timeline.json', 'scene-config.json', 'x', 'x')",
            (VID,))
    return jobs_dir


def test_submit_render_refuses_a_video_nobody_looked_at(queued_video):
    result = server.submit_render(VID)
    assert result["error"] == "preview_not_taken" and "preview_frames" in result["detail"]


def test_submit_render_queues_after_a_look_and_refuses_again_after_a_rewrite(queued_video):
    d = queued_video / VID
    fp._write_record(d / "preview", fp._content_hash(d / "scene-config.json", d / "timeline.json"), "ok", [10])
    (d / "scene-config.json").write_text(json.dumps(dict(PLAIN, fps=31)))
    assert server.submit_render(VID)["error"] == "preview_not_taken"
    fp._write_record(d / "preview", fp._content_hash(d / "scene-config.json", d / "timeline.json"), "unavailable", [10], "down")
    assert server.submit_render(VID) == {"status": "queued", "video_id": VID}


def test_a_cartoon_3d_video_is_not_asked_for_a_preview(queued_video):
    (queued_video / VID / "scene-config.json").write_text(json.dumps(CARTOON))
    assert server._preview_block(VID) is None
