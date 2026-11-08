"""Mascots: the rules shared by the API, the MCP server, the worker and the poller.

A mascot is a library entry whose drawing code is authored once (by an agent, or
shipped in the repo for a builtin) and then reused by videos. The per-video agent
never writes drawing code: it writes a cue track (data), and `cue_errors` is the
check that track must pass. The engine that plays the track is
renderer/remotion/public/mascot/ (driver.js is the ground truth for cue semantics,
walk speed and where the box lands).

Keep this module free of I/O beyond reading a builtin file: it is imported by
every process.
"""
import math
import re
from pathlib import Path

from tubematic_core import jobfiles

MASCOT_STATUSES = ("PENDING", "BUILDING", "IN_REVIEW", "READY", "FAILED")
MAX_MASCOT_ATTEMPTS = 2
MAX_SHEET_RENDERS_PER_ATTEMPT = 6
SHEETS = ("turn", "feels", "act")
# Keep in sync with the feels loop in renderer/remotion/public/mascot/sheet.js
# (pinned by a test).
EMOTIONS = ("neutral", "happy", "excited", "thinking", "idea",
            "surprised", "confused", "sad", "love", "cool")

# What a user sees when the mascot feature is refused for want of a GPU. Worded
# like renderer/api/pipeline.py's CARTOON3D_* copies; the pipeline imports these.
MASCOT_NEEDS_GPU = (
    "Mascots render on the GPU only (on the CPU a 90-second Short would take hours). "
    "The renderer has no working GPU: configure one with `python onboard.py --step gpu`, test it "
    "on the dashboard Settings page under GPU, or turn the mascot off."
)
MASCOT_GPU_UNKNOWN = (
    "Mascots render on the GPU only, and the renderer has not tested its GPU yet (it does so "
    "when it starts, and on Test GPU on the dashboard Settings page). Test it first, then choose "
    "a mascot."
)


# Shown when a mascot is chosen for a Cartoon 3D video. Shared so the API and the
# MCP server refuse in the same words.
MASCOT_NOT_ON_CARTOON_3D = ("Mascots are not available in the Cartoon 3D style (its 3D world "
                            "has no place for a flat watercolour character). Choose another "
                            "visual style, or no mascot.")


class MascotError(ValueError):
    """A mascot, version or path that cannot be used. The message says why."""


# Ids become directory names and are typed by people and agents.
MASCOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _check_id(mascot_id) -> str:
    if not isinstance(mascot_id, str) or not MASCOT_ID_RE.match(mascot_id):
        raise MascotError(f"mascot id {mascot_id!r} must be 1-64 lowercase letters, digits, '-' or '_'")
    return mascot_id


def _check_version(version) -> int:
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise MascotError(f"mascot version {version!r} must be a whole number of 1 or more")
    return version


def mascot_gpu_error(gpu_status: str) -> str:
    """Why a mascot may not be chosen on a renderer whose GPU is in `gpu_status`,
    or "". Only "working" passes; "unknown" gets its own message, since its fix
    is a test, not an install."""
    if gpu_status == "working":
        return ""
    return MASCOT_GPU_UNKNOWN if gpu_status == "unknown" else MASCOT_NEEDS_GPU


def _get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def pickable(row) -> bool:
    """A mascot can be chosen once a version is approved, until it is archived."""
    return (_get(row, "approved_version", 0) or 0) > 0 and not _get(row, "archived", 0)


def resolve_default(con, project_default: str, install_default: str) -> str:
    """The mascot a new video starts with. "none" means no mascot even if the
    install has a default; "" inherits the install default. A result that is
    not pickable (gone, archived, never approved) is "" rather than a fallback
    to something the caller did not choose."""
    project_default = (project_default or "").strip()
    chosen = "" if project_default == "none" else (project_default or (install_default or "").strip())
    if not chosen:
        return ""
    row = con.execute("SELECT approved_version, archived FROM mascots WHERE id = ?", (chosen,)).fetchone()
    return chosen if row is not None and pickable(row) else ""


def builtin_dir(remotion_dir, mascot_id, version) -> Path:
    """`<remotion>/mascot-builtin/<id>/v<N>/`, where a builtin's code ships."""
    _check_id(mascot_id)
    _check_version(version)
    return jobfiles.join_below(remotion_dir, "mascot-builtin", mascot_id, f"v{version}")


def sheet_file(db_dir, mascot_id, version, sheet) -> Path:
    """`<db_dir>/mascots/<id>/v<N>/<sheet>.png`, a rendered model sheet."""
    _check_id(mascot_id)
    _check_version(version)
    if sheet not in SHEETS:
        raise MascotError(f"sheet {sheet!r} must be one of {', '.join(SHEETS)}")
    return jobfiles.join_below(db_dir, "mascots", mascot_id, f"v{version}", f"{sheet}.png")


def code_for(con, remotion_dir, mascot_id, version) -> str:
    """The drawing code of one mascot version. A builtin's lives in its
    versioned repo file (immutable per version), any other in mascot_versions.
    Raises MascotError when the version is missing or empty."""
    _check_id(mascot_id)
    _check_version(version)
    row = con.execute("SELECT builtin FROM mascots WHERE id = ?", (mascot_id,)).fetchone()
    if row is None:
        raise MascotError(f"mascot {mascot_id!r} does not exist")
    if row[0]:
        path = builtin_dir(remotion_dir, mascot_id, version) / "mascot.js"
        try:
            code = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise MascotError(f"builtin mascot {mascot_id!r} has no version {version}") from None
        except OSError as exc:
            raise MascotError(f"builtin mascot {mascot_id!r} version {version} cannot be read: {exc}") from None
    else:
        v = con.execute("SELECT code FROM mascot_versions WHERE mascot_id = ? AND version = ?",
                        (mascot_id, version)).fetchone()
        if v is None:
            raise MascotError(f"mascot {mascot_id!r} has no version {version}")
        code = v[0] or ""
    if not code.strip():
        raise MascotError(f"mascot {mascot_id!r} version {version} has no code")
    return code


# ---------- geometry ----------

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
FPS = 30  # Keep in sync with fps in renderer/remotion/src/Root.tsx.
# Keep in sync with mcp/text_audit.py::SAFE_ZONE.
SAFE_ZONE = {"top": 150, "bottom": 170, "left": 60, "right": 60}

# The engine's canvas (renderer/remotion/public/mascot/frame.html: KIT_W, KIT_H)
# and where the feet stand in it (kit driver.js: FEET_Y = H - 50). The canvas
# already includes the headroom emotes float into, so the box is the whole of it.
# Keep in sync with those files.
BOX_W = 560
BOX_H = 640
FEET_Y = BOX_H - 50

# Walk model, from driver.js. Keep in sync.
DEFAULT_STATE = {"x": 0.8, "y": 0.96, "scale": 1.0, "on": False}   # before any cue
WALK_PX_PER_S = 320
WALK_MIN_S, WALK_MAX_S = 0.5, 3.2
EDGE_PX = BOX_W / 2 + 40       # how far past the edge the feet go to walk on or off

# Cue bounds. x/y are the feet as fractions of the frame; 0..1 is the frame itself.
X_MIN, X_MAX = 0.0, 1.0
Y_MIN, Y_MAX = 0.0, 1.0
# Below 0.4 the character is too small to read on a phone; above 1.2 its 560-wide
# box cannot fit the 960-wide safe zone with room to move.
SCALE_MIN, SCALE_MAX = 0.4, 1.2
LOOKS = ("up", "down", "left", "right", "none")
FACINGS = ("left", "right", "front")
CUE_KEYS = ("frame", "emotion", "x", "y", "scale", "look", "facing", "jump", "on")

# Subtitles.tsx defaults ("absent means enabled"). Keep in sync.
SUBTITLE_POSITION, SUBTITLE_FONT_SIZE = 0.78, 62
SUBTITLE_LINE_HEIGHT, SUBTITLE_LINES, SUBTITLE_PAD_Y = 1.15, 2, 14
# Words wrap, the agent can resize the band, and a reviewer measures it glyph-tight:
# this much clear air above and below the two-line band keeps a box off it.
CAPTION_SAFETY_MARGIN = 40


# The mascot must stand in view (walk-on finished) for this long at least once:
# a walk-on at the very end of the video would pass the "has an on cue" test
# without a viewer ever seeing it.
MIN_REST_FRAMES = FPS


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def box_at(cue_state) -> tuple:
    """The on-screen rectangle (x0, y0, x1, y1) of the mascot canvas with the feet
    at (x, y) frame fractions and the cue `scale`. Emote headroom is inside it."""
    x = cue_state.get("x", DEFAULT_STATE["x"])
    y = cue_state.get("y", DEFAULT_STATE["y"])
    s = cue_state.get("scale", 1.0)
    fx, fy = x * FRAME_WIDTH, y * FRAME_HEIGHT
    return (fx - BOX_W / 2 * s, fy - FEET_Y * s, fx + BOX_W / 2 * s, fy + (BOX_H - FEET_Y) * s)


def caption_band(subtitles):
    """(y0, y1) of the burned-in caption band, or None when captions are off."""
    sub = subtitles if isinstance(subtitles, dict) else {}
    if sub.get("enabled") is False:
        return None
    pos = sub.get("position")
    size = sub.get("fontSize")
    pos = pos if _num(pos) else SUBTITLE_POSITION
    size = size if _num(size) else SUBTITLE_FONT_SIZE
    half = (SUBTITLE_LINES * size * SUBTITLE_LINE_HEIGHT) / 2 + SUBTITLE_PAD_Y + CAPTION_SAFETY_MARGIN
    centre = pos * FRAME_HEIGHT
    return (centre - half, centre + half)


def _inside_safe_zone(box) -> bool:
    return (box[0] >= SAFE_ZONE["left"] and box[2] <= FRAME_WIDTH - SAFE_ZONE["right"]
            and box[1] >= SAFE_ZONE["top"] and box[3] <= FRAME_HEIGHT - SAFE_ZONE["bottom"])


def _hits_band(box, band) -> bool:
    return band is not None and box[1] < band[1] and box[3] > band[0]


def _check_cue_fields(cue, i, total_frames) -> tuple:
    """(errors, frame or None) for one cue's own fields."""
    errs = []
    where = f"cue {i + 1}"
    frame = cue.get("frame")
    ok_frame = isinstance(frame, int) and not isinstance(frame, bool)
    if ok_frame:
        where = f"the cue at frame {frame}"
        if not 0 <= frame < total_frames:
            errs.append(f"{where}: frame must be from 0 to {total_frames - 1} (the video has {total_frames} frames)")
    else:
        errs.append(f"{where}: frame must be a whole number")
    for key in cue:
        if key not in CUE_KEYS:
            errs.append(f"{where}: unknown key {key!r}. Allowed keys: {', '.join(CUE_KEYS)}. "
                        "The mascot never speaks, so there is no talk cue")
    if "emotion" in cue and cue["emotion"] not in EMOTIONS:
        errs.append(f"{where}: emotion {cue['emotion']!r} is not one of {', '.join(EMOTIONS)}")
    for key, lo, hi in (("x", X_MIN, X_MAX), ("y", Y_MIN, Y_MAX), ("scale", SCALE_MIN, SCALE_MAX)):
        if key in cue and not (_num(cue[key]) and lo <= cue[key] <= hi):
            errs.append(f"{where}: {key} must be a number from {lo} to {hi}"
                        + (" (a fraction of the frame, where the feet stand)" if key != "scale" else ""))
    if "look" in cue and cue["look"] not in LOOKS:
        errs.append(f"{where}: look must be one of {', '.join(LOOKS)}")
    if "facing" in cue and cue["facing"] not in FACINGS:
        errs.append(f"{where}: facing must be one of {', '.join(FACINGS)}")
    for key in ("jump", "on"):
        if key in cue and not isinstance(cue[key], bool):
            errs.append(f"{where}: {key} must be true or false")
    return errs, (frame if ok_frame else None)


def _compile(cues, edge_dx=EDGE_PX / FRAME_WIDTH):
    """Port of driver.js `compile`: the states and moves a valid track produces."""
    st = dict(DEFAULT_STATE)
    states = [(-math.inf, dict(st), None)]
    moves = []
    pos_cue = None

    def edge_x(x):
        return -edge_dx if x < 0.5 else 1 + edge_dx

    def moving_at(t):
        m = _move_at(moves, t)
        return None if m is None else _move_pos(m, t)

    for c in sorted(cues, key=lambda c: c["frame"]):
        t = c["frame"] / FPS
        prev = dict(st)
        for k in ("x", "y", "scale", "on"):
            if k in c:
                if c[k] != st[k]:
                    pos_cue = c["frame"]    # the cue that set the rest position, for error messages
                st[k] = c[k]
        here = moving_at(t)
        x0 = y0 = None
        x1, y1 = st["x"], st["y"]
        if st["on"] and not prev["on"] and not here:
            x0, y0 = edge_x(st["x"]), st["y"]
        elif not st["on"] and (prev["on"] or here):
            x0, y0 = here if here else (prev["x"], prev["y"])
            x1, y1 = edge_x(x0), y0
        elif st["on"] and ((not prev["on"] and here) or st["x"] != prev["x"] or st["y"] != prev["y"]):
            x0, y0 = here if here else (prev["x"], prev["y"])
        if x0 is not None:
            d = math.hypot((x1 - x0) * FRAME_WIDTH, (y1 - y0) * FRAME_HEIGHT)
            dur = min(WALK_MAX_S, max(WALK_MIN_S, d / WALK_PX_PER_S))
            edge = any(v < 0 or v > 1 for v in (x0, x1))   # walks on or off across the frame edge
            moves.append({"t0": t, "t1": t + dur, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                          "edge": edge, "cue": c["frame"]})
        states.append((t, dict(st), pos_cue))
    return states, moves


def _move_at(moves, t):
    """The move in progress at time t (the last one started), or None."""
    m = None
    for mv in moves:
        if mv["t0"] <= t:
            m = mv
    return m if m is not None and t < m["t1"] else None


def _move_pos(m, t):
    k = _ease((t - m["t0"]) / (m["t1"] - m["t0"]))
    return (m["x0"] + (m["x1"] - m["x0"]) * k, m["y0"] + (m["y1"] - m["y0"]) * k)


def _ease(k):
    k = min(1.0, max(0.0, k))
    return k * k * (3 - 2 * k)


def boxes_at_frames(cues, frames) -> dict:
    """{frame: box} for each requested frame: where the mascot's canvas sits when
    that frame renders (walking included), or None while it is off screen. `cues`
    must already pass cue_errors. Used by the text-layout audit, which measures
    text at a few frames and asks whether the mascot would stand over it."""
    states, moves = _compile(cues)
    out = {}
    for f in frames:
        t = f / FPS
        st = states[0][1]
        for s in states:
            if s[0] <= t:
                st = s[1]
        m = _move_at(moves, t)
        if m is not None:
            x, y = _move_pos(m, t)
            out[f] = box_at({"x": x, "y": y, "scale": st["scale"]})
        elif st["on"]:
            out[f] = box_at(st)
        else:
            out[f] = None
    return out


def cue_errors(cues, total_frames: int, subtitles=None) -> list:
    """Why a cue track cannot be used, as plain sentences for the agent; [] when it can.

    Checks each cue's fields, then plays the track the way the engine will and
    checks every frame: at rest the mascot's whole box must sit inside the safe
    zone and clear of the caption band; while walking (including onto and off the
    screen, which crosses the edge by design) it must still clear the band. A walk
    is tested along its path, so two clear positions on either side of the band
    are refused. The track must bring the mascot on screen at least once."""
    if not isinstance(cues, list):
        return ["cues must be a list of cue objects"]
    if isinstance(total_frames, bool) or not isinstance(total_frames, int) or total_frames < 1:
        return ["the video has no frames to place a mascot in"]
    errs, seen, good = [], {}, []
    for i, cue in enumerate(cues):
        if not isinstance(cue, dict):
            errs.append(f"cue {i + 1} must be an object like {{\"frame\": 0, \"on\": true, \"x\": 0.5, \"y\": 0.5}}")
            continue
        e, frame = _check_cue_fields(cue, i, total_frames)
        errs += e
        if frame is not None:
            if frame in seen:
                errs.append(f"two cues sit at frame {frame}: merge them into one cue, or move one to a later frame")
            seen[frame] = True
        if not e and frame is not None:
            good.append(cue)
    if errs:
        return errs
    if not any(c.get("on") is True for c in good):
        return ["the mascot never comes on screen: add a cue with \"on\": true, \"x\" and \"y\" to bring it in"]

    band = caption_band(subtitles)
    states, moves = _compile(good)
    reported = set()

    def report(frame, why):
        if (frame, why) not in reported:
            reported.add((frame, why))
            errs.append(why)

    si = 0
    rest_frames = 0
    for f in range(total_frames):
        t = f / FPS
        while si + 1 < len(states) and states[si + 1][0] <= t:
            si += 1
        _, st, state_cue = states[si]
        m = _move_at(moves, t)
        if m is not None:
            x, y = _move_pos(m, t)
            box = box_at({"x": x, "y": y, "scale": st["scale"]})
            if _hits_band(box, band):
                how = ("walk the mascot on or off at a height above the captions" if m["edge"] else
                       "keep both positions on the same side of the captions, or walk the mascot off screen "
                       "and back on above them")
                report(m["cue"], f"the walk started by the cue at frame {m['cue']} passes over the captions "
                       f"(the band is y {band[0]:.0f}-{band[1]:.0f}): {how}")
            elif not m["edge"] and not _inside_safe_zone(box):
                report(m["cue"], f"the walk started by the cue at frame {m['cue']} leaves the safe zone "
                       f"(box x {box[0]:.0f}-{box[2]:.0f}, y {box[1]:.0f}-{box[3]:.0f}; it must stay within "
                       f"x {SAFE_ZONE['left']}-{FRAME_WIDTH - SAFE_ZONE['right']}, "
                       f"y {SAFE_ZONE['top']}-{FRAME_HEIGHT - SAFE_ZONE['bottom']}): a larger scale or a "
                       "position near the edge makes the box too wide, so lower scale or keep x nearer the centre")
        elif st["on"]:
            rest_frames += 1
            box = box_at(st)
            if _hits_band(box, band):
                report(state_cue, f"the cue at frame {state_cue} puts the mascot over the captions "
                       f"(box y {box[1]:.0f}-{box[3]:.0f}, caption band y {band[0]:.0f}-{band[1]:.0f}): "
                       "raise y or lower scale")
            elif not _inside_safe_zone(box):
                report(state_cue, f"the cue at frame {state_cue} puts the mascot outside the safe zone "
                       f"(box x {box[0]:.0f}-{box[2]:.0f}, y {box[1]:.0f}-{box[3]:.0f}; it must stay within "
                       f"x {SAFE_ZONE['left']}-{FRAME_WIDTH - SAFE_ZONE['right']}, "
                       f"y {SAFE_ZONE['top']}-{FRAME_HEIGHT - SAFE_ZONE['bottom']}): move x or y toward the "
                       "centre, or lower scale")
    if rest_frames < MIN_REST_FRAMES:
        errs.append(f"the mascot is not on screen long enough: it must stand in view for at least "
                    f"{MIN_REST_FRAMES} frames (1 second) after walking on, which takes 0.5-3.2 seconds. "
                    "Bring it on earlier")
    return errs
