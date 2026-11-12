"""A voice per script segment on the Flask API (TMDEV-216).

A segment may name its own roster voice; the rest are spoken by the video's
voice. The rules here decide what a person can change on the Script tab and
what approval lets through to a paid voicing:

- The segment_voices PATCH changes only a segment's voice, only at
  SCRIPT_READY, refuses a voice that cannot speak the segment's markup, and
  never overwrites a script written in between (compare-and-swap).
- A change of the VIDEO's voice is checked against the segments it speaks
  only; approval checks every segment against its own voice.
- The negative controls matter as much: a two-voice script whose markup fits
  each voice must approve, or every two-voice video is stuck at Script Ready.

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
V4 = {"name": "Teja", "voice_id": "t1", "model_id": "eleven_v4"}
V2B = {"name": "Bella", "voice_id": "b1", "model_id": "eleven_flash_v2_5"}

BREAK = 'Wait <break time="0.4s" /> what.'      # v2 markup
PAUSE = "So [pause] here it is."                 # v3/v4 markup


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
        c.post("/settings", json={"elevenlabs_voices": [V2, V4, V2B],
                                  "elevenlabs_voice_id": "t1"})
        yield c


def _scripted(db_path, segments, vid="vid-1", voice_id="t1", status="SCRIPT_READY"):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, topic, strategy, producibility_score, status, video_version, "
        "voice_id, script, script_segments, created_at, updated_at) "
        "VALUES (?, 't', 'manual', 5, ?, 1, ?, 'x', ?, '2026-01-01', '2026-01-01')",
        (vid, status, voice_id, json.dumps(segments)))
    con.commit()
    con.close()
    return vid


def _segments(db_path, vid="vid-1"):
    con = sqlite3.connect(db_path)
    raw = con.execute("SELECT script_segments FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    return json.loads(raw)


def _seg(id_, voice, **extra):
    return {"id": id_, "voice": voice, "visual": "", **extra}


def _patch(client, body, vid="vid-1"):
    return client.patch(f"/videos/{vid}", json=body)


# ── the segment_voices PATCH ─────────────────────────────────────────────────

def test_a_segment_gets_its_own_voice(client, db_path):
    _scripted(db_path, [_seg("s1", "Hello there."), _seg("s2", "Wait, what?")])
    r = _patch(client, {"segment_voices": {"s2": "r1"}})
    assert r.status_code == 200
    assert _segments(db_path)[1]["voice_id"] == "r1"
    assert "voice_id" not in _segments(db_path)[0]
    assert json.loads(r.data)["script_segments"][1]["voice_id"] == "r1"


def test_a_blank_or_the_video_voice_gives_the_segment_back(client, db_path):
    _scripted(db_path, [_seg("s1", "Hi.", voice_id="r1"), _seg("s2", "Yo.", voice_id="b1")])
    assert _patch(client, {"segment_voices": {"s1": "", "s2": "t1"}}).status_code == 200
    assert all("voice_id" not in s for s in _segments(db_path))


def test_the_spoken_words_and_record_are_untouched(client, db_path):
    _scripted(db_path, [_seg("s1", "Hello there.", beat="Hook")])
    _patch(client, {"segment_voices": {"s1": "r1"}})
    seg = _segments(db_path)[0]
    assert seg["voice"] == "Hello there." and seg["beat"] == "Hook"


@pytest.mark.parametrize("body,code", [
    ({"segment_voices": {"nope": "r1"}}, 400),           # unknown segment
    ({"segment_voices": {"s1": "ghost"}}, 400),          # voice not on the roster
    ({"segment_voices": {}}, 400),                       # nothing to change
    ({"segment_voices": {"s1": 3}}, 400),                # not a string
    ({"segment_voices": {"s1": "r1"}, "title": "x"}, 400),   # not on its own
])
def test_a_bad_segment_voices_body_is_refused_and_nothing_changes(client, db_path, body, code):
    _scripted(db_path, [_seg("s1", "Hello.")])
    assert _patch(client, body).status_code == code
    assert "voice_id" not in _segments(db_path)[0]


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "VOICING", "VIDEO_READY"])
def test_a_segment_voice_changes_only_at_script_ready(client, db_path, status):
    _scripted(db_path, [_seg("s1", "Hello.")], status=status)
    assert _patch(client, {"segment_voices": {"s1": "r1"}}).status_code == 409


def test_a_voice_that_cannot_speak_the_segment_is_refused(client, db_path):
    # [pause] is v3/v4 markup; Rachel is on multilingual_v2.
    _scripted(db_path, [_seg("s1", PAUSE)])
    r = _patch(client, {"segment_voices": {"s1": "r1"}})
    assert r.status_code == 409 and json.loads(r.data)["voice_conflict"] is True
    assert "voice_id" not in _segments(db_path)[0]


def test_a_script_written_in_between_is_not_overwritten(client, db_path, monkeypatch):
    _scripted(db_path, [_seg("s1", "Hello.")])
    real = pipeline.tvoice.normalize_segment_voices

    def racing(segments, video_voice_id):
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET script_segments = ? WHERE id = 'vid-1'",
                    (json.dumps([_seg("s1", "Rewritten.")]),))
        con.commit()
        con.close()
        return real(segments, video_voice_id)

    monkeypatch.setattr(pipeline.tvoice, "normalize_segment_voices", racing)
    assert _patch(client, {"segment_voices": {"s1": "r1"}}).status_code == 409
    assert _segments(db_path) == [_seg("s1", "Rewritten.")]


# ── conflicts on the video payload ───────────────────────────────────────────

def test_the_picker_greys_out_voices_a_segment_cannot_use(client, db_path):
    _scripted(db_path, [_seg("s1", PAUSE), _seg("s2", BREAK, voice_id="r1")])
    video = json.loads(client.get("/videos/vid-1").data)
    assert set(video["segment_voice_conflicts"]["s1"]) == {"r1", "b1"}
    assert set(video["segment_voice_conflicts"]["s2"]) == {"t1"}


def test_no_segment_conflicts_outside_script_ready(client, db_path):
    _scripted(db_path, [_seg("s1", PAUSE)], status="VOICE_READY")
    assert json.loads(client.get("/videos/vid-1").data)["segment_voice_conflicts"] == {}


def test_a_video_voice_change_ignores_segments_with_their_own_voice(client, db_path):
    # The video's own segment is plain; Rachel's segment carries <break/>,
    # which Teja (v4) cannot speak — but Teja never speaks it.
    _scripted(db_path, [_seg("s1", "Hello."), _seg("s2", BREAK, voice_id="r1")], voice_id="b1")
    video = json.loads(client.get("/videos/vid-1").data)
    assert "t1" not in video["voice_conflicts"]


# ── approval ─────────────────────────────────────────────────────────────────

def _approve(client, **extra):
    return _patch(client, {"status": "VOICING", "onlyIfCurrentStatus": "SCRIPT_READY", **extra})


def test_a_two_voice_script_that_fits_each_voice_approves(client, db_path):
    _scripted(db_path, [_seg("s1", PAUSE), _seg("s2", BREAK, voice_id="r1")])
    assert _approve(client, voice_id="t1").status_code == 200


def test_approval_refuses_a_segment_voice_that_can_no_longer_speak_it(client, db_path):
    _scripted(db_path, [_seg("s1", "Hello."), _seg("s2", BREAK, voice_id="r1")])
    # Rachel's model is edited to v4 after scripting: her <break/> would be ignored.
    client.post("/settings", json={"elevenlabs_voices": [{**V2, "model_id": "eleven_v4"}, V4, V2B]})
    r = _approve(client, voice_id="t1")
    assert r.status_code == 409 and json.loads(r.data)["voice_conflict"] is True
    assert "Rachel" in json.loads(r.data)["error"]


def test_approval_without_a_voice_still_checks_every_segment(client, db_path):
    """The Kanban card approves with no voice_id."""
    _scripted(db_path, [_seg("s1", "Hello."), _seg("s2", BREAK, voice_id="r1")])
    client.post("/settings", json={"elevenlabs_voices": [{**V2, "model_id": "eleven_v4"}, V4, V2B]})
    assert _approve(client).status_code == 409


def test_approval_refuses_a_segment_voice_that_left_the_roster(client, db_path):
    _scripted(db_path, [_seg("s1", "Hello."), _seg("s2", "Hi.", voice_id="r1")])
    client.post("/settings", json={"elevenlabs_voices": [V4, V2B]})
    assert _approve(client).status_code == 409
