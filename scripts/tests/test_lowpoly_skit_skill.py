"""The Low-Poly Skit authoring skill (TMDEV-250): it names what the style needs, and points only at files that exist.

A skill that tells the agent to read a kit file the renderer does not ship, or to import a name the kit does not
export, sends it into a typecheck failure it cannot explain. The look of this style is the same cartoon_still and
beat gate as Cartoon 3D's (test_look_step.py), and it carries no rule about the words a script uses.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-lowpoly-skit"
KIT = REPO / "renderer" / "remotion" / "src" / "cartoon3d"
sys.path.insert(0, str(REPO))

from tubematic_core import visual_styles as tvs  # noqa: E402


def _text(*names) -> str:
    return "\n".join((SKILL / n).read_text(encoding="utf-8") for n in names)


def test_the_pack_names_this_skill_and_its_files_exist():
    assert tvs.pack("low_poly_skit")["authoring_skill"] == SKILL.name
    for rel in ("SKILL.md", "reference/kit.md", "reference/verifier.md"):
        assert (SKILL / rel).is_file(), rel


def test_every_kit_file_the_skill_reads_exists():
    body = _text("SKILL.md", "reference/kit.md")
    paths = set(re.findall(r'cartoon_kit_read\("([^"]+)"\)', body))
    assert "lowpoly/examples/dig/index.ts" in paths
    for rel in paths:
        assert (KIT / rel).is_file(), rel


def test_the_kit_reference_names_what_the_kit_exports():
    ref = _text("reference/kit.md")
    # name -> the kit file that must export it
    needs = {
        "buildFigure": "lowpoly/figure.ts", "setFace": "lowpoly/faces.ts", "applyPose": "lowpoly/poses.ts",
        "poseTrack": "lowpoly/poses.ts", "lerpPose": "lowpoly/poses.ts", "walkPose": "lowpoly/cycles.ts",
        "dancePose": "lowpoly/cycles.ts", "idlePose": "lowpoly/cycles.ts", "footfalls": "lowpoly/cycles.ts",
        "Crowd": "lowpoly/crowd.ts", "Burst": "lowpoly/fx.ts", "Debris": "lowpoly/fx.ts", "ComicWord": "lowpoly/fx.ts",
        "lightCone": "lowpoly/fx.ts", "ramp": "lowpoly/fx.ts", "room": "lowpoly/diorama.ts", "box": "lowpoly/diorama.ts",
        "sign": "lowpoly/diorama.ts", "globe": "lowpoly/diorama.ts", "strata": "lowpoly/diorama.ts",
        "discs": "lowpoly/diorama.ts", "joltAt": "camera.ts", "jolted": "camera.ts", "whip": "camera.ts",
        "LowPolyDef": "lowpoly/def.ts", "LPShot": "lowpoly/def.ts", "randomOutfit": "lowpoly/figure.ts",
    }
    for name, rel in needs.items():
        assert name in ref, f"kit.md never mentions {name}"
        src = (KIT / rel).read_text(encoding="utf-8")
        assert re.search(rf"export (?:const|function|class|type|interface) {name}\b", src), f"{rel} does not export {name}"


def test_every_named_pose_and_face_exists():
    ref = _text("reference/kit.md")
    poses = (KIT / "lowpoly" / "poses.ts").read_text(encoding="utf-8")
    for name in "stand sit lie fall thrust bang point hold cheer shrug slump stomp flinch".split():
        assert re.search(rf"^  {name}:", poses, re.M), name
        assert name in ref, name
    faces = (KIT / "lowpoly" / "faces.ts").read_text(encoding="utf-8")
    for name in "neutral smile smug shock shout worry grin blank".split():
        assert f'"{name}"' in faces, name


def test_the_skill_writes_the_scene_the_3d_worlds_share():
    body = _text("SKILL.md")
    # the engine's entry module and beats marker are Cartoon 3D's, by contract (mcp/cartoon.py)
    assert "CartoonShort.tsx" in body and '"cartoon3d": {"beats"' in body
    assert "cartoon_beat_gate" in body and "cartoon_soundtrack" in body and "cartoon_still" in body
    assert "LowPolyShort" in body


def test_the_style_carries_no_rule_about_the_words_a_script_uses():
    # a person decides the register of a script; nothing in this style filters, flags or discourages any word
    pack = tvs.pack("low_poly_skit")
    text = (_text("SKILL.md", "reference/kit.md", "reference/verifier.md") + str(pack.get("script", "")) + str(pack.get("review", ""))).lower()
    for phrase in ("profan", "swear", "clean language", "family-friendly", "family friendly", "bleep"):
        assert phrase not in text, phrase
