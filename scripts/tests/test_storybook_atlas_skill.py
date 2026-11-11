"""The Storybook Atlas skill. The operator hands a video to it by the name its
style pack gives (get_video's style.authoring_skill), so the name, the pack and
the operator's routing must agree, and the skill must be loadable by an
unattended run. Its limits and its catalogue must be the ones the validator
enforces: a skill that teaches a refused value teaches the agent to be refused,
and a prop or backdrop it does not list is one the agent will not use.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-storybook-atlas"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import storybook_atlas as sa  # noqa: E402

EXTRA = tvs.pack("storybook_atlas")["extra"]


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-storybook-atlas$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("storybook_atlas")["authoring_skill"] == "tubematic-storybook-atlas"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-storybook-atlas" in operator


def test_the_contract_lists_exactly_the_props_backdrops_and_knobs_the_validator_accepts():
    text = _contract()
    rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| `(\w+)` \| [^|]+ \| (floor|wall) \|.*$", text, re.M)}
    assert set(rows) == set(EXTRA["props"])
    for prop, spec in EXTRA["props"].items():
        row = rows[prop]
        assert f"| {spec['box'][0]} x {spec['box'][1]} | {spec['states']} |" in row, prop
        for act in spec["acts"]:
            assert act in row, (prop, act)
        assert ("| yes |" in row) == bool(spec.get("portal")), prop
    backdrops = set(re.findall(r"^\| `(\w+)` \| [^|]+ \|$", text.split("## Backdrops")[1].split("## Props")[0], re.M))
    assert backdrops == set(EXTRA["backdrops"])
    for knob, values in EXTRA["knobs"].items():
        assert f"| `{knob}` | " + ", ".join(f"`{v}`" for v in values) + " |" in text, knob
    for coat in EXTRA["coats"]:
        assert f"`{coat}`" in text


def test_the_skill_states_the_validators_limits():
    text = " ".join(_text().split())
    lo, hi = sa.LIMITS["chapters"]
    for phrase in (f"{lo} to {hi}.", f"within {sa.TIMING['onWord']} frames", f"at least {sa.LIMITS['chapterMinSeconds']} seconds long",
                   f"2 lines of {sa.LIMITS['title']} characters", f"at most {sa.LIMITS['byline']}",
                   f"{sa.TIMING['endMargin']} frames before it ends", f"at least {sa.TIMING['pushFrames']} frames before the cut",
                   f"last {sa.LIMITS['plateSeconds'][0]} to {sa.LIMITS['plateSeconds'][1]} seconds",
                   f"at most {sa.LIMITS['cast']} in the cast", f"at most {sa.LIMITS['onStage']} on stage at once",
                   f"at most {sa.LIMITS['propsOnStage']} in a chapter", f"from {sa.STAGE['wallBase'][0]} to {sa.STAGE['wallBase'][1]}",
                   f"({sa.TIMING['propIn']} frames after it appears)", f"at most {sa.LIMITS['tag']} characters",
                   f"at least every {sa.LIMITS['quietSeconds']} seconds", f"{sa.TIMING['walkSpeed']} px a frame",
                   f"{2 * sa.PERSON_HALF} px of floor", f"the guide {2 * sa.GUIDE_HALF}"):
        assert phrase in text, phrase


def test_the_skill_names_the_tools_it_uses_and_never_the_image_tools_as_steps():
    text = " ".join(_text().split())
    for tool in ("get_video", "get_timeline", "write_scene_config", "validate_job", "submit_render", "render_storybook_props"):
        assert tool in text
    assert "never call `generate_image`" in text


def test_the_skill_names_every_backdrop_pose_and_event():
    text = _text()
    for b in EXTRA["backdrops"]:
        assert f"`{b}`" in text, b
    for kind in sa.EVENT_TYPES:
        assert f"`{kind}`" in text, kind
    for pose in [p for p in EXTRA["guidePoses"] + EXTRA["personPoses"] if not p.startswith("walk")]:
        assert f"`{pose}`" in text, pose


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    starts = [w["startFrame"] for w in timeline["words"]]
    assert sa.check(config, timeline["fps"], starts, EXTRA) == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-storybook-atlas"' in (REPO / "uninstall.py").read_text()


def test_the_skill_teaches_props_of_your_own_within_the_validators_limits():
    text = " ".join(_text().split())
    for phrase in (f"at most {sa.CUSTOM['maxProps']} per video", f"{sa.CUSTOM['minSide']} to {sa.CUSTOM['maxSide']} px",
                   f"1 to {sa.CUSTOM['maxStates']} states", f"1 to {sa.CUSTOM['maxActs']} acts",
                   "write_scene_file", "example-prop-moth.tsx", "storybookAtlas/ink"):
        assert phrase in text, phrase


def test_the_example_prop_passes_the_validators_source_checks():
    body = (SKILL / "reference" / "example-prop-moth.tsx").read_text()
    comment = " ".join(line.lstrip("/ ") for line in body.splitlines() if line.startswith("//"))
    spec = json.loads(re.search(r"(\{\"id\": \"moth\".*?\})(?=\s+Modelled)", comment).group(1))
    spec["src"] = "vid_x/prop-moth"
    errs, _ = sa.custom_prop_errors([spec], "vid_x", EXTRA["props"], {"vid_x/prop-moth": body})
    assert errs == []
