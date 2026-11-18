"""External style packages (TMDEV-252): the loader that reads installed packages.

A package comes from outside the release, so every rule here turns a bad
package into "unavailable, with a reason" and never into an exception: one
broken package must not stop the API, the MCP server or the worker at start-up,
the way a broken built-in pack does on purpose.
"""
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


write_manifest = ext.write_manifest


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


# ── How the style lookups see installed packages ─────────────────────────────

@pytest.fixture
def installed(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path)
    make_package(tmp_path, sid="ext_dom")
    make_package(tmp_path, sid="ext_world", renderer="cartoon_3d", gpu=True)
    make_package(tmp_path, sid="ext_broken", manifest=False)
    return tmp_path


def test_an_installed_style_has_a_pack_and_a_broken_one_has_none(installed):
    assert tvs.pack("ext_dom")["label"] == "Test ext_dom"
    assert tvs.pack("ext_broken") is None
    assert tvs.is_external("ext_dom") and tvs.is_external("ext_broken")
    assert not tvs.is_external("night_signal") and not tvs.is_external("auto")


@pytest.mark.parametrize("style, known, main, world", [
    ("ext_dom", True, True, False),
    ("ext_world", True, True, True),
    ("ext_broken", False, False, False),
    ("ext_absent", False, False, False),
    ("auto", True, True, False),
    ("night_signal", True, True, False),
    ("cartoon_3d", True, True, True),
    ("system_flow", True, False, False),
])
def test_style_membership_includes_installed_styles(installed, style, known, main, world):
    assert tvs.is_known_style(style) is known
    assert tvs.is_main_style(style) is main
    assert tvs.is_world_style(style) is world


def test_an_installed_style_fixes_its_canvas(installed):
    assert tvs.fixed_canvas("ext_dom") == "dark"
    assert tvs.effective_canvas("ext_dom", "") == "dark"
    assert tvs.fixed_canvas("auto") is None


def test_an_installed_style_hosts_no_inserts(installed):
    assert tvs.hosts_inserts("ext_dom") == {"host": False}


def test_the_public_list_marks_installed_styles(installed):
    rows = {r["id"]: r for r in tvs.public_list(openai_key_set=False, gpu_status="not_usable")}
    assert rows["ext_dom"]["external"] is True and rows["ext_dom"]["available"] is True
    assert rows["night_signal"]["external"] is False
    assert rows["ext_world"]["available"] is False and rows["ext_world"]["unavailable_reason"] == "needs a working GPU"
    assert rows["ext_broken"]["available"] is False
    assert "MANIFEST.json" in rows["ext_broken"]["unavailable_reason"]
    assert rows["ext_dom"]["mascot"] is False
    assert rows["ext_dom"]["preview"] == "ext_dom"


def test_the_agent_view_of_an_installed_style(installed):
    view = tvs.agent_view("ext_dom")
    assert view["authoring_skill"] == ext.AUTHORING_SKILL
    assert view["external"] is True and view["props_key"] == "testStyle"
    assert tvs.agent_view("night_signal")["external"] is False


def test_auto_routes_to_an_installed_style_only_once_opted_in(installed):
    ids = [c["id"] for c in tvs.routing_candidates(False, "working", False)]
    assert "ext_dom" not in ids
    ids = [c["id"] for c in tvs.routing_candidates(False, "working", False, auto_externals=["ext_dom", "ext_broken"])]
    assert "ext_dom" in ids and "ext_broken" not in ids
    assert ids[-1] == tvs.SCENES
    assert "ext_dom" in tvs.route_choices(["ext_dom"]) and "ext_dom" not in tvs.route_choices([])


def test_an_installed_world_style_that_needs_a_gpu_is_gated(installed):
    from tubematic_core import renderers
    assert renderers.requires_gpu({"visual_style": "ext_world"}) is True
    assert renderers.requires_gpu({"visual_style": "ext_dom"}) is False
    assert tvs.cartoon_3d_gpu_error("ext_world", "not_usable") == "needs a GPU"


def test_an_installed_style_takes_no_mascot(installed):
    import sqlite3
    from tubematic_core import mascots
    assert mascots.no_mascot_error("ext_dom")
    assert mascots.no_mascot_error("ext_broken")
    con = sqlite3.connect(":memory:")
    cond = mascots.cartoon_mascot_clash_sql("?", "?", "?")
    assert con.execute(f"SELECT {cond}", ("ext_dom", "", "m1")).fetchone()[0] == 1
    assert con.execute(f"SELECT {cond}", ("night_signal", "", "m1")).fetchone()[0] == 1
    assert con.execute(f"SELECT {cond}", ("whiteboard", "", "m1")).fetchone()[0] == 0


@pytest.mark.parametrize("config, style", [
    ({"scenes": [{"type": "generated", "src": "vid/Intro"},
                 {"type": "generated", "source": "external", "src": "ext_dom/components/Main"}]}, "ext_dom"),
    ({"scenes": [{"type": "generated", "source": "installed", "src": "NightSignal"}]}, ""),
    ({"scenes": [{"type": "generated", "source": "external", "src": "../etc/components/Main"}]}, ""),
    ({"scenes": "nope"}, ""),
    ([], ""),
])
def test_the_external_style_a_scene_config_draws(config, style):
    assert ext.config_style(config) == style


def test_check_now_sees_a_file_edited_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path)
    d = make_package(tmp_path)
    assert ext.registry()["ext_test"].ok
    (d / "guide" / "guide.md").write_text("edited in place")
    assert not ext.check_now("ext_test").ok
    assert ext.check_now("ext_absent") is None and ext.check_now("../x") is None


# ── review round 2 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    'import x from "../../ext_other/components/Main";',
    'import "../../outside";',
    'const m = import("../../installed/Whiteboard");',
    'import y from "/etc/thing";',
    "export * from '../../x';",
])
def test_code_that_imports_outside_its_package_is_unavailable(tmp_path, line):
    """The package's fingerprint covers its own folder only, and a remote renderer
    stages that folder alone: a relative import leaving it is refused."""
    d = make_package(tmp_path, manifest=False)
    (d / "components" / "Main.tsx").write_text(line + "\nexport default () => null;\n")
    write_manifest(d)
    got = ext.load(tmp_path)["ext_test"]
    assert not got.ok and "outside" in got.reason


def test_imports_inside_the_package_and_bare_imports_are_fine(tmp_path):
    d = make_package(tmp_path, manifest=False)
    (d / "components" / "parts").mkdir()
    (d / "components" / "parts" / "a.ts").write_text('import * as THREE from "three";\nexport const a = 1;\n')
    (d / "components" / "Main.tsx").write_text(
        'import { a } from "./parts/a";\nimport { KEEP_OUT_X } from "@tubematic/scene-api";\nexport default () => a;\n')
    write_manifest(d)
    assert ext.load(tmp_path)["ext_test"].ok


def test_the_agent_view_of_a_broken_package_stays_external(installed):
    view = tvs.agent_view("ext_broken")
    assert view["external"] is True and view["authoring_skill"] == ext.AUTHORING_SKILL
    assert "MANIFEST.json" in view["unavailable_reason"]
    assert view["allows"] == {"figures": False, "line_art": False, "generated_characters": False}


def test_a_package_folder_removed_while_listed_does_not_break_the_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path)
    make_package(tmp_path)
    real = os.lstat

    def vanish(path, *a, **k):
        if str(path).endswith("ext_test"):
            raise FileNotFoundError(path)
        return real(path, *a, **k)
    monkeypatch.setattr(ext.os, "lstat", vanish)
    ext._stamp(tmp_path)   # must not raise
