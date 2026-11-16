"""Every video is looked at before it is queued (TMDEV-241).

preview_frames draws chosen frames of the composed scene, and submit_render
refuses a video whose current scene-config nobody looked at. The refusal is
the backstop; the skills are what make the agent look on purpose, at the right
frames, and fix what it sees. A style whose skill never mentions the step
sends its agent into a refusal it has not been told about, so every style that
a person or Auto can pick must carry it, and a style added later cannot ship
without it.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
sys.path.insert(0, str(REPO))

from tubematic_core import visual_styles as tvs  # noqa: E402

# The 3D worlds (Cartoon 3D, Low-Poly Skit) draw their world from source and have their own look, cartoon_still,
# which their beat gate requires.
OWN_LOOK = set(tvs.WORLD_STYLES)
# Insert styles are scenes inside another style's video and are looked at in that style's step; these two
# also have a legacy whole-video path (a video voiced before they became insert styles), written by the
# same skill, which submits it.
LEGACY_WHOLE_VIDEO = {"system_flow", "terminal_doc"}


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _authoring_skills() -> dict[str, str]:
    out = {}
    for sid, pack in tvs.PACKS.items():
        if sid in OWN_LOOK:
            continue
        if pack["role"] == "main" or sid in LEGACY_WHOLE_VIDEO:
            out[sid] = pack["authoring_skill"]
    return out


def test_every_main_style_and_legacy_path_names_the_look_step():
    skills = _authoring_skills()
    assert skills, "no style found"
    for sid, name in skills.items():
        body = _skill(name)
        assert "`preview_frames" in body, f"{name} ({sid}) never tells the agent to look with preview_frames"
        assert "preview_not_taken" in body, f"{name} ({sid}) does not name the refusal an unlooked video meets"
        assert "Look before you submit" in body, f"{name} ({sid}) has no 'Look before you submit' step"


def test_the_look_comes_before_submit_render_in_each_skills_closing_steps():
    look_re = re.compile(r"^(\d+)\. \*\*Look before you submit", re.M)
    submit_re = re.compile(r"^(\d+)\. `submit_render\(video_id\)`", re.M)
    for sid, name in _authoring_skills().items():
        body = _skill(name)
        look = look_re.search(body)
        assert look, f"{name}: no numbered 'Look before you submit' step"
        submit = submit_re.search(body)
        if submit:      # the shared scene-config skill hands back to the operator instead of submitting
            assert int(look.group(1)) < int(submit.group(1)), f"{name}: the look step must precede its submit_render step"


def test_the_3d_worlds_keep_their_own_look():
    for sid in tvs.WORLD_STYLES:
        body = _skill(tvs.PACKS[sid]["authoring_skill"])
        assert "cartoon_still" in body, sid
        assert "preview_frames" not in body.replace("cartoon_still", ""), sid


def test_the_operator_looks_at_a_new_video_and_again_after_a_revision():
    text = _skill("tubematic-operator")
    assert "preview_frames, submit_render" in text           # the state table row
    assert "look at the video" in text                       # the VOICE_READY row
    assert "look again with `preview_frames`" in text        # the render revision row
    assert text.count("`preview_frames`, `submit_render`") >= 2   # the voice revisions re-enter the flow through it


def test_the_scene_config_skill_says_what_a_failed_tool_and_a_rewrite_mean():
    body = _skill("tubematic-scene-config")
    assert "preview_not_taken" in body and "records that it could not draw" in body
