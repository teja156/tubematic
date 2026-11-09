# Agent CLI Reference

This page lists the behaviour of each supported agent CLI (Claude Code, Codex and OpenCode) that
Tubematic depends on, as coded in the CLI's adapter class in `scripts/agent_adapters.py`.
[The Agent Layer](07-agent-layer.md) explains the layer these facts belong to.

In the commands below, `<workspace>` is the agent's workspace (`~/.tubematic-agent/<agent>` by
default), `<url>` is the MCP server's address (`http://localhost:4100/mcp` unless the `mcp_port`
setting names another port), `<token file>` is `~/.tubematic-data/secrets/mcp_token`, and `<helper>`
is the installer's own Python interpreter followed by `<install>/scripts/mcp_auth_header.py`, which
prints `{"Authorization": "Bearer <token>"}`. To install, update or uninstall an agent, see
[Agents](../user-guide/12-agents.md).

---

## Claude Code

Agent id `claude`, binary `claude`, adapter `ClaudeAdapter`.

### Unattended invocation

```
claude -p <prompt> --output-format json [--model <model>] [--effort <level>]
```

| Part | Why it is there |
|---|---|
| `-p <prompt>` | Runs one prompt without the interactive UI, then exits |
| `--output-format json` | Prints one JSON object when the run ends. Usage is read from it |
| `--model <model>` | Sent when a model applies. Takes an alias (`opus`, `sonnet`, `fable`, `haiku`) or a full model ID |
| `--effort <level>` | Sent when an effort level applies |

The command line carries no permission flags. Permissions come from files in the workspace (see
[Permissions](#permissions)), and Tubematic does not use `--dangerously-skip-permissions`.

### Login check

`claude auth status --json` prints JSON on stdout and makes no model call. The CLI counts as logged
in when `loggedIn` is `true`. The exit code and stderr are ignored. The installer tells a
logged-out user to run `claude` once interactively, or `claude auth login`.

### Files and MCP registration

| Scope | Skills | Commands | MCP registration |
|---|---|---|---|
| `user` (default) | `~/.claude/skills/` and `<workspace>/.claude/skills/` | `~/.claude/commands/` | User scope: `mcpServers` in `~/.claude.json` |
| `project` | `<workspace>/.claude/skills/` | `<workspace>/.claude/commands/` | Local scope: `projects.<workspace>.mcpServers` in `~/.claude.json` |

A user-scope install copies the skills to the home directory for every session, and to the
workspace, where scheduled runs start. The installer registers the server with two commands. A
project-scope install drops `--scope user` and runs them from the workspace.

```
claude mcp remove --scope user tubematic
claude mcp add-json --scope user tubematic '{"type":"http","url":"<url>","headersHelper":"<helper>"}'
```

- `claude mcp add` has no option for a header helper, so the installer uses `mcp add-json`.
- `claude mcp` refuses to add a name that already exists (observed on Claude Code 2.1.296), so the
  installer removes the entry first. On a first install that removal fails, which is expected.
- Uninstalling runs the same `claude mcp remove`.
- The config root is `~/.claude`. No environment variable moves it.
- The Remotion skills (agent flag `claude-code`) land in Claude Code's own skills directory.
- The model sees each tool as `mcp__tubematic__<tool>`.

### MCP token

The registration's `headersHelper` holds `<helper>`. Claude Code runs it on every connection, so a
rotated token needs no new registration. The helper is a separate process that reads the token file
itself, so the `Read` deny on the data directory does not block it.

### Permissions

The installer merges three lists into `<workspace>/.claude/settings.json`
(`onboard/actions.py::_write_agent_allowlist`):

- `permissions.allow`: `mcp__tubematic`, `WebFetch`, `WebSearch`, `Read`, `Glob`, `Grep`. It grants
  no `Write` and no `Bash`.
- `permissions.additionalDirectories`: the poll logs directory, `~/.tubematic-agent/logs`.
- `permissions.deny`: `Read(//<home>/.tubematic-data/**)` and `Read(~/.tubematic-data/**)`
  (`onboard/actions.py::claude_read_denies`).

It also sets `projects.<workspace>.hasTrustDialogAccepted` to `true` in `~/.claude.json`. Claude
Code ignores a project's `permissions.allow` in `-p` mode until the project is trusted, so both
files are needed.

In a rule, `//path` is absolute and `~/path` starts at the home directory. A single leading slash
anchors at the settings file's project, so `Read(/home/...)` denies nothing. A `Read` rule also
covers `Grep` and `Glob`, and a deny wins over an allow whatever their order.

### Rejected model or effort

The install prompt suggests the aliases, then the model IDs found in the installed binary's own
catalog.

A rejected model is read from the output, and the exit code is ignored. The markers are
`unrecognized_model` and `may not exist or you may not have access to it`, matched across stdout
and stderr. A plain `claude -p` run exits `0` on a model it does not recognise. Under
`--output-format json` the same run exits `1`, with the first marker on stderr and the second in
the JSON `result` (observed on Claude Code 2.1.281). An unknown model fails locally with no API
call.

Effort fails in two ways (observed on Claude Code 2.1.278). An unknown value prints a warning on
stderr and exits `0`, and the run does its work at the default effort, so nothing needs a retry. A
CLI too old to know the flag prints `error: unknown option '--effort'`, exits `1` and runs nothing.
`effort_rejected` matches the second case only: a non-zero exit, the text `--effort`, and
`unknown option` or `unknown argument`. It reads stderr only, so a session whose own output
mentions the flag cannot match.

The CLI rejects the flag whatever the model, so the install can probe effort without one
(`PROBES_EFFORT_WITHOUT_A_MODEL = True`).

### Usage and cost

`parse_usage` reads `modelUsage` from the JSON object: the tokens and the `costUSD` of each model
the session used, one usage event per model. `costUSD` is Claude Code's own figure at API list
price, whatever the login, so no price table is involved.

### Traps

- The CLI treats an unrecognised subcommand as a prompt, so a mistyped verification command becomes
  a billed model call.
- An allowlist written without the trust record has no effect in an unattended run, and nothing
  reports it.

---

## Codex

Agent id `codex`, binary `codex`, adapter `CodexAdapter`. The behaviour below was observed on
codex-cli 0.155.1 unless a line names another version.

### Unattended invocation

```
codex exec --json --skip-git-repo-check -s read-only -c approvals_reviewer="auto_review" \
  [-m <model>] [-c model_reasoning_effort=<level>] -- <prompt>
```

| Part | Why it is there |
|---|---|
| `exec` | Runs one prompt without the interactive UI |
| `--json` | Makes stdout a JSONL event stream, which usage is read from. It also moves the CLI's own error messages onto stdout |
| `--skip-git-repo-check` | The workspace is not a git repository. Without the flag Codex exits `1` with `Not inside a trusted directory and --skip-git-repo-check was not specified` |
| `-s read-only` | The sandbox: files are readable and not writable. MCP tool calls and the built-in web search work under it |
| `-c approvals_reviewer="auto_review"` | Lets MCP tool calls run (see below) |
| `-m <model>` | Sent when a model applies. Takes a catalog slug such as `gpt-5.6-sol` |
| `-c model_reasoning_effort=<level>` | Sent when an effort level applies |
| `--` | `codex exec` has the subcommands `resume`, `fork` and `review`. Without the separator, a prompt that is one of those words is parsed as the subcommand |

`codex exec` defaults its approval policy to `Never`. Under `Never` an MCP tool call is refused
with `MCP tool call requires approval, but approval policy is never`, and the run still exits `0`.
Every pipeline action goes through MCP, so a run without `approvals_reviewer` does nothing and
looks healthy. The setting routes approval requests to Codex's automatic reviewer and leaves the
approval system on. Tubematic uses it in place of `--dangerously-bypass-approvals-and-sandbox`.

### Login check

`codex login status` answers in prose on stderr, with no `--json` form, and makes no model call. It
exits `0` when logged in and `1` when logged out. `logged_in` joins stdout and stderr and requires
both an exit code of `0` and text that starts with `Logged in`. The installer tells a logged-out
user to run `codex login`.

### Files and MCP registration

| Scope | Skills | Commands | MCP registration |
|---|---|---|---|
| `user` (the only scope) | `~/.codex/skills/` | None | Global: `[mcp_servers.tubematic]` in `~/.codex/config.toml` |

```
codex mcp add tubematic --url <url>
```

- Codex is user-scope only. `codex mcp add` has no scope flag, and Codex discovers project-scope
  skills (`<project>/.codex/skills`) only inside a git repository, which the workspace is not.
- Codex finds `~/.codex/skills/` from any working directory, so the workspace holds no second copy.
- Codex has no user-defined slash commands.
- `codex mcp add` overwrites an existing entry and drops every key it does not set, the header
  helper included (observed on codex-cli 0.160.0).
- Uninstalling runs `codex mcp remove tubematic`.
- The config root is `$CODEX_HOME`, else `~/.codex`. A non-default root blocks the install (see
  [Deployment](07-agent-layer.md#deployment)).
- The Remotion skills (agent flag `codex`) land in `~/.agents/skills/`, which Codex also reads.

### MCP token

`codex mcp add` has no header option. After every add, the installer sets
`http_headers_helper = "<helper>"` inside `[mcp_servers.tubematic]` in `config.toml`
(`CodexAdapter.set_mcp_header_helper`), and Codex runs the helper on every connection.

The change is a line edit inside that one table, because Python's standard library cannot write
TOML and a full rewrite would drop the operator's comments. The installer parses the edited text
before writing it, and leaves the file alone if it does not parse.

### Permissions

`-s read-only` on the command line is the whole permission setup. The installer writes no
allowlist and no trust record: `codex exec` runs without prompting in a directory that
`config.toml` does not list under `[projects]`.

The sandbox mode has no per-path read rule. A Codex agent can read any file the host user can,
`~/.tubematic-data` included.

### Rejected model or effort

Codex has no aliases. The install prompt suggests the slugs in the CLI's catalog cache
(`models_cache.json` under the config root).

A rejected model exits non-zero and costs one refused API call. The wording depends on the login,
and `model_rejected` matches both forms:

- A ChatGPT account prints that the model `is not supported when using Codex`.
- An API key returns a 404 saying the model `does not exist or you do not have access to it`.

The match also requires a non-zero exit, because the second marker is an ordinary sentence that a
successful session could print. Codex also warns `Model metadata for ... not found` for models the
API then accepts, so that warning is not a marker.

Codex accepts the effort flag always, because it is a generic `-c` override. The API rejects a
level the chosen model does not support: `gpt-5.5` stops at `xhigh` and rejects `max`. The run
exits `1`, and the error names the parameter `reasoning.effort`, which is the marker. Under
`--json` the rejection arrives on stdout as an `error` or `turn.failed` event (observed on
codex-cli 0.156.1). `effort_rejected` requires a non-zero exit and reads stderr plus those error
events. It does not read the `item.*` events, which hold the agent's own text.

The rejection depends on the model and level together, so the install probes effort with the
default model (`PROBES_EFFORT_WITHOUT_A_MODEL = False`).

### Usage and cost

`parse_usage` sums the token counts of every `turn.completed` event into one usage event for the
run. The stream names no model and no cost. The model is the `-m` value, else the `model` key in
`config.toml`, and the cost comes from Tubematic's price table.

### Traps

- A developer's own `~/.codex/config.toml` may already name an approvals reviewer, which hides a
  missing `approvals_reviewer` on that machine. Test the command line in a clean environment.
- A login check that reads stdout alone reports every logged-in CLI as logged out.
- A manual `codex mcp add` removes the header helper. Run `--install-agent` again afterwards.

---

## OpenCode

Agent id `opencode`, binary `opencode`, adapter `OpenCodeAdapter`. Tubematic supports the v2 CLI,
published as `@opencode/cli`. The older `opencode-ai` package uses different configuration field
names and is not supported. The behaviour below was observed on OpenCode 2.0.14 unless a line
names another version.

### Unattended invocation

```
opencode run --auto --format json [--model <provider>/<model>[#<level>]] -- <prompt>
```

| Part | Why it is there |
|---|---|
| `run` | Runs one prompt without the interactive UI |
| `--auto` | Approves every permission request that no rule denies (see below) |
| `--format json` | Makes stdout a JSONL event stream whose events carry the `sessionID` that usage is read by. It also moves the CLI's own errors onto stdout |
| `--model` | Sent when a model applies. The effort level rides on it as a `#variant` suffix (`--model anthropic/claude-sonnet-4-5#high`), so a run without a model carries no effort |
| `--` | Keeps a prompt that begins with a dash from being parsed as a flag |

OpenCode resolves a permission that no rule matches to `ask`. A non-interactive `opencode run`
rejects an `ask` and cancels the session: it prints `Session interrupted: shutdown` and exits `1`.
The workspace sits beside the poll logs and the prompts tell the agent to read them, so an ordinary
run reaches outside its working directory. Under `--auto` a `deny` rule still holds: the tool
returns an error and the session continues.

### Login check

`opencode auth list` makes no model call. It exits `0` whether or not anything is authenticated,
and a logged-out CLI prints `No authenticated integrations` on stdout. `logged_in` requires an exit
code of `0`, some output, and the absence of that phrase. The installer tells a logged-out user to
run `opencode auth login`.

### Files and MCP registration

| Scope | Skills | Commands | MCP registration |
|---|---|---|---|
| `user` | `~/.config/opencode/skills/` | `~/.config/opencode/commands/` | With `--global`: `~/.config/opencode/opencode.json` |
| `project` | `<workspace>/.opencode/skills/` | `<workspace>/.opencode/commands/` | Run from the workspace: `<workspace>/opencode.json` |

```
opencode mcp add tubematic [--global] --url <url> --header "Authorization=Bearer {file:<token file>}"
```

At both scopes the installer also writes a managed document, `<workspace>/.opencode/opencode.json`
with an identical `opencode.jsonc` beside it. It holds the permission rules and a second, complete
copy of the server entry, and scheduled runs read it because they start in the workspace.

- The config root is `$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode`. A non-default root
  blocks the install (see [Deployment](07-agent-layer.md#deployment)).
- OpenCode finds `~/.config/opencode/skills/` from any working directory, so a user-scope install
  puts no second copy in the workspace.
- A config document is named `opencode.json` or `opencode.jsonc`, and `opencode mcp add` writes to
  whichever exists. With only a `.jsonc` it appends there and keeps comments and trailing commas.
  With both it chooses `.json`, and with neither it creates `.json`. The adapter resolves the name
  the same way (`CONFIG_BASENAMES`).
- OpenCode accepts comments and trailing commas in a plain `opencode.json` too. Tubematic reads
  every config document with `parse_jsonc`, a string-aware scanner, because `json.loads` fails on
  such a file and a regular expression would corrupt a URL that contains `//`.
- `opencode mcp add` overwrites an existing entry (observed on OpenCode 2.0.26).
- `opencode mcp` has the subcommands `list`, `add`, `auth` and `logout`, and no `remove`.
  `mcp_remove_argv` returns `None`, and uninstalling edits `mcp.servers.tubematic` out of the
  document the registration went into.
- That edit changes the text, so the operator's comments survive. It is written only if the result
  parses and equals the original data with that one key removed. Otherwise the installer leaves the
  file alone and asks you to remove the entry by hand, as it does for a document that does not
  parse.
- The Remotion skills (agent flag `opencode`) land in `~/.agents/skills/`, which OpenCode also
  reads.

OpenCode's Code Mode is on by default for MCP servers. It replaces the native tools with a
`search()` and `execute()` sandbox in which a tool is called as `tools.tubematic.<tool>(…)`. The
skills name their tools directly, so an agent in Code Mode spends its session looking for them. The
managed server entry sets `"codemode": false`, and the tools then appear as `tubematic_<tool>`.

The managed entry is complete: `type`, `url`, `headers` and `codemode`. An entry with only
`codemode` merges far enough for `opencode mcp list` to report the server connected, and Code Mode
stays on. The entry does not set `oauth`: OpenCode documents OAuth as the default for a remote
server, but a server that answers a bad token with a bare `WWW-Authenticate: Bearer` connects with
the header alone, and `opencode mcp add` has no flag for it.

### MCP token

The header value `Bearer {file:<token file>}` makes OpenCode read the token file itself (observed
on OpenCode 2.0.26; the substitution is not in the v2 documentation). OpenCode answers from a
background service that caches its config and the token. The installer runs `opencode reload`
after every deploy, and `python3 onboard.py --rotate-tokens` runs it after a rotation. Without the
reload the service keeps its old connection and the MCP server answers `401`. The substitution
happens when the config loads, so the rules on the data directory do not block it.

### Permissions

The managed document's `permissions` list holds these rules, in this order
(`OpenCodeAdapter.PERMISSION_RULES`, completed by `onboard/actions.py::managed_permission_rules`):

| Effect | Action | Resource |
|---|---|---|
| allow | `tubematic_*` (the MCP tools), `webfetch`, `websearch`, `read`, `grep`, `glob` | `*` |
| deny | `edit`, `write`, `shell` | `*` |
| deny | `read` | `*.env` and `*.env.*` |
| allow | `read` | `*.env.example` |
| allow | `external_directory` | `<home>/.tubematic-agent/logs/*` |
| deny | `external_directory`, then `read` | `<home>/.tubematic-data/**` |

OpenCode concatenates the `permissions` lists of every config document it loads, and the last
matching rule wins. Documents load in this order (observed on OpenCode 2.0.15):

| Precedence | Document |
|---|---|
| Lowest | `~/.config/opencode/opencode.json(c)` |
| | `<ancestor>/opencode.json(c)` |
| | `<workspace>/opencode.json(c)` |
| | `<ancestor>/.opencode/opencode.json(c)` |
| Highest | `<workspace>/.opencode/opencode.json(c)` |

That order explains the design:

- The rules live in `<workspace>/.opencode/`, because a rule in the workspace's direct
  `opencode.json` loses to one in a developer's own `~/.opencode/opencode.json`.
- Tubematic writes both basenames. `.opencode/opencode.jsonc` loads after
  `.opencode/opencode.json`, so one rule in a file Tubematic did not write would outrank every rule
  in the file it did. Other names in that directory (`opencode.json5`, `config.json`,
  `opencode.jsonc.local`, `settings.json`, `opencode.yaml`) are not loaded. The post-install checks
  report a missing managed file.
- The installer moves its own rules to the end of the list on every deploy and leaves the other
  rules where they were, and the post-install checks assert the same shape. A `read *.env deny`
  followed by a `read *.env allow` lets the agent read the file.
- The list asserts the allows as well as the denies. Without them, a `deny webfetch`,
  `deny websearch` or `deny tubematic_*` in the operator's global config would be the only matching
  rule and would stop research or every MCP tool.
- `shell` and the `.env` reads are denied because `--auto` approves an `ask`, which is OpenCode's
  own default for a credential file, and nothing else limits a command OpenCode runs.
- The data directory needs two rules. OpenCode checks `grep` and `glob` against the search pattern,
  so a `read` deny alone does not stop them. Reaching outside the workspace is the separate
  `external_directory` permission.
- OpenCode removes a denied tool from the catalogue the model sees.

The install's workspace question refuses a directory that already holds an OpenCode config
(`onboard/agent_install.py::workspace_conflict`). It exempts Tubematic's own two files in the
workspace that the agent's live `agents` row records. An uninstalled agent's row does not count,
because a document found there after an uninstall is the operator's. When a foreign document sits
beside Tubematic's in the agent's own workspace, the message says to remove that file, and the
pre-filled answer keeps the recorded workspace so that `upgrade.py` does not move the agent.

### Rejected model or effort

Model names are `provider/model` slugs with no aliases, such as `anthropic/claude-sonnet-4-5`. A
provider that namespaces by vendor adds a segment (`openrouter/qwen/qwen3.8-27b`). The install
prompt suggests the output of `opencode models`, which also works logged out.

OpenCode resolves the model and the variant against its catalog before any API call. Both
rejections exit `1`:

| Rejected | Output | Marker |
|---|---|---|
| Model | `Error: Model unavailable: <slug>` | `Model unavailable` |
| Effort | `Error: Variant unavailable for <model>: <variant>` | `Variant unavailable` |

Both matchers require a non-zero exit, because either phrase could appear in a successful
session's output. Under `--format json` the rejection arrives on stdout as an `error` event, and
`effort_rejected` reads stderr plus those error events.

The two wordings differ, so the poller retries a rejected effort level with the chosen model kept.
Effort levels are per-model variant names, so the install probes effort with the default model
(`PROBES_EFFORT_WITHOUT_A_MODEL = False`).

### Usage and cost

`opencode api GET /api/session/<id>/message` returns every message of one session from the local
background service, with no model call. Each assistant message carries its model, its tokens and
OpenCode's own `cost`, and `parse_usage` groups them into one usage event per provider and model.
The JSONL stream alone is not enough, because the event that carries the last step's usage is
sometimes missing. If the session record cannot be read, the stream is used and the usage is marked
estimated.

### Traps

- `opencode mcp list` is unreliable just after a config change or a service restart. For several
  seconds it prints `No MCP servers configured`, then `✓ tubematic  connected`. The post-install
  checks read the config document. By hand, run `opencode reload`, wait, and run the list twice.
- A denied tool cannot be approved from inside a session.
- On OpenCode 2.0.14 a `shell` deny made the free tier refuse to run, with
  `Error from provider (Console): OpenCode's free tier can only be used from within OpenCode`.
  OpenCode 2.0.15 runs normally with the same rule. If a run fails with that message, look at the
  `shell` rule first.
- The free models are too weak to drive the pipeline. Log in to a paid provider.

---

## Comparison

| | Claude Code | Codex | OpenCode |
|---|---|---|---|
| Unattended command | `claude -p <prompt> --output-format json` | `codex exec --json --skip-git-repo-check -s read-only -c approvals_reviewer="auto_review" -- <prompt>` | `opencode run --auto --format json -- <prompt>` |
| Login check | `claude auth status --json`: JSON on stdout | `codex login status`: prose on stderr, and the exit code | `opencode auth list`: prose on stdout, exit code always `0` |
| Install scopes | `user`, `project` | `user` | `user`, `project` |
| User-scope skills | `~/.claude/skills/` and the workspace | `~/.codex/skills/` | `~/.config/opencode/skills/` |
| Slash commands | `~/.claude/commands/` | None | `~/.config/opencode/commands/` |
| Config root | `~/.claude` | `$CODEX_HOME`, else `~/.codex` | `$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode` |
| MCP registration | `claude mcp remove`, then `claude mcp add-json` | `codex mcp add`, then a `config.toml` edit | `opencode mcp add`, plus the managed document |
| MCP deregistration | `claude mcp remove` | `codex mcp remove` | A config edit |
| MCP token | `headersHelper`, run on every connection | `http_headers_helper`, run on every connection | `{file:}`, read when the config loads |
| Permissions | Workspace allowlist and trust record | `-s read-only` | Ordered rules in the managed document |
| Model names | Aliases or full IDs | Catalog slugs | `provider/model` slugs |
| Effort | `--effort <level>`, rejected as a flag | `-c model_reasoning_effort=<level>`, rejected per model | `#variant` on the model, rejected per model |
| Usage and cost | `modelUsage`: tokens and cost | `turn.completed`: tokens only | The session's message record: tokens and cost |
