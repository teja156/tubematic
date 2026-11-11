"""Advisory picture checks: the first frame, and a visible change on each beat
that needs one (TMDEV-215).

The script's formula names which beats are the turn, the re-openings and the
payoff (tubematic_core.formulas.BEAT_ROLES), and the script labels each segment
with its beat. get_timeline hands the scene author each segment's role. These
checks read the scene-config the author wrote and say, as warnings, where the
picture does not follow: a first frame with nothing but a headline or an empty
board on it, and a turn, re-opening or payoff spoken with nothing changing on
screen.

Everything here is computed from data (the scene-config and the timeline),
so it is pure and costs nothing. The data-driven styles describe every
change on screen as data, so both checks apply to them. A mixed-scenes video
is TSX, so only its scene cuts are visible here; its first frame is checked by
the text-layout audit's frame-0 pass (mcp/text_audit.py), which measures the
rendered page. A Cartoon 3D video's cuts live in its own TypeScript, so it is
not checked at all.

Advisory, never a gate: validate_job returns these in "warnings", which never
touch "passed". A picture is a judgement; a check that blocked a render on a
false positive would cost more than the defect it catches. Every threshold
lives in this file.
"""
import re

import bean_explainer
import cartoon
import case_file_story
import storybook_atlas
import system_flow
import terminal_doc
import under_the_hood
import whiteboard
from tubematic_core import formulas as tformulas

# A first frame counts as showing something when a picture element starts by
# this frame: a few frames into an entrance it is already on screen and moving.
FIRST_FRAME_WINDOW = 3
# A turn, re-opening or payoff counts as having a visible change when one
# starts this many frames before the segment's first word, up to this many
# after it (0.1 s before to 0.4 s after, at 30 fps).
CHANGE_LEAD = 3
CHANGE_WINDOW = 12
# How many of a segment's words a warning quotes, so the agent can find it.
QUOTE_WORDS = 6

ROLES_CHECKED = ("turn", "reopen", "payoff")
ROLE_NAMES = {"turn": "turn", "reopen": "re-opening", "payoff": "payoff"}
OPENING = "opening"

MIXED = "scenes"
_STYLES = (system_flow, whiteboard, bean_explainer, terminal_doc, storybook_atlas, under_the_hood,
           case_file_story)

# What each style can do about a beat with nothing changing on screen, in its
# own words. The pack's picture.turn says the same at length.
_CHANGE_FIX = {
    MIXED: "start a new scene on its first word with a visibly different picture",
    system_flow.STYLE_ID: "start a new board there, or a focus, packet or fault event on that word",
    whiteboard.STYLE_ID: "glide to a new region there, or draw a doodle or arrow on that word",
    bean_explainer.STYLE_ID: "cut to a new shot there, or a pose, prop, act, impact or strike on that word",
    terminal_doc.STYLE_ID: "start a new beat there, or a push, bracket, wall or new string on that word",
    storybook_atlas.STYLE_ID: "start a new chapter there, or move the guide, bring a person or prop "
                              "in, or open a plate on that word",
    under_the_hood.STYLE_ID: "start a new plate there, or an outline, arcs, stat or chart on that word",
    case_file_story.STYLE_ID: "cut to a new shot there, a punch in, or the next card part on that word",
}

# Event types that change too little of the frame to count as a visible
# change: a text pill, a small mark, a label, a footnote, a corner pose.
_SUBTLE = {
    system_flow.STYLE_ID: {"chip"},
    bean_explainer.STYLE_ID: {"label", "mark"},
    storybook_atlas.STYLE_ID: {"tag"},
    under_the_hood.STYLE_ID: {"footnote", "pose"},
}
_WHITEBOARD_PICTURES = ("doodle", "arrow")

_TAG = re.compile(r"<[^>]+>|\[[^\]]*\]")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _ints(values) -> list[int]:
    return [v for v in values if _int(v)]


def style_of(config: dict) -> str | None:
    """Which style drew this scene-config: a data-driven style's id, MIXED for
    generated scenes, or None for a config nothing here can read (Cartoon 3D,
    a malformed file)."""
    scenes = config.get("scenes") if isinstance(config, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return None
    for mod in _STYLES:
        if any(isinstance(s, dict) and s.get("src") == mod.SCENE_SRC for s in scenes):
            return mod.STYLE_ID
    # A Cartoon 3D scene is generated TSX named "<video_id>/CartoonShort", so
    # it would otherwise read as mixed scenes.
    if cartoon.is_cartoon(config) or any(
            isinstance(s, dict) and str(s.get("src", "")).rsplit("/", 1)[-1] == "CartoonShort"
            for s in scenes):
        return None
    return MIXED


def _props(config: dict, mod) -> dict:
    for scene in config.get("scenes") or []:
        if isinstance(scene, dict) and scene.get("src") == mod.SCENE_SRC:
            props = (scene.get("props") or {}).get(mod.PROPS_KEY)
            return props if isinstance(props, dict) else {}
    return {}


def _list(d: dict, key: str) -> list:
    v = d.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


# ── segment roles ─────────────────────────────────────────────────────────────

def annotate_segments(timeline_segments: list, script_segments: list, roles: dict) -> list[dict]:
    """The timeline's segments, each with its beat and its picture role.

    roles is {beat name: role} from the video's formula. The first segment is
    the opening. A segment takes its beat's role only when it is the first
    segment of that beat: a long beat split over several segments needs its
    change once, where the beat starts. Returns new dicts; the inputs are not
    changed.
    """
    beats = {s.get("id"): (s.get("beat") or "") for s in script_segments or []
             if isinstance(s, dict)}
    by_key = {tformulas.beat_key(name): role for name, role in roles.items()}
    out, previous, started = [], None, set()
    for seg in timeline_segments or []:
        if not isinstance(seg, dict):
            continue
        beat = beats.get(seg.get("id"), "")
        key = tformulas.beat_key(beat)
        if not out:
            role = OPENING
        elif key and key != previous and key not in started:
            role = by_key.get(key, "")
        else:
            role = ""
        out.append({**seg, "beat": beat, "role": role})
        previous = key
        started.add(key)
    return out


# ── the first frame ───────────────────────────────────────────────────────────

def _first_frame_problem(style: str, config: dict) -> str | None:
    """Why this data-driven video's first frame shows nothing but a headline,
    a blank stage or text, or None when it shows a subject."""
    early = FIRST_FRAME_WINDOW
    if style == system_flow.STYLE_ID:
        boards = _list(_props(config, system_flow), "boards")
        events = _list(boards[0], "events") if boards else []
        within = system_flow.TIMING["openWithin"]  # the renderer draws these half grown on frame 0
        if not any(e.get("type") == "node" and _int(e.get("at")) and e["at"] <= within for e in events):
            return ("board 1 has no node on screen until after frame "
                    f"{within}, so the video opens on the headline alone. Add a node event at frame 0 "
                    "for the component the first sentence names")
    elif style == whiteboard.STYLE_ID:
        regions = _list(_props(config, whiteboard), "regions")
        items = sorted(_list(regions[0], "items"), key=lambda it: it.get("at") if _int(it.get("at")) else 1e9) \
            if regions else []
        first = items[0] if items else {}
        # An arrow joins two earlier items, so it can never be the first.
        if not (first.get("kind") == "doodle" and first.get("at") == 0):
            return ("region 1's first item is not a doodle at frame 0, so the video opens on "
                    "a blank board or on words alone. Make the first item a doodle of the "
                    "first sentence's subject at frame 0")
    elif style == bean_explainer.STYLE_ID:
        shots = _list(_props(config, bean_explainer), "shots")
        events = _list(shots[0], "events") if shots else []
        if not any(e.get("type") in ("pose", "prop") and _int(e.get("frame")) and e["frame"] <= early
                   for e in events):
            return ("the first shot has no pose or prop until after frame "
                    f"{early}, so the video opens on an empty field. Pose the bean on the first word "
                    "and bring in the first sentence's subject as a prop at frame 0")
    elif style == terminal_doc.STYLE_ID:
        beats = _list(_props(config, terminal_doc), "beats")
        events = _list(beats[0], "events") if beats else []
        if not any(_int(e.get("at")) and e["at"] <= early for e in events):
            return (f"beat 1 has nothing on stage until after frame {early}, so the video opens on an "
                    "empty screen. Start the string or number the first sentence names at frame 0")
    elif style == storybook_atlas.STYLE_ID:
        chapters = _list(_props(config, storybook_atlas), "chapters")
        events = _list(chapters[0], "events") if chapters else []
        if not any(e.get("type") != "tag" and _int(e.get("at")) and e["at"] <= early for e in events):
            return (f"nothing moves in chapter 1 until after frame {early}, so the video opens on the "
                    "plaque over a still stage. Walk the guide, bring a person in or the subject's "
                    "prop at frame 0")
    elif style == under_the_hood.STYLE_ID:
        plates = _list(_props(config, under_the_hood), "plates")
        if not plates or not plates[0].get("image"):
            return ("plate 1 has no photograph, so the video opens on a dark panel. Open on the "
                    "photograph of the part the first sentence names")
    return None


def first_frame_warnings(config: dict) -> list[str]:
    """Warnings about a data-driven video's first frame. A mixed-scenes video's
    first frame is checked by the text-layout audit instead."""
    style = style_of(config)
    if style in (None, MIXED):
        return []
    problem = _first_frame_problem(style, config)
    return [f"First frame: {problem}. The first frame should show what the first sentence names, "
            "already moving."] if problem else []


# ── a visible change on each turn, re-opening and payoff ──────────────────────

def change_frames(style: str, config: dict) -> list[int]:
    """Every frame at which something visible starts changing, in this style's
    data: a cut to a new unit or an event that changes the picture."""
    if style == MIXED:
        return _ints(s.get("startFrame") for s in _list(config, "scenes"))
    subtle = _SUBTLE.get(style, set())
    if style == system_flow.STYLE_ID:
        boards = _list(_props(config, system_flow), "boards")
        return _ints([b.get("startFrame") for b in boards]
                     + [e.get("at") for b in boards for e in _list(b, "events")
                        if e.get("type") not in subtle])
    if style == whiteboard.STYLE_ID:
        wb = _props(config, whiteboard)
        regions = _list(wb, "regions")
        frames = [r.get("startFrame") for r in regions] + [wb.get("recapFrame")]
        try:
            frames += [s["start"] for s in whiteboard.schedule(regions, wb.get("recapFrame"))
                       if s["item"].get("kind") in _WHITEBOARD_PICTURES]
        except (KeyError, TypeError):
            pass
        return _ints(frames)
    if style == bean_explainer.STYLE_ID:
        bean = _props(config, bean_explainer)
        shots = _list(bean, "shots")
        return _ints([s.get("start") for s in shots] + [s.get("start") for s in _list(bean, "sections")]
                     + [e.get("frame") for s in shots for e in _list(s, "events")
                        if e.get("type") not in subtle])
    if style == terminal_doc.STYLE_ID:
        beats = _list(_props(config, terminal_doc), "beats")
        return _ints([b.get("start") for b in beats]
                     + [e.get("at") for b in beats for e in _list(b, "events")])
    if style == storybook_atlas.STYLE_ID:
        chapters = _list(_props(config, storybook_atlas), "chapters")
        return _ints([c.get("start") for c in chapters]
                     + [e.get("at") for c in chapters for e in _list(c, "events")
                        if e.get("type") not in subtle])
    if style == under_the_hood.STYLE_ID:
        plates = _list(_props(config, under_the_hood), "plates")
        return _ints([p.get("start") for p in plates]
                     + [e.get("frame") for p in plates for e in _list(p, "events")
                        if e.get("type") not in subtle])
    if style == case_file_story.STYLE_ID:
        frames = []
        for beat in _list(_props(config, case_file_story), "beats"):
            try:
                frames += case_file_story.part_frames(beat)
            except (KeyError, IndexError, TypeError):
                frames.append(beat.get("start"))
        return _ints(frames)
    return []


def _clock(frame: int, fps: int) -> str:
    secs = int(frame // max(1, fps))
    return f"{secs // 60}:{secs % 60:02d}"


def _quote(voice: str) -> str:
    words = _TAG.sub("", voice or "").split()
    text = " ".join(words[:QUOTE_WORDS])
    return text + ("..." if len(words) > QUOTE_WORDS else "")


def change_warnings(config: dict, segments: list, script_segments: list, fps: int) -> list[str]:
    """Warnings for each turn, re-opening and payoff (segments annotated by
    annotate_segments) with nothing visible starting near its first word."""
    style = style_of(config)
    if style is None:
        return []
    frames = sorted(set(change_frames(style, config)))
    voices = {s.get("id"): s.get("voice", "") for s in script_segments or [] if isinstance(s, dict)}
    out = []
    for seg in segments:
        role, start = seg.get("role"), seg.get("startFrame")
        if role not in ROLES_CHECKED or not _int(start):
            continue
        if any(start - CHANGE_LEAD <= f <= start + CHANGE_WINDOW for f in frames):
            continue
        out.append(
            f"The {ROLE_NAMES[role]} at {_clock(start, fps)} (segment {seg.get('id')}, beat "
            f"\"{seg.get('beat')}\": \"{_quote(voices.get(seg.get('id'), ''))}\") has nothing new "
            f"on screen within {CHANGE_WINDOW} frames of its first word (frame {start}). "
            f"{_CHANGE_FIX[style][0].upper()}{_CHANGE_FIX[style][1:]}.")
    return out


def check(config: dict, timeline_segments: list, script_segments: list, roles: dict,
          fps: int) -> list[str]:
    """Every picture warning for one video. roles is the formula's
    {beat: role}; {} for a video with no formula, which then gets the
    first-frame check only."""
    segments = annotate_segments(timeline_segments, script_segments, roles)
    return first_frame_warnings(config) + change_warnings(config, segments, script_segments, fps)
