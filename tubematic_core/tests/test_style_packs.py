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
    assert {"motion_graphics", "stick", "illustrated", "cartoon_3d", "system_flow",
            "bean_explainer", "whiteboard", "storybook_atlas", "terminal_doc",
            "under_the_hood", "case_file_story"} <= set(tvs.VISUAL_STYLES)


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


def test_whiteboard():
    """A whole-video style like System Flow, on the light canvas, with no
    figures of any kind (a role is a doodle) and nothing to install."""
    p = tvs.pack("whiteboard")
    assert p["renderer"] == "dom" and tvs.effective_canvas("whiteboard", "dark") == "light"
    assert p["authoring_skill"] == "tubematic-whiteboard"
    assert not any(p["allows"].values()) and not any(p["needs"].values())
    assert not tvs.figures_allowed("whiteboard") and not tvs.characters_allowed("whiteboard")
    assert "review" in p and p["captions"]["fontFamily"].startswith("Kalam")
    assert p["extra"]["doodles"] == sorted(set(p["extra"]["doodles"]))
    # TMDEV-203 routes on these; each must name what sets it apart.
    avoid = " ".join(p["routing"]["avoid_for"])
    assert "System Flow" in avoid and "Stick" in avoid and "Motion Graphics" in avoid
def test_bean_explainer():
    p = tvs.pack("bean_explainer")
    assert p["renderer"] == "dom" and p["canvas"] == "light"
    assert p["authoring_skill"] == "tubematic-bean-explainer"
    assert p["experimental"] is True
    # its bean is a figure, but neither line art nor a generated character
    assert tvs.figures_allowed("bean_explainer") is True
    assert tvs.line_art_allowed("bean_explainer") is False
    assert tvs.characters_allowed("bean_explainer") is False
    assert not any(p["needs"].values())
    assert "review" in p and "captions" in p
    assert len(p["extra"]["props"]) >= 40
    assert tvs.effective_canvas("bean_explainer", "dark") == "light"


def test_storybook_atlas():
    p = tvs.pack("storybook_atlas")
    assert p["renderer"] == "dom" and p["canvas"] == "light"
    assert p["authoring_skill"] == "tubematic-storybook-atlas"
    assert p["experimental"] is True
    # its guide and people are figures of its own, neither line art nor generated characters
    assert tvs.figures_allowed("storybook_atlas") is True
    assert tvs.line_art_allowed("storybook_atlas") is False
    assert tvs.characters_allowed("storybook_atlas") is False
    assert not any(p["needs"].values())
    assert "review" in p and "captions" in p and "script" in p
    assert p["captions"]["background"] == "label"
    assert len(p["extra"]["props"]) >= 40 and len(p["extra"]["backdrops"]) >= 10
    assert tvs.effective_canvas("storybook_atlas", "dark") == "light"


def test_terminal_doc():
    p = tvs.pack("terminal_doc")
    assert p["renderer"] == "dom" and p["canvas"] == "dark"
    assert p["authoring_skill"] == "tubematic-terminal-doc"
    assert p["experimental"] is False
    # the text is the picture: no figures, no line art, no generated characters
    assert not any(p["allows"].values()) and not any(p["needs"].values())
    assert "review" in p and p["captions"]["background"] == "log"
    assert p["routing"]["images"] == 0
    # each skin's caption changes are caption keys
    assert set(p["extra"]["skins"]) == {"house", "crt"}
    for skin in p["extra"]["skins"].values():
        assert set(skin["captions"]) <= set(p["captions"]) | {"accent"}
    assert tvs.effective_canvas("terminal_doc", "light") == "dark"


def test_under_the_hood():
    p = tvs.pack("under_the_hood")
    assert p["renderer"] == "dom" and p["canvas"] == "dark"
    assert p["authoring_skill"] == "tubematic-under-the-hood"
    assert p["experimental"] is True
    # its presenter is a figure drawn by the scene, never a generated character
    assert tvs.figures_allowed("under_the_hood") is True
    assert tvs.line_art_allowed("under_the_hood") is False
    assert tvs.characters_allowed("under_the_hood") is False
    # built on generated photographs: refused without an OpenAI key, like Illustrated
    assert tvs.needs_openai_key("under_the_hood") is True and tvs.needs_gpu("under_the_hood") is False
    assert "OpenAI" in tvs.openai_key_error("under_the_hood")
    assert p["routing"]["images"] == 12
    assert p["captions"]["look"] == "selection"
    assert tvs.effective_canvas("under_the_hood", "light") == "dark"
    # its own presenter stands where a mascot would: no mascot, like Cartoon 3D
    assert p["mascot"] is False and "presenter" in p["messages"]["mascot"]
    assert set(tvs.NO_MASCOT_STYLES) == {"cartoon_3d", "under_the_hood", "case_file_story"}
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="working")}
    assert rows["under_the_hood"]["mascot"] is False and rows["cartoon_3d"]["mascot"] is False
    assert rows["auto"]["mascot"] is True and rows["stick"]["mascot"] is True


def test_case_file_story():
    p = tvs.pack("case_file_story")
    assert p["renderer"] == "dom" and p["canvas"] == "dark"
    assert p["authoring_skill"] == "tubematic-case-file-story"
    assert p["experimental"] is True and p["order"] == 100
    # its lead is painted into generated stills, never a cut-out from generate_character
    assert tvs.figures_allowed("case_file_story") is True
    assert tvs.line_art_allowed("case_file_story") is False
    assert tvs.characters_allowed("case_file_story") is False
    # built on generated stills: refused without an OpenAI key, like Illustrated
    assert tvs.needs_openai_key("case_file_story") is True and tvs.needs_gpu("case_file_story") is False
    assert "OpenAI" in tvs.openai_key_error("case_file_story")
    # sixteen stills and the lead sheet
    assert p["routing"]["images"] == 17
    assert p["captions"]["look"] == "fill"
    assert tvs.effective_canvas("case_file_story", "light") == "dark"
    # the story has its own lead: no mascot
    assert p["mascot"] is False and "lead" in p["messages"]["mascot"]
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=False, gpu_status="working")}
    assert rows["case_file_story"]["mascot"] is False
    assert rows["case_file_story"]["unavailable_reason"] == "needs an OpenAI key"
    # what generate_image adds to this style's prompts
    for key in ("sheet_lead", "sheet_style", "still_lead", "still_style"):
        assert p["extra"][key].strip()
    # the script text carries the ending and the subject line the user set
    script = p["script"]
    for phrase in ("second person", "the last sentence is only the two options", "invented",
                   "Never write it as instructions", "No violence", "at most sixteen pictures"):
        assert phrase in script, phrase
    assert "comes before the ending" in script


def test_a_pack_that_takes_no_mascot_must_say_why():
    data = json.loads((tvs.PACKS_DIR / "stick.json").read_text())
    data["mascot"] = False
    with pytest.raises(tvs.PackError, match="messages.mascot"):
        tvs._check_pack(pathlib.Path("stick.json"), data)
    data["mascot"] = "no"
    with pytest.raises(tvs.PackError, match="mascot, when present"):
        tvs._check_pack(pathlib.Path("stick.json"), data)


def test_the_public_list_says_why_a_style_is_unavailable():
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=False, gpu_status="unknown")}
    assert list(rows)[0] == "auto" and rows["auto"]["available"]
    assert rows["illustrated"]["unavailable_reason"] == "needs an OpenAI key"
    assert rows["under_the_hood"]["unavailable_reason"] == "needs an OpenAI key"
    assert rows["cartoon_3d"]["unavailable_reason"] == "GPU not tested yet"
    assert rows["system_flow"]["available"] and rows["whiteboard"]["available"]
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="not_usable")}
    assert rows["illustrated"]["available"]
    assert rows["cartoon_3d"]["unavailable_reason"] == "needs a working GPU"
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="working")}
    assert all(r["available"] for r in rows.values())


def test_the_agent_view_names_the_authoring_skill():
    assert tvs.agent_view("system_flow")["authoring_skill"] == "tubematic-system-flow"
    assert tvs.agent_view("whiteboard")["authoring_skill"] == "tubematic-whiteboard"
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
