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
    "eleven_v4",
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
# eleven_v4 is the same (no normalization, and its docs say it takes no SSML).
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
# eleven_v4 (TMDEV-172) was probed live the same way as v3: its alignment
# mirrors the "/ph/" form exactly and normalized_alignment is identical to it
# (no normalization), and wrapping "Madison" in the IPA for "tomato"
# transcribes as "tomato".
IPA_COMPATIBLE_MODELS = frozenset({"eleven_v3", "eleven_v4"})

# The models that understand the bracketed pause tags ([pause] /
# [short pause] / [long pause]) and do NOT support SSML. Probed live on v4:
# the tags are carried verbatim in the alignment and never spoken; [long pause]
# added ~2s of silence, a [pause] right after a full stop only ~0.14s.
V3_PAUSE_MODELS = frozenset({"eleven_v3", "eleven_v4"})

# Models that honor SSML <break time="..."/> tags: every model except the
# bracketed-pause ones, which take no SSML at all.
BREAK_TAG_COMPATIBLE_MODELS = DICTIONARY_COMPATIBLE_MODELS - V3_PAUSE_MODELS

# Models that honour voice_settings.speed (TMDEV-216, probed live with paid
# calls). On every model below, speed 1.2 made the same line 15-22% shorter and
# the alignment timings shrank with the audio. eleven_v3 and eleven_v4 answer
# 200 and ignore the field: across repeats their lengths at 1.0 and 1.2
# overlap. ElevenLabs does not refuse it there, so Tubematic does — a speed a
# person sets has to change the audio or be refused, never be dropped quietly.
# Keep in sync with dashboard SPEED_MODELS (pinned by the cross-copy test).
SPEED_MODELS = frozenset({
    "eleven_multilingual_v2",
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_flash_v2",
    "eleven_turbo_v2",
})
SPEED_MIN = 0.7
SPEED_MAX = 1.2
SPEED_STEP = 0.05
DEFAULT_SPEED = 1.0

# Models that refuse previous_text / next_text, the context fields a request
# for one run of a two-voice script carries about its neighbours (TMDEV-216,
# probed: eleven_v3 answers 400 unsupported_model; eleven_v4 and the v2 models
# accept them).
CONTEXT_REFUSED_MODELS = frozenset({"eleven_v3"})

# A roster entry's keys. `speed` is optional and stored only when it is not
# DEFAULT_SPEED, so a roster nobody gave a speed keeps the exact shape older
# versions read (their readers drop a roster with any other key).
ROSTER_KEYS = frozenset({"name", "voice_id", "model_id"})
ROSTER_OPTIONAL_KEYS = frozenset({"speed"})

# The voices a fresh install starts with (TMDEV-172), in roster order; the
# first is the install default. Onboarding seeds them as the default answers
# of its voice questions, so they reach only an install that has never stored
# a roster: an existing roster is kept, and one whose defaults were deleted
# stays that way. The API's own default for a missing row is still [] —
# editing this list must never change the voices of an install nobody
# re-onboarded. Every entry must pass the roster readers' validation (a model
# in DICTIONARY_COMPATIBLE_MODELS, at most MAX_VOICES entries), or the
# readers drop the whole list.
DEFAULT_VOICES = (
    {"name": "Teja", "voice_id": "w7yaXuKi0bjR3rtgNpVp", "model_id": "eleven_v4"},
    {"name": "Adam", "voice_id": "bfGb7JTLUnZebZRiFYyq", "model_id": "eleven_v3"},
)
DEFAULT_VOICE_ID = DEFAULT_VOICES[0]["voice_id"]

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
                f"{', '.join(sorted(IPA_COMPATIBLE_MODELS))} understand, but "
                f"{_voice_phrase(voice_label, model_id)} — it would read the IPA aloud. "
                "Rewrite those terms with the pronunciation lexicon or an inline "
                '<respell as="...">word</respell> tag.')
    return None


def pause_model_error(text: str, model_id: str, voice_label: str = "") -> str | None:
    """Error if the pause syntax doesn't match the model.

    The two syntaxes are mutually exclusive by model: eleven_v3 and eleven_v4
    ignore SSML break tags, and every other model has no notion of the
    bracketed audio tags. Getting this wrong doesn't fail loudly at ElevenLabs — the markup is
    simply carried into the audio or the alignment — so it's refused instead.
    """
    if BREAK_TAG_RE.search(text) and model_id not in BREAK_TAG_COMPATIBLE_MODELS:
        return (f"voice text uses <break/> tags but {_voice_phrase(voice_label, model_id)}, "
                "which does not support them. Use [pause] / [short pause] / [long pause] "
                "instead, or pick a voice on one of: "
                f"{sorted(BREAK_TAG_COMPATIBLE_MODELS)}")
    if V3_PAUSE_TAG_RE.search(text) and model_id not in V3_PAUSE_MODELS:
        return (f"voice text uses [pause]-style audio tags, which only "
                f"{', '.join(sorted(V3_PAUSE_MODELS))} understand, but {_voice_phrase(voice_label, model_id)}. Use "
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


# ── Speed (TMDEV-216) ──────────────────────────────────────────────────────────

def voice_speed(entry: dict) -> float:
    """A roster voice's speed: its stored speed, else DEFAULT_SPEED."""
    return float(entry.get("speed", DEFAULT_SPEED))


def speed_error(speed, model_id: str, voice_label: str = "") -> str | None:
    """Why `speed` cannot be set on a voice on model_id, or None.

    The range is ElevenLabs' own; the 0.05 step keeps a value a person can
    read, and a preview cache key that does not split on float noise."""
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        return f"speed must be a number, got {speed!r}"
    if not SPEED_MIN <= speed <= SPEED_MAX:
        return f"speed must be between {SPEED_MIN} and {SPEED_MAX}, got {speed}"
    if abs(round(speed / SPEED_STEP) * SPEED_STEP - speed) > 1e-9:
        return f"speed must be a multiple of {SPEED_STEP}, got {speed}"
    if round(speed, 2) != DEFAULT_SPEED and model_id not in SPEED_MODELS:
        who = f"voice {voice_label!r} is on" if voice_label else "the model is"
        return (f"{who} '{model_id}', which ignores speed; only "
                f"{', '.join(sorted(SPEED_MODELS))} honour it. Keep it at {DEFAULT_SPEED}.")
    return None


def roster_entry_error(entry) -> str | None:
    """Why one roster entry is malformed, or None: the shape, model and speed
    rules every roster reader shares. Names, ids and duplicates stay the
    readers' own checks (they need the whole list)."""
    if not isinstance(entry, dict):
        return f"a roster entry must be an object, got {entry!r}"
    keys = set(entry)
    if not ROSTER_KEYS <= keys or not keys <= ROSTER_KEYS | ROSTER_OPTIONAL_KEYS:
        return ("a roster entry must be {name, voice_id, model_id} with an optional speed, "
                f"got {entry!r}")
    # Type first: a list or dict is unhashable and would raise on the `in`.
    if not isinstance(entry["model_id"], str) or entry["model_id"] not in DICTIONARY_COMPATIBLE_MODELS:
        return (f"voice {entry.get('name')!r} has model_id {entry['model_id']!r}; "
                f"it must be one of {sorted(DICTIONARY_COMPATIBLE_MODELS)}")
    if "speed" in entry:
        return speed_error(entry["speed"], entry["model_id"], str(entry.get("name", "")))
    return None


def normalize_roster_entry(entry: dict) -> dict:
    """The entry as stored: a speed of DEFAULT_SPEED is dropped and any other
    rounded to two places. Call only on an entry roster_entry_error passed."""
    out = {k: entry[k] for k in ("name", "voice_id", "model_id")}
    if "speed" in entry and round(float(entry["speed"]), 2) != DEFAULT_SPEED:
        out["speed"] = round(float(entry["speed"]), 2)
    return out


# ── A voice per segment (TMDEV-216) ────────────────────────────────────────────

def segment_voice_id(seg) -> str:
    """The roster voice a segment names, or "" for the video's own voice."""
    if isinstance(seg, dict) and isinstance(seg.get("voice_id"), str):
        return seg["voice_id"].strip()
    return ""


def segment_voice_error(segments, roster: list[dict]) -> str | None:
    """Why a segment's voice_id is unusable, or None. Absent or "" means the
    video's voice; anything else must be a string naming a roster voice."""
    ids = {v["voice_id"] for v in roster}
    for i, seg in enumerate(segments or []):
        if not isinstance(seg, dict) or "voice_id" not in seg:
            continue
        vid = seg["voice_id"]
        if not isinstance(vid, str):
            return f"script_segments[{i}].voice_id must be a string, got {vid!r}"
        if vid.strip() and vid.strip() not in ids:
            return (f"script_segments[{i}].voice_id {vid!r} is not in elevenlabs_voices — "
                    "use a voice_id from get_pipeline_status's elevenlabs_voices")
    return None


def normalize_segment_voices(segments: list, video_voice_id: str) -> list:
    """Segments as stored: a voice_id that is blank or equal to the video's
    own voice is dropped, so a stored voice_id always means "a voice other
    than the video's", and a later change of the video's voice moves every
    segment without one. Both write paths call this: MCP update_video and the
    API's segment_voices PATCH."""
    out = []
    for seg in segments:
        seg = dict(seg)
        vid = segment_voice_id(seg)
        seg.pop("voice_id", None)
        if vid and vid != (video_voice_id or ""):
            seg["voice_id"] = vid
        out.append(seg)
    return out


def segment_runs(segments: list, video_voice_id: str) -> list[tuple[str, list[int]]]:
    """Consecutive segments grouped by the voice that speaks them, in play
    order: [(voice_id, [segment indices])]. One run means one voice."""
    runs: list[tuple[str, list[int]]] = []
    for i, seg in enumerate(segments):
        vid = segment_voice_id(seg) or video_voice_id
        if runs and runs[-1][0] == vid:
            runs[-1][1].append(i)
        else:
            runs.append((vid, [i]))
    return runs


def video_voice_conflict(segments, script: str, model_id: str,
                         voice_label: str = "") -> str | None:
    """markup_conflict for a change of the VIDEO's voice: only the segments it
    speaks are checked. A script whose every segment has its own voice gives
    the video voice nothing to speak."""
    if segments:
        own = [s for s in segments if isinstance(s, dict) and not segment_voice_id(s)]
        if not own:
            return None
        return markup_conflict(own, "", model_id, voice_label)
    return markup_conflict(segments, script, model_id, voice_label)


def script_markup_conflict(segments, script: str, video_voice: dict | None,
                           roster: list[dict]) -> str | None:
    """Why a script cannot be voiced as written, or None. Every segment is
    checked against the model of the voice that speaks it: its own voice_id,
    else the video's voice. A segment voice that has left the roster is a
    conflict, as a video voice that has is. `video_voice` is the resolved
    roster entry; None checks nothing for the segments it would speak (every
    caller refuses a missing video voice on its own)."""
    if not segments:
        if video_voice is None:
            return None
        return markup_conflict(segments, script, video_voice["model_id"], video_voice["name"])
    by_id = {v["voice_id"]: v for v in roster}
    groups: dict[str, list] = {}
    for seg in segments:
        if isinstance(seg, dict):
            groups.setdefault(segment_voice_id(seg), []).append(seg)
    for vid, segs in groups.items():
        entry = video_voice if not vid else by_id.get(vid)
        if entry is None:
            if not vid:
                continue
            return (f"a segment is voiced by {vid!r}, which is no longer in elevenlabs_voices. "
                    "Re-add it, or give the segment another voice.")
        err = markup_conflict(segs, "", entry["model_id"], entry["name"])
        if err:
            return err
    return None
