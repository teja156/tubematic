"""Tests for the TMDEV-61 cross-call scene-work claim: an owner-keyed,
TTL-refreshed in-process lock guarding generate_image, write_scene_file,
write_scene_config, and submit_render, so two agent sessions can't duplicate
paid work or clobber each other's scene-config on the same video.

Unlike generate_voice's _voicing_in_progress (a bare per-call set), this
claim spans many calls, so it needs an owner (a session can safely re-enter
its own claim) and a TTL (a crashed session's claim self-heals instead of
wedging the video until an MCP server restart).

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import threading
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def clear_claims():
    """_scene_claims is a module-global dict — without this, a claim left by
    one test (deliberately, since the claim is meant to survive across
    calls) leaks into the next test that reuses the same video_id."""
    server._scene_claims.clear()
    yield
    server._scene_claims.clear()


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()

    def make_video(video_id, status="VOICE_READY"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos "
                "(id, project_id, topic, status, voice_file_path, timeline_path, "
                " scene_config_path, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id, "test topic", status,
                    str(tmp_path / "audio.mp3"), str(tmp_path / "timeline.json"),
                    str(tmp_path / "scene-config.json"),
                    _now(), _now(),
                ),
            )

    return make_video


@pytest.fixture
def scene_dirs(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    generated.mkdir()
    monkeypatch.setattr(server, "SCENES_DIR", generated)
    monkeypatch.setattr(server, "INSTALLED_DIR", tmp_path / "installed")


# ── Primitives ────────────────────────────────────────────────────────────

def test_claim_is_granted_to_first_owner():
    assert server._try_claim_scene_work("vid_1", "session:a") is None


def test_second_owner_is_rejected_and_gets_the_holder_back():
    server._try_claim_scene_work("vid_1", "session:a")
    assert server._try_claim_scene_work("vid_1", "session:b") == "session:a"


def test_same_owner_reclaims_and_refreshes(monkeypatch):
    calls = iter([100.0, 200.0])
    monkeypatch.setattr(server.time, "monotonic", lambda: next(calls))
    assert server._try_claim_scene_work("vid_1", "session:a") is None
    first_expiry = server._scene_claims["vid_1"][1]
    assert server._try_claim_scene_work("vid_1", "session:a") is None
    assert server._scene_claims["vid_1"][1] > first_expiry


def test_expired_claim_is_reclaimable_by_anyone(monkeypatch):
    monkeypatch.setattr(server, "SCENE_CLAIM_TTL_SECS", 0)
    server._try_claim_scene_work("vid_1", "session:a")
    assert server._try_claim_scene_work("vid_1", "session:b") is None


def test_release_is_owner_checked():
    server._try_claim_scene_work("vid_1", "session:a")
    server._release_scene_claim("vid_1", "session:b")  # no-op, wrong owner
    assert server._try_claim_scene_work("vid_1", "session:b") == "session:a"


def test_release_with_owner_none_is_unconditional():
    server._try_claim_scene_work("vid_1", "session:a")
    server._release_scene_claim("vid_1")
    assert server._try_claim_scene_work("vid_1", "session:b") is None


def test_expired_entries_are_pruned(monkeypatch):
    monkeypatch.setattr(server, "SCENE_CLAIM_TTL_SECS", 0)
    server._try_claim_scene_work("vid_1", "session:a")
    server._try_claim_scene_work("vid_2", "session:b")  # any claim attempt prunes
    assert "vid_1" not in server._scene_claims


# ── Owner resolution ──────────────────────────────────────────────────────

def test_session_owner_falls_back_outside_a_request_context():
    assert server._session_owner() == "no-session"


def test_session_owner_never_raises_on_a_broken_context(monkeypatch):
    def _broken():
        raise AttributeError("shape changed")
    monkeypatch.setattr(
        "fastmcp.server.dependencies.get_context", _broken, raising=False
    )
    assert server._session_owner() == "no-session"


# ── Tool guards ───────────────────────────────────────────────────────────

def test_generate_image_rejected_for_non_owner_before_any_http_call(job_db, monkeypatch):
    job_db("vid_1")
    monkeypatch.setattr(server, "_openai_key", lambda: "k")
    # A real (non-"no-session") calling identity — bare calls resolve to the
    # no-session fallback, which never checks or holds a claim by design (see
    # _guard_scene_work), so a meaningful "rejected as a non-owner" test needs
    # a real owner on the calling side too.
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._try_claim_scene_work("vid_1", "session:other")

    called = []
    import httpx

    class _Client:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **kw):
            called.append(1)
            raise AssertionError("must not be called")
    monkeypatch.setattr(httpx, "Client", _Client)

    result = server.generate_image("vid_1", "skyline", "a prompt")
    assert result["error"] == "scene_work_claimed"
    assert result["claimed_by"] == "session:other"
    assert called == []


def test_write_scene_file_rejected_for_non_owner_writes_nothing(job_db, scene_dirs, monkeypatch):
    job_db("vid_1")
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._try_claim_scene_work("vid_1", "session:other")

    result = server.write_scene_file("vid_1", "intro-hook", "x")
    assert result["error"] == "scene_work_claimed"
    assert not (server.SCENES_DIR / "vid_1").exists()


def test_write_scene_config_rejected_for_non_owner_leaves_scene_config_path_unset(job_db, monkeypatch):
    job_db("vid_1")
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._try_claim_scene_work("vid_1", "session:other")

    config = {"totalFrames": 300, "fps": 30,
              "scenes": [{"type": "generated", "src": "x", "startFrame": 0, "durationInFrames": 300}]}
    result = server.write_scene_config("vid_1", config)
    assert result["error"] == "scene_work_claimed"
    with server._conn() as con:
        row = con.execute("SELECT scene_config_path FROM videos WHERE id = ?", ("vid_1",)).fetchone()
    assert row["scene_config_path"] != ""


def test_submit_render_rejected_for_non_owner_leaves_status_voice_ready(job_db, monkeypatch):
    job_db("vid_1", status="VOICE_READY")
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._try_claim_scene_work("vid_1", "session:other")

    result = server.submit_render("vid_1")
    assert result["error"] == "scene_work_claimed"
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_1",)).fetchone()
    assert row["status"] == "VOICE_READY"


def test_unclaimed_video_passes_every_guard(job_db, scene_dirs, monkeypatch):
    """The normal single-session path: nobody pre-claims, every guarded tool
    just works. This is the concrete proof claim-on-first-use doesn't change
    existing behavior."""
    job_db("vid_1", status="VOICE_READY")
    monkeypatch.setattr(server, "_openai_key", lambda: "k")

    import httpx
    import base64

    class _Client:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **kw):
            class R:
                status_code = 200
                def json(self):
                    return {"data": [{"b64_json": base64.b64encode(b"x").decode()}]}
            return R()
    monkeypatch.setattr(httpx, "Client", _Client)

    assert "error" not in server.generate_image("vid_1", "skyline", "a prompt")
    assert "error" not in server.write_scene_file("vid_1", "intro-hook", "x")
    config = {"totalFrames": 300, "fps": 30,
              "scenes": [{"type": "generated", "src": "vid_1/intro-hook",
                          "startFrame": 0, "durationInFrames": 300}]}
    assert "error" not in server.write_scene_config("vid_1", config)
    assert "error" not in server.submit_render("vid_1")


def test_first_guarded_call_takes_the_claim_for_a_real_owner(job_db, scene_dirs, monkeypatch):
    monkeypatch.setattr(server, "_session_owner", lambda: "session:real")
    job_db("vid_1")
    server.write_scene_file("vid_1", "intro-hook", "x")
    video = server.get_video("vid_1")
    assert video["claimed_by"] == "session:real"
    assert video["claim_expires_in_secs"] > 0


def test_no_session_caller_never_takes_a_claim(job_db, scene_dirs):
    """A context-free caller (bare function call, the "no-session" fallback)
    must never hold a cross-call claim: every such caller shares the same
    owner string, so a claim taken under it could block a real, distinct
    session for the full TTL with no way for that real session to ever be
    recognized as the same "owner" and release it."""
    job_db("vid_1")
    assert server._session_owner() == "no-session"
    server.write_scene_file("vid_1", "intro-hook", "x")
    assert server.get_video("vid_1")["claimed_by"] is None


def test_no_session_caller_is_never_blocked_by_a_stale_no_session_claim(job_db, scene_dirs):
    """Guards against the fix regressing: even if 'no-session' somehow ends up
    in _scene_claims (e.g. a leftover from before this fix, or a future bug),
    a subsequent no-session call must not be rejected by it — the whole point
    is that this identity never participates in the claim at all."""
    server._scene_claims["vid_1"] = ("no-session", server.time.monotonic() + 900)
    job_db("vid_1")
    result = server.write_scene_file("vid_1", "intro-hook", "x")
    assert "error" not in result


def test_cheap_validation_errors_do_not_take_a_claim(job_db, scene_dirs):
    job_db("vid_1")
    assert "error" in server.write_scene_file("vid_1", "not valid!", "x")
    assert server.get_video("vid_1")["claimed_by"] is None


def test_unknown_video_does_not_take_a_claim(job_db, scene_dirs):
    job_db("vid_1")  # ensures DB is initialized
    result = server.write_scene_file("vid_nope", "intro-hook", "x")
    assert "error" in result
    assert "vid_nope" not in server._scene_claims


# ── Release ───────────────────────────────────────────────────────────────

def test_submit_render_releases_on_success(job_db):
    job_db("vid_1", status="VOICE_READY")
    server._try_claim_scene_work("vid_1", "no-session")
    server.submit_render("vid_1")
    assert "vid_1" not in server._scene_claims


@pytest.mark.parametrize("new_status", ["FAILED", "SCRIPT_READY", "RENDER_QUEUED"])
def test_set_video_status_out_of_the_window_releases(job_db, new_status):
    job_db("vid_1", status="REVISION_REQUESTED")
    server._try_claim_scene_work("vid_1", "session:a")
    server.set_video_status("vid_1", new_status)
    assert "vid_1" not in server._scene_claims


def test_set_video_status_within_the_window_preserves_the_claim(job_db):
    """The revision-loop regression test: the animation-revision path calls
    write_scene_file/write_scene_config while REVISION_REQUESTED, then moves
    to VOICE_READY before submit_render. That transition must not release
    the claim mid-revision."""
    job_db("vid_1", status="REVISION_REQUESTED")
    server._try_claim_scene_work("vid_1", "session:a")
    server.set_video_status("vid_1", "VOICE_READY")
    assert server._scene_claims["vid_1"][0] == "session:a"


def test_status_mismatch_does_not_release(job_db):
    job_db("vid_1", status="VOICE_READY")
    server._try_claim_scene_work("vid_1", "session:a")
    result = server.set_video_status("vid_1", "FAILED", only_if_current_status="REVISION_REQUESTED")
    assert result["error"] == "status_mismatch"
    assert server._scene_claims["vid_1"][0] == "session:a"


def test_revision_loop_end_to_end(job_db, scene_dirs):
    job_db("vid_1", status="REVISION_REQUESTED")
    server.write_scene_file("vid_1", "intro-hook", "x")  # claims as "no-session"
    server.set_video_status("vid_1", "VOICE_READY")
    config = {"totalFrames": 300, "fps": 30,
              "scenes": [{"type": "generated", "src": "vid_1/intro-hook",
                          "startFrame": 0, "durationInFrames": 300}]}
    assert "error" not in server.write_scene_config("vid_1", config)
    result = server.submit_render("vid_1")
    assert result == {"status": "queued", "video_id": "vid_1"}


# ── Debug surface ─────────────────────────────────────────────────────────

def test_get_video_reports_claim_state(job_db):
    job_db("vid_1")
    server._try_claim_scene_work("vid_1", "session:a")
    video = server.get_video("vid_1")
    assert video["claimed_by"] == "session:a"
    assert video["claim_expires_in_secs"] > 0


def test_get_video_reports_null_claim_when_unclaimed_or_expired(job_db, monkeypatch):
    job_db("vid_1")
    assert server.get_video("vid_1")["claimed_by"] is None

    monkeypatch.setattr(server, "SCENE_CLAIM_TTL_SECS", 0)
    server._try_claim_scene_work("vid_1", "session:a")
    assert server.get_video("vid_1")["claimed_by"] is None


def test_get_pipeline_status_lists_live_claims_and_session_owner(job_db):
    job_db("vid_1")
    server._try_claim_scene_work("vid_1", "session:a")
    status = server.get_pipeline_status()
    assert status["session_owner"] == "no-session"
    assert {"video_id": "vid_1", "claimed_by": "session:a",
            "expires_in_secs": status["scene_claims"][0]["expires_in_secs"]} in status["scene_claims"]


# ── Concurrency ───────────────────────────────────────────────────────────

def test_two_threads_only_one_wins():
    results = []
    barrier = threading.Barrier(20)

    def attempt(owner):
        barrier.wait()
        results.append(server._try_claim_scene_work("vid_race", owner))

    threads = [threading.Thread(target=attempt, args=(f"session:{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(None) == 1
