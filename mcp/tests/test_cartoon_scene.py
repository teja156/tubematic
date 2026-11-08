"""Tests for the shape of a Cartoon 3D scene-config (TMDEV-185), as far as
write_scene_config can see it.

A Cartoon 3D video is one generated scene spanning the whole video, the
`<video_id>/CartoonShort` the agent wrote, whose props carry `cartoon3d:
{beats}`. The code itself is typechecked by validate_job and judged by the
beat gate; what is worth pinning here is that a config whose scene is not even
the right SHAPE is refused with a reason, and that a config without such a
scene is untouched.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pytest

import server

VID = "vid_a"


def _scene(**over):
    scene = {"type": "generated", "src": f"{VID}/CartoonShort", "startFrame": 0, "durationInFrames": 300,
             "props": {"cartoon3d": {"beats": [{"start": 0, "end": 299, "shot": "the quay at dawn"}]}}}
    scene.update(over)
    return scene


def test_a_sound_scene_passes_and_a_config_without_one_is_not_looked_at():
    assert server._validate_cartoon_scene([_scene()], 300, VID) == ""
    assert server._validate_cartoon_scene([_scene()]) == ""                 # the shape alone, no frame count
    assert server._validate_cartoon_scene([{"src": "KenBurnsImage", "props": {}}, {"src": "x/y"}], 300, VID) == ""
    assert server._validate_cartoon_scene([], 300, VID) == ""


@pytest.mark.parametrize("scenes, total, fragment", [
    ([_scene(), _scene()], 300, "exactly one generated scene"),
    ([_scene(), {"src": "x/intro", "props": {}}], 300, "exactly one generated scene"),
    ([_scene(source="installed", src="Cartoon3D")], 300, "not an installed one"),
    ([_scene(src="vid_b/CartoonShort")], 300, f"must be '{VID}/CartoonShort'"),
    ([_scene(src=f"{VID}/intro")], 300, f"must be '{VID}/CartoonShort'"),
    ([_scene(startFrame=10)], 300, "must start at frame 0"),
    ([_scene(durationInFrames=200)], 300, "must span the whole video"),
    ([_scene(props={"cartoon3d": {"beats": []}})], 300, "non-empty list of beats"),
    ([_scene(props={"cartoon3d": {"beats": [{"start": 0, "end": 299}]}})], 300, "needs a 'shot'"),
    ([_scene(props={"cartoon3d": {"beats": [{"start": 0, "end": 99, "shot": "a"}, {"start": 101, "end": 299, "shot": "b"}]}})], 300, "frame 100 is the first not yet covered"),
    ([_scene(props={"cartoon3d": {"beats": [{"start": 0, "end": 250, "shot": "a"}]}})], 300, "must end at frame 299"),
    ([_scene(props={"cartoon3d": {"beats": [{"start": 0, "end": "299", "shot": "a"}]}})], 300, "integer start and end"),
])
def test_a_malformed_cartoon_scene_is_refused_with_a_reason(scenes, total, fragment):
    err = server._validate_cartoon_scene(scenes, total, VID)
    assert fragment in err, err


def test_without_a_video_id_the_src_only_has_to_name_the_entry_scene():
    assert server._validate_cartoon_scene([_scene(src="whoever/CartoonShort")], 300) == ""
    assert "CartoonShort" in server._validate_cartoon_scene([_scene(src="whoever/intro")], 300)
