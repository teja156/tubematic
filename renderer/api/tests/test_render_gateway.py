"""The render gateway, render_gateway.py: the only API a renderer calls.

Who may call (the built-in renderer's token read per request, an enrolled
remote credential with expiry and rotation, never the API's own token), which
video a claim hands out (the scheduler's pick, GPU videos only to a renderer
whose GPU passed its probe, the pre-render refusals), the lease that keeps a
lost renderer from touching a video another one took over (a heartbeat
included: it extends and stops by claim, not by video), the bundle and the
upload, how each result moves the video, and the bounds on what a renderer
can make the gateway hold (the JSON body limit on every JSON route, the open
enroll route included; one upload per claim, a global upload cap and a free
space floor), and for how long (authentication before any body is read, the
idle, head, JSON-body and drain deadlines, the enrollment-reader and
per-renderer caps, a stalled upload releasing its slot), the process-wide
connection cap (refused before a thread is made), a renderer's request
counted until its response is closed (after a streamed bundle and a drain),
the upload temporary directory (cleared at start, swept by age, never
followed), and an unusable TLS pair leaving the API up without a gateway.

Driven through Flask's test client against a migrated temporary database; the
time bounds and one TLS test serve the app over real TLS on 127.0.0.1 and talk
to it over raw sockets.

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


def J(env, headers=B, claim=None):
    """`headers` plus the X-Render-Claim of the claim a job route acts for
    (by default the last one _claimed made)."""
    return {**headers, "X-Render-Claim": claim if claim is not None else env.claim}


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


def test_a_heartbeat_extends_the_lease_of_the_claim_it_renders(env):
    _seed(env, status="RENDERING", renderer_id="builtin", render_claim_id="c-1",
          render_lease_until="2026-01-01T00:00:00Z")
    _beat(env, state="rendering", video_id="vid-1", claim_id="c-1")
    lease = _video(env)["render_lease_until"]
    assert renderers.age_secs(renderers.now_ts(), lease) > renderers.LEASE_SECS - 60
    # idle, another video, another claim of this video, or no claim at all:
    # the lease is left to run out
    _sql(env, "UPDATE videos SET render_lease_until = '2026-01-01T00:00:00Z'")
    _beat(env)
    _beat(env, state="rendering", video_id="vid-9", claim_id="c-1")
    _beat(env, state="rendering", video_id="vid-1", claim_id="c-0")
    _beat(env, state="rendering", video_id="vid-1")
    assert _video(env)["render_lease_until"] == "2026-01-01T00:00:00Z"


def test_the_stop_list_names_claims_that_moved_on(env):
    _seed(env, status="RENDERING", renderer_id="builtin", render_claim_id="c-1")
    assert _beat(env, state="rendering", video_id="vid-1", claim_id="c-1").get_json()["stop"] == []
    # a human moved it; then a lease sweep requeued another the renderer held
    _sql(env, "UPDATE videos SET status = 'REVISION_REQUESTED' WHERE id = 'vid-1'")
    _seed(env, "vid-2", status="RENDER_QUEUED", renderer_id="builtin", render_claim_id="c-2")
    stop = _beat(env, state="rendering", video_id="vid-1", claim_id="c-1").get_json()["stop"]
    assert sorted(stop, key=lambda e: e["video_id"]) == [{"video_id": "vid-1", "claim_id": "c-1"},
                                                         {"video_id": "vid-2", "claim_id": "c-2"}]
    assert _video(env)["renderer_id"] == "" and _video(env, "vid-2")["renderer_id"] == ""
    # an archived render is stopped too
    _seed(env, "vid-3", status="RENDERING", renderer_id="builtin", render_claim_id="c-3",
          archived_at="2026-01-01T00:00:00Z")
    assert _beat(env, state="rendering", video_id="vid-3", claim_id="c-3").get_json()["stop"] == [
        {"video_id": "vid-3", "claim_id": "c-3"}]


def test_a_heartbeat_for_an_earlier_claim_never_touches_the_newer_one(env):
    """Claim A's heartbeat is delayed; meanwhile A is re-queued and the same
    renderer claims the video again as claim B. When A's heartbeat arrives it
    neither extends B's lease nor fails to say A is over — and the stop it
    returns names claim A, which the renderer applies to A only."""
    a = _claimed(env)["claim_id"]
    assert render_results.requeue_interrupted("vid-1", "Render lost — automatically re-queued.",
                                              renderer_id="builtin")
    b = env.client.post("/v1/claim", json={}, headers=B).get_json()["claim_id"]
    assert b != a
    _sql(env, "UPDATE videos SET render_lease_until = '2026-01-01T00:00:00Z'")
    reply = _beat(env, state="rendering", video_id="vid-1", claim_id=a).get_json()
    assert reply["stop"] == [{"video_id": "vid-1", "claim_id": a}]
    v = _video(env)
    assert v["render_lease_until"] == "2026-01-01T00:00:00Z"         # B's lease not extended by A
    assert v["status"] == "RENDERING" and v["render_claim_id"] == b
    # B's own heartbeat extends it and stops nothing
    assert _beat(env, state="rendering", video_id="vid-1", claim_id=b).get_json()["stop"] == []
    assert _video(env)["render_lease_until"] > "2026-01-02"


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
    claim_id = resp.get_json()["claim_id"]
    assert len(claim_id) == 32
    assert resp.get_json() == {
        "video_id": "vid-1", "claim_id": claim_id, "kind": "dom", "needs_gpu": False, "cartoon": False, "mascot": False,
        "total_frames": 123, "lease_secs": renderers.LEASE_SECS,
        "settings": {"render_timeout_secs": 5000, "render_stall_timeout_secs": 60, "watermark": False}}
    v = _video(env)
    assert v["status"] == "RENDERING" and v["renderer_id"] == "builtin" and v["render_claim_id"] == claim_id
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


def test_a_video_not_yet_queued_is_never_handed_out(env):
    """VOICE_READY means the agent is still authoring scene config — not a
    renderer's to touch until submit_render advances it to RENDER_QUEUED."""
    _beat(env)
    _seed(env, status="VOICE_READY")
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env)["status"] == "VOICE_READY"


# ── TMDEV-162: every location is derived from the ids (moved from the renderer) ──

def test_a_tampered_row_bundles_the_derived_files_not_the_planted_ones(env):
    """A row whose path columns were pointed elsewhere before the fix (PATCH
    and update_video once accepted any string) still gets the video's own
    files; a legacy host-shaped path renders from the derived location too."""
    planted = env.secrets / "planted.json"
    planted.write_text('{"secret": true}')
    _claimed(env, written=str(planted))
    members = _members(env.client.get("/v1/jobs/vid-1/bundle", headers=J(env)))
    assert members["audio.mp3"] == b"AUDIO" and b"secret" not in members["timeline.json"]


@pytest.mark.parametrize("project", ["node.js", "x" * 129])
def test_a_legacy_project_id_still_renders(env, project):
    """A dot, or more than the creation cap of 128: legacy ids are checked as
    path components at use, as ids.py promises."""
    _claimed(env, project=project)
    _upload(env)
    _result(env, outcome="success", frames=90, seconds=1.0)
    assert _video(env)["video_path"] == str(env.out / project / "vid-1.mp4")


@pytest.mark.parametrize("vid", ["..", "../x", "/tmp/x", "a/b", "x" * 256, "x" * 252])
def test_an_unusable_video_id_is_refused_before_anything_is_bundled(env, vid):
    """252 bytes is a working job directory but an impossible `<id>.mp4`: refused
    up front, not with ENAMETOOLONG after a render."""
    _beat(env)
    _seed(env, vid, files=False)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env, vid)["status"] == "FAILED"
    assert _comments(env, vid)[-1].startswith("Render refused, moved to FAILED:")


def test_a_video_id_that_leaves_room_for_its_mp4_is_handed_out(env):
    vid = "x" * 251
    _beat(env)
    _seed(env, vid)
    assert env.client.post("/v1/claim", json={}, headers=B).get_json()["video_id"] == vid


def test_a_job_dir_linked_to_another_video_is_refused(env):
    """vid-1 -> vid-2 stays inside the jobs root, so only the per-component
    symlink walk stops vid-1 rendering with vid-2's audio."""
    _beat(env)
    _seed(env, "vid-2", status="VOICE_READY")
    _seed(env, files=False)
    (env.jobs / "vid-1").symlink_to(env.jobs / "vid-2")
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env)["status"] == "FAILED" and "symlink" in _comments(env)[-1]


def test_a_symlinked_job_file_is_refused(env):
    _beat(env)
    _seed(env)
    secret = env.secrets / "secret.json"
    secret.write_text("{}")
    (env.jobs / "vid-1" / "timeline.json").unlink()
    (env.jobs / "vid-1" / "timeline.json").symlink_to(secret)
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env)["status"] == "FAILED"


# ── the lease ─────────────────────────────────────────────────────────────────

def _claimed(env, headers=B, **seed):
    _beat(env, headers)
    _seed(env, **seed)
    reply = env.client.post("/v1/claim", json={}, headers=headers)
    assert reply.status_code == 200, reply.data
    env.claim = reply.get_json()["claim_id"]
    return reply.get_json()


def test_only_the_lease_holder_reaches_the_job(env):
    _claimed(env)
    _rid, h = _remote(env)
    assert env.client.get("/v1/jobs/vid-1/bundle", headers=J(env, h)).status_code == 403
    assert env.client.put("/v1/jobs/vid-1/output", data=b"mp4", headers=J(env, h)).status_code == 403
    assert env.client.post("/v1/jobs/vid-1/result", json={"outcome": "success"}, headers=J(env, h)).status_code == 403
    assert not (env.out / "proj-1" / "vid-1.mp4").exists()
    assert _video(env)["status"] == "RENDERING" and _video(env)["renderer_id"] == "builtin"


def test_a_job_route_without_the_claim_id_is_refused(env):
    """The lease holder's credential alone is not enough: the request must
    name the claim (X-Render-Claim), and only the current one."""
    _claimed(env)
    for claim in ("", "0" * 32):
        h = J(env, claim=claim) if claim else B
        assert env.client.get("/v1/jobs/vid-1/bundle", headers=h).status_code == 403
        assert env.client.put("/v1/jobs/vid-1/output", data=b"mp4", headers=h).status_code == 403
        assert env.client.post("/v1/jobs/vid-1/result", json={"outcome": "failed"}, headers=h).status_code == 403
    assert not (env.out / "proj-1" / "vid-1.mp4").exists()
    assert _video(env)["status"] == "RENDERING" and _comments(env) == []


def test_a_lost_lease_drops_a_late_result(env):
    _claimed(env)
    _sql(env, "UPDATE videos SET status = 'RENDER_QUEUED', renderer_id = ''")
    assert env.client.get("/v1/jobs/vid-1/bundle", headers=J(env)).status_code == 403
    resp = env.client.post("/v1/jobs/vid-1/result", json={"outcome": "failed", "error": "x"}, headers=J(env))
    assert resp.status_code == 403
    assert _video(env)["status"] == "RENDER_QUEUED" and _comments(env) == []


# ── one claim, one render ─────────────────────────────────────────────────────

def test_a_lost_claim_reply_is_answered_again_with_the_same_claim(env):
    """The claim committed but its reply never arrived: the renderer's retry
    gets the same video and the same claim id, never a second video."""
    first = _claimed(env)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    again = env.client.post("/v1/claim", json={}, headers=B)
    assert again.status_code == 200 and again.get_json() == first
    assert _video(env, "vid-2")["status"] == "RENDER_QUEUED"
    assert _video(env)["render_claim_id"] == first["claim_id"]


def test_a_renderer_holding_a_claim_cannot_get_another(env, monkeypatch):
    """Two claims from one renderer racing: the second already looked and saw
    no claim of its own, then the first took vid-1. The NOT EXISTS in the
    claim's own UPDATE refuses it vid-2; its next pass answers vid-1's claim."""
    _beat(env)
    _seed(env)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    real_pick = renderers.pick_video
    inner = {}

    def racing_pick(*args):
        if not inner:
            inner["racing"] = True
            inner["reply"] = env.client.post("/v1/claim", json={}, headers=B).get_json()
            return "vid-2"
        return real_pick(*args)
    monkeypatch.setattr(renderers, "pick_video", racing_pick)
    outer = env.client.post("/v1/claim", json={}, headers=B).get_json()
    assert inner["reply"]["video_id"] == "vid-1"
    assert outer == inner["reply"]
    assert _video(env, "vid-2")["status"] == "RENDER_QUEUED" and _video(env, "vid-2")["renderer_id"] == ""


def test_an_archived_claim_holds_the_renderer_until_its_lease_runs_out(env):
    _claimed(env)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    _sql(env, "UPDATE videos SET archived_at = '2026-01-03T00:00:00Z' WHERE id = 'vid-1'")
    assert env.client.post("/v1/claim", json={}, headers=B).status_code == 204
    assert _video(env, "vid-2")["status"] == "RENDER_QUEUED"


def test_a_stale_failure_result_never_touches_the_claim_that_took_over(env, monkeypatch):
    """The result is authorized; then, before it is routed, the lease runs
    out, the worker re-queues the video and the same renderer claims it again.
    The stale result must change nothing: no retry counted, no comment, no
    status — the new claim is left exactly as it was."""
    first = _claimed(env)
    real_guard = render_results._claim_guard
    second = {}

    def reclaim_first(claim):
        if not second:
            second["n"] = 1
            assert render_results.requeue_interrupted("vid-1", "Render lost — automatically re-queued.",
                                                      renderer_id="builtin")
            second.update(env.client.post("/v1/claim", json={}, headers=B).get_json())
        return real_guard(claim)
    monkeypatch.setattr(render_results, "_claim_guard", reclaim_first)
    assert _result(env, outcome="failed", error="late crash").status_code == 200
    assert second["video_id"] == "vid-1" and second["claim_id"] != first["claim_id"]
    v = _video(env)
    assert v["status"] == "RENDERING" and v["renderer_id"] == "builtin"
    assert v["render_claim_id"] == second["claim_id"] and v["render_fail_count"] == 1    # the re-queue's only
    assert _comments(env) == ["Render lost — automatically re-queued."]


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
    resp = env.client.get("/v1/jobs/vid-1/bundle", headers=J(env))
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
    resp = env.client.get("/v1/jobs/vid-1/bundle", headers=J(env), buffered=False)
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
    members = _members(env.client.get("/v1/jobs/vid-1/bundle", headers=J(env)))
    assert "cartoon/audio/mix/mix.wav" not in members           # a re-voice made it stale
    assert members["cartoon/source.json"] == b'{"fingerprint": "f"}'
    os.utime(mix, (time.time() + 100, time.time() + 100))
    members = _members(env.client.get("/v1/jobs/vid-1/bundle", headers=J(env)))
    assert members["cartoon/audio/mix/mix.wav"] == b"MIX"


def test_a_mascot_video_bundles_its_pinned_versions_code(env):
    _gpu(env)
    _sql(env, "INSERT INTO mascots (id, name, status, approved_version) VALUES ('m1', 'M', 'READY', 2)")
    _sql(env, "INSERT INTO mascot_versions (mascot_id, version, code) VALUES ('m1', 1, 'v1 code'), ('m1', 2, 'v2')")
    _claimed(env, mascot_id="m1", mascot_version=1)
    assert _members(env.client.get("/v1/jobs/vid-1/bundle", headers=J(env)))["mascot.js"] == b"v1 code"


def test_a_video_without_a_mascot_gets_no_mascot_code(env):
    _claimed(env)
    assert "mascot.js" not in _members(env.client.get("/v1/jobs/vid-1/bundle", headers=J(env)))


def test_a_bundle_whose_files_vanished_is_refused(env):
    _claimed(env)
    (env.jobs / "vid-1" / "audio.mp3").unlink()
    resp = env.client.get("/v1/jobs/vid-1/bundle", headers=J(env))
    assert resp.status_code == 409 and resp.get_json()["error"] == "bundle_unavailable"


# ── output upload ─────────────────────────────────────────────────────────────

def test_the_output_is_streamed_into_place(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 7)
    data = os.urandom(100)
    resp = env.client.put("/v1/jobs/vid-1/output", data=io.BytesIO(data), headers=J(env))
    assert resp.status_code == 200 and resp.get_json() == {"bytes": 100}
    out = env.out / "proj-1" / "vid-1.mp4"
    assert out.read_bytes() == data
    assert sorted(p.name for p in out.parent.iterdir()) == ["vid-1.mp4"]
    assert _temps(env) == []                                                  # no temp left behind


def test_the_upload_never_reads_the_whole_body_into_memory(env, monkeypatch):
    import flask
    _claimed(env)
    monkeypatch.setattr(flask.Request, "get_data", lambda *a, **k: pytest.fail("read whole"))
    assert env.client.put("/v1/jobs/vid-1/output", data=b"x" * 10, headers=J(env)).status_code == 200


def _raw_put(env, stream, headers, length=None, path="/v1/jobs/vid-1/output", method="PUT"):
    """A request whose body is `stream`, read as the server reads it: with a
    Content-Length, or (length None) as a chunked body that ends at EOF."""
    from werkzeug.test import EnvironBuilder
    b = EnvironBuilder(path=path, method=method, headers=headers)
    environ = b.get_environ()
    b.close()
    environ["wsgi.input"] = stream
    if length is None:
        environ.pop("CONTENT_LENGTH", None)
        environ["wsgi.input_terminated"] = True
    else:
        environ["CONTENT_LENGTH"] = str(length)
    from werkzeug.wrappers import Response as WResponse
    resp = WResponse.from_app(env.app, environ)
    resp.get_json = lambda: json.loads(resp.get_data())
    return resp


class _Body(io.RawIOBase):
    """An upload body of `total` bytes handed out in `chunk`-sized reads,
    calling `on_read(n)` before the n-th read (1-based)."""

    def __init__(self, total, chunk=4, fill=b"A", on_read=None):
        self.left, self.chunk, self.fill, self.on_read, self.reads = total, chunk, fill, on_read, 0

    def readable(self):
        return True

    def readinto(self, b):
        self.reads += 1
        if self.on_read is not None:
            self.on_read(self.reads)
        take = min(self.left, self.chunk, len(b))
        b[:take] = self.fill * take
        self.left -= take
        return take


def _upload_dir(env):
    d = env.out / "proj-1"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def _temps(env):
    """The gateway's upload temp directory, which is never beside a video."""
    d = env.out / render_gateway.UPLOAD_TMP_DIR
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_an_upload_over_the_declared_limit_is_refused_before_reading(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_OUTPUT_BYTES", 10)

    def never(n):
        pytest.fail("the body of an over-limit upload was read")
    resp = _raw_put(env, _Body(11, on_read=never), J(env), length=11)
    assert resp.status_code == 413
    assert resp.get_json() == {"error": "output_too_large", "limit": 10}
    assert _upload_dir(env) == []


def test_a_chunked_upload_over_the_limit_is_aborted_and_its_temp_file_removed(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_OUTPUT_BYTES", 10)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 4)
    seen = []
    body = _Body(1 << 20, chunk=4, on_read=lambda n: seen.append(_temps(env)))
    resp = _raw_put(env, body, J(env))
    assert resp.status_code == 413 and resp.get_json()["error"] == "output_too_large"
    assert any(name.endswith(".upload") for name in seen[-1])     # it was being written ...
    assert _temps(env) == [] and _upload_dir(env) == []            # ... and is gone
    assert body.reads <= 4                                         # stopped at the limit, not at EOF


def test_a_chunked_upload_under_the_limit_lands(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_OUTPUT_BYTES", 10)
    resp = _raw_put(env, _Body(10, fill=b"Z"), J(env))
    assert resp.status_code == 200 and resp.get_json() == {"bytes": 10}
    assert (env.out / "proj-1" / "vid-1.mp4").read_bytes() == b"Z" * 10


def test_a_stale_upload_never_replaces_the_new_claims_output(env):
    """Renderer A's upload is slow; meanwhile its lease runs out, the video is
    re-queued, renderer B claims it and uploads its own render. When A's body
    finally ends, A is told its claim was lost and B's file is left intact."""
    _claimed(env)
    a_claim = env.claim
    rid, h = _remote(env)
    took_over = {}

    def take_over(n):
        if n == 1:
            assert render_results.requeue_interrupted("vid-1", "Render lost — automatically re-queued.",
                                                      renderer_id="builtin")
            reply = env.client.post("/v1/claim", json={}, headers=h).get_json()
            took_over["claim"] = reply["claim_id"]
            assert env.client.put("/v1/jobs/vid-1/output", data=b"B-OUTPUT",
                                  headers=J(env, h, reply["claim_id"])).status_code == 200
    resp = _raw_put(env, _Body(8, fill=b"A", on_read=take_over), J(env, B, a_claim), length=8)
    assert resp.status_code == 409 and resp.get_json() == {"error": "claim_lost"}
    assert (env.out / "proj-1" / "vid-1.mp4").read_bytes() == b"B-OUTPUT"
    assert _upload_dir(env) == ["vid-1.mp4"] and _temps(env) == []  # A's temp file is gone
    v = _video(env)
    assert v["renderer_id"] == rid and v["render_claim_id"] == took_over["claim"]


def test_a_second_upload_for_the_same_claim_is_refused_while_the_first_streams(env, monkeypatch):
    """A renderer whose first PUT timed out on its side retries while the
    gateway is still receiving the first: the retry is refused before its
    body is read or a temp file made, and the first one lands."""
    _claimed(env)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 4)
    seen = {}

    def second(n):
        if n == 2:
            seen["temps"] = _temps(env)
            body = _Body(8, on_read=lambda _n: pytest.fail("the second upload's body was read"))
            r = _raw_put(env, body, J(env), length=8)
            seen["status"], seen["json"] = r.status_code, r.get_json()
            seen["temps_after"] = _temps(env)
    resp = _raw_put(env, _Body(12, fill=b"F", on_read=second), J(env), length=12)
    assert seen["status"] == 409 and seen["json"] == {"error": "upload_in_progress"}
    assert len(seen["temps"]) == 1 and seen["temps_after"] == seen["temps"]     # no second temp file
    assert resp.status_code == 200 and (env.out / "proj-1" / "vid-1.mp4").read_bytes() == b"F" * 12
    # the claim's slot is released once the first is done, however it ended
    assert env.client.put("/v1/jobs/vid-1/output", data=b"AGAIN", headers=J(env)).status_code == 200
    monkeypatch.setattr(render_gateway, "MAX_OUTPUT_BYTES", 1)
    assert env.client.put("/v1/jobs/vid-1/output", data=b"TOO BIG", headers=J(env)).status_code == 413
    monkeypatch.setattr(render_gateway, "MAX_OUTPUT_BYTES", 100)
    assert env.client.put("/v1/jobs/vid-1/output", data=b"OK", headers=J(env)).status_code == 200


def test_uploads_across_claims_are_capped(env, monkeypatch):
    _claimed(env)
    a_claim = env.claim
    _rid, h = _remote(env)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    b = env.client.post("/v1/claim", json={}, headers=h).get_json()
    assert b["video_id"] == "vid-2"
    monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 1)
    seen = {}

    def other(n):
        if n == 1:
            r = env.client.put("/v1/jobs/vid-2/output", data=b"B", headers=J(env, h, b["claim_id"]))
            seen["status"], seen["json"] = r.status_code, r.get_json()
            seen["retry_after"] = r.headers.get("Retry-After")
            seen["temps"] = _temps(env)
    resp = _raw_put(env, _Body(4, on_read=other), J(env, B, a_claim), length=4)
    assert resp.status_code == 200
    assert seen["status"] == 503 and seen["json"] == {"error": "busy"} and seen["retry_after"]
    assert len(seen["temps"]) == 1                                            # only the first one's temp file
    assert env.client.put("/v1/jobs/vid-2/output", data=b"B", headers=J(env, h, b["claim_id"])).status_code == 200


def _free(monkeypatch, frees):
    """shutil.disk_usage answering each free figure in turn (the last one
    from then on)."""
    import collections
    import shutil
    usage = collections.namedtuple("usage", "total used free")
    calls = []

    def disk_usage(path):
        calls.append(path)
        return usage(10 << 40, 0, frees[min(len(calls), len(frees)) - 1])
    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    return calls


def test_an_upload_that_would_leave_too_little_free_space_is_refused(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MIN_FREE_BYTES", 1000)
    _free(monkeypatch, [1050])

    def never(n):
        pytest.fail("the body of a refused upload was read")
    resp = _raw_put(env, _Body(100, on_read=never), J(env), length=100)      # 1050 - 100 < 1000
    assert resp.status_code == 507 and resp.get_json()["error"] == "insufficient_storage"
    assert _upload_dir(env) == []
    resp = _raw_put(env, _Body(40, fill=b"S"), J(env), length=40)            # 1050 - 40 >= 1000
    assert resp.status_code == 200


def test_a_chunked_upload_is_stopped_when_free_space_runs_low(env, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MIN_FREE_BYTES", 1000)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 4)
    monkeypatch.setattr(render_gateway, "DISK_CHECK_BYTES", 8)
    calls = _free(monkeypatch, [5000, 5000, 900])
    seen = []
    body = _Body(1 << 20, chunk=4, on_read=lambda n: seen.append(_temps(env)))
    resp = _raw_put(env, body, J(env))
    assert resp.status_code == 507 and resp.get_json()["error"] == "insufficient_storage"
    assert len(calls) == 3                                         # before, at 8 bytes, at 16 bytes
    assert any(name.endswith(".upload") for name in seen[-1])      # it was being written ...
    assert _temps(env) == [] and _upload_dir(env) == []            # ... and is gone
    assert body.reads <= 5


# ── JSON bodies ───────────────────────────────────────────────────────────────

def _enrollment_rows(env):
    return _sql(env, "SELECT secret_hash, used_at, renderer_id FROM renderer_enrollments")


@pytest.mark.parametrize("chunked", [False, True])
def test_an_oversized_enrollment_is_refused_before_it_is_read_or_used(env, monkeypatch, chunked):
    """The enroll route is open: an unauthenticated body is bounded too, and
    an oversized one never reaches the enrollment, even with a valid secret."""
    monkeypatch.setattr(render_gateway, "MAX_JSON_BYTES", 1024)
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, "")
    con.commit()
    con.close()
    before, renderers_before = _enrollment_rows(env), _sql(env, "SELECT id FROM renderers")
    payload = json.dumps({"secret": secret, "machine_id": "m-1", "version": VERSION,
                          "pad": "x" * 100_000}).encode()
    reads = []

    class Stream(io.RawIOBase):
        def __init__(self):
            self.data = io.BytesIO(payload)

        def readable(self):
            return True

        def readinto(self, b):
            n = self.data.readinto(b)
            reads.append(n)
            return n
    resp = _raw_put(env, Stream(), {"Content-Type": "application/json"},
                    length=None if chunked else len(payload), path="/v1/enroll", method="POST")
    assert resp.status_code == 413 and resp.get_json() == {"error": "body_too_large", "limit": 1024}
    assert _enrollment_rows(env) == before and before[0]["used_at"] is None
    assert _sql(env, "SELECT id FROM renderers") == renderers_before
    if chunked:
        assert 1024 < sum(reads) < 20_000                       # stopped just past the limit, not at EOF
    else:
        assert reads == []                                      # refused on the declared length alone


def test_a_json_body_at_the_limit_is_read(env, monkeypatch):
    monkeypatch.setattr(render_gateway, "MAX_JSON_BYTES", 1024)
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, "")
    con.commit()
    con.close()
    body = {"secret": secret, "machine_id": "m-1", "version": VERSION, "pad": ""}
    body["pad"] = "x" * (1024 - len(json.dumps(body).encode()))
    payload = json.dumps(body).encode()
    assert len(payload) == 1024
    resp = _raw_put(env, io.BytesIO(payload), {"Content-Type": "application/json"},
                    path="/v1/enroll", method="POST")
    assert resp.status_code == 200 and resp.get_json()["renderer_id"]


@pytest.mark.parametrize("chunked", [False, True])
def test_an_oversized_heartbeat_is_refused(env, monkeypatch, chunked):
    monkeypatch.setattr(render_gateway, "MAX_JSON_BYTES", 1024)
    payload = json.dumps({"version": VERSION, "state": "idle", "last_error": "e" * 2000}).encode()
    resp = _raw_put(env, io.BytesIO(payload), {**B, "Content-Type": "application/json"},
                    length=None if chunked else len(payload), path="/v1/heartbeat", method="POST")
    assert resp.status_code == 413 and resp.get_json()["error"] == "body_too_large"
    assert _renderer(env)["last_heartbeat_at"] == ""


@pytest.mark.parametrize("path", ["/v1/claim", "/v1/jobs/vid-1/result"])
def test_the_claim_and_result_bodies_are_bounded_too(env, monkeypatch, path):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_JSON_BYTES", 1024)
    payload = json.dumps({"outcome": "failed", "error": "e" * 2000}).encode()
    resp = _raw_put(env, io.BytesIO(payload), {**J(env), "Content-Type": "application/json"},
                    path=path, method="POST")
    assert resp.status_code == 413
    assert _video(env)["status"] == "RENDERING" and _comments(env) == []


def test_the_gateway_never_parses_json_with_get_json(env, monkeypatch):
    import flask
    monkeypatch.setattr(flask.Request, "get_json", lambda *a, **k: pytest.fail("get_json"))
    _claimed(env)
    assert _beat(env, state="rendering", video_id="vid-1", claim_id=env.claim).status_code == 200
    assert _result(env, outcome="failed", error="x").status_code == 200


# ── result ────────────────────────────────────────────────────────────────────

def _upload(env, headers=B, data=b"MP4DATA"):
    assert env.client.put("/v1/jobs/vid-1/output", data=data, headers=J(env, headers)).status_code == 200


def _result(env, headers=B, **body):
    return env.client.post("/v1/jobs/vid-1/result", json=body, headers=J(env, headers))


def test_a_success_marks_the_render_uploaded_for_the_review(env):
    _claimed(env)
    _upload(env)
    assert _result(env, outcome="success", on_gpu=False, frames=90, seconds=45.0).get_json() == {}
    v = _video(env)
    assert v["status"] == "RENDERING"                # the worker's review thread finishes it
    assert v["render_uploaded_at"] and v["video_path"] == str(env.out / "proj-1" / "vid-1.mp4")
    assert v["renderer_id"] == "" and v["render_lease_until"] == "" and v["render_claim_id"] == ""
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
    assert v["renderer_id"] == "" and v["render_lease_until"] == "" and v["render_claim_id"] == ""
    assert _comments(env) == ["Render failed: Render stalled: no progress for 600s"]


def test_a_failed_render_that_timed_out_in_the_browser_is_requeued_once(env):
    _claimed(env)
    _result(env, outcome="failed", error="Error: Timeout (30000ms) exceeded rendering the component initially.",
            on_gpu=False, gpu_ok=None)
    v = _video(env)
    assert v["status"] == "RENDER_QUEUED" and v["render_fail_count"] == 0 and v["renderer_id"] == ""
    assert _comments(env)[-1].startswith("Render timed out inside the browser, so it was re-queued once")


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


# ── concurrency caps (test client) ────────────────────────────────────────────

def _enroll_body(env):
    con = sqlite3.connect(env.db)
    secret, _ = renderers.create_enrollment(con, "")
    con.commit()
    con.close()
    return json.dumps({"secret": secret, "machine_id": f"m-{secret[:6]}", "version": VERSION}).encode()


def test_unauthenticated_enrollment_bodies_are_capped(env, monkeypatch):
    """Only MAX_ENROLL_READERS enrollment bodies are read at once: one more
    is refused busy before a byte of it is read, and the slot comes back."""
    monkeypatch.setattr(render_gateway, "MAX_ENROLL_READERS", 1)
    seen = {}
    payload = _enroll_body(env)

    def second(n):
        if n == 1:
            body = _Body(8, on_read=lambda _n: pytest.fail("the refused enrollment's body was read"))
            r = _raw_put(env, body, {"Content-Type": "application/json"}, length=8,
                         path="/v1/enroll", method="POST")
            seen["status"], seen["json"], seen["retry"] = r.status_code, r.get_json(), r.headers.get("Retry-After")

    class Slow(io.RawIOBase):
        def __init__(self):
            self.data, self.reads = io.BytesIO(payload), 0

        def readable(self):
            return True

        def readinto(self, b):
            self.reads += 1
            second(self.reads)
            return self.data.readinto(b)
    resp = _raw_put(env, Slow(), {"Content-Type": "application/json"}, length=len(payload),
                    path="/v1/enroll", method="POST")
    assert resp.status_code == 200
    assert seen["status"] == 503 and seen["json"] == {"error": "busy"} and seen["retry"]
    assert _raw_put(env, io.BytesIO(_enroll_body(env)), {"Content-Type": "application/json"},
                    path="/v1/enroll", method="POST").status_code == 200


def test_one_renderers_requests_at_once_are_capped(env, monkeypatch):
    _claimed(env)
    _rid, h = _remote(env)
    monkeypatch.setattr(render_gateway, "MAX_REQUESTS_PER_RENDERER", 1)
    seen = {}

    def during(n):
        if n == 1:
            r = _beat(env)
            seen["builtin"], seen["json"] = r.status_code, r.get_json()
            seen["other"] = _beat(env, h).status_code
    resp = _raw_put(env, _Body(4, on_read=during), J(env), length=4)
    assert resp.status_code == 200
    assert seen["builtin"] == 503 and seen["json"] == {"error": "busy"}
    assert seen["other"] == 200                                    # another renderer is not held up
    assert _beat(env).status_code == 200                           # and the count comes back


def _in_flight(env):
    return dict(env.app.extensions["render_gateway.in_flight"])


def test_a_streamed_bundle_holds_its_renderers_count_until_it_is_closed(env, monkeypatch):
    """Served for real (the app as make_gateway_server wraps it), a request
    keeps its renderer's count until its response is closed: a bundle streams
    after the request's teardown, so a count released there let one renderer
    hold any number of bundles open."""
    from werkzeug.test import Client
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_REQUESTS_PER_RENDERER", 1)
    served = Client(render_gateway._bounded_app(env.app))
    held = served.get("/v1/jobs/vid-1/bundle", headers=J(env), buffered=False)
    assert held.status_code == 200
    assert _in_flight(env) == {"builtin": 1}
    busy = _beat(env)
    assert busy.status_code == 503 and busy.get_json() == {"error": "busy"}
    held.close()
    assert _in_flight(env) == {}
    assert _beat(env).status_code == 200
    assert _in_flight(env) == {}


def test_a_failing_app_releases_its_count_at_once(env, monkeypatch):
    """With no response to close (the app raised), the count goes back
    straight away."""
    from werkzeug.test import Client
    monkeypatch.setattr(env.app, "wsgi_app", _raising_after(env.app.wsgi_app))
    with pytest.raises(RuntimeError):
        Client(render_gateway._bounded_app(env.app)).post("/v1/heartbeat", json={}, headers=B)
    assert _in_flight(env) == {}


def _raising_after(wsgi_app):
    def app(environ, start_response):
        body = wsgi_app(environ, start_response)
        if hasattr(body, "close"):
            body.close()
        raise RuntimeError("dispatch failed")
    return app


def test_a_json_body_is_bounded_in_time(env, monkeypatch):
    """Checked between reads too, so a body trickled slower than its deadline
    ends with 408 even where no socket deadline applies."""
    monkeypatch.setattr(render_gateway, "JSON_BODY_SECS", 0.2)
    payload = json.dumps({"version": VERSION, "state": "idle"}).encode()

    class Trickle(io.RawIOBase):
        def __init__(self):
            self.data = io.BytesIO(payload)

        def readable(self):
            return True

        def readinto(self, b):
            time.sleep(0.05)
            return self.data.readinto(b[:2])
    resp = _raw_put(env, Trickle(), {**B, "Content-Type": "application/json"}, path="/v1/heartbeat", method="POST")
    assert resp.status_code == 408 and resp.get_json() == {"error": "body_timeout"}
    assert _renderer(env)["last_heartbeat_at"] == ""


class _Stalls(io.RawIOBase):
    """A body that hands out `first` bytes, then times out (as a socket read
    whose idle timeout ran out does)."""

    def __init__(self, first):
        self.left = first

    def readable(self):
        return True

    def readinto(self, b):
        if self.left <= 0:
            raise TimeoutError("timed out")
        take = min(self.left, len(b), 4)
        b[:take] = b"S" * take
        self.left -= take
        return take


@pytest.mark.parametrize("chunked", [False, True])
def test_an_upload_that_stalls_releases_its_slot_and_its_temp_file(env, monkeypatch, chunked):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 4)
    monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 1)
    resp = _raw_put(env, _Stalls(12), J(env), length=None if chunked else 100)
    assert resp.status_code == 408 and resp.get_json() == {"error": "body_timeout"}
    assert _temps(env) == [] and _upload_dir(env) == []
    # neither the claim's slot nor the only global one is still held
    assert env.client.put("/v1/jobs/vid-1/output", data=b"AGAIN", headers=J(env)).status_code == 200


# ── upload temp files ─────────────────────────────────────────────────────────

def test_leftover_temp_uploads_are_cleared_when_the_gateway_starts(env, tmp_path):
    temps = env.out / render_gateway.UPLOAD_TMP_DIR
    temps.mkdir(exist_ok=True)                              # made by the env's own gateway
    (temps / "abc.upload").write_bytes(b"orphan")
    (env.out / "proj-1").mkdir()
    final = env.out / "proj-1" / "vid-1.mp4"
    final.write_bytes(b"VIDEO")
    outside = tmp_path / "precious.upload"
    outside.write_bytes(b"keep")
    (temps / "link.upload").symlink_to(outside)
    (temps / "notes.txt").write_text("not ours")
    (temps / "dir.upload").mkdir()
    render_gateway.create_gateway_app(env.db, env.jobs, env.out, secrets_dir=env.secrets, remotion_dir=env.remotion)
    assert _temps(env) == ["dir.upload", "notes.txt"]       # only temp uploads go; a directory stays
    assert final.read_bytes() == b"VIDEO"                   # the video beside it is untouched
    assert outside.read_bytes() == b"keep"                  # a link is removed, never followed


def test_a_symlinked_upload_dir_is_never_used(env, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "x.upload").write_bytes(b"keep")
    (env.out / render_gateway.UPLOAD_TMP_DIR).rmdir()      # made by the env's own gateway
    (env.out / render_gateway.UPLOAD_TMP_DIR).symlink_to(elsewhere)
    app = render_gateway.create_gateway_app(env.db, env.jobs, env.out, secrets_dir=env.secrets,
                                            remotion_dir=env.remotion)
    assert (elsewhere / "x.upload").read_bytes() == b"keep"
    env.client = app.test_client()
    _claimed(env)
    resp = env.client.put("/v1/jobs/vid-1/output", data=b"MP4", headers=J(env))
    assert resp.status_code == 500 and resp.get_json()["error"] == "upload_failed"
    assert sorted(p.name for p in elsewhere.iterdir()) == ["x.upload"]


def test_old_orphans_are_swept_when_an_upload_is_admitted(env):
    _claimed(env)
    temps = env.out / render_gateway.UPLOAD_TMP_DIR
    temps.mkdir(exist_ok=True)
    old, fresh = temps / "old.upload", temps / "fresh.upload"
    old.write_bytes(b"o")
    fresh.write_bytes(b"f")
    then = time.time() - render_gateway.UPLOAD_ORPHAN_SECS - 60
    os.utime(old, (then, then))
    assert env.client.put("/v1/jobs/vid-1/output", data=b"MP4", headers=J(env)).status_code == 200
    assert _temps(env) == ["fresh.upload"]


def test_the_sweep_never_takes_an_upload_being_written(env, monkeypatch):
    """Even with no age margin, a second claim's admission leaves the first
    claim's temp file alone while it streams."""
    _claimed(env)
    a_claim = env.claim
    _rid, h = _remote(env)
    _seed(env, "vid-2", updated="2026-01-02T00:00:00Z")
    b = env.client.post("/v1/claim", json={}, headers=h).get_json()
    monkeypatch.setattr(render_gateway, "UPLOAD_ORPHAN_SECS", 0)
    monkeypatch.setattr(render_gateway, "CHUNK_BYTES", 4)
    seen = {}

    def other(n):
        if n == 2:
            seen["b"] = env.client.put("/v1/jobs/vid-2/output", data=b"B", headers=J(env, h, b["claim_id"])).status_code
    resp = _raw_put(env, _Body(12, fill=b"A", on_read=other), J(env, B, a_claim), length=12)
    assert seen["b"] == 200
    assert resp.status_code == 200 and (env.out / "proj-1" / "vid-1.mp4").read_bytes() == b"A" * 12


# ── time bounds on a real server ──────────────────────────────────────────────

@pytest.fixture
def live(env, tmp_path, monkeypatch):
    """The gateway served over real TLS on 127.0.0.1, with short time bounds
    (set them on render_gateway before calling `start`)."""
    tls = tmp_path / "live-tls"
    tauth.ensure_secrets(tls)
    started = []

    def start(**bounds):
        for k, v in bounds.items():
            monkeypatch.setattr(render_gateway, k, v)
        server = render_gateway.make_gateway_server(env.app, "127.0.0.1", 0, secrets_dir=tls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return server.server_port

    def connect(port, handshake=True):
        import socket
        raw = socket.create_connection(("127.0.0.1", port), timeout=10)
        if not handshake:
            return raw
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx.wrap_socket(raw)
    yield type("Live", (), {"start": staticmethod(start), "connect": staticmethod(connect)})
    for server, thread in started:
        server.shutdown()
        thread.join(5)


def _request_threads():
    return [t for t in threading.enumerate() if "process_request_thread" in t.name]


def _wait_no_request_threads(secs=5.0):
    end = time.monotonic() + secs
    while _request_threads() and time.monotonic() < end:
        time.sleep(0.05)
    return _request_threads()


def _reply(sock, timeout=10.0) -> tuple[bytes, float]:
    """Everything the server sends until it closes, and how long that took."""
    sock.settimeout(timeout)
    t0 = time.monotonic()
    data = b""
    while True:
        try:
            chunk = sock.recv(65536)
        except (ssl.SSLError, OSError):
            break
        if not chunk:
            break
        data += chunk
    return data, time.monotonic() - t0


def _head(path, headers, method="POST") -> bytes:
    lines = [f"{method} {path} HTTP/1.1", "Host: gateway"] + [f"{k}: {v}" for k, v in headers.items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


@pytest.mark.parametrize("chunked", [False, True])
def test_a_json_body_that_stalls_is_ended_and_its_thread_freed(env, live, chunked):
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=1)
    sock = live.connect(port)
    framing = {"Transfer-Encoding": "chunked"} if chunked else {"Content-Length": "500"}
    sock.sendall(_head("/v1/enroll", {"Content-Type": "application/json", **framing}))
    sock.sendall(b"5\r\n{\"sec\r\n" if chunked else b"{\"sec")         # well under the limit, then nothing
    data, took = _reply(sock)
    sock.close()
    assert data.startswith(b"HTTP/1.1 408") and b"body_timeout" in data
    assert took < 5
    assert _wait_no_request_threads() == []


@pytest.mark.parametrize("chunked", [False, True])
def test_a_json_body_trickled_past_its_deadline_is_ended(env, live, chunked):
    """Each byte arrives inside the idle timeout, so only the body's total
    deadline can end it. Chunked, one large chunk is announced and trickled:
    werkzeug then asks for the whole chunk in one read, which only the
    connection's reader can cut short."""
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5, JSON_BODY_SECS=1)
    sock = live.connect(port)
    framing = {"Transfer-Encoding": "chunked"} if chunked else {"Content-Length": "60000"}
    sock.sendall(_head("/v1/enroll", {"Content-Type": "application/json", **framing})
                 + (b"ea60\r\n" if chunked else b""))
    stop = threading.Event()

    def trickle():
        while not stop.wait(0.2):
            try:
                sock.sendall(b" ")
            except OSError:
                return
    t = threading.Thread(target=trickle, daemon=True)
    t.start()
    try:
        data, took = _reply(sock, timeout=8)
    finally:
        stop.set()
        t.join(2)
        sock.close()
    assert data.startswith(b"HTTP/1.1 408") and took < 4
    assert _wait_no_request_threads() == []


@pytest.mark.parametrize("length", ["1000", str(1 << 40)])
def test_a_protected_route_answers_401_without_reading_its_body(env, live, length):
    """The body is announced and never sent: authentication needs only the
    headers, so the refusal comes at once, not after a read times out."""
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5)
    sock = live.connect(port)
    sock.sendall(_head("/v1/heartbeat", {"Authorization": "Bearer nope", "Content-Type": "application/json",
                                         "Content-Length": length}))
    data, took = _reply(sock)
    sock.close()
    assert data.startswith(b"HTTP/1.1 401") and b"unauthorized" in data
    assert took < 2


def test_an_unread_body_after_a_reply_is_drained_only_briefly(env, live):
    """werkzeug reads what is left of a body after the reply so the client
    sees it (as long as more keeps arriving within 10 ms, up to 10 GB); a
    client that keeps trickling gets DRAIN_SECS of that, then the connection
    closes."""
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5, DRAIN_SECS=1)
    sock = live.connect(port)
    sock.sendall(_head("/v1/heartbeat", {"Authorization": "Bearer nope", "Content-Length": str(1 << 30)})
                 + b"x" * 100)
    stop = threading.Event()

    def trickle():
        while not stop.wait(0.003):
            try:
                sock.sendall(b"x")
            except OSError:
                return
    t = threading.Thread(target=trickle, daemon=True)
    t.start()
    try:
        data, took = _reply(sock, timeout=10)
    finally:
        stop.set()
        t.join(2)
        sock.close()
    assert data.startswith(b"HTTP/1.1 401") and took < 4
    assert _wait_no_request_threads() == []


def test_a_request_head_trickled_past_its_deadline_is_closed(env, live):
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5, REQUEST_HEAD_SECS=1)
    sock = live.connect(port)
    sock.sendall(b"GET /v1/version HTTP/1.1\r\n")
    stop = threading.Event()

    def trickle():
        while not stop.wait(0.2):
            try:
                sock.sendall(b"X-Slow: 1\r\n")
            except OSError:
                return
    t = threading.Thread(target=trickle, daemon=True)
    t.start()
    try:
        data, took = _reply(sock, timeout=8)
    finally:
        stop.set()
        t.join(2)
        sock.close()
    assert b"200" not in data and took < 4
    assert _wait_no_request_threads() == []


def test_a_client_that_never_finishes_its_handshake_holds_up_no_one(env, live):
    """The handshake happens in the connection's own thread under the head
    deadline, never in the accept loop."""
    port = live.start(REQUEST_HEAD_SECS=30)
    silent = live.connect(port, handshake=False)        # TCP only; no ClientHello ever
    try:
        sock = live.connect(port)
        sock.sendall(_head("/v1/version", {}, method="GET"))
        data, took = _reply(sock, timeout=5)
        sock.close()
        assert data.startswith(b"HTTP/1.1 200") and took < 3
    finally:
        silent.close()


def _until(check, secs=5.0):
    end = time.monotonic() + secs
    while not check() and time.monotonic() < end:
        time.sleep(0.02)
    return check()


def test_connections_past_the_cap_are_closed_before_a_thread_is_made(env, live):
    """Clients that open connections and never start a TLS handshake hold
    every slot: the next connections are closed at once and get no thread,
    and the slots come back when the holders' head deadline ends them."""
    assert _wait_no_request_threads() == []
    port = live.start(MAX_CONNECTIONS=3, REQUEST_HEAD_SECS=3)
    holders = [live.connect(port, handshake=False) for _ in range(3)]
    try:
        assert _until(lambda: len(_request_threads()) == 3)
        for _ in range(10):
            extra = live.connect(port, handshake=False)
            data, took = _reply(extra, timeout=5)
            extra.close()
            assert data == b"" and took < 1
            assert len(_request_threads()) <= 3
        assert _wait_no_request_threads(secs=6) == []        # the holders' head deadline ended them
        sock = live.connect(port)
        sock.sendall(_head("/v1/version", {}, method="GET"))
        data, _ = _reply(sock)
        sock.close()
        assert data.startswith(b"HTTP/1.1 200")
    finally:
        for h in holders:
            h.close()


def _trickling(sock):
    stop = threading.Event()

    def trickle():
        while not stop.wait(0.003):
            try:
                sock.sendall(b"x")
            except OSError:
                return
    t = threading.Thread(target=trickle, daemon=True)
    t.start()
    return stop, t


def _read_head(sock, timeout=5.0) -> bytes:
    sock.settimeout(timeout)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    return data


def test_an_early_answer_holds_its_renderers_count_until_its_body_is_drained(env, live, monkeypatch):
    """A 413 goes out before the body is read; werkzeug then drains the
    body, and the renderer's count is held until that drain ends."""
    monkeypatch.setattr(render_gateway, "MAX_REQUESTS_PER_RENDERER", 1)
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5, DRAIN_SECS=1.5)
    sock = live.connect(port)
    sock.sendall(_head("/v1/heartbeat", {**B, "Content-Type": "application/json",
                                         "Content-Length": str(1 << 30)}) + b"x" * 100)
    stop, t = _trickling(sock)
    try:
        assert _read_head(sock).startswith(b"HTTP/1.1 413")
        assert _in_flight(env) == {"builtin": 1}
        busy = _beat(env)
        assert busy.status_code == 503 and busy.get_json() == {"error": "busy"}
        _reply(sock, timeout=10)
    finally:
        stop.set()
        t.join(2)
        sock.close()
    assert _wait_no_request_threads() == []
    assert _in_flight(env) == {}
    assert _beat(env).status_code == 200


def test_a_drain_that_fails_still_releases_its_count(env, live, monkeypatch):
    """werkzeug closes the response only when its drain of the body ended
    without an error; a client gone mid-drain (a read raising) skips that
    close, and the connection's end releases the count instead."""
    real_read = render_gateway._BoundedReader.read

    def read(self, n=-1):
        if self.eof_at is not None:          # the reply has started: this is the drain
            raise ConnectionResetError("the client went away")
        return real_read(self, n)
    monkeypatch.setattr(render_gateway._BoundedReader, "read", read)
    monkeypatch.setattr(render_gateway, "MAX_REQUESTS_PER_RENDERER", 1)
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5)
    sock = live.connect(port)
    sock.sendall(_head("/v1/heartbeat", {**B, "Content-Type": "application/json",
                                         "Content-Length": str(1 << 30)}) + b"x" * 100)
    stop, t = _trickling(sock)
    try:
        assert _read_head(sock).startswith(b"HTTP/1.1 413")
        _reply(sock, timeout=10)
    finally:
        stop.set()
        t.join(2)
        sock.close()
    assert _wait_no_request_threads() == []
    assert _in_flight(env) == {}
    assert _beat(env).status_code == 200


def test_a_request_on_a_real_server_is_released_exactly_once(env, live, monkeypatch):
    """The real server releases from two places (the response's close and
    the connection's end): another request of the same renderer, still
    open, keeps its count."""
    from werkzeug.test import Client
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_REQUESTS_PER_RENDERER", 2)
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=5)
    held = Client(render_gateway._bounded_app(env.app)).get("/v1/jobs/vid-1/bundle", headers=J(env),
                                                             buffered=False)
    assert _in_flight(env) == {"builtin": 1}
    body = json.dumps({"version": VERSION, "state": "idle"}).encode()
    sock = live.connect(port)
    sock.sendall(_head("/v1/heartbeat", {**B, "Content-Type": "application/json",
                                         "Content-Length": str(len(body))}) + body)
    data, _ = _reply(sock)
    sock.close()
    assert data.startswith(b"HTTP/1.1 200")
    assert _wait_no_request_threads() == []
    assert _in_flight(env) == {"builtin": 1}
    held.close()
    assert _in_flight(env) == {}


def test_a_stalled_upload_on_a_real_server_frees_its_slot(env, live, monkeypatch):
    _claimed(env)
    monkeypatch.setattr(render_gateway, "MAX_CONCURRENT_UPLOADS", 1)
    port = live.start(GATEWAY_IDLE_TIMEOUT_SECS=1)
    sock = live.connect(port)
    sock.sendall(_head("/v1/jobs/vid-1/output", {**J(env), "Content-Length": "1000000"}, method="PUT"))
    sock.sendall(b"M" * 1000)
    data, took = _reply(sock)
    sock.close()
    assert data.startswith(b"HTTP/1.1 408") and took < 5
    assert _temps(env) == [] and _upload_dir(env) == []
    assert _wait_no_request_threads() == []
    assert env.client.put("/v1/jobs/vid-1/output", data=b"AGAIN", headers=J(env)).status_code == 200


# ── the whole path, twice, by the scheduler ───────────────────────────────────

def test_a_remote_renderer_claims_renders_and_uploads(env):
    rid, h = _remote(env)
    _seed(env)
    reply = env.client.post("/v1/claim", json={}, headers=h).get_json()
    assert reply["video_id"] == "vid-1"
    env.claim = reply["claim_id"]
    assert env.client.get("/v1/jobs/vid-1/bundle", headers=J(env, h)).status_code == 200
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


def _damage_tls(tls, other, damage):
    """Leave `tls` holding two non-empty files that are not a usable pair."""
    if damage == "mismatched":
        tauth.ensure_secrets(other)
        (tls / tauth.TLS_CERT_NAME).write_text((other / tauth.TLS_CERT_NAME).read_text())
    else:
        pem = (tls / tauth.TLS_CERT_NAME).read_text()
        (tls / tauth.TLS_CERT_NAME).write_text(pem[: len(pem) // 2])


@pytest.mark.parametrize("damage", ["mismatched", "truncated"])
def test_an_unusable_tls_pair_means_no_gateway_server(env, tmp_path, caplog, damage):
    """A key and a certificate restored from different backups, or a
    truncated one, are logged and the gateway is not started (the API goes
    on); the pair is left as it is, since a new one would be a new pin."""
    tls = tmp_path / "tls"
    tauth.ensure_secrets(tls)
    _damage_tls(tls, tmp_path / "other", damage)
    before = {n: (tls / n).read_text() for n in tauth.TLS_NAMES}
    assert render_gateway.make_gateway_server(env.app, "127.0.0.1", 0, secrets_dir=tls) is None
    assert "render gateway not started: its TLS key and certificate cannot be used as a pair" in caplog.text
    assert {n: (tls / n).read_text() for n in tauth.TLS_NAMES} == before


def test_a_port_that_cannot_be_bound_means_no_gateway_server(env, tmp_path, caplog):
    """werkzeug answers a failed bind with sys.exit(1): that must not end the
    API process, which serves the dashboard too."""
    import socket
    tls = tmp_path / "tls"
    tauth.ensure_secrets(tls)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert render_gateway.make_gateway_server(env.app, "127.0.0.1", port, secrets_dir=tls) is None
    assert f"render gateway not started: it cannot listen on port {port}" in caplog.text


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


@pytest.mark.parametrize("damage", ["mismatched", "truncated"])
def test_the_api_runs_without_the_gateway_when_its_tls_pair_is_unusable(api_server, tmp_path, caplog, damage):
    server, _, secrets = api_server
    _damage_tls(secrets, tmp_path / "other", damage)
    assert server.start_render_gateway() is None
    assert "cannot be used as a pair" in caplog.text
    ran = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(server.app, "run", lambda **kw: ran.append(kw))
        server.main()
    assert ran and ran[0]["port"] == 4000        # the dashboard's API still serves


def test_the_api_runs_without_the_gateway_when_its_port_is_taken(api_server, monkeypatch, caplog):
    import socket
    server, _, _ = api_server
    with socket.socket() as taken:
        taken.bind(("0.0.0.0", 0))
        taken.listen()
        monkeypatch.setenv("TUBEMATIC_GATEWAY_PORT", str(taken.getsockname()[1]))
        assert server.start_render_gateway() is None
        assert "cannot listen on port" in caplog.text
        ran = []
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(server.app, "run", lambda **kw: ran.append(kw))
            server.main()
    assert ran and ran[0]["port"] == 4000        # the dashboard's API still serves
