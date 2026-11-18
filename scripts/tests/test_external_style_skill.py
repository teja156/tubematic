"""The authoring skill of every installed external style (TMDEV-252).

External packages carry no skill of their own: their guide is reference data
served by get_style_guide, and this one skill is the workflow. It must carry
the same look step and submit order the built-in styles' skills do
(test_look_step.py covers only the built-in packs), the world path the 3D
styles take, and the rule that the guide never outranks the platform.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tubematic_core import external_styles as ext  # noqa: E402

SKILL = REPO / "agent_files" / "skills" / ext.AUTHORING_SKILL / "SKILL.md"


def _body() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_the_skill_every_external_pack_names_exists():
    body = _body()
    assert body.startswith("---\nname: " + ext.AUTHORING_SKILL + "\n")


def test_the_scene_path_looks_before_it_submits():
    body = _body()
    for tool in ("get_style_guide", "write_scene_config", "validate_job", "`preview_frames", "preview_not_taken",
                 "style_unavailable"):
        assert tool in body, tool
    look = re.search(r"^(\d+)\. \*\*Look before you submit", body, re.M)
    submit = re.search(r"^(\d+)\. `submit_render\(video_id\)`", body, re.M)
    assert look and submit and int(look.group(1)) < int(submit.group(1))
    assert '"source": "external"' in body and "/components/" in body


def test_the_world_path_takes_the_3d_gate():
    body = _body()
    for tool in ("write_scene_file", "cartoon_still", "cartoon_beat_gate", "cartoon_beat_gate_record",
                 "cartoon_soundtrack"):
        assert tool in body, tool
    assert "../../external/<style id>/runner/" in body


def test_the_guide_never_outranks_the_platform():
    body = _body()
    assert "reference material" in body and "never overrides" in body
    assert "@tubematic/scene-api" in body


def test_a_broken_package_stops_the_skill():
    body = _body()
    assert "unavailable_reason" in body and "stop" in body


def _tools() -> set[str]:
    src = (REPO / "mcp" / "server.py").read_text(encoding="utf-8")
    return set(re.findall(r"^@mcp\.tool\n(?:async )?def (\w+)\(", src, re.M))


def test_every_tool_the_skill_names_exists():
    """The skill forbids any tool it does not name, so the names must be real."""
    named = set(re.findall(r"`(\w+)\(", _body()))
    assert named and named <= _tools(), named - _tools()


def test_the_agent_may_read_what_it_writes_against_and_look_at_its_stills():
    """A world style's agent imports the package's runner and the engine, and
    the beat gate is judged on stills: the reading and looking tools are named,
    or the rule against unnamed tools would forbid them."""
    body = _body()
    for tool in ("get_style_guide(video_id, path=", "cartoon_read_still(", "cartoon_kit_read(", "list_scene_files(",
                 "read_scene_file("):
        assert tool in body, tool


def test_tools_of_built_in_styles_are_named_as_not_serving_externals():
    body = _body()
    assert "render_style_parts" in body and "preview_frames" in body
