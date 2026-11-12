"""A video's voice speed (TMDEV-227): native on the v2 family, a pitch-keeping
stretch on eleven_v3/v4, word timings scaled with the audio, and the
recording kept so a speed-only re-voice costs nothing.

What these guard:

- A video nobody gave a speed voices exactly as before: no speed in the
  request, no stretch.
- v4 is never sent a speed (it would be ignored); its recording is stretched.
  A v2 voice gets the speed natively up to 1.2 and a stretch for the rest.
- The timeline follows the stretched audio: a caption on the old times would
  run ahead of the voice.
- A re-voice with the same words at another speed makes no ElevenLabs call;
  the same words at the same speed is a new take and is paid for; other words
  are paid for.
- Everything that can refuse refuses before spend (ffmpeg missing for a
  stretch, a bad stored speed).

The ElevenLabs client, the stretch and the join are faked (test_voice_segments'
recorder): the fake audio carries its length, and a stretch divides it.

Run from repo root: pytest mcp/tests/
"""
import json

import pytest

import server
from test_generate_voice import job_db, voice_env  # noqa: F401 — fixtures
from test_voice_segments import ADAM, CHAR, PUBLISH, RACHEL, TEJA, _roster, _seg, _status, _timeline, recorder  # noqa: F401


def _set(video_id, **cols):
    with server._conn() as con:
        con.execute(f"UPDATE videos SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?",
                    [*cols.values(), video_id])


def _revoice(video_id):
    _set(video_id, status="VOICING")
    return server.generate_voice(video_id, "")


def test_a_video_without_a_speed_voices_as_before(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    out = server.generate_voice("v1", "")
    assert out["voice_speed"] == 1.0 and out["reused_recording"] is False
    assert "speed" not in recorder.payloads[0]["voice_settings"]
    assert recorder.stretches == []


def test_a_v4_video_speed_is_a_stretch_and_the_words_follow_it(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there friend.")], voice_id="t1")
    _set("v1", voice_speed=1.15)
    out = server.generate_voice("v1", "")
    assert "error" not in out and out["voice_speed"] == 1.15
    assert "speed" not in recorder.payloads[0]["voice_settings"]
    assert recorder.stretches == [1.15]
    sent = recorder.payloads[0]["text"]
    tl = _timeline("v1")
    assert tl["audioDurationSeconds"] == pytest.approx(len(sent) * CHAR / 1.15)
    # the last word ends where the stretched audio ends, not where the recording did
    assert tl["words"][-1]["endFrame"] == round(len(sent) * CHAR / 1.15 * server.FPS)


def test_a_v2_video_speed_is_native_up_to_its_maximum(job_db, recorder):
    _roster(TEJA, RACHEL, ADAM, default="r1")
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="r1")
    _set("v1", voice_speed=1.1)
    server.generate_voice("v1", "")
    assert recorder.payloads[0]["voice_settings"]["speed"] == 1.1 and recorder.stretches == []
    job_db("v2", script_segments=[_seg("s1", "Hello there.")], voice_id="r1")
    _set("v2", voice_speed=1.25)
    server.generate_voice("v2", "")
    assert recorder.payloads[1]["voice_settings"]["speed"] == 1.2
    assert recorder.stretches == [pytest.approx(1.25 / 1.2, abs=1e-6)]


def test_the_video_speed_replaces_the_roster_speed(job_db, recorder):
    _roster(TEJA, {**RACHEL, "speed": 0.8}, ADAM, default="r1")
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="r1")
    _set("v1", voice_speed=1.0)
    server.generate_voice("v1", "")
    assert "speed" not in recorder.payloads[0]["voice_settings"]


def test_a_two_voice_script_stretches_each_run_before_the_join(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there."), _seg("s2", "Second voice.", voice_id="r1")],
           voice_id="t1")
    _set("v1", voice_speed=1.1)
    server.generate_voice("v1", "")
    # v4 run stretched; the multilingual_v2 run sent natively
    assert "speed" not in recorder.payloads[0]["voice_settings"]
    assert recorder.payloads[1]["voice_settings"]["speed"] == 1.1
    assert recorder.stretches == [1.1]
    tl = _timeline("v1")
    first_len = len(recorder.payloads[0]["text"]) * CHAR / 1.1
    second_words = [w for w in tl["words"] if w["word"] in ("Second", "voice.")]
    assert second_words[0]["startFrame"] >= round(first_len * server.FPS) - 1


def test_a_speed_only_revoice_reuses_the_recording_and_costs_nothing(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there friend.")], voice_id="t1")
    first = server.generate_voice("v1", "")
    assert first["credits"] > 0
    _set("v1", voice_speed=1.2)
    out = _revoice("v1")
    assert out["reused_recording"] is True and out["credits"] == 0
    assert len(recorder.payloads) == 1          # no second ElevenLabs call
    assert recorder.stretches == [1.2]
    sent = recorder.payloads[0]["text"]
    assert _timeline("v1")["audioDurationSeconds"] == pytest.approx(len(sent) * CHAR / 1.2)
    assert _status("v1") == "VOICE_READY"


def test_a_v2_recording_is_re_stretched_from_its_own_native_speed(job_db, recorder):
    _roster(TEJA, RACHEL, ADAM, default="r1")
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="r1")
    _set("v1", voice_speed=1.1)
    server.generate_voice("v1", "")
    _set("v1", voice_speed=1.2)
    out = _revoice("v1")
    assert out["reused_recording"] is True and len(recorder.payloads) == 1
    assert recorder.stretches == [pytest.approx(1.2 / 1.1, abs=1e-6)]


def test_the_same_words_at_the_same_speed_is_a_new_paid_take(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    server.generate_voice("v1", "")
    out = _revoice("v1")
    assert out["reused_recording"] is False and len(recorder.payloads) == 2


def test_back_to_the_recorded_speed_after_a_restretch_is_free_too(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    server.generate_voice("v1", "")
    _set("v1", voice_speed=1.15)
    _revoice("v1")
    _set("v1", voice_speed=None)
    out = _revoice("v1")
    assert out["reused_recording"] is True and len(recorder.payloads) == 1


def test_changed_words_are_voiced_again_and_paid_for(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    server.generate_voice("v1", "")
    _set("v1", script_segments=json.dumps([_seg("s1", "Goodbye now.")]), voice_speed=1.1)
    out = _revoice("v1")
    assert out["reused_recording"] is False and len(recorder.payloads) == 2


def test_a_changed_voice_is_voiced_again(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    server.generate_voice("v1", "")
    _set("v1", voice_id="a1", voice_speed=1.1)
    out = _revoice("v1")
    assert out["reused_recording"] is False and recorder.payloads[1]["model_id"] == "eleven_v3"


def test_a_stretch_without_ffmpeg_is_refused_before_spend(job_db, recorder, monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: None)
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    _set("v1", voice_speed=1.1)
    out = server.generate_voice("v1", "")
    assert "ffmpeg" in out["error"] and recorder.payloads == []


def test_a_bad_stored_speed_is_refused_before_spend(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    _set("v1", voice_speed=1.7)
    assert "voice_speed" in server.generate_voice("v1", "")["error"] and recorder.payloads == []


# ── update_video / get_video ─────────────────────────────────────────────────

def test_the_agent_writes_the_speed_with_the_script(job_db, recorder):
    job_db("v1", status="TOPIC_APPROVED", voice_id="t1")
    out = server.update_video("v1", voice_speed=1.1)
    assert out.get("updated_fields") == ["voice_speed"]
    v = server.get_video("v1")
    assert v["voice_speed"] == 1.1 and v["effective_voice_speed"] == 1.1
    assert v["voice_speed_source"] == "video"


def test_get_video_falls_back_to_the_roster_speed(job_db, recorder):
    _roster({**TEJA, "speed": 1.05}, RACHEL, ADAM)
    job_db("v1", status="TOPIC_APPROVED", voice_id="t1")
    v = server.get_video("v1")
    assert v["voice_speed"] is None and v["effective_voice_speed"] == 1.05
    assert v["voice_speed_source"] == "roster"


@pytest.mark.parametrize("speed", [0.85, 1.3, 1.12, "fast", True])
def test_a_speed_out_of_range_is_refused(job_db, recorder, speed):
    job_db("v1", status="TOPIC_APPROVED", voice_id="t1")
    assert "voice_speed" in server.update_video("v1", voice_speed=speed)["error"]


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "SCRIPT_READY", "VOICING", "VOICE_READY", "VIDEO_READY"])
def test_the_agent_cannot_write_the_speed_outside_its_window(job_db, recorder, status):
    job_db("v1", status=status, voice_id="t1")
    out = server.update_video("v1", voice_speed=1.1)
    assert "error" in out and "voice_speed" in out["error"]


def test_a_pacing_revision_may_change_the_speed(job_db, recorder):
    job_db("v1", status="REVISION_REQUESTED", voice_id="t1")
    assert "error" not in server.update_video("v1", voice_speed=0.95)
    assert server.get_video("v1")["voice_speed"] == 0.95
