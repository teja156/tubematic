"""tubematic_core.disk_usage (TMDEV-192): the disk-usage figures and the one
rule for "old image".

`old_images` decides what upgrade.py deletes, so its refusals matter more than
its finds: an image a Tubematic container uses, an unrelated image, and
anything at all when no Tubematic container exists must never be named. Each
refusal sits next to a control that is named.
"""
import json
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import disk_usage  # noqa: E402

CUR_BACKEND = "sha256:" + "a" * 64
CUR_DASH = "sha256:" + "b" * 64
OLD_BACKEND = "sha256:" + "c" * 64
OLD_DASH = "sha256:" + "d" * 64
DANGLING = "sha256:" + "e" * 64
KASM = "sha256:" + "f" * 64
FORK = "sha256:" + "1" * 64
RETAGGED = "sha256:" + "2" * 64


def _img(image_id, repo, tag):
    return json.dumps({"ID": image_id, "Repository": repo, "Tag": tag})


class FakeDocker:
    """Answers the read-only docker commands disk_usage runs. `containers`
    is a list of (image id, writable-layer bytes)."""

    def __init__(self, *, containers, images, dangling=(), sizes=None,
                 build_cache="1.5GB", fail=(), short_df_ids=False, images_total="40GB"):
        self.containers = containers
        self.images = images
        self.dangling = list(dangling)
        self.sizes = sizes or {}
        self.build_cache = build_cache
        self.fail = set(fail)
        self.short_df_ids = short_df_ids
        self.images_total = images_total
        self.calls = []

    def __call__(self, argv):
        assert argv[0] == "docker"
        args = argv[1:]
        self.calls.append(args)
        key = " ".join(args[:2])
        if key in self.fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")
        if args[:2] == ["ps", "-a"]:
            assert disk_usage._PROJECT_LABEL in args
            out = "\n".join(f"ctr{i}" for i in range(len(self.containers)))
        elif args[:2] == ["container", "inspect"]:
            assert "--size" in args
            out = json.dumps([{"Image": img, "SizeRw": rw} for img, rw in self.containers])
        elif args[:2] == ["image", "ls"] and "-q" in args:
            assert "dangling=true" in args and disk_usage._PROJECT_LABEL in args
            out = "\n".join(self.dangling)
        elif args[:2] == ["image", "ls"]:
            out = "\n".join(self.images)
        elif args[:3] == ["system", "df", "-v"]:
            out = json.dumps({"Images": [
                {"ID": i.split(":")[1][:12] if self.short_df_ids else i,
                 "Size": s, "UniqueSize": u, "SharedSize": "0B"}
                for i, (s, u) in self.sizes.items()], "BuildCache": []})
        elif args[:2] == ["system", "df"]:
            out = "\n".join([json.dumps({"Type": "Images", "Size": self.images_total}),
                             json.dumps({"Type": "Build Cache", "Size": self.build_cache})])
        else:
            raise AssertionError(f"unexpected docker call: {args}")
        return SimpleNamespace(returncode=0, stdout=out + "\n", stderr="")


def _release_install(**kw):
    return FakeDocker(
        containers=[(CUR_BACKEND, 1000), (CUR_BACKEND, 2000), (CUR_DASH, 500)],
        images=[
            _img(CUR_BACKEND, "ghcr.io/teja156/tubematic-backend", "2.1.0"),
            _img(CUR_DASH, "ghcr.io/teja156/tubematic-dashboard", "2.1.0"),
            _img(OLD_BACKEND, "ghcr.io/teja156/tubematic-backend", "2.0.0"),
            _img(OLD_DASH, "ghcr.io/teja156/tubematic-dashboard", "<none>"),
            _img(KASM, "ghcr.io/teja156/tubematic-kasm-workspace", "1.19.0"),
            _img(FORK, "ghcr.io/someone/tubematic-backend", "2.0.0"),
            _img("sha256:" + "9" * 64, "postgres", "16"),
        ],
        sizes={CUR_BACKEND: ("5GB", "1GB"), CUR_DASH: ("300MB", "300MB"),
               OLD_BACKEND: ("5GB", "1.2GB"), OLD_DASH: ("290MB", "290MB"),
               FORK: ("5GB", "4.5MB"), KASM: ("15.2GB", "15.2GB")},
        **kw)


# --- parse_size --------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("0B", 0), ("512B", 512), ("12kB", 12_000), ("1.38GB", 1_380_000_000),
    ("6.1GB", 6_100_000_000), ("10.57GB", 10_570_000_000), ("2TB", 2 * 10**12),
    (" 3MB ", 3_000_000)])
def test_docker_sizes_are_decimal_units(text, expected):
    assert disk_usage.parse_size(text) == expected


@pytest.mark.parametrize("text", ["N/A", "", None, "lots", "-1GB"])
def test_anything_not_a_size_is_none_never_zero(text):
    assert disk_usage.parse_size(text) is None


@pytest.mark.parametrize("n,text", [(0, "0 B"), (512, "512 B"), (1536, "1.5 KB"),
                                    (3 * 1024**3, "3.0 GB"), (2 * 1024**4, "2.0 TB")])
def test_human_uses_binary_units_like_du(n, text):
    assert disk_usage.human(n) == text


# --- old_images --------------------------------------------------------------

def test_previous_release_tags_are_old_and_the_running_ones_are_not():
    old = disk_usage.old_images(run=_release_install())
    ids = {e["id"] for e in old}
    assert OLD_BACKEND in ids and OLD_DASH in ids
    assert CUR_BACKEND not in ids and CUR_DASH not in ids


def test_a_tagged_old_image_is_removed_by_its_ref_and_an_untagged_one_by_id():
    old = {e["id"]: e for e in disk_usage.old_images(run=_release_install())}
    assert old[OLD_BACKEND]["refs"] == ["ghcr.io/teja156/tubematic-backend:2.0.0"]
    # A re-pushed tag leaves the repository with a <none> tag: no ref to use.
    assert old[OLD_DASH]["refs"] == []


def test_each_old_image_carries_what_removing_it_frees():
    old = {e["id"]: e["bytes"] for e in disk_usage.old_images(run=_release_install())}
    assert old[OLD_BACKEND] == 1_200_000_000  # unique, not the 5GB it shares
    assert old[OLD_DASH] == 290_000_000


def test_a_forks_release_images_count_as_tubematics():
    ids = {e["id"] for e in disk_usage.old_images(run=_release_install())}
    assert FORK in ids


def test_images_outside_tubematics_repositories_are_never_old():
    ids = {e["id"] for e in disk_usage.old_images(run=_release_install())}
    assert KASM not in ids  # ghcr.io/<owner>/tubematic-kasm-workspace
    assert "sha256:" + "9" * 64 not in ids


def test_an_image_a_stopped_or_running_container_uses_is_never_old():
    # A remote renderer started on this same host from the old backend tag is
    # a tubematic-project container too.
    docker = _release_install()
    docker.containers.append((OLD_BACKEND, 0))
    ids = {e["id"] for e in disk_usage.old_images(run=docker)}
    assert OLD_BACKEND not in ids
    assert OLD_DASH in ids


def test_no_tubematic_containers_means_nothing_is_old():
    docker = _release_install()
    docker.containers = []
    assert disk_usage.old_images(run=docker) == []


def test_docker_unreadable_means_nothing_is_old():
    assert disk_usage.old_images(run=_release_install(fail={"ps -a"})) == []
    assert disk_usage.old_images(run=_release_install(fail={"container inspect"})) == []
    assert disk_usage.old_images(run=_release_install(fail={"image ls"})) == []


def test_docker_missing_means_nothing_is_old():
    def run(argv):
        raise FileNotFoundError("docker")
    assert disk_usage.old_images(run=run) == []
    def slow(argv):
        raise subprocess.TimeoutExpired(argv, 60)
    assert disk_usage.old_images(run=slow) == []


def test_source_install_dangling_builds_of_this_project_are_old():
    docker = FakeDocker(
        containers=[(CUR_BACKEND, 0), (CUR_DASH, 0)],
        images=[_img(CUR_BACKEND, "tubematic-renderer-image", "latest"),
                _img(CUR_DASH, "tubematic-tubematic-dashboard", "latest"),
                _img(DANGLING, "<none>", "<none>"),
                _img(RETAGGED, "<none>", "<none>")],
        dangling=[DANGLING, CUR_DASH])  # a filter answer can't override in-use
    old = disk_usage.old_images(run=docker)
    assert old == [{"id": DANGLING, "refs": [], "bytes": 0}]


def test_an_untagged_image_not_built_for_this_project_is_left_alone():
    # RETAGGED is <none>:<none> but Docker's label filter did not return it
    # (another project's leftover, the e2e stack's, anything else).
    docker = FakeDocker(containers=[(CUR_BACKEND, 0)],
                        images=[_img(RETAGGED, "<none>", "<none>")], dangling=[])
    assert disk_usage.old_images(run=docker) == []


# --- measure_host ------------------------------------------------------------

def test_measure_host_sums_what_removal_would_free(tmp_path):
    (tmp_path / "f").write_bytes(b"x" * 10_000)
    snap = disk_usage.measure_host(tmp_path, run=_release_install())
    assert snap["images"] == {
        # the two distinct images in use, counted once each
        "current_bytes": 5_000_000_000 + 300_000_000,
        # unique sizes only: shared layers stay when an image goes
        "old_bytes": 1_200_000_000 + 290_000_000 + 4_500_000,
        "old_count": 3,
    }
    assert snap["containers_bytes"] == 3500
    assert snap["build_cache_bytes"] == 1_500_000_000
    assert snap["install_bytes"] >= 10_000


def test_sizes_join_when_docker_truncates_ids_in_system_df(tmp_path):
    # Some Docker versions print `system df -v` ids as 12 hex digits, while
    # `image ls --no-trunc` and `container inspect` give sha256:<64>.
    full = disk_usage.measure_host(tmp_path, run=_release_install())["images"]
    short = disk_usage.measure_host(tmp_path, run=_release_install(short_df_ids=True))["images"]
    assert short == full
    assert short["current_bytes"] > 0 and short["old_bytes"] > 0
    old = {e["id"]: e["bytes"] for e in disk_usage.old_images(run=_release_install(short_df_ids=True))}
    assert old[OLD_BACKEND] == 1_200_000_000


def test_an_in_use_image_named_by_a_short_id_is_still_in_use():
    docker = _release_install()
    docker.containers.append((OLD_BACKEND.split(":")[1][:12], 0))
    assert OLD_BACKEND not in {e["id"] for e in disk_usage.old_images(run=docker)}


def test_images_total_counts_each_layer_once_machine_wide():
    assert disk_usage.images_total_bytes(run=_release_install(images_total="112.9GB")) \
        == 112_900_000_000
    assert disk_usage.images_total_bytes(run=_release_install(fail={"system df"})) is None


@pytest.mark.parametrize("answer", ["", "not json", "[]", '{"Images": "x"}'])
def test_unreadable_image_sizes_are_unknown_not_zero(tmp_path, answer):
    docker = _release_install()
    real = docker.__call__
    def run(argv):
        if argv[1:4] == ["system", "df", "-v"]:
            return SimpleNamespace(returncode=0, stdout=answer, stderr="")
        return real(argv)
    snap = disk_usage.measure_host(tmp_path, run=run)
    assert snap["images"] is None
    assert snap["containers_bytes"] == 3500  # what could be read still is
    # the rule itself does not depend on sizes
    assert {e["id"] for e in disk_usage.old_images(run=run)} >= {OLD_BACKEND, OLD_DASH}


def test_a_failed_system_df_is_unknown_not_zero(tmp_path):
    docker = _release_install(fail={"system df"})
    assert disk_usage.measure_host(tmp_path, run=docker)["images"] is None


def test_measure_host_without_docker_reports_unknown_not_zero(tmp_path):
    snap = disk_usage.measure_host(tmp_path, run=_release_install(fail={"ps -a"}))
    assert snap["images"] is None
    assert snap["containers_bytes"] is None
    assert snap["build_cache_bytes"] is None
    assert isinstance(snap["install_bytes"], int)


# --- tree_bytes --------------------------------------------------------------

def test_tree_bytes_counts_a_hardlinked_file_once(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 100_000)
    base = disk_usage.tree_bytes(tmp_path)
    os.link(tmp_path / "a", tmp_path / "b")
    assert disk_usage.tree_bytes(tmp_path) == base


def test_tree_bytes_never_follows_a_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "big").write_bytes(b"x" * 500_000)
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "link").symlink_to(outside)
    (inside / "filelink").symlink_to(outside / "big")
    assert disk_usage.tree_bytes(inside) < 100_000


def test_tree_bytes_excludes_named_paths(tmp_path):
    (tmp_path / "keep").write_bytes(b"x" * 50_000)
    sub = tmp_path / "skip"
    sub.mkdir()
    (sub / "big").write_bytes(b"x" * 500_000)
    with_all = disk_usage.tree_bytes(tmp_path)
    without = disk_usage.tree_bytes(tmp_path, exclude=[sub])
    assert with_all - without >= 500_000


def test_tree_bytes_of_a_missing_path_is_zero(tmp_path):
    assert disk_usage.tree_bytes(tmp_path / "nope") == 0


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_tree_bytes_skips_what_it_cannot_read(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "f").write_bytes(b"x" * 10_000)
    locked.chmod(0)
    try:
        assert disk_usage.tree_bytes(tmp_path) >= 0
    finally:
        locked.chmod(0o700)


# --- snapshot ----------------------------------------------------------------

def test_snapshot_round_trips_with_a_utc_timestamp(tmp_path):
    path = tmp_path / "disk-usage.json"
    disk_usage.write_snapshot(path, {"install_bytes": 5})
    snap = disk_usage.read_snapshot(path)
    assert snap["install_bytes"] == 5
    assert snap["measured_at"].endswith("Z")
    assert [p.name for p in tmp_path.iterdir()] == ["disk-usage.json"]  # no tmp left


@pytest.mark.parametrize("body", ["", "{", "[]", '{"install_bytes": 1}', "null"])
def test_a_garbled_snapshot_reads_as_none(tmp_path, body):
    path = tmp_path / "disk-usage.json"
    path.write_text(body)
    assert disk_usage.read_snapshot(path) is None


def test_a_missing_snapshot_reads_as_none(tmp_path):
    assert disk_usage.read_snapshot(tmp_path / "nope.json") is None


def test_snapshot_path_is_in_the_data_folder_the_api_mounts(tmp_path):
    assert disk_usage.snapshot_path(tmp_path) == tmp_path / "data" / "disk-usage.json"


def test_refresh_respects_max_age_and_writes_when_stale(tmp_path):
    (tmp_path / "data").mkdir()
    docker = _release_install()
    assert disk_usage.refresh_snapshot(tmp_path, tmp_path, max_age=3600, run=docker) is True
    calls = len(docker.calls)
    assert disk_usage.refresh_snapshot(tmp_path, tmp_path, max_age=3600, run=docker) is False
    assert len(docker.calls) == calls  # a fresh snapshot costs no docker call
    path = disk_usage.snapshot_path(tmp_path)
    old = path.stat().st_mtime - 7200
    os.utime(path, (old, old))
    assert disk_usage.refresh_snapshot(tmp_path, tmp_path, max_age=3600, run=docker) is True
    assert disk_usage.refresh_snapshot(tmp_path, tmp_path, run=docker) is True


def test_refresh_into_an_unwritable_folder_raises_oserror(tmp_path):
    # No data/ folder: the write fails, and the caller decides how to report it.
    with pytest.raises(OSError):
        disk_usage.refresh_snapshot(tmp_path, tmp_path, run=_release_install())
