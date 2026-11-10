"""validate_job's typecheck: scoped to one video, killed whole on a timeout,
and run one call at a time.

A whole-project `npx tsc` grew with every video an install made (60 s and
1.6 GB on a 349-video install); on a timeout subprocess.run killed npx and left
tsc running; and several agent sessions validating at once stacked those tsc
processes until the host ran out of memory. These tests pin each part of the
fix with a fake `npx` that records what it was asked to do.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import pytest

import server

VID = "vid_aaaaaaaaaaaa"

FAKE_NPX = r'''#!PYTHON
import json, os, subprocess, sys, time
log = os.environ["FAKE_NPX_LOG"]
mode = os.environ.get("FAKE_NPX_MODE", "pass")
config = sys.argv[sys.argv.index("-p") + 1]
with open(log, "a") as fh:
    fh.write(json.dumps({"event": "start", "t": time.time(), "argv": sys.argv[1:],
                         "config_path": config, "config": json.load(open(config))}) + "\n")
if mode == "hang":
    # what npx does: tsc is a child of its own, which a kill of npx alone misses
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    with open(os.environ["FAKE_NPX_CHILD"], "w") as fh:
        fh.write(str(child.pid))
    time.sleep(120)
if mode == "slow":
    time.sleep(0.4)
with open(log, "a") as fh:
    fh.write(json.dumps({"event": "end", "t": time.time()}) + "\n")
if mode == "fail":
    print("src/scenes/generated/x/hero.tsx(1,7): error TS2322: Type 'string' is not assignable")
    sys.exit(2)
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throwaway Remotion dir with a tsconfig.json, a generated-scenes tree
    and a fake npx; returns a reader for the fake's call log."""
    remotion = tmp_path / "repo" / "remotion"
    scenes = remotion / "src" / "scenes" / "generated"
    scenes.mkdir(parents=True)
    (remotion / "tsconfig.json").write_text("{}")
    monkeypatch.setattr(server, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(server, "SCENES_DIR", scenes)

    npx = tmp_path / "npx"
    npx.write_text(FAKE_NPX.replace("PYTHON", sys.executable))
    npx.chmod(0o755)
    real_which = server.shutil.which
    monkeypatch.setattr(server.shutil, "which", lambda name: str(npx) if name == "npx" else real_which(name))
    log = tmp_path / "npx.log"
    monkeypatch.setenv("FAKE_NPX_LOG", str(log))

    def calls():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    calls.remotion = remotion
    calls.scenes = scenes
    return calls


def _scene(project, video_id, name):
    d = project.scenes / video_id
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.tsx"
    f.write_text("export default () => null;\n")
    return f


def _leftover_configs(project):
    return sorted(p.name for p in project.remotion.glob("tsconfig.validate-*"))


# ── Scope ─────────────────────────────────────────────────────────────────────

def test_the_typecheck_covers_only_this_video(project):
    hero = _scene(project, VID, "hero")
    _scene(project, "vid_bbbbbbbbbbbb", "other")
    assert server._typecheck_video(VID, [hero]) is None
    start = project()[0]
    assert start["argv"][:3] == ["tsc", "--noEmit", "-p"]
    assert start["config"]["extends"] == "./tsconfig.json"
    assert start["config"]["include"] == [f"{project.scenes / VID}/**/*", str(hero)]
    assert "vid_bbbbbbbbbbbb" not in json.dumps(start["config"])
    # beside tsconfig.json, so tsc finds node_modules/@types from there
    assert os.path.dirname(start["config_path"]) == str(project.remotion)


def test_a_scene_borrowed_from_elsewhere_is_included_by_file(project):
    """A config may name a legacy flat scene or another video's file: that
    file is what renders, so it is checked."""
    _scene(project, VID, "hero")
    legacy = project.scenes / "legacy-intro.tsx"
    legacy.write_text("export default () => null;\n")
    server._typecheck_video(VID, [legacy])
    assert str(legacy) in project()[0]["config"]["include"]


def test_no_scenes_of_its_own_means_no_typecheck(project):
    assert server._typecheck_video(VID, []) is None
    assert project() == []


def test_an_emptied_scene_directory_is_not_an_input(project):
    """delete_scene_file leaves the directory behind; an include that matches
    nothing makes tsc fail with "No inputs were found", which would block a
    video whose scenes are all installed ones."""
    (project.scenes / VID).mkdir()
    (project.scenes / VID / "notes.txt").write_text("not source")
    assert server._typecheck_video(VID, []) is None
    assert project() == []
    installed = project.remotion / "src" / "scenes" / "generated" / "legacy.tsx"
    installed.write_text("export default () => null;\n")
    server._typecheck_video(VID, [installed])
    assert project()[0]["config"]["include"] == [str(installed)]


def test_the_temporary_config_is_removed(project, monkeypatch):
    hero = _scene(project, VID, "hero")
    server._typecheck_video(VID, [hero])
    monkeypatch.setenv("FAKE_NPX_MODE", "fail")
    assert "TypeScript typecheck failed" in server._typecheck_video(VID, [hero])
    assert _leftover_configs(project) == []


def test_a_type_error_is_reported(project, monkeypatch):
    hero = _scene(project, VID, "hero")
    monkeypatch.setenv("FAKE_NPX_MODE", "fail")
    err = server._typecheck_video(VID, [hero])
    assert err.startswith("TypeScript typecheck failed")
    assert "TS2322" in err


# ── Timeout ───────────────────────────────────────────────────────────────────

def _dead(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] == "Z"
    except FileNotFoundError:
        return True


def test_a_timeout_kills_tsc_as_well_as_npx(project, monkeypatch, tmp_path):
    """The regression: subprocess.run(timeout=) killed npx and left its tsc
    child running. Every process npx started must be gone."""
    hero = _scene(project, VID, "hero")
    child_file = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_NPX_MODE", "hang")
    monkeypatch.setenv("FAKE_NPX_CHILD", str(child_file))
    monkeypatch.setattr(server, "TYPECHECK_TIMEOUT_SECS", 2)
    err = server._typecheck_video(VID, [hero])
    assert "ran out of time" in err
    assert "call validate_job again" in err
    assert "infinite type loops" not in err
    child = int(child_file.read_text())
    deadline = time.monotonic() + 5
    while not _dead(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _dead(child), "the timed-out typecheck's child process is still running"
    assert _leftover_configs(project) == []


# ── One at a time ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def videos(project, tmp_path, monkeypatch):
    """Minimal valid job files for two videos, each with one generated scene."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    ids = [VID, "vid_cccccccccccc"]
    for vid in ids:
        _scene(project, vid, "hero")
        job = tmp_path / "jobs" / vid
        job.mkdir(parents=True)
        (job / "audio.mp3").write_bytes(b"0" * 60_000)
        (job / "timeline.json").write_text(json.dumps(
            {"totalFrames": 50, "fps": 30, "audioDurationSeconds": 50 / 30, "words": []}))
        (job / "scene-config.json").write_text(json.dumps(
            {"totalFrames": 50, "fps": 30,
             "scenes": [{"type": "generated", "src": f"{vid}/hero", "startFrame": 0, "durationInFrames": 50}]}))
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, topic, voice_file_path, timeline_path, scene_config_path, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (vid, "t", str(job / "audio.mp3"), str(job / "timeline.json"),
                 str(job / "scene-config.json"), _now(), _now()))
    return ids


def test_concurrent_validations_never_overlap_their_typecheck(project, videos, monkeypatch):
    monkeypatch.setenv("FAKE_NPX_MODE", "slow")
    results = {}
    threads = [threading.Thread(target=lambda v=v: results.__setitem__(v, server.validate_job(v)))
               for v in videos]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    events = project()
    assert [e["event"] for e in events] == ["start", "end", "start", "end"]
    for vid in videos:
        assert not any("TypeScript" in e for e in results[vid]["errors"]), results[vid]


def test_a_busy_checker_is_reported_and_not_queued_forever(project, videos, monkeypatch):
    monkeypatch.setattr(server, "HEAVY_CHECK_WAIT_SECS", 0.2)
    assert server._heavy_checks_lock.acquire(timeout=1)
    try:
        result = server.validate_job(VID)
    finally:
        server._heavy_checks_lock.release()
    assert result["passed"] is False
    assert any("call validate_job again" in e for e in result["errors"])
    assert project() == []
