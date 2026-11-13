"""treat_image and the looks it bakes (TMDEV-229/230/231)."""
import datetime
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import treatments  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

VID = "vid_treat0001"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _object_on_plain_ground(size=(272, 480)) -> Image.Image:
    im = Image.new("RGB", size, (236, 234, 228))
    d = ImageDraw.Draw(im)
    w, h = size
    d.ellipse((w * 0.25, h * 0.3, w * 0.75, h * 0.65), fill=(150, 70, 40))
    d.rectangle((w * 0.4, h * 0.4, w * 0.6, h * 0.5), fill=(20, 20, 20))
    return im


# ── the looks ───────────────────────────────────────────────────────────────

def test_the_pack_schema_and_the_module_name_the_same_treatments():
    assert tvs.TREATMENTS == treatments.TREATMENTS


@pytest.mark.parametrize("name", ["print", "engraving", "pencil"])
def test_a_flat_treatment_keeps_the_frame_size_so_its_focus_points_stay_true(name):
    im = _object_on_plain_ground()
    out = treatments.apply(im, name)
    assert out.size == im.size and out.mode == "RGB"


def test_a_print_is_grey_dots_on_paper_with_a_border():
    out = treatments.apply(_object_on_plain_ground(), "print")
    assert out.getpixel((1, 1)) == treatments.PRINT_PAPER           # the border
    r, g, b = out.convert("RGB").getpixel((136, 228))                # inside the dark object
    assert max(r, g, b) - min(r, g, b) < 12                          # grey, not the object's colour
    colours = {c for _, c in out.getcolors(1 << 20)}
    assert len(colours) > 2                                          # a dot screen, not a flat fill


def test_a_sticker_cuts_the_subject_out_with_a_white_edge():
    out = treatments.apply(_object_on_plain_ground(), "sticker")
    assert out.mode == "RGBA"
    w, h = out.size
    assert w < 272 and h < 480                                       # cropped to the subject
    assert out.getpixel((0, 0))[3] == 0                              # transparent ground
    assert out.getpixel((w // 2, h // 2))[3] == 255                 # solid subject


def test_a_sticker_keeps_a_still_that_is_already_transparent():
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((60, 60, 140, 140), fill=(200, 30, 30, 255))
    out = treatments.apply(im, "sticker")
    assert out.getpixel((out.width // 2, out.height // 2))[:3] == (200, 30, 30)


def test_a_picture_with_nothing_on_its_ground_is_refused():
    with pytest.raises(ValueError, match="no subject"):
        treatments.apply(Image.new("RGB", (100, 100), (240, 240, 240)), "sticker")


def test_an_engraving_runs_from_ink_to_laid_paper():
    out = treatments.apply(_object_on_plain_ground(), "engraving")
    assert out.getpixel((1, 1)) == treatments.ENGRAVE_PAPER
    assert sum(out.getpixel((136, 228))) < sum(treatments.ENGRAVE_PAPER) // 3


def test_an_unknown_treatment_is_refused():
    with pytest.raises(ValueError, match="unknown treatment"):
        treatments.apply(_object_on_plain_ground(), "sepia")


# ── the tool ────────────────────────────────────────────────────────────────

@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    # A shipped pack that takes treatments, for the tool's sake.
    pics = {**tvs.PACKS["case_file_story"]["pictures"], "treatments": ["print", "sticker"]}
    monkeypatch.setitem(tvs.PACKS, "case_file_story", {**tvs.PACKS["case_file_story"], "pictures": pics})

    def make(style="case_file_story", stills=("desk",)):
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                        "VALUES (?, NULL, 't', 'VOICE_READY', ?, ?, ?)", (VID, style, _now(), _now()))
        images = tmp_path / "jobs" / VID / "images"
        images.mkdir(parents=True)
        for name in stills:
            _object_on_plain_ground().save(images / f"{name}.png")
        return VID

    return make


def test_a_still_is_treated_into_its_own_folder_and_left_as_it_was(make_video, tmp_path):
    vid = make_video()
    before = (tmp_path / "jobs" / vid / "images" / "desk.png").read_bytes()
    out = server.treat_image(vid, "desk", "print")
    assert "error" not in out, out
    assert out["public_path"] == f"/public/{vid}/images/treated/desk.print.png"
    assert (tmp_path / "jobs" / vid / "images" / "treated" / "desk.print.png").is_file()
    assert (tmp_path / "jobs" / vid / "images" / "desk.png").read_bytes() == before
    assert (out["width"], out["height"]) == (272, 480)


def test_a_treated_copy_never_counts_against_the_cap(make_video, tmp_path):
    vid = make_video(stills=[f"s{k}" for k in range(16)])
    for k in range(16):
        assert "error" not in server.treat_image(vid, f"s{k}", "print")
    images = tmp_path / "jobs" / vid / "images"
    assert server._image_cap_error(vid, "lead", images) == ""          # the sheet's own slot
    assert "already has 16 stills" in server._image_cap_error(vid, "one-more", images)
    assert server._image_cap_error(vid, "s3", images) == ""            # a regeneration


@pytest.mark.parametrize("name, treatment, fragment", [
    ("desk", "engraving", "not one this style uses"),
    ("desk", "sepia", "not one this style uses"),
    ("missing", "print", "is not a still of this video yet"),
    ("../desk", "print", "image_name"),
])
def test_a_wrong_call_is_refused(make_video, name, treatment, fragment):
    vid = make_video()
    assert fragment in server.treat_image(vid, name, treatment)["error"]


def test_a_style_with_no_treatments_takes_none(make_video):
    vid = make_video(style="under_the_hood")
    assert "takes no treatments" in server.treat_image(vid, "desk", "print")["error"]
