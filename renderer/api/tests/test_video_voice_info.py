"""The voice and model a single-video payload reports for the modal (TMDEV-147).

The video row keeps only voice_id; the model belongs to the roster voice and
can be edited in Settings after the video was voiced. So the model shown for a
voiced video comes from the usage ledger's last voicing call — the case that
matters most below is a roster edit after voicing, where reading the roster
would name a model the audio was never made with.

The opposite trap: a video sent back before voicing (a revision that may also
change the voice) still holds its old ledger row, and that row must not be
paired with the voice the next voicing will use.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint
from tubematic_core import usage as tusage

V2 = {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"}
V3 = {"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"}


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
        c.post("/settings", json={"elevenlabs_voices": [V2, V3],
                                  "elevenlabs_voice_id": "r1"})
        yield c


def _video(db_path, vid="vid-1", voice_id="a1", status="VIDEO_READY"):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, strategy, producibility_score, status, video_version, "
        "voice_id, script, created_at, updated_at) "
        "VALUES (?, 't', 'manual', 5, ?, 1, ?, 'Plain words.', '2026-01-01', '2026-01-01')",
        (vid, status, voice_id))
    con.commit()
    con.close()


def _voiced_with(db_path, model, vid="vid-1"):
    tusage.record_usage(db_path, service="elevenlabs", model=model, operation="voice",
                        units={"credits": 100}, videos=[vid])


def _info(client, vid="vid-1"):
    return json.loads(client.get(f"/videos/{vid}").data)["voice_info"]


def test_a_voiced_video_reports_the_model_it_was_voiced_with_after_a_roster_edit(client, db_path):
    _video(db_path)
    _voiced_with(db_path, "eleven_v3")
    # The voice's model is edited after voicing; the audio did not change.
    client.post("/settings", json={"elevenlabs_voices": [V2, {**V3, "model_id": "eleven_flash_v2"}]})
    assert _info(client) == {"voice_id": "a1", "name": "Adam",
                             "model_id": "eleven_v3", "model_voiced": True}


def test_the_latest_voicing_wins_after_a_re_voice(client, db_path):
    _video(db_path)
    # The latest is deliberately NOT Adam's roster model, so a fallback to the
    # roster cannot pass this.
    _voiced_with(db_path, "eleven_v3")
    _voiced_with(db_path, "eleven_multilingual_v2")
    assert _info(client)["model_id"] == "eleven_multilingual_v2"


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "TOPIC_APPROVED", "SCRIPT_READY", "VOICING"])
def test_before_voicing_an_old_ledger_row_is_ignored_for_the_current_setting(client, db_path, status):
    # Voiced on Rachel's v2 once, then sent back and switched to Adam: the next
    # voicing uses Adam's model, and the old row must not be shown beside him.
    _video(db_path, status=status)
    _voiced_with(db_path, "eleven_multilingual_v2")
    assert _info(client) == {"voice_id": "a1", "name": "Adam",
                             "model_id": "eleven_v3", "model_voiced": False}


def test_a_video_with_no_ledger_row_shows_the_current_setting(client, db_path):
    _video(db_path)  # voiced before the ledger existed
    info = _info(client)
    assert info["model_id"] == "eleven_v3" and info["model_voiced"] is False


def test_a_voice_off_the_roster_keeps_its_id_and_its_voiced_model(client, db_path):
    _video(db_path, voice_id="gone")
    _voiced_with(db_path, "eleven_v3")
    assert _info(client) == {"voice_id": "gone", "name": "",
                             "model_id": "eleven_v3", "model_voiced": True}


def test_a_voice_off_the_roster_and_never_voiced_has_no_model(client, db_path):
    _video(db_path, voice_id="gone", status="SCRIPT_READY")
    assert _info(client) == {"voice_id": "gone", "name": "", "model_id": "", "model_voiced": False}


def test_a_blank_voice_resolves_to_the_install_default(client, db_path):
    _video(db_path, voice_id="", status="TOPIC_APPROVED")
    assert _info(client) == {"voice_id": "r1", "name": "Rachel",
                             "model_id": "eleven_multilingual_v2", "model_voiced": False}


def test_another_videos_voicing_is_not_this_ones(client, db_path):
    _video(db_path)
    _video(db_path, vid="vid-2")
    _voiced_with(db_path, "eleven_multilingual_v2", vid="vid-2")
    assert _info(client)["model_voiced"] is False


def test_the_list_route_carries_no_voice_info(client, db_path):
    # One ledger query per row would be paid on every board refresh, for a
    # field only the modal shows; the modal fetches the single video.
    _video(db_path)
    assert "voice_info" not in json.loads(client.get("/videos").data)[0]


def test_a_patch_response_carries_voice_info(client, db_path):
    _video(db_path)
    _voiced_with(db_path, "eleven_v3")
    r = client.patch("/videos/vid-1", json={"title": "New title"})
    assert r.status_code == 200
    assert json.loads(r.data)["voice_info"]["model_voiced"] is True
