"""The API's bearer token and the dashboard's password login (TMDEV-152).

The check is installed on the app, not on the pipeline blueprint: about 700
existing test calls build a bare app around the blueprint, and the health
routes live on the app precisely so that blueprint hooks never see them.
"""
import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest
from flask import Flask, jsonify

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import api_auth
from api_auth import LoginThrottle, create_auth_blueprint, install_auth
from pipeline import create_pipeline_blueprint
from tubematic_core import auth as core_auth

TOKEN = "test-api-token-0123456789"
PASSWORD = "a long enough password"


def _app(db_path, throttle=None):
    os.environ["TUBEMATIC_DB"] = str(db_path)
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/render/health")
    def render_health():
        return jsonify({"status": "ok"})

    app.register_blueprint(create_pipeline_blueprint())
    app.register_blueprint(create_auth_blueprint(str(db_path), throttle=throttle))
    install_auth(app, TOKEN)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def db(tmp_path):
    return tmp_path / "t.db"


@pytest.fixture
def client(db):
    with _app(db).test_client() as c:
        yield c


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong"},
    {"Authorization": f"Basic {TOKEN}"},
    {"Authorization": TOKEN},
    {"Authorization": f"Bearer {TOKEN}x"},
])
def test_every_pipeline_route_refuses_a_missing_or_wrong_token(client, headers):
    for method, path in [("GET", "/settings"), ("GET", "/videos"), ("POST", "/settings"),
                         ("GET", "/agents"), ("POST", "/publishing/accounts/connect"),
                         ("GET", "/no/such/route")]:
        r = client.open(path, method=method, headers=headers, json={})
        assert r.status_code == 401, (method, path)
        assert r.get_json() == {"error": "unauthorized"}


def test_the_right_token_passes(client):
    assert client.get("/settings", headers=_auth()).status_code == 200
    assert client.get("/settings", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


def test_health_routes_stay_open(client):
    assert client.get("/health").status_code == 200
    assert client.get("/render/health").status_code == 200


def test_the_exemption_is_by_endpoint_not_path_prefix(db):
    """A route whose path merely starts with /health must still need the token."""
    app = _app(db)

    @app.get("/healthz-but-secret")
    def secret():
        return jsonify({"secret": True})

    with app.test_client() as c:
        assert c.get("/healthz-but-secret").status_code == 401


def test_the_check_covers_routes_outside_the_pipeline_blueprint(db):
    """Installed on the app, so a route added anywhere is covered by default."""
    app = _app(db)

    @app.get("/elsewhere")
    def elsewhere():
        return "x"

    with app.test_client() as c:
        assert c.get("/elsewhere").status_code == 401
        assert c.get("/elsewhere", headers=_auth()).status_code == 200


def test_the_password_hash_is_never_served_and_never_writable(client, db):
    core_auth.set_admin_password(db, PASSWORD)

    body = client.get("/settings", headers=_auth()).get_json()
    assert core_auth.PASSWORD_KEY not in body
    assert "scrypt$" not in str(body)

    r = client.post("/settings", headers=_auth(), json={core_auth.PASSWORD_KEY: "scrypt$1$1$1$a$b"})
    assert r.status_code == 400
    assert core_auth.verify_password(PASSWORD, core_auth.admin_password_hash(db))


def test_login_needs_the_api_token_too(client, db):
    core_auth.set_admin_password(db, PASSWORD)
    assert client.post("/auth/login", json={"password": PASSWORD}).status_code == 401


def test_login_accepts_the_right_password(client, db):
    core_auth.set_admin_password(db, PASSWORD)
    r = client.post("/auth/login", headers=_auth(), json={"password": PASSWORD})
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}


@pytest.mark.parametrize("body", [{"password": "nope nope nope"}, {"password": ""}, {}, {"password": 5}])
def test_login_refuses_a_wrong_or_malformed_password(client, db, body):
    core_auth.set_admin_password(db, PASSWORD)
    r = client.post("/auth/login", headers=_auth(), json=body)
    assert r.status_code in (400, 401)
    assert "ok" not in r.get_json()


def test_login_refuses_an_oversized_password_before_hashing(client, db, monkeypatch):
    core_auth.set_admin_password(db, PASSWORD)
    monkeypatch.setattr(api_auth.core_auth, "verify_password",
                        lambda *a: pytest.fail("hashed an oversized password"))
    r = client.post("/auth/login", headers=_auth(), json={"password": "x" * 5000})
    assert r.status_code == 400


def test_login_with_no_password_set_says_how_to_set_one(client):
    r = client.post("/auth/login", headers=_auth(), json={"password": PASSWORD})
    assert r.status_code == 503
    assert "--set-password" in r.get_json()["error"]


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_throttle_allows_free_failures_then_backs_off_exponentially():
    clock = _Clock()
    t = LoginThrottle(clock=clock)
    for _ in range(LoginThrottle.FREE_FAILURES):
        assert t.retry_after() == 0
        t.record(False)
    t.record(False)
    assert t.retry_after() == 2
    clock.now += 2
    assert t.retry_after() == 0
    t.record(False)
    assert t.retry_after() == 4


def test_throttle_caps_the_wait_and_a_success_resets_it():
    clock = _Clock()
    t = LoginThrottle(clock=clock)
    for _ in range(60):
        t.record(False)
    assert t.retry_after() == LoginThrottle.MAX_WAIT
    clock.now += LoginThrottle.MAX_WAIT
    t.record(True)
    t.record(False)
    assert t.retry_after() == 0


def test_a_locked_login_answers_429_without_checking_the_password(db, monkeypatch):
    clock = _Clock()
    throttle = LoginThrottle(clock=clock)
    app = _app(db, throttle=throttle)
    core_auth.set_admin_password(db, PASSWORD)
    with app.test_client() as c:
        for _ in range(LoginThrottle.FREE_FAILURES + 1):
            c.post("/auth/login", headers=_auth(), json={"password": "wrong wrong wrong"})
        monkeypatch.setattr(api_auth.core_auth, "verify_password",
                            lambda *a: pytest.fail("checked a password while locked"))
        r = c.post("/auth/login", headers=_auth(), json={"password": PASSWORD})
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) > 0


def test_server_refuses_to_start_without_the_token(tmp_path, monkeypatch):
    """Fail closed: a missing secret file must stop the API, never open it."""
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("TUBEMATIC_DB", str(tmp_path / "s.db"))
    spec = importlib.util.spec_from_file_location(
        "server_under_test", Path(__file__).resolve().parents[1] / "server.py")
    with pytest.raises(core_auth.SecretMissing):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_server_wires_the_check_from_the_token_file(tmp_path, monkeypatch):
    sdir = tmp_path / "secrets"
    core_auth.ensure_secrets(sdir)
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(sdir))
    monkeypatch.setenv("TUBEMATIC_DB", str(tmp_path / "s.db"))
    spec = importlib.util.spec_from_file_location(
        "server_under_test", Path(__file__).resolve().parents[1] / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with mod.app.test_client() as c:
        assert c.get("/health").status_code == 200
        assert c.get("/settings").status_code == 401
        token = core_auth.read_secret("api_token", sdir)
        assert c.get("/settings", headers=_auth(token)).status_code == 200


def test_only_one_password_check_runs_at_a_time(db, monkeypatch):
    """Codex review P1. A check that passed the throttle used to run scrypt
    before recording its result, so a burst of concurrent logins all passed the
    throttle and each hashed at once — about 32 MiB apiece, reachable without a
    session through the dashboard's login route. A second login that arrives
    while one is hashing is refused at once, without hashing."""
    import threading
    app = _app(db)
    core_auth.set_admin_password(db, PASSWORD)
    inside, release = threading.Event(), threading.Event()
    hashes = []

    def slow_verify(pw, stored):
        hashes.append(pw)
        inside.set()
        release.wait(5)
        return False

    monkeypatch.setattr(api_auth.core_auth, "verify_password", slow_verify)
    first = {}

    def run_first():
        with app.test_client() as c:
            first["r"] = c.post("/auth/login", headers=_auth(), json={"password": "one one one"})

    t = threading.Thread(target=run_first)
    t.start()
    assert inside.wait(5)
    with app.test_client() as c:
        second = c.post("/auth/login", headers=_auth(), json={"password": "two two two"})
    release.set()
    t.join(5)

    assert second.status_code == 429
    assert second.headers["Retry-After"] == "1"
    assert hashes == ["one one one"]
    assert first["r"].status_code == 401


def test_the_check_slot_is_released_even_when_hashing_raises(db, monkeypatch):
    app = _app(db)
    core_auth.set_admin_password(db, PASSWORD)

    def boom(*a):
        raise MemoryError("scrypt")

    monkeypatch.setattr(api_auth.core_auth, "verify_password", boom)
    with app.test_client() as c:
        with pytest.raises(MemoryError):
            c.post("/auth/login", headers=_auth(), json={"password": "x x x x"})
    monkeypatch.undo()
    os.environ["TUBEMATIC_DB"] = str(db)
    with app.test_client() as c:
        assert c.post("/auth/login", headers=_auth(), json={"password": PASSWORD}).status_code == 200
