"""Source guards for the "Made with tubematic.ai" watermark (TMDEV-141).

The mark is drawn by renderer/remotion/src/Watermark.tsx, and
renderer/remotion/ has no JS test runner, so nothing here can execute it —
same position as Subtitles.tsx (see test_subtitles.py). What can be pinned from
Python is the one property the feature exists for: the agent cannot move, dim
or remove the mark, because nothing about it comes from scene-config.json.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pathlib

from PIL import Image

import server

_REPO = pathlib.Path(server.__file__).resolve().parents[1]
_SRC = _REPO / "renderer" / "remotion" / "src"
_ASSET = _REPO / "renderer" / "remotion" / "public" / "watermark.png"


def _builder() -> str:
    return (_SRC / "CompositionBuilder.tsx").read_text()


def _watermark() -> str:
    return (_SRC / "Watermark.tsx").read_text()


def test_the_composition_draws_the_watermark_last_and_outside_the_scene_list():
    """After the captions, so it paints over every scene, and not inside the
    scenes map: a scene entry is wrapped in a Sequence and SceneWithFades,
    which would dissolve the mark at every scene boundary."""
    src = _builder()
    scenes_end = src.index("{/* ── Subtitles")
    mark = src.index("<Watermark />")
    assert mark > src.index("<Subtitles")
    assert "<Watermark" not in src[src.index("sceneConfig.scenes.map"):scenes_end]


def test_the_watermark_is_given_no_props():
    """No props is the whole guarantee. A prop is a value somebody upstream
    chose, and the only upstream with opinions about a frame is the agent."""
    assert _builder().count("<Watermark") == 1
    assert "<Watermark />" in _builder()
    assert "React.FC = ()" in _watermark()


def test_only_the_render_prop_can_switch_it_off_never_scene_config():
    """The switch is the watermark_enabled setting, passed by the worker as a
    render prop. Reading it from sceneConfig instead would look equivalent and
    would hand the switch to whoever writes scene-config.json — the agent."""
    src = _builder()
    assert "{watermark !== false && <Watermark />}" in src
    assert "sceneConfig.watermark" not in src
    iface = src[src.index("interface SceneConfigFile"):]
    assert "watermark" not in iface[:iface.index("}")]
    assert "sceneConfig" not in _watermark()


def test_an_absent_prop_means_the_watermark_is_drawn():
    """`!== false`, not a truthiness test: the text audit and Studio preview
    send no such prop, and must show the same frame the render does."""
    assert "watermark !== false" in _builder()
    assert "watermark &&" not in _builder()


def test_no_scene_z_index_can_cover_the_watermark():
    """DOM order alone does not put the mark on top: a positioned scene
    element with a positive z-index paints above a later z-index:auto sibling,
    so one full-frame layered element in an agent-written scene would hide the
    mark. The maximum z-index cannot be exceeded, and a tie goes to the later
    element. Lowering it to a "reasonable" number reopens the hole."""
    src = _watermark()
    assert "const Z_INDEX = 2147483647;" in src
    assert "zIndex: Z_INDEX" in src


def test_the_asset_is_local_never_fetched():
    """The mark is on the path of every render. A renderer with no egress
    would stall on a network fetch, turning branding into a pipeline outage —
    the reason the captions' default font is not a webfont either."""
    src = _watermark()
    assert 'staticFile("watermark.png")' in src
    assert "http" not in src


def test_the_baked_asset_is_the_chosen_artwork():
    """The plate-backed `smoke` variant, byte for byte. A plate-less variant
    was tried in real renders and lost its text on light backgrounds, so a
    swap here is a legibility decision, not a cosmetic one."""
    source = _REPO / "logos" / "watermarks" / "watermark-smoke-4x.png"
    assert _ASSET.read_bytes() == source.read_bytes()
    with Image.open(_ASSET) as im:
        assert im.size == (480, 630)
        assert im.mode == "RGBA"
