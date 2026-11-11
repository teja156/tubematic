"""Per-voice speed on the roster and in previews (TMDEV-216).

ElevenLabs ignores voice_settings.speed on eleven_v3 and eleven_v4 without an
error (probed with paid calls), so the API refuses a speed there: a stored
speed must always change the audio. A speed of 1.0 is never stored, so a
roster nobody gave a speed keeps the exact shape older versions read, and a
preview at 1.0 keeps the cache key every earlier preview was stored under.
"""
import hashlib
import json
import os
import unittest.mock as mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = p
    pipeline._init_db(p)
    return p


@pytest.fixture
def client(db_path):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _mock_elevenlabs_response():
    resp = mock.MagicMock()
    resp.status_code = 200
    resp.content = b"fake-mp3-bytes"
    resp.text = ""
    resp.headers = {"character-cost": "117", "request-id": "req-1"}
    return resp


def _roster(**extra):
    return [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2", **extra}]


def _stored(client):
    return json.loads(client.get("/settings").data)["elevenlabs_voices"]


def test_a_speed_on_a_v2_voice_is_saved(client):
    r = client.post("/settings", json={"elevenlabs_voices": _roster(speed=1.15)})
    assert r.status_code == 200
    assert _stored(client) == _roster(speed=1.15)


def test_a_speed_of_one_is_never_stored(client):
    client.post("/settings", json={"elevenlabs_voices": _roster(speed=1.0)})
    assert _stored(client) == _roster()


def test_a_roster_without_speed_round_trips_unchanged(client):
    """What keeps a rollback safe: older readers drop a roster with any key
    they do not know, so an install that never set a speed must not gain one."""
    client.post("/settings", json={"elevenlabs_voices": _roster()})
    assert _stored(client) == _roster()


@pytest.mark.parametrize("model", ["eleven_v3", "eleven_v4"])
def test_a_speed_on_a_v3_or_v4_voice_is_refused(client, model):
    r = client.post("/settings", json={"elevenlabs_voices": [{**_roster(speed=1.1)[0], "model_id": model}]})
    assert r.status_code == 400
    assert "ignores speed" in json.loads(r.data)["error"]


@pytest.mark.parametrize("speed", [0.6, 1.3, 1.13, "fast", None])
def test_a_bad_speed_is_refused(client, speed):
    r = client.post("/settings", json={"elevenlabs_voices": _roster(speed=speed)})
    assert r.status_code == 400


def _preview(client, **kwargs):
    with mock.patch("httpx.Client") as cls:
        post = cls.return_value.__enter__.return_value.post
        post.return_value = _mock_elevenlabs_response()
        r = client.post("/voices/abc123/preview", **kwargs)
    sent = post.call_args.kwargs["json"] if post.called else None
    return r, sent


@pytest.fixture
def preview_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    return tmp_path


def test_a_preview_at_one_sends_no_speed_and_keeps_the_old_cache_key(client, preview_env):
    client.post("/settings", json={"elevenlabs_voices": _roster()})
    r, sent = _preview(client)
    assert r.status_code == 200 and "speed" not in sent["voice_settings"]
    old_key = hashlib.sha256(
        f"abc123|eleven_multilingual_v2|{pipeline.VOICE_PREVIEW_SAMPLE_TEXT}".encode()
    ).hexdigest()[:16]
    assert json.loads(r.data)["path"].endswith(f"/{old_key}.mp3")


def test_a_preview_uses_the_voices_stored_speed(client, preview_env):
    client.post("/settings", json={"elevenlabs_voices": _roster(speed=1.15)})
    r, sent = _preview(client)
    assert r.status_code == 200 and sent["voice_settings"]["speed"] == 1.15


def test_a_changed_speed_makes_a_new_preview(client, preview_env):
    client.post("/settings", json={"elevenlabs_voices": _roster()})
    r1, _ = _preview(client)
    r2, sent = _preview(client, json={"speed": 1.1})
    assert sent["voice_settings"]["speed"] == 1.1
    assert json.loads(r1.data)["path"] != json.loads(r2.data)["path"]
    assert json.loads(r2.data)["cached"] is False


def test_a_preview_speed_on_a_model_that_ignores_it_is_refused_before_spend(client, preview_env):
    client.post("/settings", json={"elevenlabs_voices": _roster()})
    r, sent = _preview(client, json={"model_id": "eleven_v4", "speed": 1.1})
    assert r.status_code == 400 and sent is None


def test_a_stored_speed_is_dropped_when_previewing_a_model_that_ignores_it(client, preview_env):
    """Settings previews a model change before it is saved; a speed the new
    model would ignore is not sent with it."""
    client.post("/settings", json={"elevenlabs_voices": _roster(speed=1.15)})
    r, sent = _preview(client, json={"model_id": "eleven_v4"})
    assert r.status_code == 200 and "speed" not in sent["voice_settings"]
