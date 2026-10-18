"""docker-compose.yml topology — four services, one process each (TMDEV-87).

Flask and MCP used to share the tubematic-api container: entrypoint.sh
backgrounded Flask and exec'd MCP. When Flask died, MCP still held PID 1, so
the container stayed up, went at most `unhealthy`, and `restart:
unless-stopped` never fired — a dead dashboard behind a live-looking
container. These tests pin the split so it cannot quietly regress.

Parses the YAML directly rather than shelling out to `docker compose config`:
that needs a running daemon and interpolates ${HOME}, neither of which belongs
in a unit test.

Requires pyyaml, which is a test-only dependency — like pytest itself, it is
not declared in any requirements file because nothing at runtime reads YAML.
Run from repo root: pytest onboard/tests/
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def services():
    return yaml.safe_load(COMPOSE.read_text())["services"]


# ── Service split ──────────────────────────────────────────────────────────

def test_api_and_mcp_are_distinct_services(services):
    assert "tubematic-api" in services
    assert "tubematic-mcp" in services


def test_the_four_runtime_services(services):
    assert set(services) == {
        "tubematic-api", "tubematic-mcp",
        "tubematic-renderer", "tubematic-dashboard",
    }


def test_api_starts_flask_only(services):
    command = services["tubematic-api"]["command"]
    assert "/app/api/server.py" in command
    assert "/app/mcp/server.py" not in command


def test_mcp_starts_mcp_only(services):
    command = services["tubematic-mcp"]["command"]
    assert "/app/mcp/server.py" in command
    assert "/app/api/server.py" not in command


def test_api_and_mcp_both_run_through_the_shared_entrypoint(services):
    """entrypoint.sh carries the DB permission setup (host group, 0660,
    setgid). Both containers write the DB, so both need it — and it exists
    once rather than being copy-pasted into two scripts."""
    for name in ("tubematic-api", "tubematic-mcp"):
        assert services[name]["command"].startswith("/app/entrypoint.sh ")


def test_renderer_still_bypasses_the_entrypoint(services):
    """The worker replaces the CMD outright and calls os.umask(0) itself.
    Routing it through entrypoint.sh would change worker behaviour, which
    TMDEV-87 deliberately did not do."""
    assert services["tubematic-renderer"]["command"] == "python3 /app/api/worker.py"


def test_mcp_reuses_the_api_image_without_a_second_build(services):
    assert services["tubematic-mcp"]["image"] == "tubematic-renderer-image"
    assert "build" not in services["tubematic-mcp"]


# ── Health checks: each probes only its own process ────────────────────────

def test_api_healthcheck_probes_flask_only(services):
    """Asserts the PORT, not the host. These originally pinned
    `localhost:4000/health`, which coupled a test about which process is
    probed to the spelling of the loopback address -- and that spelling had
    to change: `localhost` resolves to ::1 as well as 127.0.0.1, and a probe
    using it can never succeed against an IPv4-only listener under a client
    that does not fall back (see docker-compose.yml's dashboard healthcheck).
    scripts/tests/test_gen_release_compose.py owns the host rule now."""
    probe = " ".join(services["tubematic-api"]["healthcheck"]["test"])
    assert ":4000/health" in probe
    assert "4100" not in probe


def test_mcp_healthcheck_probes_mcp_only(services):
    probe = " ".join(services["tubematic-mcp"]["healthcheck"]["test"])
    assert ":4100/health" in probe
    assert "4000" not in probe


def test_both_healthchecks_fail_on_a_bad_response(services):
    """`curl -fs` exits non-zero on 4xx/5xx. The old combined MCP probe was a
    bare `curl -s`, which passed on any HTTP response at all."""
    for name in ("tubematic-api", "tubematic-mcp"):
        assert "curl -fs" in " ".join(services[name]["healthcheck"]["test"])


# ── Dependency direction ───────────────────────────────────────────────────

def _depends(service):
    return set(service.get("depends_on", {}))


def test_dashboard_depends_on_the_api_not_mcp(services):
    assert _depends(services["tubematic-dashboard"]) == {"tubematic-api"}


def test_renderer_depends_on_the_api_not_mcp(services):
    assert _depends(services["tubematic-renderer"]) == {"tubematic-api"}


def test_flask_depends_on_nothing(services):
    """The dashboard and poller path must work with MCP down. A depends_on
    from api to mcp would invert that."""
    assert _depends(services["tubematic-api"]) == set()


def test_mcp_waits_for_the_api_at_startup_only(services):
    """Startup ordering, so schema creation stays single-writer on a fresh DB
    (both _init_db copies do check-then-ALTER). depends_on does not gate
    runtime — a later Flask crash never stops MCP."""
    assert _depends(services["tubematic-mcp"]) == {"tubematic-api"}
    assert services["tubematic-mcp"]["depends_on"]["tubematic-api"]["condition"] == "service_healthy"


# ── Ports ──────────────────────────────────────────────────────────────────

def test_api_publishes_4000_on_loopback_only(services):
    assert services["tubematic-api"]["ports"] == ["127.0.0.1:4000:4000"]


def test_mcp_publishes_4100_on_loopback_only(services):
    """MCP mutates pipeline state, spends money on paid APIs and renders
    agent-authored scene code, with no authentication of any kind."""
    assert services["tubematic-mcp"]["ports"] == ["127.0.0.1:4100:4100"]


def test_the_api_no_longer_publishes_the_mcp_port(services):
    assert not any("4100" in p for p in services["tubematic-api"]["ports"])


def test_the_renderer_publishes_nothing(services):
    assert "ports" not in services["tubematic-renderer"]


# ── Volumes: MCP gets the minimum its tools use ────────────────────────────

def _mounts(service):
    return {v.split(":")[1] for v in service["volumes"]}


def test_mcp_mounts_exactly_the_five_it_needs(services):
    """TUBEMATIC_DB, TUBEMATIC_JOBS_DIR, the generated scene tree, /logs, /backups.

    Deliberately an exact set: the standing instruction is that MCP gets no
    volume it does not use, and an exact assertion is what forces a yes/no
    answer rather than a shrug when someone adds one. /backups joined the list
    because every process runs migrations (it cannot assume Flask has), and a
    process that migrates must be able to back up first — one that silently
    could not would fail closed on every start.
    """
    assert _mounts(services["tubematic-mcp"]) == {
        "/data", "/jobs", "/app/remotion/src/scenes/generated", "/logs", "/backups",
    }


def test_mcp_does_not_mount_output_videos(services):
    """Nothing in mcp/ references it — voice previews are written by Flask's
    POST /voices/<id>/preview, not by an MCP tool."""
    assert "/output_videos" not in _mounts(services["tubematic-mcp"])


def test_mcp_does_not_mount_the_host_clock(services):
    """No MCP tool formats a local timestamp; hosttz.py is Flask-side."""
    assert "/etc/localtime" not in _mounts(services["tubematic-mcp"])


def test_renderer_mounts(services):
    assert _mounts(services["tubematic-renderer"]) == {
        "/output_videos", "/jobs", "/data", "/logs", "/backups",
        "/app/remotion/src/scenes/generated", "/etc/localtime", "/etc/timezone",
    }


def test_the_three_writers_all_mount_the_shared_logs_directory(services):
    """One directory, four writers (the fourth is host-side scripts/poll.py).
    A service that logs but does not mount it degrades to stdout-only silently,
    so its absence would show up as a gap in the dashboard, not as an error."""
    for name in ("tubematic-api", "tubematic-mcp", "tubematic-renderer"):
        assert "/logs" in _mounts(services[name]), name


def test_the_dashboard_does_not_mount_the_logs_directory(services):
    """It reads logs over HTTP from tubematic-api. That indirection is what
    makes "no Docker socket, no docker logs" true by construction — the
    dashboard has no filesystem route to a log file at all."""
    assert "/logs" not in _mounts(services["tubematic-dashboard"])


def test_the_dashboard_does_not_mount_the_backups_directory(services):
    """It has no database access and must not acquire any. A backup is a whole
    copy of a database whose settings table is the credential store."""
    assert "/backups" not in _mounts(services["tubematic-dashboard"])


# ── Environment ────────────────────────────────────────────────────────────

def _env(service):
    return dict(e.split("=", 1) for e in service["environment"])


def test_mcp_owns_the_mcp_port(services):
    assert _env(services["tubematic-mcp"])["MCP_PORT"] == "4100"
    assert "MCP_PORT" not in _env(services["tubematic-api"])


def test_mcp_points_at_the_shared_db_and_jobs_dir(services):
    env = _env(services["tubematic-mcp"])
    assert env["TUBEMATIC_DB"] == "/data/tubematic.db"
    assert env["TUBEMATIC_JOBS_DIR"] == "/jobs"


def test_mcp_is_given_no_renderer_url(services):
    """MCP never calls Flask over HTTP — nothing in mcp/ reads RENDERER_URL.
    Handing it one would imply a dependency that does not exist."""
    assert "RENDERER_URL" not in _env(services["tubematic-mcp"])


def test_no_service_reintroduces_env_file(services):
    """API keys live in the settings table (TMDEV-73), so `docker inspect`
    exposes no secrets. A new service is the easy place to lose that."""
    for name, service in services.items():
        assert "env_file" not in service, name


# ── Dockerfile default ─────────────────────────────────────────────────────

def test_dockerfile_cmd_names_a_process_for_the_entrypoint():
    """entrypoint.sh ends in `exec "$@"`, so a CMD of just the script would
    exec nothing and the container would exit immediately."""
    dockerfile = (REPO_ROOT / "renderer" / "Dockerfile").read_text()
    assert 'CMD ["/app/entrypoint.sh", "python3", "/app/api/server.py"]' in dockerfile
