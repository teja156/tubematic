"""External style packages (TMDEV-252): the loader that reads installed packages.

A package comes from outside the release, so every rule here turns a bad
package into "unavailable, with a reason" and never into an exception: one
broken package must not stop the API, the MCP server or the worker at start-up,
the way a broken built-in pack does on purpose.
"""
import hashlib
import json
import os
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import external_styles as ext  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402


def base_pack(sid, renderer="dom", gpu=False):
    p = json.loads((tvs.PACKS_DIR / "night_signal.json").read_text())
    p.pop("extra", None)
    p.update({
        "id": sid, "label": f"Test {sid}", "order": 9000,
        "inserts": {"host": False},
        "authoring_skill": ext.AUTHORING_SKILL,
        "renderer": renderer, "dimension": "3d" if renderer == "cartoon_3d" else "2d",
        "preview": sid, "mascot": False,
        "needs": {"openai_key": False, "gpu": gpu},
        "external": {"version": "1.0.0", "author": "someone", "source": "https://example.invalid/x",
                     "licence": "MIT", "scene_api": ext.SCENE_API, "props_key": "testStyle"},
    })
    p["messages"] = dict(p.get("messages", {}), inserts="This style hosts no inserts.")
    if gpu:
        p["messages"].update(gpu="needs a GPU", gpu_unknown="GPU not tested")
    return p


def write_manifest(d):
    files = {}
    for path in sorted(d.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.json":
            files[path.relative_to(d).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (d / "MANIFEST.json").write_text(json.dumps({"files": files}))


def make_package(root, sid="ext_test", renderer="dom", gpu=False, pack=None, manifest=True):
    d = root / sid
    (d / "guide").mkdir(parents=True)
    (d / "style.json").write_text(json.dumps(pack or base_pack(sid, renderer, gpu)))
    (d / "schema.json").write_text(json.dumps({"type": "object"}))
    (d / "guide" / "guide.md").write_text("# Guide\n")
    (d / "guide" / "example-config.json").write_text("{}")
    if renderer == "cartoon_3d":
        (d / "runner").mkdir()
        (d / "runner" / "Short.tsx").write_text("export default () => null;\n")
    else:
        (d / "components").mkdir()
        (d / "components" / "Main.tsx").write_text("export default () => null;\n")
    (d / "preview.mp4").write_bytes(b"\0" * 100)
    (d / "preview.webp").write_bytes(b"\0" * 100)
    if manifest:
        write_manifest(d)
    return d


def test_a_valid_dom_package_loads(tmp_path):
    make_package(tmp_path)
    got = ext.load(tmp_path)["ext_test"]
    assert got.ok, got.reason
    assert got.pack["id"] == "ext_test" and got.pack["external"]["props_key"] == "testStyle"


def test_a_valid_runner_package_with_a_gpu_loads(tmp_path):
    make_package(tmp_path, renderer="cartoon_3d", gpu=True)
    got = ext.load(tmp_path)["ext_test"]
    assert got.ok, got.reason
    assert got.pack["renderer"] == "cartoon_3d" and got.pack["needs"]["gpu"] is True


def test_a_missing_folder_is_no_packages(tmp_path):
    assert ext.load(tmp_path / "absent") == {}


def _edit_pack(tmp_path, change, sid="ext_test"):
    p = base_pack(sid)
    change(p)
    make_package(tmp_path, sid=sid, pack=p)
    return ext.load(tmp_path)[sid]


@pytest.mark.parametrize("change, words", [
    (lambda p: p["external"].update(scene_api=ext.SCENE_API + 1), "scene_api"),
    (lambda p: p.update(inserts={"host": True, "transition": "dip"}), "inserts"),
    (lambda p: p.update(mascot=True), "mascot"),
    (lambda p: p.update(role="insert"), "insert"),
    (lambda p: p.update(authoring_skill="tubematic-night-signal"), "authoring_skill"),
    (lambda p: p["external"].pop("author"), "author"),
    (lambda p: p["external"].update(props_key="not a key"), "props_key"),
    (lambda p: p.pop("label"), "label"),
])
def test_a_bad_pack_is_unavailable_with_a_reason(tmp_path, change, words):
    got = _edit_pack(tmp_path, change)
    assert not got.ok and words in got.reason


@pytest.mark.parametrize("sid", ["night_signal", "ext-bad", "Ext_upper", "ext_" + "x" * 41])
def test_an_id_outside_the_external_namespace_is_unavailable(tmp_path, sid):
    p = base_pack(sid)
    make_package(tmp_path, sid=sid, pack=p)
    got = ext.load(tmp_path)[sid]
    assert not got.ok and "id" in got.reason


def test_a_pack_id_differing_from_its_folder_is_unavailable(tmp_path):
    make_package(tmp_path, sid="ext_test", pack=base_pack("ext_other"))
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "ext_other" in got.reason


def test_invalid_json_is_unavailable(tmp_path):
    d = make_package(tmp_path, manifest=False)
    (d / "style.json").write_text("{nope")
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "JSON" in got.reason


def test_a_file_changed_after_the_manifest_is_unavailable(tmp_path):
    d = make_package(tmp_path)
    (d / "components" / "Main.tsx").write_text("export default () => 1;\n")
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "components/Main.tsx" in got.reason


def test_a_file_missing_from_the_manifest_is_unavailable(tmp_path):
    d = make_package(tmp_path)
    (d / "components" / "Extra.tsx").write_text("x")
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "components/Extra.tsx" in got.reason


def test_a_missing_manifest_is_unavailable(tmp_path):
    make_package(tmp_path, manifest=False)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "MANIFEST.json" in got.reason


def test_a_symlink_inside_a_package_is_unavailable(tmp_path):
    d = make_package(tmp_path)
    os.symlink("/etc/hostname", d / "components" / "Link.tsx")
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "symlink" in got.reason


def test_a_package_folder_that_is_a_symlink_is_unavailable(tmp_path):
    real = make_package(tmp_path / "elsewhere")
    (tmp_path / "root").mkdir()
    os.symlink(real, tmp_path / "root" / "ext_test")
    got = ext.load(tmp_path / "root")["ext_test"]
    assert not got.ok and "symlink" in got.reason


@pytest.mark.parametrize("missing", ["schema.json", "guide/guide.md", "guide/example-config.json",
                                     "components/Main.tsx", "preview.mp4", "preview.webp"])
def test_a_required_file_missing_is_unavailable(tmp_path, missing):
    d = make_package(tmp_path, manifest=False)
    (d / missing).unlink()
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and missing.split("/")[0] in got.reason


def test_a_runner_package_needs_runner_code(tmp_path):
    d = make_package(tmp_path, renderer="cartoon_3d", manifest=False)
    (d / "runner" / "Short.tsx").unlink()
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "runner" in got.reason


def test_a_schema_that_is_not_a_json_object_is_unavailable(tmp_path):
    d = make_package(tmp_path, manifest=False)
    (d / "schema.json").write_text("[]")
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "schema.json" in got.reason


@pytest.mark.parametrize("name, size", [("preview.mp4", ext.PREVIEW_CAPS["preview.mp4"] + 1),
                                        ("preview.webp", ext.PREVIEW_CAPS["preview.webp"] + 1)])
def test_an_oversize_preview_is_unavailable(tmp_path, name, size):
    d = make_package(tmp_path, manifest=False)
    (d / name).write_bytes(b"\0" * size)
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and name in got.reason


def test_fonts_need_a_licence_file(tmp_path):
    d = make_package(tmp_path, manifest=False)
    (d / "fonts").mkdir()
    (d / "fonts" / "a.woff2").write_bytes(b"\0")
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "licence" in got.reason
    (d / "fonts" / "OFL.txt").write_text("licence")
    write_manifest(d)
    assert ext.load(tmp_path)["ext_test"].ok


def test_dot_folders_and_loose_files_are_ignored(tmp_path):
    make_package(tmp_path)
    (tmp_path / ".gitkeep").write_text("")
    (tmp_path / ".staging").mkdir()
    assert list(ext.load(tmp_path)) == ["ext_test"]


def test_one_bad_package_leaves_the_others_available(tmp_path):
    make_package(tmp_path, sid="ext_good")
    make_package(tmp_path, sid="ext_bad", manifest=False)
    got = ext.load(tmp_path)
    assert got["ext_good"].ok and not got["ext_bad"].ok


def test_the_registry_sees_a_package_added_later(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path)
    assert ext.registry() == {}
    make_package(tmp_path)
    assert ext.registry()["ext_test"].ok


def test_the_registry_sees_a_package_replaced_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path)
    d = make_package(tmp_path)
    assert ext.registry()["ext_test"].ok
    (d / "components" / "Main.tsx").write_text("changed")
    st = (d / "MANIFEST.json").stat()
    os.utime(d / "MANIFEST.json", ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert not ext.registry()["ext_test"].ok


def test_the_fingerprint_changes_with_any_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path)
    d = make_package(tmp_path)
    before = ext.fingerprint("ext_test")
    (d / "guide" / "guide.md").write_text("# Changed\n")
    assert ext.fingerprint("ext_test") != before
