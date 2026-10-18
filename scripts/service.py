#!/usr/bin/env python3
"""Start, stop, restart, inspect and tail the Tubematic stack.

    python scripts/service.py start   [service]
    python scripts/service.py stop    [service] [--force]
    python scripts/service.py restart [service] [--force]
    python scripts/service.py status
    python scripts/service.py logs    [service] [-f]

Prefer this to a bare `docker compose up -d`. `start` first creates the data
directories and reconciles the Docker volumes (a volume still pointing at an
old data location would otherwise keep being mounted), then starts the
containers and waits for their health checks.

`stop` and `restart` refuse while work is in flight — a render, a voicing, a
running agent session, or a publish upload — because stopping would kill it.
`--force` stops anyway. Restarting the dashboard alone is not refused, since it
holds no work — unless a Docker volume has to be re-pointed first, which takes
the whole stack down, so `start` and a dashboard restart are gated then too.

Options:
  --force       Stop even though work is in flight
  --dry-run     Show what would happen; change nothing
  -f, --follow  With `logs`: keep following
  --help, -h    Show this and exit

Services: tubematic-api, tubematic-mcp, tubematic-renderer, tubematic-dashboard.
To upgrade, use upgrade.py instead — it owns the full sequence.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COMMANDS = ("start", "stop", "restart", "status", "logs")
OPTIONS = ("--force", "--dry-run", "-f", "--follow")
# Keep in sync: onboard/stack.py SERVICES. Duplicated so argv can be checked
# before the venv bootstrap, which may re-exec this script.
SERVICES = ("tubematic-api", "tubematic-mcp", "tubematic-renderer", "tubematic-dashboard")


def _bootstrap() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from onboard.bootstrap import ensure_deps, ensure_venv
    ensure_venv(Path(__file__))
    ensure_deps()


def run(command: str, *, service: str = None, follow: bool = False, force: bool = False,
        dry_run: bool = False, db_path=None, lock_path=None, rep=None, ex=None) -> int:
    """Carry out one command. Returns a process exit code."""
    from onboard import stack
    from onboard.actions import _compose
    from onboard.config import DB_PATH, resolve_install_mode
    from onboard.executor import Executor
    from onboard.plain import PlainReporter, console
    from onboard.state import load_state

    services = [service] if service else []
    db_path = db_path or DB_PATH
    rep = rep or PlainReporter(dry_run=dry_run)
    ex = ex or Executor(dry_run=dry_run, reporter=rep)

    if command == "status":
        mode = resolve_install_mode(None, recorded=load_state().get("install_mode"))
        return 0 if stack.report(rep, db_path=db_path, mode=mode) else 1

    if command == "logs":
        argv = [*_compose(), "logs", "--tail", "200", *(["-f"] if follow else []), *services]
        os.chdir(REPO_ROOT)
        os.execvp(argv[0], argv)
        return 0  # only reached when execvp is stubbed

    try:
        # The lock is held until the command finishes so the poller cannot
        # start an agent against a stack that is going away.
        with stack.poll_lock(lock_path) as acquired:
            def full_gate(_names=None) -> bool:
                return stack.gate(db_path, lock_acquired=acquired, force=force, rep=rep)

            # Decided before anything stops, so a refusal leaves nothing half
            # done. The dashboard alone holds no work — except that `start`
            # itself can take the whole stack down: when a Docker volume has to
            # be re-pointed, onboarding's reconcile runs `compose down`. So even
            # a start, or a dashboard-only restart, is gated then.
            stops_backend = command in ("stop", "restart") \
                and services != ["tubematic-dashboard"]
            reconciles = command in ("start", "restart") and bool(stack._stale_volumes())
            gated = stops_backend or reconciles
            if gated and not full_gate():
                return 1
            if command in ("stop", "restart"):
                stack.stop(ex, rep, services)
            if command in ("start", "restart"):
                # Already gated means already answered; otherwise start asks
                # itself if a volume turns stale in between.
                stack.start(ex, rep, services,
                            confirm_down=(lambda names: True) if gated else full_gate)
        return 0
    except RuntimeError as e:
        console.print(f"\n[red]{command} failed: {e}[/red]\n")
        return 1


def main() -> None:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    positional = [a for a in args if not a.startswith("-")]
    unknown = [a for a in args if a.startswith("-") and a not in OPTIONS]
    command = positional[0] if positional else None
    service = positional[1] if len(positional) > 1 else None
    problem = None
    if command not in COMMANDS:
        problem = f"expected one of: {', '.join(COMMANDS)}"
    elif service and service not in SERVICES:
        problem = f"unknown service '{service}' — one of: {', '.join(SERVICES)}"
    elif len(positional) > 2 or (service and command == "status"):
        problem = "too many arguments"
    elif unknown:
        problem = f"unknown option: {' '.join(unknown)}"
    if problem:
        print(f"\n  {problem}  (see --help)\n")
        sys.exit(1)

    _bootstrap()
    sys.exit(run(command, service=service, follow="-f" in args or "--follow" in args,
                 force="--force" in args, dry_run="--dry-run" in args))


if __name__ == "__main__":
    main()
