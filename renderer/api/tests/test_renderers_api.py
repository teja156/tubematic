"""The dashboard's renderer routes (TMDEV-190): list, enroll, enable/rename,
remove, and a per-renderer GPU test.

What these guard: a credential hash never leaves the API; an enrollment token
is only issued while remote renderers are on (it would otherwise name an
address nobody can reach) and carries this gateway's address and pin; the
built-in renderer can be disabled but never removed; and a removed renderer's
credentials stop working at once.

Run from renderer/api/: pytest tests/test_renderers_api.py
"""
import json
import os
import sqlite3

import pytest
from flask import Flask

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline

from tubematic_core import auth
from tubematic_core import renderers as trenderers

from .builtin_gpu import store_builtin_probe

REMOTE = "r_aaaaaaaaaaaa"


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test.db")
    pipeline._init_db(p)
    return p


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    d = tmp_path / "secrets"
    auth.ensure_secrets(d)
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(d))
    return d


@pytest.fixture
def client(db_path, secrets):
    os.environ["TUBEMATIC_DB"] = db_path
    app = Flask(__name__)
    app.register_blueprint(pipeline.create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sql(db_path, sql, params=()):
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(sql, params)
        rows = cur.fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def _remote(db_path, rid=REMOTE, name="Studio PC", **cols):
    values = {"id": rid, "name": name, "created_at": "2026-01-01T00:00:00Z",
              "credential_hash": trenderers.hash_secret("cred"),
              "previous_credential_hash": trenderers.hash_secret("old"),
              "credential_issued_at": "2026-01-01T00:00:00Z",
              "credential_expires_at": "2026-01-31T00:00:00Z",
              "host": "studio", "machine_id": "m1", **cols}
    _sql(db_path, f"INSERT INTO renderers ({', '.join(values)}) "
                  f"VALUES ({', '.join('?' for _ in values)})", tuple(values.values()))


def _turn_on(db_path, address="render.example.com:4443"):
    _sql(db_path, "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
         (pipeline.RENDER_GATEWAY_ADDRESS_KEY, address))


def _video(db_path, vid="vid_aaaaaaaaaaaa", title="The title", topic="The topic"):
    _sql(db_path, "INSERT INTO videos (id, project_id, topic, title, strategy, "
                  "producibility_score, status, created_at, updated_at) VALUES "
                  "(?, 'p', ?, ?, 'manual', 8, 'RENDERING', '2026-01-01T00:00:00Z', "
                  "'2026-01-01T00:00:00Z')", (vid, topic, title))


# ── GET /renderers ───────────────────────────────────────────────────────────

def test_the_list_starts_with_the_builtin_renderer_and_remote_off(client):
    body = client.get("/renderers").get_json()
    assert body["remote_enabled"] is False and body["gateway_address"] == ""
    [builtin] = body["renderers"]
    assert builtin["id"] == "builtin" and builtin["builtin"] is True
    assert builtin["gpu"] is None and builtin["probe_pending"] is False
    assert builtin["compute"] == {} and builtin["current_video_title"] == ""


def test_the_list_says_remote_renderers_are_on_and_where(client, db_path):
    _turn_on(db_path, "render.example.com:8443")
    body = client.get("/renderers").get_json()
    assert body["remote_enabled"] is True
    assert body["gateway_address"] == "render.example.com:8443"


def test_no_credential_hash_ever_leaves_the_api(client, db_path):
    _remote(db_path)
    raw = client.get("/renderers").get_data(as_text=True)
    assert trenderers.hash_secret("cred") not in raw
    assert trenderers.hash_secret("old") not in raw
    assert "credential_hash" not in raw and "machine_id" not in raw
    body = client.patch(f"/renderers/{REMOTE}", json={"name": "New"}).get_data(as_text=True)
    assert trenderers.hash_secret("cred") not in body and "credential_hash" not in body


def test_a_row_carries_compute_the_probe_summary_and_the_current_video(client, db_path):
    _video(db_path)
    probe = {"at": "2026-01-01T00:00:00.000001Z", "configured": True, "ok": False,
             "gpu": {"uuid": "GPU-aaaa", "name": "NVIDIA RTX 4090"}, "error": "swiftshader",
             "renderer": "ANGLE (Google, SwiftShader)", "host_gpus": [], "smi": None}
    compute = {"cpus": 16, "memory_bytes": 64 << 30,
               "gpus": [{"name": "NVIDIA RTX 4090", "uuid": "GPU-aaaa", "memory_mb": 24564}]}
    _remote(db_path, compute=json.dumps(compute), gpu_probe=json.dumps(probe),
            state="rendering", current_video_id="vid_aaaaaaaaaaaa",
            gpu_probe_requested_at="2026-01-02T00:00:00.000000Z")
    [_, row] = client.get("/renderers").get_json()["renderers"]
    assert row["compute"] == compute and row["host"] == "studio"
    assert row["gpu"] == {"ok": False, "configured": True, "error": "swiftshader",
                          "renderer": "ANGLE (Google, SwiftShader)", "name": "NVIDIA RTX 4090",
                          "at": "2026-01-01T00:00:00.000001Z"}
    assert row["current_video_title"] == "The title"
    # A Test asked for after the last probe is still waiting; it runs between
    # renders.
    assert row["probe_pending"] is True and row["waiting_for_render"] is True
    # renderer_states' own fields are all there.
    for key in ("online", "needs_upgrade", "gpu_verified", "last_heartbeat_at", "last_error",
                "credential_expires_at", "version", "gpu_probed", "gpu_configured", "gpu_error"):
        assert key in row


def test_an_untitled_current_video_shows_its_topic(client, db_path):
    _video(db_path, title="")
    _remote(db_path, current_video_id="vid_aaaaaaaaaaaa", state="rendering")
    [_, row] = client.get("/renderers").get_json()["renderers"]
    assert row["current_video_title"] == "The topic"


def test_a_removed_renderer_is_not_listed(client, db_path):
    _remote(db_path, removed_at="2026-01-05T00:00:00Z")
    assert [r["id"] for r in client.get("/renderers").get_json()["renderers"]] == ["builtin"]


# ── POST /renderers/enrollments ──────────────────────────────────────────────

def test_no_token_while_remote_renderers_are_off(client, db_path):
    r = client.post("/renderers/enrollments", json={"name": "Studio PC"})
    assert r.status_code == 409 and r.get_json() == {"error": "remote_renderers_off"}
    assert _sql(db_path, "SELECT COUNT(*) FROM renderer_enrollments") == [(0,)]


def test_a_token_names_this_gateway_and_its_pin(client, db_path, secrets):
    _turn_on(db_path, "render.example.com:8443")
    r = client.post("/renderers/enrollments", json={"name": "  Studio PC  "})
    assert r.status_code == 201
    body = r.get_json()
    assert set(body) == {"token", "expires_at", "command"}
    decoded = trenderers.decode_enrollment_token(body["token"])
    assert decoded["url"] == "https://render.example.com:8443"
    assert decoded["pin"] == auth.gateway_pin(secrets)
    assert body["command"] == (f"python3 tubematic_remote_renderer.py install "
                               f"--token '{body['token']}'")
    # One-time, hashed, named: the secret itself is never stored.
    [(stored, name, expires)] = _sql(db_path, "SELECT secret_hash, name, expires_at "
                                              "FROM renderer_enrollments")
    assert stored == trenderers.hash_secret(decoded["secret"])
    assert name == "Studio PC" and expires == body["expires_at"]


@pytest.mark.parametrize("address,url", [
    ("render.example.com", "https://render.example.com:4443"),
    ("192.168.1.20", "https://192.168.1.20:4443"),
    ("[2001:db8::1]", "https://[2001:db8::1]:4443"),
    ("[2001:db8::1]:9443", "https://[2001:db8::1]:9443"),
])
def test_the_default_port_is_added_when_the_address_names_none(client, db_path, address, url):
    _turn_on(db_path, address)
    body = client.post("/renderers/enrollments", json={}).get_json()
    assert trenderers.decode_enrollment_token(body["token"])["url"] == url


@pytest.mark.parametrize("body", [{}, {"name": None}, {"name": ""}, {"name": "   "}])
def test_a_token_needs_no_name(client, db_path, body):
    _turn_on(db_path)
    assert client.post("/renderers/enrollments", json=body).status_code == 201
    assert _sql(db_path, "SELECT name FROM renderer_enrollments") == [("",)]


@pytest.mark.parametrize("name", ["x" * 61, 5, ["a"]])
def test_a_bad_enrollment_name_is_refused(client, db_path, name):
    _turn_on(db_path)
    r = client.post("/renderers/enrollments", json={"name": name})
    assert r.status_code == 400
    assert _sql(db_path, "SELECT COUNT(*) FROM renderer_enrollments") == [(0,)]


def test_no_token_without_the_gateway_certificate(client, db_path, tmp_path, monkeypatch):
    _turn_on(db_path)
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "empty"))
    r = client.post("/renderers/enrollments", json={})
    assert r.status_code == 503 and r.get_json() == {"error": "gateway_certificate_missing"}
    assert _sql(db_path, "SELECT COUNT(*) FROM renderer_enrollments") == [(0,)]


# ── PATCH /renderers/<id> ────────────────────────────────────────────────────

def test_a_renderer_can_be_disabled_and_renamed(client, db_path):
    _remote(db_path)
    r = client.patch(f"/renderers/{REMOTE}", json={"enabled": False, "name": "  Garage  "})
    assert r.status_code == 200
    assert r.get_json()["enabled"] is False and r.get_json()["name"] == "Garage"
    assert _sql(db_path, "SELECT enabled, name FROM renderers WHERE id = ?",
                (REMOTE,)) == [(0, "Garage")]


def test_the_builtin_renderer_can_be_disabled(client, db_path):
    assert client.patch("/renderers/builtin", json={"enabled": False}).status_code == 200
    assert _sql(db_path, "SELECT enabled FROM renderers WHERE id = 'builtin'") == [(0,)]


@pytest.mark.parametrize("body", [
    {}, {"other": 1}, {"enabled": "false"}, {"enabled": 0}, {"name": ""}, {"name": "   "},
    {"name": "x" * 61}, {"name": 7},
])
def test_a_bad_patch_is_refused_and_changes_nothing(client, db_path, body):
    _remote(db_path)
    assert client.patch(f"/renderers/{REMOTE}", json=body).status_code == 400
    assert _sql(db_path, "SELECT enabled, name FROM renderers WHERE id = ?",
                (REMOTE,)) == [(1, "Studio PC")]


def test_a_sixty_character_name_is_accepted(client, db_path):
    _remote(db_path)
    assert client.patch(f"/renderers/{REMOTE}", json={"name": "x" * 60}).status_code == 200


def test_patching_an_unknown_or_removed_renderer_is_404(client, db_path):
    _remote(db_path, removed_at="2026-01-05T00:00:00Z")
    for rid in (REMOTE, "r_bbbbbbbbbbbb"):
        r = client.patch(f"/renderers/{rid}", json={"enabled": False})
        assert r.status_code == 404 and r.get_json() == {"error": "not_found"}
    assert _sql(db_path, "SELECT enabled FROM renderers WHERE id = ?", (REMOTE,)) == [(1,)]


# ── DELETE /renderers/<id> ───────────────────────────────────────────────────

def test_removing_a_renderer_clears_its_credentials(client, db_path):
    _remote(db_path)
    r = client.delete(f"/renderers/{REMOTE}")
    assert r.status_code == 200 and r.get_json()["id"] == REMOTE
    [(removed_at, cred, prev)] = _sql(db_path, "SELECT removed_at, credential_hash, "
                                               "previous_credential_hash FROM renderers "
                                               "WHERE id = ?", (REMOTE,))
    assert removed_at and cred == "" and prev == ""
    # Its credential no longer authenticates at the gateway.
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        assert trenderers.authenticate(con, "cred", trenderers.now_ts()) is None
    finally:
        con.close()


def test_the_builtin_renderer_cannot_be_removed(client, db_path):
    r = client.delete("/renderers/builtin")
    assert r.status_code == 409 and r.get_json() == {"error": "builtin"}
    assert _sql(db_path, "SELECT removed_at FROM renderers WHERE id = 'builtin'") == [(None,)]


def test_removing_twice_is_404(client, db_path):
    _remote(db_path)
    assert client.delete(f"/renderers/{REMOTE}").status_code == 200
    r = client.delete(f"/renderers/{REMOTE}")
    assert r.status_code == 404 and r.get_json() == {"error": "not_found"}


# ── POST /renderers/<id>/gpu-test ────────────────────────────────────────────

def test_a_gpu_test_stamps_only_that_renderer(client, db_path):
    _remote(db_path)
    r = client.post(f"/renderers/{REMOTE}/gpu-test")
    assert r.status_code == 202
    assert r.get_json()["id"] == REMOTE and r.get_json()["probe_pending"] is True
    [(requested,)] = _sql(db_path, "SELECT gpu_probe_requested_at FROM renderers WHERE id = ?",
                          (REMOTE,))
    # now_precise: the gateway compares it with the probe's own "at".
    assert requested.endswith("Z") and "." in requested
    assert _sql(db_path, "SELECT gpu_probe_requested_at FROM renderers "
                         "WHERE id = 'builtin'") == [("",)]


def test_a_probe_newer_than_the_request_answers_it(client, db_path):
    client.post("/renderers/builtin/gpu-test")
    store_builtin_probe(db_path, {"at": "9999-01-01T00:00:00.000000Z", "configured": False,
                                  "ok": False, "gpu": None, "error": "", "renderer": ""})
    [row] = client.get("/renderers").get_json()["renderers"]
    assert row["probe_pending"] is False and row["gpu"]["at"].startswith("9999")


def test_a_gpu_test_for_an_unknown_or_removed_renderer_is_404(client, db_path):
    _remote(db_path, removed_at="2026-01-05T00:00:00Z")
    for rid in (REMOTE, "r_bbbbbbbbbbbb"):
        assert client.post(f"/renderers/{rid}/gpu-test").status_code == 404


# ── Copies kept in sync with onboarding ──────────────────────────────────────

def test_the_api_and_onboarding_agree_on_the_row_and_the_command():
    """onboard.py --step renderers writes the row this API reads, and prints
    the same host command the dashboard shows."""
    from onboard import remote_renderers
    assert pipeline.RENDER_GATEWAY_ADDRESS_KEY == remote_renderers.SETTING_KEY
    assert pipeline.REMOTE_RENDERER_COMMAND == remote_renderers.HOST_COMMAND
    assert pipeline.RENDER_GATEWAY_DEFAULT_PORT == remote_renderers.DEFAULT_PORT
