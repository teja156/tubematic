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
import re
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
BASE = "https://gallery.tubematic.ai/"


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


RELEASE_SCRIPT = SKELETON / ".github" / "tubematic-release.sh"


def _resolve(tmp_path, releases):
    """Runs the gallery's release resolver on a fake release list; returns its step outputs."""
    feed = tmp_path / "releases.json"
    feed.write_text(json.dumps(releases))
    out = tmp_path / "out"
    out.write_text("")
    env = {**os.environ, "TUBEMATIC_RELEASES_URL": feed.as_uri(), "GITHUB_OUTPUT": str(out)}
    env.pop("GH_TOKEN", None)
    subprocess.run(["bash", str(RELEASE_SCRIPT)], check=True, env=env, capture_output=True, text=True)
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


def _release(tag, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease}


def test_the_gallery_reviews_with_the_newest_published_release(tmp_path):
    """Nothing in the gallery repo moves by hand on a Tubematic release (`tubematic-backend:latest` never
    existed: a release pushes only its version tag). The newest published release by version wins, not
    the newest by date (a patch on an older line) nor a draft or prerelease."""
    got = _resolve(tmp_path, [_release("v2.4.1"), _release("v2.3.2"), _release("v2.4.0"),
                              _release("v2.5.0", draft=True), _release("v2.6.0", prerelease=True)])
    assert got == {"ref": "v2.4.1", "image": "ghcr.io/teja156/tubematic-backend:2.4.1"}


def test_before_2_4_0_the_gallery_uses_develop_and_renders_nothing(tmp_path):
    """2.4.0 is the first release with scripts/gallery.py and external-style rendering."""
    assert _resolve(tmp_path, [_release("v2.3.1"), _release("v2.3.0")]) == {"ref": "develop", "image": ""}


def test_both_workflows_take_tubematic_from_the_resolver():
    pr = yaml.safe_load((SKELETON / ".github" / "workflows" / "pr.yml").read_text())
    pub = yaml.safe_load((SKELETON / ".github" / "workflows" / "publish.yml").read_text())
    for wf in (pr, pub):
        assert "TUBEMATIC_REF" not in str(wf) and "TUBEMATIC_IMAGE" not in str(wf) and ":latest" not in str(wf)
        steps = [s for job in wf["jobs"].values() for s in job["steps"]]
        assert any(s.get("run", "").strip() == "bash .github/tubematic-release.sh" for s in steps)
        checkouts = [s["with"] for s in steps if s.get("with", {}).get("repository") == "teja156/tubematic"]
        assert checkouts and all("outputs.ref" in c["ref"] for c in checkouts)
    render = next(s for s in pr["jobs"]["render"]["steps"] if "gallery.py render" in s.get("run", ""))
    assert "outputs.image" in render["env"]["REVIEW_IMAGE"]
    assert 'if [ -z "$REVIEW_IMAGE" ]' in render["run"]


def test_the_resolver_reads_every_page_of_releases(tmp_path):
    """GitHub lists 100 releases a page; the newest version can be on a later page."""
    import http.server
    import threading

    pages = {"/p1": ([_release("v2.4.0")], '<http://127.0.0.1:{port}/p2>; rel="next"'),
             "/p2": ([_release("v2.5.3")], "")}

    class Feed(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body, link = pages[self.path]
            self.send_response(200)
            if link:
                self.send_header("Link", link.format(port=self.server.server_port))
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Feed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = tmp_path / "out"
        out.write_text("")
        env = {**os.environ, "TUBEMATIC_RELEASES_URL": f"http://127.0.0.1:{server.server_port}/p1",
               "GITHUB_OUTPUT": str(out)}
        subprocess.run(["bash", str(RELEASE_SCRIPT)], check=True, env=env, capture_output=True)
        assert "ref=v2.5.3" in out.read_text()
    finally:
        server.shutdown()


def _set_pack(styles, sid, **fields):
    """Rewrites a test package's style.json fields (top level, or `external.<key>`) and its manifest."""
    p = styles / sid / "style.json"
    pack = json.loads(p.read_text())
    for key, value in fields.items():
        if key.startswith("external_"):
            pack["external"][key[len("external_"):]] = value
        else:
            pack[key] = value
    p.write_text(json.dumps(pack, indent=1))
    ext.write_manifest(styles / sid)


def test_build_writes_a_page_people_can_browse(tmp_path):
    """gallery.tubematic.ai showed raw JSON: the build also writes index.html from the same entries."""
    styles = _styles(tmp_path, "ext_good")
    site = tmp_path / "site"
    assert gallery.main(["build", str(styles), str(site), "--base-url", BASE,
                         "--repo-url", "https://github.com/teja156/tubematic-styles"]) == 0
    page = (site / "index.html").read_text()
    entry = json.loads((site / "index.json").read_text())["styles"][0]
    assert page.startswith("<!doctype html>") and "<script" not in page
    for value in (entry["name"], entry["id"], entry["version"], entry["author"], entry["sha256"]):
        assert value in page
    # its own files by relative path, so the page works at any address
    assert 'href="archives/ext_good-1.0.0.zip"' in page
    assert 'src="previews/ext_good.mp4"' in page and 'poster="previews/ext_good.webp"' in page
    assert 'href="https://github.com/teja156/tubematic-styles/blob/main/SUBMITTING.md"' in page
    assert "Profiles" in page and "Install from file" in page


def test_the_page_escapes_what_a_submitter_wrote(tmp_path):
    styles = _styles(tmp_path, "ext_good", "ext_link")
    _set_pack(styles, "ext_good", label='Evil "Style"', tagline="<script>alert(1)</script> & more",
              external_author="<img src=x onerror=alert(1)>", external_source="javascript:alert(1)")
    _set_pack(styles, "ext_link", external_source="https://example.com/style")
    site = tmp_path / "site"
    assert gallery.main(["build", str(styles), str(site), "--base-url", BASE]) == 0
    page = (site / "index.html").read_text()
    assert "<script" not in page and "<img src=x" not in page and "javascript:" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in page and "Evil &quot;Style&quot;" in page
    # only an https homepage becomes a link
    assert 'href="https://example.com/style"' in page


def test_an_empty_gallery_says_so(tmp_path):
    styles = tmp_path / "styles"
    styles.mkdir()
    assert gallery.main(["build", str(styles), str(tmp_path / "site"), "--base-url", BASE]) == 0
    assert "No styles yet" in (tmp_path / "site" / "index.html").read_text()


def test_the_page_is_the_same_on_every_build(tmp_path):
    styles = _styles(tmp_path, "ext_good")
    a, b = tmp_path / "a", tmp_path / "b"
    for site in (a, b):
        assert gallery.main(["build", str(styles), str(site), "--base-url", BASE]) == 0
    assert (a / "index.html").read_bytes() == (b / "index.html").read_bytes()


def test_the_publish_workflow_links_the_page_to_its_repository():
    publish = yaml.safe_load((SKELETON / ".github" / "workflows" / "publish.yml").read_text())
    build_step = next(s for s in publish["jobs"]["build"]["steps"] if s.get("name", "").startswith("Build"))
    assert '--repo-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY"' in build_step["run"]


@pytest.mark.parametrize("version", ["../../escape", "1.0/x", "1.0?x", "1.0#x", " 1.0", ""])
def test_a_version_that_is_not_a_safe_file_name_fails_scan_and_build(tmp_path, capsys, version):
    """The version names the published archive: a slash or dot-dot wrote outside the site, ? or #
    broke the download link."""
    styles = _styles(tmp_path, "ext_good")
    _set_pack(styles, "ext_good", external_version=version)
    assert gallery.main(["scan", str(styles)]) == 1
    assert gallery.main(["build", str(styles), str(tmp_path / "site"), "--base-url", BASE]) == 1
    assert not list(tmp_path.glob("**/escape*")) and not (tmp_path / "site" / "index.json").exists()


def test_the_page_wears_the_dashboards_theme(tmp_path):
    """The gallery page matches the dashboard (user, 2026-11-18): the same colour tokens, fonts and
    logo. The tokens are copied, so this pins them to dashboard/app/globals.css."""
    css = (REPO / "dashboard" / "app" / "globals.css").read_text()
    root = css[css.index("/* ── TubeMatic CRT Design Tokens"):]
    tokens = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", root[:root.index("}")]))
    page = gallery.render_page([], "")
    for name in ("bg", "panel", "panel-2", "border", "border-2", "ink", "ink-2", "dim", "mute", "amber"):
        assert f"--{name}: {tokens[name]};" in page, name
    assert "Space+Mono" in page and "Inter" in page
    logo = (REPO / "dashboard" / "public" / "logo-mark.svg").read_text()
    assert "<rect x=\"36\" y=\"24\" width=\"4\" height=\"24\">" in logo  # the mark, as the dashboard draws it
    assert "data:image/svg+xml;base64," in page and ">TUBEMATIC<" in page
