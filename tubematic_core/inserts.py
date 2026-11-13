"""Insert scenes: the limits, and the rules on a script's insert marks (TMDEV-224).

A video has one MAIN style, which carries the opening, the payoff and the
ending. It may also have a few short INSERT scenes from an insert style (its
pack's `role` is "insert"), shown where the narration reaches what that style
shows best. An insert is one script segment the script marks with
`insert: "<style id>"`; at scene time the insert covers a window inside that
segment, drawn above the main scene and below the captions.

The limits are the user's (TMDEV-223): an insert lasts about 8 seconds at
most, inserts never come back to back, an insert is never the first or the
last scene, and inserts together take at most a third of the video. Back to
back and first/last are enforced on the marks, when the script is written;
the length and the share are measured on the voiced timeline, when the scenes
are written (mcp/inserts.py), with a warning at script time when a marked
segment looks long.

Every number the checks use is here, so the MCP server and the API read one
copy. Free of I/O.
"""
import json
import re

# Pause and pronunciation tags in a segment's voice text; not spoken words.
_MARKUP = re.compile(r"<[^>]*>|\[[^\]]*\]")
# The per-video setting a person chooses: "auto" lets the agent decide whether
# inserts help (it may decide none), "none" forbids them.
INSERT_MODES = ("auto", "none")
DEFAULT_INSERT_MODE = "auto"

# Seconds. The skills aim for TARGET_SECONDS; the validator refuses past
# MAX_SECONDS, which leaves room for a sentence that runs a little long.
TARGET_SECONDS = 8.0
MAX_SECONDS = 9.0
# Inserts together, as a share of totalFrames.
MAX_SHARE = 1 / 3
# Main-style time on each side of an insert, in seconds, so the viewer is back
# in the main style before the next one and an insert never opens or closes the
# video.
MIN_MAIN_GAP_SECONDS = 1.5
# How far an insert's first frame may sit from a word's start, in frames.
WORD_SNAP_FRAMES = 2
# Spoken words per second used to estimate a marked segment's length before it
# is voiced. Measured voices run 2.3 to 2.9; the high end keeps the warning for
# segments that are long at any pace.
WORDS_PER_SECOND = 2.9

# The transitions a main style may name for going into and out of an insert.
# Keep in sync: renderer/remotion/src/inserts/transitions.ts (frames per kind).
TRANSITIONS = ("cut", "dip", "push", "wipe", "glitch")
TRANSITION_FRAMES = {"cut": 0, "dip": 8, "push": 12, "wipe": 12, "glitch": 4}

# Most insert styles one video may use.
MAX_STYLES_PER_VIDEO = 2

REASON_MAX_CHARS = 300


def parse_styles(raw) -> list | None:
    """A stored videos.insert_styles: None while undecided (''), else the list."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, str)]
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def dump_styles(styles) -> str:
    return json.dumps(list(styles))


def mark_of(segment) -> str:
    """The insert style a script segment is marked with, or ""."""
    if not isinstance(segment, dict):
        return ""
    value = segment.get("insert")
    return value.strip() if isinstance(value, str) else ""


def payoff_index(segments, formula_id: str) -> int | None:
    """The index of the segment that opens the payoff: the first segment of the
    formula beat whose role is "payoff", as get_timeline labels it. None when
    the formula has no payoff beat or the script names none."""
    # Imported here: formulas imports visual_styles, which imports this module.
    from . import formulas as tformulas
    payoff = {tformulas.beat_key(name) for name, role in tformulas.beat_roles(formula_id).items()
              if role == "payoff"}
    for i, seg in enumerate(segments if isinstance(segments, list) else []):
        if isinstance(seg, dict) and tformulas.beat_key(seg.get("beat")) in payoff:
            return i
    return None


def mark_errors(segments, *, insert_mode: str, allowed, insert_styles: tuple,
                formula_id: str = "", hosts: bool = True, host_message: str = "") -> list[str]:
    """Why a script's insert marks are refused, or [] when they are fine.

    segments: the script_segments list being written.
    insert_mode: the video's insert_mode.
    allowed: the insert styles the video may use (its stored insert_styles),
        or None while that is undecided.
    insert_styles: every insert style id (visual_styles.INSERT_STYLES).
    formula_id: the formula the script is written in, whose payoff beat
        belongs to the main style.
    hosts, host_message: whether the video's main style takes inserts, and
        why not when it does not.
    """
    if not isinstance(segments, list):
        return []
    marks = [mark_of(s) for s in segments]
    errors = []
    for i, seg in enumerate(segments):
        if isinstance(seg, dict) and "insert" in seg and not isinstance(seg["insert"], str):
            errors.append(f"script_segments[{i}].insert must be a style id string or absent")
    if not any(marks):
        return errors
    if not hosts:
        return errors + [(host_message or "This video's style takes no insert scenes.")
                         + " Remove every segment's insert key."]
    if insert_mode == "none":
        return errors + ["This video's Inserts setting is None: no segment may be marked as an "
                         "insert. Remove every segment's insert key."]
    if allowed is None:
        return errors + ["Inserts are not decided for this video yet: run the tubematic-insert-routing "
                         "skill (choose_inserts) before writing a script with insert segments."]
    for i, mark in enumerate(marks):
        if not mark:
            continue
        if mark not in insert_styles:
            errors.append(f"script_segments[{i}].insert {mark!r} is not an insert style "
                          f"(insert styles: {', '.join(insert_styles)})")
        elif mark not in allowed:
            chosen = ", ".join(allowed) if allowed else "none"
            errors.append(f"script_segments[{i}].insert {mark!r} is not one of this video's insert "
                          f"styles ({chosen})")
    if marks[0]:
        errors.append("The first segment cannot be an insert: the main style carries the opening.")
    if len(marks) > 1 and marks[-1]:
        errors.append("The last segment cannot be an insert: the main style carries the ending.")
    pay = payoff_index(segments, formula_id)
    if pay is not None and marks[pay]:
        errors.append(f"script_segments[{pay}] opens the payoff, which belongs to the main style: it cannot "
                      "be an insert. Mark another segment.")
    for i in range(1, len(marks)):
        if marks[i] and marks[i - 1]:
            errors.append(f"script_segments[{i - 1}] and [{i}] are both inserts: inserts never come "
                          f"back to back. Put a main-style segment between them.")
    return errors


def mark_warnings(segments, speed: float = 1.0) -> list[dict]:
    """Advisory warnings on the marks, as script_checks returns them: a marked
    segment whose words will likely run past TARGET_SECONDS when voiced."""
    out = []
    if not isinstance(segments, list):
        return out
    rate = WORDS_PER_SECOND * (speed if isinstance(speed, (int, float)) and speed > 0 else 1.0)
    for i, seg in enumerate(segments):
        if not mark_of(seg):
            continue
        text = seg.get("voice") if isinstance(seg.get("voice"), str) else ""
        words = len(_MARKUP.sub(" ", text).split())
        if words / rate > TARGET_SECONDS:
            out.append({"id": "insert_long",
                        "message": (f"Segment {i + 1} is an insert of {words} words, about "
                                    f"{words / rate:.0f} seconds voiced. An insert lasts "
                                    f"{TARGET_SECONDS:.0f} seconds at most: shorten the segment, or "
                                    f"cover only its part the insert shows best.")})
    return out
