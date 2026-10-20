"""tubematic_core.voice_models (TMDEV-121): the model follows the voice.

The checks here decide whether a human may switch a scripted video to another
voice. Too strict blocks approvals for no reason; too loose voices a script
whose pronunciation markup the new model reads aloud or silently drops — and
both a refusal and a silent drop land on a paid voicing. The negative
controls (a compatible switch, a script with no markup) matter as much as the
refusals.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import voice_models as vm  # noqa: E402


def _segs(*voices):
    return [{"voice": v, "visual": ""} for v in voices]


@pytest.mark.parametrize("model,mode", [
    ("eleven_multilingual_v2", "respell"),
    ("eleven_v3", "ipa"),
    ("eleven_v4", "ipa"),
    ("eleven_turbo_v2", "phoneme"),
    ("eleven_flash_v2", "phoneme"),
    ("eleven_flash_v2_5", "respell"),
    ("eleven_turbo_v2_5", "respell"),
])
def test_pronunciation_mode_follows_the_model(model, mode):
    assert vm.pronunciation_mode_for_model(model) == mode


def test_the_retired_model_is_not_offered():
    assert "eleven_english_v1" not in vm.DICTIONARY_COMPATIBLE_MODELS


def test_break_tags_work_everywhere_but_v3_and_v4():
    assert vm.BREAK_TAG_COMPATIBLE_MODELS == (
        vm.DICTIONARY_COMPATIBLE_MODELS - {"eleven_v3", "eleven_v4"})


def test_v4_takes_exactly_the_v3_rules():
    """Probed live (TMDEV-172): v4 aligns "/ipa/" and [pause] exactly as v3
    does and takes no SSML, so it sits in every set v3 is in and none it isn't."""
    for models in (vm.IPA_COMPATIBLE_MODELS, vm.V3_PAUSE_MODELS, vm.PHONEME_COMPATIBLE_MODELS,
                   vm.BREAK_TAG_COMPATIBLE_MODELS, vm.DICTIONARY_COMPATIBLE_MODELS):
        assert ("eleven_v4" in models) == ("eleven_v3" in models)


# ── markup_conflict ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("model", sorted(vm.DICTIONARY_COMPATIBLE_MODELS))
def test_a_script_with_no_markup_fits_every_model(model):
    segs = _segs("Plain words only.", "Another sentence here.")
    assert vm.markup_conflict(segs, "", model) is None


def test_ipa_needs_v3_or_v4():
    segs = _segs('Say <ipa ph="ˈmædɪsən">Madison</ipa> now.')
    assert vm.markup_conflict(segs, "", "eleven_v3") is None
    assert vm.markup_conflict(segs, "", "eleven_v4") is None
    err = vm.markup_conflict(segs, "", "eleven_multilingual_v2", voice_label="Rachel")
    assert err and "<ipa>" in err and "Rachel" in err and "eleven_multilingual_v2" in err


def test_bracketed_pauses_need_v3_or_v4():
    segs = _segs("First. [long pause] Second.")
    assert vm.markup_conflict(segs, "", "eleven_v3") is None
    assert vm.markup_conflict(segs, "", "eleven_v4") is None
    assert "[pause]" in vm.markup_conflict(segs, "", "eleven_flash_v2_5")


def test_break_tags_are_refused_on_v3_and_v4_only():
    segs = _segs('First. <break time="0.6s" /> Second.')
    assert vm.markup_conflict(segs, "", "eleven_multilingual_v2") is None
    assert "<break/>" in vm.markup_conflict(segs, "", "eleven_v3")
    assert "<break/>" in vm.markup_conflict(segs, "", "eleven_v4")


def test_phoneme_tags_conflict_with_any_model_that_cannot_honour_them():
    """No current-model exemption: when a voice's model is edited in Settings,
    the model the script was written for is gone, and the edited one is both
    "current" and "target" — an exemption keyed on it would wave the switch
    through and generate_voice would strip the tags on a paid request."""
    segs = _segs('Say <phoneme alphabet="ipa" ph="x">word</phoneme>.')
    assert "<phoneme>" in vm.markup_conflict(segs, "", "eleven_v3")
    assert "<phoneme>" in vm.markup_conflict(segs, "", "eleven_v4")
    assert "<phoneme>" in vm.markup_conflict(segs, "", "eleven_multilingual_v2")
    assert vm.markup_conflict(segs, "", "eleven_turbo_v2") is None
    assert vm.markup_conflict(segs, "", "eleven_flash_v2") is None


def test_phoneme_model_error_is_the_write_time_check():
    text = 'Say <phoneme alphabet="ipa" ph="x">word</phoneme>.'
    assert vm.phoneme_model_error(text, "eleven_flash_v2") is None
    assert "Rachel" in vm.phoneme_model_error(text, "eleven_multilingual_v2", "Rachel")
    assert vm.phoneme_model_error("plain", "eleven_multilingual_v2") is None


def test_a_legacy_flat_script_counts_only_ipa():
    # generate_voice's flat path strips pause markup itself, so it can never
    # reach ElevenLabs there and must not block a switch.
    assert vm.markup_conflict(None, 'A <break time="1s" /> B [pause] C', "eleven_v3") is None
    assert vm.markup_conflict(None, 'A <ipa ph="x">B</ipa>', "eleven_multilingual_v2")


def test_an_unscripted_video_never_conflicts():
    assert vm.markup_conflict(None, "", "eleven_v3") is None
    assert vm.markup_conflict([], "", "eleven_multilingual_v2") is None


# ── resolve_voice ────────────────────────────────────────────────────────────

ROSTER = [
    {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"},
    {"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"},
]


def test_the_videos_own_voice_wins():
    v = vm.resolve_voice("a1", "r1", ROSTER)
    assert v["voice_id"] == "a1" and v["model_id"] == "eleven_v3" and v["source"] == "video"


def test_an_empty_video_voice_falls_back_to_the_install_default():
    v = vm.resolve_voice("", "r1", ROSTER)
    assert v["voice_id"] == "r1" and v["source"] == "install"


def test_a_video_voice_that_left_the_roster_does_not_fall_back():
    # Spending against a voice nobody chose is worse than an error.
    assert vm.resolve_voice("gone", "r1", ROSTER) is None


def test_an_install_default_off_the_roster_is_no_default():
    assert vm.resolve_voice("", "gone", ROSTER) is None
    assert vm.resolve_voice("", "", ROSTER) is None


# ── DEFAULT_VOICES (TMDEV-172) ───────────────────────────────────────────────

def test_the_default_voices_are_teja_then_adam():
    assert [(v["name"], v["voice_id"], v["model_id"]) for v in vm.DEFAULT_VOICES] == [
        ("Teja", "w7yaXuKi0bjR3rtgNpVp", "eleven_v4"),
        ("Adam", "bfGb7JTLUnZebZRiFYyq", "eleven_v3"),
    ]
    assert vm.DEFAULT_VOICE_ID == "w7yaXuKi0bjR3rtgNpVp"


def test_every_default_voice_is_on_an_offered_model():
    """A roster entry on a model outside the catalog makes every reader drop
    the WHOLE roster, so a bad default would leave a fresh install with none."""
    for v in vm.DEFAULT_VOICES:
        assert set(v) == {"name", "voice_id", "model_id"}
        assert v["model_id"] in vm.DICTIONARY_COMPATIBLE_MODELS
