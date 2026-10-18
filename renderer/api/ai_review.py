"""Gemini quality review for rendered videos.

Review only — no patching. Returns a genuine critique of the video (visual
and audio), split into must-fix errors and improvement suggestions. The
caller decides what to do with the result (TMDEV-58: no more binary
passesReview — a real review of real creative output almost always has
something worth improving, so the model is no longer told to suppress that
in favor of a checklist verdict).

On any error (upload failure, API error, parse error): returns
{"overall": str, "must_fix": [], "suggestions": [], "feedback": str,
"error": str(e)} — fail open, never raises, empty findings routes the
caller the same way a clean review would. `feedback` is always populated
(even on error, and even on a clean pass) so callers always have something
human-readable to persist.
"""
import json
import os
import time

import httpx

SAFE_ZONE_TOP    = 150
SAFE_ZONE_BOTTOM = 170

# Video sampling (VQA-7). Gemini samples video at 1 FPS unless told otherwise,
# so a 30fps render was being judged on one frame in thirty and motion defects
# were invisible by construction. `video_metadata.fps` is a sibling field of
# `file_data` on the same part (NOT nested inside it), valid range (0, 24].
MAX_REVIEW_FPS = 24

# Measured 2026-08-11 against the live countTokens endpoint on a real 225s
# render, per model — NOT taken from the docs, which give three mutually
# inconsistent figures (263 tokens/second, 258 tokens/frame, 70 tokens/frame).
# The real shape: video tokens scale exactly linearly with fps, and the 263
# figure is per *frame* — it only coincides with per-second at 1 FPS.
_TOKENS_PER_FRAME = {
    "gemini-2.5-flash": 263,
    "gemini-3.5-flash": 71,
    "gemini-3.6-flash": 71,
}
# Conservative fallback for a model nobody has measured: assume the priciest.
_DEFAULT_TOKENS_PER_FRAME = 263
# Audio is a flat per-wall-clock-second cost and does NOT scale with fps
# (measured: 7,200 tokens for 225s, identical on every model above).
_AUDIO_TOKENS_PER_SEC = 32
# Leaves ~200k of the 1M window for the prompt, the inlined scene config and
# the response. Overrunning the window is a 400, and this module fails open by
# design — so without this clamp a long video would silently ship to
# VIDEO_READY having never been reviewed at all.
_VIDEO_TOKEN_BUDGET = 800_000

# Files API media upload lives under a distinct /upload path prefix, separate
# from GEMINI_BASE (which serves the files metadata/list + generateContent
# endpoints). Deriving one from the other by string surgery is a trap — an
# independent env var with its own correct default is simpler and testable.
_DEFAULT_UPLOAD_BASE = "https://generativelanguage.googleapis.com/upload/v1beta"

# Video uploads go through a PROCESSING state before ACTIVE; generateContent
# 400s if referenced too early. Hard-bounded so a stuck upload fails open
# instead of hanging the render tail forever.
_POLL_ATTEMPTS = 60
_POLL_INTERVAL_SECS = 5

_REVIEW_PROMPT = """\
You are reviewing a rendered short-form vertical video (1080×1920, 30fps) as a real creative
critique, not a pass/fail checklist. Watch and listen to the whole thing. You are being shown this
video sampled at {sampled_fps} frames per second, so judge motion, timing and animation from the
frames you actually have rather than assuming you can only see one frame per second. Judge both the
visuals (does each scene actually communicate the beat its narration is making, composition,
legibility, motion, pacing) and the audio (voice-over delivery, mix, timing).

You MUST explicitly check for each of the following, and report any you find under "mustFix":
  text_offscreen      — subtitle text is clipped or exits the visible frame
  sync_drift          — words appear > 0.5s before/after they are heard
  blank_frames        — black frames > 1s in the middle (not counting fade-in/out)
  audio_drop          — silence > 2s mid-video where speech is expected
  safe_zone_violation — text within {top}px of top or {bottom}px of bottom
  animation_defect    — an animated object/shape is unclean, misplaced, or misaligned (e.g. an
                         arrow connecting two components pointing at the wrong spot, an element
                         overlapping or drifting off its intended position, jerky/broken motion)
  mispronunciation    — a proper noun or technical term is pronounced objectively wrong: wrong
                         phonemes, read out letter-by-letter, or stressed so differently that it
                         lands as a different word. Accent, cadence, prosody, emphasis and
                         regional pronunciation variants are NOT defects — at most a suggestion.
                         Non-English, transliterated and mythological proper nouns are in scope
                         here, not only technical jargon — names of the kind Lanka, Rama, Ravana,
                         Sita, Hanuman, Kurukshetra, Vhagar, Caraxes, Targaryen.
                         Go through the proper nouns in the reference script one at a time and
                         judge each one before you answer, rather than relying on happening to
                         notice them as you watch.
                         Report every mispronounced word of the whole video in ONE finding whose
                         description lists them, not one finding per word.
You MUST also visually watch every scene's animation, not just its final frame, to check for
animation_defect — freeze-framing only the end of a scene will miss a mid-animation misalignment.
These are the minimum, not the whole scope. If you find any other problem that makes the video
unshippable as-is, include it under "mustFix" too, with a short snake_case type of your own.

Everything else you would change — anything that would make the video better but does not make it
unshippable — goes under "suggestions" instead. Cover both video and audio. A suggestion must
critique something that is actually in the video and that a viewer would notice: a shot that reads
badly, text that is hard to follow, a line delivered flatly, a beat that drags, a visual that does
not match what is being said. Do NOT propose decorative additions to a scene that already works —
adding a glow, a highlight, a checkmark, an icon, particles or an extra animation flourish is not a
suggestion, and neither is observing that something is clear but "could be more dynamic". If the
video genuinely has nothing worth changing, return an empty "suggestions" list; a short honest list
is worth more than a padded one. Your "overall" critique is where you account for the video as a
whole, so an empty list is not a non-answer.

Report EVERY must-fix defect you find — there is no limit on "mustFix", and leaving a real blocking
defect out to stay brief is a worse failure than a long response. Cap "suggestions" at 5 (pick the
most important if you find more). Keep each "description" and "suggestedFix" as compact as you can
while staying specific enough to act on without re-watching the video.
There is no hard character limit, so prefer being clear over being short when the two conflict.

Captions: this video burns in subtitles of its own narration, drawn from the voice track's word
timings, a few words at a time. THAT IS BY DESIGN AND IS CORRECT. Do not report the presence of
captions, their repetition of the spoken words, or the fact that they change rapidly, as a defect
or a suggestion — they are the feature. Judge them only on execution: legibility, whether they sit
inside the safe zone, and whether they are in sync (sync_drift and text_offscreen above are about
these). If the scene-config below has "subtitles": {{"enabled": false}} then this video
deliberately has none, and their absence is likewise not a defect.

Watermark: a small "Made with tubematic.ai" mark sits in the top-right corner of every frame, for
the whole video. THAT IS INTENTIONAL BRANDING AND IS CORRECT. Do not report the watermark as a
defect or a suggestion — not its presence, its position, its size, that it never moves or fades, or
that scene content is visible through it or passes beneath it. It is not on-screen text to be
judged for clutter, overlap or the safe zone. A video without the mark is likewise not a defect.

What IS worth reporting is the opposite: a scene that ALSO writes out what the narration is saying
— a headline, a title card, a lower third, a caption under a picture, a pull-quote of the spoken
line — is now redundant with the captions and clutters the frame. Report that under "suggestions"
as redundant_text, naming the scene. Text that carries its own information (a number, a label
pinned to part of a diagram or image, a defined term, code or a command, a chart axis or legend) is
not redundant and must not be reported.

{register_block}
Current scene-config (use "fps" to convert timestamps to frames, and each scene's
"src"/"startFrame"/"durationInFrames" to name which scene a finding falls in):
{scene_config_json}

{reference_text_block}

Respond ONLY with a JSON object (no prose, no markdown):
{{"overall": "<a few sentences on overall visual and audio quality, required>",
  "mustFix": [], "suggestions": []}}

Add one object per finding to "mustFix":
{{"type": "<one of the defect types above, or your own snake_case type>",
  "timestamp": "<m:ss into the video>",
  "scene": "<the src of the scene whose frame range contains this, or \\"unknown\\" if you can't tell>",
  "description": "<what is specifically wrong, concretely>",
  "suggestedFix": "<the smallest change that would fix it>"}}

Add one object per finding to "suggestions":
{{"area": "<\\"video\\" or \\"audio\\">",
  "timestamp": "<m:ss into the video, or \\"unknown\\">",
  "scene": "<the src of the scene this applies to, or \\"unknown\\">",
  "description": "<what could be better, concretely>",
  "suggestedFix": "<the change that would improve it>"}}
"""


def _effective_fps(requested, scene_config: dict, model: str) -> int:
    """Resolve the sampling rate to actually request, clamped to fit the
    context window (VQA-7).

    Returns 0 to mean "send no `video_metadata` at all", which reproduces the
    pre-VQA-7 request byte for byte — that is what an unset/zero `requested`
    gets, so a bare `run_ai_review()` call behaves exactly as it always did.

    The duration comes from the scene config already in hand
    (`totalFrames / fps`), not from probing the mp4 — no ffprobe, no second
    source of truth. If the config cannot supply a sane duration the request
    is sent unclamped: guessing a duration would be worse than sending what
    was asked for, and an over-budget request merely fails open.
    """
    try:
        requested = int(requested)
    except (TypeError, ValueError):
        return 0
    if requested <= 0:
        return 0
    requested = min(requested, MAX_REVIEW_FPS)

    try:
        total_frames = float(scene_config.get("totalFrames") or 0)
        config_fps   = float(scene_config.get("fps") or 0)
    except (AttributeError, TypeError, ValueError):
        return requested
    if total_frames <= 0 or config_fps <= 0:
        return requested
    duration = total_frames / config_fps

    per_frame  = _TOKENS_PER_FRAME.get(model, _DEFAULT_TOKENS_PER_FRAME)
    for_audio  = duration * _AUDIO_TOKENS_PER_SEC
    affordable = (_VIDEO_TOKEN_BUDGET - for_audio) / (duration * per_frame)
    # Never clamp below 1: one frame per second is Gemini's own default, so a
    # video too long even for that is already beyond anything this clamp can
    # rescue, and dropping to 0 would silently disable sampling control.
    return max(1, min(requested, int(affordable)))


# What the pipeline deliberately produces (TMDEV-101). Without this the prompt
# states no intended style at all and judges every video against an unstated
# default — which for line art means `animation_defect` ("unclean, misplaced or
# misaligned", wording written around polished vector diagrams) and the
# open-ended escalation clause both firing on the style itself. Under the "any
# finding routes to REVISION_REQUESTED" rule that is not a grading problem:
# every round costs a paid re-voice, so a systematically mis-judged style
# wedges the video.
#
# The canvas and the figures are SEPARATE clauses because they vary
# independently. A video may be dark and full of deliberately held, discretely
# posed figures; composing one "register" string out of the two would either
# license a defect or flag an intended look.
_CANVAS_BLOCKS = {
    "light": """\
- The canvas is deliberately plain white, with black line art at uniform weight, flat fills, and
  one saturated accent colour reserved for the thing each beat is about. This is the intended,
  approved look. Do NOT report it as low quality, unfinished, sparse, placeholder art or a
  rendering fault, and do not suggest adding shading, gradients, texture or detail to it.
- A white or near-white frame is the canvas, not a blank frame. blank_frames means BLACK frames.
- Generated photographs appear inside drawn panels rather than filling the frame. That framing is
  intended; do not report it as a cropping or scaling fault.
""",
    "dark": """\
- The canvas is deliberately dark, with generated imagery running full-bleed and vector diagrams
  drawn over it. Elements should be moving; a scene that holds completely static for more than
  about a third of a second is worth reporting.
""",
}

# Split in two on purpose, because the two clauses have different scopes and
# collapsing them costs money either way.
#
# The discrete-motion clause applies to EVERY register that may contain
# figures, hand-drawn or generated: both pose their characters discretely, so
# both need the reviewer told that a held pose is correct. Without it a held
# pose reads as broken animation, and any finding routes the video to
# REVISION_REQUESTED — so dropping it for a register wedges that register.
#
# The line-art clause is narrower: it licenses *simple line art* as intended
# rather than placeholder. That is true of the stick register, and false of the
# illustrated one, which uses generated character artwork and excludes
# hand-authored line art. Sending it to an illustrated video would license the
# exact mistake the register forbids.
#
# The tempting simplification is to gate the whole thing on line art. Don't:
# the error directions are not symmetric. Over-sending the line-art clause
# costs a missed catch; under-sending the discrete-motion clause costs false
# positives on every illustrated video, which is a paid revision loop.
_DISCRETE_MOTION_BLOCK = """\
- Character figures are an intended element. Their motion is deliberately DISCRETE: a figure holds
  a pose while the narration runs and changes state in a single frame, roughly 2 to 5 times per 10
  seconds. A held pose is correct. An instant pose change with no tween is correct. Do NOT report
  either as jerky, broken, stuttering or missing animation, and do not suggest smoothing or
  in-betweening them.
"""

_LINE_ART_BLOCK = """\
- Where those figures are simple line-art stick figures, that is the intended style, not
  placeholder art. Do NOT report flat, unshaded or minimal figure drawing as low quality, unfinished
  or in need of detail.
"""

_STILL_JUDGE = """\
Still judge, normally and strictly: legibility, text inside the safe zone, whether each scene
communicates the beat its narration is making, sync, audio, and any element that is genuinely
misplaced, overlapping or cut off.
"""


def _register_block(canvas: str, figures: bool = False, line_art: bool = False) -> str:
    """The style contract for what this video was deliberately produced as.

    Empty for an unknown canvas rather than guessing: a wrong contract here is
    worse than none, because it tells the reviewer to accept defects the video
    has no licence to contain.

    `figures` and `line_art` are separate because they are separate
    permissions: an illustrated video has figures but no line art. See the
    blocks above for why collapsing them is not safe in either direction.
    """
    body = _CANVAS_BLOCKS.get((canvas or "").strip())
    if not body:
        return ""
    if figures:
        body += _DISCRETE_MOTION_BLOCK
        if line_art:
            body += _LINE_ART_BLOCK
    return ("INTENDED VISUAL STYLE — read this before judging any visual.\n"
            + body + _STILL_JUDGE + "\n")


def _reference_text_block(script_text: str, tts_text: str) -> str:
    """Build the script-reference section of the prompt (VQA-6).

    Two forms of the same script can be passed, and which of them are
    available changes what the model should conclude from a difference:

    - `script_text` (videos.script) is the authored wording — what the
      burned-in captions show on screen.
    - `tts_text` (videos.tts_text) is the exact string sent to ElevenLabs,
      with inline <respell> tags and pronunciation-lexicon terms already
      substituted in and any <ipa> tag written as "/IPA/", so it can
      legitimately differ word-for-word.

    When both are present and differ, the model is told the difference is
    deliberate — otherwise it reports every respelling as a defect, which is
    the specific false positive this feature has to avoid. When they are
    identical, that is stated outright rather than left implied: an absent
    section makes the model hunt for a difference that does not exist.
    """
    script_text = (script_text or "").strip()
    tts_text = (tts_text or "").strip()

    if script_text and tts_text and script_text != tts_text:
        return (
            "Reference text — this video's script, in two forms:\n\n"
            "AS WRITTEN (the wording the on-screen captions show):\n"
            f"{script_text}\n\n"
            "AS SPOKEN (the exact text the text-to-speech engine was given):\n"
            f"{tts_text}\n\n"
            "The two differ at specific words on purpose: a word is sometimes deliberately\n"
            'respelled to force a correct pronunciation (written "Vhagar", spoken "Vaygar"),\n'
            'or given as an IPA transcription between slashes (spoken "/vɑːˈɡɑːr/") — the engine\n'
            "pronounces it rather than reading it out.\n"
            "A difference between the written and the spoken form is\n"
            "never itself a defect — do not report one.\n"
            "That does not make the audio automatically correct. Still report a mispronunciation\n"
            "when (a) the audio does not actually match the AS SPOKEN form, or (b) it matches it,\n"
            "but that respelling itself yields a pronunciation that is wrong for the real word\n"
            "as written.\n"
            "This exemption covers only the words that actually differ between the two forms.\n"
            "Every other name in the script is judged normally and\n"
            "gets no benefit of the doubt from this section."
        )
    if script_text and tts_text:
        return (
            "Reference text — this video's script, both as written on screen and as given to the\n"
            "text-to-speech engine (the two are identical here, so no pronunciation respelling\n"
            "applies to this video — do not look for a difference between them):\n\n"
            f"{script_text}"
        )
    if script_text:
        return (
            "Reference text — this video's script as written (the wording the on-screen captions\n"
            "show). The exact text given to the text-to-speech engine was not recorded for this\n"
            "video, so a word may have been deliberately respelled in a way you cannot see:\n\n"
            f"{script_text}"
        )
    if tts_text:
        return (
            "Reference text — the exact text the text-to-speech engine was given. Some words may\n"
            'be deliberate respellings of the on-screen wording ("Vaygar" for "Vhagar"), so\n'
            "audio matching this text is correct by design:\n\n"
            f"{tts_text}"
        )
    return (
        "No script reference is available for this video — judge pronunciation against the\n"
        "burned-in captions on screen instead."
    )


def _redact(text: str, api_key: str) -> str:
    """Strip a live API key out of an error string before it's persisted
    anywhere (DB comment, log). Belt-and-braces on top of never sending the
    key as a URL query param in the first place."""
    if not api_key:
        return text
    return text.replace(api_key, "***REDACTED***")


def _review_usage(resp, model: str, sampled_fps) -> dict | None:
    """What the review call cost, for the caller to record: the model, the fps
    actually sent, and Gemini's usageMetadata verbatim. None unless a 200."""
    if getattr(resp, "status_code", None) != 200:
        return None
    try:
        body = resp.json()
    except Exception:
        body = {}
    return {"model": model, "fps": sampled_fps or 1,
            "usageMetadata": body.get("usageMetadata") if isinstance(body, dict) else None}


def _error_result(message: str) -> dict:
    """Shared shape for every fail-open return path below — always includes
    a human-readable `feedback` alongside `error`, so the dashboard panel
    and the comment worker.py posts are never silently empty. Empty
    must_fix/suggestions route the caller the same way a clean review
    would — fail-open by shape, not by a boolean flag."""
    return {
        "overall": "",
        "must_fix": [],
        "suggestions": [],
        "feedback": f"AI review did not run: {message}",
        "error": message,
    }


def _normalize_finding(d, extra_key: str = None, extra_default: str = "",
                        bare_string_field: str = None) -> dict:
    """Normalize one must-fix/suggestion entry to a dict with best-effort
    fields. Gemini may return a well-formed object, a bare string, or
    something malformed (missing keys, wrong types) — none of that may raise
    here or one layer up in worker.py's persistence of these fields, so
    every field is defaulted rather than trusted. `extra_key` is "type" for
    must-fix entries and "area" for suggestions — the one field each shape
    has that the other doesn't. `bare_string_field` is where a bare-string
    entry's text goes: "type" for must-fix (matches the old bare-defect
    behavior), but "description" for suggestions — a bare string is
    free-form critique text, not an `area` label."""
    bare_string_field = bare_string_field or extra_key
    base = {"timestamp": "unknown", "scene": "unknown", "description": "", "suggestedFix": ""}
    if extra_key:
        base[extra_key] = extra_default
    if not isinstance(d, dict):
        result = dict(base)
        if d and bare_string_field:
            result[bare_string_field] = str(d)
        return result
    result = {
        "timestamp":    d.get("timestamp") if isinstance(d.get("timestamp"), str) else "unknown",
        "scene":        d.get("scene") if isinstance(d.get("scene"), str) else "unknown",
        "description":  d.get("description") if isinstance(d.get("description"), str) else "",
        "suggestedFix": d.get("suggestedFix") if isinstance(d.get("suggestedFix"), str) else "",
    }
    if extra_key:
        value = d.get(extra_key)
        result[extra_key] = value if isinstance(value, str) and value else extra_default
    return result


def _normalize_findings(raw, extra_key: str = None, extra_default: str = "",
                         bare_string_field: str = None) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [_normalize_finding(d, extra_key, extra_default, bare_string_field) for d in raw if d]


def _format_feedback(overall: str, must_fix: list[dict], suggestions: list[dict]) -> str:
    """Render the parsed review result as markdown for videos.gemini_feedback
    and the REVISION_REQUESTED comment. Always non-empty. Sections ordered
    Overall -> Must fix -> Suggestions so the most important content
    survives truncation."""
    lines = [f"**Overall:** {overall or 'No overall summary provided.'}", ""]

    lines.append(f"**Must fix ({len(must_fix)}):**")
    if must_fix:
        for d in must_fix:
            loc = f"@ {d['timestamp']}" if d["timestamp"] != "unknown" else "@ unknown time"
            scene = f"scene `{d['scene']}`" if d["scene"] != "unknown" else "scene unknown"
            lines.append(f"- **{d['type']}** {loc} — {scene}")
            if d["description"]:
                lines.append(f"  {d['description']}")
            if d["suggestedFix"]:
                lines.append(f"  Suggested fix: {d['suggestedFix']}")
    else:
        lines.append("No blocking errors found.")
    lines.append("")

    lines.append(f"**Suggestions ({len(suggestions)}):**")
    if suggestions:
        for d in suggestions:
            loc = f"@ {d['timestamp']}" if d["timestamp"] != "unknown" else "@ unknown time"
            scene = f"scene `{d['scene']}`" if d["scene"] != "unknown" else "scene unknown"
            lines.append(f"- **{d['area']}** {loc} — {scene}")
            if d["description"]:
                lines.append(f"  {d['description']}")
            if d["suggestedFix"]:
                lines.append(f"  Suggested fix: {d['suggestedFix']}")
    else:
        lines.append("No improvement suggestions.")

    return "\n".join(lines)


def run_ai_review(video_path: str, scene_config: dict, *,
                   script_text: str = "", tts_text: str = "",
                   model: str = "", fps=0, api_key: str = "",
                   canvas: str = "", figures: bool = False,
                   line_art: bool = False) -> dict:
    """Run a Gemini quality review on a rendered video.

    Args:
        video_path: Absolute path to the .mp4 file on disk.
        scene_config: Parsed scene-config dict (for context in the prompt,
            and for the duration `fps` is clamped against).
        script_text: videos.script — the authored wording shown in captions.
        tts_text: videos.tts_text — the exact text sent to ElevenLabs.
        canvas: the canvas the video was deliberately painted on ("dark" or
            "light"). Templated into the prompt so the reviewer judges against
            the intended look rather than an unstated default. Unknown or blank
            adds nothing, which is the safe direction — a wrong style contract
            licenses real defects.
        line_art: whether those figures may be simple hand-drawn line art.
            False under "illustrated", which uses generated character artwork
            and excludes line art, so the reviewer must not be told line art is
            intended there.
        figures: whether the video may contain character figures, whose held poses
            and single-frame state changes would otherwise read as broken
            animation. Independent of the canvas: a dark video can have them.
            Both are optional (a video voiced before tts_text was recorded
            has none); see _reference_text_block for how each combination is
            presented to the model.
        model: Gemini model id. Arrives as an argument rather than a settings
            read because this module is deliberately DB-free — see
            vqa/tests/test_review_video.py, which copies it into an isolated
            tree as its one real dependency. Empty falls back to env.
        fps: Video sampling rate (VQA-7). 0/unset sends no `video_metadata`
            at all, i.e. Gemini's 1 FPS default and a request byte-identical
            to the pre-VQA-7 one.
        api_key: Gemini credential. Passed in for the same reason as `model`
            — the key now lives in the settings table (TMDEV-73) and this
            module must stay DB-free. Empty falls back to env.

    Returns:
        {"overall": str, "must_fix": list[dict], "suggestions": list[dict], "feedback": str,
         "usage": {"model", "fps", "usageMetadata"} | None}
        `usage` is present whenever Gemini answered 200 — on success AND on a
        reply that failed to parse, which was still billed — so the worker can
        record it (TMDEV-107). The Files API upload is free and never recorded.
        On any error: adds "error": str(e), with "must_fix"/"suggestions" both empty
        (fail-open — the caller treats empty findings the same as a clean review).
    """
    api_key     = api_key or os.environ.get("GEMINI_API_KEY", "")
    # The review model is a settings-table value (ai_review_model) passed in by
    # the caller. AI_REVIEW_MODEL then GEMINI_MODEL remain as env fallbacks —
    # GEMINI_MODEL is documented in docs/infrastructure.md as an override and
    # dropping it here would silently retire it for existing installs.
    # NOT kept in sync with mcp/server.py's mine_youtube_topics: that is a
    # text-only research call with no video, so it has no reason to move when
    # review does.
    model       = (model
                   or os.environ.get("AI_REVIEW_MODEL", "")
                   or os.environ.get("GEMINI_MODEL", "")
                   or "gemini-2.5-flash")
    if not fps:
        fps = os.environ.get("AI_REVIEW_FPS", 0)
    base        = os.environ.get("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
    upload_base = os.environ.get("GEMINI_UPLOAD_BASE", _DEFAULT_UPLOAD_BASE)

    if not api_key:
        return _error_result("Gemini API key not set")

    # Upload video to Gemini Files API
    try:
        with open(video_path, "rb") as fh:
            video_bytes = fh.read()
    except Exception as e:
        return _error_result(_redact(f"Could not read video file: {e}", api_key))

    display_name = os.path.basename(video_path)

    # Step A — start a resumable upload session; the actual upload URL comes
    # back in the `x-goog-upload-url` *response header*, not the JSON body.
    start_headers = {
        "x-goog-api-key": api_key,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(video_bytes)),
        "X-Goog-Upload-Header-Content-Type": "video/mp4",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=300) as client:
            start_resp = client.post(
                f"{upload_base}/files",
                headers=start_headers,
                json={"file": {"display_name": display_name}},
            )
        start_resp.raise_for_status()
        upload_url = start_resp.headers["x-goog-upload-url"]
    except Exception as e:
        return _error_result(_redact(f"Gemini upload failed: {e}", api_key))

    # Step B — send the bytes to the resumable session URL.
    upload_headers = {
        "x-goog-api-key": api_key,
        "Content-Length": str(len(video_bytes)),
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
    }
    try:
        with httpx.Client(timeout=300) as client:
            up_resp = client.post(upload_url, headers=upload_headers, content=video_bytes)
        up_resp.raise_for_status()
        file_info = up_resp.json()["file"]
        file_uri  = file_info["uri"]
        file_name = file_info["name"]
    except Exception as e:
        return _error_result(_redact(f"Gemini upload failed: {e}", api_key))

    # Step C — poll until the file leaves PROCESSING.
    try:
        with httpx.Client(timeout=30) as client:
            for _ in range(_POLL_ATTEMPTS):
                state_resp = client.get(f"{base}/{file_name}", headers={"x-goog-api-key": api_key})
                state_resp.raise_for_status()
                state = state_resp.json().get("state")
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    return _error_result("Gemini file processing failed")
                time.sleep(_POLL_INTERVAL_SECS)
            else:
                return _error_result("Gemini file processing timed out")
    except Exception as e:
        return _error_result(_redact(f"Gemini file status check failed: {e}", api_key))

    # Step D — run the quality review.
    sampling_fps = _effective_fps(fps, scene_config, model)
    prompt = _REVIEW_PROMPT.format(
        top=SAFE_ZONE_TOP,
        bottom=SAFE_ZONE_BOTTOM,
        sampled_fps=sampling_fps or 1,
        register_block=_register_block(canvas, figures, line_art),
        scene_config_json=json.dumps(scene_config, indent=2),
        reference_text_block=_reference_text_block(script_text, tts_text),
    )
    # `video_metadata` is a sibling of `file_data` on the same part, not a key
    # inside it — Google's own docs have shown it nested, which silently fails.
    video_part = {"file_data": {"mime_type": "video/mp4", "file_uri": file_uri}}
    if sampling_fps:
        video_part["video_metadata"] = {"fps": sampling_fps}
    payload = {
        "contents": [{"parts": [video_part, {"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }
    try:
        with httpx.Client(timeout=120) as client:
            rv_resp = client.post(
                f"{base}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json=payload,
            )
    except Exception as e:
        return _error_result(_redact(f"Gemini review failed: {e}", api_key))
    # A 200 was billed whatever happens next, so its usage rides along on
    # every return from here — the caller records it (this module stays
    # DB-free). None only when there was no 200 to bill.
    usage = _review_usage(rv_resp, model, sampling_fps)
    try:
        rv_resp.raise_for_status()
        text   = rv_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError(f"expected a JSON object, got {type(result).__name__}")
    except Exception as e:
        return {**_error_result(_redact(f"Gemini review failed: {e}", api_key)), "usage": usage}

    overall = result.get("overall")
    if not isinstance(overall, str):
        overall = ""

    must_fix    = _normalize_findings(result.get("mustFix", []), extra_key="type", extra_default="unknown")
    suggestions = _normalize_findings(result.get("suggestions", []), extra_key="area", extra_default="video",
                                       bare_string_field="description")

    feedback = _format_feedback(overall, must_fix, suggestions)

    return {"overall": overall, "must_fix": must_fix, "suggestions": suggestions,
            "feedback": feedback, "usage": usage}
