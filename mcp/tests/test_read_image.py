"""Tests for the read_image MCP tool.

Requires the mcp/ package deps (fastmcp, pillow) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import hashlib
import io
import json
from datetime import datetime, timezone

import pytest
from PIL import Image, ImageDraw

import server

VID = "vid-1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Throwaway DB + jobs dir with one video row."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    # _scene_claims is module-level and every test here reuses VID, so a claim
    # taken by one test would otherwise still be held by the next.
    monkeypatch.setattr(server, "_scene_claims", {})
    server._init_db()
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, topic, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (VID, "test topic", _now(), _now()),
        )
    return tmp_path


def _write_image(tmp_path, name, size=(768, 1344), fmt=None):
    """Drop a real image into the video's images dir and return its path."""
    d = tmp_path / "jobs" / VID / "images"
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    im = Image.new("RGB", size, (40, 90, 140))
    # Something asymmetric, so a resize or a flip would be detectable.
    ImageDraw.Draw(im).rectangle(
        [0, 0, size[0] // 3, size[1] // 4], fill=(220, 40, 40)
    )
    im.save(path, format=fmt)
    return path


def _text(result):
    return json.loads(result[0])


def _decoded(result):
    return Image.open(io.BytesIO(result[1].data))


# --- guards ----------------------------------------------------------------

def test_rejects_image_name_with_path_traversal(env):
    out = server.read_image(VID, "../../etc/passwd")
    assert "must contain only alphanumeric characters and hyphens" in out["error"]


def test_rejects_empty_image_name(env):
    assert server.read_image(VID, "")["error"] == "image_name must not be empty"


def test_unknown_video(env):
    assert server.read_image("nope", "castle")["error"] == "Video not found: nope"


def test_missing_image_reports_the_name(env):
    out = server.read_image(VID, "absent")
    assert "No image named 'absent'" in out["error"]
    assert "generate_image" in out["detail"]


def test_a_name_long_enough_only_for_a_short_extension_is_read(env):
    """read_image finds files that already exist, so the shortest extension
    sets its cap: a 251-character `.png` (a character asset) is a valid 255-byte
    name. One character more fits no extension and is refused."""
    _write_image(env, f"{'x' * 251}.png")
    assert _text(server.read_image(VID, "x" * 251))["width"] == 768
    assert "image_name" in server.read_image(VID, "x" * 252)["error"]


def test_unreadable_file_is_an_error_not_a_crash(env):
    d = env / "jobs" / VID / "images"
    d.mkdir(parents=True, exist_ok=True)
    (d / "broken.png").write_bytes(b"not actually a png")
    assert "Could not read image" in server.read_image(VID, "broken")["error"]


# --- resolution ------------------------------------------------------------

@pytest.mark.parametrize("filename", ["a.png", "a.jpg", "a.jpeg", "a.webp"])
def test_resolves_extension_the_caller_does_not_know(env, filename):
    """generate_image's extension follows whatever the model returned, so the
    agent passes a bare stem and read_image works out the rest."""
    _write_image(env, filename)
    out = server.read_image(VID, "a")
    assert _text(out)["filename"] == filename
    assert _text(out)["public_path"] == f"/public/{VID}/images/{filename}"


def test_ignores_non_image_siblings(env):
    _write_image(env, "castle.png")
    (env / "jobs" / VID / "images" / "castle.txt").write_text("notes")
    assert _text(server.read_image(VID, "castle"))["filename"] == "castle.png"


# --- result shape ----------------------------------------------------------

def test_returns_a_text_block_then_a_real_image_block(env):
    _write_image(env, "castle.png")
    out = server.read_image(VID, "castle")
    assert len(out) == 2

    meta = _text(out)
    assert meta["width"] == 768 and meta["height"] == 1344
    assert meta["grid"] is True

    block = out[1].to_image_content()
    assert block.type == "image"
    assert block.mimeType == "image/png"
    assert len(block.data) > 0


def test_reports_the_stored_dimensions_not_the_delivered_ones(env):
    _write_image(env, "castle.png")
    meta = _text(server.read_image(VID, "castle"))
    assert (meta["width"], meta["height"]) == (768, 1344)
    assert "note" not in meta


# --- the grid --------------------------------------------------------------

def test_grid_is_drawn_by_default_and_can_be_turned_off(env):
    _write_image(env, "castle.png")
    gridded = server.read_image(VID, "castle")
    plain = server.read_image(VID, "castle", grid=False)

    assert _text(gridded)["grid"] is True
    assert _text(plain)["grid"] is False
    assert gridded[1].data != plain[1].data
    # Same picture underneath — only the annotation differs.
    assert _decoded(gridded).size == _decoded(plain).size


def test_reading_never_modifies_the_file_on_disk(env):
    """The renderer loads this exact file. Annotating it in place would put a
    coordinate grid into the finished video."""
    path = _write_image(env, "castle.png")
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    server.read_image(VID, "castle")
    server.read_image(VID, "castle", grid=False)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_grid_does_not_change_the_delivered_resolution(env):
    _write_image(env, "castle.png")
    assert _decoded(server.read_image(VID, "castle")).size == (768, 1344)


# --- font resolution -------------------------------------------------------

def test_font_candidates_match_the_fonts_the_container_actually_installs():
    """renderer/Dockerfile installs fonts-liberation and fonts-freefont-ttf,
    not DejaVu. A DejaVu-first list finds no font in the container."""
    assert server._GRID_FONT_PATHS[0].endswith("LiberationSans-Bold.ttf")
    assert server._GRID_FONT_PATHS[1].endswith("FreeSansBold.ttf")


def test_bitmap_fallback_does_not_crash_when_no_ttf_is_available(env, monkeypatch):
    """The fallback runs whenever none of the candidate TTFs exist. On
    Pillow < 10.1 load_default() returns a bitmap font with no `.size` and no
    stroke rendering — assuming FreeTypeFont there makes read_image error on
    its first real call instead of merely looking worse."""
    from PIL import ImageFont

    real_truetype = ImageFont.truetype

    def _no_font_files(font=None, *a, **kw):
        # Only filesystem paths are missing. load_default() loads embedded
        # font data through this same function, so blanket-failing it would
        # break the fallback itself rather than the thing under test.
        if isinstance(font, str):
            raise OSError("cannot open resource")
        return real_truetype(font, *a, **kw)

    monkeypatch.setattr(ImageFont, "truetype", _no_font_files)
    _write_image(env, "castle.png")

    out = server.read_image(VID, "castle")
    assert _text(out)["grid"] is True
    assert _decoded(out).size == (768, 1344)


def test_bitmap_fallback_reports_no_stroke_support(monkeypatch):
    from PIL import ImageFont

    class _Bitmap:
        """Stands in for the pre-10.1 bitmap font: no .size, no stroke."""

    monkeypatch.setattr(
        ImageFont, "truetype",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("nope")),
    )
    monkeypatch.setattr(ImageFont, "load_default", lambda *a, **kw: _Bitmap())

    font, stroked = server._load_grid_font(24)
    assert stroked is False
    assert isinstance(font, _Bitmap)


# --- downscaling -----------------------------------------------------------

def test_oversized_image_is_downscaled_for_delivery(env):
    _write_image(env, "big.png", size=(3000, 2000))
    out = server.read_image(VID, "big")

    assert max(_decoded(out).size) == server._READ_IMAGE_MAX_EDGE
    # Aspect preserved, so normalized [u, v] still means the same thing.
    assert _decoded(out).size == (1568, 1045)


def test_downscale_reports_true_dimensions_and_explains_itself(env):
    _write_image(env, "big.png", size=(3000, 2000))
    meta = _text(server.read_image(VID, "big"))

    assert (meta["width"], meta["height"]) == (3000, 2000)
    assert "3000x2000" in meta["note"]
    assert "coordinates are unaffected" in meta["note"]


def test_image_at_the_limit_is_left_alone(env):
    _write_image(env, "exact.png", size=(server._READ_IMAGE_MAX_EDGE, 800))
    out = server.read_image(VID, "exact")
    assert _decoded(out).size == (server._READ_IMAGE_MAX_EDGE, 800)
    assert "note" not in _text(out)


# --- the claim -------------------------------------------------------------

def test_reading_is_not_gated_by_another_session_s_scene_claim(env):
    """A pure read: looking at a video's images must never be blocked by, nor
    take, the scene-work claim that guards spend and writes."""
    _write_image(env, "castle.png")
    server._try_claim_scene_work(VID, "some-other-session")

    out = server.read_image(VID, "castle")
    assert isinstance(out, list)
    assert _text(out)["filename"] == "castle.png"
    # ...and the other session still holds it afterwards.
    assert server._scene_claim_state(VID)["claimed_by"] == "some-other-session"


def test_reading_does_not_take_a_claim_of_its_own(env):
    _write_image(env, "castle.png")
    server.read_image(VID, "castle")
    assert server._scene_claim_state(VID)["claimed_by"] is None
