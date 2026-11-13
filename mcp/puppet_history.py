"""Puppet History (TMDEV-232): the checks a Puppet History scene-config must
pass before it is written, so an unattended agent cannot ship a mistimed,
crowded, off-map or still video.

A Puppet History video is one installed `PuppetHistory` scene spanning every
frame. `props.puppetHistory` holds the cast (house puppets in era costumes,
an optional name plate each) and the beats, joined by hard cuts: a set where
puppets enter, act, swap costumes, hold props and signs on the narration's
words; a document card with stamps and strike-outs; a flat map of today's
countries where regions fill in, arrows grow and labels appear. The
renderer's side of this contract is
renderer/remotion/src/scenes/installed/puppetHistory/contract.ts and stage.ts.

Keep in sync: the constants and catalogues mirror contract.ts;
mcp/tests/test_puppet_history.py compares them with
tests/fixtures/puppet_history_contract.json, which
renderer/remotion/character-tools/sync-contract.mjs writes from the
TypeScript. The country list comes from the pack's `extra` (written by the
same script from world-atlas).

Free of the database and of I/O.
"""
from __future__ import annotations

import re

import character_kit as ck
from quiet_windows import uncovered, window_at, window_text

SCENE_SRC = "PuppetHistory"
PROPS_KEY = "puppetHistory"
STYLE_ID = "puppet_history"
LIBRARY_KEY = "props"

LIMITS = {"maxCast": 4, "maxBeats": 14, "maxEvents": 100, "nameChars": 18, "signChars": 14, "stampChars": 10,
          "dateChars": 12, "titleChars": 22, "cardLines": 5, "lineChars": 26, "strikeChars": 12, "labelChars": 18,
          "maxFocus": 8, "maxArrows": 6, "maxStillSeconds": 3, "minBeatSeconds": 1.5, "echoWords": 5}
TIMING = {"slide": 16, "pop": 8, "move": 16, "minActorGap": 6, "stamp": 7, "strike": 14, "fill": 12, "arrow": 18,
          "endMargin": 6}
SLOTS = 3
SLOT_X = (210, 540, 870)
W = 1080
SIGN_EDGE = 20
POSES = ("stand", "point", "salute", "wave", "shrug", "hold", "cheer", "panic", "think", "sign")
FACES = ("stern", "happy", "proud", "worried", "shock", "sad", "smug", "angry")
COSTUMES = ("plain", "dress", "peasant", "farmer", "worker", "clerk", "noble", "royal", "knight", "legionary",
            "soldier_1910s", "soldier_1940s", "sailor", "pilot", "explorer", "scientist", "monk")
SETS = ("farm", "street", "office", "palace", "castle", "deck", "market", "factory", "camp", "lab", "classroom", "field")
STAMP_COLORS = ("red", "green", "blue")
FILLS = ("red", "blue", "green", "yellow", "purple", "grey")
ENTRANCES = ("slide", "pop", "cut")
BEAT_TYPES = ("set", "card", "map")
EVENT_TYPES = ("enter", "move", "exit", "act", "swap", "sign", "hold", "stamp", "date", "strike", "fill", "arrow", "label")
BEAT_EVENTS = {
    "set": ("enter", "move", "exit", "act", "swap", "sign", "hold", "stamp", "date"),
    "map": ("enter", "move", "exit", "act", "swap", "sign", "hold", "fill", "arrow", "label", "date"),
    "card": ("stamp", "strike", "date"),
}
CUSTOM = {"maxProps": 6, "minSide": 50, "maxSide": 300, "maxText": 10, "maxActs": 0}
ACTOR_EVENTS = ("enter", "move", "exit", "act", "swap", "sign", "hold")
_ALLOWED_IMPORT = re.compile(r"^(react|remotion|\.\./\.\./installed/puppetHistory/(ink|contract))$")
_ALLOWED_TEXT = "react, remotion and ../../installed/puppetHistory/ink (or contract)"
_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

SNAP_FRAMES = 2
MAX_ERRORS = 12
CHANGE_FIX = "cut to the next beat there, or have a puppet enter, act, swap costume, hold up a sign or a prop, or a stamp land on that word"


def is_scene(scene) -> bool:
    return isinstance(scene, dict) and scene.get("src") == SCENE_SRC


def check_scene_use(visual_style: str, scenes: list) -> str:
    uses = [s for s in scenes or [] if is_scene(s)]
    if (visual_style or "").strip() != STYLE_ID:
        if uses:
            return ("The PuppetHistory scene draws a whole Puppet History video and is used only when the video's "
                    "visual_style is puppet_history (chosen at the topic). Build this video's scenes from the other "
                    "components.")
        return ""
    if (len(scenes or []) != 1 or not uses or uses[0].get("type") != "generated"
            or uses[0].get("source") != "installed"):
        return ("A Puppet History video is exactly one scene: {\"type\": \"generated\", \"source\": \"installed\", "
                "\"src\": \"PuppetHistory\", \"startFrame\": 0, \"durationInFrames\": <totalFrames>, \"props\": "
                "{\"puppetHistory\": {...}}}. Put every beat in its beats.")
    return ""


def custom_prop_errors(custom, video_id: str, library: dict, sources: dict | None):
    return ck.custom_prop_errors(custom, video_id, library, sources, CUSTOM, _ALLOWED_IMPORT, _ALLOWED_TEXT)


def sign_width(text: str) -> int:
    return max(160, len(text) * 34 + 60)


def sign_x(slot: int, text: str) -> float:
    """A sign's centre (contract.ts signX): on its puppet, pulled in from the frame's edges."""
    half = sign_width(text) / 2
    return min(max(SLOT_X[slot], SIGN_EDGE + half), W - SIGN_EDGE - half)


def _sign_clash(on: dict) -> tuple[str, str] | None:
    """Two puppets on stage whose held signs overlap, or None."""
    held = [(who, p["slot"], p["sign"]) for who, p in on.items() if p["sign"] and p.get("gone") is None]
    for i, (a, sa, ta) in enumerate(held):
        for b, sb, tb in held[i + 1:]:
            if abs(sign_x(sa, ta) - sign_x(sb, tb)) < (sign_width(ta) + sign_width(tb)) / 2 - 8:
                return a, b
    return None


def _text_ok(v, limit: int, empty: bool = False) -> bool:
    return isinstance(v, str) and len(v) <= limit and (empty or bool(v.strip()))


def check(config: dict, fps: int, word_starts: list[int], words: list[str], extra: dict,
          video_id: str = "", sources: dict | None = None, quiet=()) -> list[str]:
    """Every problem with a Puppet History config, one sentence each (at most
    MAX_ERRORS), or [] when it may be written."""
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
    sp = scene.get("props")
    data = sp.get(PROPS_KEY) if isinstance(sp, dict) else None
    if not isinstance(data, dict):
        return errors + [f"The scene's props must hold {PROPS_KEY!r}: the cast and the beats."]
    if not ck.is_int(total) or total <= 0:
        return errors + ["totalFrames must be a positive whole number."]
    custom_errs, catalog, _ = custom_prop_errors(data.get("customProps"), video_id, extra[LIBRARY_KEY], sources)
    for e in custom_errs:
        err(e)
    countries = set(extra.get("countries") or ())
    snaps = sorted(set(word_starts))

    def on_word(frame: int) -> bool:
        return frame == 0 or not snaps or any(abs(frame - w) <= SNAP_FRAMES for w in snaps)

    cast = data.get("cast")
    if not isinstance(cast, list) or not 1 <= len(cast) <= LIMITS["maxCast"]:
        return errors + [f"cast must list 1 to {LIMITS['maxCast']} puppets."]
    cast_ids: set[str] = set()
    for i, c in enumerate(cast):
        where = f"cast {i + 1}"
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not _ID.match(c["id"]) or c["id"] in cast_ids:
            err(f"{where}: id must be a unique lowercase name starting with a letter.")
            continue
        cast_ids.add(c["id"])
        if c.get("costume") not in COSTUMES:
            err(f"{where} ({c['id']}): costume must be one of {', '.join(COSTUMES)}.")
        if "name" in c and not _text_ok(c["name"], LIMITS["nameChars"]):
            err(f"{where} ({c['id']}): name must be text of 1 to {LIMITS['nameChars']} characters.")

    beats = data.get("beats")
    if not isinstance(beats, list) or not 1 <= len(beats) <= LIMITS["maxBeats"]:
        return errors + [f"beats must list 1 to {LIMITS['maxBeats']} beats."]
    starts = [b.get("start") if isinstance(b, dict) else None for b in beats]
    if not all(ck.is_int(s) for s in starts):
        return errors + ["Every beat needs a whole-number start frame."]
    if starts[0] != 0:
        err("The first beat must start at frame 0.")
    if any(b <= a for a, b in zip(starts, starts[1:])) or starts[-1] >= total:
        return errors + ["Beat starts must increase and stay inside the video."]
    if sum(len(b.get("events") or []) for b in beats if isinstance(b.get("events"), list)) > LIMITS["maxEvents"]:
        err(f"A video has at most {LIMITS['maxEvents']} events across its beats.")

    runs = ck.echo_runs(words, LIMITS["echoWords"])
    changes: set[int] = set(starts)
    for bi, beat in enumerate(beats):
        start = starts[bi]
        end = starts[bi + 1] if bi + 1 < len(beats) else total
        where = f"Beat {bi + 1}"
        if bi and not on_word(start):
            err(f"{where} starts at frame {start}, which is not on a word.")
        w = window_at(start, quiet) if bi else None
        if w:
            err(f"{where} starts inside an insert ({window_text(w)}); start it at {w[1]} or before {w[0]}.")
        if end - start < LIMITS["minBeatSeconds"] * fps:
            err(f"{where} lasts {end - start} frames; a beat needs at least {LIMITS['minBeatSeconds']} s.")
        kind = beat.get("type")
        if kind not in BEAT_TYPES:
            err(f"{where}: type must be one of {', '.join(BEAT_TYPES)}.")
            continue
        focus: set[str] = set()
        lines: list = []
        if kind == "set" and beat.get("set") not in SETS:
            err(f"{where}: set must be one of {', '.join(SETS)}.")
        if kind == "map":
            f = beat.get("focus")
            if (not isinstance(f, list) or not 1 <= len(f) <= LIMITS["maxFocus"]
                    or not all(isinstance(n, str) for n in f) or len(set(f)) != len(f)):
                err(f"{where}: focus must list 1 to {LIMITS['maxFocus']} different countries.")
            else:
                unknown = [n for n in f if n not in countries]
                if unknown:
                    err(f"{where}: {', '.join(repr(n) for n in unknown[:3])} is not a country on the map; use the "
                        "names in style.extra.countries (today's borders: show a historical region as the modern "
                        "countries it covers).")
                focus = set(f)
        if kind == "card":
            title, lines = beat.get("title"), beat.get("lines")
            if not _text_ok(title, LIMITS["titleChars"]):
                err(f"{where}: title must be text of 1 to {LIMITS['titleChars']} characters.")
            if (not isinstance(lines, list) or not 1 <= len(lines) <= LIMITS["cardLines"]
                    or not all(_text_ok(x, LIMITS["lineChars"]) for x in lines)):
                err(f"{where}: lines must list 1 to {LIMITS['cardLines']} lines of at most {LIMITS['lineChars']} "
                    "characters.")
                lines = []
            for text in [title] + list(lines):
                if isinstance(text, str) and ck.echoes(text, runs, LIMITS["echoWords"]):
                    err(f"{where}: the card repeats the narration word for word ({text!r}); the captions already "
                        "show those words, so write what the document says.")
                    break
        events = beat.get("events")
        if not isinstance(events, list):
            err(f"{where}: events must be a list.")
            continue
        _check_events(events, where, kind, start, end, cast_ids, catalog, focus, len(lines), on_word, changes,
                      quiet, err)
        if bi == 0 and kind != "card" and not any(
                isinstance(e, dict) and e.get("type") == "enter" and e.get("frame") == 0 for e in events):
            err("Nothing is on the first set at frame 0: start beat 1 with a puppet entering at frame 0 "
                "(from \"cut\"), or open on a card or a map.")

    still = round(LIMITS["maxStillSeconds"] * fps)
    prev = 0
    for c in sorted(c for c in changes if 0 <= c < total) + [total]:
        for a, b in uncovered(prev, c, quiet):
            if b - a > still:
                err(f"Nothing changes from frame {a} to {b} ({(b - a) / fps:.1f} s); the longest still stretch allowed "
                    f"is {LIMITS['maxStillSeconds']} s. {CHANGE_FIX[0].upper() + CHANGE_FIX[1:]}.")
        prev = c
    return errors


def _check_events(events, where, kind, start, end, cast_ids, catalog, focus, n_lines, on_word, changes, quiet, err):
    allowed = BEAT_EVENTS[kind]
    last = end - TIMING["endMargin"]
    on: dict[str, dict] = {}      # puppets on stage: slot, busy-until, last change
    slots: dict[int, str] = {}
    arrows = 0
    prev_f = None
    for raw in events:
        if not isinstance(raw, dict):
            err(f"{where}: every event must be an object.")
            continue
        e = {k: (v if not isinstance(v, (list, dict)) else None) for k, v in raw.items()}
        t, f = e.get("type"), e.get("frame")
        at = f"{where}, the {t or 'event'} at frame {f}"
        if t not in EVENT_TYPES:
            err(f"{at}: type must be one of {', '.join(EVENT_TYPES)}.")
            continue
        if t not in allowed:
            err(f"{at}: a {kind} beat takes only {', '.join(allowed)}.")
            continue
        if not ck.is_int(f):
            err(f"{at}: frame must be a whole number.")
            continue
        if prev_f is not None and f < prev_f:
            err(f"{where}: list the events in frame order.")
        prev_f = f
        if f < start or f > last:
            err(f"{at}: it must happen during its beat, from frame {start} to {last}.")
            continue
        if f != start and not on_word(f):
            err(f"{at}: events land on words; move it within {SNAP_FRAMES} frames of a word's start.")
        w = window_at(f, quiet)
        if w:
            err(f"{at} starts inside an insert ({window_text(w)}); move it to {w[1]} or later, or before {w[0]}.")
        changes.add(f)
        # free the slots of puppets that have slid out by now
        for who in [k for k, v in on.items() if v.get("gone") is not None and f >= v["gone"]]:
            slots.pop(on[who]["slot"], None)
            del on[who]
        if t in ACTOR_EVENTS:
            who = e.get("who")
            if who not in cast_ids:
                err(f"{at}: who must be a cast id.")
                continue
            p = on.get(who)
            if t == "enter":
                slot = e.get("slot")
                if p is not None:
                    err(f"{at}: {who} is already on stage.")
                    continue
                if not ck.is_int(slot) or not 0 <= slot < SLOTS:
                    err(f"{at}: slot must be 0, 1 or 2 (left, middle, right).")
                    continue
                if slot in slots:
                    err(f"{at}: slot {slot} is taken by {slots[slot]}.")
                    continue
                how = e.get("from", "slide")
                if how not in ENTRANCES:
                    err(f"{at}: from must be one of {', '.join(ENTRANCES)}.")
                    how = "cut"
                if "pose" in e and e["pose"] not in POSES:
                    err(f"{at}: pose must be one of {', '.join(POSES)}.")
                if "face" in e and e["face"] not in FACES:
                    err(f"{at}: face must be one of {', '.join(FACES)}.")
                busy = 0 if (how == "cut" or f == 0) else TIMING[how]
                on[who] = {"slot": slot, "busy": f + busy, "last": f, "gone": None, "sign": ""}
                slots[slot] = who
                continue
            if p is None:
                err(f"{at}: {who} is not on stage; enter it first.")
                continue
            if p["gone"] is not None:
                err(f"{at}: {who} has already left.")
                continue
            if f < p["busy"]:
                err(f"{at}: {who} is still entering or moving until frame {p['busy']}.")
            elif f != p["last"] and f - p["last"] < TIMING["minActorGap"]:
                err(f"{at}: {who} changed {f - p['last']} frames ago; changes to one puppet are at least "
                    f"{TIMING['minActorGap']} frames apart, or on the same frame.")
            p["last"] = f
            if t == "move":
                slot = e.get("slot")
                if not ck.is_int(slot) or not 0 <= slot < SLOTS or slot == p["slot"]:
                    err(f"{at}: slot must be another of 0, 1 or 2.")
                elif slot in slots:
                    err(f"{at}: slot {slot} is taken by {slots[slot]}.")
                else:
                    slots.pop(p["slot"], None)
                    slots[slot] = who
                    p["slot"] = slot
                    p["busy"] = f + TIMING["move"]
                    clash = _sign_clash(on)
                    if clash:
                        err(f"{at}: the signs {clash[0]} and {clash[1]} hold up would overlap; lower one first or "
                            "shorten them.")
            elif t == "exit":
                p["gone"] = f + TIMING["slide"]
            elif t == "act":
                if "pose" not in e and "face" not in e:
                    err(f"{at}: give a pose, a face or both.")
                if "pose" in e and e["pose"] not in POSES:
                    err(f"{at}: pose must be one of {', '.join(POSES)}.")
                if "face" in e and e["face"] not in FACES:
                    err(f"{at}: face must be one of {', '.join(FACES)}.")
            elif t == "swap":
                if e.get("costume") not in COSTUMES:
                    err(f"{at}: costume must be one of {', '.join(COSTUMES)}.")
            elif t == "sign":
                if not _text_ok(e.get("text"), LIMITS["signChars"], empty=True):
                    err(f"{at}: text must be at most {LIMITS['signChars']} characters (\"\" lowers the sign).")
                else:
                    p["sign"] = e["text"]
                    clash = _sign_clash(on)
                    if clash:
                        err(f"{at}: the signs {clash[0]} and {clash[1]} hold up would overlap; lower one first, "
                            "shorten them or stand the puppets further apart.")
            elif t == "hold":
                prop = e.get("prop")
                if prop == "":
                    continue
                if not isinstance(prop, str) or prop not in catalog:
                    err(f"{at}: prop must be from the library or the video's customProps (\"\" drops it).")
                    continue
                text, limit = e.get("text"), catalog[prop]["text"]
                if text not in (None, "") and (limit == 0 or not _text_ok(text, limit)):
                    err(f"{at}: the {prop} " + ("has no label." if limit == 0 else f"takes at most {limit} characters."))
        elif t == "stamp":
            if not _text_ok(e.get("text"), LIMITS["stampChars"]):
                err(f"{at}: text must be 1 to {LIMITS['stampChars']} characters.")
            if e.get("color", "red") not in STAMP_COLORS:
                err(f"{at}: color must be one of {', '.join(STAMP_COLORS)}.")
        elif t == "date":
            if not _text_ok(e.get("text"), LIMITS["dateChars"]):
                err(f"{at}: text must be 1 to {LIMITS['dateChars']} characters.")
        elif t == "strike":
            line = e.get("line")
            if not ck.is_int(line) or not 0 <= line < n_lines:
                err(f"{at}: line must be the index of one of the card's lines (0 to {max(0, n_lines - 1)}).")
            if not _text_ok(e.get("text"), LIMITS["strikeChars"]):
                err(f"{at}: text (the new value) must be 1 to {LIMITS['strikeChars']} characters.")
        elif t in ("fill", "label"):
            if e.get("region") not in focus:
                err(f"{at}: region must be one of the beat's focus countries, so it is on the map.")
            if t == "fill" and e.get("color") not in FILLS:
                err(f"{at}: color must be one of {', '.join(FILLS)}.")
            if t == "label" and not _text_ok(e.get("text"), LIMITS["labelChars"]):
                err(f"{at}: text must be 1 to {LIMITS['labelChars']} characters.")
        elif t == "arrow":
            arrows += 1
            if e.get("from") not in focus or e.get("to") not in focus or e.get("from") == e.get("to"):
                err(f"{at}: from and to must be two different focus countries.")
            if arrows > LIMITS["maxArrows"]:
                err(f"{where}: a map takes at most {LIMITS['maxArrows']} arrows.")


# ── what the audit and the picture checks read ────────────────────────────────

def _data(config: dict) -> dict:
    scenes = config.get("scenes") or []
    if len(scenes) != 1 or not is_scene(scenes[0]):
        return {}
    d = (scenes[0].get("props") or {}).get(PROPS_KEY)
    return d if isinstance(d, dict) else {}


def audit_windows(config: dict) -> list[tuple[int, int]]:
    """(first, end) for the text-layout audit: each beat once its entrances have landed."""
    data = _data(config)
    total = config.get("totalFrames") if ck.is_int(config.get("totalFrames")) else 0
    starts = sorted({b.get("start") for b in data.get("beats") or [] if isinstance(b, dict) and ck.is_int(b.get("start"))})
    windows = [(a, b) for a, b in zip(starts, starts[1:] + [total]) if b > a]
    return ck.sample_windows(windows, TIMING["slide"], TIMING["endMargin"])


def change_frames(data: dict) -> list[int]:
    frames = []
    for b in data.get("beats") or []:
        if not isinstance(b, dict):
            continue
        frames.append(b.get("start"))
        for e in b.get("events") or []:
            if isinstance(e, dict):
                frames.append(e.get("frame"))
    return [f for f in frames if ck.is_int(f)]


def first_frame_problem(data: dict) -> str | None:
    beats = data.get("beats") or []
    b = beats[0] if beats and isinstance(beats[0], dict) else {}
    if b.get("start") != 0:
        return "the first beat does not start at frame 0, so the video opens on nothing"
    if b.get("type") in ("card", "map"):
        return None
    if not any(isinstance(e, dict) and e.get("type") == "enter" and ck.is_int(e.get("frame")) and e["frame"] <= 3
               for e in b.get("events") or []):
        return ("no puppet is on the first set by frame 3, so the video opens on an empty set. Enter the first "
                "puppet at frame 0 from \"cut\"")
    return None


def sample_text(data: dict, prop_id) -> str:
    for b in data.get("beats") or []:
        for e in (b.get("events") or []) if isinstance(b, dict) else []:
            if isinstance(e, dict) and e.get("type") == "hold" and e.get("prop") == prop_id and isinstance(e.get("text"), str):
                return e["text"]
    return ""
