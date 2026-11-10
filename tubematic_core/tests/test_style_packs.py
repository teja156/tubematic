"""Style packs (TMDEV-196): the style list and each style's rules as data.

The truth table below is the point of this file. It is what the hand-written
gates in mcp/server.py and renderer/api/pipeline.py answered before the packs
existed, for every style that existed then, plus "auto", a blank value and an
unknown one. Moving the rules into data must not change one answer: each of
them decides what an agent may draw or what the AI review is told is intended,
and a flipped answer shows up only after a render.
"""
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import visual_styles as tvs  # noqa: E402

# style: (figures, line_art, generated_characters, fixed canvas, needs key, needs GPU)
BEFORE_PACKS = {
    "auto": (True, True, True, None, False, False),
    "motion_graphics": (False, False, False, "dark", False, False),
    "stick": (True, True, False, "light", False, False),
    "illustrated": (True, False, True, None, True, False),
    "cartoon_3d": (True, False, False, "dark", False, True),
    "": (True, False, False, None, False, False),
    "nonsense": (True, False, False, None, False, False),
}


@pytest.mark.parametrize("style", list(BEFORE_PACKS))
def test_the_existing_styles_answer_as_they_did_before_packs(style):
    figures, line_art, characters, canvas, key, gpu = BEFORE_PACKS[style]
    assert tvs.figures_allowed(style) is figures
    assert tvs.line_art_allowed(style) is line_art
    assert tvs.characters_allowed(style) is characters
    assert tvs.CANVAS_BY_STYLE.get(style) == canvas
    assert tvs.needs_openai_key(style) is key
    assert tvs.needs_gpu(style) is gpu


def test_surrounding_whitespace_is_ignored():
    assert tvs.figures_allowed("  motion_graphics ") is False
    assert tvs.line_art_allowed(" stick ") is True


def test_the_list_starts_with_auto_and_holds_every_pack():
    assert tvs.VISUAL_STYLES[0] == "auto"
    assert set(tvs.VISUAL_STYLES[1:]) == {p.stem for p in tvs.PACKS_DIR.glob("*.json")}
    assert {"motion_graphics", "stick", "illustrated", "cartoon_3d", "system_flow"} <= set(tvs.VISUAL_STYLES)


def test_effective_canvas():
    assert tvs.effective_canvas("stick", "dark") == "light"  # a forced canvas wins
    assert tvs.effective_canvas("auto", "") == ""
    assert tvs.effective_canvas("auto", " light ") == "light"
    assert tvs.effective_canvas("illustrated", "dark") == "dark"  # illustrated leaves it to the agent
    assert tvs.effective_canvas("system_flow", "") == "dark"


def test_the_refusals_come_from_the_packs():
    assert tvs.openai_key_error("illustrated") == tvs.ILLUSTRATED_NEEDS_OPENAI_KEY
    assert tvs.openai_key_error("stick") == ""
    assert "onboard.py --step gpu" in tvs.CARTOON3D_NEEDS_GPU
    assert "Test GPU" in tvs.CARTOON3D_GPU_UNKNOWN
    assert tvs.cartoon_3d_gpu_error("cartoon_3d", "unknown") == tvs.CARTOON3D_GPU_UNKNOWN
    assert tvs.cartoon_3d_gpu_error("cartoon_3d", "not_usable") == tvs.CARTOON3D_NEEDS_GPU
    assert tvs.cartoon_3d_gpu_error("cartoon_3d", "working") == ""
    assert tvs.cartoon_3d_gpu_error("system_flow", "unknown") == ""


def test_system_flow():
    p = tvs.pack("system_flow")
    assert p["renderer"] == "dom" and p["canvas"] == "dark"
    assert p["authoring_skill"] == "tubematic-system-flow"
    assert not any(p["allows"].values()) and not any(p["needs"].values())
    assert "review" in p and "captions" in p
    assert len(p["extra"]["icons"]) == len(set(p["extra"]["icons"]))


def test_the_public_list_says_why_a_style_is_unavailable():
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=False, gpu_status="unknown")}
    assert list(rows)[0] == "auto" and rows["auto"]["available"]
    assert rows["illustrated"]["unavailable_reason"] == "needs an OpenAI key"
    assert rows["cartoon_3d"]["unavailable_reason"] == "GPU not tested yet"
    assert rows["system_flow"]["available"]
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="not_usable")}
    assert rows["illustrated"]["available"]
    assert rows["cartoon_3d"]["unavailable_reason"] == "needs a working GPU"
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="working")}
    assert all(r["available"] for r in rows.values())


def test_the_agent_view_names_the_authoring_skill():
    assert tvs.agent_view("system_flow")["authoring_skill"] == "tubematic-system-flow"
    assert tvs.agent_view("cartoon_3d")["authoring_skill"] == "tubematic-cartoon3d"
    assert tvs.agent_view("stick")["authoring_skill"] == "tubematic-scene-config"
    assert tvs.agent_view("auto")["authoring_skill"] == "tubematic-scene-config"
    assert tvs.agent_view("")["id"] == "auto"


# ── the schema check ─────────────────────────────────────────────────────────

def _valid(**over):
    data = json.loads((tvs.PACKS_DIR / "stick.json").read_text())
    data.update(over)
    return data


@pytest.mark.parametrize("over, fragment", [
    ({"id": "other"}, "must equal the file name"),
    ({"label": ""}, "label"),
    ({"order": "1"}, "order"),
    ({"renderer": "webgl"}, "renderer"),
    ({"canvas": "blue"}, "canvas"),
    ({"allows": {"figures": True}}, "allows"),
    ({"needs": {"openai_key": True, "gpu": False}}, "messages.openai_key"),
    ({"routing": {"best_for": [], "avoid_for": []}}, "routing.signals"),
    ({"review": ""}, "review"),
    ({"script": "  "}, "script"),
])
def test_a_malformed_pack_is_refused(over, fragment):
    with pytest.raises(tvs.PackError, match=fragment.replace(".", r"\.")):
        tvs._check_pack(pathlib.Path("stick.json"), _valid(**over))


def test_auto_cannot_be_a_pack():
    with pytest.raises(tvs.PackError, match="not a style"):
        tvs._check_pack(pathlib.Path("auto.json"), _valid(id="auto"))


def test_every_shipped_pack_passes():
    for path in tvs.PACKS_DIR.glob("*.json"):
        tvs._check_pack(path, json.loads(path.read_text()))


@pytest.mark.parametrize("routing_over, fragment", [
    ({"images": -1}, "routing.images"),
    ({"images": True}, "routing.images"),
    ({"images": "3"}, "routing.images"),
    ({"moods": ["calm", ""]}, "routing.moods"),
    ({"images_per_video": 3}, "routing.images_per_video"),
])
def test_the_optional_routing_fields_are_checked_when_present(routing_over, fragment):
    data = _valid()
    data["routing"] = {**data["routing"], **routing_over}
    with pytest.raises(tvs.PackError, match=fragment.replace(".", r"\.")):
        tvs._check_pack(pathlib.Path("stick.json"), data)


def test_a_pack_written_before_the_optional_fields_still_loads():
    data = _valid()
    data["routing"] = {k: data["routing"][k] for k in ("best_for", "avoid_for", "signals")}
    data.pop("script", None)
    tvs._check_pack(pathlib.Path("stick.json"), data)


def test_the_agent_view_carries_the_style_script_guidance():
    assert "component" in tvs.agent_view("system_flow")["script"]
    assert tvs.agent_view("stick")["script"] == ""
    assert tvs.agent_view("auto")["script"] == ""
