#!/usr/bin/env python3
"""Tubematic onboard script.

A sequential, per-step wizard: each step's questions (if it has any) are
asked right before that step's own action runs, and completed steps are
skipped on re-runs. The two container builds (renderer, dashboard) are
always the last two steps and have no prompts of their own, so nothing ever
interleaves a question in between builds — see onboard/steps.py.

Flags:
  --status         Show step-done progress table and exit (plain, pipeable)
  --steps          List every step and exactly what it prompts for (plain, pipeable)
  --step <key>     (Re-)ask and (re-)apply just this one step, regardless of done
                   state. Hyphens and underscores are interchangeable.
  --install-agent <name>
                   Install an agent (supported: claude, codex, opencode) after the project
                   is set up: checks its login, validates its models, deploys
                   skills and commands. Re-running it is the update/redeploy path.
  --uninstall-agent <name>
                   Remove the skills, commands and MCP registration the install
                   deployed and mark the agent uninstalled. Keeps its workspace.
  --list-agents    List supported agents and installed ones, then exit (pipeable)
  --set-password   Set or change the dashboard password. Changing it signs every
                   dashboard session out. Run this before upgrading from 1.2.x.
  --rotate-tokens  Replace the three service tokens, restart the services that read
                   them, and have OpenCode reload. Waits for in-flight work, like
                   upgrade.py; --force proceeds anyway.
  --install-mode {dev,release}
                   Override the auto-detected install mode. Auto-detect picks
                   release when renderer/Dockerfile is absent (that's what a
                   release tarball looks like — it ships no source trees) and
                   dev otherwise. Release installs pull container images
                   instead of building them, and don't require Node/npx.
  --force         Re-run every step regardless of done state
  --full-questionnaire
                   Ask every question. By default only the questions a first
                   install has to answer are asked; everything else uses its
                   default, editable later on the Settings dashboard. Applies to
                   --install-agent too.
  --allow-skipping Let required settings (the ElevenLabs and OpenAI API keys,
                   the voice roster) be left blank at the prompt. Without it
                   the wizard re-asks until they are supplied — onboarding is
                   meant to hand back an install that can actually run. The
                   OpenAI key is still needed for the install configuration
                   step to finish.
  --disable-verification
                   Don't check API keys against their provider as they are
                   typed. A malformed paste is still rejected locally.
  --dry-run        Ask the same questions, but apply nothing — no files written,
                    no containers built or started. Prerequisite failures warn
                    instead of blocking, so you can preview on an unset-up machine.
  --help, -h       Show usage and exit

Run:
  python onboard.py                    # full wizard
  python onboard.py --dry-run          # preview only, nothing mutates
  python onboard.py --status           # progress table, exit
  python onboard.py --steps            # what every step contains, exit
  python onboard.py --step install_config   # (re-)ask and (re-)apply just that step
  python onboard.py --full-questionnaire    # ask every question, not just the essential ones
  python onboard.py --install-agent claude  # install (or update) an agent; codex and
  python onboard.py --install-agent codex   #   opencode are also supported, and any number
  python onboard.py --install-agent opencode  # of them may be installed at once
  python onboard.py --uninstall-agent codex
  python onboard.py --list-agents
  python onboard.py --set-password
  python onboard.py --rotate-tokens
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()


def _ensure_venv() -> None:
    """Re-exec inside REPO_ROOT/.venv — see onboard/bootstrap.py, shared with
    upgrade.py and scripts/service.py."""
    from onboard.bootstrap import ensure_venv
    ensure_venv(Path(__file__))


def _ensure_deps() -> None:
    """Install the wizard's own deps if missing — see onboard/bootstrap.py."""
    from onboard.bootstrap import ensure_deps
    ensure_deps()


def _agent_arg(args: list, flag: str) -> str | None:
    """The agent name after `flag`, or None when the flag is absent. Exits 1
    on a missing or unsupported name, listing the supported ones."""
    if flag not in args:
        return None
    from onboard.agent_install import ADAPTERS
    supported = ", ".join(sorted(ADAPTERS))
    idx = args.index(flag)
    if idx + 1 >= len(args) or args[idx + 1].startswith("-"):
        print(f"\n  {flag} requires an agent name (supported: {supported})\n")
        sys.exit(1)
    name = args[idx + 1]
    if name not in ADAPTERS:
        print(f"\n  Unknown agent: '{name}'")
        print(f"  Supported: {supported}\n")
        sys.exit(1)
    return name


def main() -> None:
    _ensure_venv()
    _ensure_deps()

    # Everything below needs REPO_ROOT on sys.path to import the onboard/
    # package — the interpreter's own script directory normally covers this,
    # but the venv re-exec above can change that in edge cases, so be explicit.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from onboard.steps import VALID_KEYS

    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        from onboard.plain import print_help
        print_help()
        return

    for dead in ("--host", "--agent"):
        if dead in args:
            print(f"\n  {dead} was removed — Tubematic now installs on a single machine.")
            print("  Run: python onboard.py\n")
            sys.exit(1)

    status_only = "--status" in args
    steps_only = "--steps" in args
    dry_run = "--dry-run" in args
    force_all = "--force" in args
    full_questionnaire = "--full-questionnaire" in args
    allow_skipping = "--allow-skipping" in args
    verify_keys = "--disable-verification" not in args
    step_key = None
    install_agent = _agent_arg(args, "--install-agent")
    uninstall_agent = _agent_arg(args, "--uninstall-agent")

    install_mode = None
    if "--install-mode" in args:
        from onboard.config import INSTALL_MODES
        idx = args.index("--install-mode")
        if idx + 1 >= len(args) or args[idx + 1] not in INSTALL_MODES:
            print(f"\n  --install-mode requires one of: {', '.join(INSTALL_MODES)}\n")
            sys.exit(1)
        install_mode = args[idx + 1]

    if "--step" in args:
        idx = args.index("--step")
        if idx + 1 >= len(args):
            print("\n  --step requires a step key (e.g. --step install_config)")
            print(f"  Valid keys: {', '.join(sorted(VALID_KEYS))}\n")
            sys.exit(1)
        # Step keys use underscores, but a hyphenated spelling is the natural
        # thing to type, so accept either rather than rejecting one of the two
        # on a technicality.
        typed_key = args[idx + 1]
        step_key = typed_key.replace("-", "_")
        if step_key not in VALID_KEYS:
            # Echo what they typed, not the normalised form — otherwise the
            # error names a string they never wrote.
            print(f"\n  Unknown step key: '{typed_key}'")
            print(f"  Valid keys: {', '.join(sorted(VALID_KEYS))}\n")
            sys.exit(1)

    if status_only:
        from onboard.plain import print_status
        print_status()
        return

    if steps_only:
        from onboard.plain import print_steps
        print_steps()
        return

    if "--list-agents" in args:
        from onboard.agent_install import print_agents
        print_agents()
        return

    # Non-interactive, so it is dispatched before the terminal check below.
    if "--rotate-tokens" in args:
        from onboard.auth_commands import run_rotate_tokens
        sys.exit(run_rotate_tokens(dry_run=dry_run, force=force_all))

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("\n  The onboard wizard needs an interactive terminal (it asks questions).")
        print("  Non-interactive options: --status, --steps, --rotate-tokens.\n")
        sys.exit(1)

    if "--set-password" in args:
        from onboard.auth_commands import run_set_password
        sys.exit(run_set_password(dry_run=dry_run))

    if install_agent:
        from onboard.agent_install import run_install_agent
        sys.exit(run_install_agent(install_agent, dry_run=dry_run,
                                   allow_skipping=allow_skipping, verify_keys=verify_keys,
                                   full_questionnaire=full_questionnaire))

    if uninstall_agent:
        from onboard.agent_install import run_uninstall_agent
        sys.exit(run_uninstall_agent(uninstall_agent, dry_run=dry_run))

    from onboard.plain import run_wizard
    run_wizard(dry_run=dry_run, force_all=force_all, step_key=step_key,
               full_questionnaire=full_questionnaire, allow_skipping=allow_skipping,
               verify_keys=verify_keys, install_mode=install_mode)


if __name__ == "__main__":
    main()
