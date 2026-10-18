"""ElevenLabs model knowledge shared by the MCP server and the Flask API.

Each roster voice carries its own model (TMDEV-121), so the model a script is
voiced with follows the video's voice, and the markup a script may carry
follows the model. Both processes need the same answer to "can this voice
speak this script" — the API refuses a voice change the script cannot use, and
generate_voice refuses the same thing before spend — so the model sets and the
check live here, once, instead of as two hand-synced copies. Both processes run
in the same image, so both can import this module.

Pure functions only: no DB, no network. Callers read the roster and pass it in.

The dashboard keeps its own TypeScript copy of the model sets for the Settings
notes, pinned by renderer/api/tests/test_pipeline.py's cross-copy test. It
does not copy the markup check: the API computes the conflicts and ships them
on the video payload, so the picker's grey-out and the 409 can never disagree.
"""

import re

DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# Every ElevenLabs model a voice may be set to. Keep in sync with dashboard
# DICTIONARY_COMPATIBLE_MODELS (the name predates per-voice models).
# eleven_english_v1 was removed (TMDEV-122): ElevenLabs answers
# model_not_found for it.
DICTIONARY_COMPATIBLE_MODELS = frozenset({
    "eleven_multilingual_v2",
    "eleven_v3",
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_flash_v2",
    "eleven_turbo_v2",
})

# Models compatible with inline SSML <phoneme> tags (pronunciation_mode="phoneme").
# eleven_multilingual_v2 and eleven_turbo_v2_5 are NOT in this list — they only
# support alias-rule pronunciation dictionaries, not phoneme/arpabet rules.
# eleven_v3 was removed (TMDEV-26): a live /with-timestamps probe showed it
# applies no text normalization at all — normalized_alignment comes back
# byte-identical to alignment, so a <phoneme> tag stays as ~11 verbatim markup
# tokens instead of collapsing to one, and _lockstep_segment_frames can never
# reconcile it against the authored word count. That is true of the XML tag
# only: v3 takes IPA natively in its own syntax — see IPA_COMPATIBLE_MODELS.
# TMDEV-122, probed live with speech-to-text: wrapping "Madison" in the
# phonemes for "tomato" is spoken as "tomato" on both models below. The two
# 2.5 models EAT the tagged word (the transcript skips it), so never add them
# here "for completeness".
PHONEME_COMPATIBLE_MODELS = frozenset({
    "eleven_turbo_v2",
    "eleven_flash_v2",
})

# Models that pronounce inline IPA written between slashes
# (pronunciation_mode="ipa"), reached through <ipa ph="...">word</ipa> tags.
IPA_COMPATIBLE_MODELS = frozenset({"eleven_v3"})

# Models that honor SSML <break time="..."/> tags. Every model except eleven_v3,
# which uses bracketed audio tags ([pause] / [short pause] / [long pause])
# instead.
BREAK_TAG_COMPATIBLE_MODELS = DICTIONARY_COMPATIBLE_MODELS - {"eleven_v3"}

# The only model that understands the bracketed pause tags.
V3_PAUSE_MODELS = frozenset({"eleven_v3"})

IPA_OPEN_RE      = re.compile(r'<ipa\b', re.IGNORECASE)
PHONEME_OPEN_RE  = re.compile(r'<phoneme\b[^>]*>', re.IGNORECASE)
BREAK_TAG_RE     = re.compile(r'<break\b[^>]*>', re.IGNORECASE)
V3_PAUSE_TAG_RE  = re.compile(r'\[\s*(?:short\s+|long\s+)?pause\s*\]', re.IGNORECASE)


def pronunciation_mode_for_model(model_id: str) -> str:
    """Derive the pronunciation mode from an ElevenLabs model — never stored.

    "phoneme" tags are only honored by PHONEME_COMPATIBLE_MODELS; the
    pronunciation lexicon and inline <respell> tags are plain text
    substitution and work on every model, including in phoneme mode itself.
    So enabling phoneme mode whenever the model supports it is strictly
    additive — it never removes a capability. The same holds for "ipa" on
    IPA_COMPATIBLE_MODELS. A computed value also can't drift from the model
    the way a separately stored one could.
    """
    if model_id in IPA_COMPATIBLE_MODELS:
        return "ipa"
    return "phoneme" if model_id in PHONEME_COMPATIBLE_MODELS else "respell"


def ipa_model_error(text: str, model_id: str, voice_label: str = "") -> str | None:
    """Error if text carries an <ipa> tag and the model would read it aloud.
    There is no fallback: IPA cannot be turned into a respelling, so the
    script has to be rewritten."""
    if IPA_OPEN_RE.search(text) and model_id not in IPA_COMPATIBLE_MODELS:
        return (f"voice text uses <ipa> tags, which only "
                f"{', '.join(sorted(IPA_COMPATIBLE_MODELS))} understands, but "
                f"{_voice_phrase(voice_label, model_id)} — it would read the IPA aloud. "
                "Rewrite those terms with the pronunciation lexicon or an inline "
                '<respell as="...">word</respell> tag.')
    return None


def pause_model_error(text: str, model_id: str, voice_label: str = "") -> str | None:
    """Error if the pause syntax doesn't match the model.

    The two syntaxes are mutually exclusive by model: eleven_v3 ignores SSML
    break tags, and every other model has no notion of the bracketed audio
    tags. Getting this wrong doesn't fail loudly at ElevenLabs — the markup is
    simply carried into the audio or the alignment — so it's refused instead.
    """
    if BREAK_TAG_RE.search(text) and model_id not in BREAK_TAG_COMPATIBLE_MODELS:
        return (f"voice text uses <break/> tags but {_voice_phrase(voice_label, model_id)}, "
                "which does not support them. Use [pause] / [short pause] / [long pause] "
                "instead, or pick a voice on one of: "
                f"{sorted(BREAK_TAG_COMPATIBLE_MODELS)}")
    if V3_PAUSE_TAG_RE.search(text) and model_id not in V3_PAUSE_MODELS:
        return (f"voice text uses [pause]-style audio tags, which only eleven_v3 "
                f"understands, but {_voice_phrase(voice_label, model_id)}. Use "
                '<break time="0.6s" /> instead.')
    return None


def phoneme_model_error(text: str, model_id: str, voice_label: str = "") -> str | None:
    """Error if text carries a <phoneme> tag and the model ignores it.

    generate_voice strips the tags on such a model rather than refusing, so
    the word would be spoken as spelled and the pronunciation silently lost.
    Refused at authoring time so a script only ever carries markup its own
    voice can speak — which is what lets approval with that voice always pass.
    """
    if PHONEME_OPEN_RE.search(text) and model_id not in PHONEME_COMPATIBLE_MODELS:
        return (f"voice text uses <phoneme> tags, which {_voice_phrase(voice_label, model_id)} "
                "ignores — those words would be spoken as spelled. Use a voice on one of: "
                f"{sorted(PHONEME_COMPATIBLE_MODELS)}, or write the pronunciations with the "
                'lexicon or an inline <respell as="...">word</respell> tag.')
    return None


def markup_conflict(segments, script: str, model_id: str,
                    voice_label: str = "") -> str | None:
    """Why a script cannot be voiced on model_id, or None if it can.

    This is the check behind refusing a voice change at SCRIPT_READY: a
    script's markup was written for the model of the voice it was scripted
    for, and a voice on another model may be unable to speak it.

    segments is the stored script_segments list (or None for a legacy flat
    script, in which case script is checked instead). A legacy script counts
    only <ipa>: generate_voice's flat path strips pause markup itself, so
    that markup can never reach ElevenLabs there.

    <phoneme> tags conflict with any model that cannot honour them, even
    though generate_voice only strips them there: stripping silently loses the
    pronunciation, which is what the refusal exists to prevent. There is
    deliberately no "the current model ignores them too" exemption — when a
    voice's model is edited in Settings, the model the script was written for
    is gone, and the edited one would be both "current" and "target".
    """
    if segments:
        text = " ".join(str(seg.get("voice", "")).strip() for seg in segments
                        if isinstance(seg, dict))
        return (ipa_model_error(text, model_id, voice_label)
                or pause_model_error(text, model_id, voice_label)
                or phoneme_model_error(text, model_id, voice_label))
    return ipa_model_error(script or "", model_id, voice_label)


def resolve_voice(video_voice_id: str, install_default: str, roster: list[dict]) -> dict | None:
    """The voice a video is voiced with: its own voice_id, else the install
    default. Never the project default — that is seeded into video.voice_id
    when the video is created, so a later change to a project's default never
    reaches back to old videos.

    Returns the roster entry plus "source" ("video" or "install"), or None
    when nothing resolves to a voice in the roster. A video voice that has
    left the roster is None rather than a fallback: spending against a voice
    nobody chose is worse than an error.
    """
    by_id = {v["voice_id"]: v for v in roster}
    if video_voice_id:
        entry = by_id.get(video_voice_id)
        return {**entry, "source": "video"} if entry else None
    entry = by_id.get(install_default or "")
    return {**entry, "source": "install"} if entry else None


def _voice_phrase(voice_label: str, model_id: str) -> str:
    if voice_label:
        return f"voice {voice_label!r} is on model '{model_id}'"
    return f"the model is '{model_id}'"
