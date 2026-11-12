"""The AI review's note on a narration spoken in more than one voice (TMDEV-216).

A second voice on purpose (a viewer's objection, a dialogue) must not be
reported as a defect: any finding routes the video to a revision and a paid
re-voice. The negative control is the other half: a one-voice video's prompt
must stay exactly as it was, so this note appears only with two voices.
"""
import json

import ai_review
import render_results


def test_one_voice_adds_nothing():
    assert ai_review._voices_block([]) == ""
    assert ai_review._voices_block(["Teja"]) == ""


def test_two_voices_are_named_and_called_intended():
    block = ai_review._voices_block(["Teja", "Rachel"])
    assert "2 different voices" in block and "Teja, Rachel" in block
    assert "CORRECT BY DESIGN" in block


def _row(voice_id, segments):
    return {"voice_id": voice_id, "script_segments": json.dumps(segments) if segments else None}


def test_the_narration_voices_come_from_the_video_and_its_segments(monkeypatch):
    settings = {"elevenlabs_voices": json.dumps([
        {"name": "Teja", "voice_id": "t1", "model_id": "eleven_v4"},
        {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"}]),
        "elevenlabs_voice_id": "t1"}
    monkeypatch.setattr(render_results, "_setting", lambda k, d: settings.get(k, d))
    segs = [{"id": "a", "voice": "x", "visual": ""},
            {"id": "b", "voice": "y", "visual": "", "voice_id": "r1"},
            {"id": "c", "voice": "z", "visual": "", "voice_id": "r1"}]
    assert render_results._narration_voices(_row("", segs)) == ["Teja", "Rachel"]
    assert render_results._narration_voices(_row("t1", segs[:1])) == ["Teja"]
    gone = [{"id": "a", "voice": "x", "visual": "", "voice_id": "zz"},
            {"id": "b", "voice": "y", "visual": ""}]
    assert render_results._narration_voices(_row("t1", gone)) == ["zz", "Teja"]


def test_a_video_whose_every_segment_has_another_voice_is_one_voice(monkeypatch):
    """The video's own voice speaks nothing then, so the review must not be
    told two voices speak."""
    settings = {"elevenlabs_voices": json.dumps([
        {"name": "Teja", "voice_id": "t1", "model_id": "eleven_v4"},
        {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"}]),
        "elevenlabs_voice_id": "t1"}
    monkeypatch.setattr(render_results, "_setting", lambda k, d: settings.get(k, d))
    segs = [{"id": "a", "voice": "x", "visual": "", "voice_id": "r1"}]
    assert render_results._narration_voices(_row("t1", segs)) == ["Rachel"]
