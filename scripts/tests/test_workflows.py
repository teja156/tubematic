"""Structural tests for the GitHub Actions workflows under .github/workflows/
(TMDEV-91 Phase 3).

These workflows have never executed: GitHub Actions runs only on GitHub, this
repo has never had a .github/ directory, and actionlint is not installed
here. This file is the substitute -- it cannot prove a workflow *works*, but
it can catch the class of error that would otherwise only surface ten minutes
into a real run: a typo'd `needs:` reference, an unpinned third-party action,
a matrix that has silently drifted from the suite directories actually on
disk, and a job whose trigger condition regresses to run somewhere it must
never run.

Requires pyyaml -- a maintainer/test-only dependency, deliberately not in any
service's requirements.txt (see scripts/tests/test_gen_release_compose.py for
the existing precedent).
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # scripts/

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")
CI_PATH = os.path.join(WORKFLOWS_DIR, "ci.yml")
RELEASE_PATH = os.path.join(WORKFLOWS_DIR, "release.yml")

# The six suite directories the pre-existing conftest.py/sys.path collision
# forces to run one-at-a-time (see HANDOFF.md / CLAUDE.md). Not used as the
# source of truth for the matrix test below -- that test derives this list
# itself from the filesystem so a renamed or added suite directory fails it
# rather than being silently skipped. Used only by the other tests that need
# *a* suite path to exercise, where deriving it fresh would just be noise.
_KNOWN_SUITE_DIRS = (
    "tubematic_core/tests",
    "mcp/tests",
    "renderer/api/tests",
    "onboard/tests",
    "scripts/tests",
    "vqa/tests",
)


@pytest.fixture(scope="module")
def ci_text():
    if not os.path.exists(CI_PATH):
        pytest.fail(f"{CI_PATH} does not exist yet")
    with open(CI_PATH) as f:
        return f.read()


@pytest.fixture(scope="module")
def ci(ci_text):
    return yaml.safe_load(ci_text)


@pytest.fixture(scope="module")
def jobs(ci):
    return ci["jobs"]


def test_ci_workflow_parses(ci):
    """The most basic possible check, and still a real one -- a bad indent
    or a stray tab fails this before it ever reaches GitHub."""
    assert "jobs" in ci
    assert isinstance(ci["jobs"], dict)
    assert len(ci["jobs"]) > 0


def test_every_job_needs_reference_resolves_to_a_real_job(jobs):
    """A typo'd `needs:` fails ten minutes into a run, not at author time."""
    job_names = set(jobs.keys())
    for name, job in jobs.items():
        needs = job.get("needs")
        if needs is None:
            continue
        needed = [needs] if isinstance(needs, str) else needs
        for ref in needed:
            assert ref in job_names, (
                f"job {name!r} needs {ref!r}, which is not a job in this "
                f"workflow (known jobs: {sorted(job_names)})"
            )


# Matches `owner/repo@ref` (a third-party or first-party GitHub action).
# Local actions (`./path/to/action`) and reusable workflow calls
# (`./.github/workflows/x.yml` or `owner/repo/.github/workflows/x.yml@ref`)
# are excluded by requiring no leading `.` or `/` before the `@`.
_ACTION_USES_RE = re.compile(r"^[^./][^@]*@(.+)$")

# A ref is "pinned" if it is not a floating branch name. GitHub tags are
# conventionally `v4`, `v4.1.0`, or a full commit SHA -- all of those are
# fine; `main`, `master`, `latest` and bare `HEAD` are not.
_FLOATING_REFS = {"main", "master", "latest", "head", "trunk"}


def test_every_action_is_pinned_to_a_version(jobs):
    """An unpinned action is someone else's code running with our registry
    credentials, silently updated whenever they push."""
    found_any = False
    for name, job in jobs.items():
        for step in job.get("steps", []) or []:
            uses = step.get("uses")
            if not uses:
                continue
            m = _ACTION_USES_RE.match(uses)
            if not m:
                # A local action or a reusable-workflow call within this
                # repo -- not third-party code, nothing to pin.
                continue
            found_any = True
            ref = m.group(1)
            assert ref.lower() not in _FLOATING_REFS, (
                f"job {name!r} step {uses!r} is pinned to a floating ref "
                f"{ref!r} -- pin to a released major version or a SHA"
            )
            # A released major version tag looks like v4 / v4.1.0; a full
            # commit SHA is 40 hex chars. Reject anything else (e.g. a
            # branch name that happens not to be in _FLOATING_REFS).
            is_version_tag = re.match(r"^v\d+(\.\d+){0,2}$", ref)
            is_sha = re.match(r"^[0-9a-f]{40}$", ref)
            assert is_version_tag or is_sha, (
                f"job {name!r} step {uses!r} is not pinned to a released "
                f"version tag or a commit SHA (got {ref!r})"
            )
    assert found_any, "expected at least one third-party action in ci.yml"


def test_the_python_matrix_covers_exactly_the_suite_directories_that_exist(jobs):
    """Derived from the filesystem, not a hardcoded list -- a renamed or
    added suite directory should fail this rather than be silently
    skipped."""
    # Discover every directory in the repo that is itself named "tests" and
    # contains at least one test_*.py file, expressed relative to the repo
    # root with forward slashes (matching how the workflow will reference
    # it). This intentionally does not special-case the six known
    # directories -- if a seventh appears anywhere in the tree, this must
    # notice it.
    discovered = set()
    skip_dirs = {
        ".git", "node_modules", ".venv", "venv", "__pycache__",
        ".worktrees", ".superpowers",
    }
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        if os.path.basename(dirpath) != "tests":
            continue
        if not any(f.startswith("test_") and f.endswith(".py") for f in filenames):
            continue
        rel = os.path.relpath(dirpath, REPO_ROOT).replace(os.sep, "/")
        discovered.add(rel)

    assert discovered, "found no suite directories on disk -- test is broken"

    python_tests_job = jobs["python-tests"]
    matrix = python_tests_job["strategy"]["matrix"]
    listed = set(matrix["suite"])

    assert listed == discovered, (
        f"ci.yml's python-tests matrix lists {sorted(listed)}, but the "
        f"filesystem has {sorted(discovered)} -- a suite directory was "
        f"added, renamed, or removed without updating the workflow"
    )


def test_remotion_job_does_not_run_npm_run_lint(jobs):
    """That script is `eslint src && tsc` and eslint has two pre-existing
    errors. tsc is what validate_job actually runs."""
    remotion_job = jobs["remotion"]
    run_lines = [
        step["run"] for step in remotion_job.get("steps", []) or [] if "run" in step
    ]
    combined = "\n".join(run_lines)
    assert "npm run lint" not in combined
    assert "tsc" in combined, "remotion job must run tsc directly"


def test_the_e2e_job_never_runs_on_a_pull_request(jobs):
    """The e2e job builds two images cold (12-20 minutes) -- affordable on a
    tag or manual dispatch, not on every pull request."""
    e2e_job = jobs["e2e"]
    condition = e2e_job.get("if")
    assert condition, "e2e job must have an `if:` gate limiting when it runs"
    assert isinstance(condition, str)
    # The condition must never grant `pull_request` a path to true. The
    # simplest sound check here: the literal event name that would need to
    # appear for a pull_request run to pass is never mentioned at all, so
    # there is no way the expression can evaluate true for that event.
    assert "pull_request" not in condition
    # And it must be positively scoped to the two allowed triggers -- an
    # `if:` that merely omits "pull_request" but is otherwise unconditional
    # (e.g. `if: true`) would also pass the assertion above while running
    # everywhere, including PRs from workflow_call. Require it to actually
    # reference both allowed paths.
    assert "workflow_dispatch" in condition
    assert "refs/tags" in condition


def test_the_e2e_comment_does_not_overclaim_verification(ci_text):
    """The comment above the e2e job reports a real, but local, Kasm-session
    run of the underlying commands, and infers that its 8 failures trace to
    a fix already on main. Both of those are one step short of "verified":
    the *workflow* has never executed on GitHub at all (see this file's own
    module docstring), and the fork-point diagnosis has not been confirmed
    by actually rebasing past the fix and rerunning. A prior draft of this
    comment stated the diagnosis as settled fact -- pin the hedge so that
    overclaim can't quietly creep back in."""
    lines = ci_text.splitlines()
    e2e_line = next(i for i, line in enumerate(lines) if line.strip() == "e2e:")
    comment_lines = []
    i = e2e_line - 1
    while i >= 0 and lines[i].strip().startswith("#"):
        comment_lines.append(lines[i])
        i -= 1
    comment = "\n".join(reversed(comment_lines))

    assert comment, "expected a comment block directly above the e2e job"
    assert "re-verified" in comment, (
        "the e2e comment must say the fork-point diagnosis has not been "
        "re-verified -- dropping this hedge restates it as settled fact"
    )
    for overclaim in (
        "settled fact",
        "has been verified",
        "confirmed by rerunning",
        "workflow has run",
        "workflow has been verified",
    ):
        assert overclaim not in comment, (
            f"the e2e comment overclaims verification with {overclaim!r}"
        )


def test_ci_is_callable_and_dispatchable(ci):
    """release.yml depends on `workflow_call`; running the e2e job on demand
    depends on `workflow_dispatch`. Both triggers are load-bearing, not
    decorative."""
    # PyYAML's safe_load follows YAML 1.1, which resolves the bare word `on`
    # to the boolean True -- GitHub itself parses workflows the same way
    # (it's exactly why `on:` works at all), so the trigger block's key
    # comes back as True, not the string "on". Check both so this survives
    # either a future PyYAML change or a quoted `"on":` in the file.
    triggers = ci[True] if True in ci else ci.get("on")
    assert triggers is not None, "ci.yml has no `on:` trigger block"
    assert isinstance(triggers, dict)
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers
    assert "pull_request" in triggers
    assert "push" in triggers


def test_the_push_trigger_actually_fires_on_branch_pushes(ci):
    """A `push` block that defines only `tags-ignore` does NOT run on branch
    pushes. GitHub: "If only branches or only tags are defined, the workflow
    will not run for events affecting the undefined ref type." Defining just
    the tag side leaves the branch side undefined, so every branch push is
    silently ignored -- no error, no skipped run, nothing in the Actions tab.

    This shipped broken: `tags-ignore` alone, which meant CI had never once
    run on a branch push, including on the default branch. The pre-existing
    trigger test asserted only that the key "push" was *present*, which stayed
    green throughout -- asserting a key exists says nothing about whether the
    event it names can ever fire.
    """
    triggers = ci[True] if True in ci else ci.get("on")
    push = triggers["push"]
    assert isinstance(push, dict), (
        "ci.yml's push trigger must be a mapping carrying a branches filter")
    assert "branches" in push, (
        "ci.yml's push trigger defines no `branches` filter. With `tags-ignore` "
        "present, that leaves the branch ref type undefined and NO branch push "
        "will trigger CI at all."
    )
    assert "**" in push["branches"], (
        f"ci.yml's push branches filter is {push['branches']!r}; it must include "
        "'**' so CI runs on every branch, not a subset."
    )
    # The two filters must not be positive/ignore pairs on the SAME ref type --
    # that combination GitHub rejects outright.
    assert "branches-ignore" not in push, (
        "`branches` and `branches-ignore` cannot both be set for one event")
    assert "tags" not in push, (
        "`tags` and `tags-ignore` cannot both be set for one event")


def test_all_referenced_suite_dirs_actually_exist_on_disk(jobs):
    """Belt-and-braces on top of the matrix-vs-filesystem test: every path
    the matrix lists must be a real, existing directory relative to the
    repo root, not just a string that happens to match."""
    matrix = jobs["python-tests"]["strategy"]["matrix"]
    for suite in matrix["suite"]:
        assert os.path.isdir(os.path.join(REPO_ROOT, suite)), suite


def test_python_matrix_job_installs_all_three_requirements_files(jobs):
    """Several suites cross-import (vqa/tests needs flask/httpx/fastmcp,
    onboard/tests and scripts/tests need pyyaml) -- per-suite dependency
    pinning is a maintenance trap that fails only in CI. This pins the
    install to cover all three requirements files, not a subset."""
    steps = jobs["python-tests"]["steps"]
    combined = "\n".join(s.get("run", "") for s in steps)
    for req in (
        "scripts/requirements.txt",
        "mcp/requirements.txt",
        "renderer/api/requirements.txt",
    ):
        assert req in combined, f"python-tests job never installs {req}"
    assert "pytest" in combined
    assert "pyyaml" in combined.lower()


def test_compose_check_job_validates_both_compose_files(jobs):
    """The dev compose file and the generated release compose are two
    different documents -- a syntax error introduced by
    gen_release_compose.py into the release-only shape (image:/ports:)
    would not be caught by validating docker-compose.yml alone."""
    steps = jobs["compose-check"]["steps"]
    combined = "\n".join(s.get("run", "") for s in steps)
    assert "docker compose" in combined
    assert "config" in combined
    assert "gen_release_compose.py" in combined


# ─────────────────────────────────────────────────────────────────────────
# release.yml (TMDEV-91 Phase 3, task 2)
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def release_text():
    if not os.path.exists(RELEASE_PATH):
        pytest.fail(f"{RELEASE_PATH} does not exist yet")
    with open(RELEASE_PATH) as f:
        return f.read()


@pytest.fixture(scope="module")
def release(release_text):
    return yaml.safe_load(release_text)


@pytest.fixture(scope="module")
def release_jobs(release):
    return release["jobs"]


def _steps_of(job):
    return job.get("steps", []) or []


def _run_text(job):
    return "\n".join(s.get("run", "") for s in _steps_of(job))


def _uses_text(job):
    return "\n".join(s.get("uses", "") for s in _steps_of(job))


def _needs_of(job):
    needs = job.get("needs")
    if needs is None:
        return []
    return [needs] if isinstance(needs, str) else list(needs)


def _ancestors(job_name, jobs):
    """Every job name reachable by walking `needs:` backward from
    `job_name`, transitively. Ordering in this workflow is allowed to be an
    indirect chain (job C needs B needs A), not only a single direct edge,
    so the ordering test below must walk the whole graph rather than check
    one hop."""
    seen = set()
    stack = list(_needs_of(jobs[job_name]))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(_needs_of(jobs.get(n, {})))
    return seen


def test_release_workflow_parses(release):
    """The most basic possible check, and still a real one -- a bad indent
    or a stray tab fails this before it ever reaches GitHub."""
    assert "jobs" in release
    assert isinstance(release["jobs"], dict)
    assert len(release["jobs"]) > 0


def test_release_triggers_only_on_version_tags(release):
    """A Release and a set of pushed GHCR images must never fire from an
    ordinary branch push, a pull request, or a manual dispatch -- only from
    pushing a tag matching v*.*.*."""
    triggers = release[True] if True in release else release.get("on")
    assert triggers is not None, "release.yml has no `on:` trigger block"
    assert set(triggers.keys()) == {"push"}, (
        f"release.yml must trigger on `push` only, got {sorted(triggers.keys())}"
    )
    tags = triggers["push"].get("tags")
    assert tags, "release.yml's push trigger must be scoped to `tags:`"
    assert tags == ["v*.*.*"], f"expected the tag filter ['v*.*.*'], got {tags}"
    assert "branches" not in triggers["push"], (
        "release.yml's push trigger must not also fire on branch pushes"
    )


def test_release_reuses_the_ci_workflow(release_jobs):
    """Not a second copy of the test jobs -- one definition. A job here
    must call ci.yml via `uses:` (workflow_call) rather than re-declaring
    its python-tests/dashboard/remotion/compose-check/e2e jobs."""
    reusing_jobs = [
        name for name, job in release_jobs.items()
        if isinstance(job.get("uses"), str)
        and job["uses"].endswith(".github/workflows/ci.yml")
    ]
    assert reusing_jobs, "no job in release.yml reuses ci.yml via `uses:`"

    ci_job_names = {"python-tests", "dashboard", "remotion", "compose-check", "e2e"}
    assert not (ci_job_names & release_jobs.keys()), (
        "release.yml re-declares one of ci.yml's own jobs instead of "
        "reusing it via workflow_call -- exactly the duplicated test "
        "matrix this ticket exists to remove"
    )


def test_every_release_job_needs_reference_resolves_to_a_real_job(release_jobs):
    """A typo'd `needs:` fails ten minutes into a run, not at author time --
    same rationale as ci.yml's version of this test."""
    job_names = set(release_jobs.keys())
    for name, job in release_jobs.items():
        for ref in _needs_of(job):
            assert ref in job_names, (
                f"job {name!r} needs {ref!r}, which is not a job in "
                f"release.yml (known jobs: {sorted(job_names)})"
            )


def test_every_release_action_is_pinned_to_a_version(release_jobs):
    """Same rule as ci.yml -- an unpinned action here is someone else's
    code running with GHCR-push and Release-creation credentials."""
    found_any = False
    for name, job in release_jobs.items():
        for step in _steps_of(job):
            uses = step.get("uses")
            if not uses:
                continue
            m = _ACTION_USES_RE.match(uses)
            if not m:
                # A local action or a reusable-workflow call within this
                # repo (e.g. ./.github/workflows/ci.yml) -- not third-party
                # code, nothing to pin.
                continue
            found_any = True
            ref = m.group(1)
            assert ref.lower() not in _FLOATING_REFS, (
                f"job {name!r} step {uses!r} is pinned to a floating ref "
                f"{ref!r} -- pin to a released major version or a SHA"
            )
            is_version_tag = re.match(r"^v\d+(\.\d+){0,2}$", ref)
            is_sha = re.match(r"^[0-9a-f]{40}$", ref)
            assert is_version_tag or is_sha, (
                f"job {name!r} step {uses!r} is not pinned to a released "
                f"version tag or a commit SHA (got {ref!r})"
            )
    assert found_any, "expected at least one third-party action in release.yml"


def test_both_images_are_pushed_under_the_bare_version_tag(release_jobs):
    """The bare `X.Y.Z` tag is the ONLY image tag this project publishes, and
    gen_release_compose.py bakes exactly that form into the tarball's compose
    file. If the workflow ever pushed a different form -- `vX.Y.Z`, a SHA, a
    `latest` -- every release install would 404 on `docker compose pull`, and
    the smoke test would fail by construction rather than by regression.

    There was no test here while three tags were being pushed, which was
    survivable only because one of the three happened to be the right one.
    With a single tag there is no redundancy left to hide a mistake.
    """
    steps = release_jobs["push-images"]["steps"]
    pushed = {}
    for step in steps:
        if (step.get("uses") or "").startswith("docker/build-push-action"):
            tags = [t.strip() for t in (step["with"]["tags"] or "").splitlines() if t.strip()]
            pushed[step.get("name", "?")] = tags

    assert len(pushed) == 2, f"expected two build-push steps, got {sorted(pushed)}"
    for name, tags in pushed.items():
        assert len(tags) == 1, f"{name}: expected exactly one image tag, got {tags}"
        tag = tags[0]
        assert tag.endswith("${{ needs.preflight.outputs.version }}"), (
            f"{name}: image tag {tag!r} does not end in the bare version -- the "
            "release compose references the bare form and nothing else"
        )
        assert ":v${{" not in tag, (
            f"{name}: image tag {tag!r} carries a `v` prefix; the compose file "
            "generated for this release uses the bare version"
        )
        assert "github.sha" not in tag, (
            f"{name}: image tag {tag!r} is a commit SHA, not the version")


def test_the_smoke_test_runs_after_the_image_push_and_before_the_release(release_jobs):
    """Encoded as `needs:` ordering. Reversed, a broken artifact becomes a
    published Release, and a Release cannot be un-published (spec section
    4.3 / decision D15). Jobs are identified by what they do, not an
    assumed literal name, so a rename doesn't silently defeat this test."""
    push_jobs = [
        name for name, job in release_jobs.items()
        if "build-push-action" in _uses_text(job)
    ]
    assert push_jobs, "no job in release.yml pushes images (docker/build-push-action)"

    smoke_jobs = [
        name for name, job in release_jobs.items()
        if "docker compose" in _run_text(job) and " up" in _run_text(job)
    ]
    assert smoke_jobs, "no job in release.yml brings up the release compose stack"

    release_creating_jobs = [
        name for name, job in release_jobs.items()
        if "action-gh-release" in _uses_text(job)
    ]
    assert release_creating_jobs, "no job in release.yml creates the GitHub Release"

    for smoke in smoke_jobs:
        ancestors = _ancestors(smoke, release_jobs)
        for push in push_jobs:
            assert push in ancestors, (
                f"smoke-test job {smoke!r} does not depend, directly or "
                f"transitively, on image-push job {push!r} -- it could run "
                f"before the images it needs to pull even exist"
            )

    for rel in release_creating_jobs:
        ancestors = _ancestors(rel, release_jobs)
        for smoke in smoke_jobs:
            assert smoke in ancestors, (
                f"release-creating job {rel!r} does not depend, directly "
                f"or transitively, on smoke-test job {smoke!r} -- a broken "
                f"artifact could be published as a Release"
            )


def test_release_requests_only_the_permissions_it_needs(release):
    """`contents: write` to create the Release, `packages: write` to push
    to GHCR -- nothing broader. A workflow holding registry credentials
    with more permission than it needs is a standing risk."""
    permissions = release.get("permissions")
    assert permissions == {"contents": "write", "packages": "write"}, (
        f"release.yml must request exactly contents:write and "
        f"packages:write, got {permissions!r}"
    )


def test_the_owner_is_passed_explicitly_not_defaulted(release_jobs):
    """scripts/check_release.py and scripts/build_release_tarball.py both
    default --owner to a hardcoded namespace -- relying on that default
    would publish a fork's images into someone else's GHCR namespace."""
    combined = []
    for job in release_jobs.values():
        for step in _steps_of(job):
            if "run" in step:
                combined.append(step["run"])
            if "build-push-action" in step.get("uses", ""):
                combined.append(str(step.get("with", {})))
    text = "\n".join(combined)
    assert "--owner" in text, "no script invocation passes --owner explicitly"
    assert "github.repository_owner" in text, (
        "--owner must be github.repository_owner, not a hardcoded namespace"
    )


def test_the_smoke_test_extracts_the_tarball_rather_than_using_the_checkout(release_jobs):
    """Using the checkout would test the source tree, not the artifact --
    the whole point of this job is that only the artifact proves the
    artifact."""
    smoke_jobs = [
        name for name, job in release_jobs.items()
        if "docker compose" in _run_text(job) and " up" in _run_text(job)
    ]
    assert smoke_jobs, "no job in release.yml brings up the release compose stack"

    for name in smoke_jobs:
        job = release_jobs[name]
        uses_list = [s.get("uses", "") for s in _steps_of(job)]
        assert not any(u.startswith("actions/checkout") for u in uses_list), (
            f"smoke-test job {name!r} checks out the repository -- it must "
            f"extract the published tarball instead, nothing from the checkout"
        )
        assert "tar -x" in _run_text(job) or "tar x" in _run_text(job), (
            f"smoke-test job {name!r} never extracts a tarball"
        )


def test_the_smoke_tests_curl_checks_retry_rather_than_fire_once(release_jobs):
    """Even with docker compose --wait reporting healthy, a single unretried
    curl at a container boundary is fragile -- a dashboard whose process is
    running but hasn't bound its port yet reads as a broken artifact rather
    than a race. This pins retry options on every curl in the smoke-test job
    so a later simplification can't quietly reintroduce the flake."""
    smoke_jobs = [
        name for name, job in release_jobs.items()
        if "docker compose" in _run_text(job) and " up" in _run_text(job)
    ]
    assert smoke_jobs, "no job in release.yml brings up the release compose stack"

    for name in smoke_jobs:
        job = release_jobs[name]
        curl_steps = [
            s for s in _steps_of(job) if "curl " in s.get("run", "")
        ]
        assert curl_steps, f"smoke-test job {name!r} has no curl step to check"
        for step in curl_steps:
            run = step["run"]
            assert "--retry" in run, (
                f"job {name!r} step {step.get('name')!r} curl has no --retry "
                f"-- a single unretried request at a container boundary is "
                f"exactly the flake this exists to prevent"
            )
            assert "--retry-connrefused" in run, (
                f"job {name!r} step {step.get('name')!r} curl must retry on "
                f"connection-refused too -- that's the actual failure mode "
                f"when the process hasn't bound its port yet"
            )
            # Bounded, not indefinite -- a genuinely dead service must still
            # fail this step promptly rather than hang the job.
            assert "--retry-max-time" in run or "--max-time" in run, (
                f"job {name!r} step {step.get('name')!r} curl retries with "
                f"no time bound -- a dead service would hang this step"
            )


def test_the_smoke_test_creates_every_secret_file_compose_mounts_before_up(release_jobs, tmp_path):
    """Compose refuses to start a service whose secret file is missing, and
    the smoke test skips onboarding, which is what normally writes them. The
    v2.0.0 tag run failed exactly there ("bind source path does not exist").
    The step is run for real against a scratch HOME, and every `secrets:`
    file in docker-compose.yml must exist afterwards -- so a fourth secret
    added to compose without one here fails this test, not the next release."""
    [(name, job)] = [
        (n, j) for n, j in release_jobs.items()
        if "docker compose" in _run_text(j) and " up" in _run_text(j)
    ]
    steps = _steps_of(job)
    names = [s.get("name", "") for s in steps]
    tokens = names.index("Create the service tokens a real install gets from onboarding")
    up = next(i for i, s in enumerate(steps) if "docker compose" in s.get("run", "")
              and " up" in s.get("run", ""))
    assert tokens < up, f"{name}: the tokens must exist before `docker compose up`"

    proc = subprocess.run(["bash", "-e", "-c", steps[tokens]["run"]], cwd=REPO_ROOT,
                          capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "TUBEMATIC_SECRETS_DIR"} | {"HOME": str(tmp_path)})
    assert proc.returncode == 0, proc.stderr

    with open(os.path.join(REPO_ROOT, "docker-compose.yml")) as fh:
        compose_secrets = yaml.safe_load(fh)["secrets"]
    assert compose_secrets
    for secret, spec in compose_secrets.items():
        path = spec["file"].replace("${HOME}", str(tmp_path))
        assert os.path.isfile(path) and open(path).read().strip(), (
            f"compose mounts secret {secret!r} from {spec['file']}, which the smoke test never creates")


def test_a_prerelease_version_is_published_as_a_github_prerelease(release_jobs):
    """A `-suffix` version (2.1.0-rc.1) must be a GitHub prerelease (TMDEV-114).
    The action defaults `prerelease` to false, which published a release
    candidate as an ordinary release that GitHub could list as "Latest". The
    dashboard's update check also filters by tag, so this is not its only guard,
    but GitHub's own release page and /releases/latest depend on it."""
    steps = [
        (name, step)
        for name, job in release_jobs.items()
        for step in _steps_of(job)
        if "action-gh-release" in step.get("uses", "")
    ]
    assert len(steps) == 1, f"expected one Release-creating step, found {len(steps)}"
    name, step = steps[0]
    assert step.get("with", {}).get("prerelease") == (
        "${{ contains(needs.preflight.outputs.version, '-') }}"
    )
    assert "preflight" in _ancestors(name, release_jobs)


# ── Docs site (docs.tubematic.ai) ─────────────────────────────────────────
# release.yml's publish-docs job and docs-site.yml both run the composite
# action .github/actions/sync-docs-site, which syncs docs/ into the
# tubematic-docs repo, builds it and pushes. TUBEMATIC_DOCS_TOKEN is an
# *environment* secret: a job that does not name the environment reads it as
# an empty string, so every job using it must declare it itself.

DOCS_SITE_PATH = os.path.join(WORKFLOWS_DIR, "docs-site.yml")
SYNC_ACTION_PATH = os.path.join(REPO_ROOT, ".github", "actions", "sync-docs-site", "action.yml")
DOCS_ENVIRONMENT = "TubeMatic"
DOCS_TOKEN = "${{ secrets.TUBEMATIC_DOCS_TOKEN }}"


def _load(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def _sync_steps(job):
    return [s for s in _steps_of(job) if s.get("uses") == "./.github/actions/sync-docs-site"]


def test_publish_docs_runs_only_after_the_release_is_published(release_jobs):
    """Docs move only once the Release exists, and the job gates nothing:
    no other release job may depend on it."""
    assert "release" in _ancestors("publish-docs", release_jobs)
    for name, other in release_jobs.items():
        assert "publish-docs" not in _needs_of(other), (
            f"job {name!r} depends on publish-docs; a docs failure must never block a release")


def test_every_docs_sync_job_names_the_environment_and_passes_the_token(release_jobs):
    docs_jobs = _load(DOCS_SITE_PATH)["jobs"]
    jobs = {"release.yml publish-docs": release_jobs["publish-docs"],
            **{f"docs-site.yml {n}": j for n, j in docs_jobs.items()}}
    for name, job in jobs.items():
        assert job.get("environment") == DOCS_ENVIRONMENT, (
            f"{name} must declare environment {DOCS_ENVIRONMENT!r} or the token reads as empty")
        [step] = _sync_steps(job)
        assert step["with"]["token"] == DOCS_TOKEN, name


def test_docs_sync_jobs_share_one_concurrency_group(release_jobs):
    """A develop sync and a release sync both push to the site repo; they
    must queue, not race."""
    docs = _load(DOCS_SITE_PATH)
    groups = {release_jobs["publish-docs"]["concurrency"]["group"], docs["concurrency"]["group"]}
    assert len(groups) == 1, groups
    assert release_jobs["publish-docs"]["concurrency"]["cancel-in-progress"] is False
    assert docs["concurrency"]["cancel-in-progress"] is False


def test_docs_sync_needs_only_read_access_here(release_jobs):
    """The site repo is reached with the PAT; this repo is only read."""
    assert release_jobs["publish-docs"]["permissions"] == {"contents": "read"}
    assert _load(DOCS_SITE_PATH)["permissions"] == {"contents": "read"}


def test_docs_site_workflow_runs_on_develop_docs_pushes_and_by_hand_only():
    docs = _load(DOCS_SITE_PATH)
    on = docs.get("on", docs.get(True))  # PyYAML reads a bare `on:` key as True
    assert set(on) == {"push", "workflow_dispatch"}, on
    assert on["push"]["branches"] == ["develop"]
    assert on["push"]["paths"] == ["docs/**"]


def test_docs_site_checks_out_its_own_commit_before_the_target_ref():
    """The sync action is a local action, so the workflow's own commit must be
    checked out at the root: a manual re-sync of an older release tag would
    otherwise not contain the action at all."""
    [job] = _load(DOCS_SITE_PATH)["jobs"].values()
    checkouts = [s for s in _steps_of(job) if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert "ref" not in checkouts[0].get("with", {}), "the first checkout must be this commit"
    assert checkouts[1]["with"]["path"] == ".docs-source"
    [step] = _sync_steps(job)
    assert step["with"]["source"].endswith("/.docs-source")


def test_the_sync_action_builds_before_it_pushes_and_refuses_an_empty_token():
    """The site build fails on any broken link or anchor; it must run before
    anything reaches the site repo."""
    steps = _load(SYNC_ACTION_PATH)["runs"]["steps"]
    names = [s.get("name", s.get("uses", "")) for s in steps]
    assert names.index("Build") < names.index("Commit and push"), names
    assert "Refuse an empty token" == names[0], names
    for s in steps:
        uses = s.get("uses")
        if uses:
            assert _ACTION_USES_RE.match(uses) and re.match(r"^v\d+", uses.split("@")[1]), uses


# ── Kasm workspace registry ───────────────────────────────────────────────
#
# release.yml's publish-kasm-registry job runs the composite action
# .github/actions/sync-kasm-registry, which rewrites the Tubematic entry in the
# workspace registry repo with every published release. The workspace image
# itself is built and pushed by hand (kasm_workspace/build.sh --push): it
# carries no Tubematic version, so nothing in CI builds it.

KASM_SYNC_ACTION_PATH = os.path.join(REPO_ROOT, ".github", "actions", "sync-kasm-registry", "action.yml")
KASM_REGISTRY_TOKEN = "${{ secrets.TUBEMATIC_KASM_REGISTRY_TOKEN }}"


def test_no_workflow_builds_the_kasm_workspace_image():
    assert not os.path.exists(os.path.join(WORKFLOWS_DIR, "kasm-workspace-image.yml"))
    for name in os.listdir(WORKFLOWS_DIR):
        with open(os.path.join(WORKFLOWS_DIR, name)) as fh:
            assert "kasm_workspace/build.sh" not in "".join(
                line for line in fh if not line.lstrip().startswith("#")), name


def test_the_registry_sync_runs_after_the_release_and_gates_nothing(release_jobs):
    job = release_jobs["publish-kasm-registry"]
    assert "release" in _ancestors("publish-kasm-registry", release_jobs)
    for name, other in release_jobs.items():
        assert "publish-kasm-registry" not in _needs_of(other), (
            f"job {name!r} depends on publish-kasm-registry; a registry failure must never block a release")
    # A prerelease is never offered on the launch form.
    assert job["if"] == "${{ !contains(needs.preflight.outputs.version, '-') }}"


def test_the_registry_sync_names_the_environment_and_passes_the_token(release_jobs):
    job = release_jobs["publish-kasm-registry"]
    assert job.get("environment") == DOCS_ENVIRONMENT, "the token reads as empty without it"
    [step] = [s for s in _steps_of(job) if s.get("uses") == "./.github/actions/sync-kasm-registry"]
    assert step["with"]["token"] == KASM_REGISTRY_TOKEN
    assert job["permissions"] == {"contents": "read"}
    assert job["concurrency"] == {"group": "kasm-registry-sync", "cancel-in-progress": False}


def test_the_registry_action_checks_the_image_before_it_writes_anything():
    """An entry naming an image Kasm cannot pull lists a workspace that fails
    at install; the image is pushed by hand, so this is where a forgotten
    push is caught."""
    action = _load(KASM_SYNC_ACTION_PATH)
    steps = action["runs"]["steps"]
    names = [s.get("name", s.get("uses", "")) for s in steps]
    assert names[0] == "Refuse an empty token", names
    assert (names.index("Check the workspace image is publicly pullable")
            < names.index("Check out the registry")
            < names.index("Write the entry")
            < names.index("Commit and push")), names
    check = steps[names.index("Check the workspace image is publicly pullable")]["run"]
    assert "docker manifest inspect" in check and "docker login" not in check
    assert action["inputs"]["registry-branch"]["default"] == "1.1"
    for s in steps:
        uses = s.get("uses")
        if uses:
            assert _ACTION_USES_RE.match(uses) and re.match(r"^v\d+", uses.split("@")[1]), uses


def test_the_registry_action_offers_only_published_releases():
    steps = _load(KASM_SYNC_ACTION_PATH)["runs"]["steps"]
    [listing] = [s for s in steps if s.get("name") == "List the published releases"]
    assert "--exclude-drafts" in listing["run"] and "--exclude-pre-releases" in listing["run"]
    # The entry body comes from the newest release, never from an older line's tag.
    [entry] = [s for s in steps if s.get("name") == "Take the entry from the newest release"]
    assert entry["env"]["NEWEST"] == "${{ steps.releases.outputs.newest }}"


def test_no_release_job_builds_the_kasm_workspace_image(release_jobs):
    """A per-release rebuild of it is exactly what not baking the source avoids."""
    with open(RELEASE_PATH) as fh:
        assert "kasm-workspace" not in fh.read()
