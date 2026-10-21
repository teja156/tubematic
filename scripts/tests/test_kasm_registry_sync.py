"""kasm_workspace/sync_registry.py: the generator release.yml's
publish-kasm-registry job runs to write the Tubematic entry into the workspace
registry repo.

The launch form has no free-text fallback, so the list it writes is exactly
what can be installed from the form: a prerelease or a misordered list there
is a user-visible defect that no other check sees before a session launches.
"""

import importlib.util
import json
import os
import sys

import pytest

from . import test_kasm_workspaces as entry_checks

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENTRY_DIR = os.path.join(REPO_ROOT, "kasm_workspace", "registry", "Tubematic")


@pytest.fixture(scope="module")
def sync():
    spec = importlib.util.spec_from_file_location(
        "sync_registry", os.path.join(REPO_ROOT, "kasm_workspace", "sync_registry.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def entry():
    with open(os.path.join(ENTRY_DIR, "workspace.json")) as fh:
        return json.load(fh)


def _written(sync, tmp_path, *versions):
    out = tmp_path / "workspaces" / "Tubematic"
    assert sync.main(["--entry", ENTRY_DIR, "--out", str(out), *versions]) == 0
    return out, json.loads((out / "workspace.json").read_text())


def test_versions_are_sorted_numerically_newest_first(sync):
    # 2.0.10 is newer than 2.0.9: a string sort gets this wrong.
    assert sync.release_versions(["2.0.0", "2.1.0", "2.0.10", "2.0.9"]) == ["2.1.0", "2.0.10", "2.0.9", "2.0.0"]


def test_tags_and_duplicates_collapse_to_one_version(sync):
    assert sync.release_versions(["v2.0.0", "2.0.0", "v2.0.1"]) == ["2.0.1", "2.0.0"]


def test_prereleases_and_anything_else_are_never_offered(sync):
    assert sync.release_versions(["v2.1.0-rc.1", "develop", "2.1", "", "v2.0.0"]) == ["2.0.0"]


def test_an_empty_list_is_refused_and_nothing_is_written(sync, tmp_path):
    out = tmp_path / "Tubematic"
    assert sync.main(["--entry", ENTRY_DIR, "--out", str(out), "v2.1.0-rc.1"]) == 1
    assert not out.exists()
    assert sync.main(["--print-newest"]) == 1


def test_the_written_form_passes_the_same_checks_as_the_entry(sync, tmp_path):
    _, written = _written(sync, tmp_path, "v2.0.0", "v2.1.0", "v2.0.10")
    field = entry_checks._field(written, "tubematic_version")
    assert [o["value"] for o in field["options"]] == ["2.1.0", "2.0.10", "2.0.0"]
    assert field["value"] == "2.1.0"
    entry_checks.test_the_version_list_is_newest_first_with_the_newest_as_default(written)
    entry_checks.test_the_entry_has_the_schema_1_1_required_keys(written)
    entry_checks.test_the_form_keys_match_what_the_bootstrap_reads(written)


def test_only_the_version_list_changes(sync, tmp_path, entry):
    out, written = _written(sync, tmp_path, "v2.3.4")
    entry = json.loads(json.dumps(entry))  # the fixture is shared; compare a copy
    for form in (written, entry):
        entry_checks._field(form, "tubematic_version").pop("options")
        entry_checks._field(form, "tubematic_version").pop("value")
    assert written == entry
    assert (out / entry["image_src"]).read_bytes() == open(os.path.join(ENTRY_DIR, entry["image_src"]), "rb").read()
    assert (out / "workspace.json").read_text().endswith("}\n")


def test_print_images_lists_the_compatibility_images(sync, entry, capsys):
    assert sync.main(["--entry", ENTRY_DIR, "--print-images"]) == 0
    assert capsys.readouterr().out.split() == [c["image"] for c in entry["compatibility"]]


def test_print_newest(sync, capsys):
    assert sync.main(["--print-newest", "v2.0.0", "v2.0.10", "v2.1.0-rc.1"]) == 0
    assert capsys.readouterr().out.strip() == "2.0.10"
