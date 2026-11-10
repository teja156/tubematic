"""Visual styles: the list and each style's rules, read from one data file per style.

A style pack is a JSON file in `style_packs/`, named for the style's id. It
says what the style is called, which renderer draws it, whether it fixes the
canvas, what the agent may put in it, what the install needs to produce it,
which skill authors it, and (for TMDEV-203's Auto routing) what it suits. The
MCP server and the API import this module; the dashboard reads the same data
through GET /visual-styles. That replaces the hand-kept copies of the style
list and its gates that each of those used to carry.

"auto" is not a pack. It is the absence of a style: everything is allowed and
the agent settles the canvas and the renderer itself.

A video's visual_style is a PERMISSION SET for the scene styles, not a look.
It says which vocabularies the agent may draw from, and which canvas the video
is painted on; the per-beat treatment is still derived from each beat's
subject. Styles whose pack names another authoring skill (Cartoon 3D, System
Flow) replace the scene system with their own, so for them the pack is the
whole description.

The canvas is the one property that cannot vary between the scenes of one
video: alternating light and dark frames flashes, and a viewer reads that as a
broken render rather than a style. It is a single top-level key in
scene-config.json, and the renderer paints it under every scene. The figure
vocabulary is not tied to it: a stick figure is black on light and white on
dark, same geometry either way.

Free of Flask and of I/O beyond reading the packs once at import. A malformed
pack raises at import, so a bad file stops the process at start-up rather than
at the first video that uses it.
"""
import json
import pathlib

PACKS_DIR = pathlib.Path(__file__).resolve().parent / "style_packs"

AUTO = "auto"
DEFAULT_VISUAL_STYLE = AUTO

# Keep in sync: renderer/remotion/src/CompositionBuilder.tsx's Canvas.
VALID_CANVASES = ("dark", "light")
DEFAULT_CANVAS = "dark"

# What videos.resolved_visual_style holds: the canvas "auto" settled on, and
# nothing else. Named for the column; what it stores is a canvas, because the
# canvas is the only thing "auto" must fix for the life of the video.
RESOLVED_VISUAL_STYLES = VALID_CANVASES

# What videos.resolved_renderer holds: which renderer "auto" settled on, written
# once by the agent before any scene is authored. The renderer is the one thing
# a revision round must not flip, since flipping it discards every scene.
RENDERERS = ("dom", "cartoon_3d")

_ALLOWS = ("figures", "line_art", "generated_characters")
_NEEDS = ("openai_key", "gpu")
_NEED_MESSAGES = {"openai_key": ("openai_key",), "gpu": ("gpu", "gpu_unknown")}
_ROUTING = ("best_for", "avoid_for", "signals")

# Auto's other outcome besides a pack: keep the mixed scene system, where the
# agent draws each beat from any vocabulary and settles the canvas at scene
# time. It is what Auto meant before it could pick packs, the fallback when no
# pack clearly fits, and the path a video scripted before TMDEV-203 finishes
# on. Not a pack, so its routing block lives here.
SCENES = "scenes"
SCENES_LABEL = "Mixed scenes"
SCENES_ROUTING = {
    "best_for": [
        "topics no style describes better: the beats need different things (a real product as a "
        "picture, a role acted out, a diagram) and no one treatment carries the whole video",
    ],
    "avoid_for": [
        "a topic that clearly matches one style's best_for: that style is the better video",
    ],
    "signals": [
        "no single style's best_for matches the topic",
        "the beats split between pictures of real things and drawn explanations",
    ],
    "moods": [],
    "images": 6,
    "images_per_video": "a few, only where a beat needs a picture",
}


class PackError(ValueError):
    """A style pack that does not match the schema below."""


def _check_pack(path: pathlib.Path, data) -> dict:
    """Validate one pack; returns it unchanged. Every rule here is one a caller
    relies on, so a pack missing it would fail somewhere far from the cause."""
    where = path.name

    def fail(msg):
        raise PackError(f"style pack {where}: {msg}")

    if not isinstance(data, dict):
        fail("must be a JSON object")
    if data.get("id") != path.stem:
        fail(f"id {data.get('id')!r} must equal the file name {path.stem!r}")
    if data["id"] == AUTO:
        fail('"auto" is not a style and has no pack')
    if data["id"] == SCENES:
        fail(f'"{SCENES}" is Auto\'s mixed scene system and cannot be a pack')
    for key in ("label", "authoring_skill"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            fail(f"{key} must be a non-empty string")
    if not isinstance(data.get("order"), int) or isinstance(data["order"], bool):
        fail("order must be a whole number")
    if not isinstance(data.get("experimental"), bool):
        fail("experimental must be true or false")
    if data.get("renderer") not in RENDERERS:
        fail(f"renderer must be one of {RENDERERS}")
    if data.get("canvas") is not None and data["canvas"] not in VALID_CANVASES:
        fail(f"canvas must be one of {VALID_CANVASES}, or null when the agent chooses it")
    for group, keys in (("allows", _ALLOWS), ("needs", _NEEDS)):
        block = data.get(group)
        if not isinstance(block, dict) or set(block) != set(keys):
            fail(f"{group} must have exactly the keys {keys}")
        if not all(isinstance(v, bool) for v in block.values()):
            fail(f"every {group} value must be true or false")
    messages = data.get("messages", {})
    if not isinstance(messages, dict):
        fail("messages must be an object")
    for need, msg_keys in _NEED_MESSAGES.items():
        if data["needs"][need]:
            for mk in msg_keys:
                if not isinstance(messages.get(mk), str) or not messages[mk].strip():
                    fail(f"needs.{need} is true, so messages.{mk} must say what to do about it")
    for key in ("review",):
        if key in data and not (isinstance(data[key], str) and data[key].strip()):
            fail(f"{key}, when present, must be a non-empty string")
    if "captions" in data and not isinstance(data["captions"], dict):
        fail("captions, when present, must be an object (scene-config subtitles defaults)")
    routing = data.get("routing")
    if not isinstance(routing, dict):
        fail("routing must be an object")
    for key in _ROUTING:
        val = routing.get(key)
        if not isinstance(val, list) or not all(isinstance(s, str) and s.strip() for s in val):
            fail(f"routing.{key} must be a list of non-empty strings")
    # Optional, so a pack written before TMDEV-203 still loads. Auto reads
    # images as a cost tie-break and moods as a tie-break only.
    if "moods" in routing and not (isinstance(routing["moods"], list)
                                   and all(isinstance(m, str) and m.strip() for m in routing["moods"])):
        fail("routing.moods, when present, must be a list of non-empty strings")
    images = routing.get("images", 0)
    if not isinstance(images, int) or isinstance(images, bool) or images < 0:
        fail("routing.images, when present, must be a whole number of generated images, 0 or more")
    if "images_per_video" in routing and not isinstance(routing["images_per_video"], str):
        fail("routing.images_per_video, when present, must be a string")
    if "script" in data and not (isinstance(data["script"], str) and data["script"].strip()):
        fail("script, when present, must be a non-empty string")
    return data


def _load() -> dict:
    packs = {}
    for path in sorted(PACKS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PackError(f"style pack {path.name}: not valid JSON ({exc})") from exc
        packs[path.stem] = _check_pack(path, data)
    if not packs:
        raise PackError(f"no style packs found in {PACKS_DIR}")
    orders = [p["order"] for p in packs.values()]
    if len(set(orders)) != len(orders):
        raise PackError("two style packs share an order value")
    return dict(sorted(packs.items(), key=lambda kv: kv[1]["order"]))


PACKS = _load()

VISUAL_STYLES = (AUTO,) + tuple(PACKS)

# Styles that fix the canvas. A partial map on purpose: membership in it, never
# equality with "auto", is the test for "has the canvas been settled".
CANVAS_BY_STYLE = {sid: p["canvas"] for sid, p in PACKS.items() if p["canvas"]}


def pack(visual_style: str) -> dict | None:
    """The pack for a style id, or None for "auto", blank or an unknown value."""
    return PACKS.get((visual_style or "").strip())


def _allows(visual_style: str, what: str, unknown: bool) -> bool:
    chosen = (visual_style or "").strip()
    if chosen == AUTO:
        return True
    p = PACKS.get(chosen)
    return p["allows"][what] if p else unknown


def effective_canvas(visual_style: str, resolved_visual_style: str) -> str:
    """The canvas a video is painted on, or "" if "auto" has not settled yet.

    A forced choice wins outright and the recorded resolution is ignored, so a
    video switched off "auto" cannot be held to an older automatic decision.
    Under "auto" (and under a style that leaves the canvas to the agent) the
    answer is whatever the agent recorded, and "" until it has recorded
    anything, which callers must handle rather than guessing.
    """
    chosen = (visual_style or "").strip()
    if chosen in CANVAS_BY_STYLE:
        return CANVAS_BY_STYLE[chosen]
    return (resolved_visual_style or "").strip()


def figures_allowed(visual_style: str) -> bool:
    """Whether this video may contain character figures at all, of either kind.

    "auto" permits everything. A blank or unknown value counts as allowing
    them, as it always has: only a style that excludes figures says so.
    """
    return _allows(visual_style, "figures", unknown=True)


def line_art_allowed(visual_style: str) -> bool:
    """Whether this video's figures may be simple hand-drawn line art.

    Narrower than figures_allowed, and the difference is the point: Illustrated
    HAS figures, but they are generated artwork, and telling the AI review that
    line art is intended there would license the one mistake that style forbids.
    """
    return _allows(visual_style, "line_art", unknown=False)


def characters_allowed(visual_style: str) -> bool:
    """Whether GENERATED character art (generate_character) is permitted.

    Narrower than figures_allowed: Stick means hand-drawn line art, and letting
    it reach for generated art would erase the difference the human chose. A
    line-art figure next to a rendered one reads as an asset that failed to
    load, so the two never mix in one video; this is the tool-level guard.
    """
    return _allows(visual_style, "generated_characters", unknown=False)


def needs_openai_key(visual_style: str) -> bool:
    p = pack(visual_style)
    return bool(p and p["needs"]["openai_key"])


def needs_gpu(visual_style: str) -> bool:
    p = pack(visual_style)
    return bool(p and p["needs"]["gpu"])


def openai_key_error(visual_style: str) -> str:
    """The refusal for choosing `visual_style` with no OpenAI key stored, or ""
    when the style needs none. The caller decides whether a key is stored."""
    return pack(visual_style)["messages"]["openai_key"] if needs_openai_key(visual_style) else ""


def gpu_probe_status(raw_probe) -> str:
    """One renderer's GPU state from its stored probe (the JSON in
    renderers.gpu_probe, as the renderer reported it through the render
    gateway): "unknown" (never probed), "not_configured" (no GPU override),
    "working" (configured and the last probe passed) or "not_usable"
    (configured, but renders fall back to the CPU). The gates read the
    install-wide aggregate, tubematic_core.renderers.gpu_status, which uses
    these same values."""
    try:
        probe = json.loads(raw_probe or "null")
    except ValueError:
        probe = None
    if not isinstance(probe, dict):
        return "unknown"
    if not probe.get("configured"):
        return "not_configured"
    return "working" if probe.get("ok") else "not_usable"


def cartoon_3d_gpu_error(visual_style: str, gpu_status: str) -> str:
    """Why `visual_style` may not be chosen while the GPU is in `gpu_status`,
    or "". Only a style that needs a GPU is gated, and only "working" passes.
    Gate on "working", never on "configured": a configured GPU whose renders
    fall back to the CPU is the case the gate must catch. "unknown" gets its
    own message, since its fix is a test, not an install. (The name predates
    packs; Cartoon 3D was the first GPU-only style.)"""
    if not needs_gpu(visual_style) or gpu_status == "working":
        return ""
    messages = pack(visual_style)["messages"]
    return messages["gpu_unknown"] if gpu_status == "unknown" else messages["gpu"]


# The refusals of today's two gated styles, under the names callers and tests
# already use. They live in the packs; these are views of them.
ILLUSTRATED_NEEDS_OPENAI_KEY = PACKS["illustrated"]["messages"]["openai_key"]
CARTOON3D_NEEDS_GPU = PACKS["cartoon_3d"]["messages"]["gpu"]
CARTOON3D_GPU_UNKNOWN = PACKS["cartoon_3d"]["messages"]["gpu_unknown"]


def _unavailable_reason(p: dict, openai_key_set: bool, gpu_status: str) -> str:
    if p["needs"]["openai_key"] and not openai_key_set:
        return "needs an OpenAI key"
    if p["needs"]["gpu"] and gpu_status != "working":
        return "GPU not tested yet" if gpu_status == "unknown" else "needs a working GPU"
    return ""


def public_list(openai_key_set: bool, gpu_status: str) -> list[dict]:
    """Every style, "auto" first, as the dashboard shows them: id, label,
    experimental, the canvas a style fixes (None when it does not), what it
    needs, and whether this install can produce it now, with the reason when
    it cannot. The API is the authority on refusals; this only explains them."""
    out = [{"id": AUTO, "label": "Auto", "experimental": False, "canvas": None,
            "needs": {k: False for k in _NEEDS}, "available": True, "unavailable_reason": ""}]
    for sid, p in PACKS.items():
        reason = _unavailable_reason(p, openai_key_set, gpu_status)
        out.append({"id": sid, "label": p["label"], "experimental": p["experimental"],
                    "canvas": p["canvas"], "needs": dict(p["needs"]),
                    "available": not reason, "unavailable_reason": reason})
    return out


def agent_view(visual_style: str) -> dict:
    """What the agent needs to know about one video's style, for get_video:
    who authors it, what it may contain and which canvas it fixes. "auto"
    (or an unknown value) authors through the scene-config skill, which
    settles the renderer and the canvas itself."""
    p = pack(visual_style)
    if not p:
        chosen = (visual_style or "").strip() or AUTO
        return {"id": chosen, "label": "Auto" if chosen == AUTO else chosen,
                "renderer": None, "canvas": None,
                "authoring_skill": "tubematic-scene-config",
                "allows": {k: True for k in _ALLOWS}, "script": ""}
    return {"id": p["id"], "label": p["label"], "renderer": p["renderer"], "canvas": p["canvas"],
            "authoring_skill": p["authoring_skill"], "allows": dict(p["allows"]),
            "script": p.get("script", "")}


# ── Auto's routing (TMDEV-203) ───────────────────────────────────────────────

ROUTE_CHOICES = tuple(PACKS) + (SCENES,)

MASCOT_EXCLUDES_3D = "the video has a mascot, which has no place in a 3D world"


def route_label(choice: str) -> str:
    """The label of a routing outcome: a pack's label, or "Mixed scenes"."""
    if choice == SCENES:
        return SCENES_LABEL
    p = pack(choice)
    return p["label"] if p else choice


def routing_candidates(openai_key_set: bool, gpu_status: str, has_mascot: bool) -> list[dict]:
    """Every outcome Auto may route a video to, for get_video's style_routing:
    each pack in pack order, then mixed scenes. Each entry carries the pack's
    routing block verbatim, its generated-image count and whether this install
    and this video can have it now, with the reason when not.

    The list is read from the packs, never written out anywhere, so a new pack
    with a routing block is a candidate the moment it ships. A video with a
    mascot cannot take a 3D-world style: the mascot is a flat overlay."""
    out = []
    for sid, p in PACKS.items():
        reason = _unavailable_reason(p, openai_key_set, gpu_status)
        if not reason and has_mascot and p["renderer"] == "cartoon_3d":
            reason = MASCOT_EXCLUDES_3D
        routing = {k: (list(v) if isinstance(v, list) else v) for k, v in p["routing"].items()}
        routing.setdefault("moods", [])
        routing.setdefault("images", 0)
        out.append({"id": sid, "label": p["label"], "experimental": p["experimental"],
                    "authoring_skill": p["authoring_skill"], "routing": routing,
                    "images": routing["images"], "available": not reason,
                    "unavailable_reason": reason})
    out.append({"id": SCENES, "label": SCENES_LABEL, "experimental": False,
                "authoring_skill": "tubematic-scene-config",
                "routing": {k: (list(v) if isinstance(v, list) else v)
                            for k, v in SCENES_ROUTING.items()},
                "images": SCENES_ROUTING["images"], "available": True,
                "unavailable_reason": ""})
    return out


STYLE_REASON_MAX_CHARS = 300

# SET fragments shared by the MCP server and the API, so the two processes
# cannot drift. SQLite evaluates every SET expression against the row as it
# was before the UPDATE, so the order of the assignments does not matter.

# A video going back to TOPIC_PROPOSED (a topic revision) gives an Auto pick
# back to Auto: the topic it was decided on is about to change, and the next
# approval routes it again. A style a person chose (style_pick '') is kept.
# The scene choices made under the pick go with it, and so do those of any
# video on "auto": it is routed again at its next approval, so a renderer
# recorded for its old scenes (a "cartoon_3d" from before Auto picked styles)
# would otherwise refuse a mascot at that approval and outlive the new pick.
_BACK_TO_AUTO = ("(COALESCE(style_pick, '') != '' "
                 "OR COALESCE(NULLIF(visual_style, ''), 'auto') = 'auto')")
AUTO_PICK_RESET_SET = (
    "visual_style = CASE WHEN COALESCE(style_pick, '') != '' THEN 'auto' ELSE visual_style END, "
    f"resolved_renderer = CASE WHEN {_BACK_TO_AUTO} THEN '' ELSE resolved_renderer END, "
    f"resolved_visual_style = CASE WHEN {_BACK_TO_AUTO} THEN '' ELSE resolved_visual_style END, "
    "style_pick = '', style_runner_up = '', style_reason = ''"
)

# A new style decision (Auto's pick, or a switch to the runner-up) is always
# followed by a new script, a new voice and new scenes, so the renderer and the
# canvas recorded for the previous scenes no longer apply. Left in place, a
# renderer recorded as "cartoon_3d" by an earlier Auto would still send the new
# style's scenes to the Cartoon 3D renderer, and an old canvas would be forced
# on a style that leaves the canvas to the agent.
NEW_STYLE_CLEARS_SET = "resolved_renderer = '', resolved_visual_style = ''"


def style_change_clears_pick(value: str) -> tuple[str, list]:
    """SET fragments and their parameters for a write of visual_style by a
    person. A changed value replaces Auto's pick, so the record of that pick
    goes, and so do the renderer and canvas recorded for the old scenes (the
    style changes only at the topic, before a new script and new scenes; a
    renderer left at "cartoon_3d" would still send them to the Cartoon 3D
    renderer). The same value sent again (the dashboard re-sends the picker on
    every approval) keeps everything."""
    cols = ("style_pick", "style_runner_up", "style_reason", "resolved_renderer",
            "resolved_visual_style")
    sql = ", ".join(f"{col} = CASE WHEN COALESCE(visual_style, '') = ? THEN {col} ELSE '' END"
                    for col in cols)
    return sql, [value] * len(cols)
