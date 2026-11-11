# `onboard/tests`

Covers the onboarding wizard (`onboard/`), the stack control in `onboard/stack.py` that
`scripts/service.py` shares, and the root `upgrade.py`. The suite needs `pyyaml` and the packages
of the requirements files, and no Docker: Docker and agent commands go to a recording executor
or a patched `subprocess`. Run it in its own `pytest` invocation
([Run each Python suite on its own](README.md#run-each-python-suite-on-its-own)).

```bash
python -m pytest onboard/tests
```

`conftest.py` keeps every test off the real machine. It points the poller's session registry, the
secrets directory (`TUBEMATIC_SECRETS_DIR`) and both Compose override paths at a temporary
directory, and makes `tubematic_core.disk_usage.refresh_snapshot` do nothing. The override paths
matter because `_compose()` adds a `-f` for each override that exists, and a developer machine's
own file would change every command line a test asserts.

The steps and questions are listed in the
[Command Reference](../../user-guide/15-command-reference.md#steps).

## Flow and state

### `test_steps.py`

Covers the step list in `onboard/steps.py`.

- `directories` and `database` come before the two container steps, which come last in a full
  install, because Docker creates a missing bind-mount target as root.
- `auth` comes after `database`, which holds the password, and before every container step,
  because Compose refuses to start a service whose token file is missing.
- `gpu` comes before `renderer`, so the first `up` carries the GPU override.
- Every step is reachable with `--step`, and agent setup is not a step.

Trap: `renderers` is the one opt-in step and comes after every step of a full install. It
publishes the render gateway's port to other machines, which a full install must not do unasked.
One test fixes the number of steps in the default flow, so adding a step means editing it.

### `test_fields_for_step.py`

Covers `onboard/config.py::fields_for_step` and `SECTION_TO_STEP`, the one place where `advanced`
and `condition` filtering happens.

- Every section maps to one step, and field keys are unique.
- The default questionnaire and the required set are written out as lists, so widening either is
  an edit to the test. The required set is the ElevenLabs key and the OpenAI key.
- A required field is not `advanced`, and the postforme key is asked only after publishing is
  switched on, in that order.
- Every field has help text with no ticket identifier. The OpenAI help says it draws every scene
  image, and the Gemini help says what is off without it.

Trap: a skipped question stores its default without passing the prompt's validation. One test
runs every advanced default through its own validator, and another checks that the default voice
is on the default roster.

### `test_executor.py`

Covers `onboard/executor.py::Executor`, the one place a dry run is decided.

- In dry mode it records each intent and changes nothing.
- In live mode it performs the action.

### `test_config.py`

Covers `load_current_values` and the settings readers in `onboard/config.py`.

- Each field is pre-filled from its settings row, and from the field's default when there is no
  row or no database. A leftover `.env` file is ignored.
- An ephemeral field is not read from disk.

Trap: a new install is offered the pre-loaded voices, and a stored empty roster stays empty.
Voices that someone deleted must not return on a re-run.

### `test_state_migration.py`

Covers bringing an older `.onboard-state.json` forward.

- A state from before `install_config` existed loses its retired marker and every step derived
  from the old configuration, so those steps run again. Unrelated steps keep their mark.
- Retired steps are dropped from any state, and the migration can run twice.

### `test_bootstrap.py`

Covers `onboard/bootstrap.py`, the virtualenv and dependency bootstrap that runs before anything
else can be imported. `venv` and `pip` are patched.

- A virtualenv that holds an interpreter and no `pip` is created again. A complete one is reused.
- A `venv` run that reports success and installs no `pip` is a failure.
- When `ensurepip` is missing, the message names the apt package. For any other failure it stays
  generic.

Trap: readiness is judged on `pip` as well as the interpreter. Debian and Ubuntu package
`ensurepip` apart from Python, so `python3 -m venv` can leave an interpreter with no `pip`, and
re-running into that virtualenv fails later with an unrelated message.

### `test_onboard_cli.py`

Covers `onboard.py`'s own flag handling. The module is loaded by path with `_ensure_venv` and
`_ensure_deps` stubbed, because a real `main()` would create a `.venv` in the checkout.

- `--install-agent` and `--uninstall-agent` refuse an unknown or missing name and need a terminal.
  `--list-agents` is a report that needs none.
- `--set-password` needs a terminal. `--rotate-tokens` does not, so a script can run it.
- The shared flags reach the install with their meaning.

Trap: onboarding's `POLL_LOG_DIR` must equal the one in `scripts/config.py`. The cron line's
`cron.log` and the poller's `poll.log` land in one directory only because these two hand-kept
copies agree.

### `test_install_mode.py`

Covers the choice between a source checkout and a release tarball, and what each does at the
container steps.

- The mode is detected from the presence of `renderer/Dockerfile`. `--install-mode` overrides it,
  and the resolved mode is printed and recorded in `.onboard-state.json`.
- A release install pulls images and runs no build. A source install builds as before.
- A failed pull shows Docker's own reason (`actions.py::_pull_failure_hint`), with no
  `docker compose logs` hint and no login instruction, since a failed pull creates no container
  and the images are public.
- The Node and `npx` checks run in both modes, and the Node check compares major and minor
  against 22.20. They warn and do not block.
- The dashboard step measures disk use once its image is in place, and a failure there warns.

Trap: precedence is the explicit flag, then the recorded mode, then detection. Without the
recorded mode, a later `--step renderer` in a checkout that was installed in release mode would
detect a source install and build.

Needs: the stubs patch `onboard.plain.*`, which binds the check functions at import. Patching
`onboard.checks.*` leaves the real checks running, so each site asserts its mock was called.

## Fields and validators

### `test_agent_model.py`

Covers the model-name validator.

- An alias and a full model id pass. A value with a space, or one shaped like a flag, is refused,
  because it would corrupt the agent's command line.
- The main flow asks nothing about an agent and `install_config` writes no agent row.

### `test_ai_review_settings.py`

Covers the review model, sampling rate and loop cap fields, and the rows
`apply_pipeline_settings` writes from them ([AI Review](../21-ai-review.md)).

- The sampling-rate and loop-cap validators hold Gemini's range and the one-or-two rounds bound.
  A loop cap of 0 is refused.
- An out-of-range stored value is clamped, an unparseable one falls back to the default, and an
  unknown model is not stored.
- The review loop cap and the render retry cap are separate fields.

Trap: AI review is off by default, and that default lives in four places: the field (whose
choices lead with `false`, because a select falls back to its first choice), both fallbacks in
`actions.py`, and `SETTINGS_SPEC`. A skipped or garbled answer must land on off. A fallback left
at `true` would switch review on for the installs that never answered.

### `test_render_timeout.py`

Covers the render timeout question, asked in minutes and stored as `render_timeout_secs`.

- Stored seconds are shown as minutes, and a corrupt stored value shows the default.
- The answer is written as seconds, with a floor of one minute so that onboarding cannot store a
  value the settings API refuses.

### `test_retention_days.py`

Covers the `retention_days` field and the row written from it.

- The bounds and the validator equal the settings API's.
- `0` is stored as `0` and is not clamped, because it is the off switch.

Trap: the field is advanced, so a default install takes the value from the apply step's fallback
literal. That literal, the field default and `SETTINGS_SPEC`'s default are three copies, and a
test holds them equal.

### `test_voices.py`

Covers the voice roster and default-voice questions, `_parse_voices`, and the rows written from
them ([The roster](../08-scripting-and-voice.md#the-roster)).

- A corrupt or misshapen stored roster, or one over the cap, reads as empty. Every voice needs a
  known model.
- The default-voice choices follow the roster just answered, and a default that is not on the
  roster falls back to the first voice.

Trap: onboarding reads stored values before its `database` step migrates. A roster stored without
per-voice models would read as empty and the apply step would then erase it, so
`load_current_values` gives each such voice the install's stored model first.

### `test_image_generation.py`

Covers the image model question and the OpenAI-key gate in `apply_install_config`.

- The image model is one select over the OpenAI catalog, with no provider question and no
  `image_provider` row.
- A missing OpenAI key fails the step, with or without a Gemini key.
- A stored model outside the catalog is corrected on a re-run.

Trap: the gate fires after the settings write. Everything already typed is stored first, so the
step that asks again starts from those answers.

### `test_api_keys.py`

Covers `onboard/api_keys.py`, the live check of each key as it is entered. Every invalid case
replays the body a provider returned for a bad key.
[Rejection signatures](../04-settings.md#rejection-signatures) lists how each provider answers,
and [A pasted key is checked before it is sent](../04-settings.md#a-pasted-key-is-checked-before-it-is-sent)
covers the local check.

- A key is refused on a positive rejection only. A timeout, a server error or a rate limit is
  unknown, and onboarding accepts the key with a warning, so an offline install completes.
- ElevenLabs is probed once per permission the pipeline needs, and every missing permission is
  reported at once. The speech probe names a voice that cannot exist, so no audio is generated.
- OpenAI is probed on the image generation endpoint with an empty body, the one call Tubematic
  makes. A key that authenticates and lacks that permission is refused.
- Gemini is probed for the text model that mining and review use, and for nothing about images.
- Every secret field has a checker, and the postforme probe is read-only.

Trap: no checker may return the key in its message. OpenAI's `401` quotes part of the submitted
key, so that message is replaced, and a long rejection body is scrubbed before it is cut to
length.

### `test_auto_pilot.py`

Covers the Auto Pilot question and the row written from it.

- The question is advanced, off in the field default and in `SETTINGS_SPEC`, and stored off when
  skipped.
- Its help carries the warning.

Trap: only an explicit `true` turns it on. A blank, `yes` or `1` reads as off, because this
switch removes every human checkpoint.

## What each step writes

### `test_install_config.py`

Covers `apply_install_config`.

- Every prompted field goes to its settings row, in lowercase, and no `.env` file is written or
  read.
- A dry run writes nothing, and a missing database warns.
- The step fails without an OpenAI key, after storing what was typed.

Trap: each `v.get(key, "<literal>")` fallback in an apply function is a second copy of a field's
default. `load_current_values` pre-fills every field, so a skipped question is the same as its
default only while the two copies agree. A test compares them for the publishing switch.

### `test_database_step.py`

Covers `apply_database`.

- It calls `tubematic_core.db.migrate()` and holds no schema of its own, so a new database gets
  the schema the services expect.
- A dry run creates no database file.

### `test_apply_cron.py`

Covers `apply_cron`. The read of the existing crontab is patched.

- It writes one `poll.py` line that names no agent, at the chosen interval, and removes an older
  separate research line.
- The log directory is created before the line is written, because the line's shell redirect
  fails without it.

### `test_volume_reconcile.py`

Covers `actions.py::_reconcile_volume_devices`.

- A named volume whose bind device differs from the configured path is removed so that Compose
  recreates it. Matching volumes are left alone.
- A dry run removes nothing.

Trap: Docker fixes a volume's `driver_opts` when it creates the volume, and Compose does not
move an existing one. Without this step a moved data directory keeps its volumes on the old
path ([Volumes](../16-infrastructure.md#volumes)).

### `test_renderer_step.py`

Covers `actions.py::apply_renderer`.

- One image build covers every service that runs it, and the step starts the API, the MCP server
  and the renderer.
- It waits on the API's healthcheck and then on the MCP server's. A sick API ends the step before
  the MCP wait.
- `_await_health` names the container that is unhealthy. A container still `starting` at the
  timeout is a warning.

### `test_data_dir_checks.py`

Covers the prerequisite check's write probe on each subdirectory of `~/.tubematic-data`.

- A directory this user cannot write or search is a warning with a `sudo chown` hint. The
  containers run as root and keep working, so it is not an error.
- A missing directory is not judged, because the `directories` step creates it.
- The probe and the `directories` step share one list, `DATA_SUBDIRS`.

Trap: the probe needs write and search permission together. A directory with write and no search
cannot hold a new file, and a write-only probe passes it.

Needs: patch the directory names on `onboard.checks`, where they are looked up. A patch on
`onboard.config` leaves the probe reading the real home directory.

### `test_auth_onboarding.py`

Covers the `auth` step, `--set-password`, `--rotate-tokens` and the Executor's two secret
operations ([Authentication](../16-infrastructure.md#authentication)).

- The step creates the tokens and asks for a password only when none is set. The database holds
  the hash.
- Under `--dry-run` the Executor records the directory and the token names and no value.
- Changing a password rotates `session_secret`, which signs every dashboard session out.
  `--set-password` works before the secrets directory exists.
- `--rotate-tokens` changes nothing while work is in flight. It rewrites each token in place,
  restarts the services that read one and reloads only the agents that cache it.
- The checklist reports a missing password or token and probes the MCP server. A stopped stack
  reads as unknown.

Trap: a rotation whose restart or reload fails exits non-zero. The files already hold the new
tokens, so exit 0 would report as a success an install whose services refuse each other's calls.

## Agent install

### `test_agent_install.py`

Covers `onboard/agent_install.py`: `--install-agent`, `--uninstall-agent`, `--list-agents` and the
post-install checklist, for Claude Code, Codex and OpenCode. Every agent CLI call is stubbed,
because a model probe is a billed run. [Deployment](../07-agent-layer.md#deployment) describes the
flow, and the [Agent CLI Reference](../22-agent-cli-reference.md) has each CLI's paths and
commands.

- Before any question: a database, the binary, a login checked with the CLI's own command line,
  and the default config root. A workspace may not overlap the poll logs or another agent's
  workspace. `--dry-run` turns each stop into a warning and makes no probe.
- A model or effort probe reads a rejection marker as invalid even with exit 0, and a failure
  without the marker as unknown. The effort question is advanced and stores `high` when skipped.
  Its probe runs anyway and only warns.
- Each agent deploys to its own paths with its own MCP command line, and a Codex or OpenCode
  install creates no `.claude` path. The registration (`mcp_auth()`) names the token file and
  this install's helper and does not hold the token. Codex's helper is patched into `config.toml`
  after `mcp add`, and OpenCode is reloaded after registering.
- The data directory is denied to the agent's reads. Claude's rule is `Read(//<abs>/**)`, with a
  double leading slash, because Claude Code reads one slash as relative to the project.
  OpenCode's rules and MCP entry go into Tubematic's own document in the workspace
  ([OpenCode](../22-agent-cli-reference.md#opencode)).
- Uninstall removes what the install deployed and archives the row. A redeploy removes the
  skills in `RETIRED_SKILLS`, because `_copy_skills` only adds files. The checklist's skills
  check looks for a named Tubematic skill, because the Remotion installer creates the skills
  directory too.

Trap: OpenCode resolves permissions by the last matching rule and loads
`.opencode/opencode.jsonc` after `.opencode/opencode.json`. A membership test would pass while a
later rule or a sibling document overrides the managed rules, so the tests and the checklist
assert that the managed rules come last and that both files are Tubematic's. The schema test
compares `AGENTS_SCHEMA` with a fully migrated database, column positions included, because a
later `ADD COLUMN` appends and leaves the first migration's text untouched.

## Compose files and overrides

### `test_compose_topology.py`

Covers `docker-compose.yml` and the test stack's renderer, parsed as YAML
([Services](../16-infrastructure.md#services)).

- Five services with one process each. The worker runs `worker.py` and the renderer
  `render_agent.py`. The API and the MCP server start through `entrypoint.sh`, and the other two
  bypass it.
- Each healthcheck probes its own port with `curl -fs`. The API depends on nothing, and the MCP
  server and the worker wait for a healthy API at startup only.
- Ports bind to loopback, and the worker and the renderer publish none. The API serves the render
  gateway on 4443 without publishing it.
- The renderer has no database mount, mounts `/jobs` read-write for the stills server and is pointed
  at the gateway. The gateway's TLS key is mounted in the API alone. The test stack's renderer has
  the same shape. A read-only `/jobs` failed every Cartoon 3D still with `EROFS`.
- No service uses `env_file`, and every secret is a file in the secrets directory under the name
  `tubematic_core.auth` writes. The Dockerfile's `CMD` names a process, because `entrypoint.sh`
  ends in `exec "$@"`.

Trap: the mounts of the MCP server, the worker and the renderer are each asserted as an exact
set, so a new mount is a decision. The dashboard mounts neither the logs nor the backups
directory, because a backup is a copy of the database that holds every key.

### `test_gpu_step.py`

Covers the `gpu` step and the Compose override it writes, `onboard/gpu.py`
([GPU override](../16-infrastructure.md#gpu-override),
[The Compose override](../20-gpu-and-remote-renderers.md#the-compose-override)).

- `nvidia-smi` output is parsed for every GPU. A row that does not parse is skipped, and a
  missing or failing `nvidia-smi` means no GPU.
- The override reserves the chosen GPU by `device_ids`, changes `tubematic-renderer` only and sets
  `NVIDIA_DRIVER_CAPABILITIES`. A foreign file at its path is an error. `_compose()` is the bare
  command when no override exists.
- The step asks nothing without a GPU, removes a stale override when the GPU is gone, and keeps
  one when Docker cannot be reached. With no `nvidia` runtime it offers the CPU.
- On a running install a changed choice recreates `tubematic-renderer` only, with `up`. An
  unchanged choice recreates nothing.
- The `--check` readout names the GPU only when the renderer's probe confirmed it, and warns when
  the renderer still runs on the previous choice. The probe is read from the built-in renderer's
  row in the `renderers` table, and a `gpu_probe_result` settings row counts for nothing.

Trap: the step does not kill a render to apply a change. It writes the hold on render claims
before it looks for a render and releases it afterwards, because a render claimed between the
look and the recreate would be killed. A second run that cannot take the recreate lock leaves the
first run's hold alone. A database it cannot read, or a hold it cannot write, defers the recreate.

### `test_remote_renderers_step.py`

Covers the opt-in `renderers` step and the Compose override it writes,
`onboard/remote_renderers.py`
([Remote-renderers override](../16-infrastructure.md#remote-renderers-override)).

- The address is a host name or IP address with an optional port. An address another machine
  cannot dial (loopback, "any", multicast, link-local) is refused with the reason, and an IPv4
  address written as IPv6 is judged as that IPv4 address.
- The override publishes the gateway on `tubematic-api` only, adds an IPv6 binding only for an
  IPv6 address, and anything else at its path is a problem that names the step.
- The local check runs against a real TLS server on a loopback port and compares the certificate
  with `gateway_pin()`. It tells another certificate (`wrong_cert`) from a closed port and from a
  port that does not speak TLS.
- The step is skipped by a full install and by `--force`, and runs when named with `--step`.
- A first enrollment token is printed only when confirmed, and its secret is stored hashed.

Trap: the override file, the `render_gateway_address` row and the API container change together.
A publish upload in flight changes none of them. A failed `up` puts the previous file and row back
and runs `up` again. An API that is not `running` is neither started nor checked, because
`up -d tubematic-api` on a stopped install would start the API alone.

## Stack control and upgrade

### `test_stack.py`

Covers `onboard/stack.py`, the stack control that `upgrade.py` and `scripts/service.py` share.

- The in-flight gate blocks on a video that is `RENDERING` or `VOICING`, a publish whose upload
  has not finished, a held poll lock, an agent session a stopped poller left running, and a
  database it cannot read. `--force` proceeds and still names the work.
- The lock and the session registry are the paths `scripts/poll.py` uses, since any other path
  excludes nothing, and the lock file is not deleted
  ([Lock and heartbeat](../13-the-poller.md#lock-and-heartbeat)).
- `start` creates the data directories and missing tokens and reconciles the volumes before
  `up`. `stop` runs `docker compose stop` and does not remove containers.
- A service that fails its healthcheck, or a worker or renderer that is not running, fails the
  start. `_container_command` reads the command a container was created with, which is how
  `upgrade.py` tells an old renderer from a new one.
- The status report works with no database, no crontab and no Docker. A database newer than this
  code's migrations is reported as incompatible.

Trap: reconciling a moved volume runs `docker compose down`, which stops every container. `start`
therefore takes its caller's gate as a required argument, asks it first, and afterwards brings
back every service, including those the caller did not name.

### `test_upgrade.py`

Covers `upgrade.py`, loaded by path. Every step records itself on one dry-run executor, so one
list proves the order ([`upgrade.py` in detail](../18-releases.md#upgradepy-in-detail)).

- The order is images, stop, directories, volumes and `up`, then cron. The in-flight gate runs
  before anything changes and again after the images, because a long build is when a queued
  render can start.
- Pre-flight refusals, each before anything changes: no dashboard password, no stored OpenAI key,
  a database newer than this code, a GPU or remote-renderers override Docker cannot apply, and a
  generated scene that imports the removed component or cannot be read. The unreadable-scene
  refusal prints the `chmod` command for root-owned `0600` scenes
  ([Pre-flight refusals](../18-releases.md#pre-flight-refusals)).
- `--no-stop` is refused while a token file is missing, while one of two named migrations is
  pending (each constant is checked against the real file), and while the running renderer was
  created with the combined loop ([`--no-stop`](../18-releases.md#--no-stop)). That last refusal
  reads the renderer container's own command, and a command that cannot be read counts as old.
- `upgrade.py` runs no migration: `tubematic_core.db.migrate` is replaced by a stub that fails
  the test, and the containers migrate under their own lock when they start. The command runs
  with no terminal.
- Live agents are redeployed, and an agent left without a working MCP registration fails the
  exit code after the upgrade finishes. A successful upgrade removes the old images one at a time
  without forcing, and one that needs attention removes none.

Trap: the removed-component check is a lexer and fails closed
([The removed-component check](../18-releases.md#the-removed-component-check)). Do not replace
it with a substring search: comments and strings that mention the component must pass, and an
escaped, computed or split import must refuse. The check runs a second time after the last work
gate, because the old MCP server keeps serving during the build and can write such a scene.

## Presentation

### `test_prompt.py`

Covers the logic of `onboard/prompt.py`, with `ask_field`'s questionary calls stubbed.

- `prompt_step` asks the fields of one step, skips advanced fields unless the full questionnaire
  is on, and writes the answers into the config.
- A required key is asked again until supplied, unless `--allow-skipping` is set.
  `--disable-verification` makes no provider call and still refuses a malformed paste.
- A condition reads the answer given earlier in the same step and not the pre-filled value.
- The model list keeps its order with the first as the default. A rejected model is dropped and
  one that cannot be verified is kept.
- The summary at the end of a step lists only the questions that were asked.

Trap: a blank roster answer with nothing stored is accepted. On a new install the current value
is the pre-loaded roster, so an empty answer means the voices were removed. Colours and live
prompt behaviour are not tested, because `onboard.py` refuses to run without a terminal.

### `test_plain.py`

Covers `onboard/plain.py`, the printed reports and the frame around each question.

- `--steps` lists for each step the questions `fields_for_step` would ask.
- A dry run continues past a failed hard prerequisite.
- The question frame encloses the help, the progress and the prompt line.

Trap: the summary printed at the end of a step masks every secret (`_display_answer`), because it
stays in the terminal's scrollback. `plain.py` must not import the interactive prompt library,
since `--status` and `--steps` are reports that run without a terminal.
