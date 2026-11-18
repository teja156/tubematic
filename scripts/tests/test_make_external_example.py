"""scripts/make_external_example.py (TMDEV-252): the built-in styles repackaged as
external packages, the proof that the external path draws a whole style.

A package whose code reaches outside its own folder by a relative path compiles
in this repo and fails on an install, where the folder sits in the styles
volume: every relative import must land inside the package.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import make_external_example as mk  # noqa: E402
from tubematic_core import external_styles as ext  # noqa: E402

IMPORT = re.compile(r'(?:from |import\()"(\.[^"]+)"')


@pytest.mark.parametrize("args, sid, renderer, gpu", [
    (["night_signal"], "ext_night_signal", "dom", False),
    (["low_poly_skit"], "ext_low_poly_skit", "cartoon_3d", False),
    (["low_poly_skit", "--gpu"], "ext_low_poly_skit_gpu", "cartoon_3d", True),
])
def test_each_example_is_a_package_the_loader_accepts(tmp_path, args, sid, renderer, gpu):
    assert mk.main([args[0], str(tmp_path), *args[1:]]) == 0
    found = ext.load(tmp_path)[sid]
    assert found.ok, found.reason
    assert found.pack["renderer"] == renderer and found.pack["needs"]["gpu"] is gpu


@pytest.mark.parametrize("style", ["night_signal", "low_poly_skit"])
def test_every_relative_import_lands_inside_the_package(tmp_path, style):
    mk.main([style, str(tmp_path)])
    d = next(tmp_path.iterdir())
    for f in d.rglob("*.ts*"):
        for rel in IMPORT.findall(f.read_text()):
            target = (f.parent / rel).resolve()
            assert d.resolve() in target.parents, f"{f.relative_to(d)} imports {rel}, outside the package"
            found = [p for p in (target, *(target.with_name(target.name + e) for e in (".ts", ".tsx")))
                     if p.is_file()] or [p for p in (target / "index.ts", target / "index.tsx") if p.is_file()]
            assert found, f"{f.relative_to(d)} imports {rel}, which is no file of the package"


def test_the_night_signal_example_config_draws_the_package(tmp_path):
    mk.main(["night_signal", str(tmp_path)])
    config = json.loads((tmp_path / "ext_night_signal" / "guide" / "example-config.json").read_text())
    assert ext.config_style(config) == "ext_night_signal"
    assert (tmp_path / "ext_night_signal" / "components" / "NightSignal.tsx").is_file()


def test_gpu_applies_to_low_poly_only(tmp_path):
    with pytest.raises(SystemExit):
        mk.main(["night_signal", str(tmp_path), "--gpu"])


@pytest.mark.parametrize("style, sid, says", [
    ("night_signal", "ext_night_signal", ("render_style_parts", "preview_frames")),
    ("low_poly_skit", "ext_low_poly_skit", ('get_style_guide(video_id, path="runner/', "cartoon_kit_read")),
])
def test_each_guide_opens_with_how_the_package_differs_from_its_built_in_twin(tmp_path, style, sid, says):
    """The guide is the built-in skill's text, which names the built-in style's
    own tools and paths; the note on top says what to use instead."""
    mk.main([style, str(tmp_path)])
    note = (tmp_path / sid / "guide" / "guide.md").read_text().split("\n\n---\n\n", 1)[0]
    for word in says:
        assert word in note, word
