"""The two Kasm Workspace images: the published kasm_workspace/ and the QA-only
kasm_workspace_testing/.

Neither image is built in CI, so these pin the parts of them that fail
silently: the dind /tmp patch (skipped -> a blank-screen session), the hooks'
exec bits (an inert hook looks exactly like Kasm never invoking one), the
published image's no-baked-source invariant, and the registry entry's launch
form, which Kasm validates only when a user launches a session.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PUBLISHED = os.path.join(REPO_ROOT, "kasm_workspace")
TESTING = os.path.join(REPO_ROOT, "kasm_workspace_testing")
PUBLISHED_DOCKERFILE = os.path.join(PUBLISHED, "dockerfile_tubematic_kasm_workspace")
TESTING_DOCKERFILE = os.path.join(TESTING, "dockerfile_tubematic_kasm")
WORKSPACE_JSON = os.path.join(PUBLISHED, "registry", "Tubematic", "workspace.json")

ANCHOR = "sudo /usr/bin/supervisord -n &"
SHELL_SCRIPTS = [
    "kasm_workspace/build.sh",
    "kasm_workspace/image/kasm_post_run_root.sh",
    "kasm_workspace/image/tubematic-installer",
    "kasm_workspace_testing/build.sh",
    "kasm_workspace_testing/kasm_post_run_root.sh",
]


def _read(path):
    with open(path) as fh:
        return fh.read()


def _dind_patch_command(dockerfile):
    """The RUN instruction that patches custom_startup.sh, joined the way
    Docker joins a backslash-continued instruction."""
    lines = _read(dockerfile).splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("RUN ") and "custom_startup.sh" in "".join(lines[i:i + 3]))
    body = []
    for line in lines[start:]:
        if line.endswith("\\"):
            body.append(line[:-1])
        else:
            body.append(line)
            break
    return "".join(body)[len("RUN "):]


def _run_patch(dockerfile, tmp_path, startup_text):
    (tmp_path / "custom_startup.sh").write_text(startup_text)
    env = {**os.environ, "STARTUPDIR": str(tmp_path)}
    return subprocess.run(["sh", "-c", _dind_patch_command(dockerfile)], env=env,
                          capture_output=True, text=True)


# ── The dind /tmp patch, in both images ─────────────────────────────────────

@pytest.mark.parametrize("dockerfile", [PUBLISHED_DOCKERFILE, TESTING_DOCKERFILE],
                         ids=["published", "testing"])
def test_the_tmp_patch_inserts_one_line_before_supervisord(dockerfile, tmp_path):
    before = f"#!/bin/bash\nstart_dind() {{\n                {ANCHOR}\n}}\n"
    result = _run_patch(dockerfile, tmp_path, before)
    assert result.returncode == 0, result.stderr
    after = (tmp_path / "custom_startup.sh").read_text().splitlines()
    assert len(after) == len(before.splitlines()) + 1
    patched = after.index(f"                {ANCHOR}") - 1
    assert after[patched].strip().startswith("mountpoint -q /tmp || sudo mount --bind /tmp /tmp")


@pytest.mark.parametrize("dockerfile", [PUBLISHED_DOCKERFILE, TESTING_DOCKERFILE],
                         ids=["published", "testing"])
def test_the_tmp_patch_fails_the_build_when_the_anchor_moves(dockerfile, tmp_path):
    """A skipped patch is invisible until someone sees a blank screen, so a
    base image that changed the anchor line must fail the build."""
    result = _run_patch(dockerfile, tmp_path, "#!/bin/bash\nsudo /usr/bin/supervisord &\n")
    assert result.returncode != 0
    assert "supervisord launch line" in result.stderr


# ── The published image ────────────────────────────────────────────────────

def test_the_published_image_bakes_no_tubematic_source():
    """The image never names a Tubematic version, so a release never needs a
    rebuild of it. A COPY of the repo would quietly end that."""
    dockerfile = _read(PUBLISHED_DOCKERFILE)
    sources = [src for line in dockerfile.splitlines() if line.startswith(("COPY", "ADD"))
               for src in line.split()[1:-1] if not src.startswith("--")]
    assert sources, "expected the hook and bootstrap COPY lines"
    assert not {"tubematic", ".", "./"} & set(sources), sources
    assert "COPY kasm_post_run_root.sh $STARTUPDIR/kasm_post_run_root.sh" in dockerfile


def test_every_file_the_published_dockerfile_copies_exists_in_its_context():
    image_dir = os.path.join(PUBLISHED, "image")
    for line in _read(PUBLISHED_DOCKERFILE).splitlines():
        if not line.startswith("COPY"):
            continue
        sources = [p for p in line.split()[1:-1] if not p.startswith("--")]
        for src in sources:
            assert os.path.isfile(os.path.join(image_dir, src)), src


@pytest.mark.parametrize("path", [
    "kasm_workspace/image/kasm_post_run_root.sh",
    "kasm_workspace/image/tubematic-installer",
    "kasm_workspace/build.sh",
    "kasm_workspace_testing/kasm_post_run_root.sh",
    "kasm_workspace_testing/build.sh",
])
def test_scripts_are_executable_in_the_git_index(path):
    """COPY keeps the source mode, and a File Mapping needs is_executable, so
    the committed mode is what decides whether the hook can run at all."""
    out = subprocess.run(["git", "ls-files", "-s", path], cwd=REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755 "), f"{path}: {out or 'not tracked'}"


@pytest.mark.parametrize("path", SHELL_SCRIPTS)
def test_shell_scripts_parse(path):
    subprocess.run(["bash", "-n", os.path.join(REPO_ROOT, path)], check=True)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
@pytest.mark.parametrize("path", [p for p in SHELL_SCRIPTS if p.startswith("kasm_workspace/")])
def test_published_shell_scripts_pass_shellcheck(path):
    result = subprocess.run(["shellcheck", "-S", "warning", os.path.join(REPO_ROOT, path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


# ── The registry entry ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def workspace():
    with open(WORKSPACE_JSON) as fh:
        return json.load(fh)


def _field(workspace, key):
    [field] = [f for f in workspace["launch_config"]["launch_form"] if f["key"] == key]
    return field


def test_the_entry_has_the_schema_1_1_required_keys(workspace):
    for key in ("friendly_name", "description", "image_src", "architecture", "compatibility"):
        assert workspace.get(key), key
    assert os.path.isfile(os.path.join(os.path.dirname(WORKSPACE_JSON), workspace["image_src"]))
    assert len(workspace["categories"]) <= 3
    [compat] = workspace["compatibility"]
    assert re.fullmatch(r"ghcr\.io/[a-z0-9-]+/tubematic-kasm-workspace:\d+\.\d+\.\d+", compat["image"])


def test_the_entry_runs_privileged_and_never_asks_for_a_gpu(workspace):
    """dind needs privileged; a GPU attached to this desktop crash-loops XFCE
    on an NVIDIA EGL failure."""
    assert workspace["run_config"]["privileged"] is True
    assert workspace["gpu_count"] == 0
    assert workspace["architecture"] == ["amd64"]


def test_the_selections_land_where_the_bootstrap_reads_them(workspace):
    """Not /tmp: that would depend on the dind /tmp patch winning its race."""
    mapping = workspace["launch_config"]["file_mapping"]
    assert mapping["destination"] == "/dockerstartup/tubematic_launch_selections.json"
    assert mapping["is_readable"] is True
    assert mapping["is_writeable"] is False and mapping["is_executable"] is False


def test_the_version_list_is_newest_first_with_the_newest_as_default(workspace):
    field = _field(workspace, "tubematic_version")
    values = [o["value"] for o in field["options"]]
    assert values, "the form must offer at least one version"
    for value in values:
        assert re.fullmatch(field["validator_regex"], value), value
    keyed = [tuple(int(p) for p in v.split(".")) for v in values]
    assert keyed == sorted(keyed, reverse=True) and len(set(keyed)) == len(keyed)
    assert field["value"] == values[0]
    assert field["options"][0]["label"] == f"{values[0]} (latest)"
    assert all("(latest)" not in o["label"] for o in field["options"][1:])
    # A browser-saved pick would keep pinning an old version on every launch.
    assert field["allow_saving"] is False and field["required"] is True


def test_the_install_method_defaults_to_release(workspace):
    field = _field(workspace, "install_method")
    assert {o["value"] for o in field["options"]} == {"release", "source"}
    assert field["value"] == "release"
    assert field["required"] is True


def test_the_form_keys_match_what_the_bootstrap_reads(workspace):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "tubematic_bootstrap", os.path.join(PUBLISHED, "image", "tubematic_bootstrap.py"))
    bootstrap = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bootstrap  # dataclasses resolve annotations through it
    spec.loader.exec_module(bootstrap)
    keys = {f["key"] for f in workspace["launch_config"]["launch_form"]}
    assert keys == {bootstrap.VERSION_KEY, bootstrap.METHOD_KEY}
    assert workspace["launch_config"]["file_mapping"]["destination"] == str(bootstrap.SELECTIONS_PATH)
    assert {o["value"] for o in _field(workspace, "install_method")["options"]} == set(bootstrap.METHODS)
    assert _field(workspace, "tubematic_version")["validator_regex"] == bootstrap.VERSION_RE.pattern
