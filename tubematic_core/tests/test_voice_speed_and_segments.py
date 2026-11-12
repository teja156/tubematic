"""tubematic_core.voice_models (TMDEV-216): per-voice speed and a voice per segment.

Speed: ElevenLabs ignores voice_settings.speed on eleven_v3 and eleven_v4
without an error (probed with paid calls), so a speed on those models must be
refused, never stored, or a person would think the voice was faster. A speed of
1.0 is never stored, which keeps a roster nobody changed in the exact shape
older versions read.

Segments: a segment voice_id means "a voice other than the video's". Markup is
checked against the model of the voice that speaks each segment. The negative
controls (a two-voice script whose markup fits each voice) matter as much as
the refusals: a wrong refusal blocks an approval, a missing one voices markup
a model reads aloud.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import voice_models as vm  # noqa: E402

TEJA = {"name": "Teja", "voice_id": "teja", "model_id": "eleven_v4"}
ADAM = {"name": "Adam", "voice_id": "adam", "model_id": "eleven_multilingual_v2"}
ROSTER = [TEJA, ADAM]


def test_speed_models_are_the_catalog_minus_v3_and_v4():
    assert vm.SPEED_MODELS == vm.DICTIONARY_COMPATIBLE_MODELS - {"eleven_v3", "eleven_v4"}


@pytest.mark.parametrize("speed", [0.7, 0.95, 1.0, 1.1, 1.15, 1.2])
def test_a_speed_in_range_on_a_v2_model_is_allowed(speed):
    assert vm.speed_error(speed, "eleven_multilingual_v2") is None


@pytest.mark.parametrize("speed,fragment", [
    (0.65, "between"), (1.25, "between"), (1.13, "multiple"), ("1.1", "number"), (True, "number"),
])
def test_a_bad_speed_is_refused(speed, fragment):
    assert fragment in vm.speed_error(speed, "eleven_multilingual_v2")


@pytest.mark.parametrize("model", ["eleven_v3", "eleven_v4"])
def test_a_speed_on_v3_or_v4_is_refused_and_names_the_voice(model):
    err = vm.speed_error(1.1, model, "Teja")
    assert "ignores speed" in err and "Teja" in err


@pytest.mark.parametrize("model", ["eleven_v3", "eleven_v4"])
def test_the_default_speed_is_allowed_on_every_model(model):
    assert vm.speed_error(1.0, model) is None


def test_a_roster_entry_without_speed_is_valid_and_kept_as_is():
    assert vm.roster_entry_error(TEJA) is None
    assert vm.normalize_roster_entry(TEJA) == TEJA


def test_a_default_speed_is_never_stored():
    assert vm.normalize_roster_entry({**ADAM, "speed": 1.0}) == ADAM


def test_a_speed_is_stored_rounded():
    assert vm.normalize_roster_entry({**ADAM, "speed": 1.1500000001})["speed"] == 1.15


@pytest.mark.parametrize("entry", [
    {**TEJA, "speed": 1.1},                       # v4 ignores speed
    {**ADAM, "pitch": 1.0},                       # unknown key
    {"name": "x", "voice_id": "y"},               # missing model
    {**ADAM, "model_id": ["eleven_v3"]},          # unhashable model
])
def test_a_bad_roster_entry_is_refused(entry):
    assert vm.roster_entry_error(entry)


def test_voice_speed_defaults_to_one():
    assert vm.voice_speed(TEJA) == 1.0
    assert vm.voice_speed({**ADAM, "speed": 1.15}) == 1.15


def test_a_segment_voice_equal_to_the_video_voice_is_dropped():
    segs = [{"id": "a", "voice": "x", "visual": "", "voice_id": "teja"},
            {"id": "b", "voice": "y", "visual": "", "voice_id": "adam"},
            {"id": "c", "voice": "z", "visual": "", "voice_id": ""}]
    out = vm.normalize_segment_voices(segs, "teja")
    assert "voice_id" not in out[0] and out[1]["voice_id"] == "adam" and "voice_id" not in out[2]
    assert segs[0]["voice_id"] == "teja"  # the input is not changed


def test_a_segment_voice_must_be_a_roster_string():
    assert vm.segment_voice_error([{"voice_id": "ghost"}], ROSTER)
    assert vm.segment_voice_error([{"voice_id": 3}], ROSTER)
    assert vm.segment_voice_error([{"voice_id": "adam"}, {"voice_id": ""}, {}], ROSTER) is None


def test_runs_group_consecutive_segments_by_voice():
    segs = [{}, {"voice_id": "adam"}, {"voice_id": "adam"}, {}, {}]
    assert vm.segment_runs(segs, "teja") == [("teja", [0]), ("adam", [1, 2]), ("teja", [3, 4])]
    assert vm.segment_runs([{}, {}], "teja") == [("teja", [0, 1])]


def test_each_segment_is_checked_against_its_own_voice():
    # [pause] is v3/v4 markup; <break/> is v2 markup. Each fits its own voice.
    segs = [{"voice": "Hello [pause] there", "visual": ""},
            {"voice": 'Wait <break time="0.4s" /> what', "visual": "", "voice_id": "adam"}]
    assert vm.script_markup_conflict(segs, "", TEJA, ROSTER) is None
    swapped = [{**segs[0], "voice_id": "adam"}, {k: v for k, v in segs[1].items() if k != "voice_id"}]
    err = vm.script_markup_conflict(swapped, "", TEJA, ROSTER)
    assert err and "Adam" in err


def test_a_segment_voice_that_left_the_roster_is_a_conflict():
    segs = [{"voice": "Hi", "visual": "", "voice_id": "gone"}]
    assert "no longer in elevenlabs_voices" in vm.script_markup_conflict(segs, "", TEJA, ROSTER)


def test_a_video_voice_change_checks_only_the_segments_it_speaks():
    segs = [{"voice": "Hi there", "visual": ""},
            {"voice": 'Wait <break time="0.4s" /> what', "visual": "", "voice_id": "adam"}]
    # Changing the VIDEO voice to v4 must not trip on Adam's <break/>.
    assert vm.video_voice_conflict(segs, "", "eleven_v4", "Teja") is None
    only_own = [{"voice": "Hi", "visual": "", "voice_id": "adam"}]
    assert vm.video_voice_conflict(only_own, "", "eleven_v4") is None


def test_a_video_voice_change_still_refuses_markup_it_cannot_speak():
    segs = [{"voice": 'Hi <break time="0.4s" /> there', "visual": ""}]
    assert vm.video_voice_conflict(segs, "", "eleven_v4", "Teja")
