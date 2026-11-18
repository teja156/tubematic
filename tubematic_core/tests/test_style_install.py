"""Staging and installing external style packages (TMDEV-253).

Staging is open to the API and MCP tokens; confirming is a person's (the API
checks the dashboard password). These tests pin the half in tubematic_core:
what each source unpacks to, what is refused before anything is installed, and
that what gets installed is exactly what was scanned.
"""
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import zipfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import external_styles as ext  # noqa: E402
from tubematic_core import style_install as si  # noqa: E402
from tubematic_core.tests.test_external_styles import make_package  # noqa: E402


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    styles, pending, incoming, src = (tmp_path / n for n in ("styles", "pending", "incoming", "src"))
    for d in (styles, pending, incoming, src):
        d.mkdir()
    monkeypatch.setattr(ext, "STYLES_DIR", styles)
    monkeypatch.setattr(si, "PENDING_DIR", pending)
    monkeypatch.setattr(si, "INCOMING_DIR", incoming)
    return type("Dirs", (), {"styles": styles, "pending": pending, "incoming": incoming, "src": src})


def _zip(d, prefix=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                zf.write(p, prefix + p.relative_to(d).as_posix())
    return buf.getvalue()


def test_a_zip_stages_checks_and_scans_without_installing(dirs):
    pkg = make_package(dirs.src, approve=False)
    rec = si.stage({"kind": "zip", "data": _zip(pkg), "filename": "test.zip"})
    assert rec["style_id"] == "ext_test" and rec["check"] == {"ok": True, "reason": ""}
    assert rec["scan"]["refusals"] == [] and rec["reviewed"] is False and rec["replaces"] is None
    assert rec["source"]["kind"] == "zip" and rec["source"]["filename"] == "test.zip"
    assert rec["fingerprint"] == ext.jobfiles.source_fingerprint(pkg)
    assert (dirs.pending / rec["id"] / "package" / "style.json").is_file()
    assert not (dirs.styles / "ext_test").exists()
    assert si.get(rec["id"])["id"] == rec["id"] and [r["id"] for r in si.list_pending()] == [rec["id"]]


def test_a_zip_with_one_wrapping_folder_and_mac_litter_is_fine(dirs):
    pkg = make_package(dirs.src, approve=False)
    data = _zip(pkg, "ext_test/")
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, "a") as zf:
        zf.writestr("__MACOSX/._x", "junk")
    rec = si.stage({"kind": "zip", "data": buf.getvalue()})
    assert rec["check"]["ok"], rec["check"]


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../b.txt"])
def test_a_zip_path_outside_the_package_is_refused(dirs, name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, "x")
    with pytest.raises(si.InstallError, match="outside the package"):
        si.stage({"kind": "zip", "data": buf.getvalue()})
    assert list(p for p in dirs.pending.iterdir() if p.name != ".lock") == []


def test_a_zip_symlink_and_oversize_are_refused(dirs, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(si.InstallError, match="symlink"):
        si.stage({"kind": "zip", "data": buf.getvalue()})
    monkeypatch.setattr(si, "MAX_UNPACKED_BYTES", 10)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big", "0" * 1000)
    with pytest.raises(si.InstallError, match="unpacks to more"):
        si.stage({"kind": "zip", "data": buf.getvalue()})
    with pytest.raises(si.InstallError, match="not a zip"):
        si.stage({"kind": "zip", "data": b"not a zip"})


def test_a_package_that_fails_its_check_stages_but_cannot_be_confirmed(dirs):
    pkg = make_package(dirs.src, approve=False)
    (pkg / "schema.json").unlink()
    ext.write_manifest(pkg)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    assert rec["check"]["ok"] is False and "schema.json" in rec["check"]["reason"]
    with pytest.raises(si.InstallError, match="cannot be installed"):
        si.confirm(rec["id"])


def test_a_scan_refusal_blocks_the_confirm(dirs):
    pkg = make_package(dirs.src, approve=False)
    (pkg / "components" / "Main.tsx").write_text('import fs from "fs";\nexport default () => null;\n')
    ext.write_manifest(pkg)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    with pytest.raises(si.InstallError, match="scan refused"):
        si.confirm(rec["id"])


def test_confirm_installs_exactly_what_was_scanned_and_approves_it(dirs):
    pkg = make_package(dirs.src, approve=False)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    out = si.confirm(rec["id"])
    assert out["style_id"] == "ext_test" and out["fingerprint"] == rec["fingerprint"]
    found = ext.load(dirs.styles)["ext_test"]
    assert found.ok, found.reason
    record = ext.approvals(dirs.styles)["ext_test"]
    assert record["source"]["kind"] == "zip" and record["reviewed"] is False and record["version"] == "1.0.0"
    assert not (dirs.pending / rec["id"]).exists()
    assert [p.name for p in dirs.styles.iterdir()] == sorted([".installed.json", "ext_test"]) or \
        sorted(p.name for p in dirs.styles.iterdir()) == [".installed.json", "ext_test"]


def test_a_staged_package_changed_before_confirm_is_refused(dirs):
    pkg = make_package(dirs.src, approve=False)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    (dirs.pending / rec["id"] / "package" / "guide" / "guide.md").write_text("# swapped\n")
    with pytest.raises(si.InstallError, match="changed after it was scanned"):
        si.confirm(rec["id"])
    assert not (dirs.styles / "ext_test").exists()


def test_an_update_replaces_the_installed_version_and_says_what_it_replaces(dirs):
    pkg = make_package(dirs.src, approve=False)
    si.confirm(si.stage({"kind": "zip", "data": _zip(pkg)})["id"])
    style = json.loads((pkg / "style.json").read_text())
    style["external"]["version"] = "2.0.0"
    (pkg / "style.json").write_text(json.dumps(style))
    ext.write_manifest(pkg)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    assert rec["replaces"]["version"] == "1.0.0"
    si.confirm(rec["id"])
    assert ext.approvals(dirs.styles)["ext_test"]["version"] == "2.0.0"
    assert ext.load(dirs.styles)["ext_test"].ok
    assert sorted(p.name for p in dirs.styles.iterdir()) == [".installed.json", "ext_test"]


def test_an_incoming_folder_and_zip_stage(dirs):
    make_package(dirs.incoming, sid="ext_test", approve=False)
    assert si.stage({"kind": "incoming", "name": "ext_test"})["check"]["ok"]
    (dirs.incoming / "pkg.zip").write_bytes(_zip(dirs.incoming / "ext_test"))
    rec = si.stage({"kind": "incoming", "name": "pkg.zip"})
    assert rec["check"]["ok"] and rec["source"] == {"kind": "incoming", "name": "pkg.zip"}
    for bad in ("../x", "", "a/b"):
        with pytest.raises(si.InstallError):
            si.stage({"kind": "incoming", "name": bad})


def test_an_installed_package_waiting_for_review_stages_and_confirms(dirs):
    make_package(dirs.styles, approve=False)
    assert ext.load(dirs.styles)["ext_test"].needs_review
    rec = si.stage({"kind": "installed", "id": "ext_test"})
    si.confirm(rec["id"])
    assert ext.load(dirs.styles)["ext_test"].ok


def test_the_gallery_verifies_the_archive_checksum_and_marks_reviewed(dirs, monkeypatch):
    pkg = make_package(dirs.src, approve=False)
    data = _zip(pkg)
    index = {"styles": [{"id": "ext_test", "archive_url": "https://g.invalid/ext_test.zip",
                         "sha256": hashlib.sha256(data).hexdigest(), "commit": "abc"}]}
    served = {"https://g.invalid/index.json": json.dumps(index).encode(), "https://g.invalid/ext_test.zip": data}
    monkeypatch.setattr(si, "_http_get", lambda url, cap: served[url])
    monkeypatch.setattr(si, "OFFICIAL_GALLERY_URL", "https://g.invalid/index.json")
    rec = si.stage({"kind": "gallery", "id": "ext_test"}, index_url="https://g.invalid/index.json")
    assert rec["reviewed"] is True and rec["source"]["commit"] == "abc"
    served["https://g.invalid/ext_test.zip"] = data + b"tampered"
    with pytest.raises(si.InstallError, match="does not match the gallery's checksum"):
        si.stage({"kind": "gallery", "id": "ext_test"}, index_url="https://g.invalid/index.json")
    with pytest.raises(si.InstallError, match="no style"):
        si.stage({"kind": "gallery", "id": "ext_other"}, index_url="https://g.invalid/index.json")
    with pytest.raises(si.InstallError, match="no gallery address"):
        si.stage({"kind": "gallery", "id": "ext_test"})


def test_http_get_refuses_plain_http():
    with pytest.raises(si.InstallError, match="not an https"):
        si._http_get("http://x.invalid/a", 10)


def _git_repo(path, pkg):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for p in pkg.rglob("*"):
        if p.is_file():
            t = path / p.relative_to(pkg)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(p.read_bytes())
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x"}
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "v1"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "tag", "v1"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


def test_git_fetches_a_pinned_tag_and_records_its_commit(dirs, tmp_path, monkeypatch):
    """The real git fetch, from a local repository (a person may only name https)."""
    pkg = make_package(dirs.src, approve=False)
    commit = _git_repo(tmp_path / "repo", pkg)
    monkeypatch.setattr(si, "_GIT_PROTOCOL", ["-c", "protocol.allow=always"])
    monkeypatch.setattr(si, "_check_git_source", lambda url, ref: None)
    rec = si.stage({"kind": "git", "url": str(tmp_path / "repo"), "ref": "v1"})
    assert rec["source"]["commit"] == commit and rec["check"]["ok"], rec["check"]
    assert not (dirs.pending / rec["id"] / "package" / ".git").exists()
    rec = si.stage({"kind": "git", "url": str(tmp_path / "repo"), "ref": commit})
    assert rec["source"]["commit"] == commit


def test_git_refuses_a_local_repository_by_default(dirs, tmp_path, monkeypatch):
    pkg = make_package(dirs.src, approve=False)
    _git_repo(tmp_path / "repo", pkg)
    monkeypatch.setattr(si, "_check_git_source", lambda url, ref: None)
    with pytest.raises(si.InstallError, match="git fetch failed"):
        si.stage({"kind": "git", "url": str(tmp_path / "repo"), "ref": "v1"})


@pytest.mark.parametrize("url, ref, match", [
    ("http://github.com/a/b", "v1", "https"),
    ("https://user:tok@github.com/a/b", "v1", "no user name"),
    ("https://github.com/a/b", "", "commit or a tag"),
    ("https://github.com/a/b", "a..b", "commit or a tag"),
    ("https://github.com/a/b", "-c core.x", "commit or a tag"),
])
def test_git_refuses_unpinned_or_unsafe_sources(dirs, url, ref, match):
    with pytest.raises(si.InstallError, match=match):
        si.stage({"kind": "git", "url": url, "ref": ref})


def test_audit_discard_and_expiry(dirs):
    pkg = make_package(dirs.src, approve=False)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    got = si.set_audit(rec["id"], "concerns", "Main.tsx draws text outside the safe area")
    assert got["audit"]["verdict"] == "concerns" and si.get(rec["id"])["audit"]["notes"].startswith("Main")
    with pytest.raises(si.InstallError):
        si.set_audit(rec["id"], "maybe", "")
    si.discard(rec["id"])
    with pytest.raises(si.InstallError, match="no such pending"):
        si.get(rec["id"])
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    later = si._parse(rec["expires_at"]) + si._dt.timedelta(seconds=1)
    si.sweep(later)
    assert not (dirs.pending / rec["id"]).exists()
    with pytest.raises(si.InstallError):
        si.get("../../etc")


def test_too_many_pending_installs_are_refused(dirs, monkeypatch):
    monkeypatch.setattr(si, "MAX_PENDING", 1)
    pkg = make_package(dirs.src, approve=False)
    si.stage({"kind": "zip", "data": _zip(pkg)})
    with pytest.raises(si.InstallError, match="already waiting"):
        si.stage({"kind": "zip", "data": _zip(pkg)})


def test_read_file_shows_text_files_of_the_staged_package_only(dirs):
    pkg = make_package(dirs.src, approve=False)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    assert si.read_file(rec["id"], "components/Main.tsx").startswith("export default")
    for bad in ("../pending.json", "/etc/passwd", "preview.mp4", "nope.ts"):
        with pytest.raises(si.InstallError):
            si.read_file(rec["id"], bad)


def test_remove_deletes_the_package_and_its_approval(dirs):
    make_package(dirs.styles)
    si.remove("ext_test")
    assert not (dirs.styles / "ext_test").exists() and "ext_test" not in ext.approvals(dirs.styles)
    with pytest.raises(si.InstallError, match="not installed"):
        si.remove("ext_test")
    with pytest.raises(si.InstallError):
        si.remove("../x")


def test_staging_the_same_style_from_the_same_source_replaces_the_older_pending_install(dirs):
    """The creation skill stages after every edit; its earlier stages must not
    pile up against MAX_PENDING."""
    make_package(dirs.incoming, sid="ext_test", approve=False)
    first = si.stage({"kind": "incoming", "name": "ext_test"})
    second = si.stage({"kind": "incoming", "name": "ext_test"})
    assert [r["id"] for r in si.list_pending()] == [second["id"]]
    assert not (dirs.pending / first["id"]).exists()
    # another source of the same style is a different install to review, kept
    pkg = make_package(dirs.src, approve=False)
    third = si.stage({"kind": "zip", "data": _zip(pkg)})
    assert {r["id"] for r in si.list_pending()} == {second["id"], third["id"]}


# ── review round 1 ───────────────────────────────────────────────────────────

def test_a_redirect_to_plain_http_is_refused():
    """Only the first address was checked for https; urlopen followed a
    redirect anywhere, including an internal http address."""
    import urllib.request
    handler = si._HttpsOnlyRedirect()
    req = urllib.request.Request("https://g.invalid/a")
    with pytest.raises(si.InstallError, match="redirected to a non-https"):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8080/secret")
    assert handler.redirect_request(req, None, 302, "Found", {}, "https://cdn.invalid/b") is not None


def test_directory_entries_count_against_the_file_cap(dirs, monkeypatch):
    monkeypatch.setattr(si, "MAX_FILES", 3)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(5):
            zf.writestr(f"d{i}/", "")
    with pytest.raises(si.InstallError, match="more than 3"):
        si.stage({"kind": "zip", "data": buf.getvalue()})


def test_bytes_changed_while_confirming_are_not_installed(dirs, monkeypatch):
    """The fingerprint was taken before the copy, so a file edited between the
    two was installed and approved. The copy is what is checked now."""
    pkg = make_package(dirs.src, approve=False)
    rec = si.stage({"kind": "zip", "data": _zip(pkg)})
    real = si.shutil.copytree
    staged = dirs.pending / rec["id"] / "package"

    def tamper(src, dst, *a, **kw):
        if pathlib.Path(src) == staged:
            (staged / "guide" / "guide.md").write_text("# swapped mid-copy\n")
        return real(src, dst, *a, **kw)

    monkeypatch.setattr(si.shutil, "copytree", tamper)
    with pytest.raises(si.InstallError, match="changed after it was scanned"):
        si.confirm(rec["id"])
    assert not (dirs.styles / "ext_test").exists()
    assert not [p for p in dirs.styles.iterdir() if p.name.startswith(".incoming")]


def test_only_the_official_gallery_marks_a_package_reviewed(dirs, monkeypatch):
    """style_gallery_url can be set by anything with the API token: a gallery
    of someone's own choosing is not the maintainer's review."""
    pkg = make_package(dirs.src, approve=False)
    data = _zip(pkg)
    index = {"styles": [{"id": "ext_test", "archive_url": "https://g.invalid/a.zip",
                         "sha256": hashlib.sha256(data).hexdigest()}]}
    monkeypatch.setattr(si, "_http_get", lambda url, cap: json.dumps(index).encode() if url.endswith(".json") else data)
    monkeypatch.setattr(si, "OFFICIAL_GALLERY_URL", "https://official.invalid/index.json")
    rec = si.stage({"kind": "gallery", "id": "ext_test"}, index_url="https://other.invalid/index.json")
    assert rec["reviewed"] is False
    rec = si.stage({"kind": "gallery", "id": "ext_test"}, index_url="https://official.invalid/index.json")
    assert rec["reviewed"] is True
