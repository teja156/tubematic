"""A voice per segment and per-voice speed in generate_voice and update_video (TMDEV-216).

A script whose segments name more than one voice is voiced as runs of
consecutive same-voice segments, one ElevenLabs request each, then joined.
What these guard:

- A one-voice script is ONE request with exactly the payload it always had
  (no speed at 1.0, no context fields): every video made before this change
  must voice the same way.
- Everything that can refuse a voicing refuses before the FIRST request: a
  refusal after a paid run is money spent on audio that is thrown away.
- Each run's words are offset by the decoded length of the runs before it, so
  captions stay on the words across a change of voice.
- eleven_v3 refuses previous_text / next_text (probed), so its runs carry none.

Run from repo root: pytest mcp/tests/
"""
import base64
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

import server
from test_generate_voice import (  # noqa: F401 — fixtures
    _char_alignment, _FakeResponse, fake_httpx, job_db, voice_env,
)

TEJA = {"name": "Teja", "voice_id": "t1", "model_id": "eleven_v4"}
RACHEL = {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"}
ADAM = {"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"}
PUBLISH = {"publish_title": "A title", "publish_description": "A description."}
CHAR = 0.05   # seconds per character in the fake alignment


def _roster(*voices, default="t1"):
    server._set_setting("elevenlabs_voices", json.dumps(list(voices)))
    server._set_setting("elevenlabs_voice_id", default)


class _Recorder:
    """A fake httpx.Client that records every payload and answers each with an
    alignment of its own text; the audio bytes carry the run's length so the
    fake join can return it."""
    payloads: list = []
    fail_on: int | None = None

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):
        _Recorder.payloads.append({"url": url, **json})
        if _Recorder.fail_on == len(_Recorder.payloads):
            return _FakeResponse(500, {}, text="boom", headers={})
        text = json["text"]
        length = len(text) * CHAR
        return _FakeResponse(200, {
            "audio_base64": base64.b64encode(f"len:{length}".encode()).decode(),
            "alignment": _char_alignment(text, CHAR),
        }, headers={"character-cost": "42", "request-id": f"req-{len(_Recorder.payloads)}"})


@pytest.fixture
def recorder(monkeypatch, voice_env):
    import httpx
    _Recorder.payloads, _Recorder.fail_on = [], None
    monkeypatch.setattr(httpx, "Client", _Recorder)
    monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    def fake_join(ffmpeg, parts):
        durations = [float(p.decode().split(":")[1]) for p in parts]
        return b"joined-audio", durations

    monkeypatch.setattr(server, "_join_voice_audio", fake_join)
    _roster(TEJA, RACHEL, ADAM)
    return _Recorder


def _seg(id_, voice, **extra):
    return {"id": id_, "voice": voice, "visual": "", **extra}


def _timeline(video_id):
    return json.loads((server.JOBS_DIR / video_id / "timeline.json").read_text())


def _status(video_id):
    with server._conn() as con:
        return con.execute("SELECT status FROM videos WHERE id = ?", (video_id,)).fetchone()[0]


# ── one voice: unchanged ─────────────────────────────────────────────────────

def test_a_one_voice_script_is_one_request_with_the_old_payload(job_db, recorder):
    job_db("v1", script_segments=[_seg("s1", "Hello there."), _seg("s2", "Second part.")],
           voice_id="t1")
    assert "error" not in server.generate_voice("v1", "")
    assert len(recorder.payloads) == 1
    sent = recorder.payloads[0]
    assert set(sent) == {"url", "text", "model_id", "voice_settings", "output_format"}
    assert sent["voice_settings"] == {"stability": 0.5, "similarity_boost": 0.75}
    assert _timeline("v1")["audioDurationSeconds"] == pytest.approx(len(sent["text"]) * CHAR)


def test_a_voice_with_a_speed_sends_it(job_db, recorder):
    _roster(TEJA, {**RACHEL, "speed": 1.15}, ADAM, default="r1")
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="r1")
    assert "error" not in server.generate_voice("v1", "")
    assert recorder.payloads[0]["voice_settings"]["speed"] == 1.15


def test_a_roster_with_a_speed_on_a_model_that_ignores_it_voices_nothing(job_db, recorder):
    """A roster written around Settings (Teja on v4 with a speed) is malformed,
    so the roster reader drops all of it and no voice resolves: no spend."""
    server._set_setting("elevenlabs_voices", json.dumps([{**TEJA, "speed": 1.1}]))
    job_db("v1", script_segments=[_seg("s1", "Hello there.")], voice_id="t1")
    assert "no longer in elevenlabs_voices" in server.generate_voice("v1", "")["error"]
    assert recorder.payloads == []


# ── two voices ───────────────────────────────────────────────────────────────

def _two_voice(job_db):
    job_db("v1", voice_id="t1", script_segments=[
        _seg("s1", "So you can run it [pause] now."),
        _seg("s2", 'Wait <break time="0.4s" /> really?', voice_id="r1"),
        _seg("s3", "Yes, really."),
    ])


def test_runs_are_voiced_in_order_each_with_its_own_voice_and_model(job_db, recorder):
    _two_voice(job_db)
    result = server.generate_voice("v1", "")
    assert "error" not in result
    sent = recorder.payloads
    assert [p["url"].split("/")[-2] for p in sent] == ["t1", "r1", "t1"]
    assert [p["model_id"] for p in sent] == ["eleven_v4", "eleven_multilingual_v2", "eleven_v4"]
    assert result["credits"] == 126


def test_each_run_hears_its_neighbours(job_db, recorder):
    _two_voice(job_db)
    server.generate_voice("v1", "")
    first, middle, last = recorder.payloads
    assert "previous_text" not in first and first["next_text"] == "Wait really?"
    assert middle["previous_text"] == "So you can run it now." and middle["next_text"] == "Yes, really."
    assert last["previous_text"] == "Wait really?" and "next_text" not in last


def test_context_is_the_authored_words_never_respellings_or_ipa(job_db, recorder):
    """A v4 neighbour's IPA is sent to ElevenLabs as "/ph/"; a v2 run must not
    be given that as text."""
    job_db("v1", voice_id="t1", script_segments=[
        _seg("s1", 'Meet <ipa ph="ˈvɑːɡɑːr">Vhagar</ipa> now.'),
        _seg("s2", "Who is that?", voice_id="r1")])
    server.generate_voice("v1", "")
    assert recorder.payloads[1]["previous_text"] == "Meet Vhagar now."


def test_a_v3_run_carries_no_context(job_db, recorder):
    job_db("v1", voice_id="t1", script_segments=[
        _seg("s1", "First words here."), _seg("s2", "Second words.", voice_id="a1")])
    server.generate_voice("v1", "")
    assert "next_text" in recorder.payloads[0]
    assert "previous_text" not in recorder.payloads[1] and "next_text" not in recorder.payloads[1]


def test_words_after_a_join_are_offset_by_the_runs_before(job_db, recorder):
    _two_voice(job_db)
    server.generate_voice("v1", "")
    tl = _timeline("v1")
    first_len = len(recorder.payloads[0]["text"]) * CHAR
    first_word_of_run2 = next(w for w in tl["words"] if w["word"] == "Wait")
    assert first_word_of_run2["startFrame"] == round(first_len * server.FPS)
    assert [w["word"] for w in tl["words"]] == ["So", "you", "can", "run", "it", "now.",
                                                "Wait", "really?", "Yes,", "really."]
    total = sum(len(p["text"]) for p in recorder.payloads) * CHAR
    assert tl["audioDurationSeconds"] == pytest.approx(total)
    assert [s["id"] for s in tl["segments"]] == ["s1", "s2", "s3"]
    starts = [s["startFrame"] for s in tl["segments"]]
    assert starts == sorted(starts)


def test_every_run_is_recorded_with_its_voice(job_db, recorder):
    _two_voice(job_db)
    server.generate_voice("v1", "")
    with server._conn() as con:
        raws = [json.loads(r[0]) for r in con.execute(
            "SELECT raw_usage FROM usage_events WHERE service = 'elevenlabs' ORDER BY id")]
    assert [r["voice_id"] for r in raws] == ["t1", "r1", "t1"]


def test_the_stored_tts_text_is_every_run(job_db, recorder):
    _two_voice(job_db)
    server.generate_voice("v1", "")
    with server._conn() as con:
        tts = con.execute("SELECT tts_text FROM videos WHERE id = 'v1'").fetchone()[0]
    assert tts == " ".join(p["text"] for p in recorder.payloads)


# ── refusals before spend ────────────────────────────────────────────────────

def test_a_later_runs_markup_problem_spends_nothing(job_db, recorder):
    # Rachel (multilingual_v2) cannot speak [pause].
    job_db("v1", voice_id="t1", script_segments=[
        _seg("s1", "Fine words."), _seg("s2", "Bad [pause] words.", voice_id="r1")])
    result = server.generate_voice("v1", "")
    assert "error" in result and "Rachel" in result["error"]
    assert recorder.payloads == []


def test_a_segment_voice_that_left_the_roster_spends_nothing(job_db, recorder):
    job_db("v1", voice_id="t1", script_segments=[
        _seg("s1", "Fine words."), _seg("s2", "Other words.", voice_id="gone")])
    assert "no longer in elevenlabs_voices" in server.generate_voice("v1", "")["error"]
    assert recorder.payloads == []


def test_no_ffmpeg_spends_nothing_on_a_two_voice_script(job_db, recorder, monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: None)
    _two_voice(job_db)
    assert "ffmpeg" in server.generate_voice("v1", "")["error"]
    assert recorder.payloads == []


def test_a_failed_later_run_keeps_the_credits_spent_and_the_video_at_voicing(job_db, recorder):
    recorder.fail_on = 2
    _two_voice(job_db)
    result = server.generate_voice("v1", "")
    assert "ElevenLabs 500" in result["error"]
    assert len(recorder.payloads) == 2
    assert _status("v1") == "VOICING"
    assert not (server.JOBS_DIR / "v1" / "audio.mp3").exists()
    with server._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM usage_events WHERE service = 'elevenlabs'"
                           ).fetchone()[0] == 1


# ── update_video ─────────────────────────────────────────────────────────────

def test_update_video_keeps_a_segment_voice_and_drops_one_equal_to_the_video(job_db, voice_env):
    _roster(TEJA, RACHEL, ADAM)
    job_db("v1", status="TOPIC_APPROVED", voice_id="t1")
    r = server.update_video("v1", script_segments=[
        _seg("s1", "Hello.", voice_id="t1"), _seg("s2", "Hi there.", voice_id="r1")], **PUBLISH)
    assert "error" not in r
    with server._conn() as con:
        segs = json.loads(con.execute("SELECT script_segments FROM videos WHERE id='v1'").fetchone()[0])
    assert "voice_id" not in segs[0] and segs[1]["voice_id"] == "r1"


def test_update_video_refuses_a_segment_voice_not_on_the_roster(job_db, voice_env):
    _roster(TEJA, RACHEL)
    job_db("v1", status="TOPIC_APPROVED", voice_id="t1")
    r = server.update_video("v1", script_segments=[_seg("s1", "Hi.", voice_id="ghost")], **PUBLISH)
    assert "not in elevenlabs_voices" in r["error"]


def test_update_video_checks_each_segment_against_its_own_voice(job_db, voice_env):
    _roster(TEJA, RACHEL)
    job_db("v1", status="TOPIC_APPROVED", voice_id="t1")
    ok = server.update_video("v1", script_segments=[
        _seg("s1", "So [pause] here."),
        _seg("s2", 'Wait <break time="0.4s" /> what.', voice_id="r1")], **PUBLISH)
    assert "error" not in ok
    bad = server.update_video("v1", script_segments=[
        _seg("s1", 'So <break time="0.4s" /> here.'),
        _seg("s2", "Wait [pause] what.", voice_id="r1")], **PUBLISH)
    assert "error" in bad


def test_pipeline_status_shows_a_voices_speed(job_db, voice_env):
    _roster(TEJA, {**RACHEL, "speed": 1.15})
    voices = server.get_pipeline_status()["elevenlabs_voices"]
    assert voices[1]["speed"] == 1.15 and "speed" not in voices[0]


# ── the real join ────────────────────────────────────────────────────────────

def _find_ffmpeg(tmp_path):
    """ffmpeg on PATH, else Remotion's bundled one (it needs its own libs)."""
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    for root in (Path(__file__).resolve().parents[2], Path(os.environ.get("TUBEMATIC_MAIN_CHECKOUT", "/nonexistent"))):
        comp = root / "renderer/remotion/node_modules/@remotion/compositor-linux-x64-gnu"
        if (comp / "ffmpeg").exists():
            wrapper = tmp_path / "ffmpeg"
            wrapper.write_text(f'#!/bin/sh\nLD_LIBRARY_PATH="{comp}" exec "{comp}/ffmpeg" "$@"\n')
            wrapper.chmod(0o755)
            return str(wrapper)
    return None


def _tone_mp3(ffmpeg, path, seconds):
    wav = path.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x10\x00" * int(44100 * seconds))
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "128k",
                    str(path)], check=True)
    return path.read_bytes()


def test_the_real_join_measures_each_run_and_keeps_the_total(tmp_path):
    ffmpeg = _find_ffmpeg(tmp_path)
    if not ffmpeg:
        pytest.skip("no ffmpeg on this host (the MCP image has it)")
    parts = [_tone_mp3(ffmpeg, tmp_path / "a.mp3", 1.0), _tone_mp3(ffmpeg, tmp_path / "b.mp3", 2.0)]
    joined, durations = server._join_voice_audio(ffmpeg, parts)
    assert durations[0] == pytest.approx(1.0, abs=0.06) and durations[1] == pytest.approx(2.0, abs=0.06)
    out = tmp_path / "joined.mp3"
    out.write_bytes(joined)
    _, measured = server._join_voice_audio(ffmpeg, [joined])
    assert measured[0] == pytest.approx(sum(durations), abs=0.06)


def test_the_roster_reader_keeps_a_speed_and_drops_a_roster_with_a_bad_one(job_db):
    _roster(TEJA, {**RACHEL, "speed": 1.15})
    assert server._get_voices()[1]["speed"] == 1.15
    _roster(TEJA, {**RACHEL, "speed": 1.33})
    assert server._get_voices() == []
