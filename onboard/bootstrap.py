"""Venv + dependency bootstrap shared by every operator entry point.

onboard.py, upgrade.py and scripts/service.py all need the same thing before
they can import anything else: to be running inside <install>/.venv with the
wizard's own dependencies present. One copy, so the three cannot drift.

Stdlib only — this runs before any third-party package can be assumed. It
lives in the package rather than in onboard.py because the `onboard/` package
shadows `onboard.py`, so the script's functions cannot be imported.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensurepip_missing() -> bool:
    """True when this interpreter cannot bootstrap pip into a new venv.

    Debian and Ubuntu ship `venv` with the base interpreter but move pip's
    bootstrap into a separate python3.N-venv package. Without it
    `python3 -m venv` creates the directory, fails at the pip step and leaves
    an interpreter with no pip beside it, so the retry hint has to name that
    package — repeating `python3 -m venv` fails identically.
    """
    try:
        import importlib.util
        return importlib.util.find_spec("ensurepip") is None
    except (ImportError, ValueError):  # a shadowed or broken import system
        return False


def ensure_venv(script: Path) -> None:
    """Re-exec `script` inside REPO_ROOT/.venv if not already running in it.

    Debian/Ubuntu 23.04+ marks the system Python as externally-managed (PEP
    668), so a bare `pip install` fails outside a venv. Doing this first
    means every later pip call targets the venv automatically (via
    sys.executable) — no --break-system-packages needed anywhere.

    Checks specifically for *this project's* .venv, not merely "some venv is
    active" — an unrelated venv already active in the shell (e.g. from
    another tool) must not be trusted as a substitute, since it may not even
    have pip installed (e.g. a `uv venv` skips it by default). Re-execs into
    REPO_ROOT/.venv regardless of what else is active; python -m venv still
    bootstraps a working pip even when invoked from inside a foreign venv,
    since it seeds from that venv's own base interpreter.

    It also matters beyond pip: apply_cron writes sys.executable into the
    cron line, so whichever interpreter runs the cron step is the one every
    poll tick uses. It must be the venv that scripts/requirements.txt was
    installed into.

    Exempt from --dry-run: there is no way to run any of the entry points
    without a working Python environment to install into.
    """
    venv_dir = REPO_ROOT / ".venv"
    venv_python = venv_dir / "bin" / "python3"
    venv_pip = venv_dir / "bin" / "pip3"
    script = Path(script).resolve()

    if Path(sys.prefix).resolve() == venv_dir.resolve():
        return  # already running inside REPO_ROOT/.venv

    # A venv whose pip was never seeded counts as absent, not as ready. A
    # failed ensurepip leaves bin/python3 behind, so keying only on the
    # interpreter made the next run re-exec into a pip-less venv and fail
    # further along, at ensure_deps, with "No module named pip" — the same
    # cause reported as a different problem. Re-running `python -m venv` over
    # it seeds pip once the missing package is installed, so this self-heals.
    if not venv_python.exists() or not venv_pip.exists():
        print(f"  → No virtual environment detected — creating one at {venv_dir}…")
        r = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=False)
        if r.returncode != 0 or not venv_python.exists() or not venv_pip.exists():
            print("  ✘  Failed to create a virtual environment.")
            if _ensurepip_missing():
                print("       pip's bootstrap (ensurepip) is missing — Debian and Ubuntu")
                print("       package it separately. Install it, then run this again:")
                print("         sudo apt install python3-venv")
                print(f"         python3 {script.name} {' '.join(sys.argv[1:])}")
            else:
                print("       Run manually:")
                print(f"         python3 -m venv {venv_dir}")
                print(f"         source {venv_dir}/bin/activate")
                print(f"         python {script.name} {' '.join(sys.argv[1:])}")
            sys.exit(1)
        print(f"  ✔  Virtual environment created at {venv_dir}")

    print("  → Re-running inside the virtual environment…")
    os.execv(str(venv_python), [str(venv_python), str(script)] + sys.argv[1:])


def ensure_deps() -> None:
    """Auto-install the wizard's own runtime deps if missing. Uses stdlib print only.

    rich and questionary render every prompt. httpx is here for the same
    reason, not by association: the `env` step validates each API key against
    its provider as it is typed (onboard/api_keys.py), and `env` runs *before*
    `python_deps` — the step that installs scripts/requirements.txt, where
    httpx otherwise comes from. Without this it would be missing on exactly the
    fresh install where key validation matters most. Nothing extra lands on
    disk: python_deps would have installed it minutes later anyway.

    Exempt from --dry-run for the same reason as ensure_venv above.
    """
    try:
        import rich        # noqa: F401
        import questionary  # noqa: F401
        import httpx        # noqa: F401
    except ImportError:
        print("  → Installing wizard dependencies (rich, questionary, httpx)…")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "rich>=13.7", "questionary>=2.0", "httpx>=0.27.0"],
            check=False,
        )
        if r.returncode != 0:
            print("  ✘  pip install failed. Run manually: pip install rich questionary httpx")
            if _ensurepip_missing():
                print("       This venv has no pip: install Debian/Ubuntu's python3-venv "
                      "package,\n       delete .venv and run this again.")
            sys.exit(1)
        print("  ✔  Wizard dependencies installed.")
