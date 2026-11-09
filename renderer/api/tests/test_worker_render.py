"""The worker's render backstops and its review thread: a render whose renderer
stopped heartbeating is re-queued once its lease runs out, a GPU-only video no
renderer can take is failed (at once with no GPU renderer at all, after the
wait with one that is only offline), and every uploaded render gets its AI
review tail on a thread of its own.

Run from renderer/api/: pytest tests/test_worker_render.py
"""
import json
import os
import sqlite3
import unittest.mock as mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
import render_results
import worker
from tubematic_core import renderers

VERSION = "9.9.9"
PAST = "2020-01-01T00:00:00Z"
FUTURE = "2999-01-01T00:00:00Z"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    pipeline._init_db(p)
    monkeypatch.setattr(worker, "DB_PATH", p)
    monkeypatch.setattr(render_results, "DB_PATH", p)
    monkeypatch.setattr(render_results, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setenv("TUBEMATIC_VERSION", VERSION)
    monkeypatch.delenv("MAX_RENDER_RETRIES", raising=False)
    monkeypatch.delenv("GEMINI_REVIEW_ENABLED", raising=False)
    return p


def _sql(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(sql, params).fetchall()]
        con.commit()
        return rows
    finally:
        con.close()


def _seed(db_path, vid="vid-1", status="RENDERING", renderer_id="", lease="", uploaded="",
          updated="2026-01-01T00:00:00Z", visual_style="auto", mascot_id="", fail_count=0):
    _sql(db_path, "INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
                  "renderer_id, render_lease_until, render_uploaded_at, render_started_at, visual_style, "
                  "mascot_id, render_fail_count, video_path, created_at, updated_at) "
                  "VALUES (?, 'p', 't', 'manual', 8, ?, ?, ?, ?, ?, ?, ?, ?, '/out/p/x.mp4', "
                  "'2026-01-01T00:00:00Z', ?)",
         (vid, status, renderer_id, lease, uploaded, "2026-01-01T00:00:00Z" if renderer_id else "",
          visual_style, mascot_id, fail_count, updated))


def _video(db_path, vid="vid-1"):
    return _sql(db_path, "SELECT * FROM videos WHERE id = ?", (vid,))[0]


def _comments(db_path, vid="vid-1"):
    return [r["content"] for r in _sql(db_path, "SELECT content FROM comments WHERE video_id = ? ORDER BY id", (vid,))]


def _remote(db_path, rid="r_a", name="Studio PC", heartbeat=None, gpu=False, probe=None, version=VERSION,
            enabled=1):
    _sql(db_path, "INSERT INTO renderers (id, name, builtin, enabled, version, last_heartbeat_at, gpu_verified, "
                  "gpu_probe, created_at) VALUES (?, ?, 0, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')",
         (rid, name, enabled, version, heartbeat if heartbeat is not None else renderers.now_ts(),
          1 if gpu else 0, json.dumps(probe) if probe else ""))


def _builtin_probe(db_path, ok=False, configured=False):
    _sql(db_path, "UPDATE renderers SET gpu_probe = ?, gpu_verified = ?, version = ?, last_heartbeat_at = ? "
                  "WHERE id = 'builtin'",
         (json.dumps({"at": "x", "configured": configured, "ok": ok, "error": "" if ok else "no GPU"}),
          1 if ok else 0, VERSION, renderers.now_ts()))


# ── the lease sweep ───────────────────────────────────────────────────────────

def test_an_expired_lease_is_requeued_with_the_renderers_name(db_path):
    _remote(db_path)
    _seed(db_path, renderer_id="r_a", lease=PAST)
    worker._sweep_render_leases()
    v = _video(db_path)
    assert v["status"] == "RENDER_QUEUED" and v["render_fail_count"] == 1 and v["renderer_id"] == ""
    assert _comments(db_path) == ["Render lost: Studio PC stopped reporting — automatically re-queued."]


def test_a_lost_render_past_the_retry_cap_fails(db_path):
    _remote(db_path)
    _seed(db_path, renderer_id="r_a", lease=PAST, fail_count=1)
    worker._sweep_render_leases()
    assert _video(db_path)["status"] == "FAILED"
    assert _comments(db_path) == ["Render lost: Studio PC stopped reporting 2 times (limit 1) — giving up."]


def test_a_render_in_flight_across_the_upgrade_is_requeued(db_path):
    """A pre-gateway renderer's RENDERING row carries no renderer at all."""
    _seed(db_path)
    worker._sweep_render_leases()
    assert _video(db_path)["status"] == "RENDER_QUEUED"
    assert _comments(db_path) == ["Render interrupted by the upgrade — automatically re-queued."]


@pytest.mark.parametrize("kw", [
    {"renderer_id": "r_a", "lease": FUTURE},                              # still held
    {"renderer_id": "r_a", "lease": PAST, "uploaded": "2026-01-01T00:00:01Z"},   # uploaded: the review's
    {"renderer_id": "", "uploaded": "2026-01-01T00:00:01Z"},
    {"renderer_id": "r_a", "lease": PAST, "status": "RENDER_QUEUED"},
])
def test_the_lease_sweep_touches_only_expired_unuploaded_renders(db_path, kw):
    _remote(db_path)
    _seed(db_path, **kw)
    before = _video(db_path)
    worker._sweep_render_leases()
    assert _video(db_path) == before
    assert _comments(db_path) == []


def test_the_lease_sweep_never_raises(db_path, monkeypatch):
    monkeypatch.setattr(worker, "DB_PATH", "/nonexistent/dir/that/cannot/be/made\0")
    worker._sweep_render_leases()


# ── the GPU wait sweep ────────────────────────────────────────────────────────

def test_a_gpu_video_with_no_gpu_renderer_at_all_fails_at_once(db_path):
    _builtin_probe(db_path, ok=False, configured=False)
    _seed(db_path, status="RENDER_QUEUED", visual_style="cartoon_3d", updated=renderers.now_ts())
    _seed(db_path, "vid-2", status="RENDER_QUEUED", updated=renderers.now_ts())
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "FAILED"
    [comment] = _comments(db_path)
    assert comment.startswith("Not rendered, moved to FAILED: this video is Cartoon 3D, which renders on the GPU only")
    assert "Built-in renderer" in comment and "--step gpu" in comment
    assert _video(db_path, "vid-2")["status"] == "RENDER_QUEUED"     # an ordinary video renders anywhere


def test_a_gpu_video_waits_while_a_renderer_has_not_probed_yet(db_path):
    """Right after an upgrade the built-in renderer has no probe: nothing is
    judged on no evidence."""
    _seed(db_path, status="RENDER_QUEUED", mascot_id="m1", updated=renderers.now_ts())
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "RENDER_QUEUED"


def test_a_gpu_video_waits_for_an_offline_gpu_renderer_then_fails(db_path):
    _builtin_probe(db_path, ok=False)
    _remote(db_path, heartbeat=PAST, gpu=True, probe={"configured": True, "ok": True})
    _seed(db_path, status="RENDER_QUEUED", mascot_id="m1", updated=renderers.now_ts())
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "RENDER_QUEUED"
    _sql(db_path, "UPDATE videos SET updated_at = ?", (renderers.ts_add(renderers.now_ts(), -renderers.GPU_WAIT_SECS - 5),))
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "FAILED"
    [comment] = _comments(db_path)
    assert "has a mascot" in comment and "30 minutes" in comment
    assert f"Studio PC: offline since {PAST}, GPU working" in comment


@pytest.mark.parametrize("state", ["needs_upgrade", "disabled"])
def test_a_gpu_renderer_that_cannot_take_work_does_not_count_as_ready(db_path, state):
    _builtin_probe(db_path, ok=False)
    _remote(db_path, gpu=True, probe={"configured": True, "ok": True},
            version="1.0.0" if state == "needs_upgrade" else VERSION, enabled=0 if state == "disabled" else 1)
    _seed(db_path, status="RENDER_QUEUED", visual_style="cartoon_3d",
          updated=renderers.ts_add(renderers.now_ts(), -renderers.GPU_WAIT_SECS - 5))
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "FAILED"
    assert ("needs upgrade" if state == "needs_upgrade" else "disabled") in _comments(db_path)[0]


def test_a_gpu_video_with_a_ready_gpu_renderer_is_left_alone(db_path):
    _builtin_probe(db_path, ok=True, configured=True)
    _seed(db_path, status="RENDER_QUEUED", visual_style="cartoon_3d", updated=PAST)
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "RENDER_QUEUED"


def test_a_cartoon_scene_config_counts_under_auto(db_path, tmp_path):
    _builtin_probe(db_path, ok=False)
    _seed(db_path, status="RENDER_QUEUED", updated=renderers.now_ts())
    job = tmp_path / "jobs" / "vid-1"
    job.mkdir(parents=True)
    (job / "scene-config.json").write_text(json.dumps(
        {"scenes": [{"type": "generated", "src": "vid-1/C", "props": {"cartoon3d": {"beats": []}}}]}))
    worker._sweep_gpu_waits()
    assert _video(db_path)["status"] == "FAILED"


def test_the_gpu_sweep_never_raises(db_path, monkeypatch):
    monkeypatch.setattr(worker, "DB_PATH", "/nonexistent/dir/that/cannot/be/made\0")
    worker._sweep_gpu_waits()


# ── the review thread ─────────────────────────────────────────────────────────

def test_the_review_pass_finishes_the_oldest_uploaded_render(db_path):
    _seed(db_path, "vid-2", uploaded="2026-01-01T00:00:09Z")
    _seed(db_path, "vid-1", uploaded="2026-01-01T00:00:05Z")
    _seed(db_path, "vid-3", renderer_id="r_a", lease=FUTURE)          # still rendering: not reviewable
    assert worker._review_once() is True
    assert _video(db_path)["status"] == "VIDEO_READY"                 # review is off: straight through
    assert _video(db_path, "vid-2")["status"] == "RENDERING"
    assert worker._review_once() is True
    assert _video(db_path, "vid-2")["status"] == "VIDEO_READY"
    assert worker._review_once() is False
    assert _video(db_path, "vid-3")["status"] == "RENDERING"


def test_the_review_pass_calls_the_shared_review_tail(db_path):
    _seed(db_path, uploaded="2026-01-01T00:00:05Z")
    with mock.patch.object(render_results, "finish_render") as finish:
        worker._review_once()
    finish.assert_called_once_with("vid-1")


def test_main_starts_the_review_thread_before_its_loop(db_path, monkeypatch):
    started = []
    monkeypatch.setattr(worker, "_start_review_thread", lambda: started.append(True))

    class Stop(Exception):
        pass

    def stop(_secs):
        raise Stop
    monkeypatch.setattr(worker.time, "sleep", stop)
    for name in ("_poll_publishing_videos", "_sweep_auto_pilot", "_poll_video_metrics", "_sync_prices_if_due",
                 "_sweep_retention", "_sweep_notifications", "_sweep_stalled_voicing"):
        monkeypatch.setattr(worker, name, lambda: None)
    calls = []
    monkeypatch.setattr(worker, "_sweep_render_leases", lambda: calls.append("leases"))
    monkeypatch.setattr(worker, "_sweep_gpu_waits", lambda: calls.append("gpu"))
    monkeypatch.setattr(worker.tlog, "setup_json_logging", lambda *a, **k: None)
    with pytest.raises(Stop):
        worker.main()
    assert started == [True]
    assert calls == ["leases", "gpu"]


def test_the_review_thread_is_a_daemon_that_survives_a_failing_pass(db_path, monkeypatch):
    passes = []

    def boom():
        passes.append(1)
        if len(passes) == 1:
            raise RuntimeError("db gone")
        raise SystemExit   # ends the loop for the test
    monkeypatch.setattr(worker, "_review_once", boom)
    monkeypatch.setattr(worker.time, "sleep", lambda _s: None)
    with pytest.raises(SystemExit):
        worker._review_loop()
    assert len(passes) == 2
    with mock.patch.object(worker, "_review_loop"):
        thread = worker._start_review_thread()
        thread.join(5)
    assert thread.daemon
