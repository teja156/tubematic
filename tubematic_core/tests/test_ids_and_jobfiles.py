"""tubematic_core.ids and .jobfiles (TMDEV-158/159/162): ids that become paths.

Every refusal sits next to a working control. An id check that is too strict
breaks every real id shape (vid_<hex12>, uuid4, proj_<hex8>, `manual`, a
dashboard slug); one too loose is a path traversal. Both failures are silent
until they hit, so both directions are pinned here.
"""
import os
import pathlib
import shutil
import sys
import uuid

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import ids, jobfiles  # noqa: E402

GOOD_IDS = ["vid_0123456789ab", str(uuid.uuid4()), "proj_0123abcd", "manual",
            "proj_vqa", "rust-internals", "a"]
BAD_IDS = ["../x", "/tmp/x", "", ".", "..", "a/b", "a\\b", "-x", "a.b", "abc\n",
           "a\0b", "x" * 129, 7, None, ["a"]]


@pytest.mark.parametrize("value", GOOD_IDS)
def test_real_id_shapes_are_accepted(value):
    assert ids.check_segment(value)
    assert ids.is_component(value)


@pytest.mark.parametrize("value", BAD_IDS)
def test_unsafe_or_malformed_ids_are_refused(value):
    assert not ids.check_segment(value)


def test_the_length_cap_is_inclusive():
    assert ids.check_segment("x" * ids.MAX_SEGMENT_LEN)


# Filed before the creation rule, which is also when the 128-character cap
# arrived, so a long id is as legacy as a dotted one.
LEGACY_IDS = ["node.js-internals", "a.b", "Spaced Name", "x" * 129, "legacy-" + "y" * 200]


@pytest.mark.parametrize("value", LEGACY_IDS)
def test_a_legacy_odd_id_is_still_a_usable_component(value):
    assert ids.is_component(value)
    assert not ids.check_segment(value)


@pytest.mark.parametrize("value", ["", ".", "..", "../x", "/tmp/x", "a/b", "a\\b", "a\0b", "abc\n", "a\tb",
                                   "a\x7fb", "x" * 256, "\u00e9" * 128, "a\ud800b", 3, None])
def test_a_component_never_changes_the_directory(value):
    assert not ids.is_component(value)


def test_inside_follows_symlinks_out(tmp_path):
    base, elsewhere = tmp_path / "base", tmp_path / "elsewhere"
    base.mkdir()
    elsewhere.mkdir()
    (base / "link").symlink_to(elsewhere)
    assert ids.inside(base, base / "x")
    assert not ids.inside(base, base / ".." / "elsewhere")
    assert not ids.inside(base, base / "link" / "f")


def test_job_file_derives_the_fixed_layout(tmp_path):
    assert jobfiles.job_file(tmp_path, "vid_0123456789ab", jobfiles.AUDIO) == \
        tmp_path / "vid_0123456789ab" / "audio.mp3"
    assert jobfiles.images_dir(tmp_path, "vid_0123456789ab") == \
        tmp_path / "vid_0123456789ab" / "images"


@pytest.mark.parametrize("vid", ["../x", "/tmp/x", 5, None, "x" * 256, "", ".", "..",
                                 "a/b", "a\\b", "a\0b"])
def test_job_file_refuses_a_bad_video_id(tmp_path, vid):
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.job_file(tmp_path, vid, jobfiles.TIMELINE)
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.images_dir(tmp_path, vid)
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.output_file(tmp_path, "proj", vid)


def test_the_creation_cap_is_not_a_use_cap():
    """128 characters is the rule for a NEW id only. Rows filed before it were
    never capped, and refusing one at use moved it to FAILED."""
    assert not ids.check_segment("x" * (ids.MAX_SEGMENT_LEN + 1))
    assert ids.is_component("x" * (ids.MAX_SEGMENT_LEN + 1))


def test_the_component_bound_is_the_filesystem_name_limit_in_bytes():
    assert ids.is_component("x" * ids.MAX_COMPONENT_BYTES)
    assert not ids.is_component("x" * (ids.MAX_COMPONENT_BYTES + 1))
    # Bytes, not characters: 127 two-byte characters fit, 128 do not.
    assert ids.is_component("\u00e9" * 127)
    assert not ids.is_component("\u00e9" * 128)


@pytest.mark.parametrize("vid", LEGACY_IDS)
def test_a_legacy_video_id_still_derives_its_paths(tmp_path, vid):
    """An id that predates the creation rule is checked as a component at use
    (ids.py's contract), so an upgraded row keeps working."""
    assert jobfiles.job_file(tmp_path, vid, jobfiles.AUDIO) == tmp_path / vid / "audio.mp3"
    assert jobfiles.images_dir(tmp_path, vid) == tmp_path / vid / "images"
    assert jobfiles.output_file(tmp_path, "proj", vid) == tmp_path / "proj" / f"{vid}.mp4"


@pytest.mark.parametrize("project", LEGACY_IDS)
def test_a_legacy_project_id_still_derives_its_output_dir(tmp_path, project):
    assert jobfiles.output_file(tmp_path, project, "vid_1") == tmp_path / project / "vid_1.mp4"


def test_job_file_refuses_a_name_that_is_not_a_job_file(tmp_path):
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.job_file(tmp_path, "vid_1", "../../etc/passwd")


def test_a_symlinked_job_file_is_refused(tmp_path):
    secret = tmp_path / "secret.json"
    secret.write_text("{}")
    job = tmp_path / "jobs" / "vid_1"
    job.mkdir(parents=True)
    (job / "timeline.json").symlink_to(secret)
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.job_file(tmp_path / "jobs", "vid_1", jobfiles.TIMELINE)


def test_a_symlinked_job_dir_is_refused(tmp_path):
    (tmp_path / "jobs").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "jobs" / "vid_1").symlink_to(tmp_path / "other")
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.job_file(tmp_path / "jobs", "vid_1", jobfiles.AUDIO)


def test_a_symlinked_images_dir_is_refused(tmp_path):
    job = tmp_path / "vid_1"
    job.mkdir()
    (tmp_path / "x").mkdir()
    (job / "images").symlink_to(tmp_path / "x")
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.images_dir(tmp_path, "vid_1")


def test_a_job_dir_symlinked_to_another_video_inside_the_root_is_refused(tmp_path):
    """vid_a -> vid_b stays inside the jobs root, so containment alone passes
    it, and A would read B's audio. Every component below the root is checked."""
    jobs = tmp_path / "jobs"
    (jobs / "vid_b" / "images").mkdir(parents=True)
    (jobs / "vid_b" / "audio.mp3").write_bytes(b"b")
    (jobs / "vid_a").symlink_to(jobs / "vid_b")
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.job_file(jobs, "vid_a", jobfiles.AUDIO)
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.images_dir(jobs, "vid_a")
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.job_dir(jobs, "vid_a")
    # The control: the real directory is fine.
    assert jobfiles.job_file(jobs, "vid_b", jobfiles.AUDIO) == jobs / "vid_b" / "audio.mp3"


def test_a_project_dir_symlinked_to_another_project_inside_the_root_is_refused(tmp_path):
    out = tmp_path / "out"
    (out / "proj_b").mkdir(parents=True)
    (out / "proj_a").symlink_to(out / "proj_b")
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.output_file(out, "proj_a", "vid_1")
    assert jobfiles.output_file(out, "proj_b", "vid_1") == out / "proj_b" / "vid_1.mp4"


def test_a_symlinked_root_is_allowed(tmp_path):
    """Dev and test setups point the data root through a symlink. Only what
    lies below the root is walked."""
    real = tmp_path / "real"
    (real / "vid_1" / "images").mkdir(parents=True)
    (real / "vid_1" / "audio.mp3").write_bytes(b"a")
    (real / "proj").mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert jobfiles.job_file(link, "vid_1", jobfiles.AUDIO) == link / "vid_1" / "audio.mp3"
    assert jobfiles.images_dir(link, "vid_1") == link / "vid_1" / "images"
    assert jobfiles.output_file(link, "proj", "vid_1") == link / "proj" / "vid_1.mp4"


def test_an_ordinary_existing_tree_and_a_missing_one_both_derive(tmp_path):
    """Writers ask for paths that do not exist yet (generate_voice, a first
    render), so a missing component is not a refusal."""
    jobs = tmp_path / "jobs"
    (jobs / "vid_1" / "images").mkdir(parents=True)
    (jobs / "vid_1" / "timeline.json").write_text("{}")
    assert jobfiles.job_file(jobs, "vid_1", jobfiles.TIMELINE).is_file()
    assert jobfiles.images_dir(jobs, "vid_1").is_dir()
    assert not jobfiles.job_file(jobs, "vid_new", jobfiles.AUDIO).exists()
    assert jobfiles.output_file(tmp_path / "nothing-yet", "proj", "vid_1") == \
        tmp_path / "nothing-yet" / "proj" / "vid_1.mp4"


def test_output_file_derives_from_the_ids_alone(tmp_path):
    assert jobfiles.output_file(tmp_path, "proj_0123abcd", "vid_1") == \
        tmp_path / "proj_0123abcd" / "vid_1.mp4"
    assert jobfiles.output_file(tmp_path, "", "vid_1") == tmp_path / "default_proj" / "vid_1.mp4"


def test_output_file_keeps_a_legacy_project_id_with_a_dot(tmp_path):
    assert jobfiles.output_file(tmp_path, "node.js-internals", "vid_1") == \
        tmp_path / "node.js-internals" / "vid_1.mp4"


@pytest.mark.parametrize("proj", ["..", "../x", "/tmp", "a/b", "."])
def test_output_file_refuses_an_escaping_project_id(tmp_path, proj):
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.output_file(tmp_path, proj, "vid_1")


def test_output_file_refuses_a_symlinked_project_dir(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "out" / "proj").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.output_file(tmp_path / "out", "proj", "vid_1")


def test_ignore_symlinks_drops_links_from_a_copytree(tmp_path):
    src = tmp_path / "images"
    src.mkdir()
    (src / "real.png").write_bytes(b"png")
    secret = tmp_path / "secret"
    secret.write_text("s")
    (src / "leak.png").symlink_to(secret)
    shutil.copytree(src, tmp_path / "dst", ignore=jobfiles.ignore_symlinks)
    assert sorted(os.listdir(tmp_path / "dst")) == ["real.png"]


def test_scene_file_derives_the_namespaced_and_the_legacy_flat_form(tmp_path):
    assert jobfiles.scene_file(tmp_path, "vid_1", "intro") == tmp_path / "vid_1" / "intro.tsx"
    assert jobfiles.scene_file(tmp_path, "a.b", "intro") == tmp_path / "a.b" / "intro.tsx"
    assert jobfiles.scene_file(tmp_path, "", "intro") == tmp_path / "intro.tsx"


def test_scene_file_refuses_a_linked_video_dir_and_a_bad_name(tmp_path):
    (tmp_path / "vid_b").mkdir()
    (tmp_path / "vid_a").symlink_to(tmp_path / "vid_b")
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.scene_file(tmp_path, "vid_a", "intro")
    for vid, name in [("..", "intro"), ("vid_1", "../x"), ("vid_1", ""), ("/tmp", "x")]:
        with pytest.raises(jobfiles.UnsafePath):
            jobfiles.scene_file(tmp_path, vid, name)


def test_image_file_derives_and_refuses(tmp_path):
    assert jobfiles.image_file(tmp_path, "vid_1", "x.png") == tmp_path / "vid_1" / "images" / "x.png"
    for name in ["../x.png", "", "..", "a/b.png"]:
        with pytest.raises(jobfiles.UnsafePath):
            jobfiles.image_file(tmp_path, "vid_1", name)
    (tmp_path / "vid_1" / "images").mkdir(parents=True)
    (tmp_path / "vid_1" / "images" / "x.png").symlink_to(tmp_path / "elsewhere.png")
    with pytest.raises(jobfiles.UnsafePath, match="symlink"):
        jobfiles.image_file(tmp_path, "vid_1", "x.png")


# A name that gets a suffix appended must leave room for it: 251 + ".mp4" is
# the longest leaf a filesystem can hold, 252 + ".mp4" fails with ENAMETOOLONG
# on the real write. Both controls create the file for real, so the boundary
# is the filesystem's, not this module's arithmetic.
FITS = "x" * (ids.MAX_COMPONENT_BYTES - 4)
TOO_LONG = "x" * (ids.MAX_COMPONENT_BYTES - 3)


def test_an_output_file_whose_name_fits_is_written(tmp_path):
    path = jobfiles.output_file(tmp_path, "proj", FITS)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mp4")
    assert path.read_bytes() == b"mp4"


def test_an_output_file_too_long_with_its_suffix_is_refused_cleanly(tmp_path):
    # A 252-byte id is a usable directory component (its job dir works)...
    assert jobfiles.job_dir(tmp_path, TOO_LONG) == tmp_path / TOO_LONG
    # ...but not once ".mp4" is added. Refused before anything is created.
    with pytest.raises(jobfiles.UnsafePath, match="bytes"):
        jobfiles.output_file(tmp_path, "proj", TOO_LONG)
    assert list(tmp_path.iterdir()) == []
    # The real write it stands in for fails, so the refusal costs nothing.
    (tmp_path / "proj").mkdir()
    with pytest.raises(OSError):
        (tmp_path / "proj" / f"{TOO_LONG}.mp4").write_bytes(b"")


def test_a_scene_file_whose_name_fits_is_written(tmp_path):
    for vid in ("vid_1", ""):
        path = jobfiles.scene_file(tmp_path, vid, FITS)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
        assert path.read_text() == "x"


def test_a_scene_file_too_long_with_its_suffix_is_refused_cleanly(tmp_path):
    for vid in ("vid_1", ""):
        with pytest.raises(jobfiles.UnsafePath, match="bytes"):
            jobfiles.scene_file(tmp_path, vid, TOO_LONG)
    assert list(tmp_path.iterdir()) == []


def test_an_image_file_too_long_with_its_suffix_is_refused(tmp_path):
    # Already right before join_below learned the bound: the file name is
    # checked whole, extension included.
    assert jobfiles.image_file(tmp_path, "vid_1", FITS + ".png").name == FITS + ".png"
    with pytest.raises(jobfiles.UnsafePath):
        jobfiles.image_file(tmp_path, "vid_1", TOO_LONG + ".png")
