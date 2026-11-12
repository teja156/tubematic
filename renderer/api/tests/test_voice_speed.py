"""Per-voice speed on the roster and in previews (TMDEV-216, TMDEV-227).

ElevenLabs ignores voice_settings.speed on eleven_v3 and eleven_v4 without an
error (probed with paid calls). Since TMDEV-227 a speed there is a
pitch-keeping stretch of the recording instead of a refusal, and a native
model past its 1.2 maximum is stretched for the rest. A speed of 1.0 is never
stored, so a roster nobody gave a speed keeps the exact shape older versions
read, and a preview at 1.0 keeps the cache key every earlier preview was
stored under.
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
def test_a_speed_on_a_v3_or_v4_voice_is_saved(client, model):
    roster = [{**_roster(speed=1.1)[0], "model_id": model}]
    r = client.post("/settings", json={"elevenlabs_voices": roster})
    assert r.status_code == 200
    assert _stored(client) == roster


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


@pytest.fixture
def stretched(monkeypatch):
    """ffmpeg present and the stretch recorded instead of run (the host has no
    ffmpeg; tubematic_core/tests/test_audio_speed.py runs the real one)."""
    calls = []
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)

    def fake(ffmpeg, mp3, factor):
        calls.append(factor)
        return b"stretched:" + mp3, 1.0
    monkeypatch.setattr(pipeline.taudio, "stretch", fake)
    return calls


def test_a_v4_preview_at_a_speed_records_at_one_and_stretches(client, preview_env, stretched):
    client.post("/settings", json={"elevenlabs_voices": _roster()})
    r, sent = _preview(client, json={"model_id": "eleven_v4", "speed": 1.1})
    assert r.status_code == 200 and "speed" not in sent["voice_settings"]
    assert stretched == [1.1]
    path = preview_env / "voice-previews" / json.loads(r.data)["path"].rsplit("/", 1)[1]
    assert path.read_bytes() == b"stretched:fake-mp3-bytes"


def test_a_stored_speed_on_v4_is_used_by_its_preview(client, preview_env, stretched):
    client.post("/settings", json={"elevenlabs_voices": [{**_roster(speed=1.15)[0], "model_id": "eleven_v4"}]})
    r, sent = _preview(client)
    assert r.status_code == 200 and "speed" not in sent["voice_settings"] and stretched == [1.15]


def test_a_native_preview_needs_no_stretch(client, preview_env, stretched):
    client.post("/settings", json={"elevenlabs_voices": _roster(speed=1.15)})
    r, sent = _preview(client)
    assert sent["voice_settings"]["speed"] == 1.15 and stretched == []


def test_a_preview_that_needs_a_stretch_without_ffmpeg_is_refused_before_spend(client, preview_env, monkeypatch):
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)
    client.post("/settings", json={"elevenlabs_voices": _roster()})
    r, sent = _preview(client, json={"model_id": "eleven_v4", "speed": 1.1})
    assert r.status_code == 503 and "ffmpeg" in json.loads(r.data)["error"] and sent is None


# ── a video's own speed (TMDEV-227) ──────────────────────────────────────────

def _video(db_path, vid="vid-1", status="SCRIPT_READY", voice_id="abc123", speed=None):
    import sqlite3
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, strategy, producibility_score, status, video_version, "
        "voice_id, voice_speed, script, created_at, updated_at) "
        "VALUES (?, 't', 'manual', 5, ?, 1, ?, ?, 'Plain words.', '2026-01-01', '2026-01-01')",
        (vid, status, voice_id, speed))
    con.commit()
    con.close()


def _get(client, vid="vid-1"):
    return json.loads(client.get(f"/videos/{vid}").data)


def test_a_person_sets_the_speed_at_script_ready(client, db_path):
    client.post("/settings", json={"elevenlabs_voices": _roster(speed=1.05)})
    _video(db_path)
    v = _get(client)
    assert v["voice_speed"] is None
    assert v["voice_info"]["speed"] == 1.05 and v["voice_info"]["roster_speed"] == 1.05
    r = client.patch("/videos/vid-1", json={"voice_speed": 1.15})
    assert r.status_code == 200
    v = _get(client)
    assert v["voice_speed"] == 1.15 and v["voice_info"]["speed"] == 1.15


def test_null_gives_the_speed_back_to_the_voice(client, db_path):
    _video(db_path, speed=1.2)
    assert client.patch("/videos/vid-1", json={"voice_speed": None}).status_code == 200
    v = _get(client)
    assert v["voice_speed"] is None and v["voice_info"]["speed"] == 1.0


def test_the_approval_can_carry_the_speed(client, db_path):
    _video(db_path)
    r = client.patch("/videos/vid-1", json={"status": "VOICING", "voice_speed": 0.95})
    assert r.status_code == 200
    v = _get(client)
    assert v["status"] == "VOICING" and v["voice_speed"] == 0.95


@pytest.mark.parametrize("speed", [0.85, 1.3, 1.12, "1.1", True])
def test_a_speed_out_of_range_is_refused(client, db_path, speed):
    _video(db_path)
    r = client.patch("/videos/vid-1", json={"voice_speed": speed})
    assert r.status_code == 400 and "voice_speed" in json.loads(r.data)["error"]
    assert _get(client)["voice_speed"] is None


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "TOPIC_APPROVED", "VOICING", "VOICE_READY", "VIDEO_READY"])
def test_the_speed_is_the_person_s_only_at_script_ready(client, db_path, status):
    _video(db_path, status=status)
    r = client.patch("/videos/vid-1", json={"voice_speed": 1.1})
    assert r.status_code == 409 and "SCRIPT_READY" in json.loads(r.data)["error"]
    assert _get(client)["voice_speed"] is None


def test_the_speed_write_is_bound_to_script_ready(client, db_path, monkeypatch):
    """A status change between the check and the UPDATE must not let the speed
    land after voicing has begun."""
    import sqlite3
    from tests.test_pipeline import _RacingConn
    _video(db_path)
    real_connect = sqlite3.connect
    state = {"wrapped": False}

    def _connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        if not state["wrapped"]:
            state["wrapped"] = True
            return _RacingConn(con, "SELECT status, archived_at FROM videos", db_path,
                               "UPDATE videos SET status = 'VOICING' WHERE id = ?", ("vid-1",))
        return con
    monkeypatch.setattr(sqlite3, "connect", _connect)
    r = client.patch("/videos/vid-1", json={"voice_speed": 1.1})
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    assert r.status_code == 409
    assert _get(client)["voice_speed"] is None
