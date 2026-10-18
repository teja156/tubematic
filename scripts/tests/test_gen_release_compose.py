"""Tests for scripts/gen_release_compose.py (TMDEV-91 Phase 2).

Drives the generator against the real docker-compose.yml, not a fixture --
a fixture would let the real file drift away from what the generator is
actually tested on and stop catching a real topology change.

Requires pyyaml, a maintainer/test-only dependency (see
onboard/tests/test_compose_topology.py for the existing precedent) --
deliberately not in scripts/requirements.txt since nothing at runtime reads
YAML.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, REPO_ROOT)

from tubematic_core.version import GITHUB_REPO  # noqa: E402
from tubematic_core.version import version as core_version  # noqa: E402

import gen_release_compose  # noqa: E402

COMPOSE = os.path.join(REPO_ROOT, "docker-compose.yml")
VERSION = "9.9.9"  # distinguishable from whatever VERSION currently holds
OWNER = "some-owner"

# Keys the generator must never touch. If it rewrote any of these, the
# release compose would become a second source of truth for them.
_UNTOUCHED_KEYS = (
    "volumes", "environment", "healthcheck", "depends_on",
    "shm_size", "restart", "container_name",
)


@pytest.fixture(scope="module")
def dev_text():
    return open(COMPOSE).read()


@pytest.fixture(scope="module")
def dev_services(dev_text):
    return yaml.safe_load(dev_text)["services"]


@pytest.fixture(scope="module")
def rendered():
    return gen_release_compose.generate(COMPOSE, VERSION, owner=OWNER)


@pytest.fixture(scope="module")
def parsed(rendered):
    return yaml.safe_load(rendered)


@pytest.fixture(scope="module")
def services(parsed):
    return parsed["services"]


def test_build_sections_become_pinned_ghcr_images(services):
    """A release install has no source tree, so a `build:` key pointing at
    renderer/Dockerfile would reference a path that does not exist."""
    assert "build" not in services["tubematic-api"]
    assert services["tubematic-api"]["image"] == (
        f"ghcr.io/{OWNER}/tubematic-backend:{VERSION}"
    )


def test_services_reusing_the_local_image_are_repointed_too(services):
    """tubematic-mcp and tubematic-renderer carry `image: tubematic-renderer-image`
    and no build section -- they reuse what tubematic-api builds. A release
    install builds nothing, so that local tag would never resolve."""
    for name in ("tubematic-mcp", "tubematic-renderer"):
        assert "build" not in services[name], name
        assert services[name]["image"] == (
            f"ghcr.io/{OWNER}/tubematic-backend:{VERSION}"
        ), name


def test_the_dashboard_gets_its_own_image(services):
    assert "build" not in services["tubematic-dashboard"]
    assert services["tubematic-dashboard"]["image"] == (
        f"ghcr.io/{OWNER}/tubematic-dashboard:{VERSION}"
    )


def test_every_published_port_is_bound_to_loopback(services):
    for name, service in services.items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), (name, port)


def test_an_already_loopback_port_is_left_alone(services, dev_services):
    # tubematic-api and tubematic-mcp are already loopback-bound in dev --
    # confirm the generator did not double-prefix them.
    for name in ("tubematic-api", "tubematic-mcp"):
        assert dev_services[name]["ports"][0].startswith("127.0.0.1:")
        assert services[name]["ports"] == dev_services[name]["ports"]


def test_the_dashboard_port_gains_the_loopback_prefix(services, dev_services):
    assert dev_services["tubematic-dashboard"]["ports"] == ["3000:3000"]
    assert services["tubematic-dashboard"]["ports"] == ["127.0.0.1:3000:3000"]


def test_volumes_environment_healthchecks_and_depends_on_survive_untouched(services, dev_services):
    """The generator exists so these cannot drift from the dev file. If it
    rewrote them, it would be a second source of truth."""
    for name, dev in dev_services.items():
        released = services[name]
        for key in _UNTOUCHED_KEYS:
            if key in dev or key in released:
                assert released.get(key) == dev.get(key), (name, key)


def test_no_healthcheck_probes_localhost(dev_services, services):
    """A healthcheck must address the loopback interface numerically, never
    by the name `localhost`.

    This is not style. A container's /etc/hosts maps `localhost` to BOTH
    127.0.0.1 and ::1, while every server here binds IPv4 only
    (dashboard/Dockerfile sets HOSTNAME=0.0.0.0; Flask and the MCP server
    bind 0.0.0.0 likewise). BusyBox wget -- the only HTTP client present in
    the dashboard's node:20-alpine runtime -- resolves `localhost` to the
    IPv6 address first and does NOT fall back to IPv4 when the connection is
    refused. Reproduced directly against a 0.0.0.0 listener in that image:
    `localhost` gives "can't connect to remote host: Connection refused",
    `127.0.0.1` succeeds.

    The dashboard shipped with `http://localhost:3000/` and its container was
    reported unhealthy on the first release run that ever exercised it. The
    failure is silent in the worst way -- nothing errors, the container simply
    never becomes healthy, and `docker compose up --wait` aborts the release.

    The curl-based probes survive `localhost` only because curl retries the
    other address family. Checking all of them keeps the next probe from
    being written by copying a URL that works for the wrong reason.
    """
    for source, label in ((dev_services, "docker-compose.yml"),
                          (services, "the generated release compose")):
        for name, svc in source.items():
            hc = svc.get("healthcheck")
            if not hc:
                continue
            probe = " ".join(hc["test"]) if isinstance(hc["test"], list) else str(hc["test"])
            assert "localhost" not in probe, (
                f"{label}: service {name!r} probes `localhost` ({probe!r}). "
                "Use 127.0.0.1 -- localhost can resolve to ::1, and BusyBox "
                "wget will not fall back to IPv4."
            )


def test_the_default_owner_is_the_repos_owner():
    """Derived from tubematic_core.version.GITHUB_REPO, never spelled a second
    time, so a repo move cannot leave release images pointing at the old owner."""
    assert gen_release_compose.DEFAULT_OWNER == GITHUB_REPO.split("/")[0]


def test_the_version_comes_from_the_version_file_not_a_literal():
    text = gen_release_compose.generate(COMPOSE, core_version(), owner=OWNER)
    assert f":{core_version()}" in text
    assert ":9.9.9" not in text


def test_the_output_names_itself_as_generated(rendered):
    header = "\n".join(rendered.split("\n")[:6])
    assert "generated" in header.lower()
    assert "gen_release_compose.py" in header
    assert VERSION in header


def test_the_generated_yaml_parses(parsed):
    assert "services" in parsed
    assert set(parsed["services"]) == {
        "tubematic-api", "tubematic-mcp", "tubematic-renderer", "tubematic-dashboard",
    }


def test_no_build_key_survives_anywhere(services):
    for name, service in services.items():
        assert "build" not in service, name


def test_top_level_name_and_volumes_pass_through_untouched(parsed, dev_text):
    dev = yaml.safe_load(dev_text)
    assert parsed["name"] == dev["name"]
    assert parsed["volumes"] == dev["volumes"]
    assert parsed["networks"] == dev["networks"]
    # Service tokens: a release install must mount the same files a dev one does.
    assert parsed["secrets"] == dev["secrets"]
    for name, svc in dev["services"].items():
        assert parsed["services"][name].get("secrets") == svc.get("secrets"), name


# ── version format ────────────────────────────────────────────────────────

def test_check_version_is_tag_safe_accepts_plain_semver():
    gen_release_compose.check_version_is_tag_safe("1.2.3")  # must not raise


def test_check_version_is_tag_safe_accepts_a_prerelease_suffix():
    gen_release_compose.check_version_is_tag_safe("1.2.3-rc.1")  # must not raise


def test_check_version_is_tag_safe_rejects_build_metadata():
    """Reproduces the finding: "1.0.0+build meta" is legal SemVer and an
    illegal Docker tag -- `+` and the space are both rejected."""
    with pytest.raises(ValueError) as exc_info:
        gen_release_compose.check_version_is_tag_safe("1.0.0+build meta")
    detail = str(exc_info.value)
    assert repr("+") in detail
    assert repr(" ") in detail


def test_invalid_version_chars_reports_each_offender_once():
    assert gen_release_compose.invalid_version_chars("1.0.0+a b+c") == ["+", " "]


def test_generate_refuses_an_unusable_version_before_touching_the_compose_file():
    """generate() is reachable directly (a maintainer running this script by
    hand, or build_release_tarball.py calling it) -- not only through
    check_release.py's pre-flight -- so it must refuse rather than emit a
    broken file."""
    with pytest.raises(ValueError):
        gen_release_compose.generate(COMPOSE, "1.0.0+bad", owner=OWNER)


def test_missing_pyyaml_exits_cleanly(monkeypatch):
    """The import guard must produce an actionable message, not a traceback --
    this is a release-time script and PyYAML is deliberately not a runtime
    dependency (see scripts/requirements.txt)."""
    import builtins
    import importlib

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "gen_release_compose", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit) as exc_info:
        importlib.import_module("gen_release_compose")
    assert "pyyaml" in str(exc_info.value).lower() or "PyYAML" in str(exc_info.value)

    monkeypatch.setattr(builtins, "__import__", real_import)
    monkeypatch.delitem(sys.modules, "gen_release_compose", raising=False)
    importlib.import_module("gen_release_compose")
