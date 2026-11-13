"""Code Scenes (TMDEV-239): the checks a Code Scenes insert must pass before
the scene-config is written.

Code Scenes is an insert style only. An insert is one entry of the config's
`inserts`; its `props.codeScenes` holds the language, an optional file name and
tag, and one to four steps timed on the video's frames. A step can change the
code (the card morphs into it), move the highlight, open an error callout under
a line, or show a small output pane with what the code prints. The renderer's
side of this contract is
renderer/remotion/src/scenes/installed/codeScenes/contract.ts.

Keep in sync: LANGS, LIMITS, TIMING, BAND and the font-size rule mirror
contract.ts; both sides run the shared cases in
tests/fixtures/code_scenes_contract.json. The style pack's insert.block is
BAND.

No code runs anywhere: an output pane must be what the code on screen prints,
which the authoring skill keeps small enough to be certain and the AI review
checks against the code (`output_check` is where a real run takes over).

Free of the database and of I/O.
"""
from __future__ import annotations

import math
import unicodedata

import text_fit

SCENE_SRC = "CodeScenes"
PROPS_KEY = "codeScenes"
STYLE_ID = "code_scenes"

ADVANCE = 0.6
LANGS = ("python", "javascript", "typescript", "sql", "c", "java", "go", "rust", "json", "yaml", "html", "css")
LIMITS = {
    "maxSteps": 4, "maxLines": 14, "maxCols": 40, "tagChars": 24, "fileChars": 24, "labelChars": 24,
    "errorChars": 48, "outputLines": 3, "outputChars": 40, "outputLabelChars": 12, "typeChars": 120,
    "minStepGap": 45, "endHold": 30, "maxStillSeconds": 3,
}
TIMING = {"morph": 15, "focus": 8, "callout": 10, "squiggle": 10, "outputStagger": 3, "outputIn": 8,
          "typePerChar": 1}
BAND = (200, 1340)
LAYOUT = {"textWidth": 768, "codeBudget": 650, "maxFont": 40, "lineHeight": 1.4}
# The smallest size the one-line error callout shrinks to (CodeScenes.tsx).
CALLOUT_MIN_FONT = 22
# A step's `at` may sit this many frames from a word's start.
WORD_SNAP_FRAMES = 2
MAX_ERRORS = 12

DATA_KEYS = {"lang", "file", "tag", "steps"}
STEP_KEYS = {"at", "code", "label", "focus", "error", "output", "reveal"}


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def wide_chars(text: str) -> list[str]:
    """Characters that do not take exactly one monospace cell: wide East Asian
    letters, anything outside the Basic Multilingual Plane (emoji), combining
    marks and invisible format characters. The card places every character on
    a column grid and the renderer counts UTF-16 units, so one of these would
    land in the wrong place or shrink the font."""
    return [c for c in text if c not in "\r\n" and (ord(c) > 0xFFFF or unicodedata.east_asian_width(c) in ("W", "F")
            or unicodedata.combining(c) or unicodedata.category(c) in ("Mn", "Me", "Cf")
            or text_fit.unsupported_chars(c))]


def code_lines(code: str) -> list[str]:
    lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


def font_size_for(lines: int, cols: int) -> int:
    """The code's font size: as large as fits the longest line and the line
    count, never above maxFont (contract.ts fontSizeFor)."""
    by_cols = LAYOUT["textWidth"] / (ADVANCE * cols) if cols > 0 else LAYOUT["maxFont"]
    by_rows = LAYOUT["codeBudget"] / (LAYOUT["lineHeight"] * lines) if lines > 0 else LAYOUT["maxFont"]
    return math.floor(min(LAYOUT["maxFont"], by_cols, by_rows))


def type_frames(code: str) -> int:
    return math.ceil(len(code.replace("\n", "")) * TIMING["typePerChar"])


def code_at(steps: list, index: int) -> str:
    for i in range(index, -1, -1):
        s = steps[i] if 0 <= i < len(steps) else None
        if isinstance(s, dict) and isinstance(s.get("code"), str):
            return s["code"]
    return ""


def output_from(steps: list, index: int):
    """The step whose output pane shows at `index`, or None: output belongs to
    the code on screen, so a code change clears it (contract.ts outputAt)."""
    for i in range(index, -1, -1):
        s = steps[i] if isinstance(steps[i], dict) else {}
        if s.get("output"):
            return i
        if isinstance(s.get("code"), str):
            return None
    return None


def output_check(entry: dict) -> list[str]:
    """Whether the output panes show what the code prints. Nothing runs code
    yet, so the AI review checks it from the code (the pack's insert.review);
    a sandboxed run replaces this when it exists."""
    return []


def check_insert(entry: dict, fps: int, word_starts: list[int], words: list[str]) -> list[str]:
    """Every problem with one Code Scenes insert, one sentence each (at most
    MAX_ERRORS), or [] when it may be written. The window itself is checked by
    mcp/inserts.py."""
    start, dur = entry.get("startFrame"), entry.get("durationInFrames")
    if not (_int(start) and _int(dur) and dur > 0):
        return ["The insert needs whole-number startFrame and durationInFrames."]
    props = entry.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    if not isinstance(data, dict):
        return [f"The insert's props must hold {PROPS_KEY!r}: its language and steps."]
    end = start + dur
    errors: list[str] = []

    def err(msg: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(msg)

    extra = set(data) - DATA_KEYS
    if extra:
        err(f"codeScenes has unknown keys {sorted(extra)}; it holds lang, file, tag and steps.")
    if data.get("lang") not in LANGS:
        err(f"codeScenes.lang must be one of {', '.join(LANGS)}. A shell command and its output is a "
            "Terminal Doc insert, not code.")
    for key, cap in (("file", LIMITS["fileChars"]), ("tag", LIMITS["tagChars"])):
        v = data.get(key)
        if v is not None and (not isinstance(v, str) or len(v) > cap):
            err(f"codeScenes.{key} must be text of at most {cap} characters.")
    steps_in = data.get("steps") if isinstance(data.get("steps"), list) else []
    words = [data.get("tag"), data.get("file")]
    for s in steps_in:
        if isinstance(s, dict):
            words.append(s.get("label"))
            if isinstance(s.get("error"), dict):
                words.append(s["error"].get("text"))
            if isinstance(s.get("output"), dict):
                words.append(s["output"].get("label"))
    odd = [c for w in words if isinstance(w, str) for c in text_fit.unsupported_chars(w)]
    if odd:
        err(f"{odd[0]!r} in a tag, file name, label, error message or output label is not a character the card's "
            "fonts draw; use plain Latin text.")
    steps = data.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= LIMITS["maxSteps"]:
        err(f"codeScenes.steps must list 1 to {LIMITS['maxSteps']} steps.")
        return errors
    if not all(isinstance(s, dict) for s in steps):
        err("Every step must be an object {at, code, label, focus, error, output}.")
        return errors
    if not isinstance(steps[0].get("code"), str) or not steps[0]["code"].strip():
        err("Step 1 must hold the code: every later step starts from it.")
        return errors

    snaps = sorted(set(word_starts))
    width = 0
    height = 0
    prev_at = None
    prev_code = None
    moving_until = start
    for i, s in enumerate(steps):
        where = f"Step {i + 1}"
        extra = set(s) - STEP_KEYS
        if extra:
            err(f"{where} has unknown keys {sorted(extra)}.")
        at = s.get("at")
        if not _int(at):
            err(f"{where} needs a whole-number at (a frame of the video).")
            continue
        if i == 0 and at != start:
            err(f"{where} starts at frame {at}; the first step starts with the insert, at its startFrame {start}.")
        if i > 0:
            if prev_at is not None and at - prev_at < LIMITS["minStepGap"]:
                err(f"{where} starts {at - prev_at} frames after step {i}; keep at least {LIMITS['minStepGap']} "
                    f"frames ({LIMITS['minStepGap'] / fps:.1f} s) between steps so each can be read.")
            if at > end - LIMITS["endHold"]:
                err(f"{where} starts at frame {at}, too close to the insert's end ({end}); the last step starts at "
                    f"least {LIMITS['endHold']} frames before it.")
            if snaps and min(abs(at - w) for w in snaps) > WORD_SNAP_FRAMES:
                nearest = min(snaps, key=lambda w: abs(at - w))
                err(f"{where} starts at frame {at}, which is not on a word; put it on the word that names what "
                    f"changes (the nearest word starts at {nearest}).")
        if moving_until is not None and at - moving_until > round(LIMITS["maxStillSeconds"] * fps):
            err(f"Nothing changes for {(at - moving_until) / fps:.1f} s before step {i + 1}; the longest still "
                f"stretch is {LIMITS['maxStillSeconds']} s. Add a step (move the highlight, show the output).")
        code = s.get("code")
        if code is not None:
            if not isinstance(code, str) or not code.strip():
                err(f"{where}: code must be the whole code as text, or left out to keep the code as it was.")
                code = None
            elif "\t" in code:
                err(f"{where}: the code holds a tab; indent with spaces.")
            elif wide_chars(code):
                err(f"{where}: the code holds {wide_chars(code)[0]!r}, which does not take one column of the card "
                    "(an emoji, a wide letter, a combining mark or an invisible character); use plain characters.")
            elif code == prev_code:
                err(f"{where}: the code is the same as before; leave code out of a step that only moves the "
                    "highlight, the error or the output.")
        current = code_at(steps, i)
        lines = code_lines(current)
        if isinstance(code, str):
            if len(lines) > LIMITS["maxLines"]:
                err(f"{where}: the code has {len(lines)} lines; an insert shows at most {LIMITS['maxLines']}. Show "
                    "only the lines the narration is about.")
            long = [n + 1 for n, line in enumerate(lines) if len(line) > LIMITS["maxCols"]]
            if long:
                err(f"{where}: line {long[0]} has {len(lines[long[0] - 1])} characters; a line holds at most "
                    f"{LIMITS['maxCols']}. Break it or shorten the names.")
        width = max(width, *(len(line) for line in lines))
        height = max(height, len(lines))
        label = s.get("label")
        if label is not None and (not isinstance(label, str) or len(label) > LIMITS["labelChars"]):
            err(f"{where}: label must be text of at most {LIMITS['labelChars']} characters.")
        focus = s.get("focus")
        if focus is not None:
            if not isinstance(focus, list) or not focus or not all(_int(n) for n in focus) \
                    or len(set(focus)) != len(focus):
                err(f"{where}: focus lists the line numbers (from 1) the narration is about, each once.")
            elif any(not 1 <= n <= len(lines) for n in focus):
                err(f"{where}: focus names a line the code does not have (it has {len(lines)}).")
        error = s.get("error")
        if error is not None:
            if not isinstance(error, dict) or set(error) != {"line", "match", "text"}:
                err(f"{where}: error is {{line, match, text}}: the line, the characters to underline, the message.")
            elif not _int(error["line"]) or not 1 <= error["line"] <= len(lines):
                err(f"{where}: error.line names a line the code does not have.")
            elif not isinstance(error["match"], str) or not error["match"] \
                    or error["match"] not in lines[error["line"] - 1]:
                err(f"{where}: error.match must be characters on line {error['line']} as written.")
            elif not isinstance(error["text"], str) or not error["text"].strip() \
                    or len(error["text"]) > LIMITS["errorChars"]:
                err(f"{where}: error.text is the message, at most {LIMITS['errorChars']} characters.")
        output = s.get("output")
        if output is not None:
            for problem in _output_errors(output):
                err(f"{where}: {problem}")
        reveal = s.get("reveal")
        moving_until = at + (TIMING["morph"] if i > 0 and isinstance(code, str) else 0)
        if reveal is not None:
            if reveal != "type" or i != 0:
                err(f"{where}: reveal can only be \"type\", on the first step.")
            else:
                chars = len(current.replace("\n", ""))
                if chars > LIMITS["typeChars"]:
                    err(f"Step 1 types {chars} characters; typing is for a line or two (at most "
                        f"{LIMITS['typeChars']}). Show longer code at once.")
                typed_end = at + type_frames(current)
                nxt = steps[1].get("at") if len(steps) > 1 and _int(steps[1].get("at")) else end - LIMITS["endHold"]
                if typed_end > nxt:
                    err(f"Step 1 is still typing at frame {nxt}; type less or start the next step later.")
                moving_until = typed_end
        prev_at, prev_code = at, (code if isinstance(code, str) else prev_code)
    if moving_until is not None and end - moving_until > round(LIMITS["maxStillSeconds"] * fps) + LIMITS["endHold"]:
        err(f"Nothing changes for the last {(end - moving_until) / fps:.1f} s of the insert; add a step or end the "
            "insert sooner.")
    if width and height and font_size_for(height, width) < 32:
        err("The code is too large for the card; show fewer lines or shorter ones.")
    elif width and height:
        # The callout is one line beside the gutter; it shrinks to fit, down to
        # CALLOUT_MIN_FONT (CodeScenes.tsx). The header holds the tag and the
        # step counter with its label on one row.
        fs = font_size_for(height, width)
        text_left = 50 + 24 + round(fs * ADVANCE * 2.6 + 16)
        box = 50 + 980 - text_left - 10 - 40
        for i, s in enumerate(steps):
            e = s.get("error") if isinstance(s, dict) else None
            if isinstance(e, dict) and isinstance(e.get("text"), str) \
                    and not text_fit.fits_at(e["text"], box, CALLOUT_MIN_FONT):
                err(f"Step {i + 1}: error.text does not fit the callout; shorten it (wide letters take more room).")
        tag = data.get("tag") if isinstance(data.get("tag"), str) else ""
        for i, s in enumerate(steps):
            label = s.get("label") if isinstance(s, dict) and isinstance(s.get("label"), str) else ""
            right = (f"{i + 1}/{len(steps)}" + (f" · {label}" if label else "")) if len(steps) > 1 else label
            if text_fit.width(tag.upper(), 40, 2) + text_fit.width(right, 36) + 40 > 980:
                err(f"Step {i + 1}: the tag and the step label do not fit one row above the card; shorten them.")
                break
    for problem in output_check(entry):
        err(problem)
    return errors


def _output_errors(output) -> list[str]:
    if not isinstance(output, dict) or not set(output) <= {"lines", "label"} or "lines" not in output:
        return ["output is {lines, label}: what the code on screen prints, and an optional short label."]
    lines, label = output["lines"], output.get("label")
    out = []
    if not isinstance(lines, list) or len(lines) > LIMITS["outputLines"] \
            or not all(isinstance(x, str) for x in lines):
        out.append(f"output.lines lists at most {LIMITS['outputLines']} lines of text.")
    elif any(len(x) > LIMITS["outputChars"] for x in lines):
        out.append(f"an output line holds at most {LIMITS['outputChars']} characters.")
    elif any(wide_chars(x) for x in lines):
        out.append("an output line holds an emoji or a wide letter, which does not fit one column; use plain "
                   "characters.")
    elif any(x.lstrip().startswith(("$ ", "# ", "> ")) for x in lines):
        out.append("output shows what the code prints, never a shell prompt; a command typed at a terminal is a "
                   "Terminal Doc insert.")
    elif not lines and not (isinstance(label, str) and label.strip()):
        out.append("an output pane with no lines needs a label saying so (\"0 rows\", \"no output\").")
    if label is not None and (not isinstance(label, str) or len(label) > LIMITS["outputLabelChars"]):
        out.append(f"output.label is at most {LIMITS['outputLabelChars']} characters.")
    return out


def insert_step_windows(entry: dict) -> list[tuple[int, int]]:
    """(start, end) of every step of one Code Scenes insert, for the text audit."""
    props = entry.get("props")
    data = props.get(PROPS_KEY) if isinstance(props, dict) else None
    steps = data.get("steps") if isinstance(data, dict) and isinstance(data.get("steps"), list) else []
    ats = [s.get("at") for s in steps if isinstance(s, dict) and _int(s.get("at"))]
    s, d = entry.get("startFrame"), entry.get("durationInFrames")
    end = s + d if _int(s) and _int(d) else 0
    return [(a, b) for a, b in zip(ats, ats[1:] + [end]) if b > a]


def is_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(scenes: list) -> str:
    """CodeScenes is never one of a video's scenes: it is an insert style."""
    if any(is_scene(s) for s in scenes or []):
        return ("CodeScenes is never one of a video's scenes: Code Scenes is an insert style. Put the code in the "
                "config's \"inserts\" list, over a segment the script marks as a code_scenes insert, and build the "
                "scenes in the video's own style.")
    return ""
