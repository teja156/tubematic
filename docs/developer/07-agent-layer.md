# The Agent Layer

The AI half of Tubematic is not Python. It is a set of markdown **skills** that teach an agent the
workflow, plus optional **slash commands** that let a human working in an agent session trigger the
same actions the dashboard offers. The MCP server provides
the verbs; the skills decide when and in what order to use them.

That split is the convention to preserve when you extend the system:

> **MCP docstrings own technical contracts. Skills own workflow orchestration.** A skill should not
> restate an MCP tool's parameter signature — the agent already has it, and a second copy goes stale.

A second convention, also load-bearing: **agent-visible text carries no ticket identifiers.** Skills,
slash commands and `@mcp.tool` docstrings are read by a model that cannot look them up. Internal
comments and this documentation are free to reference whatever they like.

---

## The skills

Six ship in `agent_files/skills/`.

| Skill | Activates when | Does |
|---|---|---|
| `tubematic-operator` | Any pipeline session | The state machine. Checks setup, finds workable videos, routes each status to the right action, stops at checkpoints |
| `tubematic-topic-research` | A scheduled research run | Proposes and scores topics across the three sourcing strategies |
| `tubematic-script-writing-skill` | `TOPIC_APPROVED`, or a script revision | The whole scripting contract — segments, length budget, pronunciation, pause markup, and each beat's visual brief |
| `tubematic-create-script-writing-skill` | A script profile is queued at `PENDING` | Extracts a creator's *style* from transcripts into profile markdown |
| `tubematic-scene-config` | `VOICE_READY`, and the revision path | Turns a voiced script and timeline into images, scene TSX, and `scene-config.json` |
| `tubematic-troubleshooting` | Only when a person asks for it by name | Triages a broken install with that person, runs the diagnostics collector, and drafts a redacted bug report for them to file |

Remotion's own best-practice skills are **not vendored here**. `onboard.py --install-agent`
installs them fresh from `remotion-dev/skills`. Do not reference upstream rule-file paths in your
own skills — that layout is outside this repository's control and has already drifted once. Invoke
the skill and follow it.

### The operator skill

`agent_files/skills/tubematic-operator/SKILL.md` is the entry point for every session. It performs a setup check first
— MCP reachable, API healthy, worker running, Chromium alive, ElevenLabs key present — and stops
with a list of failures rather than starting work on a broken install.

Then it routes:

| Status | Action |
|---|---|
| `TOPIC_APPROVED` | Invoke the scripting skill, write `script_segments`, upsert lexicon entries, comment, advance to `SCRIPT_READY` |
| `VOICING` | Call `generate_voice`, which saves the paths itself, then advance to `VOICE_READY`. Already authorized by the human's approval at `SCRIPT_READY`, and the skill says so explicitly. An unattended agent once treated the spend as needing fresh consent, and the video stuck in `VOICING` |
| `VOICE_READY` | Invoke the scene-config skill, verify the image floor, `validate_job`, `submit_render`. **Queue and stop** — do not poll |
| `REVISION_REQUESTED` | Diagnose from the comment thread and route back, or escalate to `FAILED` |
| `TOPIC_PROPOSED` · `SCRIPT_READY` · `VIDEO_READY` | **Stop.** A human decides — or, for a project on [Auto Pilot](14-publishing.md#auto-pilot), the render worker. The skill tells the agent that changes nothing for it: it still never moves a video out of a checkpoint, and a video it finds past one is authorized whoever moved it |
| `VIDEO_APPROVED` | Not workable at all. Publishing is never the agent's — no MCP tool can do it, and the skill is told never to write `SCHEDULED`, `PUBLISHING` or `PUBLISHED` |
| `RENDER_QUEUED` · `RENDERING` · `SCHEDULED` | Not agent-actionable. Worker-owned |

Two ordering rules in it are easy to break:

- **In the revision table, check "pronunciation revision" before the rows below it.** Both a
  pronunciation fix and a visual fix have `video_path` and `voice_file_path` populated, but they need
  different repairs.
- **A `REVISION_REQUESTED → VOICE_READY` transition deliberately does not release the scene claim**,
  so the same session can still submit the render it just prepared.

### The troubleshooting skill

`tubematic-troubleshooting` is the one skill no agent may start by itself. It is the one place an
agent is taught to read logs and run `scripts/collect_diagnostics.py`, and it is meant for a person
at the keyboard — so a scheduled run must never wander into it. Each CLI keeps that switch
somewhere different, and each was probed live:

| CLI | Switch | How a person invokes it |
|---|---|---|
| Claude Code | `disable-model-invocation: true` in the frontmatter | `/tubematic-troubleshooting` |
| OpenCode | `metadata: opencode/autoinvoke: "false"` (it also honours the Claude field) | Ask for "the tubematic-troubleshooting skill" by name; OpenCode has no slash form for a skill |
| Codex | `agents/openai.yaml` beside `SKILL.md`, `policy.allow_implicit_invocation: false` | `$tubematic-troubleshooting` |

**There is deliberately no slash command for it.** In Claude Code a command reaches a skill
*through the model*, which is exactly what `disable-model-invocation` blocks — such a command would
be refused. The skill is its own entry point instead. Nothing fails loudly if a switch is lost, so
`scripts/tests/test_troubleshooting_skill.py` pins all three, plus that no `poll.py` prompt names
the skill.

The skill never redacts anything itself. It runs (or asks the person to run) the collector, which
does the redaction in code — see [Reporting a bug](../user-guide/08-troubleshooting.md#reporting-a-bug)
— and then reads the report once more as a second check, flagging rather than silently editing.
It never posts and never changes pipeline state, and it reads **no raw log at all** — not the data
directory, not `poll.log`, not container output — only the report. That last rule came from a live
run: told to read the poller's log tail, the agent grepped and read the whole file, and since
`poll.log` is not redacted, stored keys went to its model provider. Whatever an agent reads leaves
the machine, so the redacted report is the only log material it is given.

### The scene-config skill

The largest and most opinionated skill, and the one you are most likely to want to change. Its rules
are covered in [Scene Authoring](10-scene-authoring.md); the important thing here is that it is the
*only* place scene cadence, the image floor, and the PHOTO/HYBRID/DIAGRAM/STICK taxonomy are
defined. It is also where a video's [visual register](10-scene-authoring.md#visual-registers) is
settled when the human left the choice on `auto` — the first thing it does, because every rule
after that branches on the answer.

Several of its rules are phrased relative to an assumed number of scenes. Changing the cadence
changes that denominator — re-check the image floor and the bare-image cap whenever you touch it.

---

## Slash commands

Twelve, in `agent_files/<agent>/commands/` — one copy per agent that has a slash-command
mechanism, currently Claude Code and OpenCode. **Codex gets none**, because its CLI has no
user-defined command mechanism at all, so a Codex install deploys skills and the MCP registration
and nothing else — the scheduled pipeline is unaffected, since it is driven by a prompt rather
than by a command.

They are a convenience, not the primary interface: the dashboard is the recommended way to run
Tubematic, and every command but `/tubematic-register-mcp` (an agent repair) has a dashboard
equivalent. A new user-facing action belongs on the dashboard first; a slash command for it is
optional.

The per-agent copies exist because two of the twelve name the agent's own CLI (`claude mcp list`
versus `opencode mcp list`, and the whole MCP-registration walkthrough). A shared copy would print
an instruction that does nothing on the other install. A test pins that every agent ships the same
*set* of filenames, so a command added for one cannot silently not exist for the other, and another
pins that no agent's commands name a different agent's CLI.

| Command | Purpose |
|---|---|
| `/tubematic` | List every command |
| `/tubematic-status` | Pause state, per-status counts, checkpoints awaiting you, this month's spend, container health |
| `/tubematic-submit-new-job <topic>` | Score a topic, file it, and take it straight to `TOPIC_APPROVED` |
| `/tubematic-add-topic <name> — <description>` | Add a curriculum seed domain |
| `/tubematic-pause` · `/tubematic-resume` | Global pipeline pause |
| `/tubematic-pause-domain <id>` · `/tubematic-resume-domain <id>` | Pause or resume topic generation for a curriculum seed domain. See [Domain pause](02-pipeline.md#domain-pause) |
| `/tubematic-list-strategies` · `/tubematic-set-strategy <list>` | Which sourcing modes are active |
| `/tubematic-dashboard-status` | Container and health checks |
| `/tubematic-register-mcp` | Register or re-register the MCP server |

`/tubematic` also lists the [troubleshooting skill](#the-troubleshooting-skill), which is not a
command: as `/tubematic-troubleshooting` in Claude Code, and by name in OpenCode, which has no slash
form for a skill. That is why the two copies of `tubematic.md` differ.

`/tubematic-submit-new-job` is the one worth reading before you modify it. It scores the topic
against the producibility rubric and **stops** below 5; asks for a voice if the roster has two or
more; asks for a script profile if any are `READY`; then calls `create_video`, whose result names the
agent the video was dealt. If the user asked for a different agent it passes `agent_id`; it asks for
a model only if the video's agent has two or more — reading `agents` from `get_pipeline_status`,
since only those names are accepted — then calls `update_video` for the agent, profile, model and
effort level, and **only then** flips the status.

That ordering is not stylistic. `script_profile_id` freezes the moment the video leaves
`TOPIC_PROPOSED`, and `agent_id`, `agent_model` and `agent_effort` stay closed until the next human
checkpoint, so a write after the flip returns `409`.

---

## Agents

An *agent* is the coding-agent CLI that runs the skills against the MCP server. Three are
supported — **Claude Code** (`claude`), **Codex** (`codex`) and **OpenCode** (`opencode`) — and the
pipeline models agents as a list: each installed agent is a row in the `agents` table
([Database](03-database.md#agents)), and every video is pinned to one of them. Any number may be
installed at once; they share the skills, the MCP server and the `agents` table, and differ only in
how each is invoked and where its files live.

For OpenCode this means the **v2** CLI, published as `@opencode/cli`. The older `opencode-ai` npm
package is the 1.x line, whose configuration uses different field names; it is not supported.

**What any agent must be able to do.** Every pipeline action goes through the tubematic MCP server,
and the skills *are* the pipeline's behaviour rather than configuration. So an agent must speak MCP
over streamable-HTTP and read `SKILL.md`-format skills. One that cannot is not a candidate, however
capable it is otherwise. This is also why the skills name MCP tools and never one agent's own file
or web tools: the same markdown is deployed to whichever agent is installed.

**The adapter seam.** `scripts/agent_adapters.py` holds one class per supported agent
(`ClaudeAdapter`, `CodexAdapter`, `OpenCodeAdapter`), registered in `ADAPTERS` under the agent's
id. It owns everything
that differs from one CLI to the next: the headless invocation, the login check, the model probe,
the output markers that mean "model rejected", the model names the install prompt suggests, **and
the deployment layout** — which directories its skills and commands go to, and the argv that
registers and deregisters the MCP server. The poller and the installer both use it — the installer
loads it by path — so there is one copy rather than two kept in sync by hand.

The module is deliberately **data and pure functions only**. Every filesystem write stays in
`onboard/`, behind the executor that makes `--dry-run` truthful, and `scripts/poll.py` imports this
module directly on every cron tick, so it must stay dependency-light.

**Where the three agents differ:**

| | Claude Code | Codex | OpenCode |
|---|---|---|---|
| Headless invocation | `claude -p <prompt> --output-format json` | `codex exec --json --skip-git-repo-check -s read-only -c approvals_reviewer="auto_review" -- <prompt>` | `opencode run --auto --format json -- <prompt>` |
| Usage read from | the one JSON object's `modelUsage` — tokens and Claude's own list-price `costUSD` per model | `turn.completed` events — tokens only, no model name, no cost | `opencode api GET /api/session/<id>/message` — tokens and OpenCode's own `cost` per message |
| Login check | `claude auth status --json` (stdout, JSON) | `codex login status` (**stderr**, prose, exit code) | `opencode auth list` (stdout, prose, **exit code says nothing**) |
| Install scopes | `user` or `project` | `user` only | `user` or `project` |
| Skills land in | `~/.claude/skills/` and the workspace | `~/.codex/skills/` | `~/.config/opencode/skills/` |
| Slash commands | `~/.claude/commands/` | none | `~/.config/opencode/commands/` |
| MCP registration | `claude mcp remove`, then `claude mcp add-json [--scope user] tubematic '{"type":"http","url":…,"headersHelper":…}'` | `codex mcp add tubematic --url <url>`, then `http_headers_helper` patched into `config.toml` | `opencode mcp add tubematic [--global] --url <url> --header "Authorization=Bearer {file:<mcp_token path>}"` |
| MCP token | read by `scripts/mcp_auth_header.py` on every connection | the same helper | read from the file by OpenCode itself; `opencode reload` after every (re)install and every rotation |
| MCP deregistration | `claude mcp remove` | `codex mcp remove` | **no such command** — the config entry is edited out |
| Permission model | workspace allowlist + trust record | `-s read-only` on the command line | ordered rules in the workspace's `.opencode/opencode.json(c)` |
| Model names | aliases (`opus`, `sonnet`, …) or full IDs | catalog slugs (`gpt-5.6-sol`, …) | `provider/model` slugs (`anthropic/claude-sonnet-4-5`), with a vendor segment where the provider namespaces one (`openrouter/qwen/qwen3.8-27b`) |
| Effort | `--effort <level>` (flag-level rejection) | `-c model_reasoning_effort=<level>` (rejected per model) | a `#variant` on the model (rejected per model) |
| Config root | `~/.claude` | `$CODEX_HOME`, else `~/.codex` — a non-default root **blocks the install** | `$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode` — likewise |

Most of those asymmetries are worth the reasoning, because each looks like an omission:

- **Codex is user-scope only** because its MCP registration is global — `codex mcp add` has no
  scope flag — and its project-scope skills (`<project>/.codex/skills`) are discovered only inside
  a git repository, which the agent workspace is not. Offering `project` would be a half-promise,
  so the install simply does not ask.
- **Codex needs no allowlist and no trust record.** Its permissions come from `-s read-only` on
  argv, which is the equivalent of Claude's allowlist: MCP tool calls and its built-in web search
  work, and the filesystem is readable but not writable. The agent writes only through MCP tools,
  so that is sufficient for writes; for reads it is a gap (see
  [Deployment](#deployment)). `codex exec` runs in an untrusted directory without prompting, so there is
  nothing to pre-accept.
- **No agent's config ever holds the MCP token**, and each registration is shaped by what its CLI
  can do — all three were probed live. Claude Code's `mcp add` has no way to name a header helper,
  so the install uses `mcp add-json`; and because it refuses a name that already exists, a redeploy
  removes the old entry first. Codex's `mcp add` has no header flag at all and drops any key it does
  not set, so the installer patches `http_headers_helper` into `[mcp_servers.tubematic]` after every
  add — a line edit inside that one table, parsed before it is written, because the standard library
  reads TOML but cannot write it and a rewrite would drop the operator's comments. OpenCode has no
  helper, but its `{file:}` substitution reads the token file itself (undocumented, but probed); it
  caches its config in a background service, so both a (re)install and `--rotate-tokens` run
  `opencode reload` — seen live after an upgrade, the service otherwise kept its old, token-less
  connection and was refused until something reloaded it. The helper
  is this install's own interpreter and script, so **the registration names the install
  directory**: `upgrade.py` re-registers from the new one, and an install moved by hand must re-run
  `--install-agent`. The post-install checklist compares each registration with what the installer
  would write now, so it reports a missing helper and a moved install alike.
- **Codex reports its login status on stderr, not stdout**, and `logged_in` therefore takes both
  streams and the exit code. Reading stdout alone sees an empty string and reports every logged-in
  CLI as logged out, which blocks the install outright. It requires exit 0 *and* the affirmative
  wording, because the two error directions are not symmetric: a false "logged out" blocks an
  install in front of a human, while a false "logged in" lets the install finish and every
  unattended scheduled session fail silently afterwards.
- **Codex needs `approvals_reviewer="auto_review"` or it cannot use MCP tools at all**, which
  makes this the single most important flag in its argv. `codex exec` defaults its approval policy
  to `Never`, and an MCP tool call under `Never` is refused outright — the run prints
  `MCP tool call requires approval, but approval policy is never` and then **exits 0**. Since every
  pipeline action goes through MCP, a Codex session without this does nothing while looking perfectly
  healthy. The setting routes approval requests through Codex's own automatic reviewer rather than
  switching the approval system off, which is why it is used in preference to
  `--dangerously-bypass-approvals-and-sandbox`; with `-s read-only` alongside it, the blast radius
  is a read-only sandbox either way.

  Worth knowing when testing: a developer's own `~/.codex/config.toml` may already name a reviewer,
  which makes the bare command appear to work on their machine and fail on a clean install. Verify
  this one in a fresh environment, not a personal one.
- **A non-default `CODEX_HOME` blocks the install, deliberately.** That variable selects the root
  holding Codex's authentication *and* the skills this installer deploys, and cron strips the
  environment down to `HOME`/`LOGNAME`/`PATH`/`SHELL` — so an install made under it would verify
  here and then run every scheduled session against a different root: no skills, and almost certainly
  logged out. The environment cannot be carried across either, because the cron line deliberately
  names no agent, so one agent's variable has no place in it. This is the same judgement as
  refusing a logged-out CLI: an install known to produce a silently broken schedule is not worth
  completing. `--dry-run` downgrades it to a warning, like every other blocker. The same guard runs on every other lifecycle path — upgrade, uninstall and the post-install checks — because the dangerous case is not installing under an override but setting one *afterwards*, which would make an upgrade deploy where the scheduled runs never look and an uninstall archive the agent while removing nothing. Read-only paths report the disagreement instead of acting on it, and resolve skills against the root cron will actually use.
- **Codex's prompt is passed after a `--` separator.** `codex exec` has subcommands (`resume`,
  `fork`, `review`), so a bare positional prompt that happened to be exactly one of those words
  would be parsed as the subcommand instead. OpenCode's prompt is passed the same way, so a prompt
  beginning with a dash cannot be read as a flag.
- **OpenCode needs `--auto`, and for a sharper reason than it sounds.** OpenCode resolves a
  permission no rule matches to `ask`. In a non-interactive `opencode run` an `ask` is
  auto-**rejected**, and a rejection cancels every pending request in the session — the run prints
  `Session interrupted: shutdown` and exits 1 having done nothing. That is not an edge case here:
  the agent workspace sits beside the poll logs and the prompts tell the agent to read them, so
  reaching outside the working directory is on the normal path. `--auto` approves anything not
  explicitly **denied**, and the denials are what the installer writes into the workspace (below),
  so this is a narrowing of `ask`, not a bypass. A configured `deny` still holds under `--auto`,
  returns an ordinary tool error, and lets the session continue.
- **OpenCode's MCP tools are hidden by default, and the failure looks like a stupid agent.**
  OpenCode's *Code Mode* is on by default for MCP servers: instead of native tools the agent gets a
  `search()`/`execute()` sandbox in which the tools are named `tools.tubematic.<tool>(…)`. The
  skills name their tools directly, so with Code Mode on the agent spends the whole session hunting
  a catalogue and concludes the tools do not exist. The installer therefore sets
  `"codemode": false` on the server entry after registering it, which makes the tools appear
  natively as `tubematic_<tool>`. Note the name shape: not Claude's `mcp__tubematic__<tool>`.

  `oauth` is deliberately **not** set alongside it. Remote MCP servers are documented as using
  OAuth by default, but a server that answers a bad token with a bare `WWW-Authenticate: Bearer`
  connects with the header alone, and `opencode mcp add` has no flag for it, so leaving it out keeps
  the global and the managed entry alike.
- **OpenCode's login check cannot use the exit code.** `opencode auth list` exits `0` whether or
  not anything is authenticated; logged out it prints `No authenticated integrations`. So unlike
  Codex's, the check is "not logged out" rather than "logged in", keyed on that one phrase, with
  empty output also counting as logged out. The asymmetry is the same as Codex's: a false "logged
  out" blocks an install in front of a human, a false "logged in" lets every unattended session fail
  silently.
- **OpenCode's config document may be `opencode.json` OR `opencode.jsonc`, and the name is
  resolved rather than assumed.** The CLI writes to whichever is already there: probed against
  2.0.14, with only a `.jsonc` present `opencode mcp add --global` appended to **that** file
  (comments and trailing comma preserved); with both present it chose `.json`; with neither it
  created `.json`. Assuming `.json` meant that on a `.jsonc` machine the Code Mode patch was
  silently skipped, the post-install checklist reported a correct install as broken, and the
  uninstall left the registration behind.
- **Its config is JSONC even when it is called `.json`.** OpenCode accepts comments and trailing
  commas in a plain `opencode.json`, so `json.loads` would report a perfectly valid config as
  unreadable and have the installer skip the permission rules. Reading goes through the adapter's
  own parser, which is a string-aware scanner rather than a regex — a URL contains `//` and a
  string value can contain `, }`, and a naive pass corrupts both.

  **The installer never writes a document the operator owns.** Everything this install asserts
  goes into `<workspace>/.opencode/opencode.json`, so there is no case where it has to choose
  between deleting somebody's comments and skipping a security rule. The only thing that touches
  the operator's config is `opencode mcp add` itself, which is comment-preserving because the CLI
  wrote it.

  **The workspace is Tubematic's own directory** — `~/.tubematic-agent/<agent>` by default,
  created by the installer — so this document is Tubematic's outright: written on install, removed
  on uninstall, with no ownership test. The one case worth refusing is a workspace that is
  *already* somebody's OpenCode project, and that is caught at the workspace **question**, beside
  the existing rule that each agent needs a directory of its own. Asking there rather than deeper
  in matters: it runs before anything is copied or registered, on every path that asks the
  question, and needs no gate of its own to be kept in sync.

  Two things that rule has to get right, both of which it got wrong first:

  - **Only a LIVE agents row makes a workspace ours.** An archived row means the agent was
    uninstalled: its config was deleted and its workspace deliberately kept, so a document at that
    path now is the operator's. Counting archived rows let a re-install exempt and rewrite it, and
    a full uninstall delete it as Tubematic's.
  - **Tubematic's own documents are exempt — those files, not the directory.** Without the
    exemption the rule eats itself: a successful install creates exactly the file it rejects, so a
    re-install is refused, `current_values` falls back to the default path, and `upgrade.py` then
    deploys somewhere the `agents` row does not point at. The row is the authority on which
    directory is already ours; the file is not. Exempting the whole *directory* is equally wrong —
    a sibling dropped in afterwards then survives a re-install and an upgrade, still outranking
    the denies while the install reports success.
  - **A foreign document never relocates the agent.** It is fixed by removing that file, so the
    pre-fill keeps the recorded workspace and the question says what to remove. Falling back to
    the default would move the agent silently, and `upgrade.py` takes those values without asking
    anything — leaving the scheduled runs on the old directory.
  - **Tubematic writes every basename OpenCode loads, and that is the defence.**
    `.opencode/opencode.jsonc` is loaded *after* `.opencode/opencode.json`, so one rule in
    whichever file Tubematic did not write outranks every rule in the one it did. Measured: an
    operator `.jsonc` beside our `.json` turned a credential deny back into an allow and the agent
    read the file.

    Both are written, with identical content, so there is no slot left to outrank us. Probed with
    five other plausible names in the same directory (`opencode.json5`, `config.json`,
    `opencode.jsonc.local`, `settings.json`, `opencode.yaml`), each carrying an `allow`: none was
    loaded, the effective rules stayed `deny, deny`, and the run was blocked.

    The alternative — scanning for a foreign sibling — has to be repeated at every entrance that
    deploys or runs the agent, and was missed at two of them (`upgrade.py`, which deploys without
    asking any questions, and `poll.py`, which invokes the agent unattended on every pass).
    Occupying the names needs no check anywhere. What the checklist verifies instead is that the
    documents are all still **there**: a missing one reopens the slot.

  **`.opencode/opencode.json` rather than the workspace's direct `opencode.json`, and that is a
  correctness requirement.** Measured against 2.0.15, documents merge in this order, lowest first,
  and `permissions` arrays are **concatenated** — so only the last document is guaranteed to win:

  | | document |
  |---|---|
  | lowest | `~/.config/opencode/opencode.json(c)` |
  | | `<ancestor>/opencode.json(c)` |
  | | `<workspace>/opencode.json(c)` |
  | | `<ancestor>/.opencode/opencode.json(c)` |
  | **highest** | `<workspace>/.opencode/opencode.json(c)` |

  A deny in the workspace's *direct* file was overridden by a developer's own
  `~/.opencode/opencode.json` and the credential file was read; the same deny in the managed
  document blocked it against a user `allow` in each of the four other locations.

  **The managed document carries the COMPLETE server entry** — type, url, the token header and the
  options — not just the options. An entry
  carrying only `codemode` merges far enough for the server to connect — `opencode mcp list`
  reports it `connected`, because the `url` comes from the other document — but the option does
  not apply and Code Mode stays on. The post-install checklist has a **separate** item for the
  options, because "registered" and "usable" answer different questions: whether an interactive
  session outside the workspace can reach the server, and whether a scheduled run inside it sees
  the tools natively.
- **The permission rules are re-asserted at the END of the list, not merely appended if missing.**
  Permissions resolve **last match wins**, so a managed rule already in the file followed by a
  later contradicting one leaves the later one in force — while a membership test still reports
  the rule as present. Measured, not theorised: a `read *.env deny` followed by a `read *.env
  allow` read the credential file. The installer therefore moves its own rules to the end in order,
  leaving every unrelated rule the operator wrote exactly where it was, and the checklist asserts
  the same shape rather than mere membership.
- **`opencode mcp list` is not a reliable check.** For several seconds after any config change or
  service restart it reports `No MCP servers configured`, then starts reporting
  `✓ tubematic  connected` — OpenCode answers from a background service that reloads on its own
  schedule. The post-install checklist therefore reads the config document instead, which is
  deterministic. If you run it by hand, run `opencode reload`, wait, and run it twice before
  concluding anything.
- **OpenCode has no `opencode mcp remove`.** Its `mcp` subcommands are `list`, `add`, `auth` and
  `logout`. Deregistration is an edit that removes only `mcp.servers.tubematic` from the config
  document; the adapter returns `None` from `mcp_remove_argv` rather than an argv that does not
  exist, which is what stops an uninstall reporting success for a command it never ran.

  That edit is made **on the text, not by reserialising**, so the operator's comments survive —
  and **it is verified before it is written**: the edited document must still parse and must equal
  the original data with exactly that one key removed. Anything else leaves the file untouched and
  reports the change instead. That is what makes surgery on a human-authored file acceptable; it
  can only ever produce a proven-correct result or no change at all. A document that will not
  parse at all is still *reported*, by looking for the name in the raw text — answering "not
  registered" there would skip the whole agent in silence, on exactly the file a human most needs
  told about.

### Deployment

Skills and commands are **markdown, not code**. Editing this repository changes nothing for a
running agent until they are deployed, and deploying is part of installing the agent:

```bash
python onboard.py --install-agent claude
python onboard.py --install-agent codex
python onboard.py --install-agent opencode
```

The main `onboard.py` flow sets up the project only. The walkthrough — preconditions, questions,
flags — is in [Installing](../user-guide/02-installing.md#install-an-agent); this section covers what
lands where.

| Agent | Scope | Skills | Commands | MCP registration |
|---|---|---|---|---|
| Claude Code | `user` (default) | `~/.claude/skills/` **and** the agent workspace | `~/.claude/commands/` | `--scope user` |
| Claude Code | `project` | The agent workspace only | The agent workspace only | Local scope |
| Codex | `user` (only) | `~/.codex/skills/` | — | global |
| OpenCode | `user` | `~/.config/opencode/skills/` | `~/.config/opencode/commands/` | `--global` |
| OpenCode | `project` | The agent workspace's `.opencode/` | The agent workspace's `.opencode/` | The workspace's `opencode.json` |

For Claude Code, user scope deploys to **both** locations: the home directory so every session sees
the skills, and the workspace because cron runs the agent from there. Missing one means only half
the pipeline sees your change. Codex needs no second copy — `~/.codex/skills/` is found from any
working directory, and neither does OpenCode — `~/.config/opencode/skills/` is likewise found from
anywhere. Remotion's skills are installed from `remotion-dev/skills` in the same pass, with the
agent flag the adapter declares. Note that the agents receive them in different places: Claude
Code's land in its own skills directory, while Codex's and OpenCode's land in `~/.agents/skills/`,
a user-scope root both of those read alongside their own. All are discovered; only Tubematic's own
skills are copied by Tubematic.

For **Claude Code only**, the installer also writes two things that are easy to overlook:

- A **tool allowlist** in `<workspace>/.claude/settings.json` — `mcp__tubematic`, `WebFetch`,
  `WebSearch`, `Read`, `Glob`, `Grep` — with a **deny** on reading the data directory:
  `Read(//<home>/.tubematic-data/**)` and `Read(~/.tubematic-data/**)`
  (`onboard/actions.py::claude_read_denies`).
- A **trust record** in `~/.claude.json` marking the workspace as accepted.

Both are needed. An allowlist alone is silently ignored until the project is also marked trusted,
which is what makes unattended cron runs work without `--dangerously-skip-permissions` — a flag this
project rejects. Codex has neither file, because its equivalent is `-s read-only` on argv.

**Why the data directory is denied.** It holds the database, which stores every API key, and
`secrets/`, which holds the service tokens and the dashboard password's hash. The agent reads text
from the open internet (research pages, the transcripts behind a
[script profile](08-scripting-and-voice.md#the-profile-schema)), so it is never trusted with them.
Three details:

- **The path forms are Claude Code's own.** `//path` is absolute and `~/path` is from home. A
  single leading slash is *not* absolute — it anchors at the settings file's project — so
  `Read(/home/...)` would deny nothing. A `Read` rule also covers `Grep` and `Glob`, and a deny
  wins over the unscoped `Read` allow whatever the order.
- **Nothing the agent needs is there.** The poll logs the prompts point at live under
  `~/.tubematic-agent/logs`, and every pipeline file is reached through an MCP tool.
- **The MCP token still reaches the CLI.** Claude Code's `headersHelper` is a separate process that
  reads the token file itself, not a `Read` tool call, so the deny does not apply to it.

For **OpenCode**, the equivalent is an ordered permission list written into the workspace's
managed `.opencode/opencode.json(c)` — at **both** scopes, like Claude's allowlist, because cron runs the
agent from the workspace and because a user-scope install has no business reaching into the
operator's own global OpenCode configuration to restrict it. The rules have **two halves**, and both matter:

- **Allow** `tubematic_*` (the MCP tools), `webfetch`, `websearch`, `read`, `grep` and `glob`.
- **Deny** `edit`, `write` and `shell`, and reads of `*.env` and `*.env.*` — then allow
  `*.env.example` and `external_directory` for the poll-log directory — and, **last of all**, deny
  both `external_directory` and `read` on `<home>/.tubematic-data/**`, the data directory
  (`onboard/actions.py::managed_permission_rules`). Two rules, because OpenCode checks `grep` and
  `glob` against the search *pattern*, not a path, so a read deny alone cannot keep them out;
  reaching outside the workspace is the separate `external_directory` permission. The MCP token
  still reaches OpenCode, because `{file:…}` is resolved when the config loads, not through a tool.

**The allow half is not decoration, and deny-only was a real hole.** Permissions resolve
last-match-wins across every *merged* document, so an action this list says nothing about is
decided by whatever the operator's own config says. Measured: a global `deny webfetch` /
`deny websearch` were the only matching rules and won — and the topic-research skill tells the
agent to use exactly those tools — while a global `deny tubematic_*` blocked the MCP tools
outright, which would have left the pipeline doing nothing in every session while looking healthy.
Because Tubematic's document is the highest-precedence one, asserting the positives there is what
makes them survive a hostile or merely opinionated global config. Verified against one denying all
four: `MCP=ok, WEB=ok, ENV=blocked, SHELL=blocked`.

The denies come **after** the allows, so they win the overlap. Two further things are load-bearing:

- **`shell` is denied, not left alone.** Claude's allowlist grants no Bash and Codex runs under a
  read-only sandbox, but nothing constrains a command OpenCode runs, so allowing it would make
  OpenCode the most permissive of the three. Setting it to `ask` instead would not restrict
  anything, because `--auto` approves an `ask`.
- **The `.env` rules are denials for the same reason.** OpenCode's own default for a credential
  file is `ask`, and `--auto` would approve it.
- **The data-directory denies are last of all**, after the broad `read` allow, so they win it.

**Codex has no equivalent of the data-directory deny.** Its `-s read-only` sandbox stops writes
but lets the agent read any file the user can, `~/.tubematic-data` included, and the sandbox mode
carries no per-path read rule, so Tubematic adds none. That is a known gap: on a Codex install,
the profile schema and the skills' data-not-instructions rule are the only defences between
injected text and the stored keys.

Denied tools are removed from the catalogue the model sees, rather than merely refused, so this
also stops the agent spending turns looking for a tool it cannot have.

> **An OpenCode install wants a real provider**, but that is a judgement rather than a measured
> constraint: the free models are far too weak to drive this pipeline. Log in with
> `opencode auth login`.
>
> One observation worth recording, because it changed between releases. On **2.0.14**, denying
> `shell` made the free tier refuse to run at all —
> `Error from provider (Console): OpenCode's free tier can only be used from within OpenCode` —
> and that was isolated carefully: only `shell` + `deny` tripped it, in either config scope, while
> denying edit, write or `.env` reads was fine. On **2.0.15** the same install runs normally with
> `shell` denied. So do not rely on it in either direction; if a run ever fails with that message,
> the shell rule is the first thing to look at.

Last, it writes the agent's row. **The row goes straight into SQLite, not over HTTP.** The API
refuses model-list writes on purpose — no container has the agent binary to validate a model
against — and on a fresh install Flask may not be running yet. The same write deletes the
`agent_binary`, `agent_run_path` and `install_scope` settings rows the row replaces.

**Re-running it is the update path and the redeploy path.** Every question is pre-filled from the
agent's row. Each skill directory this repository ships is replaced wholesale; skills that did not
come from here are left alone. After editing a skill, re-run it.

**A skill this repository stopped shipping is removed by the redeploy.** Copying only ever adds, so
without that step an upgraded install would keep a skill teaching the agent a tool the server no
longer has. The names live in `onboard/agent_install.py::RETIRED_SKILLS`, with a copy in
`uninstall.py` (which runs standalone); a test pins that the two agree. When you delete a skill
directory, add its name there. Only those exact names are removed, from the same skills directories
the deploy writes to.

**Skills load at session start.** After deploying, restart the agent session. After registering the
MCP server, restart it again — tool schemas are read once.

### Models

Each agent stores a list of models, and the first is its default. The list is what the dashboard
offers at the topic checkpoint and what the API accepts for `videos.agent_model` — nothing else.

**Every model is probed against the installed CLI before it is stored**, by running that agent's
own one-word prompt with the model set. For Claude and OpenCode an unknown model fails locally with
no API call; for Codex it is rejected by the API. Either way a valid one makes one tiny real call. There is no hardcoded catalog to check against instead, because model names change
faster than this repository does and a list here would start rejecting valid models.

**Rejection is read from the output, never the exit code**, and each adapter owns its own markers.
The Claude CLI exits `0` on a model it does not recognise, printing an `unrecognized_model` marker
and "may not exist or you may not have access to it". Codex exits non-zero, but **its wording
depends on how it is authenticated** and both forms have to be matched: a ChatGPT account says "is
not supported when using Codex", while an API key returns a 404 saying the model "does not exist or
you do not have access to it". Matching only the first would leave an API-key install with no
fallback at all — every scheduled session would burn a run that does nothing. A non-zero exit *without* a
marker is some other failure, so the model is kept with a warning rather than judged.

OpenCode is the straightforward one: `Error: Model unavailable: <slug>` on stderr with a non-zero
exit, resolved against its catalog before any API call. The exit check still matters, because the
phrase is ordinary English that a *successful* session could quote out of a log.

The matchers are deliberately narrow. Codex, for instance, also prints a *warning* that a model's
metadata was not found — for models the API then accepts. Treating that as a rejection would make
the poller drop `--model` on healthy runs, silently, in every session.

The prompt's autocomplete offers what that agent's `suggest_models` finds: for Claude the aliases
`opus`, `sonnet`, `fable` and `haiku` plus the IDs in the installed binary's own catalog, and for
Codex the slugs in the CLI's catalog cache. OpenCode's come from `opencode models`, which works
logged out (it lists the free models), so the prompt has something to offer before the login is
even checked. Neither Codex nor OpenCode has aliases, so both offer slugs only. Those are
suggestions in every case: each reads an implementation detail that can change in any release, so a
failure yields no suggestions and free text is always accepted.

**Alias or full ID is a real tradeoff.** An alias always means the current model of that family —
the stored name never changes but the model behind it does, so you cannot later tell which model
made a video. A full ID is reproducible but will eventually be retired.

Validation is point-in-time. On a re-run, pressing Enter at the model prompt keeps the stored list
but re-checks every entry, so a model the CLI has since retired is dropped instead of carried
forward. For a model that disappears between installs, the poller's rejected-model fallback is the
safety net — see [The Poller](13-the-poller.md#running-one-agent-process).

With `--disable-verification` nothing is probed, and the row's `verified_at` stays blank so the
dashboard does not imply a check that never ran.

### Effort

Alongside the model, each agent stores an **effort level** — `low`, `medium`, `high`, `xhigh` or
`max` — passed to Claude Code as `--effort <level>`, to Codex as
`-c model_reasoning_effort=<level>`, and to OpenCode as a `#variant` suffix on the model itself
(`--model anthropic/claude-sonnet-4-5#high`). It is how hard the agent thinks on a run: higher levels
cost more and take longer. The default is `high`, because a pipeline run writes scripts and scene
code a human then has to review.

**It behaves like the model in every way that matters, and differs in one.** Like the model, it is
an install-wide default overridable per video (`videos.agent_effort`), settable only at a human
checkpoint, and offered wherever the model is offered. Unlike the model, the five levels are a
**closed set fixed by the CLI**, not a list discovered per install — so there is nothing to probe
per value and nothing to reorder, and any of the five can be *stored* for any agent. That is why
the effort picker stays usable on a page that has not loaded the agent list, and why a video with no
installed agent can still record one.

Storable is not the same as usable, though: a particular **model** may refuse a level that the set
allows (Codex's `gpt-5.5` stops at `xhigh`). Nothing rejects that at the picker, deliberately — the
picker cannot know which model a video will end up running. It is caught where the model is known
instead: at install time against the default model, and at run time by the fallback below.

The five levels are shared by every agent. Codex's API additionally accepts `none`, `minimal` and
`ultra`, and OpenCode's are per-model variant names rather than a fixed set at all; neither is
offered separately, because the set is duplicated into the Flask API, the MCP server and the
dashboard and pinned by a cross-copy test, so a per-agent set would push validation changes through
all three for levels nobody asked for.

**OpenCode's effort rides on the model string, which has one visible consequence**: it cannot be
sent without a model. A run with no model carries no effort, which is also what keeps the runtime
fallback below finite for OpenCode — dropping the model necessarily drops the effort, so there is
no third round to reach.

**Not every Codex model supports every one of the five, though**, so a level that is valid in
general can still be wrong for a particular model — `gpt-5.5`, for instance, stops at `xhigh` and
rejects `max`. That is an ordinary configuration, not a typo, so it is handled twice: the install
probes the chosen level against the **default model** and warns, and the poller falls back at
runtime for any pair it was not able to check (a per-video override, say). See
[The Poller](13-the-poller.md#running-one-agent-process).

**It is not asked during a minimal install.** The question carries the `advanced` attribute, so
`python onboard.py --install-agent <agent>` seeds `high` silently and only
`--full-questionnaire` asks. It is editable afterwards on **Settings → Agents**, and per video at
the topic checkpoint, so nothing is lost by not asking. Note that `--install-agent` builds its own
question list rather than going through the main wizard's, so it honours `advanced` by filtering
that list itself.

**The effort is probed at install time, against the default model**, and the runtime fallback in
[The Poller](13-the-poller.md#running-one-agent-process) is the backstop for anything the probe could not see — a per-video
override, or a model the install never tried. The two agents fail differently, which is why the
probe needs the model: Claude rejects the `--effort` flag itself regardless of model, while Codex
and OpenCode accept it always and reject the model/effort *pair*. OpenCode says so precisely —
`Error: Variant unavailable for <model>: <variant>` — which is worth real money, because it means
an unusable level costs one retry with the chosen model **kept**, rather than the model being
thrown away too.

**Blank means "follow the agent", and stays blank unless a human says otherwise.** A video's
`agent_effort` is `''` until someone picks a level, and the dashboard's picker offers blank as a
real option rather than resolving it — see [Dashboard](15-dashboard.md) for why guessing it is
worse than leaving it. `get_pipeline_status`'s `agents` entries carry each agent's `effort` so a
skill can name the level a blank choice will produce.

**It is deliberately not a settings key.** The install-wide `agent_model` key was removed on
purpose when agents became rows; per-agent defaults live on the agent, and effort follows the same
rule — see [Settings](../user-guide/05-settings.md).

### Assignment

A video gets its agent when it is created — at all three creation sites, `POST /videos`,
`POST /videos/manual` (the dashboard's New Video page, unless a picked agent is sent), and the MCP
server's `create_video`, which mining files through. `_pick_agent_id` deals
it from a **shuffled deck**: every live agent whose `weight` is above 0 gets `weight ÷ gcd` cards
(so 30:10 deals like 3:1), the deck is shuffled, and each new video takes the next card. When the
deck runs out a fresh one is shuffled. If every live weight is 0 it picks the default agent (else
the oldest) and leaves the deck alone; a weight of 0 means "deal me no cards", not "never run
anything". With no agent installed it stores `NULL`, which means "the default agent at dispatch
time".

**Why a deck rather than an independent weighted draw.** A draw per video only matches the weights
on average — at 3:1, four videos split exactly 3:1 less than half the time, and a quarter-weight
agent gets none of them about a third of the time. A deck makes every full cycle exact while keeping
the order within a cycle random. Round-robin would also be exact but fully predictable.

The deck is one row in `agent_deck`, because the Flask API and the MCP server both create videos. It
records the `[id, reduced weight]` list it was built from; when that no longer matches the live
agents — a weight changed, or an agent was installed or uninstalled — the next deal shuffles a new
deck, so a change applies from the very next video. The deal runs inside the video's own insert
transaction and starts with a write, which takes SQLite's write lock before the deck is read: two
processes can never deal the same card, and an insert that fails returns its card.

**Why assign at creation rather than run a percentage schedule in the poller.** A scheduler needs
a counter, a rolling window and a tie-break rule, and it would have to agree with the poller's
session slots about who runs next. Dealing at creation gives the split up front, is auditable per
video, and leaves the poller with no scheduler at all.

**A human may change a video's agent at any checkpoint**. At `TOPIC_PROPOSED`,
`SCRIPT_READY` and `VIDEO_READY` the dashboard offers every live agent next to the model and effort
pickers, and the pick travels with the Approve or Request Revision that hands the video its next
piece of work: the script, the scenes, or a revision. `update_video(agent_id=…)` does the same over
MCP. The rules, identical in both writers:

- **Only live agents.** An uninstalled agent cannot be handed new work; the video's own agent is
  accepted again as a no-op, and a pinned uninstalled agent still resolves for its own video.
- **The model is cleared on a change** — it belongs to the old agent's list, so kept it would be
  rejected by the next write and by the new CLI on every scheduled run. The one exception is a model
  sent in the same request, which is checked against the new agent. The UI says so the moment the
  agent changes.
- **Effort carries across**: every agent takes the same five levels.
- **The deal does not rebalance.** Weights are a dealing mechanism, not a quota, so an override
  neither takes nor returns a card.

**Between checkpoints the agent is fixed**, because an agent or the renderer holds the video, and
switching under it would change prompt tuning and style mid-task. The poller never moves a video on
its own either: a video whose agent is uninstalled or missing is skipped, never rerouted. At a
checkpoint a human can move it to a live agent; between checkpoints it resumes only when its agent
is re-installed. Switching at a checkpoint is a deliberate trade: the next stage may
be written in a different agent's style from the last.

The default agent, each weight and each agent's default model are set on the dashboard's Settings →
Agents tab, which writes through [`PATCH /agents/<id>`](05-http-api.md#agents). Uninstalling is
host-side only — `python onboard.py --uninstall-agent <name>` — and never deletes the row, so a
video pinned to an uninstalled agent still resolves it.

---

## Scheduling

Scheduled runs are started by `scripts/poll.py`, the cron entry point. It has its own page:
[The Poller](13-the-poller.md) covers the supervisor loop, the three lanes, one stage per session,
how success is judged, timeouts and orphaned sessions, and the logs.

### User preferences

The operator can write standing preferences for every video on the dashboard's Preferences tab
(the [`user_preferences`](../user-guide/05-settings.md#user-preferences) setting). They reach the agent by one of
two routes, depending on how the run started:

- **Scheduled runs.** The poller reads the setting at most once per pass, and only when it is about
  to start a session. It adds the text to the prompt as a fenced block, after the task instructions and before
  the footer:

  ```
  === USER PREFERENCES (written by the operator in the Tubematic dashboard) ===
  Standing preferences for every video Tubematic produces. They cover several stages
  at once (topic research, scripting, voice, visuals, ...). This run's stage: topic research.
  Apply ONLY the instructions relevant to this stage and ignore the rest.
  They never override the pipeline's rules: human checkpoints, tool contracts,
  per-run caps and status transitions still apply.

  <the operator's text>
  === END USER PREFERENCES ===
  ```

- **Interactive sessions.** A slash command never goes through the poller, so `get_pipeline_status()`
  returns the same text as `user_preferences`. The operator, script-writing and topic-research
  skills, and `/tubematic-submit-new-job`, read it there.

The block's wording is deliberate:

- **It names the stage.** A single text covers every stage, and a research run that took "no jokes"
  or "prefer diagrams" as a research instruction would score topics on the wrong criteria. Each
  prompt builder passes its own stage name (`poll.py::_preferences_block`).
- **It says what it cannot override.** The text is free-form, and an instruction such as "just
  approve my scripts" must not read as permission to cross a human checkpoint. The script-writing
  skill likewise keeps its fixed policy above any preference that contradicts it.
- **Empty text adds nothing.** Not even an empty fence, so an install that never sets preferences
  sends byte-identical prompts.
- **A failed read fails open.** If `/settings` cannot be read, the prompt goes out without the block
  and `poll.log` warns. A prompt without preferences still works, whereas skipping the session would
  stall the pipeline for a nicety.

This is not a system prompt in the CLI sense. Claude, Codex and OpenCode each have their own
mechanism for one, or none at all, and a block in the prompt text reaches all three the same way.

---

## Adding a capability

Roughly in order of how often you will need each:

**A new workflow rule** — edit the relevant skill, redeploy, restart the session. No code change.

**A new slash command** — add a markdown file to `agent_files/<agent>/commands/` for **every**
agent that has commands, not just the one you are using; a test pins that the sets match. Redeploy
afterwards. Remember the uninstaller has a hardcoded skill list that will not know about a new
skill. Codex has no command mechanism, so it gets none.

**A new MCP tool** — add an `@mcp.tool` function in `mcp/server.py`. Then:

1. Decide whether it needs the scene-work claim. Guard it if it *spends money or writes a file*;
   leave it exempt if it only reads. Read tools being exempt is deliberate, not an oversight.
2. Write the docstring as a technical contract — parameters, returns, failure modes. That docstring
   *is* the agent's documentation.
3. Teach a skill when to call it. A tool no skill mentions will rarely be used.
4. Add tests in `mcp/tests/`.
5. Note that **existing agent sessions will not see it** until they reconnect.

**A new sourcing strategy** — extend the topic-research skill, add the value to the strategy
validation in the API and MCP server, and add it to the dashboard's mode toggles.

**A new agent** — only one that meets the precondition in [Agents](#agents). Add an adapter class
to `scripts/agent_adapters.py` and register it in `ADAPTERS`. One class is close to the whole job:
besides invocation, the login check and model probing, the class declares its own deployment layout
(`SUPPORTED_SCOPES`, `NEEDS_ALLOWLIST`, `NEEDS_PERMISSION_CONFIG`, `COPIES_SKILLS_INTO_WORKSPACE`,
`HAS_COMMANDS`, `CONFIG_HOME_ENV`, the directory functions and the MCP argv functions), and
`onboard/agent_install.py::deploy`, `deployed_paths`, the install questionnaire, the post-install
checklist and `uninstall.py`'s sweep all read those rather than naming any agent. `upgrade.py` then
works without further change.

What one class does *not* cover is a genuinely new permission mechanism. Claude's allowlist and
OpenCode's rule list are each written by their own function in `onboard/actions.py`, selected by a
flag on the adapter; a fourth agent with a third mechanism needs a third writer. That is deliberate
— the three are not variations of one shape — but it is the one place a new agent touches code
outside its own class.

If the agent has slash commands, add `agent_files/<name>/commands/` with the same filenames the
other agents ship, adapting only the lines that name a CLI.

Keep the class free of filesystem access. Writes belong in `onboard/`, behind the executor that
makes `--dry-run` truthful, and `scripts/poll.py` imports this module on every cron tick.
