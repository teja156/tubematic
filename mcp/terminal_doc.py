"""Terminal Doc (TMDEV-199): the checks a Terminal Doc scene-config must pass
before it is written, so an unattended agent cannot ship a crowded, mistimed,
overflowing or still video.

A Terminal Doc video is one installed `TerminalDoc` scene spanning every frame.
The agent writes `props.terminalDoc`: a skin, beats (cuts) and moves timed to
the narration's word frames, placed in named slots, never in pixels. Where no
shipped move fits, it may write its own move as TSX and list it in
`customMoves`. The renderer's side of this contract is
renderer/remotion/src/scenes/installed/terminalDoc/contract.ts.

Keep in sync: GEOMETRY, SIZES, SLOTS, LIMITS, TIMING, CUSTOM, the catalogues,
max_chars, number_cells, wrap_note and move_frames mirror contract.ts.
mcp/tests/test_terminal_doc.py reads the TypeScript constants and the style
pack, and both sides run the shared cases in
tests/fixtures/terminal_doc_contract.json, so a drift fails a test instead of
a render.

Free of the database and of I/O: the caller passes the config, the narration's
word start frames and words, and the custom moves' source text.
"""
from __future__ import annotations

import math
import re

from bean_explainer import _IMPORT, FORBIDDEN_SOURCE as _BEAN_FORBIDDEN

SCENE_SRC = "TerminalDoc"
PROPS_KEY = "terminalDoc"
STYLE_ID = "terminal_doc"

W, H = 1080, 1920
CELL = 0.6
GEOMETRY = {"safeLeft": 60, "safeRight": 1020}
SIZES = {"s": 40, "m": 64, "l": 96, "xl": 128}
SLOTS = {
    "context": {"y": 384, "top": 230, "bottom": 538, "sizes": ("s", "m")},
    "a": {"y": 640, "top": 538, "bottom": 742, "sizes": ("s", "m", "l", "xl")},
    "b": {"y": 845, "top": 742, "bottom": 947, "sizes": ("s", "m", "l", "xl")},
    "c": {"y": 1050, "top": 947, "bottom": 1152, "sizes": ("s", "m", "l", "xl")},
    "note": {"y": 1248, "top": 1152, "bottom": 1344, "sizes": ("s",)},
    "stage": {"y": 845, "top": 538, "bottom": 1152, "sizes": ("s", "m")},
}
STAGE_BANDS = ("a", "b", "c")
TONES = ("white", "grey", "dim", "red", "blue")
GLOW_TONES = ("red", "blue")
REVEALS = ("scramble", "type", "cut")
SKINS = ("house", "crt")
CUTS = ("hard", "collapse")
MOVES = ("word", "rearrange", "encode", "number", "wall", "grid", "stream", "bracket", "glow", "type", "push",
         "clear", "custom")
LIMITS = {
    "maxBeats": 40,
    "maxEventsPerBeat": 24,
    "maxOnStage": 4,
    "maxStillSeconds": 3,
    "minBeatSeconds": 2,
    "echoWords": 4,
    "noteChars": 36,
    "noteLines": 2,
    "labelChars": 16,
    "boxLabelChars": 12,
    "maxGuesses": 40,
    "minGridRows": 1,
    "maxGridRows": 8,
    "maxOutputLines": 3,
    "minStreamFrames": 30,
    "maxStreamFrames": 150,
    "minPushFrames": 45,
    "maxPushFrames": 450,
    "minPushScale": 1.02,
    "maxPushScale": 1.15,
    "maxCite": 99,
}
TIMING = {
    "reveal": 9,
    "typeRate": 1.6,
    "arc": 16,
    "stagger": 3,
    "encodeHold": 5,
    "encodeOut": 15,
    "lockStart": 6,
    "lockStep": 1.4,
    "rowStep": 4,
    "bracketDraw": 14,
    "glowIn": 10,
    "outputStagger": 2,
    "clearOut": 8,
    "collapse": 8,
    "readMargin": 15,
    "snap": 2,
}
CUSTOM = {"maxMoves": 6, "minFrames": 15, "maxFrames": 240, "maxText": 40}

# Layout facts the renderer's moves use (moves.tsx), checked here so nothing
# drawn runs into the next band.
GRID_LINE = 1.3              # a grid row is size x 1.3 tall
TYPE_OUT_LINE = SIZES["s"] * 1.2
BRACKET = {"gap": 14, "label": 32}
# A number may count up from 0 only over this many frames.
COUNT_FRAMES = (15, 240)

_ID = re.compile(r"^[a-z0-9_]{1,24}$")
_CUSTOM_FILE = re.compile(r"^move-[a-z0-9-]{1,40}$")
_NUMBER = re.compile(r"^[0-9A-Za-z.,:%+\-/ ×x$]+(\^[0-9]{1,3})?$")
_COUNTABLE = re.compile(r"^\d{1,3}(,\d{3})*$|^\d{1,12}$")
# What a custom move's source may not contain: Bean Explainer's list (each one
# multiplied the CPU render time, made frames differ between renders, or
# reached outside the drawing), plus reading the frame itself: a move draws
# from the `t` it is given, which is what lets the preview show four moments
# of it in one picture.
FORBIDDEN_SOURCE = _BEAN_FORBIDDEN + (
    (re.compile(r"\buse(CurrentFrame|VideoConfig)\b"), "useCurrentFrame or useVideoConfig: a move draws from the t it is given"),
    # A move is a pure function of t: state kept between frames differs between
    # the render's parallel tabs and when frames are rendered out of order.
    (re.compile(r"\buse(State|Ref|Effect|LayoutEffect|Reducer)\b|\bset(Timeout|Interval)\b|\brequestAnimationFrame\b"),
     "state, an effect or a timer: a move draws each frame from t alone"),
    # Bean's pattern lets a CSS filter through as `.filter =` or an object key
    # outside an inline style.
    (re.compile(r"\.filter\s*=(?!=)|\bfilter\s*:"), "a CSS or canvas filter: it multiplies the render time"),
    # A move is DOM, so its gradients and filters are CSS strings Bean's
    # SVG-shaped patterns do not see; each one is full-area work per frame.
    (re.compile(r"(?i)-gradient\s*\(|backdrop-?filter|mix-?blend-?mode"),
     "a CSS gradient, backdrop filter or blend mode: it multiplies the render time; use flat colours"),
    (re.compile(r"\bimport\s*\(|\bperformance\s*\.\s*now\b"),
     "a dynamic import or performance.now(): a move imports statically and draws the same frames every render"),
    # Remotion's media and render-control parts reach outside the drawing or
    # hold the render.
    (re.compile(r"\b(Img|Audio|Video|OffthreadVideo|IFrame|Html5Audio|Html5Video|staticFile|delayRender|continueRender|"
                r"cancelRender|prefetch)\b"),
     "a Remotion media or render-control part (Img, Audio, Video, staticFile, delayRender...): a move draws "
     "glyphs and shapes only"),
)
_ALLOWED_IMPORT = re.compile(r"^(react|remotion|\.\./\.\./installed/terminalDoc/(kit|contract))$")
MAX_ERRORS = 12


def is_td_scene(scene) -> bool:
    """Any scene naming TerminalDoc, whatever its type: the use rule must catch a
    mistyped one too."""
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def max_chars(size: str) -> int:
    """Characters that fit across the safe width at a size."""
    return math.floor((GEOMETRY["safeRight"] - GEOMETRY["safeLeft"]) / (SIZES[size] * CELL))


def number_cells(value: str) -> float:
    """Cells a number takes: digits after "^" are an exponent at half size."""
    i = value.find("^")
    return len(value) if i < 0 else i + (len(value) - i - 1) / 2


def wrap_note(text: str) -> list[str]:
    """Greedy word wrap at LIMITS['noteChars']; same rule as contract.ts."""
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= LIMITS["noteChars"]:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def _letters(text: str) -> int:
    return len(text.replace(" ", ""))


def move_frames(e: dict, custom: dict | None = None, from_text: str = "") -> int:
    """How long a move plays out, in frames; same rule as contract.ts's moveFrames."""
    t = e.get("type")
    if t == "word":
        rv = e.get("reveal", "scramble")
        return 1 if rv == "cut" else math.ceil(len(e["text"]) / TIMING["typeRate"]) if rv == "type" else TIMING["reveal"]
    if t == "rearrange":
        n = max(_letters(from_text), _letters(e["text"]), 1)
        return TIMING["arc"] + TIMING["stagger"] * (n - 1)
    if t == "encode":
        n = max(_letters(from_text), 1)
        return TIMING["stagger"] * (n - 1) + TIMING["arc"] + TIMING["encodeHold"] + TIMING["encodeOut"]
    if t == "number":
        if e.get("count"):
            return e["count"]
        # Every glyph but a space and the "^" marker locks, punctuation included.
        n = len(re.sub(r"[ ^]", "", e["value"]))
        return math.ceil(TIMING["lockStart"] + TIMING["lockStep"] * (n - 1)) + 1
    if t == "grid":
        return TIMING["rowStep"] * (len(e["rows"]) - 1) + TIMING["reveal"]
    if t in ("stream", "push"):
        return e["frames"]
    if t == "bracket":
        return TIMING["bracketDraw"] + TIMING["reveal"]
    if t == "glow":
        return TIMING["glowIn"]
    if t == "type":
        return (math.ceil(len(e["text"]) / TIMING["typeRate"]) + TIMING["outputStagger"] * len(e.get("output") or [])
                + TIMING["reveal"])
    if t == "clear":
        return TIMING["clearOut"]
    if t == "custom":
        return ((custom or {}).get(e.get("move")) or {}).get("frames", 0)
    if t == "wall":
        return TIMING["reveal"]
    return 0


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _str(v, n: int | None = None) -> bool:
    return isinstance(v, str) and bool(v.strip()) and (n is None or len(v) <= n)


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def captions_for(pack: dict, skin: str) -> dict:
    """The subtitles a Terminal Doc video gets by default: the pack's captions
    with its skin's changes over them (amber for the CRT skin)."""
    over = ((pack.get("extra") or {}).get("skins") or {}).get(skin, {}).get("captions") or {}
    return {**(pack.get("captions") or {}), **over}


def skin_of(config: dict) -> str:
    """The config's skin, "house" when it names none or it is not one."""
    scenes = config.get("scenes") or []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) if scenes and isinstance(scenes[0], dict) else None
    skin = data.get("skin") if isinstance(data, dict) else None
    return skin if skin in SKINS else "house"


def check_scene_use(visual_style: str, scenes: list) -> str:
    """The whole-video rule: a Terminal Doc video is exactly the one TerminalDoc
    scene, and no other video uses it. "" when the scenes obey it."""
    uses = [s for s in scenes or [] if is_td_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The TerminalDoc scene draws a whole Terminal Doc video and is used only when the video's "
                    "visual_style is terminal_doc (chosen at the topic). Build this video's scenes from the "
                    "other components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Terminal Doc video is exactly one scene: {\"type\": \"generated\", \"source\": \"installed\", "
                "\"src\": \"TerminalDoc\", \"startFrame\": 0, \"durationInFrames\": <totalFrames>, \"props\": "
                "{\"terminalDoc\": {...}}}. Put every beat in its beats.")
    return ""


def custom_move_errors(custom, video_id: str, sources: dict | None) -> tuple[list[str], dict]:
    """Problems with config's customMoves, and the moves by id. `sources` maps
    each src to its file's text, or is None to skip the source checks."""
    errs: list[str] = []
    moves: dict[str, dict] = {}
    if custom is None:
        return errs, moves
    if not isinstance(custom, list) or len(custom) > CUSTOM["maxMoves"]:
        return [f"customMoves must be a list of at most {CUSTOM['maxMoves']} moves."], moves
    for i, c in enumerate(custom):
        where = f"customMoves {i + 1}"
        if not isinstance(c, dict):
            errs.append(f"{where} must be an object.")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not _ID.match(cid) or cid in MOVES or cid in moves:
            errs.append(f"{where}: id {cid!r} must be lowercase letters, digits or _, and not a shipped move's "
                        "or another custom move's name.")
            continue
        src = c.get("src")
        stem = src.split("/", 1)[1] if isinstance(src, str) and "/" in src else ""
        if (not isinstance(src, str) or not _CUSTOM_FILE.match(stem)
                or (video_id and src.split("/", 1)[0] != video_id)):
            errs.append(f"{where} ({cid}): src must be the src write_scene_file returned for this video's "
                        "move-<name> file (\"<video_id>/move-<name>\").")
            continue
        frames = c.get("frames")
        if not (_int(frames) and CUSTOM["minFrames"] <= frames <= CUSTOM["maxFrames"]):
            errs.append(f"{where} ({cid}): frames is how long the move plays, {CUSTOM['minFrames']} to "
                        f"{CUSTOM['maxFrames']}.")
            continue
        text = c.get("text", 0)
        if not _int(text) or not 0 <= text <= CUSTOM["maxText"]:
            errs.append(f"{where} ({cid}): text is the most characters the move is given, 0 to {CUSTOM['maxText']}.")
            continue
        if sources is not None:
            body = sources.get(src)
            if body is None:
                errs.append(f"{where} ({cid}): there is no {src}.tsx; write it with write_scene_file first.")
                continue
            for pattern, why in FORBIDDEN_SOURCE:
                if pattern.search(body):
                    errs.append(f"{where} ({cid}): the move uses {why}.")
            named = [next((g for g in groups if g), "") for groups in _IMPORT.findall(body)]
            bad = [m or '""' for m in named if not _ALLOWED_IMPORT.match(m)]
            if bad:
                errs.append(f"{where} ({cid}): it imports {', '.join(sorted(set(bad)))}; a move imports only react, "
                            "remotion and ../../installed/terminalDoc/kit (or contract).")
            if not re.search(r"export\s+default\b", body):
                errs.append(f"{where} ({cid}): the file must default-export the move component.")
        moves[cid] = {"frames": frames, "text": text}
    return errs, moves


class _El:
    """An element on stage while a beat is checked."""

    def __init__(self, ev: dict, slots: tuple, text: str, size: str, since: int, ends: int):
        self.ev, self.slots, self.text, self.size = ev, slots, text, size
        self.since, self.ends = since, ends          # created at; its move done at
        self.gone = math.inf                         # cleared or taken by another move
        self.bracket: dict | None = None

    def present(self, frame: int) -> bool:
        return self.since <= frame < self.gone


def _final_text(e: dict) -> str:
    t = e.get("type")
    if t == "number":
        return e.get("value", "")
    if t == "stream":
        return e.get("target", "")
    if t == "grid":
        return max(e.get("rows") or [""], key=len)
    if t == "custom":
        return e.get("text", "") or ""
    return e.get("text", "") or ""


def _size_of(e: dict) -> str:
    if e.get("size"):
        return e["size"]
    if e.get("type") == "grid" or e.get("slot") in ("context", "note"):
        return "s"
    return {"number": "xl", "type": "m"}.get(e.get("type"), "l")


def _bottom_of(el: _El) -> float:
    """Where an element's lowest line ends, for a bracket under it."""
    e, px = el.ev, SIZES[el.size]
    if e["type"] == "grid":
        lh = px * GRID_LINE
        top = SLOTS["stage"]["y"] - len(e["rows"]) * lh / 2 + lh / 2
        return top + (len(e["rows"]) - 1) * lh + px * 0.62
    slot = el.slots[0] if len(el.slots) == 1 else "stage"
    y = SLOTS[slot]["y"]
    if e["type"] == "type" and e.get("output"):
        h = px * 1.2 + len(e["output"]) * TYPE_OUT_LINE
        return y + h / 2
    return y + px * 0.62


def check(config: dict, fps: int, word_starts: list[int], words: list[str], video_id: str = "",
          sources: dict | None = None) -> list[str]:
    """Every problem with a Terminal Doc config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. `words` is the narration's text,
    word by word. `sources` maps each custom move's src to the file's text
    (None skips the source checks)."""
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    total = config.get("totalFrames")
    scenes = config.get("scenes") or []
    use = check_scene_use(STYLE_ID, scenes)
    if use:
        return [use]
    scene = scenes[0]
    if scene.get("startFrame") != 0 or scene.get("durationInFrames") != total:
        err(f"The {SCENE_SRC} scene must start at frame 0 and last totalFrames ({total}) frames.")
    scene_props = scene.get("props")
    data = scene_props.get(PROPS_KEY) if isinstance(scene_props, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the skin and the beats."]
    if not _int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    if data.get("skin", "house") not in SKINS:
        err(f"skin must be one of {', '.join(SKINS)}.")
    custom_errs, custom = custom_move_errors(data.get("customMoves"), video_id, sources)
    for e in custom_errs:
        err(e)

    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return not snaps or any(abs(frame - w) <= TIMING["snap"] for w in snaps)

    beats = data.get("beats")
    if not isinstance(beats, list) or not 1 <= len(beats) <= LIMITS["maxBeats"]:
        return errors + [f"beats must list 1 to {LIMITS['maxBeats']} beats."]
    starts = [b.get("start") if isinstance(b, dict) else None for b in beats]
    if not all(_int(v) for v in starts):
        return errors + ["Every beat needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first beat must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Beat starts must increase and stay inside the video."]
    ends = starts[1:] + [total]
    for i, (a, b) in enumerate(zip(starts, ends)):
        if i and not on_word(a):
            err(f"Beat {i + 1} cuts at frame {a}, which is not on a word: start a beat within "
                f"{TIMING['snap']} frames of a word's start.")
        if b - a < LIMITS["minBeatSeconds"] * fps:
            err(f"Beat {i + 1} lasts {b - a} frames; a beat needs at least {LIMITS['minBeatSeconds']} s.")
        cut = beats[i].get("cut", "hard")
        if cut not in CUTS:
            err(f"Beat {i + 1}: cut must be one of {', '.join(CUTS)}.")

    narration = [_norm(w) for w in words]
    echo = LIMITS["echoWords"]
    runs = {tuple(narration[i:i + echo]) for i in range(max(0, len(narration) - echo + 1))}

    def echoes(text: str) -> bool:
        norm = [_norm(w) for w in str(text).split()]
        norm = [w for w in norm if w]
        return any(tuple(norm[k:k + echo]) in runs for k in range(max(0, len(norm) - echo + 1)))

    active: list[tuple[int, int]] = [(s, s + 1) for s in starts]
    for i, beat in enumerate(beats):
        _check_beat(beat, i, starts[i], ends[i], custom, echoes, active, err)

    # Nothing may hold still for long: the look is a held frame with something
    # small changing every few seconds.
    still = round(LIMITS["maxStillSeconds"] * fps)
    reach = 0
    for a, b in sorted(active) + [(total, total)]:
        if a - reach > still:
            err(f"Nothing changes on stage from frame {reach} to {a} ({(a - reach) / fps:.1f} s); the longest "
                f"still stretch allowed is {LIMITS['maxStillSeconds']} s. Add a move, a glow, a bracket or a cut.")
        reach = max(reach, b)
    return errors


def _check_beat(beat, i, start, end, custom, echoes, active, err) -> None:
    where = f"Beat {i + 1}"
    events = beat.get("events")
    if not isinstance(events, list) or len(events) > LIMITS["maxEventsPerBeat"]:
        err(f"{where}: events must be a list of at most {LIMITS['maxEventsPerBeat']}.")
        return
    if not all(isinstance(e, dict) and _int(e.get("at")) for e in events):
        err(f"{where}: every event is an object with a whole-number frame `at`.")
        return
    ats = [e["at"] for e in events]
    if any(b < a for a, b in zip(ats, ats[1:])):
        err(f"{where}: list the events in frame order.")
        return
    els: dict[str, _El] = {}
    pushes = 0
    note_until = -math.inf
    # Slots held by something that is not an element: an encode's box holds b
    # while it plays, a bracket's note holds the note slot to the cut.
    holds: list[tuple[tuple, int, float, str]] = []
    push = next((e for e in events if e.get("type") == "push"), None)
    scale = push.get("scale") if isinstance(push, dict) and _num(push.get("scale")) else 1
    if push and any(e.get("type") == "custom" for e in events):
        err(f"{where}: a push and a move of your own cannot share a beat; the push scales the shipped moves only.")

    def on_stage(frame: int) -> list[_El]:
        return [el for el in els.values() if el.present(frame)]

    def slot_taken(slots: tuple, frame: int, until: float, ignore: tuple = ()) -> str:
        for el in els.values():
            if el.ev.get("id") in ignore or el.gone <= frame or el.since >= until:
                continue
            if set(el.slots) & set(slots):
                return el.ev["id"]
        for held, since, upto, name in holds:
            if since < until and frame < upto and set(held) & set(slots):
                return name
        return ""

    for k, e in enumerate(events):
        t, at = e.get("type"), e["at"]
        what = f"{where}, event {k + 1} ({t})"
        if t not in MOVES:
            err(f"{what}: type must be one of {', '.join(MOVES)}.")
            continue
        if not start <= at < end:
            err(f"{what}: at {at} is outside the beat ({start} to {end - 1}).")
            continue
        try:
            problem = _event_problem(e, t, custom)
        except (KeyError, TypeError, ValueError):
            problem = "is missing a field or has one of the wrong kind; see the contract."
        if problem:
            err(f"{what}: {problem}")
            continue

        if t in ("word", "rearrange", "encode", "number", "grid", "stream", "type", "custom"):
            eid = e.get("id")
            if eid in els:
                err(f"{what}: the id {eid!r} is already used in this beat; give each element its own id.")
                continue
            src_el = None
            from_text = ""
            if t in ("rearrange", "encode"):
                src_el = els.get(e["from"])
                if not src_el or not src_el.present(at):
                    err(f"{what}: from {e['from']!r} is not on stage at frame {at}.")
                    continue
                if at < src_el.ends:
                    err(f"{what}: {e['from']!r} is still playing its own move until frame {src_el.ends}.")
                    continue
                from_text = src_el.text
            size = _size_of(e)
            if t == "grid":
                slots = STAGE_BANDS
            elif t == "rearrange":
                slots = (e.get("slot") or src_el.slots[0],) if len(src_el.slots) == 1 else src_el.slots
                if len(slots) == 1 and size not in SLOTS[slots[0]]["sizes"]:
                    err(f"{what}: it lands in slot {slots[0]}, which takes the sizes "
                        f"{', '.join(SLOTS[slots[0]]['sizes'])}; give it a size or another slot.")
                    continue
            elif e["slot"] == "stage":
                slots = STAGE_BANDS
            else:
                slots = (e["slot"],)
            dur = move_frames(e, custom, from_text)
            if t == "encode":
                if src_el.slots[0] not in ("a", "c") or e["slot"] not in ("a", "c") or e["slot"] == src_el.slots[0]:
                    err(f"{what}: an encode goes from slot a to c or from c to a; the box takes slot b between them.")
                    continue
                busy = slot_taken(("b",), at, at + dur + TIMING["collapse"], ignore=(e["from"],))
                if busy:
                    err(f"{what}: slot b must be empty while the box is on screen, but {busy!r} is there.")
                    continue
            if t == "stream" and e["slot"] not in STAGE_BANDS:
                err(f"{what}: a stream races in slot a, b or c.")
                continue
            if t == "type" and e["slot"] not in STAGE_BANDS:
                err(f"{what}: a typed command goes in slot a, b or c.")
                continue
            if scale > 1 and not _fits_under_push(e, size, scale):
                err(f"{what}: the beat's push scales it by {scale}, and then it is wider than the frame; "
                    "use a smaller size or a smaller push.")
                continue
            busy = slot_taken(slots, at, end, ignore=(e.get("from"),))
            if busy:
                err(f"{what}: slot {'/'.join(slots)} already holds {busy!r} at frame {at}; clear it first or use "
                    "another slot.")
                continue
            if src_el:
                src_el.gone = at
                # Its letters wait in their cells until their turn to fly (and a
                # rearrange fades the letters it does not use in place), so the
                # source slot stays held while they do.
                n_src = max(len(from_text.replace(" ", "")), 1)
                upto = at + (TIMING["stagger"] * (n_src - 1) + TIMING["arc"] if t == "encode" else dur)
                holds.append((src_el.slots, at, upto, f"the letters of {e['from']!r}"))
            if t == "encode":
                holds.append((("b",), at, at + dur + TIMING["collapse"], f"the {e['label']} box"))
            el = _El(e, slots, _final_text(e), size, at, at + dur)
            els[eid] = el
            texts = [e.get("text"), e.get("label"), e.get("sub"), e.get("target"), *(e.get("output") or []),
                     *(e.get("rows") or [])]
            if any(isinstance(x, str) and echoes(x) for x in texts):
                err(f"{what}: its text repeats four or more narration words in a row. The captions carry the "
                    "sentence; the stage shows the string, number or name it is about.")
            if at + dur + TIMING["readMargin"] > end:
                err(f"{what}: it plays until frame {at + dur} and the beat cuts at {end}; start it at least "
                    f"{TIMING['readMargin']} frames before the cut, or move the cut.")
            active.append((at, at + dur))
        elif t == "bracket":
            el = els.get(e["target"])
            if not el or not el.present(at):
                err(f"{what}: target {e['target']!r} is not on stage at frame {at}.")
                continue
            if at < el.ends:
                err(f"{what}: {e['target']!r} is still playing its move until frame {el.ends}; bracket it after.")
                continue
            if el.bracket:
                err(f"{what}: {e['target']!r} already has a bracket.")
                continue
            if echoes(e["label"]) or (e.get("note") and echoes(e["note"])):
                err(f"{what}: the label or note repeats four or more narration words in a row; quote the source, "
                    "not the narration.")
            line_y = _bottom_of(el) + BRACKET["gap"] + BRACKET["label"] * 0.5
            band = el.slots[-1] if len(el.slots) == 1 else "c"
            below = {"context": "a", "a": "b", "b": "c", "c": "note"}.get(band)
            if line_y > SLOTS[band]["bottom"] and below:
                busy = slot_taken((below,), at, end)
                if busy:
                    err(f"{what}: the bracket under {e['target']!r} reaches into slot {below}, which holds {busy!r}; "
                        "use a smaller size or a free slot below.")
                    continue
                holds.append(((below,), at, end, f"the bracket under {e['target']!r}"))
            if e.get("note"):
                if at < note_until:
                    err(f"{what}: another bracket's note is still in the note slot.")
                    continue
                busy = slot_taken(("note",), at, end)
                if busy:
                    err(f"{what}: the note slot holds {busy!r}; a bracket's note goes there.")
                    continue
                note_until = end
                holds.append((("note",), at, end, "a bracket's note"))
            if scale > 1 and BRACKET["label"] * CELL * len(e["label"]) * scale > GEOMETRY["safeRight"] - GEOMETRY["safeLeft"]:
                err(f"{what}: the beat's push makes the label wider than the frame.")
                continue
            el.bracket = e
            dur = move_frames(e)
            if at + dur + TIMING["readMargin"] > end:
                err(f"{what}: it draws until frame {at + dur} and the beat cuts at {end}; start it earlier.")
            active.append((at, at + dur + (len(e.get("note") or "") // 3 if e.get("note") else 0)))
        elif t == "glow":
            el = els.get(e["target"])
            if not el or not el.present(at):
                err(f"{what}: target {e['target']!r} is not on stage at frame {at}.")
                continue
            if at < el.ends:
                err(f"{what}: {e['target']!r} is still playing its move until frame {el.ends}; glow it after.")
                continue
            if el.ev["type"] in ("type", "custom"):
                err(f"{what}: a typed command or a move of your own cannot glow; glow a word, number or string.")
                continue
            if "span" in e and el.ev["type"] == "number" and "^" in el.ev["value"]:
                err(f"{what}: span cannot pick out part of a number with an exponent; glow the whole number.")
                continue
            if "row" in e and (el.ev["type"] != "grid" or not _int(e["row"]) or not 0 <= e["row"] < len(el.ev["rows"])):
                err(f"{what}: row names a row of a grid, from 0.")
                continue
            if "span" in e:
                sp = e["span"]
                text = el.ev["rows"][e.get("row", 0)] if el.ev["type"] == "grid" else el.text
                if (not isinstance(sp, list) or len(sp) != 2 or not all(_int(v) for v in sp)
                        or not 0 <= sp[0] < sp[1] <= len(text)):
                    err(f"{what}: span is [first, last + 1] character positions inside the text.")
                    continue
            active.append((at, at + TIMING["glowIn"]))
        elif t == "clear":
            for tid in e["targets"]:
                el = els.get(tid)
                if not el or not el.present(at):
                    err(f"{what}: {tid!r} is not on stage at frame {at}.")
                    continue
                el.gone = at + TIMING["clearOut"]
            active.append((at, at + TIMING["clearOut"]))
        elif t == "push":
            pushes += 1
            if pushes > 1:
                err(f"{what}: one push per beat.")
                continue
            active.append((at, min(end, at + e["frames"])))
        elif t == "wall":
            active.append((at, at + TIMING["reveal"]))

        # Restraint: the frame is mostly empty.
        present = on_stage(at)
        count = len(present) + (1 if at < note_until else 0)
        if count > LIMITS["maxOnStage"]:
            err(f"{where}: {count} elements are on screen at frame {at}; at most {LIMITS['maxOnStage']}, the context "
                "line and a note included. Clear one first: the look is a mostly empty frame.")


def _fits(text: str, size: str, cells: float | None = None) -> bool:
    return (cells if cells is not None else len(text)) <= max_chars(size)


def _fits_under_push(e: dict, size: str, scale: float) -> bool:
    """Whether every line an element draws still fits the safe width once the
    beat's push has scaled it about the frame's centre."""
    width = GEOMETRY["safeRight"] - GEOMETRY["safeLeft"]
    rows: list[tuple[float, str]] = []
    t = e["type"]
    if t == "number":
        rows.append((number_cells(e["value"]), size))
    elif t == "grid":
        rows += [(len(r), size) for r in e["rows"]]
    elif t == "stream":
        rows += [(len(x), size) for x in [*e["guesses"], e["target"]]]
    elif t == "type":
        rows += [(len(e["text"]) + 2, size), *[(len(o), "s") for o in e.get("output") or []]]
    elif t != "custom":
        rows.append((len(e["text"]), size))
    return all(cells * CELL * SIZES[sz] * scale <= width for cells, sz in rows)


def _event_problem(e: dict, t: str, custom: dict) -> str:
    """What is wrong with one event on its own, or ""."""
    def size_ok(slot: str, default: str) -> str:
        size = e.get("size", default)
        if size not in SIZES:
            return f"size must be one of {', '.join(SIZES)}."
        if slot in SLOTS and size not in SLOTS[slot]["sizes"]:
            return f"slot {slot} takes the sizes {', '.join(SLOTS[slot]['sizes'])}."
        return ""

    if t in ("word", "rearrange", "encode", "number", "grid", "stream", "type", "custom"):
        if not isinstance(e.get("id"), str) or not _ID.match(e["id"]):
            return "id must be lowercase letters, digits or _ (at most 24)."
        if "tone" in e and e["tone"] not in TONES:
            return f"tone must be one of {', '.join(TONES)}."
    if t in ("word", "encode", "number", "stream", "type", "custom") or (t == "rearrange" and "slot" in e):
        if e.get("slot") not in SLOTS:
            return f"slot must be one of {', '.join(SLOTS)}."
    slot = e.get("slot")
    if t == "word":
        if slot == "stage":
            return "a word goes in one slot, not the whole stage."
        if not _str(e.get("text")):
            return "text must be non-empty."
        p = size_ok(slot, _size_of(e))
        if p:
            return p
        if not _fits(e["text"], _size_of(e)):
            return f"{e['text']!r} is wider than the frame at size {_size_of(e)} (at most {max_chars(_size_of(e))} characters)."
        if e.get("reveal", "scramble") not in REVEALS:
            return f"reveal must be one of {', '.join(REVEALS)}."
        if "accent" in e and (not _str(e["accent"]) or e["accent"] not in e["text"]):
            return "accent must be part of the text."
    elif t in ("rearrange", "encode"):
        if not _str(e.get("text")) or not isinstance(e.get("from"), str):
            return "it needs from (the element whose letters move) and text (what they become)."
        size = _size_of(e)
        if slot == "stage" or (slot and size_ok(slot, size)):
            return "it goes in slot a, b or c." if slot == "stage" else size_ok(slot, size)
        if not _fits(e["text"], size):
            return f"{e['text']!r} is wider than the frame at size {size} (at most {max_chars(size)} characters)."
        if t == "encode":
            if not _str(e.get("label"), LIMITS["boxLabelChars"]):
                return f"label (the box's operation, like HASH) is 1 to {LIMITS['boxLabelChars']} characters."
            if "sub" in e and not _str(e["sub"], LIMITS["boxLabelChars"]):
                return f"sub is 1 to {LIMITS['boxLabelChars']} characters."
    elif t == "number":
        v = e.get("value")
        if not isinstance(v, str) or not _NUMBER.match(v) or not v.strip():
            return "value is the number as text: digits, separators, a unit, and an optional ^exponent at the end."
        if slot == "stage":
            return "a number goes in one slot."
        p = size_ok(slot, _size_of(e))
        if p:
            return p
        if not _fits(v, _size_of(e), number_cells(v)):
            return f"{v!r} is wider than the frame at size {_size_of(e)}."
        if "count" in e and (not _int(e["count"]) or not COUNT_FRAMES[0] <= e["count"] <= COUNT_FRAMES[1]
                             or not _COUNTABLE.match(v)):
            return (f"count ({COUNT_FRAMES[0]} to {COUNT_FRAMES[1]} frames) counts a whole number up from 0; "
                    "the value must be digits, with commas or none.")
    elif t == "grid":
        rows = e.get("rows")
        size = e.get("size", "s")
        if not isinstance(rows, list) or not LIMITS["minGridRows"] <= len(rows) <= LIMITS["maxGridRows"] \
                or not all(_str(r) for r in rows):
            return f"rows lists {LIMITS['minGridRows']} to {LIMITS['maxGridRows']} non-empty strings."
        p = size_ok("stage", size)
        if p:
            return p
        if any(not _fits(r, size) for r in rows):
            return f"a row is wider than the frame at size {size} (at most {max_chars(size)} characters)."
        if len(rows) * SIZES[size] * GRID_LINE > SLOTS["stage"]["bottom"] - SLOTS["stage"]["top"]:
            return f"{len(rows)} rows at size {size} are taller than the stage; use fewer rows or size s."
    elif t == "stream":
        g, target, size = e.get("guesses"), e.get("target"), _size_of(e)
        if not isinstance(g, list) or not 1 <= len(g) <= LIMITS["maxGuesses"] or not all(_str(x) for x in g):
            return f"guesses lists 1 to {LIMITS['maxGuesses']} non-empty strings."
        if not _str(target):
            return "target is the string the stream locks on."
        if size not in ("m", "l"):
            return "a stream is size m or l."
        if any(not _fits(x, size) for x in [*g, target]):
            return f"a guess is wider than the frame at size {size} (at most {max_chars(size)} characters)."
        if not _int(e.get("frames")) or not LIMITS["minStreamFrames"] <= e["frames"] <= LIMITS["maxStreamFrames"]:
            return f"frames is how long the race runs, {LIMITS['minStreamFrames']} to {LIMITS['maxStreamFrames']}."
    elif t == "bracket":
        if not isinstance(e.get("target"), str):
            return "target names the element the bracket goes under."
        if not _str(e.get("label"), LIMITS["labelChars"]):
            return f"label is 1 to {LIMITS['labelChars']} characters."
        if "tone" in e and e["tone"] not in TONES:
            return f"tone must be one of {', '.join(TONES)}."
        if "note" in e:
            cite = e.get("cite")
            text = f"{e['note']} [{cite}]" if cite is not None else e.get("note")
            if not _str(e["note"]) or len(wrap_note(text)) > LIMITS["noteLines"]:
                return f"note wraps to more than {LIMITS['noteLines']} lines of {LIMITS['noteChars']} characters."
        if "cite" in e and (not _int(e["cite"]) or not 1 <= e["cite"] <= LIMITS["maxCite"] or "note" not in e):
            return f"cite is a whole number 1 to {LIMITS['maxCite']}, on a bracket with a note."
    elif t == "glow":
        if not isinstance(e.get("target"), str):
            return "target names the element that glows."
        if e.get("tone") not in GLOW_TONES:
            return f"tone must be one of {', '.join(GLOW_TONES)}."
    elif t == "type":
        size = _size_of(e)
        outs = e.get("output", [])
        if not _str(e.get("text")):
            return "text is the command."
        if size not in ("s", "m"):
            return "a typed command is size s or m."
        if not _fits("$ " + e["text"], size):
            return f"the command is wider than the frame at size {size} (at most {max_chars(size) - 2} characters)."
        if not isinstance(outs, list) or len(outs) > LIMITS["maxOutputLines"] or not all(_str(o) for o in outs):
            return f"output lists at most {LIMITS['maxOutputLines']} lines."
        if any(not _fits(o, "s") for o in outs):
            return f"an output line is wider than the frame (at most {max_chars('s')} characters)."
        if slot in STAGE_BANDS and SIZES[size] * 1.2 + len(outs) * TYPE_OUT_LINE > SLOTS[slot]["bottom"] - SLOTS[slot]["top"]:
            return "the command and its output are taller than the slot; use size s or fewer output lines."
    elif t == "push":
        if not _int(e.get("frames")) or not LIMITS["minPushFrames"] <= e["frames"] <= LIMITS["maxPushFrames"]:
            return f"frames is {LIMITS['minPushFrames']} to {LIMITS['maxPushFrames']}."
        if not _num(e.get("scale")) or not LIMITS["minPushScale"] <= e["scale"] <= LIMITS["maxPushScale"]:
            return f"scale is {LIMITS['minPushScale']} to {LIMITS['maxPushScale']}: a slow push, not a zoom."
    elif t == "clear":
        if not isinstance(e.get("targets"), list) or not e["targets"] or not all(isinstance(x, str) for x in e["targets"]):
            return "targets lists the ids to clear."
    elif t == "wall":
        if e.get("level") not in (0, 1, 2) or isinstance(e.get("level"), bool):
            return "level is 0 (off), 1 (faint) or 2 (bright)."
    elif t == "custom":
        spec = custom.get(e.get("move"))
        if not spec:
            return "move names one of the video's customMoves."
        if slot not in STAGE_BANDS + ("stage",):
            return "a custom move goes in slot a, b, c or stage."
        text = e.get("text", "")
        if not isinstance(text, str) or len(text) > spec["text"]:
            return f"text is at most {spec['text']} characters for this move."
    return ""


def beat_windows(config: dict) -> list[tuple[int, int]]:
    """(start, end) of every beat of a Terminal Doc config, for the text-layout
    audit to sample each like a scene. [] when the config is not one."""
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_td_scene(scenes[0]):
        return []
    data = (scenes[0].get("props") or {}).get(PROPS_KEY) or {}
    starts = [b.get("start") for b in data.get("beats") or [] if isinstance(b, dict) and _int(b.get("start"))]
    total = config.get("totalFrames") if _int(config.get("totalFrames")) else 0
    return [(a, b) for a, b in zip(starts, starts[1:] + [total]) if b > a]
