"""scripts/agent_adapters.py — the argv shapes are pinned exactly.

The Claude CLI treats an unrecognised subcommand as a *prompt*, so a malformed
verification command silently becomes a billed model call instead of an error.
Every argv the installer or poller builds is therefore asserted verbatim here.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import agent_adapters
from agent_adapters import McpAuth
from agent_adapters import (ADAPTERS, AGENT_EFFORTS, ClaudeAdapter, CodexAdapter,
                            OpenCodeAdapter, jsonc_has_comments, parse_jsonc,
                            remove_jsonc_member)


def test_every_agent_is_supported():
    assert set(ADAPTERS) == {"claude", "codex", "opencode"}
    assert ADAPTERS["claude"] is ClaudeAdapter
    assert ADAPTERS["codex"] is CodexAdapter
    assert ADAPTERS["opencode"] is OpenCodeAdapter


def test_build_argv_shapes():
    assert ClaudeAdapter.build_argv("/b/claude", "hi") == ["/b/claude", "-p", "hi", "--output-format", "json"]
    assert ClaudeAdapter.build_argv("/b/claude", "hi", "opus") == \
        ["/b/claude", "-p", "hi", "--output-format", "json", "--model", "opus"]
    assert ClaudeAdapter.build_argv("/b/claude", "hi", "opus", "max") == \
        ["/b/claude", "-p", "hi", "--output-format", "json", "--model", "opus", "--effort", "max"]
    # Effort without a model: --model must not appear as an empty pair.
    assert ClaudeAdapter.build_argv("/b/claude", "hi", "", "low") == \
        ["/b/claude", "-p", "hi", "--output-format", "json", "--effort", "low"]


def test_auth_status_argv_is_exact():
    assert ClaudeAdapter.auth_status_argv("/b/claude") == \
        ["/b/claude", "auth", "status", "--json"]


def test_probe_argv_is_exact():
    assert ClaudeAdapter.probe_argv("/b/claude", "sonnet") == \
        ["/b/claude", "-p", "ok", "--output-format", "json", "--model", "sonnet"]
    assert ClaudeAdapter.probe_argv("/b/claude", "", "high") == \
        ["/b/claude", "-p", "ok", "--output-format", "json", "--effort", "high"]


@pytest.mark.parametrize("stdout,expected", [
    ('{"loggedIn": true, "authMethod": "claude.ai"}', True),
    ('{"loggedIn": false}', False),
    ('{}', False),
    ('not json', False),
    ('["a list"]', False),
    ('', False),
])
def test_logged_in_reads_only_a_real_true(stdout, expected):
    assert ClaudeAdapter.logged_in(stdout) is expected


@pytest.mark.parametrize("output,expected", [
    ("[claude-code:unrecognized_model] {...}", True),
    ("It may not exist or you may not have access to it.", True),
    ("ok", False),
    ("", False),
    (None, False),
])
def test_model_rejected(output, expected):
    assert ClaudeAdapter.model_rejected(output) is expected


def test_suggest_models_filters_the_catalog(tmp_path):
    fake = tmp_path / "claude-bin"
    fake.write_bytes(
        b"\x00junk claude-opus-5\x00claude-sonnet-4-5-20250929\x00claude-opus-4-5-20251101-v1"
        b"\x00claude-fable-5-mythos-5\x00claude-haiku-4-5\x00claude-opus-5\x00not-a-model")
    assert ClaudeAdapter.suggest_models(str(fake)) == [
        "claude-haiku-4-5", "claude-opus-5", "claude-sonnet-4-5-20250929",
    ]


def test_suggest_models_follows_a_symlink_to_the_real_binary(tmp_path):
    """~/.local/bin/claude is a symlink into the versioned install."""
    real = tmp_path / "2.1.267"
    real.write_bytes(b"claude-opus-5")
    link = tmp_path / "claude"
    link.symlink_to(real)
    assert ClaudeAdapter.suggest_models(str(link)) == ["claude-opus-5"]


def test_suggest_models_never_raises(tmp_path):
    """Suggest only, never gate: a missing binary is an empty list."""
    assert ClaudeAdapter.suggest_models(str(tmp_path / "missing")) == []


# ── Effort (TMDEV-106) ──────────────────────────────────────────────────────

def test_the_effort_levels_are_the_documented_five():
    assert ClaudeAdapter.EFFORTS == ("low", "medium", "high", "xhigh", "max")
    assert ClaudeAdapter.DEFAULT_EFFORT == "high"
    assert ClaudeAdapter.DEFAULT_EFFORT in ClaudeAdapter.EFFORTS


# Verbatim from the installed CLI (2.1.278), which is where the matcher's
# three conditions come from — see ClaudeAdapter.effort_rejected.
_UNKNOWN_FLAG = "error: unknown option '--effort'\n"
_BAD_VALUE = ("Warning: Unknown --effort value 'nope' — ignoring it and using the default "
              "effort. Valid values: low, medium, high, xhigh, max.\n")


def test_an_unknown_effort_flag_is_a_rejection():
    assert ClaudeAdapter.effort_rejected(_UNKNOWN_FLAG, 1) is True


def test_a_bad_effort_value_is_not_a_rejection():
    """It exits 0 having done the work, at the CLI's own default effort.

    Re-running that would be a second billed session for nothing.
    """
    assert ClaudeAdapter.effort_rejected(_BAD_VALUE, 0) is False


def test_an_unknown_other_flag_is_not_an_effort_rejection():
    assert ClaudeAdapter.effort_rejected("error: unknown option '--verbose'\n", 1) is False


def test_a_zero_exit_is_never_a_rejection():
    """The whole point of falling back is that the run did nothing. An exit-0
    run did something, whatever its output says."""
    assert ClaudeAdapter.effort_rejected(_UNKNOWN_FLAG, 0) is False


def test_an_ordinary_crash_is_not_an_effort_rejection():
    assert ClaudeAdapter.effort_rejected("Traceback: boom\n", 1) is False
    assert ClaudeAdapter.effort_rejected("", 137) is False
    assert ClaudeAdapter.effort_rejected(None, 1) is False


# ── Codex ────────────────────────────────────────────────────────────────────

def test_codex_build_argv_shapes():
    # `--` is mandatory, not decoration: `codex exec` has subcommands, and a
    # prompt of exactly "resume" is otherwise parsed as `codex exec resume`.
    assert CodexAdapter.build_argv("/b/codex", "hi") == \
        ["/b/codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
         "-c", 'approvals_reviewer="auto_review"', "--", "hi"]
    assert CodexAdapter.build_argv("/b/codex", "hi", "gpt-5.6-sol") == \
        ["/b/codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
         "-c", 'approvals_reviewer="auto_review"', "-m", "gpt-5.6-sol", "--", "hi"]
    assert CodexAdapter.build_argv("/b/codex", "hi", "gpt-5.6-sol", "max") == \
        ["/b/codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
         "-c", 'approvals_reviewer="auto_review"', "-m", "gpt-5.6-sol",
         "-c", "model_reasoning_effort=max", "--", "hi"]
    assert CodexAdapter.build_argv("/b/codex", "hi", "", "low") == \
        ["/b/codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
         "-c", 'approvals_reviewer="auto_review"', "-c", "model_reasoning_effort=low",
         "--", "hi"]


def test_codex_prompt_is_always_last_and_after_the_separator():
    argv = CodexAdapter.build_argv("/b/codex", "--not-a-flag", "m", "high")
    assert argv[-2:] == ["--", "--not-a-flag"]


def test_codex_auth_status_argv_is_exact():
    assert CodexAdapter.auth_status_argv("/b/codex") == ["/b/codex", "login", "status"]


def test_codex_probe_argv_is_exact():
    assert CodexAdapter.probe_argv("/b/codex", "gpt-5.6-sol") == \
        ["/b/codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
         "-c", 'approvals_reviewer="auto_review"', "-m", "gpt-5.6-sol", "--", "ok"]


@pytest.mark.parametrize("stderr,rc,expected", [
    ("Logged in using ChatGPT\n", 0, True),
    ("Logged in using an API key\n", 0, True),
    ("Not logged in\n", 1, False),       # must not match — capital L, startswith
    ("Logged in using ChatGPT\n", 1, False),   # affirmative text, failed exit
    ("", 0, False),
    ("   ", 0, False),
    (None, 0, False),
])
def test_codex_logged_in_reads_the_real_wordings(stderr, rc, expected):
    """The status line arrives on STDERR — probed live. Reading stdout alone
    sees an empty string and reports every logged-in CLI as logged out, which
    blocks the install outright."""
    assert CodexAdapter.logged_in("", stderr, rc) is expected


def test_codex_logged_in_reads_either_stream():
    """The live CLI answers on stderr, which is the defect this signature was
    widened to fix. Both streams are read rather than just that one, so a
    future release that moves the line to stdout does not silently block every
    install; the exit code is what actually decides."""
    assert CodexAdapter.logged_in("", "Logged in using ChatGPT\n", 0) is True
    assert CodexAdapter.logged_in("Logged in using ChatGPT\n", "", 0) is True


def test_claude_logged_in_still_takes_one_argument():
    """Widening the signature must not change Claude's call shape."""
    assert ClaudeAdapter.logged_in('{"loggedIn": true}') is True
    assert ClaudeAdapter.logged_in('{"loggedIn": true}', "noise", 0) is True


# Verbatim from live runs against codex-cli 0.155.1 under each auth mode. The
# API-key transcript is the reason both are needed: its wording shares nothing
# with the ChatGPT one, so matching only the latter leaves an API-key install
# with no rejected-model fallback at all.
_CHATGPT_REJECT = ('ERROR: {"message":"The \'x\' model is not supported when using Codex '
                   'with a ChatGPT account."}')
_APIKEY_REJECT = ("ERROR: unexpected status 404 Not Found: The model `x` does not exist or "
                  "you do not have access to it., url: https://api.openai.com/v1/responses")
# Printed for models the API then ACCEPTS, and printed directly beside the real
# rejection in the API-key transcript — which is how it would get swept in.
_BENIGN_METADATA = ("warning: Model metadata for `gpt-9` not found. Defaulting to fallback "
                    "metadata; this can degrade performance and cause issues.")


@pytest.mark.parametrize("output,expected", [
    (_CHATGPT_REJECT, True),
    (_APIKEY_REJECT, True),
    (_BENIGN_METADATA, False),
    ("Logged in using ChatGPT", False),
    ("", False),
    (None, False),
])
def test_codex_model_rejected_under_both_auth_modes(output, expected):
    assert CodexAdapter.model_rejected(output, 1) is expected


def test_the_benign_metadata_warning_never_counts_even_beside_a_real_rejection():
    """Both lines appear in one API-key transcript. The rejection must win on
    its own terms, and the warning alone must never be enough."""
    assert CodexAdapter.model_rejected(_BENIGN_METADATA, 1) is False
    assert CodexAdapter.model_rejected(f"{_BENIGN_METADATA}\n{_APIKEY_REJECT}", 1) is True


def test_a_successful_codex_run_is_never_a_model_rejection():
    """The API-key marker is an ordinary English sentence that a working run
    could easily produce — an agent reporting a missing file, or quoting an
    error out of a log. Both real rejections exit non-zero, so requiring
    failure costs nothing and stops a good run being repeated at full price."""
    assert CodexAdapter.model_rejected(_APIKEY_REJECT, 0) is False
    assert CodexAdapter.model_rejected(_CHATGPT_REJECT, 0) is False


def test_claude_model_rejection_stays_exit_code_independent():
    """The opposite requirement, and the reason this is per-adapter: the Claude
    CLI exits 0 on an unknown model, so demanding failure would detect none."""
    assert ClaudeAdapter.model_rejected("[claude-code:unrecognized_model]", 0) is True


# Verbatim from `-m gpt-5.5 -c model_reasoning_effort=max`: the shared five
# levels are NOT all supported by every catalog model (gpt-5.5 stops at xhigh),
# so this is reachable through ordinary configuration, not a typo.
_EFFORT_UNSUPPORTED_FOR_MODEL = (
    '{"error": {"code": "unsupported_value", "message": "Unsupported value: \'max\' is not '
    "supported with the 'gpt-5.5' model. Supported values are: 'none', 'low', 'medium', "
    '\'high\', and \'xhigh\'.", "param": "reasoning.effort"}, "status": 400}')
_EFFORT_BAD_VALUE = ("[ReasoningEffortParam] [reasoning.effort] [invalid_enum_value] Invalid "
                     "value: 'bogus'.")


def test_codex_rejects_an_effort_its_model_cannot_use():
    """Codex cannot reject the effort *flag*, but the API rejects a level the
    chosen model does not support — and without this the poller would never
    retry, so every tick for that model/effort pair would do nothing."""
    assert CodexAdapter.effort_rejected(_EFFORT_UNSUPPORTED_FOR_MODEL, 1) is True
    assert CodexAdapter.effort_rejected(_EFFORT_BAD_VALUE, 1) is True


def test_a_zero_exit_is_never_an_effort_rejection_for_codex():
    """The point of retrying is that the run did nothing."""
    assert CodexAdapter.effort_rejected(_EFFORT_UNSUPPORTED_FOR_MODEL, 0) is False


def test_an_unrelated_codex_crash_is_not_an_effort_rejection():
    assert CodexAdapter.effort_rejected("Traceback: boom", 1) is False
    assert CodexAdapter.effort_rejected("error: unknown option '--effort'", 1) is False
    assert CodexAdapter.effort_rejected(None, 1) is False


def test_codexs_effort_probe_needs_a_model_to_mean_anything():
    """Its rejection depends on the model/effort pair, so onboarding must not
    spend a billed model-less run that could never produce a verdict."""
    assert CodexAdapter.PROBES_EFFORT_WITHOUT_A_MODEL is False
    assert ClaudeAdapter.PROBES_EFFORT_WITHOUT_A_MODEL is True


def test_every_adapter_offers_the_same_effort_levels():
    """Pinned because AGENT_EFFORTS is hand-duplicated into the Flask API, the
    MCP server and the dashboard. A per-agent tuple would silently desync them."""
    for adapter in ADAPTERS.values():
        assert adapter.EFFORTS == AGENT_EFFORTS
        assert adapter.DEFAULT_EFFORT in AGENT_EFFORTS


def test_codex_has_no_aliases():
    """`codex exec -m` takes catalog slugs only; there is no `opus`/`sonnet`
    equivalent, so the install prompt must offer the catalog and nothing else."""
    assert CodexAdapter.ALIASES == ()


def _cache(tmp_path, payload):
    (tmp_path / "models_cache.json").write_text(json.dumps(payload))
    return tmp_path


def test_codex_suggest_models_reads_the_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(_cache(tmp_path, {"models": [
        {"slug": "gpt-5.6-sol", "visibility": "list"},
        {"slug": "gpt-6-astra", "visibility": "list"},
    ]})))
    assert CodexAdapter.suggest_models("/b/codex") == ["gpt-5.6-sol", "gpt-6-astra"]


def test_codex_never_suggests_an_internal_model(tmp_path, monkeypatch):
    """The live catalog marks internal entries `visibility: "hide"` and has no
    `hidden` key at all, so a truthiness test on `hidden` filtered nothing and
    offered gpt-reserve and codex-auto-review for selection."""
    monkeypatch.setenv("CODEX_HOME", str(_cache(tmp_path, {"models": [
        {"slug": "gpt-5.6-sol", "visibility": "list"},
        {"slug": "gpt-reserve", "visibility": "hide"},
        {"slug": "codex-auto-review", "visibility": "hide"},
        {"slug": "no-visibility-field-at-all"},
    ]})))
    assert CodexAdapter.suggest_models("/b/codex") == ["gpt-5.6-sol"]


def test_codex_suggest_models_defaults_to_the_home_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(agent_adapters.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".codex").mkdir()
    _cache(tmp_path / ".codex", {"models": [{"slug": "gpt-5.6-sol", "visibility": "list"}]})
    assert CodexAdapter.suggest_models("/b/codex") == ["gpt-5.6-sol"]


@pytest.mark.parametrize("payload", ["not json", '{"models": "nope"}', '{}', '[]'])
def test_codex_suggest_models_never_raises(tmp_path, monkeypatch, payload):
    """Suggest only, never gate — this reads a cache file the CLI owns and may
    reshape on any release. Any failure means a plain free-text prompt."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "models_cache.json").write_text(payload)
    assert CodexAdapter.suggest_models("/b/codex") == []


def test_codex_suggest_models_survives_a_missing_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nope"))
    assert CodexAdapter.suggest_models("/b/codex") == []


# ── Deployment layout ────────────────────────────────────────────────────────

def test_claude_deployment_layout_is_unchanged():
    home, ws = Path("/home/u"), Path("/srv/ws")
    assert ClaudeAdapter.SUPPORTED_SCOPES == ("user", "project")
    assert ClaudeAdapter.NEEDS_ALLOWLIST is True
    assert ClaudeAdapter.COPIES_SKILLS_INTO_WORKSPACE is True
    assert ClaudeAdapter.HAS_COMMANDS is True
    assert ClaudeAdapter.REMOTION_AGENT_FLAG == "claude-code"
    assert ClaudeAdapter.user_skills_dir(home) == home / ".claude" / "skills"
    assert ClaudeAdapter.user_commands_dir(home) == home / ".claude" / "commands"
    assert ClaudeAdapter.project_skills_dir(ws) == ws / ".claude" / "skills"
    assert ClaudeAdapter.project_commands_dir(ws) == ws / ".claude" / "commands"
    entry = json.dumps({"type": "http", "url": "http://h/mcp", "headersHelper": AUTH.helper})
    assert ClaudeAdapter.mcp_add_argv("/b/claude", "user", "http://h/mcp", AUTH) == \
        ["/b/claude", "mcp", "add-json", "--scope", "user", "tubematic", entry]
    assert ClaudeAdapter.mcp_add_argv("/b/claude", "project", "http://h/mcp", AUTH) == \
        ["/b/claude", "mcp", "add-json", "tubematic", entry]
    # Probed: `claude mcp add` refuses an existing name, so a redeploy removes first.
    assert ClaudeAdapter.MCP_ADD_REPLACES is False
    assert ClaudeAdapter.mcp_remove_argv("/b/claude", "user") == \
        ["/b/claude", "mcp", "remove", "--scope", "user", "tubematic"]
    assert ClaudeAdapter.mcp_remove_argv("/b/claude", "project") == \
        ["/b/claude", "mcp", "remove", "tubematic"]


def test_codex_deployment_layout():
    home, ws = Path("/home/u"), Path("/srv/ws")
    assert CodexAdapter.SUPPORTED_SCOPES == ("user",)
    assert CodexAdapter.NEEDS_ALLOWLIST is False
    assert CodexAdapter.COPIES_SKILLS_INTO_WORKSPACE is False
    assert CodexAdapter.HAS_COMMANDS is False
    assert CodexAdapter.REMOTION_AGENT_FLAG == "codex"
    assert CodexAdapter.user_skills_dir(home) == home / ".codex" / "skills"
    assert CodexAdapter.user_commands_dir(home) is None
    assert CodexAdapter.project_commands_dir(ws) is None


def test_codex_mcp_argv_ignores_scope_because_codex_has_none():
    """`codex mcp add` has no --scope flag; registration is always global."""
    for scope in ("user", "project"):
        assert CodexAdapter.mcp_add_argv("/b/codex", scope, "http://h/mcp", AUTH) == \
            ["/b/codex", "mcp", "add", "tubematic", "--url", "http://h/mcp"]
        assert CodexAdapter.mcp_remove_argv("/b/codex", scope) == \
            ["/b/codex", "mcp", "remove", "tubematic"]


def test_an_agent_with_one_scope_declares_it_first():
    """deploy() and the questionnaire both take SUPPORTED_SCOPES[0] as the
    value to store when the scope question is not asked."""
    for adapter in ADAPTERS.values():
        assert adapter.SUPPORTED_SCOPES[0] == "user"


def test_no_adapter_promises_commands_it_does_not_ship():
    """HAS_COMMANDS must agree with agent_files/<agent>/commands/ on disk — a
    True with no directory deploys nothing and warns on every install."""
    root = Path(__file__).resolve().parents[2] / "agent_files"
    for adapter in ADAPTERS.values():
        assert adapter.HAS_COMMANDS == (root / adapter.name / "commands").is_dir()


def test_every_agent_with_commands_ships_the_same_set():
    """The command files are hand-duplicated per agent, because two of them name
    the agent's own CLI. The BODIES may differ; the set must not, or a command
    added for one agent silently does not exist for the other."""
    root = Path(__file__).resolve().parents[2] / "agent_files"
    sets = {a.name: sorted(f.name for f in (root / a.name / "commands").glob("*.md"))
            for a in ADAPTERS.values() if a.HAS_COMMANDS}
    assert len(set(map(tuple, sets.values()))) == 1, sets
    assert sets["claude"], "no command files found at all"


def test_no_agents_commands_tell_the_user_to_run_another_agents_cli():
    """A command that says `claude mcp list` is wrong instruction inside
    OpenCode — following it would not touch that install at all."""
    root = Path(__file__).resolve().parents[2] / "agent_files"
    others = {a.binary_name for a in ADAPTERS.values()}
    offenders = []
    for adapter in ADAPTERS.values():
        if not adapter.HAS_COMMANDS:
            continue
        for path in sorted((root / adapter.name / "commands").glob("*.md")):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                for other in others - {adapter.binary_name}:
                    if f"{other} mcp " in line:
                        offenders.append(f"{path.name}:{n} ({adapter.name} says '{other} mcp')")
    assert offenders == [], offenders


def test_no_command_tells_an_agent_to_run_a_tool_its_install_denies():
    """A denied tool in OpenCode cannot be approved interactively the way an
    unlisted Claude tool can — the install's `shell: deny` is absolute inside
    the agent workspace, which is the directory the install points people at.
    A command that simply says `docker compose ps` is therefore dead there.

    Pinned as prose rather than by parsing commands, because the same words are
    legitimate when they are addressed to the *human*: any command file that
    names a shell command must also say that the agent itself cannot run one.
    """
    root = Path(__file__).resolve().parents[2] / "agent_files"
    offenders = []
    for adapter in ADAPTERS.values():
        denied = {r["action"] for r in getattr(adapter, "PERMISSION_RULES", ())
                  if r["effect"] == "deny"}
        if not adapter.HAS_COMMANDS or "shell" not in denied:
            continue
        for path in sorted((root / adapter.name / "commands").glob("*.md")):
            text = path.read_text()
            names_a_command = "docker compose" in text or "curl " in text
            if names_a_command and "`shell`" not in text:
                offenders.append(f"{adapter.name}/{path.name}")
    assert offenders == [], offenders


def test_each_agent_names_a_login_command_that_exists():
    """`codex auth login` does not exist — the hint used to be built from the
    binary name plus Claude's subcommand, so it told a Codex user to run a
    command that would fail."""
    assert ClaudeAdapter.LOGIN_HINT == "run `claude` once interactively (or `claude auth login`)"
    assert CodexAdapter.LOGIN_HINT == "run `codex login` (a browser/device flow)"
    for adapter in ADAPTERS.values():
        assert adapter.binary_name in adapter.LOGIN_HINT


def test_codex_always_routes_approvals_to_the_auto_reviewer():
    """Without this, MCP tools are unusable and the failure is silent.

    `codex exec` defaults its approval policy to Never, and an MCP tool call
    under Never is refused ("MCP tool call requires approval, but approval
    policy is never") while the process still exits 0. Every pipeline action
    goes through MCP, so a run would do nothing and look healthy. Verified in
    a clean container both ways; a developer's own ~/.codex/config.toml can
    hide it by already setting a reviewer.
    """
    for argv in (CodexAdapter.build_argv("/b/codex", "hi"),
                 CodexAdapter.build_argv("/b/codex", "hi", "m", "high"),
                 CodexAdapter.probe_argv("/b/codex", "m")):
        assert "-c" in argv
        assert 'approvals_reviewer="auto_review"' in argv
    # Never the blunt instrument: this project rejects bypass flags.
    assert not any("dangerously" in part
                   for part in CodexAdapter.build_argv("/b/codex", "hi"))


def test_codex_reads_one_config_root_for_both_the_catalog_and_its_skills(tmp_path, monkeypatch):
    """They used to disagree: the catalog honoured CODEX_HOME while skills
    always went to ~/.codex, so an install run with CODEX_HOME set deployed
    its skills where that Codex would never look."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "custom"))
    assert CodexAdapter.config_home() == tmp_path / "custom"
    assert CodexAdapter.user_skills_dir(Path("/home/u")) == tmp_path / "custom" / "skills"
    _cache((tmp_path / "custom"), {"models": [{"slug": "m", "visibility": "list"}]}) \
        if (tmp_path / "custom").mkdir(parents=True, exist_ok=True) is None else None
    assert CodexAdapter.suggest_models("/b/codex") == ["m"]


def test_codex_falls_back_to_the_home_directory_with_no_override(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert CodexAdapter.user_skills_dir(tmp_path) == tmp_path / ".codex" / "skills"


def test_the_help_text_lists_exactly_the_supported_agents():
    """Two help strings name the agents literally rather than deriving them,
    so a third adapter would leave them quietly wrong. This is the check that
    makes the literal safe."""
    root = Path(__file__).resolve().parents[2]
    expected = ", ".join(sorted(ADAPTERS))
    for rel in ("onboard.py", "onboard/plain.py"):
        text = (root / rel).read_text()
        assert f"supported: {expected}" in text, f"{rel} does not say 'supported: {expected}'"


def test_no_user_facing_hint_hardcodes_one_agent():
    """A hint that names one agent is wrong instruction on an install running
    the other — following it would not touch that install at all."""
    root = Path(__file__).resolve().parents[2]
    offenders = []
    for rel in ("scripts/poll.py", "upgrade.py", "onboard/checks.py", "onboard/plain.py",
                "onboard/agent_install.py", "renderer/api/pipeline.py", "mcp/server.py"):
        for n, line in enumerate((root / rel).read_text().splitlines(), 1):
            if "--install-agent claude" in line or "--uninstall-agent claude" in line:
                offenders.append(f"{rel}:{n}")
    assert offenders == [], offenders


# ── OpenCode ────────────────────────────────────────────────────────────────
# Every assertion below quotes output probed live against @opencode/cli 2.0.14
# in a clean container with no credentials.

def test_opencode_build_argv_shapes():
    assert OpenCodeAdapter.build_argv("/b/opencode", "hi") == \
        ["/b/opencode", "run", "--auto", "--format", "json", "--", "hi"]
    assert OpenCodeAdapter.build_argv("/b/opencode", "hi", "anthropic/claude-sonnet-4-5") == \
        ["/b/opencode", "run", "--auto", "--format", "json", "--model", "anthropic/claude-sonnet-4-5", "--", "hi"]


def test_opencode_effort_is_a_variant_of_the_model_not_a_flag():
    """OpenCode has no --effort. The level is a `#variant` on the model, which
    is also why it cannot be sent without one — and that is what keeps poll.py's
    fallback ladder finite: dropping the model necessarily drops the effort."""
    assert OpenCodeAdapter.build_argv("/b/opencode", "hi", "openai/gpt-5.2", "high") == \
        ["/b/opencode", "run", "--auto", "--format", "json", "--model", "openai/gpt-5.2#high", "--", "hi"]
    assert "high" not in OpenCodeAdapter.build_argv("/b/opencode", "hi", "", "high")
    assert OpenCodeAdapter.build_argv("/b/opencode", "hi", "", "high") == \
        ["/b/opencode", "run", "--auto", "--format", "json", "--", "hi"]


def test_opencode_always_passes_the_separator_before_the_prompt():
    """A prompt beginning with a dash would otherwise be parsed as a flag."""
    for argv in (OpenCodeAdapter.build_argv("/b/opencode", "-p"),
                 OpenCodeAdapter.build_argv("/b/opencode", "-p", "m", "low"),
                 OpenCodeAdapter.probe_argv("/b/opencode", "m", "low")):
        assert argv[-2:] == ["--", argv[-1]]


def test_opencode_always_auto_approves_and_never_bypasses():
    """--auto is what makes an unattended run possible: an `ask` in a
    non-interactive `opencode run` is auto-REJECTED and takes the whole session
    down (`Session interrupted: shutdown`, exit 1, nothing done). It is not a
    blanket bypass — a configured deny still holds under it — and the adapter
    must never reach for a real bypass flag instead."""
    for argv in (OpenCodeAdapter.build_argv("/b/opencode", "hi"),
                 OpenCodeAdapter.build_argv("/b/opencode", "hi", "m", "max"),
                 OpenCodeAdapter.probe_argv("/b/opencode", "m")):
        assert "--auto" in argv
        assert not any("dangerous" in part for part in argv)


def test_opencode_auth_status_argv_is_exact():
    assert OpenCodeAdapter.auth_status_argv("/b/opencode") == ["/b/opencode", "auth", "list"]


@pytest.mark.parametrize("stdout, rc, expected", [
    # Probed: a logged-OUT CLI exits 0 and prints this on stdout.
    ("No authenticated integrations", 0, False),
    ("anthropic  oauth  (active)", 0, True),
    ("", 0, False),
    ("anthropic  oauth  (active)", 1, False),
])
def test_opencode_logged_in_cannot_lean_on_the_exit_code(stdout, rc, expected):
    """`opencode auth list` exits 0 whether or not anything is authenticated,
    so the negative phrase is the only signal there is. Empty output counts as
    logged out — a CLI that printed nothing must not pass."""
    assert OpenCodeAdapter.logged_in(stdout, "", rc) is expected


@pytest.mark.parametrize("output, rc, expected", [
    ("Error: Model unavailable: bogus/bogus", 1, True),
    ("Error: Model unavailable: bogus/bogus", 0, False),
    ("Error: connection reset", 1, False),
])
def test_opencode_model_rejection_requires_a_failed_run(output, rc, expected):
    """The marker is ordinary English that a successful session could quote out
    of a log; without the exit check such a run would be repeated on the CLI
    default, doubling the work and the bill."""
    assert OpenCodeAdapter.model_rejected(output, rc) is expected


def test_opencode_tells_a_missing_variant_apart_from_a_missing_model():
    """Unlike Codex's, OpenCode's two rejections are distinguishable, which is
    worth real money: an unusable effort costs one retry with the chosen model
    KEPT, instead of throwing the model away too."""
    variant = "Error: Variant unavailable for openai/gpt-5.2: definitelynotavariant"
    model = "Error: Model unavailable: bogus/bogus"
    assert OpenCodeAdapter.effort_rejected(variant, 1) is True
    assert OpenCodeAdapter.model_rejected(variant, 1) is False
    assert OpenCodeAdapter.effort_rejected(model, 1) is False
    assert OpenCodeAdapter.model_rejected(model, 1) is True


def test_a_zero_exit_is_never_an_effort_rejection_for_opencode():
    assert OpenCodeAdapter.effort_rejected("Error: Variant unavailable for x: y", 0) is False


def test_opencodes_effort_probe_needs_a_model_to_mean_anything():
    """The rejection depends on the model/variant pair, so a model-less probe
    would be a billed run that could never produce a verdict."""
    assert OpenCodeAdapter.PROBES_EFFORT_WITHOUT_A_MODEL is False


def test_opencode_has_no_aliases():
    """`opencode run --model` takes provider/model slugs; there is no stable
    shorthand to lead the install prompt with."""
    assert OpenCodeAdapter.ALIASES == ()


def _models_output(monkeypatch, stdout, returncode=0, boom=None):
    import types

    def fake_run(cmd, **kw):
        if boom:
            raise boom
        assert cmd == ["/b/opencode", "models"]
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(agent_adapters.subprocess, "run", fake_run)


def test_opencode_suggest_models_reads_the_models_command(monkeypatch):
    _models_output(monkeypatch, "anthropic/claude-sonnet-4-5\nopencode/gpt-5.5\n")
    assert OpenCodeAdapter.suggest_models("/b/opencode") == \
        ["anthropic/claude-sonnet-4-5", "opencode/gpt-5.5"]


def test_a_vendor_namespaced_slug_is_suggested(monkeypatch):
    """Some providers namespace by vendor as well, so a slug can carry more
    than one `/`. Requiring exactly two segments dropped every OpenRouter model
    from the suggestions while `opencode models` listed them — silently,
    because a dropped line is indistinguishable from a header line that was
    meant to be dropped."""
    _models_output(monkeypatch, "openrouter/qwen/qwen3.8-27b\n"
                                "openrouter/meta-llama/llama-4-70b\n"
                                "anthropic/claude-sonnet-4-5\n")
    assert OpenCodeAdapter.suggest_models("/b/opencode") == [
        "openrouter/qwen/qwen3.8-27b",
        "openrouter/meta-llama/llama-4-70b",
        "anthropic/claude-sonnet-4-5",
    ]


@pytest.mark.parametrize("line", ["* anthropic/x", "-anthropic/x", "/leading", "trailing/"])
def test_a_decorated_or_malformed_line_is_still_dropped(monkeypatch, line):
    """Widening the pattern must not turn the filter into a pass-through: each
    segment still has to start alphanumeric, so nothing `_agent_model` would
    reject at the prompt can be offered as a suggestion."""
    _models_output(monkeypatch, line + "\n")
    assert OpenCodeAdapter.suggest_models("/b/opencode") == []


@pytest.mark.parametrize("stdout", ["Available models:\nnot-a-slug\n", "", "   \n"])
def test_opencode_suggest_models_drops_anything_that_is_not_a_slug(monkeypatch, stdout):
    """Suggest-only: offering too few names degrades to free text, while
    offering a header line invites storing one as a model."""
    _models_output(monkeypatch, stdout)
    assert OpenCodeAdapter.suggest_models("/b/opencode") == []


def test_opencode_suggest_models_never_raises(monkeypatch):
    _models_output(monkeypatch, "", returncode=1)
    assert OpenCodeAdapter.suggest_models("/b/opencode") == []
    _models_output(monkeypatch, "", boom=OSError("no such binary"))
    assert OpenCodeAdapter.suggest_models("/b/opencode") == []


def test_opencode_deployment_layout(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cfg = tmp_path / ".config" / "opencode"
    assert OpenCodeAdapter.user_skills_dir(tmp_path) == cfg / "skills"
    assert OpenCodeAdapter.user_commands_dir(tmp_path) == cfg / "commands"
    assert OpenCodeAdapter.config_file(tmp_path) == cfg / "opencode.json"
    ws = tmp_path / "ws"
    assert OpenCodeAdapter.project_skills_dir(ws) == ws / ".opencode" / "skills"
    assert OpenCodeAdapter.project_commands_dir(ws) == ws / ".opencode" / "commands"
    # Not .opencode/opencode.json: that is where `opencode mcp add` writes a
    # project registration, so a scope's whole config stays one file.
    assert OpenCodeAdapter.workspace_config_file(ws) == ws / "opencode.json"
    assert OpenCodeAdapter.SUPPORTED_SCOPES == ("user", "project")
    assert OpenCodeAdapter.NEEDS_ALLOWLIST is False
    assert OpenCodeAdapter.NEEDS_PERMISSION_CONFIG is True
    assert OpenCodeAdapter.COPIES_SKILLS_INTO_WORKSPACE is False


def test_opencode_honours_xdg_config_home_except_for_scheduled_runs(tmp_path, monkeypatch):
    """cron strips the environment to HOME/LOGNAME/PATH/SHELL, so a read-only
    diagnostic must be able to ask for the root a scheduled run will use."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "elsewhere"))
    assert OpenCodeAdapter.user_skills_dir(tmp_path) == tmp_path / "elsewhere" / "opencode" / "skills"
    assert OpenCodeAdapter.user_skills_dir(tmp_path, respect_override=False) == \
        tmp_path / ".config" / "opencode" / "skills"


def test_opencode_mcp_argv_uses_global_only_for_user_scope():
    header = "Authorization=Bearer {file:/h/.tubematic-data/secrets/mcp_token}"
    assert OpenCodeAdapter.mcp_add_argv("/b/opencode", "user", "http://x/mcp", AUTH) == \
        ["/b/opencode", "mcp", "add", "tubematic", "--global", "--url", "http://x/mcp",
         "--header", header]
    assert OpenCodeAdapter.mcp_add_argv("/b/opencode", "project", "http://x/mcp", AUTH) == \
        ["/b/opencode", "mcp", "add", "tubematic", "--url", "http://x/mcp", "--header", header]


def test_opencode_has_no_mcp_remove_command(tmp_path):
    """Probed: `opencode mcp` offers list, add, auth and logout only. Returning
    None rather than an argv that does not exist is what stops an uninstall
    reporting success for a command that never ran."""
    assert OpenCodeAdapter.mcp_remove_argv("/b/opencode", "user") is None
    home, ws = tmp_path, tmp_path / "ws"
    assert OpenCodeAdapter.mcp_config_file(home, ws, "project") == ws / "opencode.json"


def test_the_rules_assert_what_the_pipeline_needs_not_only_what_it_may_not_do():
    """Deny-only is not enough. Permissions resolve last-match-wins across
    every merged document, so an action this list says nothing about is decided
    by the operator's own config. Measured: a global `deny webfetch` was the
    only matching rule and won, and a global `deny tubematic_*` blocked the MCP
    tools outright — the pipeline would have done nothing on every tick while
    looking healthy. With these allows asserted, the same hostile global config
    yields MCP=ok, WEB=ok, ENV=blocked, SHELL=blocked."""
    rules = OpenCodeAdapter.PERMISSION_RULES
    allowed = {r["action"] for r in rules if r["effect"] == "allow"}
    # The MCP namespace above all: permission actions match the normalised
    # `<server>_<tool>` name, confirmed by denying it and watching a tool call
    # fail.
    assert "tubematic_*" in allowed
    # The topic-research skill tells the agent to use its web tools.
    assert {"webfetch", "websearch"} <= allowed
    assert {"read", "grep", "glob"} <= allowed
    order = [(r["action"], r["resource"]) for r in rules]
    for denied in ("edit", "write", "shell"):
        assert order.index((denied, "*")) > order.index(("read", "*")), \
            f"{denied} must be denied AFTER the broad allows, or the allow wins"


def test_opencode_permission_rules_are_the_whole_security_posture():
    """The counterpart of Claude's allowlist and Codex's `-s read-only`. Every
    pipeline write goes through an MCP tool, so edit/write are denied; nothing
    sandboxes a command OpenCode runs, so shell is denied; and the .env rules
    are DENY rather than OpenCode's default `ask` precisely because --auto
    approves an ask."""
    rules = {(r["action"], r["resource"]): r["effect"] for r in OpenCodeAdapter.PERMISSION_RULES}
    assert rules[("edit", "*")] == "deny"
    assert rules[("write", "*")] == "deny"
    assert rules[("shell", "*")] == "deny"
    assert rules[("read", "*.env")] == "deny"
    assert rules[("read", "*.env.*")] == "deny"
    assert rules[("read", "*.env.example")] == "allow"
    # Ordered, last-match-wins: the example allowance must follow its deny.
    order = [(r["action"], r["resource"]) for r in OpenCodeAdapter.PERMISSION_RULES]
    assert order.index(("read", "*.env.example")) > order.index(("read", "*.env"))


def test_opencode_turns_code_mode_off_for_the_tubematic_server():
    """Code Mode is OpenCode's default and hides MCP tools behind a
    search()/execute() sandbox as `tools.tubematic.<tool>`. The skills name
    their tools directly, so with it on the agent hunts a catalogue instead of
    working — observed, not theorised."""
    assert OpenCodeAdapter.MCP_SERVER_OPTIONS == {"codemode": False}
    # `oauth` is deliberately absent: a plain unauthenticated HTTP MCP server
    # was probed and connects with no OAuth and no `oauth: false`.
    assert "oauth" not in OpenCodeAdapter.mcp_server_entry("http://x/mcp", AUTH)


def test_every_adapter_declares_where_its_config_root_comes_from():
    """config_root_conflict asks each adapter for the root cron will use. An
    adapter that forgot to declare the variable would report every install as
    overridden, or none."""
    for adapter in ADAPTERS.values():
        assert hasattr(adapter, "CONFIG_HOME_ENV")
        if adapter.CONFIG_HOME_ENV is None:
            continue
        assert hasattr(adapter, "config_home")


# ── OpenCode's config dialect ───────────────────────────────────────────────

def test_the_config_document_name_is_resolved_not_assumed(tmp_path):
    """Probed against 2.0.14: with only a `.jsonc` present, `mcp add --global`
    appends to THAT file; with both, it picks `.json`; with neither it creates
    `.json`. Assuming `.json` meant the Code Mode patch was silently skipped on
    a `.jsonc` machine, the checklist called a correct install broken, and the
    uninstall left the registration behind."""
    assert OpenCodeAdapter._resolve_config(tmp_path).name == "opencode.json"
    (tmp_path / "opencode.jsonc").write_text("{}")
    assert OpenCodeAdapter._resolve_config(tmp_path).name == "opencode.jsonc"
    (tmp_path / "opencode.json").write_text("{}")
    assert OpenCodeAdapter._resolve_config(tmp_path).name == "opencode.json"


def test_config_file_and_workspace_config_both_resolve(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cfg = tmp_path / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "opencode.jsonc").write_text("{}")
    assert OpenCodeAdapter.config_file(tmp_path).name == "opencode.jsonc"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "opencode.jsonc").write_text("{}")
    assert OpenCodeAdapter.workspace_config_file(ws).name == "opencode.jsonc"


def test_jsonc_parses_comments_and_trailing_commas():
    """OpenCode accepts both inside a plain `.json`, verified with
    `opencode debug config`, so `json.loads` alone would report a perfectly
    valid config as broken and have the installer skip the permission rules."""
    text = '{\n  // lead\n  "a": 1, /* mid */\n  "b": [1, 2,],\n}'
    assert parse_jsonc(text) == {"a": 1, "b": [1, 2]}


def test_jsonc_never_touches_data_that_looks_like_syntax():
    """The reason this is a scanner and not a regex: a URL contains `//`, and a
    string value can contain `, }`. A naive pass corrupts both."""
    text = '{"url": "http://x//y", "glob": "a, }", "c": "/* not a comment */"}'
    parsed = parse_jsonc(text)
    assert parsed["url"] == "http://x//y"
    assert parsed["glob"] == "a, }"
    assert parsed["c"] == "/* not a comment */"


def test_only_comments_make_a_document_unsafe_to_rewrite():
    """Rewriting means json.dumps, which cannot preserve comments — so a
    commented document is left alone and reported. A trailing comma is syntax
    nobody will miss, so that one is normalised rather than refused."""
    assert jsonc_has_comments('{ // hi\n "a": 1 }') is True
    assert jsonc_has_comments('{"a": [1,],}') is False
    assert jsonc_has_comments('{"url": "http://x//y"}') is False


def test_every_config_document_owner_can_parse_its_own_dialect():
    """An adapter that names a config document must also say how to read it,
    or a caller holding one has to guess — and guessing `json.loads` is the
    bug this pins."""
    for adapter in ADAPTERS.values():
        if hasattr(adapter, "mcp_config_file"):
            assert callable(getattr(adapter, "parse_config", None))
            assert callable(getattr(adapter, "remove_mcp_entry", None))


def test_every_root_resolving_call_can_ignore_the_environment(tmp_path, monkeypatch):
    """An uninstall has to act on the root a SCHEDULED run uses. Honouring an
    override on some of these paths and not others removed the default skills
    while leaving the default commands and MCP registration in place."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "elsewhere"))
    default = tmp_path / ".config" / "opencode"
    assert OpenCodeAdapter.user_skills_dir(tmp_path, False) == default / "skills"
    assert OpenCodeAdapter.user_commands_dir(tmp_path, False) == default / "commands"
    assert OpenCodeAdapter.mcp_config_file(tmp_path, tmp_path / "ws", "user", False) == \
        default / "opencode.json"
    # And every adapter accepts the keyword, so a caller need not special-case.
    for adapter in ADAPTERS.values():
        adapter.user_commands_dir(tmp_path, respect_override=False)


@pytest.mark.parametrize("text, expected", [
    ('{"a": 1, // c\n}', {"a": 1}),
    ('{"a": 1, /* c */ }', {"a": 1}),
    ('{"a": [1, 2, // c\n]}', {"a": [1, 2]}),
])
def test_a_trailing_comma_followed_by_a_comment_parses(text, expected):
    """All three are valid JSONC and all three raised. Doing both passes at
    once means the comma's lookahead lands on the comment that has not been
    removed yet, keeps the comma, and then removes the comment — leaving a
    genuine trailing comma behind."""
    assert parse_jsonc(text) == expected


# ── The managed document ────────────────────────────────────────────────────

def test_the_managed_document_outranks_every_other(tmp_path):
    """`.opencode/opencode.json` inside the workspace, not the workspace's
    direct `opencode.json`, and that is a correctness requirement. Measured
    against 2.0.15: documents merge global < ancestor direct < workspace direct
    < ancestor `.opencode` < workspace `.opencode`, and `permissions` arrays
    are concatenated, so only the last one is guaranteed to win. A deny in the
    direct file was overridden by a developer's own `~/.opencode` and the
    credential file was read."""
    assert OpenCodeAdapter.managed_config_file(tmp_path) == \
        tmp_path / ".opencode" / "opencode.json"
    # Distinct from the document `opencode mcp add` writes at project scope.
    assert OpenCodeAdapter.managed_config_file(tmp_path) != \
        OpenCodeAdapter.workspace_config_file(tmp_path)


def test_the_managed_server_entry_is_complete():
    """An entry carrying only the options merges far enough for the server to
    connect — `mcp list` reports it connected, because the url comes from the
    other document — but the option does not apply and Code Mode stays on."""
    entry = OpenCodeAdapter.mcp_server_entry("http://localhost:4100/mcp", AUTH)
    assert entry == {"type": "remote", "url": "http://localhost:4100/mcp", "codemode": False,
                     "headers": {"Authorization":
                                 "Bearer {file:/h/.tubematic-data/secrets/mcp_token}"}}
    for key, value in OpenCodeAdapter.MCP_SERVER_OPTIONS.items():
        assert entry[key] == value


# ── Comment-preserving removal ──────────────────────────────────────────────

_PATH = ["mcp", "servers", "tubematic"]


@pytest.mark.parametrize("text", [
    '{"mcp":{"servers":{"tubematic":{"url":"u"},"other":{}}}}',              # middle member
    '{"mcp":{"servers":{"other":{},"tubematic":{"url":"u"}}}}',              # last member
    '{\n  // mine\n  "mcp": {"servers": {"tubematic": {"url":"u"}, "other": {}}},\n}\n',
    '{"mcp":{"servers":{"tubematic":{"url":"http://x//y"},"other":{}}}}',    # // inside a string
    '{"mcp":{"servers":{"tubematic":{"note":"a} , {b"},"other":{}}}}',       # braces in a string
    '{"mcp":{"servers":{"tubematic":{"args":[1,[2,3],{"k":"}"}]},"other":{}}}}',
    '{"mcp":{"servers":{"tubematic":{"s":"he said \\"hi\\""},"other":{}}}}',
])
def test_removal_drops_exactly_one_member_and_keeps_comments(text):
    edited = remove_jsonc_member(text, _PATH)
    assert edited is not None
    expected = parse_jsonc(text)
    expected["mcp"]["servers"].pop("tubematic")
    assert parse_jsonc(edited) == expected
    assert jsonc_has_comments(edited) == jsonc_has_comments(text)


@pytest.mark.parametrize("text", [
    '{"mcp":{"servers":{"other":{}}}}',              # the key is not there
    '{"a":1}',                                        # the path is not there
    '{"mcp":{"servers":{"tubematic":{"url":"u"}',     # unbalanced
    '[1,2,3]',                                        # not an object
    'not json at all',
])
def test_removal_refuses_rather_than_guessing(text):
    """Every result is verified — the edited text must parse AND equal the
    original minus exactly that key — so surgery on a human's file can only
    produce a proven-correct result or no change at all."""
    assert remove_jsonc_member(text, _PATH) is None


def test_the_adapter_exposes_removal_for_its_own_server():
    text = '{"mcp":{"servers":{"tubematic":{"url":"u"},"other":{}}}}'
    assert parse_jsonc(OpenCodeAdapter.remove_mcp_entry(text))["mcp"]["servers"] == {"other": {}}


# ── Usage parsing and JSON-mode rejections (TMDEV-107) ───────────────────────
# Fixtures are trimmed copies of real output, probed live 2026-09-24 against
# Claude Code 2.1.281, codex-cli 0.156.1 and @opencode/cli 2.0.14.

CLAUDE_JSON = json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.0259719,
    "usage": {"input_tokens": 10, "output_tokens": 205},
    "modelUsage": {"claude-haiku-4-5-20251001": {
        "inputTokens": 10, "outputTokens": 205, "cacheReadInputTokens": 13689,
        "cacheCreationInputTokens": 11784, "thinkingTokens": 199, "costUSD": 0.0259719,
        "canonicalModel": "claude-haiku-4-5", "costBasis": "list"}},
})

CODEX_JSONL = "\n".join([
    '{"type":"thread.started","thread_id":"01a0"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"ok"}}',
    '{"type":"turn.completed","usage":{"input_tokens":14889,"cached_input_tokens":6656,'
    '"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}',
])

OPENCODE_STREAM = "\n".join([
    '{"type":"step_start","sessionID":"ses_1","part":{"type":"step-start"}}',
    '{"type":"text","sessionID":"ses_1","part":{"type":"text","text":"done"}}',
    '{"type":"step_finish","sessionID":"ses_1","part":{"type":"step-finish","cost":0.01,'
    '"tokens":{"input":2875,"output":32,"reasoning":33,"cache":{"read":3456,"write":0}}}}',
])

OPENCODE_MESSAGES = json.dumps({"data": [
    {"type": "idle"},
    {"type": "assistant", "model": {"id": "claude-sonnet-5", "providerID": "anthropic"},
     "cost": 0.02, "tokens": {"input": 6135, "output": 3, "reasoning": 0,
                              "cache": {"read": 476, "write": 0}}},
    {"type": "assistant", "model": {"id": "claude-sonnet-5", "providerID": "anthropic"},
     "cost": 0.01, "tokens": {"input": 2875, "output": 32, "reasoning": 33,
                              "cache": {"read": 3456, "write": 0}}},
    {"type": "user"},
]})


def test_claude_usage_is_one_event_per_model_with_its_own_list_cost():
    [ev] = ClaudeAdapter.parse_usage(CLAUDE_JSON, model="haiku")
    assert ev["service"] == "anthropic" and ev["model"] == "claude-haiku-4-5"
    assert ev["reported_cost_usd"] == pytest.approx(0.0259719)
    assert ev["units"] == {"input": 10, "output": 205, "cache_read": 13689,
                           "cache_write": 11784}


def test_claude_usage_from_a_rejected_model_run_is_empty():
    """A rejected model never started, so there is nothing to record."""
    out = json.dumps({"is_error": True, "total_cost_usd": 0, "modelUsage": {},
                      "result": "…It may not exist or you may not have access to it."})
    assert ClaudeAdapter.parse_usage(out) == []
    assert ClaudeAdapter.parse_usage("not json at all") == []


def test_claude_rejected_model_still_matches_in_json_mode():
    out = json.dumps({"result": "There's an issue with the selected model (x). It may not "
                                "exist or you may not have access to it."})
    assert ClaudeAdapter.model_rejected(out, 1)


def test_codex_usage_sums_turns_and_splits_cached_input_out():
    [ev] = CodexAdapter.parse_usage(CODEX_JSONL, model="gpt-5.6-sol")
    assert (ev["service"], ev["model"]) == ("openai", "gpt-5.6-sol")
    assert ev["units"] == {"input": 14889 - 6656, "cache_read": 6656, "cache_write": 0,
                           "output": 5}
    assert ev["reported_cost_usd"] is None  # priced from the table


def test_codex_usage_without_a_model_reads_the_configured_default(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text('model = "gpt-5.5"\n')
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    [ev] = CodexAdapter.parse_usage(CODEX_JSONL, model="")
    assert ev["model"] == "gpt-5.5"


def test_codex_effort_rejection_is_read_from_json_error_events_on_stdout():
    """Under --json the rejection is on stdout, and stderr has only a notice."""
    stdout = "\n".join([
        '{"type":"thread.started","thread_id":"x"}',
        '{"type":"error","message":"{\\"error\\":{\\"message\\":\\"[ReasoningEffortParam] '
        '[reasoning.effort] [invalid_enum_value] Invalid value\\"}}"}',
        '{"type":"turn.failed","error":{"message":"[reasoning.effort] invalid"}}',
    ])
    assert CodexAdapter.effort_rejected("Reading additional input from stdin...", 1, stdout)


def test_codex_effort_is_never_read_from_the_agents_own_words():
    """A session that merely discusses the parameter must not strip the flag."""
    stdout = ('{"type":"item.completed","item":{"type":"agent_message",'
              '"text":"the reasoning.effort param was rejected earlier"}}')
    assert not CodexAdapter.effort_rejected("", 1, stdout)


def test_opencode_usage_comes_from_the_session_api():
    seen = []

    def fetch(session_id):
        seen.append(session_id)
        return OPENCODE_MESSAGES
    [ev] = OpenCodeAdapter.parse_usage(OPENCODE_STREAM, model="anthropic/claude-sonnet-5",
                                       fetch=fetch)
    assert seen == ["ses_1"]
    assert (ev["service"], ev["model"]) == ("anthropic", "claude-sonnet-5")
    assert ev["reported_cost_usd"] == pytest.approx(0.03)
    assert ev["units"]["input"] == 6135 + 2875
    assert ev["estimated"] is False


def test_opencode_falls_back_to_the_stream_marked_estimated():
    """step_finish events can miss the last step, so the stream is only a fallback."""
    [ev] = OpenCodeAdapter.parse_usage(OPENCODE_STREAM, model="anthropic/claude-sonnet-5#high",
                                       fetch=lambda sid: "")
    assert (ev["service"], ev["model"]) == ("anthropic", "claude-sonnet-5")
    assert ev["reported_cost_usd"] == pytest.approx(0.01)
    assert ev["estimated"] is True


def test_opencode_session_usage_argv_is_exact():
    assert OpenCodeAdapter.session_usage_argv("/b/opencode", "ses_1") == \
        ["/b/opencode", "api", "GET", "/api/session/ses_1/message"]


def test_opencode_variant_rejection_is_read_from_json_error_events():
    stdout = ('{"type":"error","sessionID":"s","error":{"type":"provider.no-route",'
              '"message":"Variant unavailable for opencode/m: bogus"}}')
    assert OpenCodeAdapter.effort_rejected("", 1, stdout)
    assert not OpenCodeAdapter.effort_rejected(
        "", 1, '{"type":"text","part":{"text":"Variant unavailable, it said"}}')


# ── What a run leaves in the logs (TMDEV-124) ────────────────────────────────
# The JSON output modes make stdout the whole session — every tool call's
# arguments and results — so poll.py logs a summary instead. The summary is
# log-only: the verdict and usage parsers above still read the full stdout.

from agent_adapters import LOG_OUTPUT_CAP, clip

# A tool result nothing may copy into a log: the whole point of the summary.
_BULK = "BULKY-TOOL-RESULT-" + "x" * 50_000


def _codex_item(item, kind="item.completed"):
    return json.dumps({"type": kind, "item": item})


def test_clip_leaves_short_text_alone():
    assert clip("short", 10) == "short"


def test_clip_keeps_the_head_and_says_how_much_went():
    out = clip("x" * 10 + "y" * 10, 10)
    assert out.startswith("x" * 10) and "y" not in out
    assert "10 chars trimmed" in out


def test_clip_can_keep_the_tail_instead():
    out = clip("x" * 10 + "y" * 10, 10, keep="tail")
    assert out.endswith("y" * 10) and "x" not in out
    assert "10 chars trimmed" in out


def test_claude_summary_is_the_final_result_and_turn_count():
    out = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "num_turns": 7, "result": "Scripted vid_1.", "modelUsage": {},
                      "usage": {"input_tokens": 10}})
    summary = ClaudeAdapter.summarize_output(out)
    assert summary.splitlines()[0] == "Agent result — 7 turns"
    assert "Scripted vid_1." in summary
    assert "modelUsage" not in summary and "input_tokens" not in summary


def test_claude_summary_names_denied_tools_and_error_results():
    out = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True,
                      "num_turns": 3, "result": "",
                      "permission_denials": [{"tool_name": "Bash", "tool_input": {"c": _BULK}},
                                             {"tool_name": "Bash"}, {"tool_name": "Write"}]})
    summary = ClaudeAdapter.summarize_output(out)
    assert "3 permission denials: Bash ×2, Write" in summary
    assert "Errors:" in summary and "error_max_turns" in summary
    assert "BULKY" not in summary


def test_codex_summary_is_the_last_message_and_a_counted_tool_trace():
    out = "\n".join([
        '{"type":"thread.started","thread_id":"t"}',
        _codex_item({"id": "0", "type": "agent_message", "text": "I'll look first."}),
        # item.started carries the same call: it must not be counted twice.
        _codex_item({"id": "1", "type": "mcp_tool_call", "server": "tubematic",
                     "tool": "list_videos", "status": "in_progress"}, kind="item.started"),
        _codex_item({"id": "1", "type": "mcp_tool_call", "server": "tubematic",
                     "tool": "list_videos", "arguments": {}, "status": "completed",
                     "result": {"content": [{"type": "text", "text": _BULK}]}}),
        _codex_item({"id": "2", "type": "mcp_tool_call", "tool": "add_comment",
                     "status": "completed"}),
        _codex_item({"id": "3", "type": "mcp_tool_call", "tool": "add_comment",
                     "status": "failed", "error": {"message": "nope"}}),
        _codex_item({"id": "4", "type": "command_execution", "command": "ls",
                     "aggregated_output": _BULK, "status": "completed"}),
        _codex_item({"id": "5", "type": "reasoning", "text": "thinking " + _BULK}),
        _codex_item({"id": "6", "type": "agent_message", "text": "Filed 2 topics."}),
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}',
    ])
    summary = CodexAdapter.summarize_output(out)
    assert summary.splitlines()[0] == ("Agent result — 4 tool calls (1 failed): "
                                       "list_videos, add_comment ×2, command_execution")
    assert summary.splitlines()[-1] == "Filed 2 topics."
    assert "I'll look first." not in summary
    assert "BULKY" not in summary and "thinking" not in summary


def test_codex_summary_surfaces_the_clis_error_events():
    out = "\n".join([
        '{"type":"thread.started","thread_id":"t"}',
        '{"type":"turn.failed","error":{"message":"model gpt-x does not exist"}}',
    ])
    summary = CodexAdapter.summarize_output(out)
    assert "Agent result — no tool calls" in summary
    assert "Errors: model gpt-x does not exist" in summary
    assert "(no final message)" in summary


def test_opencode_summary_is_the_last_text_and_a_deduped_tool_trace():
    def tool(call, name, status, output=""):
        return json.dumps({"type": "tool_use", "sessionID": "s", "part": {
            "type": "tool", "callID": call, "tool": name,
            "state": {"status": status, "input": {"q": 1}, "output": output}}})
    out = "\n".join([
        '{"type":"step_start","sessionID":"s","part":{"type":"step-start"}}',
        '{"type":"text","sessionID":"s","part":{"type":"text","text":"Checking the queue."}}',
        tool("c1", "tubematic_get_pipeline_status", "running"),
        tool("c1", "tubematic_get_pipeline_status", "completed", _BULK),
        tool("c2", "webfetch", "error"),
        tool("c3", "tubematic_create_video", "completed", _BULK),
        '{"type":"text","sessionID":"s","part":{"type":"text","text":"Filed one topic."}}',
        '{"type":"step_finish","sessionID":"s","part":{"type":"step-finish","cost":0.01}}',
    ])
    summary = OpenCodeAdapter.summarize_output(out)
    assert summary.splitlines()[0] == (
        "Agent result — 3 tool calls (1 failed): tubematic_get_pipeline_status, webfetch, "
        "tubematic_create_video")
    assert summary.splitlines()[-1] == "Filed one topic."
    assert "Checking the queue." not in summary and "BULKY" not in summary


def test_opencode_summary_surfaces_the_clis_error_events():
    out = ('{"type":"error","sessionID":"s","error":{"type":"provider.no-route",'
           '"message":"Model unavailable: x/y"}}')
    assert "Errors: Model unavailable: x/y" in OpenCodeAdapter.summarize_output(out)


@pytest.mark.parametrize("adapter", [ClaudeAdapter, CodexAdapter, OpenCodeAdapter])
def test_a_long_final_message_is_clipped(adapter):
    text = "M" * (LOG_OUTPUT_CAP * 3)
    out = {
        ClaudeAdapter: json.dumps({"type": "result", "num_turns": 1, "result": text}),
        CodexAdapter: _codex_item({"id": "0", "type": "agent_message", "text": text}),
        OpenCodeAdapter: json.dumps({"type": "text", "part": {"type": "text", "text": text}}),
    }[adapter]
    summary = adapter.summarize_output(out)
    assert len(summary) < LOG_OUTPUT_CAP + 200
    assert f"{LOG_OUTPUT_CAP * 2} chars trimmed" in summary


@pytest.mark.parametrize("adapter", [ClaudeAdapter, CodexAdapter, OpenCodeAdapter])
def test_output_in_no_known_shape_is_clipped_not_dropped(adapter):
    """An old CLI, a crash banner, plain text: kept, but never whole."""
    summary = adapter.summarize_output("Error: something broke\n" + "z" * (LOG_OUTPUT_CAP * 2))
    assert "Error: something broke" in summary
    assert len(summary) < LOG_OUTPUT_CAP + 200


@pytest.mark.parametrize("adapter", [ClaudeAdapter, CodexAdapter, OpenCodeAdapter])
def test_empty_output_summarises_to_nothing(adapter):
    assert adapter.summarize_output("") == ""
    assert adapter.summarize_output("  \n") == ""


# ── MCP authentication (TMDEV-152) ──────────────────────────────────────────

AUTH = McpAuth(helper="/v/bin/python3 /r/scripts/mcp_auth_header.py",
               token_file="/h/.tubematic-data/secrets/mcp_token")


def test_no_registration_ever_carries_the_token_itself():
    """Every CLI is pointed at the token FILE or a helper that reads it, so the
    secret is never in an argv, a dry-run listing or an agent's config, and a
    rotation needs no re-registration."""
    secret = "s3cr3t-token-value"
    for adapter in ADAPTERS.values():
        for scope in adapter.SUPPORTED_SCOPES:
            argv = adapter.mcp_add_argv("/b/x", scope, "http://h/mcp", AUTH)
            assert secret not in " ".join(argv)
    assert secret not in json.dumps(OpenCodeAdapter.mcp_server_entry("http://h/mcp", AUTH))


def test_every_adapter_says_whether_mcp_add_replaces():
    for adapter in ADAPTERS.values():
        assert isinstance(adapter.MCP_ADD_REPLACES, bool)


_CODEX_TOML = """model = "gpt-5"

# the operator's own comment
[mcp_servers.other]
url = "http://other/mcp"

[mcp_servers.tubematic]
url = "http://localhost:4100/mcp"

[profiles.x]
model = "y"
"""


def test_codex_header_helper_is_set_inside_our_table_only():
    import tomllib
    out = CodexAdapter.set_mcp_header_helper(_CODEX_TOML, AUTH.helper)
    data = tomllib.loads(out)
    assert data["mcp_servers"]["tubematic"]["http_headers_helper"] == AUTH.helper
    assert data["mcp_servers"]["tubematic"]["url"] == "http://localhost:4100/mcp"
    assert "http_headers_helper" not in data["mcp_servers"]["other"]
    assert data["profiles"]["x"] == {"model": "y"}
    assert "# the operator's own comment" in out


def test_codex_header_helper_replaces_rather_than_duplicates():
    import tomllib
    once = CodexAdapter.set_mcp_header_helper(_CODEX_TOML, "old helper")
    twice = CodexAdapter.set_mcp_header_helper(once, AUTH.helper)
    assert twice.count("http_headers_helper") == 1
    assert tomllib.loads(twice)["mcp_servers"]["tubematic"]["http_headers_helper"] == AUTH.helper


def test_codex_header_helper_quotes_a_path_with_specials():
    import tomllib
    helper = '/opt/my "tools"/python3 /r\\x/mcp_auth_header.py'
    out = CodexAdapter.set_mcp_header_helper(_CODEX_TOML, helper)
    assert tomllib.loads(out)["mcp_servers"]["tubematic"]["http_headers_helper"] == helper


def test_codex_header_helper_without_our_table_is_none():
    assert CodexAdapter.set_mcp_header_helper('[mcp_servers.other]\nurl = "u"\n', "h") is None


def test_codex_config_toml_follows_codex_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ch"))
    assert CodexAdapter.config_toml(tmp_path) == tmp_path / "ch" / "config.toml"
    assert CodexAdapter.config_toml(tmp_path, respect_override=False) == \
        tmp_path / ".codex" / "config.toml"


def test_opencode_reload_argv():
    assert OpenCodeAdapter.reload_argv("/b/opencode") == ["/b/opencode", "reload"]
