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

from tubematic_core import inserts as tinserts  # noqa: E402
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
    assert "System Flow" in avoid and "Stick" in avoid and "Photo Explainer" in avoid
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
    assert set(p["extra"]["skins"]) == {"house", "crt", "paper"}  # paper: an insert on a light canvas
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
    assert set(tvs.NO_MASCOT_STYLES) == {"cartoon_3d", "under_the_hood", "case_file_story", "paper_diorama",
                                         "archive_engraving", "editorial_collage", "storybook_reveal"}
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="working")}
    assert rows["under_the_hood"]["mascot"] is False and rows["cartoon_3d"]["mascot"] is False
    assert rows["auto"]["mascot"] is True and rows["stick"]["mascot"] is True


def test_paper_diorama():
    p = tvs.pack("paper_diorama")
    assert p["renderer"] == "dom" and p["canvas"] == "light" and p["role"] == "main"
    assert p["authoring_skill"] == "tubematic-paper-diorama"
    assert p["experimental"] is True and p["order"] == 110
    assert p["inserts"] == {"host": True, "transition": "cut"}
    # code-drawn paper: no images, no key, no GPU, its own critter in place of a mascot
    assert tvs.needs_openai_key("paper_diorama") is False and tvs.needs_gpu("paper_diorama") is False
    assert p["routing"]["images"] == 0 and "pictures" not in p
    assert "paper_diorama" in tvs.NO_MASCOT_STYLES and "critter" in p["messages"]["mascot"]
    assert p["captions"]["look"] == "tags" and p["captions"]["maxWords"] == 3
    assert "Bean Explainer" in " ".join(p["routing"]["avoid_for"])
    assert "Stick Explainer" in " ".join(p["routing"]["avoid_for"])
    for phrase in ("room", "banner", "stressed word", "brand"):
        assert phrase in p["script"], phrase


def test_archive_engraving():
    p = tvs.pack("archive_engraving")
    assert p["renderer"] == "dom" and p["canvas"] == "light" and p["role"] == "main"
    assert p["authoring_skill"] == "tubematic-archive-engraving"
    assert p["experimental"] is True and p["order"] == 130 and p["dimension"] == "2d"
    assert p["inserts"] == {"host": True, "transition": "dip"}
    # built on generated engravings: refused without an OpenAI key, no GPU, no mascot
    assert tvs.needs_openai_key("archive_engraving") is True and tvs.needs_gpu("archive_engraving") is False
    assert "OpenAI" in tvs.openai_key_error("archive_engraving")
    assert tvs.characters_allowed("archive_engraving") is False
    assert "archive_engraving" in tvs.NO_MASCOT_STYLES and p["mascot"] is False
    # ten engravings, each baked with the engraving treatment, every still tall
    assert p["routing"]["images"] == 10
    pics = p["pictures"]
    assert pics["treatments"] == ["engraving"] and pics["still_aspect"] == "9:16"
    assert "{count}" in pics["cap_message"] and "{cap}" in pics["cap_message"]
    for phrase in ("engraving", "no detailed face", "No text"):
        assert phrase in pics["still_style"], phrase
    assert p["captions"]["look"] == "fill" and p["captions"]["background"] == "chip"
    assert p["captions"]["position"] == 0.73 and p["captions"]["maxWords"] == 5
    assert "face" in p["routing"]["cannot_show"]
    for name in ("Storybook Atlas", "Photo Explainer", "Paper Diorama"):
        assert name in " ".join(p["routing"]["avoid_for"]), name
    for phrase in ("name card", "dates", "red", "brands"):
        assert phrase in p["script"], phrase


def test_editorial_collage():
    p = tvs.pack("editorial_collage")
    assert p["renderer"] == "dom" and p["canvas"] == "light" and p["role"] == "main"
    assert p["authoring_skill"] == "tubematic-editorial-collage"
    assert p["experimental"] is True and p["order"] == 120 and p["dimension"] == "2d"
    assert p["inserts"] == {"host": True, "transition": "cut"}
    # built on generated prints and cut-outs: refused without an OpenAI key, no GPU, no mascot
    assert tvs.needs_openai_key("editorial_collage") is True and tvs.needs_gpu("editorial_collage") is False
    assert "OpenAI" in tvs.openai_key_error("editorial_collage")
    assert tvs.characters_allowed("editorial_collage") is False and tvs.figures_allowed("editorial_collage") is True
    assert "editorial_collage" in tvs.NO_MASCOT_STYLES and p["mascot"] is False
    # ten stills, each baked as a print or a sticker, in the shape the agent asks for
    assert p["routing"]["images"] == 10
    pics = p["pictures"]
    assert pics["treatments"] == ["print", "sticker"] and "still_aspect" not in pics
    assert "{count}" in pics["cap_message"] and "{cap}" in pics["cap_message"]
    for phrase in ("No text, no letters, no logos, no watermark, no brand names", "no detailed face"):
        assert phrase in pics["still_style"], phrase
    caps = p["captions"]
    assert caps["look"] == "highlight" and caps["position"] == 0.73 and caps["maxWords"] == 4
    assert "Source Serif 4" in caps["fontFamily"]
    assert "face" in p["routing"]["cannot_show"] and "logo" in p["routing"]["cannot_show"]
    for name in ("Photo Explainer", "Case File Story", "Stick Explainer", "Bean Explainer", "Paper Diorama"):
        assert name in " ".join(p["routing"]["avoid_for"]), name
    for phrase in ("station", "dates", "numbers", "never describe a face", "newspaper"):
        assert phrase in p["script"], phrase


def test_storybook_reveal():
    p = tvs.pack("storybook_reveal")
    assert p["renderer"] == "dom" and p["canvas"] == "light" and p["role"] == "main"
    assert p["authoring_skill"] == "tubematic-storybook-reveal"
    assert p["experimental"] is True and p["order"] == 140 and p["dimension"] == "2d"
    assert p["inserts"] == {"host": True, "transition": "wipe"}
    # built on generated pages: refused without an OpenAI key, no GPU, no mascot
    assert tvs.needs_openai_key("storybook_reveal") is True and tvs.needs_gpu("storybook_reveal") is False
    assert "OpenAI" in tvs.openai_key_error("storybook_reveal")
    assert tvs.characters_allowed("storybook_reveal") is False and tvs.figures_allowed("storybook_reveal") is True
    assert "storybook_reveal" in tvs.NO_MASCOT_STYLES and p["mascot"] is False
    # twelve pages and the hero sheet in a slot of its own, made from a description alone (no house file)
    assert p["routing"]["images"] == 13
    pics = p["pictures"]
    assert pics["apart"] == ["hero"] and pics["sheet"]["name"] == "hero" and "house" not in pics["sheet"]
    assert pics["treatments"] == ["pencil"] and pics["still_aspect"] == "1:1"
    assert pics["still_lead"].startswith("The character from the reference picture")
    for phrase in ("coloured pencil", "watercolour", "cream paper", "No text"):
        assert phrase in pics["still_style"], phrase
    assert p["captions"]["look"] == "fill" and p["captions"]["background"] == "none"
    assert p["captions"]["position"] == 0.72 and p["captions"]["maxWords"] == 5
    assert "real people" in p["routing"]["cannot_show"]
    for name in ("Storybook Atlas", "Archive and Engraving", "Illustrated", "Stick Explainer", "Bean Explainer"):
        assert name in " ".join(p["routing"]["avoid_for"]), name
    for phrase in ("one protagonist", "moral", "brand"):
        assert phrase in p["script"], phrase


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
    pics = p["pictures"]
    assert pics["still_lead"].strip() and pics["still_style"].strip() and pics["still_aspect"] == "9:16"
    assert pics["sheet"]["name"] == "lead" and pics["sheet"]["house"] == "house" and pics["apart"] == ["lead"]
    assert pics["sheet"]["lead"].strip() and pics["sheet"]["style"].strip()
    # the script text carries the ending and the subject line the user set
    script = p["script"]
    for phrase in ("second person", "the last sentence is only the two options", "invented",
                   "Never write it as instructions", "No violence", "at most sixteen pictures",
                   # the cards' limits, so the script names things the cards can show
                   "at most 26 characters", "at most 16 characters", "at most 10 characters"):
        assert phrase in script, phrase
    assert "comes before the ending" in script
    # what is real and what belongs to the invented situation
    assert "Every law, limit, threshold, penalty and term in it is real" in script
    assert "belong to the invented situation" in script
    # the choice question varies from video to video, and a closing line the preferences ask for follows it
    assert "starts with the first option" in script and "a closing line the preferences ask for" in script
    assert "close-ups and the closing choice" in p["review"]


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
    ({"routing": {"best_for": ["a"], "avoid_for": [], "signals": []}}, "routing.cannot_show"),
    ({"routing": {"best_for": ["a"], "avoid_for": [], "signals": [], "cannot_show": " "}}, "routing.cannot_show"),
    ({"review": ""}, "review"),
    ({"script": "  "}, "script"),
    ({"picture": None}, "picture"),
    ({"picture": {"opening": "a", "turn": "b", "payoff": "c"}}, "picture"),
    ({"picture": {"opening": "a", "turn": "b", "payoff": "c", "ending": " "}}, "picture"),
    ({"dimension": "2.5d"}, "dimension"),
    ({"dimension": None}, "dimension"),
    ({"preview": ""}, "preview"),
    ({"preview": "../stick"}, "preview"),
    ({"preview": "Stick.mp4"}, "preview"),
    ({"tagline": " "}, "tagline"),
])
def test_a_malformed_pack_is_refused(over, fragment):
    with pytest.raises(tvs.PackError, match=fragment.replace(".", r"\.")):
        tvs._check_pack(pathlib.Path("stick.json"), _valid(**over))


def _pictured(**pics):
    """Case File Story's pack with its pictures block changed."""
    data = json.loads((tvs.PACKS_DIR / "case_file_story.json").read_text())
    data["pictures"] = {**data["pictures"], **pics}
    return data


@pytest.mark.parametrize("pics, fragment", [
    ({"cap_message": "too many"}, "cap_message"),
    ({"still_style": ""}, "still_style"),
    ({"still_aspect": "4:3"}, "still_aspect"),
    ({"treatments": ["sepia"]}, "treatments"),
    ({"treatments": ["print", "print"]}, "treatments"),
    ({"apart": []}, "sheet.name must be in pictures.apart"),
    ({"sheet": {"name": "lead", "lead": "a", "style": "b", "house": "house"}}, "house and house_file"),
    ({"sheet": {"name": "lead", "lead": "a"}}, "pictures.sheet must have"),
    ({"colour": "red"}, "has only the keys"),
])
def test_a_malformed_pictures_block_is_refused(pics, fragment):
    with pytest.raises(tvs.PackError, match=fragment.replace(".", r"\.")):
        tvs._check_pack(pathlib.Path("case_file_story.json"), _pictured(**pics))


def test_a_pictures_block_needs_an_openai_key_and_a_cap():
    data = _pictured()
    data["needs"] = {"openai_key": False, "gpu": False}
    with pytest.raises(tvs.PackError, match="needs.openai_key"):
        tvs._check_pack(pathlib.Path("case_file_story.json"), data)
    data = _pictured()
    data["routing"] = {**data["routing"], "images": 0}
    with pytest.raises(tvs.PackError, match="routing.images"):
        tvs._check_pack(pathlib.Path("case_file_story.json"), data)


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
    data["routing"] = {k: data["routing"][k] for k in ("best_for", "avoid_for", "signals", "cannot_show")}
    data.pop("script", None)
    tvs._check_pack(pathlib.Path("stick.json"), data)


def test_every_style_says_how_it_shows_the_opening_the_turn_and_the_payoff():
    # The scene author reads these to put a change on each turn and re-opening
    # and the strongest picture on the payoff; a style without them leaves
    # the beats with nothing on screen.
    for sid, pack in tvs.PACKS.items():
        assert set(pack["picture"]) == set(tvs.PICTURE_KEYS), sid
        view = tvs.agent_view(sid)["picture"]
        assert view == pack["picture"] and view is not pack["picture"], sid
    assert tvs.agent_view("auto")["picture"] == tvs.SCENES_PICTURE
    assert tvs.agent_view("")["picture"] == tvs.SCENES_PICTURE


def test_a_style_with_its_own_ending_says_so():
    # The user's decision: Case File Story ends on its choice card and
    # Whiteboard on its recap; every other style holds on the payoff.
    assert "choice card" in tvs.PACKS["case_file_story"]["picture"]["ending"]
    assert "recap" in tvs.PACKS["whiteboard"]["picture"]["ending"]
    assert "No closing card" in tvs.SCENES_PICTURE["ending"]


def test_the_agent_view_carries_the_style_script_guidance():
    assert "component" in tvs.agent_view("system_flow")["script"]
    assert tvs.agent_view("stick")["script"] == ""
    assert tvs.agent_view("auto")["script"] == ""


# ── main styles and insert styles (TMDEV-224) ────────────────────────────────

def test_the_insert_styles_are_the_insert_only_styles_and_the_rest_are_main():
    # The user's decision (TMDEV-223): these are only ever scenes inside another
    # style's video, never a whole video.
    assert set(tvs.INSERT_STYLES) == {"system_flow", "terminal_doc", "code_scenes", "format_packs"}
    assert tvs.MAIN_STYLES == ("auto",) + tuple(s for s in tvs.PACKS if s not in tvs.INSERT_STYLES)
    # A stored legacy value still reads as a style.
    assert {"system_flow", "terminal_doc"} <= set(tvs.VISUAL_STYLES)


def test_every_main_style_hosts_inserts_except_cartoon_3d():
    hosts = {sid: tvs.hosts_inserts(sid)["host"] for sid in tvs.MAIN_PACKS}
    assert {sid for sid, host in hosts.items() if not host} == {"cartoon_3d"}
    assert tvs.hosts_inserts("auto") == tvs.SCENES_INSERTS
    assert tvs.hosts_inserts("system_flow") == {"host": False}  # a legacy whole-video video
    for sid, p in tvs.MAIN_PACKS.items():
        if p["inserts"]["host"]:
            assert p["inserts"]["transition"] in tinserts.TRANSITIONS, sid
    assert tvs.PACKS["cartoon_3d"]["messages"]["inserts"]


def test_an_insert_style_is_refused_as_a_video_style_with_a_reason():
    assert "insert style" in tvs.insert_style_error("system_flow")
    assert "Terminal Doc" in tvs.insert_style_error(" terminal_doc ")
    assert tvs.insert_style_error("whiteboard") == ""
    assert tvs.insert_style_error("auto") == ""


def test_the_public_list_and_the_agent_view_carry_the_role():
    rows = {r["id"]: r for r in tvs.public_list(True, "working")}
    assert rows["system_flow"]["role"] == "insert"
    assert rows["whiteboard"]["role"] == "main" and rows["whiteboard"]["inserts"]["host"] is True
    assert rows["cartoon_3d"]["inserts"] == {"host": False}
    assert rows["auto"]["role"] == "main"
    view = tvs.agent_view("bean_explainer")
    assert view["role"] == "main" and view["inserts"] == {"host": True, "transition": "wipe"}
    assert tvs.agent_view("auto")["inserts"] == tvs.SCENES_INSERTS


def _insert_pack(**over):
    data = json.loads((tvs.PACKS_DIR / "system_flow.json").read_text())
    data.update(over)
    return data


@pytest.mark.parametrize("make, fragment", [
    (lambda: _valid(role="side"), "role must be one of"),
    (lambda: {k: v for k, v in _valid().items() if k != "inserts"}, "inserts: {host"),
    (lambda: _valid(inserts={"host": True}), "inserts.transition"),
    (lambda: _valid(inserts={"host": True, "transition": "spin"}), "inserts.transition"),
    (lambda: _valid(inserts={"host": False, "transition": "cut"}), "only the key host"),
    (lambda: _valid(inserts={"host": False}), "messages.inserts"),
    (lambda: _valid(insert={"max_seconds": 8}), 'no "insert" block'),
    (lambda: _insert_pack(inserts={"host": True, "transition": "cut"}), 'no "inserts" block'),
    (lambda: _insert_pack(insert={"max_seconds": 8}), "insert: {max_seconds"),
    (lambda: _insert_pack(insert={"max_seconds": 20, "palettes": ["dark"], "props_key": "x", "component": "X", "block": [200, 1300], "review": "r"}),
     "insert.max_seconds"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["blue"], "props_key": "x", "component": "X", "block": [200, 1300], "review": "r"}),
     "insert.palettes"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["dark"], "props_key": "", "component": "X", "block": [200, 1300], "review": "r"}),
     "insert.props_key"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["dark"], "props_key": "x", "component": " ", "block": [200, 1300], "review": "r"}),
     "insert.component"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["dark"], "props_key": "x", "component": "X", "review": "r"}),
     "insert: {max_seconds"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["dark"], "props_key": "x", "component": "X",
                                  "block": [1300, 200], "review": "r"}), "insert.block"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["dark"], "props_key": "x", "component": "X",
                                  "block": [0.1, 0.6], "review": "r"}), "insert.block"),
    (lambda: _insert_pack(insert={"max_seconds": 8, "palettes": ["dark"], "props_key": "x", "component": "X",
                                  "block": [200, 2000], "review": "r"}), "insert.block"),
])
def test_a_malformed_role_block_is_refused(make, fragment):
    data = make()
    name = "system_flow.json" if data.get("id") == "system_flow" else "stick.json"
    with pytest.raises(tvs.PackError, match=fragment.replace(".", r"\.")):
        tvs._check_pack(pathlib.Path(name), data)


# ── what the dashboard's picker shows (TMDEV-226) ─────────────────────────────

PREVIEW_DIR = REPO_ROOT / "dashboard" / "public" / "style-previews"
# The previews ship inside the dashboard image, so their size is part of every
# install's download. Each loop is a ~6 s, 540x960, silent H.264 clip; the
# folder budget leaves room for the 2.3.x round's new styles. Raise it only on
# purpose: scripts/make_style_preview.py re-encodes a clip that comes out over.
PREVIEW_MAX_BYTES = 400 * 1024
POSTER_MAX_BYTES = 40 * 1024
FOLDER_MAX_BYTES = 12 * 1024 * 1024


def test_the_picker_fields_come_from_the_packs():
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=True, gpu_status="working")}
    assert rows["auto"]["dimension"] is None and rows["auto"]["preview"] is None
    assert rows["auto"]["tagline"].strip()
    assert rows["cartoon_3d"]["dimension"] == "3d"
    for sid, p in tvs.PACKS.items():
        assert rows[sid]["dimension"] == p["dimension"]
        assert rows[sid]["preview"] == p["preview"]
        assert rows[sid]["tagline"] == p["tagline"]
    # the GPU tag reads needs.gpu, which only Cartoon 3D sets today
    assert [sid for sid, r in rows.items() if r["needs"]["gpu"]] == ["cartoon_3d"]


@pytest.mark.parametrize("sid", list(tvs.PACKS))
def test_every_pack_ships_its_preview_within_budget(sid):
    stem = tvs.PACKS[sid]["preview"]
    clip, poster = PREVIEW_DIR / f"{stem}.mp4", PREVIEW_DIR / f"{stem}.webp"
    assert clip.is_file(), f"{clip} is missing: make it with scripts/make_style_preview.py"
    assert poster.is_file(), f"{poster} is missing: make it with scripts/make_style_preview.py"
    assert clip.stat().st_size <= PREVIEW_MAX_BYTES, f"{clip.name} is over {PREVIEW_MAX_BYTES} bytes"
    assert poster.stat().st_size <= POSTER_MAX_BYTES, f"{poster.name} is over {POSTER_MAX_BYTES} bytes"


def test_the_preview_folder_stays_within_budget():
    total = sum(f.stat().st_size for f in PREVIEW_DIR.iterdir() if f.is_file())
    assert total <= FOLDER_MAX_BYTES, f"style previews total {total} bytes, over {FOLDER_MAX_BYTES}"
    stems = {f.stem for f in PREVIEW_DIR.iterdir() if f.suffix in (".mp4", ".webp")}
    for stem in stems:
        assert (PREVIEW_DIR / f"{stem}.mp4").is_file() and (PREVIEW_DIR / f"{stem}.webp").is_file(), stem


# ── Photo Explainer (TMDEV-225) ─────────────────────────────────────────────

def test_motion_graphics_is_labelled_photo_explainer_and_yields_close_calls():
    p = tvs.pack("motion_graphics")
    assert p["label"] == "Photo Explainer"  # the stored id is unchanged
    assert p["routing"]["yields_ties"] is True
    # Its diagrams are System Flow inserts: no picture duty asks it to build one.
    assert "diagram" not in " ".join(p["picture"].values()).lower()
    others = [sid for sid, q in tvs.MAIN_PACKS.items() if q["routing"].get("yields_ties")]
    assert others == ["motion_graphics"]


def test_yields_ties_is_checked_when_present():
    data = _valid()
    data["routing"] = {**data["routing"], "yields_ties": "yes"}
    with pytest.raises(tvs.PackError, match=r"routing\.yields_ties"):
        tvs._check_pack(pathlib.Path("stick.json"), data)
