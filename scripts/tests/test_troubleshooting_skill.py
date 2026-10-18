"""The troubleshooting skill is explicit-only on every agent CLI (TMDEV-167).

It tells an agent how to read logs and run the diagnostics collector, so a
scheduled run must never pick it up by itself. Each CLI keeps the switch in a
different place, and each was probed live: Claude Code and OpenCode read the
SKILL.md frontmatter, Codex reads agents/openai.yaml beside it. Losing any one
of them is silent — the skill still works when asked for, so nothing else fails.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-troubleshooting"


def _frontmatter() -> str:
    text = (SKILL / "SKILL.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md has no frontmatter"
    return m.group(1)


def test_claude_code_and_opencode_cannot_invoke_it_by_themselves():
    fm = _frontmatter()
    assert re.search(r"^name: tubematic-troubleshooting$", fm, re.M)
    assert re.search(r"^disable-model-invocation: true$", fm, re.M)
    assert re.search(r'^  opencode/autoinvoke: "false"$', fm, re.M)


def test_codex_cannot_invoke_it_by_itself():
    text = (SKILL / "agents" / "openai.yaml").read_text()
    assert re.search(r"^policy:\n  allow_implicit_invocation: false$", text, re.M)


def test_no_scheduled_prompt_names_it():
    """An explicit-only skill named in a cron prompt would not load — and the
    skill's own rule is to do nothing when started by the poller."""
    for name in ("poll.py", "agent_adapters.py"):
        assert "tubematic-troubleshooting" not in (REPO / "scripts" / name).read_text()


def test_it_never_tells_the_agent_to_read_secrets_or_post():
    body = (SKILL / "SKILL.md").read_text()
    for forbidden in ("gh issue create --", "sqlite3 ", "cat ~/.tubematic-data", "api_token"):
        assert forbidden not in body, forbidden


def test_raw_logs_are_off_limits_and_only_the_report_is_read():
    """Seen live: told to read the poller's log tail, an agent grepped and read
    the whole unredacted file, sending stored keys to its model provider. Logs
    reach the agent only through the redacted report."""
    body = (SKILL / "SKILL.md").read_text()
    rules, _, workflow = body.partition("## 1.")
    assert "~/.tubematic-agent/logs/" in rules and "~/.tubematic-data/" in rules
    assert "poll.log" not in workflow and ".tubematic-agent/logs" not in workflow
    assert "docker logs" not in workflow and "docker compose logs" not in workflow
