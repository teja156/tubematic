#!/usr/bin/env python3
"""Tubematic upgrade — one non-interactive command that runs the whole upgrade.

Run it from the install you are upgrading *to*: a source checkout after
`git checkout vX.Y.Z`, or a freshly extracted release tarball's directory.

In order:
  1. Pre-flight: an existing install, the prerequisites, a dashboard password
     (`python onboard.py --set-password` sets one; this command never asks),
     a stored OpenAI API key (every scene image comes from OpenAI),
     no generated scene importing the removed GifFX component,
     and no work in flight (a render, a voicing, a running agent session, a
     publish upload). It holds poll.py's lock from here to the end, so no
     agent tick starts mid-upgrade.
  2. Python dependencies into this directory's .venv (cron will run it).
  3. New images: pulled (release) or built (source). The old stack keeps
     serving while this happens.
  4. The in-flight check and the GifFX check again (the old stack kept serving
     through the build), then stop the whole stack — so new code never
     migrates the database while old code is still running against it.
  5. Start: data directories, Docker volume reconciliation, any missing
     service token, `up -d`, health.
     The containers apply any pending migrations themselves, backing up
     first. This script never runs a migration.
  6. Rewrite the cron entry to point at this directory.
  7. Redeploy each installed agent's skills and commands from this directory,
     and re-register MCP with the token. An agent left without it fails the
     upgrade: the MCP server would refuse every call it makes.
  8. Report: version, schema, cron, containers.

Flags:
  --check          Report the install's state and change nothing
  --dry-run        Show what would happen; change nothing
  --force          Proceed even though work is in flight (it will be killed)
  --no-stop        Skip the stop and let `up -d` recreate containers one at a
                   time. Only for an upgrade whose migrations you know are
                   additive: old code briefly runs against the new schema.
                   Refused while any service token is missing, because old and
                   new containers would then refuse each other's calls, and
                   while the migration retiring the Gemini image provider is
                   pending, because old containers would keep generating
                   images through a provider the database no longer names.
  --install-mode {dev,release}
                   Override the detected install mode
  --help, -h       Show this and exit
"""
import json
import posixpath
import re
import shutil
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()

FLAGS = ("--check", "--dry-run", "--force", "--no-stop", "--install-mode", "--help", "-h")

# The onboarding steps an upgrade actually re-runs, recorded as done in this
# directory's .onboard-state.json. Only these: claiming install_config or
# pipeline_settings would be claiming work this command never did.
UPGRADE_STEPS = ("prerequisites", "python_deps", "directories", "auth", "cron", "renderer",
                 "dashboard")


def _bootstrap() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from onboard.bootstrap import ensure_deps, ensure_venv
    ensure_venv(Path(__file__))
    ensure_deps()


def _section(title: str) -> None:
    from rich.rule import Rule
    from onboard.plain import console
    console.print()
    console.print(Rule(f"[bold] {title} [/bold]", style="blue"))


def _fetch_images(ex, rep, mode: str) -> None:
    """Pull or build both images. Only the images change here: running
    containers keep the image they were started from until recreated, so the
    old stack serves throughout and downtime is the stop/start, not the build."""
    from onboard.actions import _compose, _pull_failure_hint
    verb = "pull" if mode == "release" else "build"
    with rep.spinner(f"{'Pulling' if verb == 'pull' else 'Building'} images…"):
        r = ex.run([*_compose(), verb, "tubematic-api", "tubematic-dashboard"], cwd=REPO_ROOT)
    if r.returncode != 0:
        hint = (_pull_failure_hint(r) if verb == "pull"
                else (r.stderr or "").strip()[-500:])
        rep.fail(f"docker compose {verb} failed", hint)
    rep.ok(f"Images {'pulled' if verb == 'pull' else 'built'}")


def _redeploy_agents(ex, rep, db_path) -> list:
    """Copy each installed agent's skills and commands again, from this
    directory, and re-register MCP — what `onboard.py --install-agent` does,
    minus the questions, the login check and the (paid) model probe. The
    stored row supplies every answer. Skipped rather than failed when the
    agent's binary is gone: the stack upgrade itself has already succeeded.

    Returns the agents left without a working MCP registration. Since the
    server requires a token (TMDEV-152), such an agent is refused on every call
    -- a pipeline that stalls while looking healthy -- so the caller fails the
    upgrade on any of them rather than only warning."""
    from onboard import agent_install, checks
    from onboard.config import read_agents

    rows = [a for a in read_agents(db_path) if not a.get("archived_at")]
    if not rows:
        rep.info("No agent installed — nothing to redeploy. "
                 "Install one with: python onboard.py --install-agent <agent>")
        return []
    stranded = []
    for row in rows:
        adapter = agent_install.ADAPTERS.get(row["id"])
        if adapter is None:
            rep.warn(f"Agent '{row['id']}' is not supported by this version — skipped")
            continue
        conflict = agent_install.config_root_conflict(adapter)
        if conflict:
            # Redeploying here would put the skills in a root the scheduled
            # runs never read, leaving the upgrade looking successful.
            rep.warn(f"{conflict[0]} — agent '{row['id']}' not redeployed. {conflict[1]}")
            stranded.append(row["id"])
            continue
        binary = row.get("binary") or adapter.binary_name
        if not (shutil.which(binary) or Path(binary).exists()):
            rep.warn(f"{binary} not found — agent '{row['id']}' not redeployed. Fix the path, "
                     f"then: python onboard.py --install-agent {row['id']}")
            stranded.append(row["id"])
            continue
        workspace = agent_install.deploy(adapter, binary, agent_install.current_values(row["id"]),
                                         ex=ex, rep=rep)
        if not ex.dry_run and not checks._mcp_auth_wired(adapter, row, workspace):
            rep.warn(f"Agent '{row['id']}' was redeployed but its MCP registration carries no "
                     f"token. Run: python onboard.py --install-agent {row['id']}")
            stranded.append(row["id"])
    return stranded


def _carry_state(previous, mode: str, ex) -> None:
    """Keep `onboard.py --status` truthful in this directory.

    .onboard-state.json lives per directory, so a freshly extracted release
    starts with none and would report an uninstalled system. Start from the
    previous install's file when this one has none, then mark the steps this
    upgrade re-ran.
    """
    from onboard import state as st

    current = st.load_state() if st.STATE_FILE.exists() else {}
    if not current and previous and Path(previous).resolve() != REPO_ROOT:
        old = Path(previous) / ".onboard-state.json"
        try:
            current = json.loads(old.read_text()) if old.exists() else {}
        except (OSError, json.JSONDecodeError):
            current = {}
    for key in UPGRADE_STEPS:
        st.mark_done(current, key)
    current["install_mode"] = mode
    ex.write_file(st.STATE_FILE, json.dumps(current, indent=2))


def _files_naming(root: Path, pattern: str, needle: str) -> tuple[list, list]:
    """Files under `root` matching `pattern` whose text contains `needle`, and
    the ones that could not be read (a root-owned leftover, say)."""
    found, unreadable = [], []
    if not root.is_dir():
        return found, unreadable
    for path in sorted(root.rglob(pattern)):
        try:
            if needle in path.read_text(errors="replace"):
                found.append(path)
        except OSError:
            unreadable.append(path)
    return found, unreadable


# The escapes a JavaScript string may hold in a module: \xHH, \uHHHH, \u{H…},
# a line continuation, \0 not followed by a digit, and any other character
# escaped as itself. Octal (\1–\7) and \8 \9 are errors in a module.
_ESCAPE = re.compile(r"\\(?:x([0-9a-fA-F]{2})|u\{([0-9a-fA-F]+)\}|u([0-9a-fA-F]{4})"
                     r"|(\r\n|[\r\n\u2028\u2029])|(0)(?![0-9])|([^xu0-9]))")
_SIMPLE_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_SOURCE_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")


def _cooked(raw: str) -> str | None:
    """The value of a string literal's body, or None when it holds an escape
    that is not valid in a module (and so cannot be decoded)."""
    if not re.fullmatch(r"(?:[^\\]|" + _ESCAPE.pattern + r")*", raw):
        return None

    def decode(m):
        hex_byte, code_point, code_unit, _continuation, nul, char = m.groups()
        if hex_byte or code_unit:
            return chr(int(hex_byte or code_unit, 16))
        if code_point:
            return chr(int(code_point, 16))  # ValueError past U+10FFFF
        if nul:
            return "\0"
        if char is not None:
            return _SIMPLE_ESCAPES.get(char, char)
        return ""
    try:
        return _ESCAPE.sub(decode, raw)
    except (ValueError, OverflowError):
        return None


def _names_giffx(spec: str) -> bool:
    """True when a decoded module specifier resolves to installed/GifFX.

    It is normalised (`./`, `//`, `a/../`, an extension) and the last two
    components compared. That is a superset of resolving it against the
    scene's own directory: no tsconfig or webpack alias exists, so the only way
    a scene reaches the component is a path ending in installed/GifFX. The
    comparison is case-sensitive, like module resolution on the Linux renderer
    (a differently cased import never resolved, so it was already failing)."""
    path = posixpath.normpath(spec)
    for ext in _SOURCE_EXTENSIONS:
        if path.endswith(ext):
            path = path[:-len(ext)]
            break
    return path.split("/")[-2:] == ["installed", "GifFX"]


# Words after which a "/" starts a regex and a "<" a JSX element, not division
# or less-than (after any other word, a number, ")", "]" or "}" they are
# operators).
_BEFORE_EXPRESSION = frozenset(("return", "typeof", "instanceof", "in", "of", "new", "delete",
                                "void", "throw", "case", "do", "else", "yield", "await"))
# The words that open a module path. JSX text holding none of them cannot
# import anything, so `_SceneScan._unplaced` skips lexing it.
_IMPORT_WORD = re.compile(r"\b(?:import|require|from)\b")
# What TSX reads as a generic arrow's type parameters, not a JSX tag: `<T,`,
# `<T =`, or `<T extends` followed by anything but `=`, `>` or `/` (the rule in
# TypeScript's parser; `const` may come first). A bare `<T>` is JSX in TSX.
# The name may start with any Unicode letter, as a tag may (`isalpha()`).
_GENERIC_HEAD = re.compile(r"<(?:const\s+)?(?:[^\W\d]|\$)[\w$]*(?![\w$])"
                           r"(?:\s*[,=]|\s+extends(?![\w$])\s*[^\s=>/])")


class _SceneScan:
    """One left-to-right pass over a scene's TSX that finds the module paths it
    really imports: `import … from "x"`, `import "x"`, `export … from "x"`,
    `import(…)` and `require(…)` in code — never inside a comment or a
    string, so a scene that keeps its old import as a note is not refused.

    A lexer, not a TypeScript parser, so it can misread odd code (code taken
    for JSX). Every misreading is bounded to err towards refusing: a quote or
    regex that does not close on its line is treated as an operator, so it
    never swallows the lines after it; a comment, template or attribute that
    never closes is not one, so what follows it is lexed as code; and JSX text
    is lexed as code too (`_unplaced`), so code misread as JSX hides nothing.
    The pass is linear: no scan is repeated, however the calls nest or the
    quotes stray."""

    def __init__(self, text: str):
        self.text = text
        self.i = 0
        # Where the lexer is: "code", or what the innermost open bracket
        # returns to — "{" (code), "${" (a template), "{jsx" (JSX), "tag" (a
        # JSX tag's attributes) or "children" (JSX text between tags).
        self.stack = ["code"]
        self.prev = None      # "value", a _BEFORE_EXPRESSION word or a punctuator
        self.pending = None   # "from", "import" or "require", awaiting its module path
        self.depth = 0        # open parentheses in code
        self.brackets = 0     # open square brackets in code, and the depths of
        self.members = []     # those opened right after require (`require["resolve"]`)
        # The import()/require() calls still open, each holding where its
        # argument starts in the running record below — so a token costs the
        # same however deeply calls nest.
        self.calls = []
        self.others = 0       # code tokens so far that are not literals
        self.parts = []       # the decoded literals met inside an open call ("" if undecodable)
        self.bad_at = -1      # the index in parts of the last undecodable one
        self.joined = 0       # the length of parts joined, its last 4 characters,
        self.tail = ""        # and where the last "GifFX" in it starts
        self.giffx_at = -1
        self.found = False
        self.undecodable = False
        self.cut_off = False  # the text ended inside an import()/require() call
        self.split = False    # a comment the text cut off followed a word awaiting its path
        # Per opener ("'", '"', "/"), the line end before which a scan already
        # found no closing one: the scan is not repeated, which keeps a line of
        # stray quotes linear.
        self.unclosed = {}
        # Where a "/*" or a template text was found to run to the end of the
        # file: any later one does too, so it is not searched again.
        self.open_comment = self.open_template = len(text)

    def result(self) -> bool | None:
        while self.i < len(self.text):
            top = self.stack[-1]
            if top == "tag":
                self._tag()
            elif top == "children":
                self._children()
            else:
                self._code()
        self.cut_off = bool(self.calls)
        while self.calls:  # an argument the file never closed is still judged
            self._finish(self.calls.pop())
        return True if self.found else (None if self.undecodable else False)

    def _unplaced(self, start: int, end: int):
        """Lexes JSX text (or a closing tag) as code, on its own, in case it was
        code the lexer took for JSX. A call the text cuts off (at a `{`) cannot
        be judged, so it refuses — and so does text that ends, or ends in a
        comment, while an import word still awaits its path or call: the "<"
        or "{" that ended it may sit inside a comment or a bracket key that
        the code goes on past. JSX text holds no "<" and a closing tag no
        ">", so this scan never reaches JSX text and never comes back here."""
        text = self.text[start:end]
        if _IMPORT_WORD.search(text):
            inner = _SceneScan(text)
            self.found = (self.found or inner.result() is True or inner.cut_off or inner.split
                          or bool(inner.members)
                          or inner.pending in ("import", "require", "require."))
            self.undecodable = self.undecodable or inner.undecodable

    def _module_path(self, raw: str):
        spec = _cooked(raw)
        if spec is None:
            self.undecodable = True
        elif _names_giffx(spec):
            self.found = True

    def _other(self, prev: str):
        """A code token that is not a literal: an import()/require() argument
        holding one is computed, not a single literal."""
        self.others += 1
        self.pending, self.prev = None, prev

    def _literal(self, raw: str, whole: bool = True):
        """A string literal's body, or a template's chunk (`whole` when the
        template has no substitution)."""
        if whole and self.pending:
            self._module_path(raw)
        if self.calls:
            cooked = _cooked(raw)
            if cooked is None:
                self.bad_at, cooked = len(self.parts), ""
            self.others += not whole  # a template with a substitution is computed
            window = self.tail + cooked
            if (at := window.rfind("GifFX")) >= 0:
                self.giffx_at = self.joined - len(self.tail) + at
            self.parts.append(cooked)
            self.joined += len(cooked)
            self.tail = window[-4:]
        self.pending, self.prev = None, "value"

    def _finish(self, call: dict):
        """A single literal argument is a module path like any other. A computed
        one (`"../../installed/" + "GifFX"`, a template with a substitution)
        is folded by webpack, or becomes a context over installed/ — so it
        refuses when its literal parts, joined, name GifFX."""
        if self.bad_at >= call["part"]:
            self.undecodable = True
        elif self.others == call["others"] and len(self.parts) - call["part"] == 1:
            self.found = self.found or _names_giffx(self.parts[-1])
        elif self.giffx_at >= call["joined"]:
            self.found = True

    def _code(self):
        t, i, n = self.text, self.i, len(self.text)
        c = t[i]
        after_value = self.prev == "value"
        if c.isspace():
            self.i += 1
        elif t.startswith("//", i):
            end = t.find("\n", i)
            self.split = self.split or (end < 0 and self.pending is not None)
            self.i = n if end < 0 else end
        elif t.startswith("/*", i):
            end = -1 if i >= self.open_comment else t.find("*/", i + 2)
            if end < 0:  # not a comment after all: what follows is code
                self.split = self.split or self.pending is not None
                self.open_comment = min(self.open_comment, i)
                self._other("/")
            self.i = i + 2 if end < 0 else end + 2
        elif c in "'\"":
            end = self._closing(i)
            if end is None:  # no closing quote on its line: not a string
                self._other(c)
                self.i = i + 1
            else:
                self._literal(t[i + 1:end - 1])
                self.i = end
        elif c == "`":
            self.i = i + 1
            self._template(first=True)
        elif c == "/" and not after_value and (end := self._closing(i)) is not None:
            self._other("value")
            self.i = end
        elif (c == "<" and not after_value and i + 1 < n
              and (t[i + 1].isalpha() or t[i + 1] in "_$>")
              and not _GENERIC_HEAD.match(t, i)):
            self._other("<")
            self.stack.append("children" if t[i + 1] == ">" else "tag")
            self.i = i + (2 if t[i + 1] == ">" else 1)
        elif c.isalnum() or c in "_$":
            j = i
            while j < n and (t[j].isalnum() or t[j] in "_$"):
                j += 1
            word = t[i:j]
            member = self.pending == "require."
            self._other(word if word in _BEFORE_EXPRESSION else "value")
            if word in ("from", "import", "require"):
                self.pending = word
            elif member and word in ("resolve", "resolveWeak"):
                self.pending = "require"  # webpack bundles what these name too
            self.i = j
        elif self.pending == "require" and (c == "." or t.startswith("?.", i)):
            # require.resolve(…), require?.(…): "require." awaits either
            self.pending, self.prev = "require.", "."
            self.i = i + (1 if c == "." else 2)
        elif c == "(":
            opens_call = self.pending in ("import", "require", "require.")
            self._other("(")
            if opens_call:
                self.calls.append({"depth": self.depth, "others": self.others,
                                   "part": len(self.parts), "joined": self.joined})
            self.depth += 1
            self.i = i + 1
        elif c == ")":
            self.depth = max(0, self.depth - 1)
            self.i = i + 1
            if self.calls and self.calls[-1]["depth"] == self.depth:
                self._finish(self.calls.pop())
            # `(require)(…)` is still require; any other ")" ends a value
            self.pending = "require" if self.pending == "require" else None
            self.prev = "value"
        elif c == "[":
            # require["resolve"](…): any key, literal or not, is carried like
            # `.resolve`, so the call it makes is judged (fail closed)
            if self.pending in ("require", "require."):
                self.members.append(self.brackets)
            self._other("[")
            self.brackets += 1
            self.i = i + 1
        elif c == "]":
            self.brackets = max(0, self.brackets - 1)
            self._other("]")
            if self.members and self.members[-1] == self.brackets:
                self.members.pop()
                self.pending = "require"
            self.i = i + 1
        elif c == "{":
            self._other("{")
            self.stack.append("{")
            self.i = i + 1
        elif c == "}":
            self._other("value")
            top = self.stack.pop() if len(self.stack) > 1 else "code"
            self.i = i + 1
            if top == "${":
                self._template(first=False)
        else:
            self._other(c)
            self.i = i + 1

    def _closing(self, i: int) -> int | None:
        """The index after the string or regex literal opened at i, or None
        when its line ends first."""
        t, c = self.text, self.text[i]
        if i < self.unclosed.get(c, -1):
            return None
        end = self._string_end(i) if c in "'\"" else self._regex_end(i)
        if end is None:
            line_end = t.find("\n", i)
            self.unclosed[c] = len(t) if line_end < 0 else line_end
        return end

    def _string_end(self, i: int) -> int | None:
        """The index after the quote closing the string opened at i, or None
        when the line ends first."""
        t, quote, j = self.text, self.text[i], i + 1
        while j < len(t):
            if t[j] == "\\":
                j += 3 if t.startswith("\r\n", j + 1) else 2
            elif t[j] == quote:
                return j + 1
            elif t[j] in "\r\n":
                return None
            else:
                j += 1
        return None

    def _regex_end(self, i: int) -> int | None:
        """The index after the regex literal opened at i and its flags, or None
        when the line ends first."""
        t, j, in_class = self.text, i + 1, False
        while j < len(t) and t[j] not in "\r\n":
            if t[j] == "\\":
                j += 1
            elif t[j] == "[":
                in_class = True
            elif t[j] == "]":
                in_class = False
            elif t[j] == "/" and not in_class:
                j += 1
                while j < len(t) and t[j].isalnum():
                    j += 1
                return j
            j += 1
        return None

    def _template(self, *, first: bool):
        """A template literal's text from self.i to its closing backtick, or to
        a `${`, whose closing `}` comes back here."""
        t, start, j = self.text, self.i, self.i
        while j < len(t) and start < self.open_template:
            if t[j] == "\\":
                j += 2
            elif t[j] == "`":
                self._literal(t[start:j], whole=first)
                self.i = j + 1
                return
            elif t.startswith("${", j):
                self._literal(t[start:j], whole=False)
                self._other("{")
                self.stack.append("${")
                self.i = j + 2
                return
            else:
                j += 1
        # It never closes, so it was not a template: what follows is code.
        self.open_template = min(self.open_template, start)
        self._other("`")

    def _tag(self):
        """Inside `<Name …>`: attribute names, quoted values (which may span
        lines and hold no escapes), `{…}` expressions, then `>` or `/>`."""
        t, i, n = self.text, self.i, len(self.text)
        c = t[i]
        if c.isspace() or c.isalnum() or c in "_$.:-=":
            self.i = i + 1
        elif c in "'\"":
            end = t.find(c, i + 1)
            if end < 0:  # a value that never closes: not a tag, back to code
                self.stack.pop()
                self.prev = "<"
            self.i = i + 1 if end < 0 else end + 1
        elif c == "{":
            self.stack.append("{jsx")
            self.prev = "{"
            self.i = i + 1
        elif t.startswith("/>", i):
            self.stack.pop()
            self.prev = "value"
            self.i = i + 2
        elif c == ">":
            self.stack[-1] = "children"
            self.i = i + 1
        else:  # not a JSX tag after all (a TSX generic like `<T,>`): back to code
            self.stack.pop()
            self.prev = "<"

    def _children(self):
        """JSX text up to the next tag or `{…}`. It is text, not code, so its
        quotes and slashes open nothing — but it is lexed as code on its own
        (`_unplaced`), in case it was code the lexer took for JSX."""
        t, i, n = self.text, self.i, len(self.text)
        j = i
        while j < n and t[j] not in "<{":
            j += 1
        self._unplaced(i, j)
        if j == n:
            self.i = n
            return
        if t[j] == "{":
            self.stack.append("{jsx")
            self.prev = "{"
            self.i = j + 1
            return
        k = j + 1
        while k < n and t[k].isspace():
            k += 1
        if k < n and t[k] == "/":  # a closing tag
            end = t.find(">", k)
            self._unplaced(k + 1, n if end < 0 else end)
            self.stack.pop()
            self.prev = "value"
            self.i = n if end < 0 else end + 1
        elif k < n and t[k] == ">":  # a fragment
            self.stack.append("children")
            self.i = k + 1
        else:
            self.stack.append("tag")
            self.i = j + 1


def _imports_giffx(text: str) -> bool | None:
    """True when a scene's TSX imports installed/GifFX; None when a module path
    holds an escape that cannot be decoded, so it cannot tell."""
    return _SceneScan(text).result()


def _giffx_scenes(root: Path) -> tuple[list, list, list]:
    """Generated scenes importing GifFX, the ones that could not be read, and
    the ones with a module path that could not be decoded."""
    found, unreadable, undecodable = [], [], []
    if not root.is_dir():
        return found, unreadable, undecodable
    for path in sorted(root.rglob("*.tsx")):
        try:
            imports = _imports_giffx(path.read_text(errors="replace"))
        except OSError:
            unreadable.append(path)
            continue
        if imports:
            found.append(path)
        elif imports is None:
            undecodable.append(path)
    return found, unreadable, undecodable


# The migration that makes OpenAI the only image provider (TMDEV-165). Old
# code still reads the image_provider row it deletes, so it must not run
# alongside new code — see the --no-stop refusal in run_upgrade.
OPENAI_ONLY_IMAGES_MIGRATION = 16


def _has_openai_key(db_path) -> bool:
    """Whether the settings table holds a non-blank OpenAI key.

    Read-only, and the database row only: the release compose file passes no
    keys through the environment, so the row is the only place a key can be.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT value FROM settings WHERE key = 'openai_api_key'").fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()
    return bool(row and row[0] and row[0].strip())


def _check_removed_giffx(data_root: Path, rep, *, configs: bool = True) -> bool:
    """False when a generated scene still imports the removed GifFX component,
    or one cannot be read or decoded to tell.

    The renderer bundles every generated scene together, so a single scene
    importing a component that no longer exists fails every render on the
    install, not just its own video. An unreadable scene fails the same way, so
    it refuses too. A scene-config that names GifFX only loses that overlay if
    the video is rendered again (the renderer skips a scene it cannot load), so
    it is a warning — given once, by the first of the two checks (`configs`)."""
    scenes, unreadable, undecodable = _giffx_scenes(data_root / "scenes" / "generated")
    if configs:
        named, unreadable_cfg = _files_naming(data_root / "jobs", "scene-config.json",
                                              '"GifFX"')
        for path in unreadable_cfg:
            rep.warn(f"Could not read {path} to check it for the removed GifFX component.")
        if named:
            rep.warn("These videos' scene-configs use GifFX, which this version removed. If "
                     "one is rendered again, that overlay is left out: "
                     + ", ".join(str(p) for p in named))
    if unreadable:
        rep.warn("These generated scenes cannot be read, so they cannot be checked for the "
                 "removed GifFX component — and the renderer could not compile them either. "
                 "Make them readable or delete them, then re-run this upgrade: "
                 + ", ".join(str(p) for p in unreadable))
    if undecodable:
        rep.warn("These generated scenes import a module path with an escape this upgrade "
                 "cannot decode, so it cannot tell whether they import the removed GifFX "
                 "component (TypeScript rejects that escape too). Write the path without the "
                 "escape or delete them, then re-run this upgrade: "
                 + ", ".join(str(p) for p in undecodable))
    if scenes:
        rep.warn("These generated scenes import GifFX, which this version removed. The renderer "
                 "compiles every generated scene together, so any one of them would fail every "
                 "render. Delete or fix them, then re-run this upgrade: "
                 + ", ".join(str(p) for p in scenes))
    return not (scenes or unreadable or undecodable)


def run_upgrade(*, dry_run: bool, force: bool, no_stop: bool, install_mode: str | None,
                db_path=None, lock_path=None, rep=None, ex=None, data_root=None) -> int:
    """The whole upgrade. Returns a process exit code."""
    from onboard import actions, checks, stack
    from onboard.config import DATA_ROOT, DB_PATH, OnboardConfig, resolve_install_mode
    from onboard.executor import Executor
    from onboard.plain import PlainReporter, console
    from onboard.state import load_state
    from tubematic_core import db as tdb

    db_path = Path(db_path) if db_path else DB_PATH
    data_root = Path(data_root) if data_root else DATA_ROOT
    rep = rep or PlainReporter(dry_run=dry_run)
    ex = ex or Executor(dry_run=dry_run, reporter=rep)
    mode = resolve_install_mode(install_mode, recorded=load_state().get("install_mode"))

    _section(f"Upgrade Tubematic — {mode} install{' (dry run)' if dry_run else ''}")
    if not db_path.exists():
        rep.warn(f"No Tubematic database at {db_path}. This command upgrades an existing "
                 "install; for a new one run: python onboard.py")
        return 1

    # An older version run against a database a newer one migrated would start
    # old code on a schema it may not understand — the rollback case, which
    # needs the matching backup restored first, not an "upgrade".
    try:
        applied = tdb.current_schema_version(db_path)
    except sqlite3.Error as e:
        rep.warn(f"Cannot read the database at {db_path}: {e}. Run as its owner.")
        return 1
    available = max((m.version for m in tdb.discover()), default=0)
    if applied > available:
        rep.warn(f"The database is at schema {applied:04d}, newer than this version understands "
                 f"({available:04d}). This install is older than the one that last ran. To go "
                 "back a version, follow Rollback policy in docs/user-guide/07-upgrading.md.")
        return 1

    # The dashboard has no way in without a password, and this command never
    # asks a question, so the operator sets one first. Safe to do on the old
    # version: it ignores the row (TMDEV-152).
    from tubematic_core import auth
    if not auth.has_admin_password(db_path):
        rep.warn("No dashboard password is set. From 2.0.0 the dashboard asks for one. "
                 "Set it first, from this directory, then re-run this upgrade: "
                 "python onboard.py --set-password")
        return 1
    # From 2.0.0 every scene image comes from OpenAI (TMDEV-165). Without a key
    # the upgrade would succeed and then fail every image — on a video whose
    # script a human already approved and whose voicing was already paid for.
    # Safe to add on the old version: every supported one has the key field.
    if not _has_openai_key(db_path):
        rep.warn("No OpenAI API key is stored. From 2.0.0 every scene image is generated by "
                 "OpenAI. Add the key on the dashboard first (Settings → API Keys), then "
                 "re-run this upgrade.")
        return 1
    if not _check_removed_giffx(data_root, rep):
        return 1
    missing_tokens = [n for n in auth.SECRET_NAMES
                      if not (auth.secrets_dir() / n).is_file()]
    if no_stop and missing_tokens:
        rep.warn("--no-stop is refused for this upgrade: it creates the service tokens, and "
                 "recreating containers one at a time would leave old and new ones refusing "
                 "each other's calls. Re-run without --no-stop.")
        return 1
    if no_stop and applied < OPENAI_ONLY_IMAGES_MIGRATION:
        rep.warn("--no-stop is refused for this upgrade: it retires the Gemini image provider, "
                 "and old containers recreated one at a time would keep reading a setting the "
                 "new database no longer has. Re-run without --no-stop.")
        return 1

    errors = [i for i in checks.check_prerequisites(mode=mode)
              if not i.ok and i.severity == "error"]
    for item in errors:
        rep.warn(f"{item.label} — {item.hint}" if item.hint else item.label)
    if errors and not dry_run:
        rep.info("Fix the above and re-run. See docs/user-guide/02-installing.md → Prerequisites.")
        return 1

    # Read before apply_cron rewrites it: the old line is the only record of
    # where the previous install lives.
    previous = stack.install_dir_of(stack.poll_cron_line(stack.read_crontab()))

    with stack.poll_lock(lock_path) as acquired:
        _section("Work in flight")
        if not stack.gate(db_path, lock_acquired=acquired, force=force, rep=rep):
            return 1
        try:
            cfg = OnboardConfig.load(db_path=db_path)
            cfg.values["install_mode"] = mode

            _section("Python dependencies")
            actions.apply_python_deps(cfg, ex, rep)

            _section("Images")
            _fetch_images(ex, rep, mode)

            _section("Stop")
            # Again: a long build is exactly when the worker can claim a
            # queued render, or the old MCP server can write a GifFX scene.
            # The new images stay; a re-run is quick.
            if not no_stop and not stack.gate(db_path, lock_acquired=acquired,
                                              force=force, rep=rep):
                rep.info("The new images are in place. Nothing was stopped — "
                         "re-run once the work above has finished.")
                return 1
            if not _check_removed_giffx(data_root, rep, configs=False):
                rep.info("The new images are in place. Nothing was stopped.")
                return 1
            if no_stop:
                rep.warn("--no-stop: containers are recreated one at a time, so old code "
                         "briefly runs against the upgraded database")
            else:
                stack.stop(ex, rep)

            _section("Start")
            # The gate has already passed twice and the poll lock is held, so a
            # volume reconcile taking the stack down needs no further question.
            stack.start(ex, rep, confirm_down=lambda names: True)

            _section("Cron")
            actions.apply_cron(cfg, ex, rep)

            _section("Agents")
            stranded = _redeploy_agents(ex, rep, db_path)

            _carry_state(previous, mode, ex)
        except RuntimeError as e:
            console.print(f"\n[red]Upgrade failed: {e}[/red]")
            console.print("[dim]Check the state with: python upgrade.py --check[/dim]\n")
            return 1

    _section("Result")
    healthy = True
    if dry_run:
        rep.info("[dry-run] nothing was changed")
    else:
        healthy = stack.report(rep, db_path=db_path, mode=mode)
    if stranded:
        rep.warn("These agents cannot reach the MCP server and will do nothing until fixed: "
                 + ", ".join(stranded))
        healthy = False
    if previous and Path(previous).resolve() != REPO_ROOT:
        rep.info(f"The previous install at {previous} is no longer used by cron"
                 + (" (once this runs for real)." if dry_run else
                    ". Remove it once you are satisfied with this one."))
    rep.info("Restart any open agent session: MCP tool schemas are read once, at session start.")
    return 0 if healthy else 1


def run_check(install_mode: str | None) -> int:
    from onboard import stack
    from onboard.config import resolve_install_mode
    from onboard.plain import PlainReporter
    from onboard.state import load_state

    mode = resolve_install_mode(install_mode, recorded=load_state().get("install_mode"))
    _section("Tubematic install check")
    rep = PlainReporter()
    healthy = stack.report(rep, mode=mode)
    _section("Authentication")
    return 0 if (_report_auth(rep) and healthy) else 1


def _report_auth(rep) -> bool:
    """The password, the tokens, a live MCP probe, and each agent's wiring (TMDEV-152)."""
    from onboard import agent_install, checks
    from onboard.config import DB_PATH, read_agents

    items = checks.auth_items(DB_PATH)
    refused, accepted = checks.mcp_auth_probe()
    if refused is None:
        rep.info("MCP server not reachable — its token check was not probed")
    else:
        items.append(checks.CheckItem("MCP refuses a request without the token", refused,
                                      hint="the running MCP server has no auth — re-run "
                                           "this upgrade"))
        items.append(checks.CheckItem("MCP accepts the install's token", bool(accepted),
                                      hint="docker compose restart tubematic-mcp"))
    for row in read_agents(DB_PATH):
        adapter = agent_install.ADAPTERS.get(row["id"])
        if row.get("archived_at") or adapter is None:
            continue
        workspace = Path(row.get("run_path") or "").expanduser()
        items.append(checks.CheckItem(
            f"Agent '{row['id']}': MCP token wired into its registration",
            checks._mcp_auth_wired(adapter, row, workspace),
            hint=f"python onboard.py --install-agent {row['id']}"))
    ok = True
    for item in items:
        if item.ok:
            rep.ok(item.label)
        else:
            rep.warn(f"{item.label} — {item.hint}" if item.hint else item.label)
            ok = ok and item.severity != "error"
    return ok


def main() -> None:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    install_mode = None
    rest = list(args)
    if "--install-mode" in rest:
        idx = rest.index("--install-mode")
        if idx + 1 >= len(rest) or rest[idx + 1] not in ("dev", "release"):
            print("\n  --install-mode requires one of: dev, release\n")
            sys.exit(1)
        install_mode = rest[idx + 1]
        del rest[idx:idx + 2]
    unknown = [a for a in rest if a not in FLAGS]
    if unknown:
        print(f"\n  Unknown option: {' '.join(unknown)}  (see --help)\n")
        sys.exit(1)

    _bootstrap()

    if "--check" in rest:
        sys.exit(run_check(install_mode))
    sys.exit(run_upgrade(dry_run="--dry-run" in rest, force="--force" in rest,
                         no_stop="--no-stop" in rest, install_mode=install_mode))


if __name__ == "__main__":
    main()
