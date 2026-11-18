"""External styles through the HTTP API (TMDEV-252): an installed package is a
style a person can choose for a video or a domain, a broken one is refused, and
the Auto opt-in setting names installed styles only.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint
from tubematic_core import external_styles as ext
from tubematic_core import visual_styles as tvs


def _package(root, sid, ok=True):
    d = root / sid
    (d / "guide").mkdir(parents=True)
    (d / "components").mkdir()
    p = json.loads((tvs.PACKS_DIR / "night_signal.json").read_text())
    p.pop("extra", None)
    p.update(id=sid, label=f"Test {sid}", order=9000, inserts={"host": False},
             authoring_skill=ext.AUTHORING_SKILL, preview=sid,
             external={"version": "1", "author": "a", "source": "s", "licence": "MIT",
                       "scene_api": ext.SCENE_API, "props_key": "testStyle"})
    p["messages"] = dict(p["messages"], inserts="No inserts.")
    (d / "style.json").write_text(json.dumps(p))
    for name, body in (("schema.json", "{}"), ("guide/guide.md", "#"), ("guide/example-config.json", "{}"),
                       ("components/Main.tsx", "export default () => null;"),
                       ("preview.mp4", "x"), ("preview.webp", "x")):
        (d / name).write_text(body)
    if ok:
        ext.write_manifest(d)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    styles = tmp_path / "styles"
    styles.mkdir()
    _package(styles, "ext_good")
    _package(styles, "ext_broken", ok=False)
    monkeypatch.setattr(ext, "STYLES_DIR", styles)
    db = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = db
    pipeline._init_db(db)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _video(client, **extra):
    body = {"topic": "a topic", "strategy": "manual", "producibility_score": 7, **extra}
    return json.loads(client.post("/videos", json=body).data)["id"]


def test_an_installed_style_can_be_chosen_for_a_video(client):
    vid = _video(client)
    assert client.patch(f"/videos/{vid}", json={"visual_style": "ext_good"}).status_code == 200
    assert client.get(f"/videos/{vid}").get_json()["visual_style"] == "ext_good"


def test_a_broken_package_cannot_be_chosen(client):
    vid = _video(client)
    r = client.patch(f"/videos/{vid}", json={"visual_style": "ext_broken"})
    assert r.status_code == 400 and "Invalid visual_style" in r.get_json()["error"]
    assert client.post("/videos", json={"topic": "t", "strategy": "manual", "producibility_score": 7,
                                        "visual_style": "ext_broken"}).status_code == 400


def test_an_installed_style_can_be_a_domain_default_and_seeds_curriculum(client):
    r = client.post("/projects", json={"id": "d1", "name": "D", "default_visual_style": "ext_good"})
    assert r.status_code == 201
    vid = _video(client, project_id="d1", strategy="curriculum")
    assert client.get(f"/videos/{vid}").get_json()["visual_style"] == "ext_good"
    r = client.post("/projects", json={"id": "d2", "name": "D", "default_visual_style": "ext_broken"})
    assert r.status_code == 400


def test_the_style_list_carries_installed_styles(client):
    by_id = {r["id"]: r for r in client.get("/visual-styles").get_json()["styles"]}
    assert by_id["ext_good"]["external"] and by_id["ext_good"]["available"]
    assert not by_id["ext_broken"]["available"]


def test_the_auto_opt_in_names_installed_styles_only(client):
    r = client.post("/settings", json={"external_styles_in_auto": ["ext_good"]})
    assert r.status_code == 200, r.get_json()
    assert client.get("/settings").get_json()["external_styles_in_auto"] == ["ext_good"]
    for bad in (["ext_broken"], ["night_signal"], ["ext_absent"]):
        r = client.post("/settings", json={"external_styles_in_auto": bad})
        assert r.status_code == 400 and bad[0] in r.get_json()["error"]


def test_an_unchanged_opt_in_list_saves_after_its_style_breaks(client, monkeypatch, tmp_path):
    """Checked on change only, like the research agent: a package that broke
    since must not block an unrelated save."""
    assert client.post("/settings", json={"external_styles_in_auto": ["ext_good"]}).status_code == 200
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path / "empty")
    assert client.post("/settings", json={"external_styles_in_auto": ["ext_good"],
                                          "pipeline_paused": True}).status_code == 200
