"""`/tubematic-install-style` (TMDEV-253): the agent's way to stage a style.

The human yes is the dashboard's. The command must stage and audit, hand over
the link, and never ask for the password or try to confirm.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
CLAUDE = REPO / "agent_files" / "claude" / "commands" / "tubematic-install-style.md"
OPENCODE = REPO / "agent_files" / "opencode" / "commands" / "tubematic-install-style.md"


def _tools() -> set[str]:
    src = (REPO / "mcp" / "server.py").read_text(encoding="utf-8")
    return set(re.findall(r"^@mcp\.tool\n(?:async )?def (\w+)\(", src, re.M))


def test_both_agents_get_the_same_command():
    assert CLAUDE.read_text() == OPENCODE.read_text()


def test_it_stages_audits_and_hands_over_the_link():
    body = CLAUDE.read_text()
    named = set(re.findall(r"tubematic:(\w+)\(", body))
    assert named == {"stage_style_install", "audit_style_install"} and named <= _tools()
    for form in ('"incoming:<name>"', '"git:<https url>@<commit or tag>"', '"gallery:<id>"', "dashboard_link",
                 "~/.tubematic-data/styles-incoming/"):
        assert form in body, form


def test_it_never_asks_for_the_password_or_picks_a_branch():
    body = CLAUDE.read_text()
    assert "Never ask for that password" in body
    assert "never pick a branch" in body
    assert "Never run anything from the package" in body


def test_the_command_list_names_it():
    for agent in ("claude", "opencode"):
        assert "/tubematic-install-style" in (REPO / "agent_files" / agent / "commands" / "tubematic.md").read_text()
