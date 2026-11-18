"""Installing, reviewing and removing external styles through the API (TMDEV-253).

The trap this suite guards: the dashboard relays every request with the same
API token an agent on the host can read, so the token alone must never be able
to install a style. Confirming needs the dashboard password.

Run from repo root: pytest renderer/api/tests/
"""
import base64
import hashlib
import io
import json
import os
import zipfile

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from api_auth import LoginThrottle, create_auth_blueprint
from pipeline import create_pipeline_blueprint
from styles_api import create_styles_blueprint
from tubematic_core import auth as core_auth
from tubematic_core import external_styles as ext
from tubematic_core import style_install as si
from tubematic_core.tests.test_external_styles import make_package

PASSWORD = "correct horse battery staple"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    styles, pending, src = tmp_path / "styles", tmp_path / "pending", tmp_path / "src"
    for d in (styles, pending, src):
        d.mkdir()
    monkeypatch.setattr(ext, "STYLES_DIR", styles)
    monkeypatch.setattr(si, "PENDING_DIR", pending)
    db = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = db
    pipeline._init_db(db)
    core_auth.set_admin_password(db, PASSWORD)
    from flask import Flask
    app = Flask(__name__)
    throttle = LoginThrottle()
    app.register_blueprint(create_pipeline_blueprint())
    app.register_blueprint(create_auth_blueprint(db, throttle))
    app.register_blueprint(create_styles_blueprint(db, throttle))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield type("Env", (), {"client": c, "styles": styles, "src": src, "db": db, "throttle": throttle})


def _zip_b64(d):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(d).as_posix())
    return base64.b64encode(buf.getvalue()).decode()


def _stage(env, sid="ext_test"):
    pkg = make_package(env.src, sid=sid, approve=False)
    r = env.client.post("/external-styles/pending", json={"kind": "zip", "filename": f"{sid}.zip",
                                                         "data": _zip_b64(pkg)})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_staging_a_zip_shows_the_scan_and_installs_nothing(env):
    rec = _stage(env)
    assert rec["style_id"] == "ext_test" and rec["check"]["ok"] and rec["scan"]["refusals"] == []
    got = env.client.get(f"/external-styles/pending/{rec['id']}").get_json()
    assert got["in_use"] == {"videos": [], "domains": []}
    assert env.client.get(f"/external-styles/pending/{rec['id']}/file?path=components/Main.tsx").get_json()["text"]
    assert env.client.get(f"/external-styles/pending/{rec['id']}/file?path=../x").status_code == 404
    assert not (env.styles / "ext_test").exists()
    listing = env.client.get("/external-styles").get_json()
    assert [p["id"] for p in listing["pending"]] == [rec["id"]] and listing["styles"] == []


def test_confirm_needs_the_dashboard_password_and_the_token_alone_cannot_install(env):
    rec = _stage(env)
    url = f"/external-styles/pending/{rec['id']}/confirm"
    assert env.client.post(url, json={}).status_code == 401
    assert env.client.post(url, json={"password": "wrong"}).status_code == 401
    assert not (env.styles / "ext_test").exists()
    r = env.client.post(url, json={"password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    styles = env.client.get("/external-styles").get_json()["styles"]
    assert [(s["id"], s["ok"], s["source"]["kind"], s["reviewed"]) for s in styles] == [
        ("ext_test", True, "zip", False)]
    assert any(s["id"] == "ext_test" and s["available"]
               for s in env.client.get("/visual-styles").get_json()["styles"])


def test_the_confirm_shares_the_logins_throttle(env):
    rec = _stage(env)
    for _ in range(LoginThrottle.FREE_FAILURES):
        env.client.post("/auth/login", json={"password": "wrong"})
    r = env.client.post(f"/external-styles/pending/{rec['id']}/confirm", json={"password": "wrong"})
    r = env.client.post(f"/external-styles/pending/{rec['id']}/confirm", json={"password": PASSWORD})
    assert r.status_code == 429 and not (env.styles / "ext_test").exists()


def test_a_bad_upload_and_an_incoming_source_are_refused(env):
    assert env.client.post("/external-styles/pending", json={"kind": "zip", "data": "@@"}).status_code == 400
    r = env.client.post("/external-styles/pending", json={"kind": "incoming", "name": "x"})
    assert r.status_code == 400 and "MCP" in r.get_json()["error"]
    assert env.client.post("/external-styles/pending", json={"kind": "ftp"}).status_code == 400


def test_discard_removes_a_pending_install(env):
    rec = _stage(env)
    assert env.client.delete(f"/external-styles/pending/{rec['id']}").status_code == 200
    assert env.client.get(f"/external-styles/pending/{rec['id']}").status_code == 404


def test_a_package_copied_in_by_hand_is_listed_for_review_and_approved_through_the_screen(env):
    make_package(env.styles, approve=False)
    row = env.client.get("/external-styles").get_json()["styles"][0]
    assert row["needs_review"] and not row["ok"] and "approved" in row["reason"]
    rec = env.client.post("/external-styles/pending", json={"kind": "installed", "id": "ext_test"}).get_json()
    assert env.client.post(f"/external-styles/pending/{rec['id']}/confirm",
                           json={"password": PASSWORD}).status_code == 200
    assert env.client.get("/external-styles").get_json()["styles"][0]["ok"]


def _install(env, sid="ext_test"):
    rec = _stage(env, sid)
    assert env.client.post(f"/external-styles/pending/{rec['id']}/confirm",
                           json={"password": PASSWORD}).status_code == 200


def test_remove_is_refused_while_a_video_or_domain_uses_the_style(env):
    _install(env)
    vid = env.client.post("/videos", json={"topic": "t", "strategy": "manual", "producibility_score": 7,
                                           "visual_style": "ext_test"}).get_json()["id"]
    r = env.client.delete("/external-styles/ext_test")
    assert r.status_code == 409 and "1 unfinished video" in r.get_json()["error"]
    assert env.client.get("/external-styles").get_json()["styles"][0]["unfinished_videos"] == 1
    with pipeline_conn(env) as con:
        con.execute("UPDATE videos SET status = 'PUBLISHED' WHERE id = ?", (vid,))
        con.execute("INSERT INTO projects (id, name, default_visual_style, created_at) VALUES ('d1', 'Space', 'ext_test', 'x')")
    r = env.client.delete("/external-styles/ext_test")
    assert r.status_code == 409 and "Space" in r.get_json()["error"]
    with pipeline_conn(env) as con:
        con.execute("UPDATE projects SET default_visual_style = 'auto' WHERE id = 'd1'")
    assert env.client.delete("/external-styles/ext_test").status_code == 200
    assert not (env.styles / "ext_test").exists()
    assert env.client.delete("/external-styles/night_signal").status_code == 404


def test_remove_takes_the_style_out_of_auto(env):
    _install(env)
    assert env.client.post("/settings", json={"external_styles_in_auto": ["ext_test"]}).status_code == 200
    assert env.client.get("/external-styles").get_json()["styles"][0]["in_auto"] is True
    assert env.client.delete("/external-styles/ext_test").status_code == 200
    assert env.client.get("/settings").get_json()["external_styles_in_auto"] == []


def pipeline_conn(env):
    import db
    return db.conn(env.db)


def test_the_gallery_lists_the_index_and_marks_installed_versions(env, monkeypatch):
    assert env.client.get("/external-styles/gallery").get_json()["error"] == "No gallery address is set."
    assert env.client.post("/settings", json={"style_gallery_url": "http://g.invalid/i.json"}).status_code == 400
    assert env.client.post("/settings", json={"style_gallery_url": "https://g.invalid/i.json"}).status_code == 200
    _install(env)
    index = {"styles": [{"id": "ext_test", "name": "Test", "version": "2.0.0"}, {"id": "bad id"}]}
    monkeypatch.setattr(si, "_http_get", lambda url, cap: json.dumps(index).encode())
    got = env.client.get("/external-styles/gallery").get_json()
    assert [(s["id"], s["installed_version"]) for s in got["styles"]] == [("ext_test", "1.0.0")]


def test_a_gallery_install_is_marked_reviewed(env, monkeypatch):
    env.client.post("/settings", json={"style_gallery_url": "https://g.invalid/i.json"})
    pkg = make_package(env.src, approve=False)
    data = base64.b64decode(_zip_b64(pkg))
    served = {"https://g.invalid/i.json": json.dumps({"styles": [{
        "id": "ext_test", "archive_url": "https://g.invalid/a.zip", "sha256": hashlib.sha256(data).hexdigest()}]}).encode(),
        "https://g.invalid/a.zip": data}
    monkeypatch.setattr(si, "_http_get", lambda url, cap: served[url])
    rec = env.client.post("/external-styles/pending", json={"kind": "gallery", "id": "ext_test"}).get_json()
    assert rec["reviewed"] is True
    env.client.post(f"/external-styles/pending/{rec['id']}/confirm", json={"password": PASSWORD})
    assert env.client.get("/external-styles").get_json()["styles"][0]["reviewed"] is True
