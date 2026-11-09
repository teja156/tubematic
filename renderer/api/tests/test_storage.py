"""GET /storage: the dashboard's disk-usage figures (TMDEV-192).

The API measures the data folders itself and adds the host's snapshot for
what no container can see (images, container layers, the install folder).
The rules pinned here: each data line is measured once (voice previews and
mascot sheets are split out of their parents, never counted twice); a missing
or garbled snapshot leaves the host half null rather than zero; only the
host figures that are real sizes reach the total, and the machine-wide build
cache never does; and the walk is cached.

Run from renderer/api/: pytest tests/test_storage.py
"""
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline

MB = 1_000_000


def _write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    db = str(data / "tubematic.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    backups = tmp_path / "backups"
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(backups))
    dirs = {name: tmp_path / name for name in ("output_videos", "jobs", "logs", "remotion")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", dirs["output_videos"])
    monkeypatch.setattr(pipeline, "JOBS_DIR", dirs["jobs"])
    monkeypatch.setattr(pipeline, "LOG_DIR", dirs["logs"])
    monkeypatch.setattr(pipeline, "REMOTION_DIR", dirs["remotion"])
    pipeline._init_db(db)
    pipeline._reset_storage_cache()
    yield SimpleNamespace(db=db, data=data, backups=backups, **dirs)
    pipeline._reset_storage_cache()


@pytest.fixture
def client(env):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(pipeline.create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _items(body):
    return {i["key"]: i["bytes"] for i in body["data"]["items"]}


def _snapshot(env, **fields):
    doc = {"measured_at": "2026-11-09T10:00:00Z", "images": {
        "current_bytes": 5000 * MB, "old_bytes": 1200 * MB, "old_count": 2},
        "containers_bytes": 30 * MB, "build_cache_bytes": 900 * MB,
        "install_bytes": 400 * MB}
    doc.update(fields)
    (env.data / "disk-usage.json").write_text(json.dumps(doc))
    return doc


def test_every_data_line_is_reported_in_order(client):
    body = client.get("/storage").get_json()
    assert [i["key"] for i in body["data"]["items"]] == [
        "videos", "voice_previews", "jobs", "scenes", "database", "mascots",
        "backups", "logs"]
    assert body["data"]["measured_at"].endswith("Z")


def test_each_folder_lands_on_its_own_line(client, env):
    _write(env.output_videos / "proj" / "vid.mp4", 3 * MB)
    _write(env.output_videos / "voice-previews" / "a.mp3", 1 * MB)
    _write(env.jobs / "vid_1" / "audio.mp3", 2 * MB)
    _write(env.remotion / "src" / "scenes" / "generated" / "vid_1" / "S.tsx", 1 * MB)
    _write(env.data / "mascots" / "pip" / "v1" / "front.png", 4 * MB)
    _write(env.backups / "tubematic-1.db", 5 * MB)
    _write(env.logs / "api.jsonl", 6 * MB)
    items = _items(client.get("/storage").get_json())
    # du-style blocks: at least the bytes, at most a few blocks over
    for key, size in [("videos", 3), ("voice_previews", 1), ("jobs", 2), ("scenes", 1),
                      ("mascots", 4), ("backups", 5), ("logs", 6)]:
        assert size * MB <= items[key] < size * MB + 64_000, key


def test_previews_and_mascots_are_not_counted_twice(client, env):
    _write(env.output_videos / "voice-previews" / "a.mp3", 8 * MB)
    _write(env.data / "mascots" / "pip" / "v1" / "front.png", 8 * MB)
    items = _items(client.get("/storage").get_json())
    assert items["videos"] < 1 * MB
    assert items["database"] < 2 * MB  # the sqlite file only


def test_the_snapshot_itself_is_not_counted_as_database(client, env):
    _snapshot(env, padding="x" * (3 * MB))
    assert _items(client.get("/storage").get_json())["database"] < 2 * MB


def test_total_is_the_data_lines_alone_without_a_snapshot(client, env):
    _write(env.jobs / "vid_1" / "a.bin", 2 * MB)
    body = client.get("/storage").get_json()
    assert body["host"] is None
    assert body["total_bytes"] == body["data"]["total_bytes"] == sum(_items(body).values())


def test_snapshot_figures_reach_the_total_but_build_cache_does_not(client, env):
    _snapshot(env)
    body = client.get("/storage").get_json()
    assert body["host"]["install_bytes"] == 400 * MB
    assert body["total_bytes"] == body["data"]["total_bytes"] + (5000 + 1200 + 30 + 400) * MB


def test_unknown_host_figures_add_nothing(client, env):
    _snapshot(env, images=None, containers_bytes=None, build_cache_bytes=None)
    body = client.get("/storage").get_json()
    assert body["host"]["images"] is None
    assert body["total_bytes"] == body["data"]["total_bytes"] + 400 * MB


@pytest.mark.parametrize("bad", [True, -5, "12", 1.5])
def test_a_figure_that_is_not_a_size_adds_nothing(client, env, bad):
    _snapshot(env, install_bytes=bad, containers_bytes=None,
              images={"current_bytes": None, "old_bytes": None, "old_count": 0})
    body = client.get("/storage").get_json()
    assert body["total_bytes"] == body["data"]["total_bytes"]


@pytest.mark.parametrize("raw", ["", "{not json", "[]", '{"install_bytes": 1}'])
def test_a_garbled_snapshot_reads_as_not_measured(client, env, raw):
    (env.data / "disk-usage.json").write_text(raw)
    body = client.get("/storage").get_json()
    assert body["host"] is None
    assert body["total_bytes"] == body["data"]["total_bytes"]


def test_the_walk_is_cached_but_the_snapshot_is_read_fresh(client, env, monkeypatch):
    first = _items(client.get("/storage").get_json())
    _write(env.jobs / "vid_2" / "big.bin", 5 * MB)
    _snapshot(env)
    body = client.get("/storage").get_json()
    assert _items(body) == first          # cached walk
    assert body["host"] is not None       # snapshot is not cached
    monkeypatch.setattr(pipeline, "STORAGE_CACHE_SECS", 0)
    assert _items(client.get("/storage").get_json())["jobs"] >= 5 * MB


def test_missing_folders_measure_zero_not_an_error(client, env):
    import shutil
    shutil.rmtree(env.logs)
    assert client.get("/storage").status_code == 200
    assert _items(client.get("/storage").get_json())["logs"] == 0
