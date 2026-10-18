"""Per-voice ElevenLabs models over HTTP (TMDEV-121).

The model follows the voice, so the voice decides which pronunciation and
pause markup a script may carry. Three things here:

- A voice change the script cannot use is refused with 409 at the checkpoint,
  before VOICING — the alternative is a paid voicing that reads IPA aloud or
  drops a pronunciation. The negative control matters as much: approving
  with the video's own voice must NEVER be refused, or every approval breaks.
- The video payload carries voice_conflicts, computed by the same function the
  refusal uses, so the dashboard's grey-out and the 409 cannot disagree.
- A project's default voice seeds every video filed into it, on every creation
  path, and a later change to that default never reaches back.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint

V2 = {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"}
V3 = {"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"}
FLASH = {"name": "Bella", "voice_id": "b1", "model_id": "eleven_flash_v2"}


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
        c.post("/settings", json={"elevenlabs_voices": [V2, V3, FLASH],
                                  "elevenlabs_voice_id": "r1"})
        yield c


def _scripted(db_path, vid="vid-1", voice_id="", voice_text="Plain words.",
              status="SCRIPT_READY", script=None):
    con = sqlite3.connect(db_path)
    segs = None if script is not None else json.dumps([{"voice": voice_text, "visual": ""}])
    con.execute(
        "INSERT INTO videos (id, topic, strategy, producibility_score, status, video_version, "
        "voice_id, script, script_segments, created_at, updated_at) "
        "VALUES (?, 't', 'manual', 5, ?, 1, ?, ?, ?, '2026-01-01', '2026-01-01')",
        (vid, status, voice_id, script if script is not None else "Plain words.", segs))
    con.commit()
    con.close()
    return vid


def _voice(db_path, vid="vid-1"):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT voice_id, status FROM videos WHERE id = ?", (vid,)).fetchone()
    con.close()
    return row


IPA = 'Say <ipa ph="ˈmædɪsən">Madison</ipa> now.'


# ── the refusal ──────────────────────────────────────────────────────────────

def test_approving_with_an_incompatible_voice_is_refused_and_nothing_changes(client, db_path):
    _scripted(db_path, voice_id="a1", voice_text=IPA)
    r = client.patch("/videos/vid-1", json={"status": "VOICING", "voice_id": "r1",
                                            "onlyIfCurrentStatus": "SCRIPT_READY"})
    assert r.status_code == 409
    body = json.loads(r.data)
    assert body["voice_conflict"] is True and "<ipa>" in body["error"] and "Rachel" in body["error"]
    assert _voice(db_path) == ("a1", "SCRIPT_READY")


def test_approving_with_the_videos_own_voice_is_never_refused(client, db_path):
    """The negative control: a script is compatible with its own voice by
    construction, so the ordinary approval must go straight through."""
    _scripted(db_path, voice_id="a1", voice_text=IPA)
    r = client.patch("/videos/vid-1", json={"status": "VOICING", "voice_id": "a1",
                                            "onlyIfCurrentStatus": "SCRIPT_READY"})
    assert r.status_code == 200
    assert _voice(db_path) == ("a1", "VOICING")


def test_a_compatible_switch_passes(client, db_path):
    _scripted(db_path, voice_id="r1", voice_text='A <break time="0.5s" /> B.')
    r = client.patch("/videos/vid-1", json={"voice_id": "b1"})
    assert r.status_code == 200
    assert _voice(db_path)[0] == "b1"


def test_clearing_to_the_install_default_is_checked_against_that_voice(client, db_path):
    _scripted(db_path, voice_id="a1", voice_text="First. [pause] Second.")
    r = client.patch("/videos/vid-1", json={"voice_id": ""})
    assert r.status_code == 409  # the install default is Rachel, on v2


def test_losing_phoneme_tags_is_refused(client, db_path):
    _scripted(db_path, voice_id="b1",
              voice_text='Say <phoneme alphabet="ipa" ph="x">word</phoneme>.')
    assert client.patch("/videos/vid-1", json={"voice_id": "r1"}).status_code == 409


def test_a_voice_whose_model_was_edited_after_scripting_is_refused_at_approval(client, db_path):
    """The one case the pin cannot prevent: someone moves the video's own
    voice to another model in Settings. Caught at the checkpoint, not at a
    paid VOICING."""
    _scripted(db_path, voice_id="a1", voice_text=IPA)
    client.post("/settings", json={"elevenlabs_voices": [
        V2, {**V3, "model_id": "eleven_multilingual_v2"}, FLASH]})
    r = client.patch("/videos/vid-1", json={"status": "VOICING", "voice_id": "a1"})
    assert r.status_code == 409


def test_phoneme_tags_after_the_voices_own_model_was_edited_are_refused(client, db_path):
    """The voice keeps its id but its model moves off phoneme support in
    Settings: approving with it must be refused, not voiced with the tags
    stripped."""
    _scripted(db_path, voice_id="b1",
              voice_text='Say <phoneme alphabet="ipa" ph="x">word</phoneme>.')
    client.post("/settings", json={"elevenlabs_voices": [
        V2, V3, {**FLASH, "model_id": "eleven_multilingual_v2"}]})
    r = client.patch("/videos/vid-1", json={"status": "VOICING", "voice_id": "b1"})
    assert r.status_code == 409


def test_an_unscripted_video_takes_any_voice(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO videos (id, topic, strategy, producibility_score, status, "
                "video_version, created_at, updated_at) VALUES "
                "('t1', 't', 'manual', 5, 'TOPIC_PROPOSED', 1, '2026', '2026')")
    con.commit()
    con.close()
    assert client.patch("/videos/t1", json={"voice_id": "a1"}).status_code == 200


def test_a_legacy_flat_script_counts_only_ipa(client, db_path):
    _scripted(db_path, voice_id="r1", script='A <break time="1s" /> B [pause] C')
    assert client.patch("/videos/vid-1", json={"voice_id": "a1"}).status_code == 200


# ── TOPIC_PROPOSED waives the check (TMDEV-127) ─────────────────────────────
# A topic revision can send a scripted video back to TOPIC_PROPOSED with its
# old script still stored. Approving the topic has that script rewritten for
# the voice picked now, so refusing a voice over it would block the checkpoint
# where a voice on another model is supposed to be chosen.

def test_a_stale_script_at_topic_proposed_blocks_no_voice(client, db_path):
    _scripted(db_path, voice_id="r1", voice_text='A <break time="0.5s" /> B.',
              status="TOPIC_PROPOSED")
    v = json.loads(client.get("/videos/vid-1").data)
    assert v["voice_conflicts"] == {}
    r = client.patch("/videos/vid-1", json={"status": "TOPIC_APPROVED", "voice_id": "a1",
                                            "onlyIfCurrentStatus": "TOPIC_PROPOSED"})
    assert r.status_code == 200
    assert _voice(db_path) == ("a1", "TOPIC_APPROVED")


def test_the_same_stale_script_still_blocks_it_at_script_ready(client, db_path):
    """The waiver is the status, not the script: the identical row one
    checkpoint later is refused as before."""
    _scripted(db_path, voice_id="r1", voice_text='A <break time="0.5s" /> B.')
    assert set(json.loads(client.get("/videos/vid-1").data)["voice_conflicts"]) == {"a1"}
    assert client.patch("/videos/vid-1", json={"voice_id": "a1"}).status_code == 409


def test_a_waived_voice_write_is_bound_to_topic_proposed(client, db_path, monkeypatch):
    """The check was waived because of the status, so a write landing after the
    video moved on (here: an agent finishing the script mid-request) must match
    no row rather than put the voice under a script it cannot speak."""
    _scripted(db_path, voice_id="r1", voice_text='A <break time="0.5s" /> B.',
              status="TOPIC_PROPOSED")
    real = pipeline._voice_state

    def moved_on(video, settings):
        result = real(video, settings)
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET status = 'SCRIPT_READY' WHERE id = 'vid-1'")
        con.commit()
        con.close()
        return result

    monkeypatch.setattr(pipeline, "_voice_state", moved_on)
    r = client.patch("/videos/vid-1", json={"voice_id": "a1"})
    assert r.status_code == 409
    assert _voice(db_path) == ("r1", "SCRIPT_READY")


# ── the payload ──────────────────────────────────────────────────────────────

def test_the_payload_names_every_conflicting_voice(client, db_path):
    _scripted(db_path, voice_id="a1", voice_text=IPA)
    v = json.loads(client.get("/videos/vid-1").data)
    assert v["effective_voice_id"] == "a1"
    assert set(v["voice_conflicts"]) == {"r1", "b1"}
    listed = json.loads(client.get("/videos").data)[0]
    assert set(listed["voice_conflicts"]) == {"r1", "b1"}


def test_the_payload_resolves_an_empty_voice_to_the_install_default(client, db_path):
    _scripted(db_path)
    v = json.loads(client.get("/videos/vid-1").data)
    assert v["effective_voice_id"] == "r1" and v["voice_conflicts"] == {}


# ── project default voice ────────────────────────────────────────────────────

def _project(client, pid="p1", **extra):
    return client.post("/projects", json={"id": pid, "name": "P", **extra})


def test_a_project_stores_its_default_voice(client):
    r = _project(client, default_voice_id="a1")
    assert r.status_code == 201 and json.loads(r.data)["default_voice_id"] == "a1"


def test_a_project_default_voice_off_the_roster_is_refused(client):
    assert _project(client, default_voice_id="ghost").status_code == 400


def test_a_kept_default_voice_that_left_the_roster_does_not_block_other_edits(client):
    """POST /projects is a full replace, so every edit re-sends the stored
    default. Refusing a re-sent stale one would lock the domain."""
    _project(client, default_voice_id="a1")
    client.post("/settings", json={"elevenlabs_voices": [V2]})
    r = _project(client, description="edited", default_voice_id="a1")
    assert r.status_code == 201


def test_omitting_the_default_voice_clears_it(client):
    _project(client, default_voice_id="a1")
    assert json.loads(_project(client).data)["default_voice_id"] == ""


@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining", "manual"])
def test_every_strategy_inherits_the_project_voice(client, strategy):
    _project(client, default_voice_id="a1")
    r = client.post("/videos", json={"topic": "x", "strategy": strategy,
                                     "producibility_score": 7, "project_id": "p1"})
    assert json.loads(r.data)["voice_id"] == "a1"


def test_an_explicit_voice_beats_the_project_default(client):
    _project(client, default_voice_id="a1")
    r = client.post("/videos", json={"topic": "x", "strategy": "trending",
                                     "producibility_score": 7, "project_id": "p1",
                                     "voice_id": "b1"})
    assert json.loads(r.data)["voice_id"] == "b1"


def test_a_stale_project_default_is_not_seeded(client):
    _project(client, default_voice_id="a1")
    client.post("/settings", json={"elevenlabs_voices": [V2]})
    r = client.post("/videos", json={"topic": "x", "strategy": "trending",
                                     "producibility_score": 7, "project_id": "p1"})
    assert json.loads(r.data)["voice_id"] == ""


def test_changing_a_project_default_never_reaches_back(client, db_path):
    _project(client, default_voice_id="a1")
    vid = json.loads(client.post("/videos", json={
        "topic": "x", "strategy": "trending", "producibility_score": 7,
        "project_id": "p1"}).data)["id"]
    _project(client, default_voice_id="b1")
    assert _voice(db_path, vid)[0] == "a1"


def test_a_manual_submission_inherits_the_manual_domains_voice(client):
    r = client.post("/videos/manual", json={"title": "T", "topic": "x"})
    assert json.loads(r.data)["voice_id"] == ""  # the domain has no default yet
    _project(client, pid=pipeline.MANUAL_PROJECT_ID, default_voice_id="b1")
    r = client.post("/videos/manual", json={"title": "T2", "topic": "y"})
    assert json.loads(r.data)["voice_id"] == "b1"
    r = client.post("/videos/manual", json={"title": "T3", "topic": "z", "voice_id": "a1"})
    assert json.loads(r.data)["voice_id"] == "a1"
