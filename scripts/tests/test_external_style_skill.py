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
