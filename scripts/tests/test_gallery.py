"""The style gallery's tools (TMDEV-255): scripts/gallery.py and the gallery
repository skeleton in scripts/gallery/repo/.

The trap: the gallery promises that what an install downloads is what the
maintainer reviewed. That holds only if the index's checksum is of the exact
archive published, the archive is the same bytes on every build, and an
install from it passes the installer's own checks.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import gallery  # noqa: E402
from tubematic_core import external_styles as ext  # noqa: E402
from tubematic_core import style_install as si  # noqa: E402
from tubematic_core.tests.test_external_styles import make_package  # noqa: E402

SKELETON = REPO / "scripts" / "gallery" / "repo"
BASE = "https://tejaswaroop.com/tubematic-styles/"


def _styles(tmp_path, *ids):
    styles = tmp_path / "styles"
    styles.mkdir()
    for sid in ids:
        make_package(styles, sid=sid, approve=False)
    return styles


def test_scan_passes_a_good_package_and_fails_a_refused_one(tmp_path, capsys):
    styles = _styles(tmp_path, "ext_good", "ext_bad")
    (styles / "ext_bad" / "components" / "Main.tsx").write_text('import fs from "fs";\n')
    ext.write_manifest(styles / "ext_bad")
    assert gallery.main(["scan", str(styles), "--only", "ext_good"]) == 0
    assert "## ext_good: passes" in capsys.readouterr().out
    assert gallery.main(["scan", str(styles)]) == 1
    out = capsys.readouterr().out
    assert "## ext_bad: FAILED" in out and "Refused: components/Main.tsx: imports 'fs'" in out


def test_scan_fails_a_package_named_differently_from_its_id(tmp_path, capsys):
    styles = tmp_path / "styles"
    styles.mkdir()
    make_package(styles, sid="ext_one", approve=False)
    (styles / "ext_one").rename(styles / "ext_two")
    assert gallery.main(["scan", str(styles)]) == 1
    assert "ext_two: FAILED" in capsys.readouterr().out


def test_a_pointer_must_name_a_full_commit(tmp_path, capsys):
    styles = tmp_path / "styles"
    styles.mkdir()
    (styles / "ext_ptr.json").write_text(json.dumps({"repo": "https://github.com/a/b", "commit": "main"}))
    assert gallery.main(["scan", str(styles)]) == 1
    assert "40-hex commit" in capsys.readouterr().out


def test_build_writes_a_deterministic_archive_and_an_index_an_install_accepts(tmp_path, monkeypatch):
    styles = _styles(tmp_path, "ext_good")
    site, again = tmp_path / "site", tmp_path / "again"
    assert gallery.main(["build", str(styles), str(site), "--base-url", BASE, "--commit", "c" * 40]) == 0
    assert gallery.main(["build", str(styles), str(again), "--base-url", BASE]) == 0
    archive = site / "archives" / "ext_good-1.0.0.zip"
    assert archive.read_bytes() == (again / "archives" / "ext_good-1.0.0.zip").read_bytes()
    index = json.loads((site / "index.json").read_text())
    entry = index["styles"][0]
    assert index["version"] == 1 and entry["id"] == "ext_good" and entry["version"] == "1.0.0"
    assert entry["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert entry["archive_url"] == BASE + "archives/ext_good-1.0.0.zip" and entry["commit"] == "c" * 40
    assert (site / "previews" / "ext_good.mp4").is_file() and (site / "previews" / "ext_good.webp").is_file()

    # an install from the published site: the official gallery's, so reviewed
    for name in ("installed", "pending"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path / "installed")
    monkeypatch.setattr(si, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(si, "_http_get", lambda url, cap: (site / url[len(BASE):]).read_bytes())
    rec = si.stage({"kind": "gallery", "id": "ext_good"}, index_url=si.OFFICIAL_GALLERY_URL)
    assert rec["check"]["ok"] and rec["reviewed"] is True
    si.confirm(rec["id"])
    assert ext.load(tmp_path / "installed")["ext_good"].ok


def test_build_refuses_to_publish_a_failing_package(tmp_path):
    styles = _styles(tmp_path, "ext_good")
    (styles / "ext_good" / "schema.json").unlink()
    ext.write_manifest(styles / "ext_good")
    assert gallery.main(["build", str(styles), str(tmp_path / "site"), "--base-url", BASE]) == 1
    assert not (tmp_path / "site" / "index.json").exists()


def test_the_official_gallery_is_the_skeletons_pages_site():
    assert si.OFFICIAL_GALLERY_URL == BASE + "index.json"
    publish = yaml.safe_load((SKELETON / ".github" / "workflows" / "publish.yml").read_text())
    build_step = next(s for s in publish["jobs"]["build"]["steps"] if s.get("name", "").startswith("Build"))
    assert f'--base-url "{BASE}"' in build_step["run"]


def test_the_skeletons_workflows_call_the_tools_that_exist():
    pr = yaml.safe_load((SKELETON / ".github" / "workflows" / "pr.yml").read_text())
    runs = " ".join(s.get("run", "") for job in pr["jobs"].values() for s in job["steps"])
    assert 'gallery.py scan styles --only "$IDS"' in runs and "gallery.py render" in runs
    # a fork has no origin/<base> branch: the diff is against the event's base commit
    assert '"$BASE_SHA" HEAD' in runs and "origin/" not in runs
    for job in pr["jobs"].values():
        assert job["runs-on"] == "ubuntu-24.04"


def test_the_checklist_covers_what_the_design_asks_a_reviewer_to_check():
    checklist = (SKELETON / "REVIEW-CHECKLIST.md").read_text().lower()
    for item in ("network", "eval", "obfuscated", "guide", "reference footage", "logos", "named characters",
                 "licence", "rendered example"):
        assert item in checklist, item


@pytest.mark.skipif(not os.environ.get("TUBEMATIC_GALLERY_RENDER_IMAGE"),
                    reason="renders with a backend image: set TUBEMATIC_GALLERY_RENDER_IMAGE")
def test_render_makes_a_video_of_a_scene_styles_example(tmp_path):
    """Opt-in: a real render in the backend image (CPU, a few seconds of video)."""
    styles = _styles(tmp_path, "ext_good")
    pkg = styles / "ext_good"
    (pkg / "components" / "Main.tsx").write_text(
        'import React from "react";\nimport { AbsoluteFill } from "remotion";\n'
        'export default () => <AbsoluteFill style={{ background: "#246" }} />;\n')
    (pkg / "guide" / "example-config.json").write_text(json.dumps({
        "totalFrames": 60, "fps": 30, "scenes": [{"type": "generated", "source": "external",
        "src": "ext_good/components/Main", "startFrame": 0, "durationInFrames": 60, "props": {"testStyle": {}}}]}))
    ext.write_manifest(pkg)
    out = tmp_path / "out" / "ext_good.mp4"
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "gallery.py"), "render", str(pkg), str(out),
                           "--image", os.environ["TUBEMATIC_GALLERY_RENDER_IMAGE"]], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out.stat().st_size > 1000


def test_render_names_the_browser_with_the_flag_remotion_reads():
    """--browser-executable-path is ignored by the Remotion CLI (renderer/api/tests/test_gpu_rendering.py)."""
    src = (REPO / "scripts" / "gallery.py").read_text()
    assert "--browser-executable /usr/bin/chromium" in src and "--browser-executable-path" not in src


def test_a_world_style_is_not_rendered_and_says_so_with_its_own_exit_code(tmp_path):
    styles = tmp_path / "styles"
    styles.mkdir()
    make_package(styles, sid="ext_world", renderer="cartoon_3d", approve=False)
    assert gallery.main(["render", str(styles / "ext_world"), str(tmp_path / "x.mp4"), "--image", "unused"]) == 3


def test_the_pr_workflow_fails_on_a_failed_render():
    """A failed render used to be a warning, so a pull request passed with no example to review."""
    pr = (SKELETON / ".github" / "workflows" / "pr.yml").read_text()
    assert 'if [ "$rc" = 3 ]' in pr and 'exit 1; fi' in pr and "::warning::" not in pr


def test_no_pull_request_controlled_value_is_expanded_inside_a_shell_command():
    """A path like styles/$(cmd)/x reached `echo "${{ steps.changed.outputs.ids }}"` and ran."""
    pr = yaml.safe_load((SKELETON / ".github" / "workflows" / "pr.yml").read_text())
    for job in pr["jobs"].values():
        for step in job["steps"]:
            run = step.get("run", "")
            assert "${{ steps." not in run and "${{ needs." not in run, step.get("name")
    changed = next(s for s in pr["jobs"]["scan"]["steps"] if s.get("id") == "changed")["run"]
    assert "ext_[a-z0-9_]{1,40}" in changed and "exit 1" in changed
