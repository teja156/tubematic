"""Host-side callers must be able to import pipeline.py and mcp/server.py.

The vqa helpers run on the host, not in a container, and each puts only the
*module's own* directory on sys.path — not the repo root. When those two modules
gained a `tubematic_core` import they stopped being importable that way, and
every one of these scripts died with ModuleNotFoundError.

The container hides this completely: PYTHONPATH=/app/lib resolves the package
there, so nothing in the image or in the isolated-tree tests (which set
PYTHONPATH explicitly) can catch it. These tests reproduce the host shape.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_with_only(dir_on_path: Path, module: str) -> subprocess.CompletedProcess:
    """Import `module` with just one directory on sys.path, as the vqa scripts do."""
    code = f"import sys; sys.path.insert(0, {str(dir_on_path)!r}); import {module}"
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd="/",
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},  # no PYTHONPATH
    )


@pytest.mark.parametrize("subdir,module", [
    ("renderer/api", "pipeline"),
    ("mcp", "server"),
])
def test_importable_with_only_its_own_directory_on_the_path(subdir, module):
    r = _import_with_only(REPO_ROOT / subdir, module)
    assert r.returncode == 0, r.stderr
    assert "ModuleNotFoundError" not in r.stderr


def test_the_vqa_helpers_that_import_pipeline_actually_run(tmp_path):
    """make_seed_db is the cheapest end-to-end proof: it imports pipeline for
    the schema and writes a database."""
    db = tmp_path / "seed.db"
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "vqa" / "make_seed_db.py"), str(db)],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
    )
    assert r.returncode == 0, r.stderr
    assert db.exists()


def test_the_guard_leaves_sys_path_alone_when_the_package_already_resolves():
    """In the container PYTHONPATH=/app/lib already provides it. The fallback
    must not fire there, because inserting the repo root would also put an `mcp`
    directory on the path whose name collides with the MCP SDK."""
    code = (
        "import sys; sys.path.insert(0, %r); before=list(sys.path); import pipeline;"
        "added=[p for p in sys.path if p not in before];"
        "print('ADDED:' + ','.join(added))" % str(REPO_ROOT / "renderer" / "api")
    )
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd="/",
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()),
             "PYTHONPATH": str(REPO_ROOT)},
    )
    assert r.returncode == 0, r.stderr
    added = r.stdout.split("ADDED:")[-1].strip()
    assert added == "", f"fallback fired despite PYTHONPATH: added {added!r}"
