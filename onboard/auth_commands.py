"""`onboard.py --set-password` and `--rotate-tokens` (TMDEV-152).

The onboarding `auth` step creates the tokens and the first password; these
two change them later. Neither needs a container to be rebuilt:

* A new password rotates `session_secret`, which the dashboard reads on every
  request, so every signed-in browser is signed out at once.
* A token rotation rewrites the files in place (a bind mount keeps its inode),
  restarts the three services that read a token at start-up, and has OpenCode
  re-read its config. Claude Code and Codex read the token through the helper
  on every connection, so they need nothing.
"""
from onboard.actions import REPO_ROOT, _compose, _upsert_settings
from onboard.config import DB_PATH, read_agents
from onboard.executor import Executor
from onboard.plain import PlainReporter

TOKEN_READERS = ("tubematic-api", "tubematic-mcp", "tubematic-dashboard")


def run_set_password(*, dry_run: bool = False, rep=None, ex=None, ask=None) -> int:
    """Set or change the dashboard password. Safe to run before an upgrade:
    an install that does not know the row ignores it."""
    from tubematic_core import auth

    rep = rep or PlainReporter(dry_run=dry_run)
    ex = ex or Executor(dry_run=dry_run, reporter=rep)
    if not DB_PATH.exists():
        rep.warn(f"No Tubematic database at {DB_PATH}. Set up the install first: python onboard.py")
        return 1
    had_one = auth.has_admin_password(DB_PATH)
    if dry_run:
        rep.info("[dry-run] would ask for the new dashboard password and store its hash"
                 + (", then sign every dashboard session out" if had_one else ""))
        return 0
    if ask is None:
        from onboard.prompt import ask_new_password as ask
    password = ask()
    _upsert_settings(ex, {auth.PASSWORD_KEY: auth.hash_password(password)},
                     "the dashboard password (its hash only)")
    rep.ok("Dashboard password " + ("changed" if had_one else "set"))
    if had_one and (auth.secrets_dir() / "session_secret").is_file():
        ex.rotate_secrets(["session_secret"])
        rep.ok("Every dashboard session was signed out")
    return 0


def run_rotate_tokens(*, dry_run: bool = False, force: bool = False, rep=None, ex=None,
                      lock_path=None, adapters=None) -> int:
    """Replace all three tokens. Waits for in-flight work like upgrade.py does,
    because the services that hold a token are restarted."""
    from onboard import stack
    from tubematic_core import auth

    rep = rep or PlainReporter(dry_run=dry_run)
    ex = ex or Executor(dry_run=dry_run, reporter=rep)
    if not auth.secrets_dir().is_dir():
        rep.warn(f"No service tokens in {auth.secrets_dir()} yet. "
                 "Run: python onboard.py (or upgrade.py) to create them.")
        return 1
    if adapters is None:
        from onboard.agent_install import ADAPTERS as adapters

    with stack.poll_lock(lock_path) as acquired:
        if not stack.gate(DB_PATH, lock_acquired=acquired, force=force, rep=rep):
            rep.info("Nothing was changed. Re-run once the work above has finished, "
                     "or with --force.")
            return 1
        ex.rotate_secrets(auth.SECRET_NAMES)
        rep.ok("Service tokens replaced")
        # From here the files hold the new tokens, so every consumer that fails
        # to pick them up leaves the install unable to authenticate somewhere.
        # Each is still attempted, but any failure fails the command.
        incomplete = []
        r = ex.run([*_compose(), "restart", *TOKEN_READERS], cwd=REPO_ROOT)
        if r.returncode != 0:
            incomplete.append("restart the services")
            rep.warn("Could not restart the services; they keep the old tokens until they "
                     f"restart: docker compose restart {' '.join(TOKEN_READERS)}")
        else:
            rep.ok(f"Restarted {', '.join(TOKEN_READERS)}")
        for agent in read_agents(DB_PATH):
            adapter = adapters.get(agent["id"])
            reload_argv = getattr(adapter, "reload_argv", None)
            if agent.get("archived_at") or not reload_argv or not agent.get("binary"):
                continue
            r = ex.run(reload_argv(agent["binary"]))
            if r.returncode == 0:
                rep.ok(f"Agent '{agent['id']}' reloaded its config, and with it the new MCP token")
            else:
                incomplete.append(f"reload agent '{agent['id']}'")
                rep.warn(f"Agent '{agent['id']}' did not reload — run: "
                         f"{' '.join(reload_argv(agent['binary']))}")
    if incomplete:
        rep.warn("Rotation not finished: could not " + " or ".join(incomplete) + ". The new "
                 "tokens are in place, so until the commands above succeed the parts still "
                 "holding the old ones will refuse, or be refused by, everything else.")
        return 1
    rep.info("Every dashboard session was signed out. Restart any open agent session.")
    return 0
