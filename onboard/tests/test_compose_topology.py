"""docker-compose.yml topology — five services, one process each (TMDEV-87, TMDEV-188).

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


def test_the_five_runtime_services(services):
    assert set(services) == {
        "tubematic-api", "tubematic-mcp", "tubematic-worker",
        "tubematic-renderer", "tubematic-dashboard",
    }


def test_the_worker_and_the_renderer_run_different_loops(services):
    """The housekeeping passes and the render claim used to share one loop, so
    a render held every publish, approval and notification for its length.
    Both containers starting the same file would put them back in one loop
    twice over: two publishing polls, and a render in the worker."""
    assert services["tubematic-worker"]["command"] == "python3 /app/api/worker.py"
    assert services["tubematic-renderer"]["command"] == "python3 /app/api/render_agent.py"


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


def test_the_worker_and_renderer_still_bypass_the_entrypoint(services):
    """Both replace the CMD outright and call os.umask(0) themselves. Routing
    them through entrypoint.sh would change their behaviour, which TMDEV-87
    deliberately did not do."""
    for name in ("tubematic-worker", "tubematic-renderer"):
        assert not services[name]["command"].startswith("/app/entrypoint.sh"), name


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


def test_worker_depends_on_the_api_not_mcp(services):
    assert _depends(services["tubematic-worker"]) == {"tubematic-api"}


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


def test_the_renderer_and_the_worker_publish_nothing(services):
    for name in ("tubematic-worker", "tubematic-renderer"):
        assert "ports" not in services[name], name


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
    """Exact: the built-in renderer has no database. It reaches the pipeline
    only through the render gateway, as a renderer on another machine does, so
    /data, /output_videos and /backups are gone (the gateway writes the
    uploaded mp4; nothing here migrates). The scene tree stays because its
    renders compile it; /jobs stays for the stills server; /logs for its trail."""
    assert _mounts(services["tubematic-renderer"]) == {
        "/jobs", "/logs", "/app/remotion/src/scenes/generated",
        "/etc/localtime", "/etc/timezone",
    }


def test_the_renderer_reads_the_jobs_tree_only(services):
    """Read-only: the stills server reads job files, and a render works from
    its downloaded bundle, so nothing in this container may write a job's
    files — the API, MCP and the worker own them."""
    jobs = [v for v in services["tubematic-renderer"]["volumes"] if v.split(":")[1] == "/jobs"]
    assert jobs == ["jobs-data:/jobs:ro"]


def test_worker_mounts(services):
    """Exact, like MCP's: retention deletes mp4s (/output_videos) and job
    directories (/jobs); Auto Pilot and scheduling count host-zone days
    (/etc/localtime). It never touches a scene, so no scenes-generated."""
    assert _mounts(services["tubematic-worker"]) == {
        "/output_videos", "/jobs", "/data", "/logs", "/backups",
        "/etc/localtime", "/etc/timezone",
    }


def test_the_four_writers_all_mount_the_shared_logs_directory(services):
    """One directory, five writers (the fifth is host-side scripts/poll.py).
    A service that logs but does not mount it degrades to stdout-only silently,
    so its absence would show up as a gap in the dashboard, not as an error."""
    for name in ("tubematic-api", "tubematic-mcp", "tubematic-worker", "tubematic-renderer"):
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


def test_the_renderer_is_pointed_at_the_gateway_not_the_database(services):
    env = _env(services["tubematic-renderer"])
    assert env["TUBEMATIC_GATEWAY_URL"] == "https://tubematic-api:4443"
    assert env["TUBEMATIC_RENDERER_BUILTIN"] == "1"
    # A leftover TUBEMATIC_DB would let a stray import open a fresh empty
    # database in the container's writable layer instead of failing.
    assert "TUBEMATIC_DB" not in env
    assert "OUTPUT_BASE_PATH" not in env


def test_the_api_serves_the_gateway_on_4443_without_publishing_it(services):
    """The built-in renderer reaches the gateway over the compose network.
    Publishing 4443 is opt-in (an override for remote renderers), because it
    is the one port meant to be reachable from other machines."""
    api = services["tubematic-api"]
    assert _env(api)["TUBEMATIC_GATEWAY_PORT"] == "4443"
    assert not any("4443" in p for p in api["ports"])


# ── Secrets ────────────────────────────────────────────────────────────────

def test_every_secret_file_lives_in_the_secrets_directory(services):
    """The names are the files tubematic_core.auth.ensure_secrets writes, which
    onboarding and upgrade.py run before `up` (a missing file stops `up`)."""
    from tubematic_core import auth
    declared = yaml.safe_load(COMPOSE.read_text())["secrets"]
    assert set(declared) == set(auth.SECRET_NAMES) | set(auth.TLS_NAMES)
    for name, spec in declared.items():
        assert spec["file"] == f"${{HOME}}/.tubematic-data/secrets/{name}", name


def test_the_gateway_key_never_leaves_the_api(services):
    """The TLS key is what a renderer's pin trusts; only the process serving
    the gateway may hold it. The renderer gets the certificate to pin and its
    own token, and nothing that would let it pass for the API or MCP."""
    holders = {name for name, svc in services.items()
               if "render_tls_key" in (svc.get("secrets") or [])}
    assert holders == {"tubematic-api"}
    assert set(services["tubematic-api"]["secrets"]) == {
        "api_token", "builtin_renderer_token", "render_tls_key", "render_tls_cert"}
    assert set(services["tubematic-renderer"]["secrets"]) == {
        "builtin_renderer_token", "render_tls_cert"}


def test_the_test_stack_renders_through_the_gateway_too():
    """docker-compose.test.yml mirrors the production wiring: a test renderer
    with a database mount would hide a renderer that still reads it."""
    test = yaml.safe_load((REPO_ROOT / "docker-compose.test.yml").read_text())
    renderer = test["services"]["tubematic-renderer-test"]
    assert [v.split(":", 1)[1] for v in renderer["volumes"]] == ["/jobs:ro"]
    assert _env(renderer)["TUBEMATIC_GATEWAY_URL"] == "https://tubematic-api-test:4443"
    assert set(renderer["secrets"]) == {"builtin_renderer_token", "render_tls_cert"}
    assert {"builtin_renderer_token", "render_tls_key", "render_tls_cert"} <= set(
        test["services"]["tubematic-api-test"]["secrets"])
    for name in ("builtin_renderer_token", "render_tls_key", "render_tls_cert"):
        assert test["secrets"][name]["file"] == f"./dashboard/tests/e2e/secrets/{name}"


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
