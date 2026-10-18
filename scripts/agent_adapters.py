"""Per-agent CLI knowledge: how to invoke an agent and how to read its output.

One class per supported agent, keyed in ADAPTERS by the agent's id (the id
`python onboard.py --install-agent <id>` takes, and the `agents.id` row it
writes). poll.py uses an adapter to build argv and judge a finished run;
onboarding uses it to verify login and probe models at install time. Both run
on the host from the same checkout, so this is the single home for it rather
than two hand-synced copies.

Claude Code, Codex and OpenCode are supported. Any agent added here must speak
MCP over streamable-http and read SKILL.md-format skills — every pipeline action
goes through the tubematic MCP server, and the skills are the pipeline's
behaviour, not configuration.

Each class also declares where its files are deployed and what its MCP
registration argv is, which is what keeps onboard/ free of any one agent's
directory names. That half is data and pure functions only: every filesystem
write stays in onboard/, behind the Executor that makes --dry-run honest, and
poll.py imports this module directly so it must stay dependency-light.
"""
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class McpAuth:
    """How an agent CLI authenticates to the MCP server (TMDEV-152).

    Neither field is the token itself, and that is the point: every CLI is
    pointed at the token FILE, so the secret never sits in an agent's config,
    an argv or a dry-run listing, and rotating it needs no re-registration.
    """
    helper: str       # shell command printing {"Authorization": "Bearer <mcp_token>"}
    token_file: str   # absolute path of the mcp_token file

# Every supported agent offers the same five levels. Codex additionally accepts
# `none`, `minimal` and `ultra`, and OpenCode's levels are per-model variant
# names rather than a fixed set; neither is offered separately, because this
# tuple is hand-duplicated into renderer/api/pipeline.py, mcp/server.py and
# dashboard/lib/agents.ts and pinned by a cross-copy test, so a per-agent set
# would push validation changes through the Flask API, the MCP server and the
# dashboard.
#
# NOTE: offering all five to every agent does NOT mean every agent's every
# model accepts all five — gpt-5.5 stops at xhigh and rejects max. That is an
# ordinary configuration, so it is caught twice: the install probes the level
# against the default model, and the poller drops the flag and retries at
# runtime. See CodexAdapter.EFFORT_UNSUPPORTED_MARKERS, and
# OpenCodeAdapter's, where the same thing is a missing model *variant*.
AGENT_EFFORTS = ("low", "medium", "high", "xhigh", "max")

# ── JSONC ───────────────────────────────────────────────────────────────────
# OpenCode's config documents are JSON *or* JSONC, and it accepts comments and
# trailing commas inside a plain `opencode.json` as readily as inside a
# `.jsonc` — verified against 2.0.14 with `opencode debug config`. So a config
# a human has annotated is perfectly valid to OpenCode and fatal to
# `json.loads`, which would have the installer skip the permission rules and
# the Code Mode patch on a machine whose config was merely commented.
#
# These live here because this module is the one thing both `onboard/` and
# `uninstall.py` already load, and because the dialect is a property of the
# agent rather than of either caller. Pure functions, no I/O, as the rest of
# the module is.


def _scan_jsonc(text: str, *, drop_comments: bool, drop_trailing_commas: bool) -> str:
    """One string-aware pass over a JSONC document.

    String-aware is the whole point: a regex over the raw text corrupts any
    document whose *data* contains `//`, `/*` or `, }` — a URL, a glob, a
    prose value. Both transformations share this scanner so neither can be
    written the naive way by accident.
    """
    out = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:      # an escape consumes the next char,
                out.append(text[i + 1])       # so an escaped quote cannot end
                i += 2                        # the string
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if drop_comments and c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if drop_comments and c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if drop_trailing_commas and c == ",":
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            if j < n and text[j] in "}]":
                i += 1                        # a comma before a closer is JSONC
                continue                      # syntax, not data — drop it
        out.append(c)
        i += 1
    return "".join(out)


def parse_jsonc(text: str):
    """`json.loads` over a document that may carry comments or trailing commas.

    TWO passes, and the order is the whole point: a comma's "is the next thing
    a closer?" lookahead has to run over text the comments are already gone
    from. Doing both in one pass means the lookahead lands on the comment that
    has not been removed yet, keeps the comma, and then removes the comment —
    leaving a genuine trailing comma behind. `{"a": 1, // c\n}`,
    `{"a": 1, /* c */ }` and `{"a": [1, 2, // c\n]}` are all valid JSONC and
    all raised JSONDecodeError that way.
    """
    plain = _scan_jsonc(text, drop_comments=True, drop_trailing_commas=False)
    plain = _scan_jsonc(plain, drop_comments=False, drop_trailing_commas=True)
    return json.loads(plain)


def jsonc_has_comments(text: str) -> bool:
    """Whether the document carries comments, as opposed to merely trailing commas.

    The distinction decides whether we may rewrite the file. Comments are the
    author's, and reserialising through `json.dumps` would delete them
    silently; a trailing comma is syntax nobody will miss. So a commented
    document is reported and left alone, and a merely trailing-comma one is
    normalised.
    """
    return _scan_jsonc(text, drop_comments=True, drop_trailing_commas=False) != text


DEFAULT_AGENT_EFFORT = "high"



def _jsonc_skip_ws(text: str, i: int) -> int:
    """Past whitespace and comments, from `i`."""
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        break
    return i


def _jsonc_read_string(text: str, i: int) -> tuple:
    """(value, index past the closing quote) for the string starting at `i`."""
    if text[i] != '"':
        raise ValueError("expected a string")
    start = i
    i += 1
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return json.loads(text[start:i + 1]), i + 1
        i += 1
    raise ValueError("unterminated string")


def _jsonc_skip_value(text: str, i: int) -> int:
    """The index just past the value starting at `i`."""
    i = _jsonc_skip_ws(text, i)
    if i >= len(text):
        raise ValueError("expected a value")
    c = text[i]
    if c == '"':
        return _jsonc_read_string(text, i)[1]
    if c in "{[":
        closer = "}" if c == "{" else "]"
        i += 1
        while True:
            i = _jsonc_skip_ws(text, i)
            if i >= len(text):
                raise ValueError("unterminated container")
            if text[i] == closer:
                return i + 1
            if text[i] == ",":
                i += 1
                continue
            if c == "{":
                _, i = _jsonc_read_string(text, i)
                i = _jsonc_skip_ws(text, i)
                if text[i] != ":":
                    raise ValueError("expected ':'")
                i += 1
            i = _jsonc_skip_value(text, i)
    n = len(text)
    while i < n and text[i] not in ",}]" and not text[i].isspace():
        i += 1
    return i


def _jsonc_member_span(text: str, i: int, key: str) -> tuple:
    """(key_start, value_start, value_end) of `key` in the object at `i`."""
    i = _jsonc_skip_ws(text, i)
    if text[i] != "{":
        raise ValueError("expected an object")
    i += 1
    while True:
        i = _jsonc_skip_ws(text, i)
        if i >= len(text):
            raise ValueError("unterminated object")
        if text[i] == "}":
            return None
        if text[i] == ",":
            i += 1
            continue
        key_start = i
        name, i = _jsonc_read_string(text, i)
        i = _jsonc_skip_ws(text, i)
        if text[i] != ":":
            raise ValueError("expected ':'")
        value_start = _jsonc_skip_ws(text, i + 1)
        end = _jsonc_skip_value(text, i + 1)
        if name == key:
            return key_start, value_start, end
        i = end


def remove_jsonc_member(text: str, path: list):
    """`text` with the member at `path` removed, or None if that is not safe.

    A targeted text edit rather than a reserialise, because reserialising a
    JSONC document through `json.dumps` deletes the author's comments — and
    refusing to edit at all is what left an uninstalled agent's MCP server
    registered.

    **Every result is verified before it is returned**: the edited text must
    still parse, and must equal the original data with exactly that one key
    removed. Anything else — a shape this scanner mis-reads, an unbalanced
    document, a key that is not there — returns None and the caller reports the
    edit instead of performing it. That is what makes surgery on a
    human-authored file acceptable: it can only ever produce a proven-correct
    result or no change at all.
    """
    try:
        before = parse_jsonc(text)
    except Exception:
        return None
    node = before
    for key in path[:-1]:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if not isinstance(node, dict) or path[-1] not in node:
        return None

    try:
        i = _jsonc_skip_ws(text, 0)
        for key in path[:-1]:
            span = _jsonc_member_span(text, i, key)
            if span is None:
                return None
            i = span[1]                      # descend into that member's value
        span = _jsonc_member_span(text, i, path[-1])
    except (ValueError, IndexError):
        return None
    if span is None:
        return None
    start, _, end = span

    # Swallow one adjacent comma so the document stays well-formed. Prefer the
    # following one; fall back to the preceding one when this was the last
    # member. A comment that sat beside the removed member is left where it is
    # — it is the author's text, and a stray comment is still valid JSONC.
    after = _jsonc_skip_ws(text, end)
    if after < len(text) and text[after] == ",":
        end = after + 1
    else:
        head = text[:start].rstrip()
        if head.endswith(","):
            start -= len(text[:start]) - len(head) + 1

    edited = text[:start] + text[end:]

    expected = json.loads(json.dumps(before))
    node = expected
    for key in path[:-1]:
        node = node[key]
    node.pop(path[-1], None)
    try:
        if parse_jsonc(edited) != expected:
            return None
    except Exception:
        return None
    return edited

# ── Usage (TMDEV-107) ───────────────────────────────────────────────────────
# Every adapter runs its CLI in a machine-readable output mode so poll.py can
# record what each session used. parse_usage turns one run's stdout into usage
# events: {service, model, units, raw, reported_cost_usd, estimated}. Units use
# tubematic_core.prices' kinds (input, output, reasoning, cache_read, ...).
#
# The JSON modes move the CLIs' own error messages onto STDOUT (probed live,
# Codex and OpenCode both), which is why the effort matchers accept stdout —
# but only the CLI's *error events* in it, never the agent's own text, so a
# session that merely discusses a flag still cannot strip it.

def _json_lines(stdout: str) -> list:
    """Every JSON object in a JSONL stream; non-JSON lines are skipped."""
    out = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _json_error_messages(stdout: str) -> str:
    """The text of a JSONL stream's error events — the CLI's own errors, not the agent's words."""
    msgs = []
    for ev in _json_lines(stdout):
        if ev.get("type") not in ("error", "turn.failed"):
            continue
        err = ev.get("error")
        msgs.append(str(ev.get("message") or ""))
        if isinstance(err, dict):
            msgs.append(str(err.get("message") or ""))
        elif err:
            msgs.append(str(err))
    return "\n".join(m for m in msgs if m)


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ── What a run leaves in the logs (TMDEV-124) ───────────────────────────────
# The same JSON modes make stdout the whole session — every tool call's
# arguments and results — which flooded poll.log and the dashboard's Logs page.
# summarize_output turns it into what a reader of the log needs: the agent's
# final message, which tools it called, and the CLI's own errors. The raw
# stream is deliberately not kept anywhere; each CLI records its own session
# history. This is log-only: the verdict and usage parsers read the full stdout.

LOG_OUTPUT_CAP = 4000


def clip(text: str, limit: int = LOG_OUTPUT_CAP, keep: str = "head") -> str:
    """`text` cut to `limit` characters, saying how many went. keep="tail" keeps the end."""
    text = text or ""
    if len(text) <= limit:
        return text
    marker = f"[… {len(text) - limit} chars trimmed]"
    if keep == "tail":
        return f"{marker}\n{text[-limit:]}"
    return f"{text[:limit]}\n{marker}"


def _counted(names: list) -> str:
    """"a ×2, b" — each name once, in first-seen order."""
    counts = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    return ", ".join(n if c == 1 else f"{n} ×{c}" for n, c in counts.items())


def _tool_trace(names: list, failed: int = 0) -> str:
    if not names:
        return "no tool calls"
    plural = "s" if len(names) != 1 else ""
    fails = f" ({failed} failed)" if failed else ""
    return f"{len(names)} tool call{plural}{fails}: {_counted(names)}"


def _summary(trace: str, errors: str, message: str) -> str:
    lines = [f"Agent result — {trace}" if trace else "Agent result"]
    if errors.strip():
        lines.append("Errors: " + clip(errors.strip()))
    lines.append(clip(message.strip()) if message.strip() else "(no final message)")
    return "\n".join(lines)


def _unparsed(stdout: str) -> str:
    """Output in no shape the adapter knows — kept, since it may be the only clue, but clipped."""
    return "Agent output (not in the expected format):\n" + clip(stdout.strip())


class ClaudeAdapter:
    name = "claude"
    display_name = "Claude Code"
    binary_name = "claude"

    # Documented in `claude --help` and stable across releases, unlike full
    # model IDs — offered first at the install prompt.
    ALIASES = ("opus", "sonnet", "fable", "haiku")

    # What to tell a human whose CLI is not logged in. Per-agent because the
    # subcommands genuinely differ: `codex auth login` does not exist, and a
    # hint naming a command that does not exist is worse than no hint.
    LOGIN_HINT = "run `claude` once interactively (or `claude auth login`)"

    # The Claude CLI exits 0 on a model it does not recognise — probed live:
    #   $ claude -p "ok" --model definitely-not-a-real-model-xyz
    #   [claude-code:unrecognized_model] {...}
    #   There's an issue with the selected model (...). It may not exist or you
    #   may not have access to it.
    #   $ echo $?  →  0
    # So a rejected model is detectable only in the output, never from the
    # exit code. A valid model's run contains neither marker. Under
    # --output-format json (2.1.281) the same run exits 1, the first marker is
    # still on stderr and the second is in the JSON `result` on stdout — both
    # streams are read, so it matches either way.
    MODEL_REJECTED_MARKERS = (
        "unrecognized_model",
        "may not exist or you may not have access to it",
    )

    # Effort levels the CLI accepts, as `claude --help` documents them:
    #   --effort <level>   Effort level for the current session
    #                      (low, medium, high, xhigh, max)
    # A closed, documented set, so unlike a model this CAN be checked before
    # the run. Keep in sync: renderer/api/pipeline.py and mcp/server.py's
    # AGENT_EFFORTS, and dashboard/lib/agents.ts's AGENT_EFFORTS.
    EFFORTS = AGENT_EFFORTS
    DEFAULT_EFFORT = DEFAULT_AGENT_EFFORT

    # An OLDER CLI that has never heard of --effort is the only effort failure
    # worth falling back from, and it looks nothing like the model case.
    # Probed live against 2.1.278:
    #   $ claude -p "ok" --effort bogus-level
    #   Warning: Unknown --effort value 'bogus-level' — ignoring it and using
    #   the default effort. Valid values: low, medium, high, xhigh, max.
    #   $ echo $?  →  0        ...and the run still did the work.
    #   $ claude -p "ok" --definitely-not-a-flag x
    #   error: unknown option '--definitely-not-a-flag'
    #   $ echo $?  →  1        ...and nothing ran at all.
    # So a bad VALUE degrades gracefully and needs no re-run (_usable_effort
    # stops one reaching argv anyway); an unknown FLAG exits non-zero having
    # done nothing, and is what the fallback exists for.
    EFFORT_UNSUPPORTED_MARKERS = ("unknown option", "unknown argument")

    # The Claude CLI rejects the flag itself, independently of any model, so a
    # model-less install-time probe is a valid check for it.
    PROBES_EFFORT_WITHOUT_A_MODEL = True

    @classmethod
    def model_rejected(cls, output: str, returncode: int = 0) -> bool:
        # Exit-code INDEPENDENT, and that is the whole point for Claude: its
        # CLI exits 0 on a model it does not recognise, so requiring failure
        # here would never detect one. The returncode is accepted for the
        # shared signature and deliberately ignored.
        output = output or ""
        return any(marker in output for marker in cls.MODEL_REJECTED_MARKERS)

    @classmethod
    def effort_rejected(cls, stderr: str, returncode: int, stdout: str = "") -> bool:
        """Whether this run died because the CLI does not know --effort.

        Three conditions, all required, because the cost of a false positive is
        silently running every future tick without the flag:

        - a non-zero exit, since the process must have done nothing;
        - an unknown-option marker;
        - the flag's own name, so an unknown *other* option is not read as this.

        STDERR ONLY, deliberately — unlike model_rejected, which reads both
        streams. commander writes this error to stderr and produces no stdout,
        so nothing is lost; and an agent session whose own stdout happens to
        discuss `unknown option '--effort'` (a session editing this very file,
        say) would otherwise strip the flag for every run that followed.
        """
        if returncode == 0:
            return False
        stderr = stderr or ""
        return "--effort" in stderr and any(m in stderr for m in cls.EFFORT_UNSUPPORTED_MARKERS)

    # Model IDs as they appear in the installed CLI's own model catalog (the
    # CLI's error for an unknown model names "this version's model catalog").
    # The raw scan also finds Bedrock/Vertex `-v1` variants and odd internal
    # names; the second pattern keeps only plain IDs.
    _CATALOG_RE = re.compile(rb"claude-(?:opus|sonnet|haiku|fable)-[0-9a-z.-]+")
    _SUGGESTION_RE = re.compile(r"claude-(?:opus|sonnet|haiku|fable)-\d+(?:-\d+)?(?:-\d{8})?")

    @staticmethod
    def build_argv(binary: str, prompt: str, model: str = "", effort: str = "") -> list:
        # Permissions for a headless run come from the workspace's
        # .claude/settings.json (onboarding's _write_agent_allowlist), which
        # only takes effect once the workspace is also marked trusted in
        # ~/.claude.json (_write_agent_trust) — a project's permissions.allow
        # entries are otherwise silently ignored in `-p` mode. If that ever
        # proves insufficient, the documented fallback is passing them here:
        #   cmd += ["--allowedTools", "mcp__tubematic WebFetch WebSearch Read Glob Grep"]
        #
        # --output-format json is how the run's usage is read (TMDEV-107): one
        # JSON object whose `modelUsage` lists every model the session used,
        # each with its tokens and its own list-price `costUSD`.
        cmd = [binary, "-p", prompt, "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        return cmd

    @staticmethod
    def parse_usage(stdout: str, model: str = "", fetch=None) -> list:
        """One usage event per model the session used, from --output-format json.

        Cost is Claude's own `costUSD` for that model (`costBasis: "list"` —
        API list price, whatever the login), so no price table is involved.
        """
        try:
            data = json.loads((stdout or "").strip() or "{}")
        except ValueError:
            return []
        if not isinstance(data, dict):
            return []
        events = []
        for name, mu in (data.get("modelUsage") or {}).items():
            if not isinstance(mu, dict):
                continue
            events.append({
                "service": "anthropic",
                "model": mu.get("canonicalModel") or name,
                "units": {"input": _int(mu.get("inputTokens")),
                          "output": _int(mu.get("outputTokens")),
                          "cache_read": _int(mu.get("cacheReadInputTokens")),
                          "cache_write": _int(mu.get("cacheCreationInputTokens"))},
                "raw": {name: mu},
                "reported_cost_usd": float(mu.get("costUSD") or 0.0),
                "estimated": False,
            })
        if not events and float(data.get("total_cost_usd") or 0) > 0:
            events.append({"service": "anthropic", "model": model, "units": {},
                           "raw": {"usage": data.get("usage")},
                           "reported_cost_usd": float(data["total_cost_usd"]),
                           "estimated": False})
        return events

    @staticmethod
    def summarize_output(stdout: str) -> str:
        """The log's view of one run: its final `result`, turn count and denied tools.

        The one JSON object lists no individual tool calls, so the turn count
        and any permission denials are the trace.
        """
        if not (stdout or "").strip():
            return ""
        try:
            data = json.loads(stdout.strip())
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return _unparsed(stdout)
        trace = []
        if "num_turns" in data:
            turns = _int(data.get("num_turns"))
            trace.append(f"{turns} turn{'s' if turns != 1 else ''}")
        denied = [str(d.get("tool_name") or "?")
                  for d in data.get("permission_denials") or [] if isinstance(d, dict)]
        if denied:
            trace.append(f"{len(denied)} permission denial{'s' if len(denied) != 1 else ''}: "
                         f"{_counted(denied)}")
        errors = f"the CLI reported an error ({data.get('subtype') or 'no subtype'})" \
            if data.get("is_error") else ""
        return _summary("; ".join(trace), errors, str(data.get("result") or ""))

    @staticmethod
    def auth_status_argv(binary: str) -> list:
        # Free: no model call. The exact shape matters — the CLI treats an
        # unrecognised subcommand as a *prompt*, so a malformed verification
        # command silently becomes a billed model call instead of an error.
        return [binary, "auth", "status", "--json"]

    @staticmethod
    def logged_in(stdout: str, stderr: str = "", returncode: int = 0) -> bool:
        # `claude auth status --json` answers on stdout; stderr and the exit
        # code are accepted for the shared signature and ignored here.
        try:
            return json.loads(stdout).get("loggedIn") is True
        except (ValueError, AttributeError):
            return False

    @classmethod
    def probe_argv(cls, binary: str, model: str, effort: str = "") -> list:
        # An unknown model fails locally with no API call; a known one makes
        # one tiny real call. Judged by model_rejected, never the exit code.
        # With an effort, this doubles as the install-time check that the
        # installed CLI knows the flag at all — judged by effort_rejected.
        return cls.build_argv(binary, "ok", model, effort)

    # ── Deployment layout (consumed by onboard/, never by poll.py) ──────────
    CONFIG_HOME_ENV = None             # Claude's root is not environment-selectable
    SUPPORTED_SCOPES = ("user", "project")
    NEEDS_ALLOWLIST = True             # .claude/settings.json + the ~/.claude.json trust record
    NEEDS_PERMISSION_CONFIG = False    # that allowlist IS this agent's permission config
    COPIES_SKILLS_INTO_WORKSPACE = True  # cron runs from the workspace and needs them there
    HAS_COMMANDS = True
    REMOTION_AGENT_FLAG = "claude-code"

    @staticmethod
    def user_skills_dir(home, respect_override: bool = True):
        # Claude's root is not environment-selectable, so the flag is accepted
        # for the shared signature and ignored.
        return home / ".claude" / "skills"

    @staticmethod
    def user_commands_dir(home, respect_override: bool = True):
        # Claude's root is not environment-selectable, so the flag is accepted
        # for the shared signature and ignored.
        return home / ".claude" / "commands"

    @staticmethod
    def project_skills_dir(workspace):
        return workspace / ".claude" / "skills"

    @staticmethod
    def project_commands_dir(workspace):
        return workspace / ".claude" / "commands"

    # `claude mcp add` refuses a name that already exists ("MCP server ...
    # already exists"), so a redeploy removes the entry first. Probed against
    # 2.1.296. Before this, every upgrade's re-registration failed with a warning.
    MCP_ADD_REPLACES = False

    @staticmethod
    def mcp_add_argv(binary, scope, url, auth: McpAuth):
        """`add-json`, because `headersHelper` has no `mcp add` flag. Probed:
        the helper runs on every connection, so a rotated token file is picked
        up with no re-registration."""
        cmd = [binary, "mcp", "add-json"]
        if scope == "user":
            cmd += ["--scope", "user"]
        entry = {"type": "http", "url": url, "headersHelper": auth.helper}
        return cmd + ["tubematic", json.dumps(entry)]

    @staticmethod
    def mcp_remove_argv(binary, scope):
        """Undo mcp_add_argv: user scope by flag, a project install in the
        workspace's local scope (hence run with the workspace as cwd)."""
        return [binary, "mcp", "remove", *(["--scope", "user"] if scope == "user" else []),
                "tubematic"]

    @classmethod
    def suggest_models(cls, binary: str) -> list:
        """Model IDs named in the installed CLI's catalog, for the install
        prompt to offer.

        Suggest only, never gate: this reads an implementation detail of the
        binary that can change on any release. Any failure yields [] and the
        prompt falls back to plain free text.
        """
        try:
            data = Path(binary).resolve().read_bytes()
        except OSError:
            return []
        found = {m.decode("ascii", "ignore") for m in cls._CATALOG_RE.findall(data)}
        return sorted(m for m in found if cls._SUGGESTION_RE.fullmatch(m))


class CodexAdapter:
    """OpenAI's Codex CLI, driven through `codex exec`.

    Every argv and marker here was probed live against codex-cli 0.155.1; the
    reasoning for each choice is in the comments rather than in a ticket.
    """
    name = "codex"
    display_name = "Codex"
    binary_name = "codex"

    # No alias names exist: `codex exec -m` takes catalog slugs (gpt-5.6-sol,
    # gpt-6-astra, ...). The install prompt therefore offers only what
    # suggest_models finds, with no stable shorthand to lead with.
    ALIASES = ()

    LOGIN_HINT = "run `codex login` (a browser/device flow)"

    EFFORTS = AGENT_EFFORTS
    DEFAULT_EFFORT = DEFAULT_AGENT_EFFORT

    # Codex cannot reject the effort *flag* — it rides on the generic `-c`
    # override every version accepts — but the API rejects an effort the chosen
    # MODEL does not support, which is a different failure and a real one:
    # the shared five levels are not supported by every catalog model. Probed
    # live, `-m gpt-5.5 -c model_reasoning_effort=max` exits 1 with
    #   "code": "unsupported_value", "param": "reasoning.effort",
    #   "Unsupported value: 'max' is not supported with the 'gpt-5.5' model.
    #    Supported values are: 'none', 'low', 'medium', 'high', and 'xhigh'."
    # and a bad value gives "[ReasoningEffortParam] [reasoning.effort]
    # [invalid_enum_value]". Both name the parameter, so that is the marker.
    # On stderr, like Claude's, and the run does nothing — so it is worth the
    # one retry poll.py already knows how to make.
    EFFORT_UNSUPPORTED_MARKERS = ("reasoning.effort",)

    # ...but an install-time probe cannot find it, which is why this is a
    # separate flag rather than "are there markers". The rejection depends on
    # the model/effort PAIR, so it is probed with the default model in
    # onboard/agent_install.py rather than by a model-less run.
    PROBES_EFFORT_WITHOUT_A_MODEL = False

    # Codex reports an unusable model differently depending on how it is
    # authenticated, and BOTH have to be matched — probed live against each:
    #
    #   ChatGPT account: exit 1,
    #     ERROR: {..."The 'x' model is not supported when using Codex with a
    #     ChatGPT account."}
    #   API key: exit 1, after ten transport retries,
    #     ERROR: unexpected status 404 Not Found: The model `x` does not exist
    #     or you do not have access to it.
    #
    # Matching only the first leaves an API-key install with no fallback at
    # all: model_rejected stays false, poll.py never drops --model, and every
    # scheduled tick burns a run that does nothing.
    #
    # Deliberately NOT matching "Model metadata for ... not found", which the
    # CLI also prints for models the API subsequently accepts — treating that
    # as a rejection would drop --model on healthy runs, every tick, silently.
    # It appears in the API-key transcript above, directly beside a real
    # rejection, which is exactly how it would get swept in by accident.
    MODEL_REJECTED_MARKERS = (
        "is not supported when using Codex",
        "does not exist or you do not have access to it",
    )

    # ── Deployment layout (consumed by onboard/, never by poll.py) ───────────
    # User scope only, and that is a property of Codex rather than a
    # simplification: `codex mcp add` registers globally with no scope flag,
    # and project-scope skills (<project>/.codex/skills) are discovered only
    # inside a git repository, which the agent workspace is not. Offering
    # "project" would be a half-promise.
    SUPPORTED_SCOPES = ("user",)
    # Nothing to write: permission comes from `-s read-only` on argv, and
    # `codex exec` was verified to run in a directory absent from config.toml's
    # [projects] table with no trust prompt and no failure.
    NEEDS_ALLOWLIST = False
    NEEDS_PERMISSION_CONFIG = False
    # ~/.codex/skills is found from any working directory — verified against a
    # non-repo cwd — so the workspace needs no second copy for cron.
    COPIES_SKILLS_INTO_WORKSPACE = False
    # codex-cli 0.155.1 has no user-defined slash-command mechanism.
    HAS_COMMANDS = False
    REMOTION_AGENT_FLAG = "codex"

    @classmethod
    def model_rejected(cls, output: str, returncode: int = 0) -> bool:
        """Unlike Claude's, this REQUIRES a non-zero exit.

        Both observed Codex rejections exit non-zero, so demanding failure
        costs nothing — and it is what keeps the API-key marker safe. That one
        is an ordinary English sentence ("does not exist or you do not have
        access to it") which a *successful* run could easily contain: an agent
        reporting on a missing file, or quoting an error it read out of a log.
        Without the exit check such a run would be judged a model rejection and
        repeated with the CLI default, doubling the work and the bill.
        """
        if returncode == 0:
            return False
        output = output or ""
        return any(marker in output for marker in cls.MODEL_REJECTED_MARKERS)

    @classmethod
    def effort_rejected(cls, stderr: str, returncode: int, stdout: str = "") -> bool:
        """Whether this run died because the effort was not usable.

        For Codex that means the API refused the level for the chosen model,
        not that the CLI lacked the flag. Same two conditions as Claude's, and
        the same reason for each: a non-zero exit, so the run really did
        nothing, and never the agent's own words, so a session that merely
        discusses `reasoning.effort` cannot strip the flag from every run that
        follows.

        Under --json the rejection moves to STDOUT, as an `error` /
        `turn.failed` event (probed live, 0.156.1: stderr then carries only
        "Reading additional input from stdin..."). So stderr is read as
        before, plus the stream's error events only — the agent's own text is
        in `item.*` events and is never looked at.
        """
        if returncode == 0:
            return False
        text = f"{stderr or ''}\n{_json_error_messages(stdout)}"
        return any(m in text for m in cls.EFFORT_UNSUPPORTED_MARKERS)

    @staticmethod
    def build_argv(binary: str, prompt: str, model: str = "", effort: str = "") -> list:
        # --skip-git-repo-check is mandatory, not tidiness: the agent workspace
        # is not a git repository, and without it Codex refuses to start with
        # "Not inside a trusted directory and --skip-git-repo-check was not
        # specified" (exit 1, nothing run).
        #
        # -s read-only mirrors the Claude workspace allowlist (MCP tools, web,
        # read; no Write, no Bash). MCP tool calls are not sandboxed and were
        # verified to run unattended under it with no approval prompt, as was
        # Codex's built-in web search.
        #
        # `--` before the prompt is mandatory too: `codex exec` has subcommands
        # (resume/fork/review), so a bare positional prompt of exactly "resume"
        # is parsed as one.
        #
        # approvals_reviewer=auto_review is what makes MCP tools usable at all,
        # and it is NOT optional decoration. `codex exec` defaults its approval
        # policy to Never, and an MCP tool call under Never is refused outright:
        #   mcp: tubematic/get_pipeline_status (failed)
        #   MCP tool call requires approval, but approval policy is never
        # Every pipeline action goes through MCP, so without this the agent can
        # do nothing at all — it still exits 0, which is how this would have
        # shipped looking healthy. Verified in a clean container both ways.
        #
        # This routes approval requests through Codex's own automatic reviewer
        # rather than bypassing the approval system, which is why it is used in
        # preference to --dangerously-bypass-approvals-and-sandbox (a flag this
        # project rejects for Claude too). Combined with -s read-only the blast
        # radius stays a read-only sandbox either way.
        #
        # A developer machine can hide this: a personal ~/.codex/config.toml
        # that already sets a reviewer makes the bare command appear to work.
        #
        # --json turns stdout into a JSONL event stream, which is how the run's
        # usage is read (TMDEV-107): every `turn.completed` carries its token
        # counts. It carries no model name and no cost, so the model is the one
        # passed here (or the CLI's configured default) and the cost comes from
        # the price table.
        cmd = [binary, "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
               "-c", 'approvals_reviewer="auto_review"']
        if model:
            cmd += ["-m", model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        return cmd + ["--", prompt]

    @classmethod
    def parse_usage(cls, stdout: str, model: str = "", fetch=None) -> list:
        """One usage event for the whole run, summed over its turns.

        OpenAI counts cached input inside input_tokens, so it is split out into
        cache_read (priced far lower); reasoning tokens are inside
        output_tokens and are kept in the raw usage but not priced twice.
        """
        totals, turns = {}, 0
        for ev in _json_lines(stdout):
            if ev.get("type") != "turn.completed" or not isinstance(ev.get("usage"), dict):
                continue
            turns += 1
            for k, v in ev["usage"].items():
                totals[k] = totals.get(k, 0) + _int(v)
        if not turns:
            return []
        cached = totals.get("cached_input_tokens", 0)
        written = totals.get("cache_write_input_tokens", 0)
        return [{
            "service": "openai",
            "model": model or cls.configured_model(),
            "units": {"input": max(totals.get("input_tokens", 0) - cached - written, 0),
                      "cache_read": cached, "cache_write": written,
                      "output": totals.get("output_tokens", 0)},
            "raw": {"turns": turns, **totals},
            "reported_cost_usd": None,
            "estimated": False,
        }]

    # Item types that are a tool call; `mcp_tool_call` is traced by its tool name.
    _TOOL_ITEMS = ("mcp_tool_call", "command_execution", "web_search", "file_change")

    @classmethod
    def summarize_output(cls, stdout: str) -> str:
        """The log's view of one run: the last agent_message and the tool calls made.

        Only `item.completed` is read — a call also appears as `item.started`
        (probed live), so counting both would double every call.
        """
        if not (stdout or "").strip():
            return ""
        events = _json_lines(stdout)
        if not events:
            return _unparsed(stdout)
        names, failed, message, item_errors = [], 0, "", []
        for ev in events:
            item = ev.get("item")
            if ev.get("type") != "item.completed" or not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "agent_message":
                message = str(item.get("text") or "")
            elif kind == "error":
                item_errors.append(str(item.get("message") or ""))
            elif kind in cls._TOOL_ITEMS:
                names.append(str(item.get("tool") or kind) if kind == "mcp_tool_call" else kind)
                failed += item.get("status") in ("failed", "declined")
        errors = "\n".join(m for m in [_json_error_messages(stdout), *item_errors] if m)
        return _summary(_tool_trace(names, failed), errors, message)

    @classmethod
    def configured_model(cls) -> str:
        """The `model` in Codex's config.toml, which a run without -m uses; "" if unknown."""
        try:
            import tomllib
            with open(cls.config_home() / "config.toml", "rb") as fh:
                value = tomllib.load(fh).get("model")
            return value if isinstance(value, str) else ""
        except Exception:
            return ""

    @staticmethod
    def auth_status_argv(binary: str) -> list:
        # Free: no model call. There is no --json, so logged_in parses prose.
        return [binary, "login", "status"]

    @staticmethod
    def logged_in(stdout: str, stderr: str = "", returncode: int = 0) -> bool:
        """Whether `codex login status` reported a logged-in CLI.

        **It answers on STDERR, not stdout** — probed live, and the reason this
        signature takes both. Reading stdout alone sees an empty string and
        reports every logged-in CLI as logged out, which blocks the install.

        Both signals are required, because the two failure directions are not
        symmetric. Saying "logged out" when it is logged in blocks an install
        loudly, in front of a human. Saying "logged in" when it is not lets the
        install finish and every unattended cron tick fail silently afterwards.
        So: exit 0 (logged out exits 1) AND the affirmative wording, which
        cannot be matched by the logged-out "Not logged in".
        """
        if returncode != 0:
            return False
        return f"{stdout or ''}\n{stderr or ''}".strip().startswith("Logged in")

    @classmethod
    def probe_argv(cls, binary: str, model: str, effort: str = "") -> list:
        # An unknown model costs one rejected API call; a known one makes one
        # tiny real run. Judged by model_rejected, as Claude's is.
        return cls.build_argv(binary, "ok", model, effort)

    @classmethod
    def suggest_models(cls, binary: str) -> list:
        """Model slugs from the CLI's own catalog cache, for the install prompt.

        Suggest only, never gate: this reads a cache file the CLI owns and may
        reshape on any release, so any failure yields [] and the prompt falls
        back to plain free text. `binary` is unused — unlike Claude's catalog,
        Codex's does not live inside the executable.
        """
        try:
            data = json.loads((cls.config_home() / "models_cache.json").read_text())
            models = data["models"]
        except (OSError, ValueError, KeyError, TypeError):
            return []
        if not isinstance(models, list):
            return []
        # `visibility` is the field that exists; there is no `hidden` boolean.
        # Internal entries (gpt-reserve, codex-auto-review) carry "hide", and a
        # truthiness test on a key that is never present filtered nothing, so
        # they were being offered for selection. Anything that is not
        # explicitly listed is skipped: for a suggest-only feature, offering
        # too few names degrades to free text, while offering an internal model
        # invites storing one.
        return [m["slug"] for m in models
                if isinstance(m, dict) and m.get("slug")
                and m.get("visibility") == "list"]

    # ── Deployment layout ───────────────────────────────────────────────────

    # The environment variable that moves this agent's config root. Declared
    # rather than only read inside config_home so that a caller which has to
    # *strip* the override — the uninstaller, which must act on the root a
    # scheduled run uses — does not have to know the name by heart.
    CONFIG_HOME_ENV = "CODEX_HOME"

    @staticmethod
    def config_home(home=None, respect_override: bool = True):
        """Codex's own config root: $CODEX_HOME, else ~/.codex.

        One resolution for the catalog AND the skills destination. They used to
        disagree — the catalog honoured CODEX_HOME while skills always went to
        ~/.codex — so an install run with CODEX_HOME set deployed its skills
        where that Codex would never look for them.
        """
        override = os.environ.get("CODEX_HOME") if respect_override else None
        if override:
            return Path(override)
        return (home or Path.home()) / ".codex"

    @classmethod
    def user_skills_dir(cls, home, respect_override: bool = True):
        """Where this agent's skills live.

        `respect_override=False` asks for the root the *scheduled* runs will
        use, ignoring any environment override — which is what a read-only
        diagnostic wants, since cron never inherits one. A caller that is about
        to write files wants the default, True: it should act on the root this
        shell's CLI actually reads, and the lifecycle guard refuses the case
        where those two disagree.
        """
        return cls.config_home(home, respect_override) / "skills"

    @staticmethod
    def user_commands_dir(home, respect_override: bool = True):
        return None

    @staticmethod
    def project_skills_dir(workspace):
        return workspace / ".codex" / "skills"

    @staticmethod
    def project_commands_dir(workspace):
        return None

    # `codex mcp add` overwrites an existing entry -- and drops any key it does
    # not know how to set, the header helper included. Probed against 0.160.0.
    MCP_ADD_REPLACES = True

    @staticmethod
    def mcp_add_argv(binary, scope, url, auth: McpAuth):
        # scope is accepted and ignored: Codex registration is always global.
        # `auth` too: `codex mcp add` has no header flag, so the helper is
        # patched into config.toml afterwards (set_mcp_header_helper).
        return [binary, "mcp", "add", "tubematic", "--url", url]

    @classmethod
    def config_toml(cls, home=None, respect_override: bool = True):
        return cls.config_home(home, respect_override) / "config.toml"

    _TOML_HEADER = re.compile(r"^\s*\[")
    _OUR_TABLE = re.compile(r"^\s*\[mcp_servers\.tubematic\]\s*(#.*)?$")

    @classmethod
    def set_mcp_header_helper(cls, text: str, helper: str):
        """`text` with `http_headers_helper` set in `[mcp_servers.tubematic]`,
        or None when that table is absent.

        A line edit inside our own table rather than a TOML rewrite: the stdlib
        reads TOML but cannot write it, and a rewrite would drop the operator's
        comments. Probed: Codex parses a hand-added key and reports it through
        `codex mcp get tubematic --json`.
        """
        lines = text.splitlines()
        start = next((i for i, line in enumerate(lines) if cls._OUR_TABLE.match(line)), None)
        if start is None:
            return None
        end = next((i for i in range(start + 1, len(lines)) if cls._TOML_HEADER.match(lines[i])),
                   len(lines))
        body = [line for line in lines[start + 1:end]
                if not line.strip().startswith("http_headers_helper")]
        # A JSON string is a valid TOML basic string for this alphabet.
        new = lines[:start + 1] + [f"http_headers_helper = {json.dumps(helper)}"] + body + lines[end:]
        return "\n".join(new) + "\n"

    @staticmethod
    def mcp_remove_argv(binary, scope):
        return [binary, "mcp", "remove", "tubematic"]


class OpenCodeAdapter:
    """OpenCode's CLI (v2), driven through `opencode run`.

    Every argv, marker and path here was probed live against `@opencode/cli`
    2.0.14 in a clean container with no credentials at all; the reasoning for
    each choice is in the comments rather than in a ticket. Only the v2 package
    (`@opencode/cli`) is supported — the legacy 1.x line (`opencode-ai`) uses
    different config field names and is deliberately out of scope.
    """
    name = "opencode"
    display_name = "OpenCode"
    binary_name = "opencode"

    # No alias names exist: `opencode run --model` takes `provider/model` slugs
    # (anthropic/claude-sonnet-4-5, opencode/gpt-5.5, ...). The install prompt
    # therefore offers only what suggest_models finds.
    ALIASES = ()

    LOGIN_HINT = "run `opencode auth login` (a browser/device flow, or an API key)"

    EFFORTS = AGENT_EFFORTS
    DEFAULT_EFFORT = DEFAULT_AGENT_EFFORT

    # OpenCode has no --effort flag at all. Reasoning effort is a model
    # *variant*, written as a `#suffix` on the model itself — documented in
    # `opencode run --help` as "provider/model#variant". So the effort cannot
    # be expressed without a model, which build_argv enforces and which is what
    # keeps poll.py's fallback ladder terminating.
    #
    # A variant the model does not define is rejected before any API call, and
    # — unlike Codex's — it is cleanly distinguishable from a rejected model.
    # Probed live, logged out, both on stderr with exit 1:
    #   $ opencode run -m bogus/bogus -- "ok"
    #   Error: Model unavailable: bogus/bogus
    #   $ opencode run -m opencode/nemotron-3-ultra-free#definitelynotavariant -- "ok"
    #   Error: Variant unavailable for opencode/nemotron-3-ultra-free: definitelynotavariant
    # Distinguishable matters: it means an unusable effort costs one retry with
    # the model kept, instead of throwing the chosen model away as well.
    EFFORT_UNSUPPORTED_MARKERS = ("Variant unavailable",)

    # The rejection depends on the model/variant PAIR, exactly like Codex's, so
    # a model-less probe proves nothing and would still be a billed run.
    PROBES_EFFORT_WITHOUT_A_MODEL = False

    MODEL_REJECTED_MARKERS = ("Model unavailable",)

    @classmethod
    def model_rejected(cls, output: str, returncode: int = 0) -> bool:
        """Like Codex's, this REQUIRES a non-zero exit.

        The marker is an ordinary English phrase that a *successful* run could
        easily contain — an agent reporting on a provider outage, or quoting an
        error out of poll.log. Without the exit check such a run would be
        judged a model rejection and repeated with the CLI default, doubling
        the work and the bill.
        """
        if returncode == 0:
            return False
        output = output or ""
        return any(marker in output for marker in cls.MODEL_REJECTED_MARKERS)

    @classmethod
    def effort_rejected(cls, stderr: str, returncode: int, stdout: str = "") -> bool:
        """Whether this run died because the model has no such variant.

        Same two conditions as the other adapters, for the same reasons: a
        non-zero exit, so the run really did nothing, and never the agent's
        own words, so a session that merely discusses variants cannot strip
        the effort from every run that follows.

        Under --format json the rejection moves to STDOUT as an `error` event,
        with stderr empty (probed live, 2.0.14):
          {"type":"error",...,"error":{"type":"provider.no-route",
           "message":"Variant unavailable for opencode/...: bogus"}}
        So stderr is read as before, plus the stream's error events only.
        """
        if returncode == 0:
            return False
        text = f"{stderr or ''}\n{_json_error_messages(stdout)}"
        return any(m in text for m in cls.EFFORT_UNSUPPORTED_MARKERS)

    @staticmethod
    def build_argv(binary: str, prompt: str, model: str = "", effort: str = "") -> list:
        # --auto is what makes an unattended run possible at all, and it is NOT
        # optional decoration. OpenCode resolves an unmatched permission to
        # `ask`; in a non-interactive `opencode run` an `ask` is auto-REJECTED
        # and takes the whole session down with it. Probed live:
        #   ! permission requested: external_directory (/tmp/*); auto-rejecting
        #   Error: Session interrupted: shutdown        (exit 1, nothing done)
        # The agent workspace sits beside the poll logs and the prompts tell the
        # agent to read them, so that `ask` is on the normal path, not an edge
        # case. With --auto the same run completes and exits 0.
        #
        # This is not a blanket bypass: --auto approves only what is not
        # explicitly DENIED, and the install writes the denials into the
        # workspace's own opencode.json (see PERMISSION_RULES). A deny survives
        # --auto, returns a clean tool error, and the session keeps going —
        # verified both ways.
        #
        # `--` before the prompt keeps a prompt that begins with a dash from
        # being parsed as a flag.
        #
        # Deliberately NOT `--agent plan`: `plan` is a built-in read-only agent
        # whose system prompt is about exploring and planning, and this agent's
        # job is to operate the pipeline. The restriction belongs in the
        # workspace permissions, which is also how the Claude and Codex
        # adapters do it — a normal agent plus an external limit.
        #
        # --format json makes stdout a JSONL event stream whose events carry
        # the sessionID the run's usage is then read by (TMDEV-107; see
        # parse_usage). It also moves the CLI's own errors onto stdout.
        cmd = [binary, "run", "--auto", "--format", "json"]
        if model:
            # Effort is a variant of the model, so it cannot be sent without
            # one. poll.py's model fallback therefore drops the effort with it,
            # which is fine: three runs remain the hard ceiling either way.
            cmd += ["--model", f"{model}#{effort}" if effort else model]
        return cmd + ["--", prompt]

    # OpenCode's providers, mapped to the ledger's service names where they
    # are the same vendor; any other provider (opencode, openrouter, ...) is
    # recorded under its own id.
    _SERVICE_BY_PROVIDER = {"anthropic": "anthropic", "openai": "openai", "google": "gemini"}

    @staticmethod
    def session_usage_argv(binary: str, session_id: str) -> list:
        """Every message of one session, with per-message tokens and cost.

        Free — a read against the local background service, no model call.
        """
        return [binary, "api", "GET", f"/api/session/{session_id}/message"]

    @classmethod
    def parse_usage(cls, stdout: str, model: str = "", fetch=None) -> list:
        """Usage events per (provider, model), from the session's own record.

        The JSONL stream alone is not enough, which is why this takes `fetch`
        (a callable taking a session id and returning the stdout of
        session_usage_argv for it). Probed live,
        2.0.14: `step_finish` events do carry each step's tokens and cost, but
        the LAST step's event is sometimes never written — a one-step run
        emitted none at all. The session API returns every assistant message
        with its model, tokens and OpenCode's own `cost`, so it is the source;
        the stream's step_finish events are the fallback, marked estimated.
        """
        events = _json_lines(stdout)
        session_id = next((e.get("sessionID") for e in events if e.get("sessionID")), "")
        messages = []
        if session_id and fetch is not None:
            try:
                page = json.loads(fetch(session_id) or "{}")
                messages = [m for m in page.get("data") or []
                            if isinstance(m, dict) and m.get("type") == "assistant"]
            except Exception:
                messages = []
        estimated = False
        if not messages:
            estimated = True
            provider, _, name = (model or "").partition("/")
            messages = [{"model": {"providerID": provider, "id": name.split("#")[0]},
                         "cost": (e.get("part") or {}).get("cost"),
                         "tokens": (e.get("part") or {}).get("tokens")}
                        for e in events if e.get("type") == "step_finish"]
        grouped = {}
        for m in messages:
            mdl = m.get("model") or {}
            provider = str(mdl.get("providerID") or "")
            key = (cls._SERVICE_BY_PROVIDER.get(provider, provider or "opencode"),
                   str(mdl.get("id") or ""))
            g = grouped.setdefault(key, {"input": 0, "output": 0, "reasoning": 0,
                                         "cache_read": 0, "cache_write": 0, "cost": 0.0,
                                         "messages": 0})
            tokens = m.get("tokens") or {}
            cache = tokens.get("cache") or {}
            g["input"] += _int(tokens.get("input"))
            g["output"] += _int(tokens.get("output"))
            g["reasoning"] += _int(tokens.get("reasoning"))
            g["cache_read"] += _int(cache.get("read"))
            g["cache_write"] += _int(cache.get("write"))
            try:
                g["cost"] += float(m.get("cost") or 0.0)
            except (TypeError, ValueError):
                pass
            g["messages"] += 1
        return [{
            "service": service, "model": name,
            "units": {k: g[k] for k in ("input", "output", "reasoning", "cache_read",
                                        "cache_write")},
            "raw": {"session_id": session_id, **g},
            "reported_cost_usd": g["cost"],
            "estimated": estimated,
        } for (service, name), g in grouped.items()]

    @staticmethod
    def summarize_output(stdout: str) -> str:
        """The log's view of one run: the last `text` part and the tool calls made.

        A call is keyed by its callID, the last event for it winning, so a call
        reported more than once (running, then completed) is counted once.
        """
        if not (stdout or "").strip():
            return ""
        events = _json_lines(stdout)
        if not events:
            return _unparsed(stdout)
        calls, message = {}, ""
        for i, ev in enumerate(events):
            part = ev.get("part") if isinstance(ev.get("part"), dict) else {}
            if ev.get("type") == "text":
                message = str(part.get("text") or "") or message
            elif ev.get("type") == "tool_use":
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                key = part.get("callID") or part.get("id") or f"#{i}"
                calls[key] = (str(part.get("tool") or "tool"), state.get("status"))
        names = [name for name, _ in calls.values()]
        failed = sum(status == "error" for _, status in calls.values())
        return _summary(_tool_trace(names, failed), _json_error_messages(stdout), message)

    @staticmethod
    def auth_status_argv(binary: str) -> list:
        # Free: no model call. There is no `auth status` and no --json.
        return [binary, "auth", "list"]

    @staticmethod
    def logged_in(stdout: str, stderr: str = "", returncode: int = 0) -> bool:
        """Whether `opencode auth list` reported any usable credential.

        **The exit code carries no information here** — probed live, a logged
        OUT CLI exits 0 and prints `No authenticated integrations` on stdout,
        with stderr empty. So unlike Codex's, this cannot lean on the exit
        code, and the negative phrase is the only signal available.

        Read as "not logged out" rather than "logged in" on purpose. The two
        failure directions are not symmetric: saying "logged out" when it is
        logged in blocks an install loudly, in front of a human, while saying
        "logged in" when it is not lets the install finish and every unattended
        cron tick fail silently afterwards. Matching the one phrase the CLI
        prints for an empty credential store keeps the silent direction tied to
        that exact wording changing, rather than to a listing format we would
        have to keep re-parsing. Empty output is treated as logged out, so a
        CLI that printed nothing at all cannot pass.
        """
        if returncode != 0:
            return False
        text = f"{stdout or ''}\n{stderr or ''}".strip()
        if not text:
            return False
        return "No authenticated integrations" not in text

    @classmethod
    def probe_argv(cls, binary: str, model: str, effort: str = "") -> list:
        # An unknown model or variant is rejected locally, before any API call,
        # so a bad name costs nothing; a good one makes one tiny real run.
        return cls.build_argv(binary, "ok", model, effort)

    @classmethod
    def suggest_models(cls, binary: str) -> list:
        """Model slugs from `opencode models`, for the install prompt to offer.

        Suggest only, never gate: any failure yields [] and the prompt falls
        back to plain free text. Unlike the other two adapters this shells out
        rather than reading a file — OpenCode keeps no catalog on disk, and the
        command works logged out (it lists the free models) so it is safe to
        run before the login has been checked. Read-only, and called only from
        onboarding, never from poll.py.
        """
        try:
            r = subprocess.run([binary, "models"], capture_output=True, text=True,
                               timeout=cls.MODELS_TIMEOUT_SECS)
        except (OSError, subprocess.SubprocessError):
            return []
        if r.returncode != 0:
            return []
        # One `provider/model` slug per line. Anything else the command might
        # print (a header, a warning) simply does not match and is dropped.
        return [line.strip() for line in (r.stdout or "").splitlines()
                if cls._SLUG_RE.fullmatch(line.strip())]

    MODELS_TIMEOUT_SECS = 30

    # A slug is two OR MORE `/`-separated segments, not exactly two. Some
    # providers namespace by vendor as well: `openrouter/qwen/qwen3.8-27b`,
    # `openrouter/meta-llama/llama-4-70b`. A pattern that allowed one `/`
    # dropped every OpenRouter model from the suggestions while `opencode
    # models` listed them happily — silently, because a dropped line looks
    # exactly like a header line that was meant to be dropped.
    #
    # Each segment must still START alphanumeric, which is what keeps this a
    # filter rather than a pass-through: a decorated or prose line
    # (`Available models:`, `* anthropic/x`) does not match, and neither does
    # anything `_agent_model` would reject at the prompt anyway.
    _SLUG_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._:-]*"
    _SLUG_RE = re.compile(rf"{_SLUG_SEGMENT}(?:/{_SLUG_SEGMENT})+")

    # ── Deployment layout (consumed by onboard/, never by poll.py) ───────────
    SUPPORTED_SCOPES = ("user", "project")
    # Claude's `.claude/settings.json` allowlist plus the ~/.claude.json trust
    # record. OpenCode has its own, different mechanism — see
    # NEEDS_PERMISSION_CONFIG.
    NEEDS_ALLOWLIST = False
    # An ordered permission list in the workspace's own opencode.json, which
    # every scheduled run picks up because cron runs the agent from there.
    NEEDS_PERMISSION_CONFIG = True
    # `~/.config/opencode/skills` is found from any working directory —
    # verified against a non-repo cwd — so the workspace needs no second copy.
    COPIES_SKILLS_INTO_WORKSPACE = False
    HAS_COMMANDS = True
    # Probed: `skills add -a opencode` is recognised ("copy → OpenCode") and
    # installs into ~/.agents/skills/, which OpenCode reads as a global
    # compatibility source.
    REMOTION_AGENT_FLAG = "opencode"

    # Written into the workspace's opencode.json by the installer. Ordered, and
    # the last matching rule wins, so these sit on top of OpenCode's own
    # defaults (which start at `* * allow`).
    #
    # This is the whole security posture of an OpenCode install, and it is the
    # counterpart of Claude's allowlist and Codex's `-s read-only`:
    #
    # - edit/write are denied because every pipeline write goes through an MCP
    #   tool. A denied tool is not merely refused, it is removed from the
    #   catalogue the model sees — verified — so this also stops the agent
    #   wasting turns looking for it.
    # - shell is denied because, unlike Codex's read-only sandbox, nothing
    #   constrains a command OpenCode runs. See the free-tier note below.
    # - the .env rules encode the rule that this project's agents never read
    #   credential files. They are DENY rather than OpenCode's default `ask`
    #   precisely because --auto approves an `ask`.
    PERMISSION_RULES = (
        # ── ALLOW: what the pipeline needs, asserted rather than assumed ────
        # Deny-only is not enough. OpenCode resolves permissions last-match-
        # wins across every merged document, so an action this list says
        # nothing about is decided by whatever the operator's own config says.
        # Measured: with a global `deny webfetch`/`deny websearch` those were
        # the only matching rules and won, and a global `deny tubematic_*`
        # blocked the MCP tools outright — the pipeline would have done
        # nothing, every tick, while looking healthy.
        #
        # This document is the highest-precedence one, so asserting the
        # positives here is what makes them survive a hostile or merely
        # opinionated global config. `tubematic_*` is the MCP namespace:
        # permission actions match the normalised `<server>_<tool>` name, which
        # was confirmed by denying it and watching the tool call fail.
        {"action": "tubematic_*", "resource": "*", "effect": "allow"},
        {"action": "webfetch", "resource": "*", "effect": "allow"},
        {"action": "websearch", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "grep", "resource": "*", "effect": "allow"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        # ── DENY: what it must never do, last so they win the overlap ───────
        # Every pipeline write goes through an MCP tool, so edit/write cost
        # nothing. Nothing sandboxes a command OpenCode runs — unlike Codex's
        # read-only sandbox — so shell would make OpenCode the most permissive
        # of the three agents. A denied tool is removed from the catalogue the
        # model sees, not merely refused, so this also stops the agent spending
        # turns looking for one it cannot have.
        #
        # The .env rules are DENY rather than OpenCode's default `ask`
        # precisely because `--auto` approves an `ask`.
        {"action": "edit", "resource": "*", "effect": "deny"},
        {"action": "write", "resource": "*", "effect": "deny"},
        {"action": "shell", "resource": "*", "effect": "deny"},
        {"action": "read", "resource": "*.env", "effect": "deny"},
        {"action": "read", "resource": "*.env.*", "effect": "deny"},
        {"action": "read", "resource": "*.env.example", "effect": "allow"},
    )

    # A note about OpenCode's FREE tier, because it changed under us.
    #
    # On 2.0.14, denying `shell` made the free tier refuse to run at all —
    # "OpenCode's free tier can only be used from within OpenCode" — and that
    # was isolated carefully: only `shell` + `deny` tripped it, in either
    # config scope, while denying edit, write or `.env` reads was fine. On
    # 2.0.15 the same install runs normally with `shell` denied (measured on
    # `space-bunny-free`, with the deny confirmed in the effective rules).
    #
    # So do not state it as a requirement in either direction. The reason an
    # OpenCode install wants a real provider is unchanged, and is a judgement
    # rather than a measurement: the free models are far too weak to drive this
    # pipeline. If a run ever fails with that message, the shell rule is the
    # first thing to look at.

    # Tubematic's own config document, inside the agent workspace. Everything
    # this install asserts lives here and NOWHERE else, which is what keeps the
    # installer out of documents a human owns.
    #
    # The workspace is Tubematic's own directory — `~/.tubematic-agent/<agent>`
    # by default, created by the installer and documented as the agent's own —
    # so this document is Tubematic's outright. It is written on install and
    # removed on uninstall, with no ownership test: the guard that matters is
    # at the workspace *question*, which refuses a directory that is already
    # somebody's OpenCode project.
    #
    # `.opencode/opencode.json` rather than the workspace's direct
    # `opencode.json`, and that is a correctness requirement, not tidiness.
    # Probed against 2.0.15 — documents are merged in this order, lowest first,
    # and `permissions` arrays are CONCATENATED, so the last matching rule
    # across the whole merged list wins:
    #
    #   ~/.config/opencode/       (global)
    #   <ancestor>/opencode.json
    #   <workspace>/opencode.json
    #   <ancestor>/.opencode/opencode.json
    #   <workspace>/.opencode/opencode.json     ← highest
    #
    # So this file's rules beat every other document, including an ancestor
    # `~/.opencode/opencode.json` a developer may keep. Measured both ways: a
    # deny here blocked a credential read against a user `allow` in each of the
    # four other locations, while the same deny in the workspace's *direct*
    # file was overridden by `~/.opencode` and the file was read.
    MANAGED_CONFIG_DIR = ".opencode"

    @classmethod
    def managed_config_file(cls, workspace):
        """The document to read Tubematic's own settings back from."""
        return cls.managed_config_files(workspace)[0]

    @classmethod
    def managed_config_files(cls, workspace):
        """EVERY basename OpenCode loads from the managed directory.

        Tubematic writes all of them, with identical content, and that is the
        defence rather than a flourish. OpenCode loads
        `.opencode/opencode.jsonc` *after* `.opencode/opencode.json`, so a
        single rule in whichever file Tubematic did not write outranks every
        rule in the one it did — measured, an operator `.jsonc` beside our
        `.json` turned a credential deny into an allow and the agent read the
        file.

        Occupying both leaves no slot. Probed against 2.0.15 with five other
        plausible names in that directory (`opencode.json5`, `config.json`,
        `opencode.jsonc.local`, `settings.json`, `opencode.yaml`), each
        carrying an `allow`: none was loaded, the effective rules stayed
        `deny, deny`, and the run was blocked. The alternative — scanning for a
        foreign sibling — must be repeated at every entrance that deploys or
        runs the agent, and was missed at two of them.
        """
        return [workspace / cls.MANAGED_CONFIG_DIR / name for name in cls.CONFIG_BASENAMES]

    # The options this install asserts on the server entry.
    MCP_SERVER_OPTIONS = {"codemode": False}

    @classmethod
    def remove_mcp_entry(cls, text: str):
        """`text` with this project's MCP server removed, or None if unsafe."""
        return remove_jsonc_member(text, ["mcp", "servers", "tubematic"])

    @staticmethod
    def auth_headers(auth: McpAuth) -> dict:
        """`{file:}` makes OpenCode read the token file itself. Undocumented in
        the v2 docs but probed against 2.0.26 (connects; a wrong token is
        refused). OpenCode reads it when its background service loads the
        config, so a rotation needs `opencode reload` (RELOAD_ARGV)."""
        return {"Authorization": f"Bearer {{file:{auth.token_file}}}"}

    # `opencode mcp add` overwrites an existing entry. Probed against 2.0.26.
    MCP_ADD_REPLACES = True

    @classmethod
    def mcp_server_entry(cls, url: str, auth: McpAuth) -> dict:
        """The COMPLETE server entry for the managed document.

        Complete, not just the options, and that was probed rather than
        assumed: an `mcp.servers.tubematic` entry carrying only `codemode`
        merges far enough for the server to connect — `mcp list` reports it
        `connected`, because the `url` is picked up from the other document —
        but the option itself does not apply and Code Mode stays on. Repeating
        `type` and `url` here is what makes it take effect.
        """
        return {"type": "remote", "url": url, "headers": cls.auth_headers(auth),
                **cls.MCP_SERVER_OPTIONS}

    # Why the managed entry turns Code Mode off.
    # Code Mode is OpenCode's default and hides every MCP tool behind a
    # `search()`/`execute()` sandbox, where the tools are named
    # `tools.tubematic.<tool>(...)`. The skills name their tools directly, so
    # the agent spends its whole session hunting a catalogue instead of working
    # — observed, not theorised. With codemode off the same tools appear
    # natively as `tubematic_<tool>` and are called on the first try.
    #
    # `oauth` is deliberately NOT set: remote servers are documented as using
    # OAuth by default, but a server answering a bad token with a bare
    # `WWW-Authenticate: Bearer` was probed and connects with the header alone;
    # `opencode mcp add` has no flag for it either, so leaving it out keeps the
    # global and the managed entry alike.

    CONFIG_HOME_ENV = "XDG_CONFIG_HOME"

    @staticmethod
    def config_home(home=None, respect_override: bool = True):
        """OpenCode's own config root: $XDG_CONFIG_HOME/opencode, else
        ~/.config/opencode.

        One resolution for the skills, the commands and the global config file.
        `respect_override=False` asks for the root the *scheduled* runs will
        use: cron strips the environment down to HOME/LOGNAME/PATH/SHELL, so it
        never inherits XDG_CONFIG_HOME.
        """
        override = os.environ.get("XDG_CONFIG_HOME") if respect_override else None
        base = Path(override) if override else (home or Path.home()) / ".config"
        return base / "opencode"

    @classmethod
    def user_skills_dir(cls, home, respect_override: bool = True):
        return cls.config_home(home, respect_override) / "skills"

    @classmethod
    def user_commands_dir(cls, home, respect_override: bool = True):
        return cls.config_home(home, respect_override) / "commands"

    @staticmethod
    def project_skills_dir(workspace):
        return workspace / ".opencode" / "skills"

    @staticmethod
    def project_commands_dir(workspace):
        return workspace / ".opencode" / "commands"

    # OpenCode reads `opencode.json` OR `opencode.jsonc`, and the CLI writes to
    # whichever is already there. Probed against 2.0.14: with only a `.jsonc`
    # present, `opencode mcp add --global` appended to **that** file (comments
    # and trailing comma preserved); with both present it chose `.json`; with
    # neither it created `.json`. Assuming `.json` meant that on a `.jsonc`
    # machine the Code Mode patch was silently skipped, the post-install check
    # reported a correct install as broken, and the uninstall left the
    # registration behind — so the name is resolved, never assumed.
    CONFIG_BASENAMES = ("opencode.json", "opencode.jsonc")

    # Exposed on the adapter so a caller holding one never has to know which
    # dialect that agent's config is written in.
    parse_config = staticmethod(parse_jsonc)

    @classmethod
    def _resolve_config(cls, directory):
        for name in cls.CONFIG_BASENAMES:
            if (directory / name).is_file():
                return directory / name
        # Neither exists: name the one the CLI would create.
        return directory / cls.CONFIG_BASENAMES[0]

    @classmethod
    def config_file(cls, home=None, respect_override: bool = True):
        """The global config document `opencode mcp add --global` writes."""
        return cls._resolve_config(cls.config_home(home, respect_override))

    @classmethod
    def workspace_config_file(cls, workspace):
        """The project config document, and the one the permission rules go in.

        `<workspace>/opencode.json(c)`, not `<workspace>/.opencode/...`: that is
        where `opencode mcp add` writes a project registration, and keeping both
        in one document means a scope's whole configuration is one file to read,
        patch and remove.
        """
        return cls._resolve_config(workspace)

    @classmethod
    def mcp_config_file(cls, home, workspace, scope: str, respect_override: bool = True):
        """The document holding this scope's `mcp.servers.tubematic` entry."""
        if scope == "project":
            return cls.workspace_config_file(workspace)
        return cls.config_file(home, respect_override)

    @classmethod
    def mcp_add_argv(cls, binary, scope, url, auth: McpAuth):
        # --global writes the shared ~/.config/opencode/opencode.json; without
        # it the entry goes to <cwd>/opencode.json, so a project registration
        # must be run with the workspace as cwd (deploy already does). The
        # header value is the `{file:}` reference, stored as written.
        cmd = [binary, "mcp", "add", "tubematic"]
        if scope == "user":
            cmd.append("--global")
        header = "Authorization=" + cls.auth_headers(auth)["Authorization"]
        return cmd + ["--url", url, "--header", header]

    @staticmethod
    def reload_argv(binary):
        """Re-read the config, and with it the token file. OpenCode answers
        from a background service that caches both."""
        return [binary, "reload"]

    @staticmethod
    def mcp_remove_argv(binary, scope):
        """None: there is no `opencode mcp remove`.

        Probed — `opencode mcp` offers list, add, auth and logout, and nothing
        else. Deregistration is therefore a config edit, which the caller does
        through mcp_config_file(); returning None rather than an argv that does
        not exist is what stops an uninstall reporting success for a command
        that never ran.
        """
        return None


ADAPTERS = {a.name: a for a in (ClaudeAdapter, CodexAdapter, OpenCodeAdapter)}
