"""Tests for the agent-made parts of a Cartoon 3D scene (TMDEV-181), as far as
write_scene_config can see them.

A Cartoon 3D world rides inside one installed "Cartoon3D" scene, and may
carry parts the agent wrote in the renderer's part grammar under
props.world.parts. The grammar's real checks (sizes, materials, nothing
floating, the vision judge) live in the renderer and cannot be reached from
Python; what is worth pinning here is that a file whose parts are not even the
right SHAPE is refused with a reason, and that a world without parts (every
world before this feature) is untouched.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pytest

import server


BOLLARD = {
    "name": "bollard",
    "blurb": "iron mooring post on a square base",
    "prims": [
        {"kind": "box", "size": [0.6, 0.1, 0.6], "at": [0, 0.05, 0], "mat": "iron"},
        {"kind": "cylinder", "r": 0.12, "h": 0.9, "at": [0, 0.55, 0], "mat": "iron"},
    ],
}


def _scenes(parts):
    world = {"name": "quay", "pieces": []}
    if parts is not None:
        world["parts"] = parts
    return [{"type": "generated", "source": "installed", "src": "Cartoon3D",
             "startFrame": 0, "durationInFrames": 100, "props": {"world": world, "beats": []}}]


def test_sound_parts_and_no_parts_pass():
    assert server._validate_cartoon_parts(_scenes({"bollard": BOLLARD})) == ""
    assert server._validate_cartoon_parts(_scenes(None)) == ""
    # a scene that is not Cartoon 3D is not looked at
    assert server._validate_cartoon_parts([{"src": "KenBurnsImage", "props": {}}]) == ""


@pytest.mark.parametrize("parts, fragment", [
    ({"Big Post": BOLLARD}, "lowerCamelCase"),
    ({"post": BOLLARD}, "name must equal its key"),
    ({"bollard": {**BOLLARD, "blurb": " "}}, "blurb"),
    ({"bollard": {**BOLLARD, "prims": []}}, "non-empty list"),
    ({"bollard": {**BOLLARD, "prims": [{"kind": "blob"}]}}, "kind must be one of"),
    ({"bollard": {**BOLLARD, "prims": [{"kind": "box", "repeat": {"n": 0}}]}}, "repeat.n"),
    ({"bollard": {**BOLLARD, "prims": [{"kind": "box", "repeat": {"n": 161}}]}}, "more than 160"),
    ({"bollard": {**BOLLARD, "prims": [{"kind": "group", "items": []}]}}, "items must be"),
    ("not an object", "keyed by part name"),
])
def test_malformed_parts_are_refused_with_a_reason(parts, fragment):
    err = server._validate_cartoon_parts(_scenes(parts))
    assert fragment in err, err
    assert err.startswith("scenes[0].props.world.")


def test_nested_groups_are_walked_and_capped():
    deep = {"kind": "group", "items": [{"kind": "box"}]}
    for _ in range(4):
        deep = {"kind": "group", "items": [deep]}
    err = server._validate_cartoon_parts(_scenes({"bollard": {**BOLLARD, "prims": [deep]}}))
    assert "deeper than 4" in err


def test_cartoon_scene_without_a_world_is_refused():
    scenes = [{"src": "Cartoon3D", "props": {"beats": []}}]
    assert "needs props.world" in server._validate_cartoon_parts(scenes)
