# `scripts/tests`

Covers the host scripts in `scripts/`: the poller (`poll.py`), the agent adapters, the operations
scripts (`service.py`, `status.py`, `uninstall.py`, `collect_diagnostics.py`), the release tooling
and the remote-renderer script. It also checks files that no local test run executes: the GitHub
Actions workflows, the two Kasm Workspace images and three agent skills. The suite needs `pytest`,
PyYAML, `git` and the packages in `scripts/requirements.txt`.

```bash
python -m pytest scripts/tests
```

Run each suite in its own pytest invocation. [`README.md`](README.md) lists the suites that fail to
collect together.

`conftest.py` points `TUBEMATIC_SECRETS_DIR` and the poller's heartbeat, session registry and session
output files at a temporary directory, and creates the service tokens there. No test reads or writes
the state under your home directory.

## The poller

### `test_poll_main.py`

Covers `poll.py::main`: what each of [the four lanes](../13-the-poller.md#the-four-lanes) starts in
one pass.

- The pause gate, the pipeline lane and the two [research caps](../13-the-poller.md#research-caps)
  (`research_pending_cap` and `max_research_runs_per_day`), each tested on its own.
- The script-profile lane and the mascot lane run beside the other two and still run while the
  pipeline is paused. An item whose attempt cannot be recorded starts nothing, and an item that has
  used its attempts falls through to the next.
- A mascot runs on its pinned agent, model and effort, or on the defaults, one mascot per pass. A
  mascot pinned to an agent that is gone is skipped and records no attempt.
- The user preferences reach every prompt, an idle pass reads no settings, a dry run records nothing
  and starts nothing, and an install with no agent stops before the profile and research lanes.

Trap: The poller records a research run before the agent starts, and `_record_research_run` fails
closed: it starts no research when the record request fails. A count taken when a run finishes never
advances for a run that dies, so research would start again on every pass.

### `test_poll_supervisor.py`

Covers the loop in `poll.py`: session slots, the progress verdict, the scene-work claim wait,
timeouts and orphan adoption.

- The pipeline lane never runs more than `max_concurrent_agent_sessions`, fills oldest first and
  never dispatches a video that is already in flight. Research runs beside a full lane, once per
  poller process. With no active research mode it starts nothing and records no run.
- A pause starts nothing new and lets running sessions finish. The poller exits once idle.
- The verdict comes from the API
  ([Success is read from the database](../13-the-poller.md#success-is-read-from-the-database)). A
  changed status is progress whatever the exit code. No progress is a warning on exit 0 and an error
  otherwise. A stuck flag is an error that names **Retry agent**. A replayed outcome is logged and
  not scored again.
- A session past its deadline is killed with its children, including a child that ignores `SIGTERM`,
  and a timed-out run is not retried.
- A session stays registered until it is scored. A live orphan is adopted, holds its video and is
  scored when it exits. A finished session that was never recorded is recorded by the next poller
  under its original run id. A reused pid is not taken for an orphan, and a stale heartbeat is
  logged and kills nothing ([Timeouts and orphans](../13-the-poller.md#timeouts-and-orphans)).
- The claim wait and its statuses equal `SCENE_CLAIM_TTL_SECS` and `_CLAIM_STATUSES` in
  `mcp/server.py`, compared as source text because `poll.py` cannot import the server.

Trap: The timeout and adoption tests start real processes and threads. A mocked `Popen` cannot show
that `killpg` reached a grandchild, so replacing them with mocks removes the coverage of the kill
path.

Needs: real child processes. The stub API becomes unreachable after a few hundred passes, so a loop
that never ends fails the test and does not hang the suite.

### `test_workable_videos.py`

Covers the `GET /videos/workable` fetch and the per-video dispatch in `poll.py`, called through the
real functions.

- Each workable video gets its own session under its own agent, model and effort. A blank value
  falls back to the agent's default.
- A video pinned to an archived or unknown agent is skipped with an error in the log. An install
  with no active agent logs that and starts nothing. An unreachable `/agents` exits 1 and is told
  apart from an empty list.
- Each session is tagged with its one video and the status it started at, which is the stage its
  cost is recorded under.

Trap: An unreachable `/videos/workable` starts no session. A fallback prompt that covers every
workable video would let one session work videos assigned to other agents. The tests call the real
functions because a copy of the dispatch rule kept in the test file cannot fail when the code does.

### `test_invoke_agent.py`

Covers `poll.py::invoke_agent`: the argv for each agent, the fallback when a CLI rejects the model or
the effort ([Rejected model or effort](../13-the-poller.md#rejected-model-or-effort)), usage
reporting and what reaches the log.

- The agent row's id picks the adapter that builds the argv. A model that would corrupt the argv and
  an unknown effort level are dropped before the run. A missing binary, an agent with no adapter and
  a dry run start no process.
- A rejected model is read from the output whatever the exit code, and the run repeats once without
  it. A rejected effort is dropped before the model. No invocation runs more than three processes.
  OpenCode retries without the variant and keeps the model.
- Every run posts its parsed usage to `/usage/agent-session`. A retry posts too, since it is a second
  billed session. A run whose model was rejected and a dry run post nothing. A failed POST, or a
  `200` that recorded fewer events than were sent, logs the full payload.
- The log entry is the adapter's summary and stderr is logged by its tail. A model rejection printed
  past the log cap still triggers the retry.

Trap: The effort marker is matched against the CLI's own error output and never against the agent's
message. A session that discusses the flag would otherwise lose its effort on a retry. The agent's
stdin is closed, because Codex appends piped stdin to the prompt and an inherited stdin can hang an
unattended run.

### `test_poll_prompt.py`

Covers `build_research_prompt`, `build_pipeline_prompt` and `build_mascot_prompt` in `poll.py`.

- The research prompt names a mining target only when mining is active. It tells the agent to
  deduplicate with `list_project_topics` and to skip a paused or expired domain.
- The pipeline prompt names one video and where its stage ends, for every workable status. A
  cross-copy check keeps the stage table equal to the API's `WORKABLE_STATUSES`, since a status with
  no stage would never be dispatched.
- The mascot prompt names the builder skill, the mascot and the three build tools, and tells the
  agent not to advance any video.
- The user preferences block names the stage of the run, limits itself to that stage and says it
  cannot override a checkpoint ([User preferences](../07-agent-layer.md#user-preferences)). Empty
  preferences leave every prompt byte-identical.

Trap: The pipeline prompt forbids looking for other work, and it must still allow
`get_pipeline_status`, because the skills read the pronunciation lexicon and the voice roster from
that tool. A revision is told not to stop at `VOICE_READY`, where the scene-work claim would refuse
the next session. A pronunciation revision is told, in the prompt and in the operator skill's row,
to end at `VOICING` without voicing again.

### `test_bootstrap_args.py`

Covers the poller's command line and log directory ([The cron entry](../13-the-poller.md#the-cron-entry)).

- `poll.LOG_DIR` is the fixed `~/.tubematic-agent/logs`, because logging starts before the first HTTP
  call.
- A crontab that still passes `--agent-run-path` or `--agent-binary` gets a warning that names
  `--step cron`, and the run continues.
- Each prompt names its one video and gives the absolute path of `poll.log`.

Trap: An agent's working directory is its own workspace. A relative `./logs/poll.log` in a prompt
points nowhere for any agent whose workspace is not the poller's log directory.

### `test_poll_api_auth.py`

Covers the API token `poll.py` sends.

- One opener adds `Authorization: Bearer` to requests for `RENDERER_URL` and to no other URL.
- `main()` exits non-zero before it does anything when there is no token.

Trap: The token file is read on each request, because a running poller outlives
`onboard.py --rotate-tokens`. A cached token would be refused until the poller restarts.

### `test_poll_lock.py`

Covers `poll.py::LOCKFILE` ([Lock and heartbeat](../13-the-poller.md#lock-and-heartbeat)).

- The lock sits beside the poller's logs under the agent home and outside `/tmp`, so every poller
  that shares a home directory shares one lock.
- A finished run leaves the file in place.

Trap: Deleting a file that is held with `flock` lets two pollers each lock a different inode.
Cleanup code that removes the lock file allows two pollers to run at once.

### `test_poll_disk_snapshot.py`

Covers the poller's disk-usage measurement ([Disk usage](../13-the-poller.md#disk-usage)).

- The measurement starts before the pass, so a paused pipeline or an unreachable API still gets a
  fresh figure.
- It runs detached (`start_new_session`), at most once an hour per poller, and never on a dry run.
- A failure to start it is logged once and does not cost the pass.

Needs: nothing outside the test. `conftest.py` replaces `poll._refresh_disk_snapshot` with a no-op for
every other poller test, because the real function runs Docker and writes into `~/.tubematic-data`.

### `test_poll_json_logging.py`

Covers the poller's `poll.<date>.jsonl` log file.

- `poll.py` has no database access, and a test reads its source to keep it that way. The log
  retention setting arrives over HTTP and falls back to the default when the API is unreachable or
  the value is out of range.
- The JSONL file is written beside `poll.log`, and `poll.log` stays.
- An unwritable shared log directory leaves `poll.log` working.

Trap: `setup_json_logging` returns `None` without an error when the directory is unwritable, so the
poller must report it. The `poll.log` warning names the directory and the `chown` fix. Without the
warning, a root-owned `~/.tubematic-data/logs` drops every poller entry from the dashboard's Logs
page and nothing says why.

## Agent adapters and skills

### `test_agent_adapters.py`

Covers `scripts/agent_adapters.py`. The CLI behaviour behind each rule is in the
[Agent CLI Reference](../22-agent-cli-reference.md).

- Each argv is compared whole: the unattended run, the login check, the model probe and the MCP
  registration, for Claude Code, Codex and OpenCode.
- Claude Code: a bad `--effort` value (exit 0, a warning, the work done) does not count as a
  rejection, since a retry would be a second billed session for nothing.
- Codex: `--` precedes the prompt, and every argv carries `--skip-git-repo-check` and
  `approvals_reviewer="auto_review"` and no `dangerously` bypass flag. `"Logged in"` is a prefix test,
  so `"Not logged in"` cannot match. The model matcher covers the wording of both auth modes and
  ignores the "metadata not found" warning, which Codex prints for models the API accepts.
- OpenCode: the effort appears only as a `#variant` suffix on a model, and `--auto` is on every
  argv. `logged_in` reads the output, since `opencode auth list` exits 0 when logged out. `Variant
  unavailable` is told apart from `Model unavailable`, which lets the retry keep the model.
  `mcp_remove_argv` returns `None`, because OpenCode has no `mcp remove` command. A model slug with a
  vendor segment is suggested.
- OpenCode's config: the document name is resolved between `opencode.json` and `opencode.jsonc` in
  the order the CLI uses. The JSONC parser keeps a `//` inside a URL. Removing the server entry
  keeps the comments and refuses a malformed document. The permission rules deny edit, write, shell
  and `.env` reads, and allow `.env.example`, `webfetch`, `websearch` and the `tubematic_*` tools.
  Code Mode is off on the server entry.
- The usage parsers and `summarize_output` are checked against trimmed copies of real CLI output.
  Codex's parser splits cached input out of `input_tokens`, because OpenAI counts it inside.
  Codex and OpenCode print their errors on stdout in JSON mode, so their effort matchers read the
  stream's error events and ignore the same phrase in the agent's message.
- No MCP registration carries the token. Claude Code's entry names a `headersHelper`, OpenCode's
  header is a `{file:}` reference, and Codex's `http_headers_helper` is a line edit inside
  `[mcp_servers.tubematic]` that keeps the rest of `config.toml`.
- Checks over the whole registry: every adapter offers the same effort levels, `HAS_COMMANDS` matches
  the files on disk, every agent with commands ships the same set, no command names another agent's
  CLI or a tool its own install denies, and every call that resolves a config root accepts
  `respect_override=False`.

Trap: The Claude CLI treats an unrecognised subcommand as a prompt, so a malformed login check or
probe becomes a billed model call. Without `approvals_reviewer="auto_review"`, `codex exec` refuses
every MCP tool call and still exits 0. OpenCode's rules allow what the pipeline needs because a
global config that denies `webfetch` or `tubematic_*` would otherwise win, and each run would do
nothing and exit 0.

### `test_mcp_auth_header.py`

Covers `scripts/mcp_auth_header.py`, the helper Claude Code and Codex run on each MCP connection,
run as a real subprocess.

- It prints one JSON object that carries `Authorization: Bearer <mcp_token>`.
- With no token it exits non-zero and prints nothing on stdout, so the CLI sends no header and the
  server's `401` is the visible failure.
- It never reads the API token, which is a different credential.

### `test_voicing_authorization.py`

Covers the wording that lets an unattended agent voice a video in `VOICING`: the operator skill,
`build_pipeline_prompt` and the `generate_voice` docstring.

- The skill's `VOICING` row, its row for voicing again after a pronunciation fix, the pipeline prompt
  and the docstring each say the voicing is already authorized. Each names both the spend and the
  sending of the script to ElevenLabs.
- The `SCRIPT_READY` checkpoint stays, limited to moving a video into `VOICING`.
- The skill's `generate_voice` error row does not set the status again.

Trap: `VOICING` is a workable status, so an agent that asks for approval there is dispatched and
refuses again on every pass, and the video never moves. Naming only the spend, or only the
disclosure, leaves the other as a reason to refuse. Setting the status again on an error rewrites
`updated_at`, the clock [the stalled-voicing check](../12-the-worker.md#the-stalled-voicing-check)
measures.

### `test_troubleshooting_skill.py`

Covers the files of [the troubleshooting skill](../07-agent-layer.md#the-troubleshooting-skill).

- The skill is explicit-only on all three CLIs: `disable-model-invocation` and `opencode/autoinvoke`
  in the frontmatter, and `agents/openai.yaml` for Codex. No scheduled prompt names it.
- It never tells the agent to query the database, read a token or file the issue.
- It reads the redacted report and no raw log: not `poll.log`, not container output.

Trap: Losing one of the three switches breaks nothing visible, because the skill still works when
you ask for it. A skill that reads a raw log sends stored keys to the agent's model provider.

### `test_mascot_builder_skill.py`

Covers the files of the mascot builder skill.

- The skill is not explicit-only on any CLI, because [the mascot lane](../13-the-poller.md#mascots)
  invokes it by name in an unattended run.
- It names the three MCP tools of the build loop, and the poller's mascot prompt names the skill.
- Its guide keeps three rules: each face record carries `bx`, randomness is seeded through
  `boilSeed` and never `Math.random()`, and the mascot has no talking mouth.

Trap: A face record without `bx` turns every blush into `NaN` with no error.

## Operations scripts

### `test_service.py`

Covers `scripts/service.py`: `start`, `stop`, `restart`, `status` and `logs`.

- `start` creates the data directories, reconciles the volumes and creates any missing service
  token before `up`. `restart` is `stop` then `start`.
- `stop` and `restart` refuse while a render is in flight, the same gate `upgrade.py` uses, and
  `--force` overrides it. Restarting the dashboard alone is not gated.
- `status` prints the shared report, and `logs` hands the terminal to `docker compose logs`. Bad
  commands, unknown services and unknown options are refused before the venv bootstrap runs.

Trap: When a Docker volume has to be re-pointed, the reconcile runs `docker compose down` on every
container. A plain `start` and a dashboard-only restart are then gated too, and are refused before
anything stops, so a refusal never leaves the dashboard stopped.

### `test_status_format.py`

Covers `status.py::_local_date`.

- A UTC timestamp prints as the host's local calendar day, and an unparseable value falls back to
  its first ten characters.

### `test_status_spend.py`

Covers the spend summary in `status.py`, read from the usage ledger.

- Unpriced calls are named and are not counted as `$0`, ElevenLabs is shown in credits, and the
  API-list-price caveat is printed.
- A database that has not been migrated prints that there is no usage ledger yet and does not
  raise.

### `test_mcp_url.py`

Covers `config.py::_mcp_base`, which turns `MCP_URL` into the server root.

- A trailing `/mcp` is stripped as a whole path segment, so `/mcpx` is left alone and a
  reverse-proxy path prefix survives.

Trap: `status.py` probes `{MCP_URL}/health`, and the server serves that route beside `/mcp`. The
endpoint form (ending in `/mcp`) is the one `claude mcp add` takes, so without the strip a healthy MCP
container is reported unreachable.

### `test_clear_db_wipe.py`

Covers the "Wipe all videos" action of `clear_db.py`.

- The wipe clears the spend ledger when there are no videos. That state is ordinary: research that
  filed nothing, voice previews and videos deleted one at a time all leave spend with no video.
- An empty database has nothing to wipe.

### `test_uninstall_config.py`

Covers `uninstall.py`: the install-config read, the agent sweeps, the scenes step and the data-root
step.

- The install scope and the agent workspace are read once, before anything is deleted, and the
  values survive the deletion of the database. `--force` never stops at the scope prompt.
- A kept data root names the GPU choice and the remote-renderers override in it, since a reinstall
  over it would hand the GPU to the new renderer and publish the render gateway's port again.
- The agent sweep goes through one adapter-keyed entry point. It removes each deployed and each
  retired skill, the commands and the MCP registration, sweeps a project-scope install from its
  workspace, and ignores a config-root override on every path. A config document that cannot be
  edited safely is left alone and the edit is reported. A skill Tubematic did not install is kept.
- The Claude command list covers every file in `agent_files/claude/commands/`.

Trap: The database is deleted in an early step, and later steps need the install scope and the
workspace path from it. Without the cached read, the agent step prompts under `--force` or skips a
project-level workspace. The sweep is keyed by adapter so that a new agent cannot ship without an
uninstall path.

### `test_collect_diagnostics.py`

Covers `scripts/collect_diagnostics.py`, whose report is meant to be pasted into a public issue.

- One fixture plants every secret and personal value the collector can read into all three log
  sources (structured logs, `poll.log`, container output), and the finished report is searched for
  each: secret settings, service tokens, the password hash, provider keys, auth headers, a cookie,
  an email, public addresses, the home path, user and host names, account, voice and domain ids, and
  a video's content.
- An opening the agent drafted and did not use is content too. It is in no script column, so it
  is read from the video's recorded openings.
- Ids become the same short hash wherever they appear, so lines about one account still match up.
  Content stays out unless you pass `--include-content`. Content under 12 characters is replaced as
  a whole word, and content under four characters is left.
- The collector refuses to write inside `~/.tubematic-data`, refuses an existing `report.md` and a
  symlink planted while the report is built (the file is opened with `O_EXCL`), writes modes 0700 and
  0600, and opens the database read-only.
- `--since` bounds `poll.log` and reaches its dated rotations. A non-positive `--lines` is refused,
  because `lines[-0:]` is the whole file.
- The GPU readout leaves out the GPU UUID, which identifies a physical card.

Trap: The residual scan fails closed. With the redactor broken in the test, nothing is written and
the surviving value is not printed. A line is cut to the length limit after redaction and the scan,
because a cut made first can leave a prefix of a secret that the stored value does not match.
Agent-authored comments stay in the report: the worker files render errors as agent comments, and
those errors are the evidence a report exists to carry.

## Release tooling

The scripts and workflows these files cover are described in [Releases](../18-releases.md).

### `test_release_clis.py`

Covers the command-line contract of `print_version.py`, `migrate_db.py` and `backup_db.py`: exit
codes and what goes to stdout and to stderr. The migration logic is covered in
[`tubematic_core/tests`](tubematic-core.md).

- `migrate_db.py` reports the backup path and exits 1 with the reason on stderr when a migration
  fails.
- `backup_db.py` prints the backup path and exits 1 when the database does not exist.

Trap: `migrate_db.py --allow-no-backup` skips the pre-migration backup, so it must print a warning.
The test asserts that the warning appears, since the flag would work the same without it.

### `test_update_price_snapshot.py`

Covers `update_price_snapshot.py`, the maintainer script that writes the model prices a new install
starts from.

- It applies the same source precedence as the runtime price sync: OpenRouter first, LiteLLM for a
  model OpenRouter lacks.
- It refuses to write when a model Tubematic can select is in neither feed.
- The committed `tubematic_core/prices_snapshot.json` covers every model in `KNOWN_MODELS`.

Trap: A model missing from the snapshot is unpriced on every new install.

### `test_gen_release_compose.py`

Covers `gen_release_compose.py::generate`, run against the real `docker-compose.yml`
([`gen_release_compose.py`](../18-releases.md#gen_release_composepy)).

- Every `build:` section becomes a pinned `ghcr.io/<owner>/tubematic-<role>:<version>` image, and so
  does every service that reuses the locally built image under its `tubematic-renderer-image` tag.
- Every published port is bound to `127.0.0.1`, and everything else passes through unchanged,
  `secrets:` blocks and the top-level `name:` included.
- The release renderer has no database mount and never holds the TLS key, and the gateway port is
  not published.
- `check_version_is_tag_safe` and `invalid_version_chars` reject `+build` metadata, and `generate()`
  refuses such a version before it reads the compose file. A version goes into the image reference
  with no escaping.
- No healthcheck probes `localhost`. The servers bind IPv4, and the BusyBox `wget` in the dashboard
  image resolves `localhost` to IPv6 first and does not fall back.

Trap: The test reads the real compose file, because a fixture would not notice a topology change.
Services are matched by the shared image tag, so a new service that reuses the image is repointed
too.

Needs: PyYAML.

### `test_build_release_tarball.py`

Covers `build_release_tarball.py`, which builds the real `dist/tubematic-v<version>.tar.gz` from the
checkout ([The release tarball](../18-releases.md#the-release-tarball)).

- Every allowlisted path is present, and a missing one fails the build. The list includes
  `upgrade.py`, `scripts/service.py`, `onboard/stack.py`, `scripts/mcp_auth_header.py`,
  `scripts/collect_diagnostics.py`,
  `scripts/tubematic_remote_renderer.py`, `LICENSE`, and the public docs: `docs/README.md`,
  `docs/quickstart.md`, `docs/release-notes.md` and the `docs/user-guide/`, `docs/developer/` and
  `docs/images/` trees.
- Every excluded pattern is asserted absent on its own: the source trees, `.env`, `HANDOFF.md`,
  `.onboard-state.json`, `docs/superpowers` and both packages' `tests/`.
- The bundled `docker-compose.yml` is the generated release file. Building one commit twice gives
  byte-identical archives, and `CHECKSUMS.txt` covers every other file.
- No shipped file other than `.py` and `.sql` names an issue-tracker id.
- The dead-link guard reads every shipped file other than `.py`. Each relative link to a Markdown
  page or to an image is resolved against the linking file's own directory inside the archive, and
  its target must be in the archive. A link written inside a code span is skipped.
- The extracted tree imports the `onboard` modules and `tubematic_core.db` in a fresh subprocess, so
  a module the test session already imported cannot hide a file missing from the copy list.
- A `.pytest_cache` planted in every shipped tree does not fail the build. pytest writes one inside
  each suite directory and hides it from git, and the name is also forbidden.

Trap: The allowlist test proves presence only. The absence test and `_assert_no_forbidden_names`
exist because a later allowlist entry, such as a bare `docs/`, would bring `docs/superpowers/` in
behind it. Only part of `docs/` ships, so a link from a shipped page to an unshipped page or image
is dead for a reader who holds only the tarball.

Needs: PyYAML.

### `test_check_release.py`

Covers `check_release.py`, each check run against a real git repository built in `tmp_path`
([`check_release.py`](../18-releases.md#check_releasepy)).

- Each check fails on its own condition: a dirty tree, a version mismatch, a version that is not
  tag-safe, a duplicate migration number, a compose file that does not generate, a missing
  allowlisted path, and a forbidden name inside an allowlisted tree.
- The tag check has three cases. No such tag passes. A tag at `HEAD` passes, because the release
  workflow runs after its checkout has fetched the tag. A tag at another commit fails and names both
  SHAs.
- The migration check fails on a committed migration file that has changed, and ignores a new file
  that was never committed.
- Two checks warn and do not change the exit code: missing workflow files, and `HEAD` outside
  `release/X.Y.x`.
- An all-clear fixture drives `run_checks()` and `main()` end to end, and a run with two faults
  reports both.

Trap: The release-line check is a warning because the first release of a minor version runs before
the line exists, and CI checks out a detached tag with no branches. `check_version_format` is the
one check that refuses the development marker `develop`, so it is what stops a `vdevelop` tag.
`check_tarball_exclusions` runs the real builder against a scratch directory and keeps no second
copy of `_FORBIDDEN_NAMES`.

Needs: `git`. The tests create commits and tags for real, since a mocked git would only confirm the
test's own idea of git.

### `test_release.py`

Covers `release.py` ([`release.py`](../18-releases.md#releasepy)).

- A failing pre-flight check stops the run before `build_release_tarball.build()` is called. A build
  failure stops it after the checks pass. The `v`-prefixed version form is accepted.
- The all-clear path builds the tarball and prints the release-notes skeleton and the git tag, push
  and branch commands.

Trap: `release.py` prints the git commands and never runs them, because a script that tags and
pushes can publish a release nobody approved. The test runs against a real git repository and
asserts that no new tag and no new branch exist, which a mocked `subprocess` could miss.

### `test_release_notes.py`

Covers `release_notes.py`, which extracts one version's section from `docs/release-notes.md`, and
`release_line()`.

- The section comes back without its heading and ends at the next version heading or at a
  horizontal rule.
- Four failures are told apart: no section, a section that is still an unfilled skeleton, a
  prerelease whose base version is also absent, and an unreadable file.
- A prerelease with no section of its own gets its base version's notes, and its own section wins
  when it has one.
- The extractor runs against the repository's real page at the current `VERSION`. On the development
  branch it checks the page's newest section.
- `release_line()` groups patches onto one branch, ignores a prerelease suffix and refuses `develop`.

Trap: An unfilled skeleton counts as missing. A pasted skeleton looks like written notes, and the
release workflow would publish it as the Release body.

### `test_workflows.py`

Covers `.github/workflows/ci.yml`, `release.yml`, `docs-site.yml` and their composite actions. The
files are parsed with PyYAML and checked for structure, since GitHub Actions runs only on GitHub
([Continuous Integration](../18-releases.md#continuous-integration)).

- In every workflow, each `needs:` names a real job, and each third-party action is pinned to a
  version tag or a full SHA.
- `ci.yml`: the Python matrix equals the suite directories on disk, and the e2e job has no path to
  `pull_request`.
- `release.yml` triggers on `v*.*.*` tags only and reuses `ci.yml`. Both images are pushed under the
  bare version tag. The Release step sets `prerelease` from a `-` in the version, because the
  action's default would publish a release candidate that GitHub can list as Latest.
- The smoke test runs after the image push and before the Release job, walked through `needs:`
  transitively. It extracts the published tarball and uses no checkout. It creates every secret
  file `docker-compose.yml` mounts before `up`, because it skips onboarding and Compose refuses a
  service whose token file is missing. Its `curl` checks carry `--retry`, because a container can
  report healthy before its process has bound its port.
- The remote-renderer script is a Release asset named in `CHECKSUMS.txt`. The release owner is
  stamped into its `GITHUB_OWNER` before the tarball is built, so a fork's renderers do not pull
  upstream's image. The stamp step fails when it cannot stamp, and the asset must be byte-identical
  to the tarball's copy.
- The docs sync: nothing depends on `publish-docs`. Each job that syncs names the `TubeMatic`
  environment and passes `TUBEMATIC_DOCS_TOKEN`. `docs-site.yml` runs on a `docs/` push to `develop` or
  a `release/*.*.x` line, or by hand. It labels a line with the newest stable release it contains
  and does not sync a line with no release.
- The Kasm registry sync: `publish-kasm-registry` gates nothing and skips a prerelease. Its action
  lists published Releases that are neither draft nor prerelease, fails on a `gh` error, and checks
  the workspace image with `docker manifest inspect` before it writes anything. No workflow calls
  `kasm_workspace/build.sh`.

Trap: If the Release job could run before the smoke test, a broken artifact would become a published
Release. An environment secret reads as an empty string in a job that does not name its
environment, which is why each syncing job declares it. A release line with no release yet would be
the highest line and become Latest on the docs site. The registry action fetches the entry without
writing a local tag, because `actions/checkout` leaves a lightweight tag and git refuses to fetch
the annotated tag onto it.

Needs: PyYAML, `bash` and `git`. Several steps (the token step, the owner stamp, the docs input and
labelling steps, the registry fetch) are run for real against scratch directories.

## The Kasm workspace and the remote renderer

### `test_kasm_workspaces.py`

Covers the two Kasm Workspace images, `kasm_workspace/` (published) and `kasm_workspace_testing/`,
which CI does not build ([the published workspace](../17-development.md#kasm_workspace-the-published-workspace)).

- In both images, the `dind` `/tmp` patch's `RUN` body is executed with `sh` against a fixture
  `custom_startup.sh`. With the anchor line it inserts one line before `supervisord`, and with the
  anchor changed it fails the build.
- Every hook and build script is mode `100755` in the git index and parses with `bash -n`.
- The published Dockerfile does not `COPY` the repository, and the image runs on UTC
  (`ENV TZ=Etc/UTC`).
- The registry entry (`registry/Tubematic/workspace.json`) has the schema 1.1 keys, `privileged`,
  `gpu_count: 0`, a version list that is newest first, and `allow_saving: false` on the version so a
  remembered pick does not pin an old one. The form's keys, mapping path, methods and regex equal
  the bootstrap's constants.

Trap: A skipped `/tmp` patch gives a blank-screen session that nobody sees until one is launched.
`COPY` keeps the file mode, and a hook without its exec bit looks the same as Kasm never calling it.
The published image carries no Tubematic source so that a release needs no rebuild.

Needs: `shellcheck` for one test, which skips without it.

### `test_kasm_workspace_bootstrap.py`

Covers `kasm_workspace/image/tubematic_bootstrap.py`, which the published workspace runs at launch.

- Every refusal downloads nothing: bad JSON, a missing key, a version that is not a plain `X.Y.Z`,
  an unknown method.
- On a relaunch, an empty profile installs, the same version is left alone, a different version is
  refused with a pointer to the upgrade, and Tubematic data with no readable install marker is
  refused.
- A release is checksum-verified before extraction. A mismatch, an unpublished version, an archive
  with a path outside `tubematic-v<version>/` and an existing target directory are each refused.
- A source install clones the version's tag and never the default branch.
- `GITHUB_REPO` equals `tubematic_core.version.GITHUB_REPO`, since the image cannot import it.

Trap: The fakes replace the module's `urllib.request.urlopen` and `subprocess.run`, so the functions
must look those names up at call time. A default argument bound at definition time lets the
"downloads nothing" tests pass without ever seeing the fake.

### `test_kasm_registry_sync.py`

Covers `kasm_workspace/sync_registry.py`, which `release.yml` runs to write the Tubematic entry into
the workspace registry
([Publishing the Kasm registry entry](../18-releases.md#publishing-the-kasm-registry-entry)).

- Versions sort numerically, newest first, so `2.0.10` comes before `2.0.9`. Tags and duplicates
  collapse to one version.
- A prerelease, or anything that is not `X.Y.Z`, is never offered. An empty list is refused and
  nothing is written.
- The written entry passes the checks `test_kasm_workspaces.py` applies to the in-repo entry, and
  nothing but the version list changes.

Trap: The launch form has no free-text field, so the written list is the set of versions a user can
install from it. A string sort or a listed prerelease is a defect no other check sees before a
session launches.

### `test_bean_explainer_skill.py`

Covers the `tubematic-bean-explainer` skill ([Bean Explainer](../10-scene-authoring.md#bean-explainer)).

- The skill is loadable by an unattended run (not explicit-only), its pack names it as the authoring
  skill, and the operator skill routes to it.
- The prop catalogue in `reference/contract.md` lists the pack's props and no others, each with its text
  limit and acts, and every pose, face, mark, accessory, tint, entrance, field and section colour.
- The limits the skill states are the ones `mcp/bean_explainer.py` enforces, the worked example
  passes the validator, and the uninstaller removes the skill.
- The skill teaches props of the agent's own within the validator's limits (count, box, text slot,
  acts, the whole-prop acts, the preview tool), and its worked custom prop, `example-prop-rocket.tsx`,
  passes the validator's source checks.

Trap: `reference/contract.md`'s catalogue is generated from the pack. A prop added to the library
and left out of that file is a prop no agent will use.

### `test_storybook_atlas_skill.py`

Covers the `tubematic-storybook-atlas` skill ([Storybook Atlas](../10-scene-authoring.md#storybook-atlas)).

- The skill is loadable by an unattended run, its pack names it as the authoring skill, and the
  operator skill routes to it.
- `reference/contract.md` lists the pack's props and no others, each with its box, states, acts and
  portal, every backdrop, every knob value and every coat. The skill names every backdrop, pose and
  event type.
- The limits the skill states are the ones `mcp/storybook_atlas.py` enforces, the worked example
  passes the validator, and the uninstaller removes the skill.
- The skill teaches props of the agent's own within the validator's limits, and its worked custom
  prop, `example-prop-moth.tsx`, passes the validator's source checks.

Trap: `reference/contract.md`'s tables are generated from the pack. A prop or backdrop added to the
library and left out of that file is one no agent will use.

### `test_terminal_doc_skill.py`

Covers the `tubematic-terminal-doc` skill ([Terminal Doc](../10-scene-authoring.md#terminal-doc)).

- The skill is loadable by an unattended run (not explicit-only), its pack names it as the authoring
  skill, and the operator skill routes to it.
- The skill and `reference/contract.md` list every move, and the contract every slot (with its
  centre and sizes), size (with its characters per line), tone, skin, reveal and cut.
- The limits the skill and the contract state are the ones `mcp/terminal_doc.py` enforces, the
  worked example passes the validator and uses at least ten of the moves, and the uninstaller removes
  the skill.
- The skill teaches moves of the agent's own within the validator's limits, and its worked move,
  `example-move-caesar.tsx`, passes the validator's source checks.
### `test_under_the_hood_skill.py`

Covers the `tubematic-under-the-hood` skill ([Under the Hood](../10-scene-authoring.md#under-the-hood)).

- The skill is loadable by an unattended run (not explicit-only), its pack names it as the authoring
  skill, and the operator skill routes to it.
- The skill and `reference/contract.md` list every pose, event kind and tone in the pack, and state
  the limits `mcp/under_the_hood.py` enforces.
- The skill asks for square photographs with the no-text prompt recipe, checks each with
  `read_image`, and never calls `generate_character`.
- The worked example passes the validator and uses every kind of event, and the uninstaller removes
  the skill.

### `test_system_flow_skill.py`

Covers the `tubematic-system-flow` skill ([System Flow](../10-scene-authoring.md#system-flow)).

- The skill is loadable by an unattended run (not explicit-only), its pack names it as the authoring
  skill, and the operator skill routes by `style.authoring_skill`.
- The icon list and the limits the skill states are the ones `mcp/system_flow.py` enforces.
- The reference files ship, and the uninstaller removes the skill.

Trap: a skill that teaches a value the validator refuses teaches the agent to be refused on every
video. Change a limit in `system_flow.py` and the skill text together.

### `test_style_routing_skill.py`

Covers the `tubematic-style-routing` skill
([How Auto picks a style](../10-scene-authoring.md#how-auto-picks-a-style)).

- The skill is loadable by an unattended run and names no style id or label.
- It reads every field `routing_candidates` gives a candidate, names the real fallback, and calls
  `choose_visual_style` with its real arguments and reason limit.
- The operator runs it before the script-writing skill at `TOPIC_APPROVED`, the script-writing skill
  follows `style.script`, and the uninstaller and the skills README know it.

Trap: a skill that named styles would prefer the ones it knew about, and a new pack would need an
edit to be picked. The candidates are data for that reason.

### `test_formula_routing_skill.py`

Covers the `tubematic-formula-routing` skill
([How a formula is picked](../08-scripting-and-voice.md#how-a-formula-is-picked)).

- The skill is loadable by an unattended run and names no formula id or label except its two
  fallbacks, which are formulas that are not experimental, one for an explanation and one for a
  story.
- It reads every field `routing_candidates` gives a candidate, and calls `choose_script_formula`
  with its real arguments, reason limit and result keys.
- It names the rotation window the server enforces, routes around a person's choice with the
  agent's own best formula, covers every refusal the tool makes, and uses the topic's angle only
  when there is one.
- The operator runs it after style routing and before the script-writing skill at
  `TOPIC_APPROVED`, and names it on a script revision. A revision runs it for a video with no
  formula, and a person's choice is kept with a comment saying so. Rotation is skipped beside a
  person's choice. The uninstaller and the skills README know it.

Trap: a skill that named formulas would prefer the ones it knew about, and a new formula would need
an edit to be picked. The candidates are data for that reason.

### `test_eval_formula_routing.py`

Covers the plumbing of `scripts/eval_formula_routing.py` ([Formula routing](formula-routing.md)). No
model is called.

- The prompt carries the video as `get_video` returns it at `TOPIC_APPROVED`, with its style
  decided, the style's script text and every candidate. A topic is routed with experimental
  formulas only when it says so, and a topic with no style is a video on mixed scenes.
- The answer is the last JSON object in the reply that names a formula, and the style eval's own
  answer key still works.
- The report counts best, acceptable and failed picks overall and by formula, and lists the wrong
  ones. Every topic in the set builds a prompt.

### `test_eval_style_routing.py`

Covers the plumbing of `scripts/eval_style_routing.py` ([Style routing](style-routing.md)). No model
is called.

- The prompt carries the video as `get_video` returns it at `TOPIC_APPROVED`, with every candidate.
- The answer is the last JSON object in the reply that names a style.
- A pick is scored best, acceptable or wrong, and the report counts each and lists the wrong ones.

### `test_script_writing_skill.py`

Covers the `tubematic-script-writing-skill` skill and `scripts/gen_formula_references.py`
([Formulas](../08-scripting-and-voice.md#formulas)).

- The skill's `formulas/` files equal what the generator renders from the formula data, and
  `--check` reports an edited file and a stray one. The skill holds no table for choosing a
  formula.
- The hand-off names `update_video`'s real arguments, reads `warnings`, allows one extra write, and
  says what to do when an older tool server refuses the new arguments.
- The authority order is fixed policy, the style's script text, the formula, the profile. The
  grammar has fourteen rules, and a closing line comes only from the preferences.
- The skill holds no fixed five-part sequence, no per-part word budget and no call-to-action step.
- The headings other skills and tests point at are present, and the operator's `TOPIC_APPROVED` and
  revision rows pass the record. The pronunciation row leaves the record out, in a place where
  the sentence cannot be read as being about the publish title and description.
- The formula's reference file and the style's script text decide how the payoff rules are met.
  The length starts from the lower half of the band, and a length the style's script text gives
  wins over the band.
- The skill writes in `formula_routing.pick` and does not choose a formula. It covers a video with
  no pick (the router has not run, a script from before picks existed, a revision with no formula
  at all, an older tool server) and says a changed style or topic drops the pick.
- The openings step prefers a type the domain's previous two videos did not use, and starts from
  the opening a person switched to, word for word, only while that comment is the newest and no
  script has been written since.
- A style that asks for names may name its people.
- The user guide's formula table names every formula.

Trap: an instruction that survives beside its replacement is followed whenever the agent reads it
last, so the removed phrases are pinned as absent.

### `test_eval_script_writing.py`

Covers the plumbing of `scripts/eval_script_writing.py` ([Script writing](script-writing.md)). No
model is called.

- The topic set is well formed, and each topic's formula is one that is not experimental. The
  prompt carries the video as the skill reads it at `TOPIC_APPROVED`, with no profile, no
  preferences and the topic's formula as the pick.
- The new side carries every formula file. The old side is read from git at the given ref.
- The answer is the last JSON object in the reply that holds a script. A script is scored on its
  spoken words, with its record when it has one.
- The summary shows both sides for each topic and counts each warning per side.
### `test_whiteboard_skill.py`

Covers the `tubematic-whiteboard` skill ([Whiteboard](../10-scene-authoring.md#whiteboard)).

- The skill is loadable by an unattended run (not explicit-only), its pack names it as the authoring
  skill, and the operator skill routes to it.
- The doodle list, the layouts and their slots, and the limits the skill states are the ones
  `mcp/whiteboard.py` enforces.
- The worked example passes the validator against its own timeline, and the uninstaller removes the
  skill.
- The skill's `reference/doodles.json` is the shipped library and its names are the pack's list, and
  the skill teaches every primitive, the preview tool and the custom-doodle limits.

Trap: a skill that teaches a value the validator refuses teaches the agent to be refused on every
video. Change a limit in `whiteboard.py` and the skill text together.

### `test_tubematic_remote_renderer.py`

Covers `scripts/tubematic_remote_renderer.py`, the stdlib-only script that installs, upgrades,
removes and reports on a renderer on another machine
([The host script](../20-gpu-and-remote-renderers.md#the-host-script)).

- The script runs with no checkout and carries its own copies of shared code. Each copy is checked
  against its original: the enrollment-token decoder and the certificate pin
  (`tubematic_core.renderers`), the image owner and name, the container's command and
  shared-memory size (`docker-compose.yml`), the `nvidia-smi` parsing, and the GPU environment
  (`onboard/gpu.py::render_override`).
- Nothing is sent to a gateway before its certificate matches the token's pin. A real TLS server
  sees the handshake and no HTTP request line when the pin is wrong, for the version check and for
  a whole `install`.
- The token is never written down: it is in no argv, in no printed line and not in the state file.
  The enrollment container gets it through its environment. Once the renderer has enrolled, that
  container is removed and the renderer starts again without the token.
- A refused enrollment, a failed `docker run` and Ctrl-C each leave no container.
- The token comes from a hidden prompt, or from stdin with `--token-stdin`. `--token` is refused in
  every form before Docker or the gateway is touched.
- An unknown GPU, a GPU with no `nvidia` runtime and several GPUs with no terminal are refused, and
  none of them falls back to the CPU.
- `upgrade` pulls before it stops anything, and `remove` asks separately before it deletes the saved
  credential.

Trap: The fake Docker keeps each container's environment the way Docker does: a bare `-e NAME` is
resolved and stored, and `docker inspect` shows it. That is what lets the tests see that a container
recreated without dropping the token would keep it.

Needs: PyYAML and `cryptography`. Docker is a fake `run_cmd`, and the TLS server is real.
