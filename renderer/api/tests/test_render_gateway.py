"""The render gateway, render_gateway.py: the only API a renderer calls.

Who may call (the built-in renderer's token read per request, an enrolled
remote credential with expiry and rotation, never the API's own token), which
video a claim hands out (the scheduler's pick, GPU videos only to a renderer
whose GPU passed its probe, the pre-render refusals), the lease that keeps a
lost renderer from touching a video another one took over, the bundle and the
upload, and how each result moves the video.

Driven through Flask's test client against a migrated temporary database; one
test serves the app over real TLS to prove the pinned certificate is what a
client trusts.

Run from renderer/api/: pytest tests/test_render_gateway.py
"""
import io
import json
import os
import sqlite3
import ssl
import tarfile
import threading
import time
import urllib.error
import urllib.request

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
import render_gateway
import render_results
from tubematic_core import auth as tauth
from tubematic_core import renderers

VERSION = "9.9.9"
BUILTIN_TOKEN = "builtin-token-for-tests"
API_TOKEN = "api-token-for-tests"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    pipeline._init_db(db_path)
    jobs, out, remotion, secrets = (tmp_path / n for n in ("jobs", "out", "remotion", "secrets"))
    for d in (jobs, out, remotion / "src" / "scenes" / "generated", secrets):
        d.mkdir(parents=True)
    (secrets / "builtin_renderer_token").write_text(BUILTIN_TOKEN)
    (secrets / "api_token").write_text(API_TOKEN)
    monkeypatch.setattr(render_results, "DB_PATH", db_path)
    monkeypatch.setattr(render_results, "JOBS_DIR", jobs)
    monkeypatch.setattr(render_results, "OUTPUT_DIR", out)
    monkeypatch.setenv("TUBEMATIC_VERSION", VERSION)
    for var in ("GEMINI_REVIEW_ENABLED", "MAX_RENDER_RETRIES", "WATERMARK_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    app = render_gateway.create_gateway_app(db_path, jobs, out, secrets_dir=secrets, remotion_dir=remotion)

    class Env:
        pass
    e = Env()
    e.db, e.jobs, e.out, e.remotion, e.secrets = db_path, jobs, out, remotion, secrets
    e.generated = remotion / "src" / "scenes" / "generated"
    e.client = app.test_client()
    e.app = app
    return e


B = {"Authorization": f"Bearer {BUILTIN_TOKEN}"}


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _sql(env, sql, params=()):
    con = sqlite3.connect(env.db)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(sql, params).fetchall()]
        con.commit()
        return rows
    finally:
        con.close()


def _video(env, vid="vid-1"):
    return _sql(env, "SELECT * FROM videos WHERE id = ?", (vid,))[0]


def _renderer(env, rid="builtin"):
    return _sql(env, "SELECT * FROM renderers WHERE id = ?", (rid,))[0]


def _comments(env, vid="vid-1"):
    return [r["content"] for r in _sql(env, "SELECT content FROM comments WHERE video_id = ? ORDER BY id", (vid,))]


def _seed(env, vid="vid-1", status="RENDER_QUEUED", project="proj-1", updated="2026-01-01T00:00:00Z",
          visual_style="auto", mascot_id="", mascot_version=0, files=True, frames=90, scenes=None,
          written="x", **cols):
    _sql(env, "INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
              "voice_file_path, timeline_path, scene_config_path, visual_style, mascot_id, mascot_version, "
              "created_at, updated_at) VALUES (?, ?, 't', 'manual', 8, ?, ?, ?, ?, ?, ?, ?, "
              "'2026-01-01T00:00:00Z', ?)",
         (vid, project, status, written, written, written, visual_style, mascot_id, mascot_version, updated))
    for k, v in cols.items():
        _sql(env, f"UPDATE videos SET {k} = ? WHERE id = ?", (v, vid))
    if files:
        job = env.jobs / vid
        job.mkdir(parents=True, exist_ok=True)
        (job / "audio.mp3").write_bytes(b"AUDIO")
        (job / "timeline.json").write_text(json.dumps({"totalFrames": frames, "fps": 30, "words": []}))
        (job / "scene-config.json").write_text(json.dumps({"scenes": scenes or []}))


def _beat(env, headers=B, **body):
    body.setdefault("version", VERSION)
    body.setdefault("state", "idle")
    return env.client.post("/v1/heartbeat", json=body, headers=headers)


def _gpu(env, headers=B, ok=True, at="2026-01-01T00:00:00.000000Z"):
    return _beat(env, headers, gpu_probe={"at": at, "configured": True, "ok": ok,
                                          "error": "" if ok else "Chromium is rendering on another device: SwiftShader",
                                          "gpu": {"uuid": "GPU-1", "name": "GTX 1650"}})


def _enroll(env, machine_id="m-1", name="", **extra):
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, name)
    con.commit()
    con.close()
    body = {"secret": secret, "machine_id": machine_id, "name": "Studio PC", "host": "studio",
            "version": VERSION, "compute": {"cpus": 8}}
    body.update(extra)
    return env.client.post("/v1/enroll", json=body), secret


def _remote(env, machine_id="m-1", gpu=False):
    resp, _ = _enroll(env, machine_id)
    out = resp.get_json()
    h = bearer(out["credential"])
    if gpu:
        _gpu(env, h)
    else:
        _beat(env, h)
    return out["renderer_id"], h


CARTOON_SCENES = [{"type": "generated", "src": "vid-1/CartoonShort",
                   "props": {"cartoon3d": {"beats": [{"start": 0, "end": 9, "shot": "x"}]}}}]


# ── open routes and authentication ────────────────────────────────────────────

def test_version_is_open(env):
    resp = env.client.get("/v1/version")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": VERSION, "gateway": 1}


def test_every_other_route_needs_a_credential(env):
    for method, path in [("post", "/v1/heartbeat"), ("post", "/v1/claim"), ("get", "/v1/jobs/vid-1/bundle"),
                         ("put", "/v1/jobs/vid-1/output"), ("post", "/v1/jobs/vid-1/result")]:
        resp = getattr(env.client, method)(path, json={})
        assert resp.status_code == 401, path
        assert resp.get_json() == {"error": "unauthorized"}


def test_the_builtin_token_authenticates(env):
    assert _beat(env).status_code == 200
    assert _renderer(env)["last_heartbeat_at"] != ""


def test_the_api_token_is_not_a_renderer_credential(env):
    """The dashboard's token reaches every pipeline route; it must not be
    able to claim, upload or rewrite renders."""
    resp = _beat(env, bearer(API_TOKEN))
    assert resp.status_code == 401
    assert env.client.post("/v1/claim", json={}, headers=bearer(API_TOKEN)).status_code == 401


def test_a_missing_builtin_secret_fails_closed(env):
    (env.secrets / "builtin_renderer_token").unlink()
    assert _beat(env).status_code == 401
    (env.secrets / "builtin_renderer_token").write_text("")
    assert _beat(env).status_code == 401
    # an absent secret must not let an empty or whitespace token through either
    assert env.client.post("/v1/heartbeat", json={}, headers={"Authorization": "Bearer  "}).status_code == 401


def test_a_rotated_builtin_token_applies_without_a_restart(env):
    (env.secrets / "builtin_renderer_token").write_text("rotated")
    assert _beat(env).status_code == 401
    assert _beat(env, bearer("rotated")).status_code == 200


def test_a_remote_credential_authenticates(env):
    rid, h = _remote(env)
    assert _beat(env, h).status_code == 200
    assert _renderer(env, rid)["last_heartbeat_at"] != ""


def test_an_expired_credential_is_refused_with_its_own_error(env):
    rid, h = _remote(env)
    _sql(env, "UPDATE renderers SET credential_expires_at = '2020-01-01T00:00:00Z' WHERE id = ?", (rid,))
    resp = _beat(env, h)
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "credential_expired"}
    # written although the request was refused: the dashboard shows why
    assert _renderer(env, rid)["last_error"] == renderers.CREDENTIAL_EXPIRED_ERROR


def test_a_rotated_credential_keeps_the_old_one_until_the_new_one_is_used(env):
    rid, old = _remote(env)
    _sql(env, "UPDATE renderers SET credential_issued_at = '2020-01-01T00:00:00Z' WHERE id = ?", (rid,))
    reply = _beat(env, old).get_json()
    lost = reply["credential"]
    assert lost and reply["credential_expires_at"]
    # The renderer never received it (say the reply was lost): the old one
    # still works, and the next heartbeat issues a fresh one in its place.
    again = _beat(env, old)
    assert again.status_code == 200
    new = again.get_json()["credential"]
    assert new != lost
    assert _beat(env, bearer(new)).status_code == 200    # first use of the new one ...
    assert _beat(env, old).status_code == 401            # ... retires the old one
    assert _beat(env, bearer(lost)).status_code == 401


def test_a_removed_renderer_never_authenticates(env):
    rid, h = _remote(env)
    _sql(env, "UPDATE renderers SET removed_at = '2026-01-01T00:00:00Z' WHERE id = ?", (rid,))
    assert _beat(env, h).status_code == 401


# ── enrollment ────────────────────────────────────────────────────────────────

def test_enrollment_issues_a_credential_and_is_single_use(env):
    resp, secret = _enroll(env)
    assert resp.status_code == 200
    out = resp.get_json()
    assert set(out) == {"renderer_id", "credential", "credential_expires_at"}
    row = _renderer(env, out["renderer_id"])
    assert row["credential_hash"] == renderers.hash_secret(out["credential"])
    assert row["version"] == VERSION and json.loads(row["compute"]) == {"cpus": 8}
    again = env.client.post("/v1/enroll", json={"secret": secret, "machine_id": "m-2"})
    assert again.status_code == 403 and again.get_json() == {"error": "enrollment_invalid"}


def test_an_unknown_or_expired_enrollment_is_refused_the_same_way(env):
    assert env.client.post("/v1/enroll", json={"secret": "nope"}).get_json() == {"error": "enrollment_invalid"}
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, now="2020-01-01T00:00:00Z")
    con.commit()
    con.close()
    resp = env.client.post("/v1/enroll", json={"secret": secret, "machine_id": "m-1"})
    assert resp.status_code == 403 and resp.get_json() == {"error": "enrollment_invalid"}


def test_reenrolling_the_same_machine_replaces_its_row(env):
    first, _ = _enroll(env, "m-1")
    second, _ = _enroll(env, "m-1")
    assert first.get_json()["renderer_id"] == second.get_json()["renderer_id"]
    assert len(_sql(env, "SELECT id FROM renderers WHERE builtin = 0")) == 1
    assert _beat(env, bearer(first.get_json()["credential"])).status_code == 401
    assert _beat(env, bearer(second.get_json()["credential"])).status_code == 200


# ── heartbeat ─────────────────────────────────────────────────────────────────

def test_heartbeat_reply_shape(env):
    reply = _beat(env, compute={"cpus": 4}).get_json()
    assert reply == {"enabled": True, "needs_upgrade": False, "main_version": VERSION, "probe_now": False,
                     "stop": [], "credential_expires_at": ""}
    assert json.loads(_renderer(env)["compute"]) == {"cpus": 4}


def test_a_version_mismatch_needs_an_upgrade_and_claims_nothing(env):
    _seed(env)
    reply = _beat(env, version="9.9.8").get_json()
    assert reply["needs_upgrade"] is True and reply["main_version"] == VERSION
    resp = env.client.post("/v1/claim", json={}, headers=B)
    assert resp.status_code == 409 and resp.get_json() == {"error": "needs_upgrade"}
    assert _video(env)["status"] == "RENDER_QUEUED"


def test_a_disabled_renderer_is_told_and_claims_nothing(env):
    _seed(env)
    _sql(env, "UPDATE renderers SET enabled = 0 WHERE id = 'builtin'")
    assert _beat(env).get_json()["enabled"] is False
    resp = env.client.post("/v1/claim", json={}, headers=B)
    assert resp.status_code == 409 and resp.get_json() == {"error": "disabled"}


def test_the_probe_is_stored_and_sets_gpu_verified(env):
    _gpu(env, ok=True)
    row = _renderer(env)
    assert row["gpu_verified"] == 1 and json.loads(row["gpu_probe"])["gpu"]["name"] == "GTX 1650"
    _gpu(env, ok=False)
    assert _renderer(env)["gpu_verified"] == 0
    # "ok" must be exactly True
    _beat(env, gpu_probe={"at": "x", "configured": True, "ok": "yes"})
    assert _renderer(env)["gpu_verified"] == 0


def test_probe_now_follows_a_dashboard_request_until_a_newer_probe(env):
    _gpu(env, at="2026-01-01T00:00:00.000000Z")
    _sql(env, "UPDATE renderers SET gpu_probe_requested_at = '2026-01-02T00:00:00.000000Z' WHERE id = 'builtin'")
    assert _beat(env).get_json()["probe_now"] is True
    reply = _gpu(env, at="2026-01-02T00:00:01.000000Z").get_json()
    assert reply["probe_now"] is False
    assert _renderer(env)["gpu_probe_requested_at"] == ""


def test_a_started_heartbeat_requeues_what_the_renderer_held(env):
    _beat(env)
    _seed(env, status="RENDERING", renderer_id="builtin", render_lease_until="2999-01-01T00:00:00Z")
    _seed(env, "vid-2", status="RENDERING", renderer_id="builtin", render_uploaded_at="2026-01-01T00:00:01Z")
    rid, h = _remote(env)
    _seed(env, "vid-3", status="RENDERING", renderer_id=rid)
    _beat(env, started=True)
    v = _video(env)
    assert v["status"] == "RENDER_QUEUED" and v["render_fail_count"] == 1 and v["renderer_id"] == ""
    assert _comments(env) == ["Render interrupted by renderer restart — automatically re-queued."]
    assert _video(env, "vid-2")["status"] == "RENDERING"     # uploaded: the review's
    assert _video(env, "vid-3")["status"] == "RENDERING"     # another renderer's


def test_a_heartbeat_extends_the_lease_of_the_video_it_renders(env):
    _seed(env, status="RENDERING", renderer_id="builtin", render_lease_until="2026-01-01T00:00:00Z")
    _beat(env, state="rendering", video_id="vid-1")
    lease = _video(env)["render_lease_until"]
    assert renderers.age_secs(renderers.now_ts(), lease) > renderers.LEASE_SECS - 60
    # idle, or reporting another video: the lease is left to run out
    _sql(env, "UPDATE videos SET render_lease_until = '2026-01-01T00:00:00Z'")
    _beat(env)
    _beat(env, state="rendering", video_id="vid-9")
    assert _video(env)["render_lease_until"] == "2026-01-01T00:00:00Z"


def test_the_stop_list_names_videos_that_moved_on(env):
    _seed(env, status="RENDERING", renderer_id="builtin")
    assert _beat(env, state="rendering", video_id="vid-1").get_json()["stop"] == []
    # a human moved it; then a lease sweep requeued another the renderer held
    _sql(env, "UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = 'vid-1'")
    _seed(env, "vid-2", status="RENDER_QUEUED", renderer_id="builtin")
    stop = _beat(env, state="rendering", video_id="vid-1").get_json()["stop"]
    assert sorted(stop) == ["vid-1", "vid-2"]
    assert _video(env)["renderer_id"] == "" and _video(env, "vid-2")["renderer_id"] == ""
    # an archived render is stopped too
    _seed(env, "vid-3", status="RENDERING", renderer_id="builtin", archived_at="2026-01-01T00:00:00Z")
    assert _beat(env, state="rendering", video_id="vid-3").get_json()["stop"] == ["vid-3"]


# ── claim ─────────────────────────────────────────────────────────────────────

def test_nothing_queued_is_204(env):
    _beat(env)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204


def test_a_claim_hands_out_the_oldest_video_with_its_settings(env):
    _beat(env)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    _seed(env, "vid-1", frames=123)
    _sql(env, "INSERT INTO settings (key, value) VALUES ('render_timeout_secs', '5000'), "
              "('render_stall_timeout_secs', '60'), ('watermark_enabled', 'false')")
    resp = env.client.post("/v1/claim", json={}, headers=B)
    assert resp.status_code == 200
    assert resp.get_json() == {
        "video_id": "vid-1", "kind": "dom", "needs_gpu": False, "cartoon": False, "mascot": False,
        "total_frames": 123, "lease_secs": renderers.LEASE_SECS,
        "settings": {"render_timeout_secs": 5000, "render_stall_timeout_secs": 60, "watermark": False}}
    v = _video(env)
    assert v["status"] == "RENDERING" and v["renderer_id"] == "builtin"
    assert v["render_lease_until"] > v["render_started_at"] and v["render_uploaded_at"] == ""
    assert _video(env, "vid-2")["status"] == "RENDER_QUEUED"


def test_an_archived_video_is_never_handed_out(env):
    _beat(env)
    _seed(env, archived_at="2026-01-01T00:00:00Z")
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204


def test_a_renderer_that_never_reported_its_version_claims_nothing(env):
    _seed(env)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204


@pytest.mark.parametrize("kind", ["style", "scene_config", "mascot"])
def test_a_gpu_video_is_never_offered_to_a_renderer_without_a_verified_gpu(env, kind):
    _beat(env)
    if kind == "style":
        _seed(env, visual_style="cartoon_3d")
    elif kind == "scene_config":
        # an `auto` video whose written scene-config is a Cartoon 3D world
        _seed(env, scenes=CARTOON_SCENES)
    else:
        _sql(env, "INSERT INTO mascots (id, name, status, approved_version) VALUES ('m1', 'M', 'READY', 1)")
        _sql(env, "INSERT INTO mascot_versions (mascot_id, version, code) VALUES ('m1', 1, 'code')")
        _seed(env, mascot_id="m1", mascot_version=1)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env)["status"] == "RENDER_QUEUED"
    _gpu(env, ok=True)
    reply = env.client.post("/v1/claim", json={}, headers=B).get_json()
    assert reply["video_id"] == "vid-1" and reply["needs_gpu"] is True
    assert reply["cartoon"] is (kind != "mascot") and reply["mascot"] is (kind == "mascot")


def test_the_scheduler_leaves_a_fresh_video_to_a_much_faster_renderer(env):
    _beat(env, compute={"cpus": 1})                    # ~6 s/frame on its prior
    rid, h = _remote(env, gpu=True)                    # 0.25 s/frame on a verified GPU
    _seed(env, updated=renderers.now_ts())
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert env.client.post("/v1/claim", json={}, headers=h).get_json()["video_id"] == "vid-1"
    assert _video(env)["renderer_id"] == rid


def test_the_onboarding_hold_blocks_only_the_builtin_renderer(env):
    _beat(env)
    rid, h = _remote(env)
    _seed(env)
    _sql(env, "INSERT INTO settings (key, value) VALUES (?, '2999-01-01T00:00:00Z')",
         (pipeline.RENDER_CLAIM_HOLD_KEY,))
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert env.client.post("/v1/claim", json={}, headers=h).get_json()["video_id"] == "vid-1"


def test_an_expired_hold_is_ignored(env):
    _beat(env)
    _seed(env)
    _sql(env, "INSERT INTO settings (key, value) VALUES (?, '2020-01-01T00:00:00Z')",
         (pipeline.RENDER_CLAIM_HOLD_KEY,))
    assert env.client.post("/v1/claim", json={}, headers=B).get_json()["video_id"] == "vid-1"


@pytest.mark.parametrize("project", ["..", "a/b"])
def test_an_unusable_project_id_is_refused_and_the_claim_moves_on(env, project):
    _beat(env)
    _seed(env, project=project)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    assert env.client.post("/v1/claim", json={}, headers=B).get_json()["video_id"] == "vid-2"
    assert _video(env)["status"] == "FAILED"
    assert _comments(env)[-1].startswith("Render refused, moved to FAILED:")
    assert "cannot be used as a file path, so nothing was staged or rendered" in _comments(env)[-1]


def test_missing_job_files_go_back_for_revision(env):
    _beat(env)
    _seed(env, files=False)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env)["status"] == "REVISION_REQUESTED"
    assert _comments(env) == [
        "Render failed: missing job file(s): ['voice_file_path', 'timeline_path', 'scene_config_path']"]


def test_an_empty_path_column_still_means_not_written(env):
    _beat(env)
    _seed(env, written="")
    env.client.post("/v1/claim", json={}, headers=B)
    assert _video(env)["status"] == "REVISION_REQUESTED"


def test_a_cartoon_video_holding_a_mascot_is_refused(env):
    from tubematic_core import mascots as tmascots
    _gpu(env)
    _seed(env, visual_style="cartoon_3d", mascot_id="tubi", mascot_version=1)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    v = _video(env)
    assert v["status"] == "FAILED" and v["render_fail_count"] == 0
    assert tmascots.MASCOT_NOT_ON_CARTOON_3D in _comments(env)[-1] and "tubi" in _comments(env)[-1]


@pytest.mark.parametrize("version, code, why", [
    (0, "code", "no version of mascot 'm1' is pinned"),
    (2, None, "has no version 2"),
    (1, "   ", "has no code"),
])
def test_a_mascot_whose_code_cannot_be_staged_is_refused(env, version, code, why):
    _gpu(env)
    _sql(env, "INSERT INTO mascots (id, name, status, approved_version) VALUES ('m1', 'M', 'READY', 1)")
    if code is not None:
        _sql(env, "INSERT INTO mascot_versions (mascot_id, version, code) VALUES ('m1', 1, ?)", (code,))
    _seed(env, mascot_id="m1", mascot_version=version)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env)["status"] == "FAILED"
    assert _comments(env)[-1].startswith("Not rendered, moved to FAILED: this video has a mascot, "
                                         "and its drawing code cannot be staged")
    assert why in _comments(env)[-1]


# ── the lease ─────────────────────────────────────────────────────────────────

def _claimed(env, headers=B, **seed):
    _beat(env, headers)
    _seed(env, **seed)
    reply = env.client.post("/v1/claim", json={}, headers=headers)
    assert reply.status_code == 200, reply.data
    return reply.get_json()


def test_only_the_lease_holder_reaches_the_job(env):
    _claimed(env)
    _rid, h = _remote(env)
    assert env.client.get("/v1/jobs/vid-1/bundle", headers=h).status_code == 403
    assert env.client.put("/v1/jobs/vid-1/output", data=b"mp4", headers=h).status_code == 403
    assert env.client.post("/v1/jobs/vid-1/result", json={"outcome": "success"}, headers=h).status_code == 403
    assert not (env.out / "proj-1" / "vid-1.mp4").exists()
    assert _video(env)["status"] == "RENDERING" and _video(env)["renderer_id"] == "builtin"


def test_a_lost_lease_drops_a_late_result(env):
    _claimed(env)
    _sql(env, "UPDATE videos SET status = 'RENDER_QUEUED', renderer_id = ''")
    assert env.client.get("/v1/jobs/vid-1/bundle", headers=B).status_code == 403
    resp = env.client.post("/v1/jobs/vid-1/result", json={"outcome": "failed", "error": "x"}, headers=B)
    assert resp.status_code == 403
    assert _video(env)["status"] == "RENDER_QUEUED" and _comments(env) == []


# ── bundle ────────────────────────────────────────────────────────────────────

def _members(resp) -> dict:
    out = {}
    with tarfile.open(fileobj=io.BytesIO(resp.data), mode="r|") as tf:
        for m in tf:
            out[m.name] = tf.extractfile(m).read() if m.isfile() else None
    return out


def test_the_bundle_streams_the_jobs_files(env):
    _claimed(env, scenes=[{"type": "generated", "src": "vid-1/Intro"}, {"type": "generated", "src": "Legacy"},
                          {"type": "generated", "src": "Lib", "source": "installed"}])
    job = env.jobs / "vid-1"
    (job / "images" / "sub").mkdir(parents=True)
    (job / "images" / "a.png").write_bytes(b"PNG" * 1000)
    (job / "images" / "sub" / "b.png").write_bytes(b"B")
    outside = env.secrets / "outside"
    outside.write_text("SECRET")
    os.symlink(outside, job / "images" / "planted.png")
    os.symlink(env.secrets, job / "images" / "planted_dir")
    tree = env.generated / "vid-1"
    (tree / "sets").mkdir(parents=True)
    (tree / "Intro.tsx").write_text("intro")
    (tree / "sets" / "street.ts").write_text("street")
    os.symlink(outside, tree / "link.tsx")
    (env.generated / "Legacy.tsx").write_text("legacy")
    (env.generated / "Lib.tsx").write_text("not this one")
    (env.generated / "Unrelated.tsx").write_text("nor this")
    resp = env.client.get("/v1/jobs/vid-1/bundle", headers=B)
    assert resp.status_code == 200 and resp.mimetype == "application/x-tar" and resp.is_streamed
    members = _members(resp)
    assert members == {
        "audio.mp3": b"AUDIO", "timeline.json": (job / "timeline.json").read_bytes(),
        "scene-config.json": (job / "scene-config.json").read_bytes(),
        "images/a.png": b"PNG" * 1000, "images/sub/b.png": b"B",
        "scenes/vid-1/Intro.tsx": b"intro", "scenes/vid-1/sets/street.ts": b"street",
        "scenes/_flat/Legacy.tsx": b"legacy"}
    assert len(resp.data) % tarfile.RECORDSIZE == 0


def test_the_bundle_streams_in_chunks(env, monkeypatch):
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 1000)
    _claimed(env)
    (env.jobs / "vid-1" / "audio.mp3").write_bytes(os.urandom(4500))
    resp = env.client.get("/v1/jobs/vid-1/bundle", headers=B, buffered=False)
    chunks = list(resp.response)
    # never a whole file at once (the last chunk is the end-of-archive padding)
    assert max(len(c) for c in chunks[:-1]) <= 1024
    assert _members(type("R", (), {"data": b"".join(chunks)})())["audio.mp3"] == \
        (env.jobs / "vid-1" / "audio.mp3").read_bytes()


def test_the_mix_is_bundled_only_when_it_is_not_older_than_the_voice(env):
    _claimed(env)
    job = env.jobs / "vid-1"
    mix = job / "cartoon" / "audio" / "mix" / "mix.wav"
    mix.parent.mkdir(parents=True)
    mix.write_bytes(b"MIX")
    (job / "cartoon" / "source.json").write_text('{"fingerprint": "f"}')
    os.utime(mix, (time.time() - 100, time.time() - 100))
    members = _members(env.client.get("/v1/jobs/vid-1/bundle", headers=B))
    assert "cartoon/audio/mix/mix.wav" not in members           # a re-voice made it stale
    assert members["cartoon/source.json"] == b'{"fingerprint": "f"}'
    os.utime(mix, (time.time() + 100, time.time() + 100))
    members = _members(env.client.get("/v1/jobs/vid-1/bundle", headers=B))
    assert members["cartoon/audio/mix/mix.wav"] == b"MIX"


def test_a_mascot_video_bundles_its_pinned_versions_code(env):
    _gpu(env)
    _sql(env, "INSERT INTO mascots (id, name, status, approved_version) VALUES ('m1', 'M', 'READY', 2)")
    _sql(env, "INSERT INTO mascot_versions (mascot_id, version, code) VALUES ('m1', 1, 'v1 code'), ('m1', 2, 'v2')")
    _claimed(env, mascot_id="m1", mascot_version=1)
    assert _members(env.client.get("/v1/jobs/vid-1/bundle", headers=B))["mascot.js"] == b"v1 code"


def test_a_video_without_a_mascot_gets_no_mascot_code(env):
    _claimed(env)
    assert "mascot.js" not in _members(env.client.get("/v1/jobs/vid-1/bundle", headers=B))


def test_a_bundle_whose_files_vanished_is_refused(env):
    _claimed(env)
    (env.jobs / "vid-1" / "audio.mp3").unlink()
    resp = env.client.get("/v1/jobs/vid-1/bundle", headers=B)
    assert resp.status_code == 409 and resp.get_json()["error"] == "bundle_unavailable"


# ── output upload ─────────────────────────────────────────────────────────────

def test_the_output_is_streamed_into_place(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 7)
    data = os.urandom(100)
    resp = env.client.put("/v1/jobs/vid-1/output", data=io.BytesIO(data), headers=B)
    assert resp.status_code == 200 and resp.get_json() == {"bytes": 100}
    out = env.out / "proj-1" / "vid-1.mp4"
    assert out.read_bytes() == data
    assert sorted(p.name for p in out.parent.iterdir()) == ["vid-1.mp4"]     # no temp left behind


def test_the_upload_never_reads_the_whole_body_into_memory(env, monkeypatch):
    import flask
    _claimed(env)
    monkeypatch.setattr(flask.Request, "get_data", lambda *a, **k: pytest.fail("read whole"))
    assert env.client.put("/v1/jobs/vid-1/output", data=b"x" * 10, headers=B).status_code == 200


# ── result ────────────────────────────────────────────────────────────────────

def _upload(env, headers=B, data=b"MP4DATA"):
    assert env.client.put("/v1/jobs/vid-1/output", data=data, headers=headers).status_code == 200


def _result(env, headers=B, **body):
    return env.client.post("/v1/jobs/vid-1/result", json=body, headers=headers)


def test_a_success_marks_the_render_uploaded_for_the_review(env):
    _claimed(env)
    _upload(env)
    assert _result(env, outcome="success", on_gpu=False, frames=90, seconds=45.0).get_json() == {}
    v = _video(env)
    assert v["status"] == "RENDERING"                # the worker's review thread finishes it
    assert v["render_uploaded_at"] and v["video_path"] == str(env.out / "proj-1" / "vid-1.mp4")
    assert v["renderer_id"] == "" and v["render_lease_until"] == ""
    [t] = _sql(env, "SELECT renderer_id, kind, on_gpu, frames, seconds FROM render_timings")
    assert t == {"renderer_id": "builtin", "kind": "dom", "on_gpu": 0, "frames": 90, "seconds": 45.0}


def test_a_success_with_no_output_is_an_error(env):
    _claimed(env)
    _result(env, outcome="success", frames=90, seconds=1.0)
    v = _video(env)
    assert v["status"] == "RENDER_QUEUED" and v["render_fail_count"] == 1 and v["renderer_id"] == ""
    assert "output missing" in _comments(env)[-1]
    assert _sql(env, "SELECT * FROM render_timings") == []


@pytest.mark.parametrize("outcome, status", [
    ("failed", "REVISION_REQUESTED"), ("stalled", "RENDER_QUEUED"),
    ("timeout", "RENDER_QUEUED"), ("error", "RENDER_QUEUED"),
])
def test_each_failure_outcome_routes_as_before(env, outcome, status):
    _claimed(env)
    _result(env, outcome=outcome, error="Render stalled: no progress for 600s", on_gpu=False, gpu_ok=None)
    v = _video(env)
    assert v["status"] == status and v["render_fail_count"] == 1
    assert v["renderer_id"] == "" and v["render_lease_until"] == ""
    assert _comments(env) == ["Render failed: Render stalled: no progress for 600s"]


def test_a_failure_past_the_retry_cap_fails(env):
    _claimed(env, render_fail_count=1)
    _result(env, outcome="stalled", error="Render stalled")
    assert _video(env)["status"] == "FAILED"
    assert "giving up" in _comments(env)[-1]


def test_a_gpu_render_whose_gpu_failed_its_retest_fails_the_video(env):
    _gpu(env)
    _claimed(env, visual_style="cartoon_3d")
    _result(env, outcome="failed", error="WebGL context lost", on_gpu=True, gpu_ok=False,
            gpu_probe={"at": "2026-01-03T00:00:00.000000Z", "configured": True, "ok": False,
                       "error": "Chromium is rendering on another device: SwiftShader"})
    v = _video(env)
    assert v["status"] == "FAILED" and v["render_fail_count"] == 0
    [comment] = _comments(env)
    assert comment.startswith("Render failed, moved to FAILED: this video is Cartoon 3D, which renders on the GPU only")
    assert "SwiftShader" in comment and comment.endswith("The render's error: WebGL context lost")
    assert _renderer(env)["gpu_verified"] == 0       # no more GPU work for it until a probe passes


def test_a_gpu_render_whose_gpu_still_works_is_the_videos_own_failure(env):
    _gpu(env)
    _claimed(env, visual_style="cartoon_3d")
    _result(env, outcome="failed", error="TypeError in scene", on_gpu=True, gpu_ok=True)
    v = _video(env)
    assert v["status"] == "REVISION_REQUESTED" and v["render_fail_count"] == 1
    assert _renderer(env)["gpu_verified"] == 1


def test_a_bad_outcome_is_refused(env):
    _claimed(env)
    assert _result(env, outcome="done").status_code == 400
    assert _video(env)["status"] == "RENDERING"


# ── the whole path, twice, by the scheduler ───────────────────────────────────

def test_a_remote_renderer_claims_renders_and_uploads(env):
    rid, h = _remote(env)
    _seed(env)
    reply = env.client.post("/v1/claim", json={}, headers=h).get_json()
    assert reply["video_id"] == "vid-1"
    assert env.client.get("/v1/jobs/vid-1/bundle", headers=h).status_code == 200
    _upload(env, h)
    assert _result(env, h, outcome="success", frames=90, seconds=9.0).status_code == 200
    assert _video(env)["render_uploaded_at"]
    assert _sql(env, "SELECT renderer_id FROM render_timings")[0]["renderer_id"] == rid


# ── real TLS ──────────────────────────────────────────────────────────────────

def test_the_gateway_serves_tls_with_the_pinned_certificate(env, tmp_path):
    tls = tmp_path / "tls"
    other = tmp_path / "other"
    tauth.ensure_secrets(tls)
    tauth.ensure_secrets(other)
    server = render_gateway.make_gateway_server(env.app, "127.0.0.1", 0, secrets_dir=tls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"https://127.0.0.1:{server.server_port}/v1/version"

        def context(cert_dir):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(cadata=tauth.read_secret(tauth.TLS_CERT_NAME, cert_dir))
            return ctx
        with urllib.request.urlopen(url, context=context(tls), timeout=10) as resp:
            assert json.loads(resp.read()) == {"version": VERSION, "gateway": 1}
        # the pin a token would carry is this certificate's
        pem = ssl.get_server_certificate(("127.0.0.1", server.server_port))
        assert renderers.cert_pin(ssl.PEM_cert_to_DER_cert(pem)) == tauth.gateway_pin(tls)
        with pytest.raises(urllib.error.URLError) as err:
            urllib.request.urlopen(url, context=context(other), timeout=10)
        assert isinstance(err.value.reason, ssl.SSLError)
    finally:
        server.shutdown()
        thread.join(5)


def test_no_tls_pair_means_no_gateway_server(env, tmp_path, caplog):
    assert render_gateway.make_gateway_server(env.app, "127.0.0.1", 0, secrets_dir=tmp_path / "empty") is None
    assert "render gateway not started" in caplog.text


# ── server.py starts it ───────────────────────────────────────────────────────

@pytest.fixture
def api_server(tmp_path, monkeypatch):
    """server.py imported against a temporary database and secrets
    directory. Importing it starts nothing; start_render_gateway does."""
    import importlib
    import sys
    secrets = tmp_path / "api-secrets"
    tauth.ensure_secrets(secrets)
    db_path = tmp_path / "api.db"
    for k, v in {"TUBEMATIC_DB": str(db_path), "TUBEMATIC_SECRETS_DIR": str(secrets),
                 "TUBEMATIC_JOBS_DIR": str(tmp_path / "jobs"), "OUTPUT_BASE_PATH": str(tmp_path / "out"),
                 "TUBEMATIC_GATEWAY_PORT": "0"}.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    yield server, db_path, secrets
    sys.modules.pop("server", None)


def test_the_api_starts_the_gateway_and_restores_the_builtin_row(api_server):
    server, db_path, _ = api_server
    con = sqlite3.connect(db_path)
    con.execute("DELETE FROM renderers")
    con.commit()
    con.close()
    gateway = server.start_render_gateway()
    try:
        assert gateway is not None
        con = sqlite3.connect(db_path)
        assert con.execute("SELECT builtin, enabled FROM renderers WHERE id = 'builtin'").fetchone() == (1, 1)
        con.close()
    finally:
        gateway.shutdown()


def test_the_api_runs_without_the_gateway_when_its_tls_pair_is_missing(api_server, caplog):
    server, _, secrets = api_server
    (secrets / tauth.TLS_CERT_NAME).unlink()
    assert server.start_render_gateway() is None
    assert "render gateway not started" in caplog.text
    ran = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server.app, "run", lambda **kw: ran.append(kw))
        server.main()
    assert ran and ran[0]["port"] == 4000        # the dashboard's API still serves
