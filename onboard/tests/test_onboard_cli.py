"""onboard.py's own argv handling for --install-agent (TMDEV-90).

onboard.py is loaded by path with its venv re-exec and dependency bootstrap
stubbed out: a real main() would create a .venv in the checkout and pip-install
into it before parsing a single flag.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def onboard_main(monkeypatch):
    spec = importlib.util.spec_from_file_location("onboard_entry", REPO_ROOT / "onboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_ensure_venv", lambda: None)
    monkeypatch.setattr(module, "_ensure_deps", lambda: None)

    def run(*args, tty=True):
        monkeypatch.setattr(sys, "argv", ["onboard.py", *args])
        monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
        try:
            module.main()
        except SystemExit as exc:
            return exc.code
        return 0  # the report flags (--list-agents, --status) return normally

    return run


def test_an_unknown_agent_is_refused_with_the_supported_list(onboard_main, capsys):
    assert onboard_main("--install-agent", "openclaw") == 1
    out = capsys.readouterr().out
    assert "Unknown agent: 'openclaw'" in out
    assert "Supported: claude" in out


@pytest.mark.parametrize("args", [("--install-agent",), ("--install-agent", "--dry-run")])
def test_a_missing_agent_name_is_refused(onboard_main, capsys, args):
    assert onboard_main(*args) == 1
    assert "requires an agent name" in capsys.readouterr().out


def test_install_agent_still_needs_a_terminal(onboard_main, capsys):
    """It asks questions, so the non-interactive guard applies to it too."""
    assert onboard_main("--install-agent", "claude", tty=False) == 1
    assert "interactive terminal" in capsys.readouterr().out


def test_install_agent_dispatches_with_the_shared_flags(onboard_main, monkeypatch):
    seen = {}

    def fake(name, **kwargs):
        seen.update(name=name, **kwargs)
        return 0

    monkeypatch.setattr("onboard.agent_install.run_install_agent", fake)
    assert onboard_main("--install-agent", "claude", "--dry-run",
                        "--disable-verification", "--allow-skipping") == 0
    assert seen == {"name": "claude", "dry_run": True, "allow_skipping": True,
                    "verify_keys": False, "full_questionnaire": False}


@pytest.mark.parametrize("args,expected", [
    (("--uninstall-agent", "openclaw"), "Unknown agent: 'openclaw'"),
    (("--uninstall-agent",), "--uninstall-agent requires an agent name"),
    (("--uninstall-agent", "--dry-run"), "--uninstall-agent requires an agent name"),
])
def test_a_bad_uninstall_agent_name_is_refused(onboard_main, capsys, args, expected):
    assert onboard_main(*args) == 1
    assert expected in capsys.readouterr().out


def test_uninstall_agent_needs_a_terminal(onboard_main, capsys):
    """It asks for confirmation before removing anything."""
    assert onboard_main("--uninstall-agent", "claude", tty=False) == 1
    assert "interactive terminal" in capsys.readouterr().out


def test_uninstall_agent_dispatches_with_dry_run(onboard_main, monkeypatch):
    seen = {}
    monkeypatch.setattr("onboard.agent_install.run_uninstall_agent",
                        lambda name, **kw: seen.update(name=name, **kw) or 0)
    assert onboard_main("--uninstall-agent", "claude", "--dry-run") == 0
    assert seen == {"name": "claude", "dry_run": True}


def test_list_agents_is_a_non_interactive_report(onboard_main, monkeypatch):
    """Pipeable like --status: no terminal needed, and nothing else runs."""
    calls = []
    monkeypatch.setattr("onboard.agent_install.print_agents", lambda: calls.append(1))
    monkeypatch.setattr("onboard.plain.run_wizard", lambda **k: pytest.fail("wizard ran"))
    assert onboard_main("--list-agents", tty=False) == 0
    assert calls == [1]


def test_the_poll_log_dir_copies_agree():
    """cron.log (onboard's cron line) and poll.log (poll.py) must land in the
    same directory; the two copies are Keep-in-sync by hand."""
    from onboard.config import POLL_LOG_DIR
    spec = importlib.util.spec_from_file_location("scripts_config",
                                                  REPO_ROOT / "scripts" / "config.py")
    scripts_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scripts_config)
    assert scripts_config.POLL_LOG_DIR == POLL_LOG_DIR


def test_set_password_needs_a_terminal(onboard_main, capsys):
    """It asks for the password twice, hidden."""
    assert onboard_main("--set-password", tty=False) == 1
    assert "interactive terminal" in capsys.readouterr().out


def test_set_password_dispatches(onboard_main, monkeypatch):
    seen = {}
    monkeypatch.setattr("onboard.auth_commands.run_set_password",
                        lambda **kw: seen.update(kw) or 0)
    assert onboard_main("--set-password", "--dry-run") == 0
    assert seen == {"dry_run": True}


def test_rotate_tokens_runs_without_a_terminal(onboard_main, monkeypatch):
    """No question is asked, so cron or a script can run it."""
    seen = {}
    monkeypatch.setattr("onboard.auth_commands.run_rotate_tokens",
                        lambda **kw: seen.update(kw) or 0)
    assert onboard_main("--rotate-tokens", "--force", tty=False) == 0
    assert seen == {"dry_run": False, "force": True}
