"""The onboard wizard's console output layer — questionary for prompts (see
onboard/prompt.py), rich for everything printed around them. There is no
separate full-screen UI mode; this is the only interface.

`run_wizard` is the single entry point for a real run, a --dry-run preview,
or a --step/--force override. `print_status`/`print_steps` are separate,
pipeable, non-interactive report commands (`--status`/`--steps`).
"""
import textwrap

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from onboard.actions import ACTIONS
from onboard.checks import check_installation, check_prerequisites
from onboard.config import OnboardConfig, fields_for_step, read_agents, resolve_install_mode
from onboard.executor import Executor, Reporter
from onboard.state import is_done, load_state, mark_done, save_state
from onboard.steps import STEP_DEFS, STEP_BY_KEY

console = Console()

# Palette shared by the rich output here and, via these same hex values, by
# questionary's own ASK_STYLE in onboard/prompt.py — the wizard should read as
# one surface rather than a stack of differently-styled widgets (TMDEV-79).
# The questionary Style itself lives in prompt.py deliberately: --status and
# --steps import this module and are documented as pipeable non-interactive
# reports, so it must not start requiring the interactive prompt library.
MUTED = "#7b88a1"
BORDER = "#4c566a"
ACCENT = "#88c0d0"
OK = "#a3be8c"

PANEL_WIDTH = 88
BAR_WIDTH = 24


def _panel_width() -> int:
    return min(console.width, PANEL_WIDTH)


def open_field_frame(field, number: int, total: int) -> None:
    """Draw the top of a question's box: title bar, help text, progress.

    The box is *not* a rich Panel, because a Panel renders as a finished block
    and the thing that has to sit inside this one is a live questionary prompt
    that redraws itself. Instead the frame is opened here, the left rail is
    continued through the prompt by prompt.py's `│ ›` qmark, and
    close_field_frame draws the bottom edge once the answer is in.

    Mid-prompt the box is therefore open at the bottom (and a select's choice
    list spills past the rail, which prompt_toolkit gives no way to prefix).
    That resolves on its own: questionary collapses a finished prompt to a
    single line, so what persists in the scrolled-back transcript — the part
    the user actually re-reads — is one closed box per question.
    """
    width = _panel_width()
    title = " What's this for? "
    subtitle = f" question {number} of {total} "
    fill = max(1, width - 4 - len(title) - len(subtitle))
    top = Text("╭─", style=BORDER)
    top.append(title, style=f"bold {ACCENT}")
    top.append("─" * fill, style=BORDER)
    top.append(subtitle, style=MUTED)
    top.append("─╮", style=BORDER)

    console.print()
    console.print(top)
    if field.help:
        for line in textwrap.wrap(field.help, width=width - 6) or [""]:
            console.print(Text("│  ", style=BORDER) + Text(line, style="#b8c4d8"))
    console.print(Text("│", style=BORDER))

    filled = round(BAR_WIDTH * (number - 1) / total) if total else 0
    bar = Text("━" * filled, style=ACCENT) + Text("╸" * (BAR_WIDTH - filled), style=BORDER)
    console.print(Text("│  ", style=BORDER) + bar)
    console.print(Text("│", style=BORDER))


def close_field_frame() -> None:
    """Bottom edge, drawn once the question has been answered."""
    console.print(Text("╰" + "─" * (_panel_width() - 2) + "╯", style=BORDER))


def rail(msg: str, style: str = MUTED) -> None:
    """A line printed *inside* an open question box, on its left rail.

    Used by the few prompts that print their own context mid-question (the
    "already set" hint on a secret, the current voice roster) — without this
    they would break out of the frame.
    """
    console.print(Text("│  ", style=BORDER) + Text(msg, style=style))


def _display_answer(field, value: str) -> str:
    """One answer, rendered for the end-of-step summary.

    A `secret` field never shows its value — this line is printed to the
    terminal and scrolls in the user's history, so the mask is the whole point,
    not a nicety.
    """
    if field.kind == "secret":
        return "•••••• (set)" if value else "not set"
    if value is None or value == "":
        return "—"
    if field.kind == "voices":
        try:
            import json as _json
            entries = _json.loads(value)
            return ", ".join(f"{e['name']} ({e.get('model_id', '?')})"
                             for e in entries) if entries else "—"
        except Exception:
            return "—"
    if field.kind == "models":
        try:
            import json as _json
            models = _json.loads(value)
            return ", ".join(models) if models else "—"
        except Exception:
            return "—"
    if field.kind == "checkbox":
        try:
            import json as _json
            picked = _json.loads(value)
            return ", ".join(picked) if picked else "—"
        except Exception:
            return value
    return value


def render_step_summary(fields, values: dict) -> None:
    """What the step is about to apply, shown once after its last question."""
    if not fields:
        return
    table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    table.add_column(style=MUTED, no_wrap=False, max_width=44)
    table.add_column(style=f"bold {OK}")
    for f in fields:
        table.add_row(f.label, _display_answer(f, values.get(f.key, "")))
    console.print()
    console.print(Panel(
        table,
        title=f"[bold {OK}]Answers for this step[/]",
        border_style=BORDER,
        padding=(1, 2),
        width=_panel_width(),
    ))
    console.print()


class PlainReporter(Reporter):
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def ok(self, msg: str) -> None:
        # Actions call rep.ok() unconditionally, so a real "wrote the file"
        # and the dry-run branch that only recorded an intent are otherwise
        # indistinguishable — hedge here so a --dry-run run never reads as
        # a real one that succeeded.
        if self.dry_run:
            console.print(f"    [dim green]✔[/dim green]  (would) {msg}")
        else:
            console.print(f"    [green]✔[/green]  {msg}")

    def info(self, msg: str) -> None:
        console.print(f"    [blue]→[/blue]  {msg}")

    def warn(self, msg: str) -> None:
        console.print(f"    [yellow]![/yellow]  {msg}")

    def fail(self, msg: str, hint: str = "") -> None:
        console.print(f"    [red]✘[/red]  {msg}" + (f"  [dim]{hint}[/dim]" if hint else ""))
        raise RuntimeError(msg)

    def spinner(self, msg: str):
        label = f"(dry-run) {msg}" if self.dry_run else msg
        return console.status(f"[yellow]{label}[/yellow]", spinner="dots")


def print_status() -> None:
    """Step-done progress table. Pipeable/doc-referenced, so its output
    contract stays stable across UI rewrites."""
    state = load_state()
    total = len(STEP_DEFS)

    table = Table(box=None, show_header=False, padding=(0, 1), expand=False)
    table.add_column("glyph", no_wrap=True, width=1)
    table.add_column("step", no_wrap=True, style="dim", width=5)
    table.add_column("label")

    for idx, step in enumerate(STEP_DEFS, start=1):
        entry = state.get(step.key, {})
        if entry.get("done"):
            ts = entry.get("ts", "")
            glyph = "[green]✔[/green]"
            note = f"  [dim]done {ts}[/dim]" if ts else ""
            text = f"{step.label}{note}"
        else:
            glyph = "[yellow]○[/yellow]"
            text = step.label
        table.add_row(glyph, f"{idx}/{total}", text)

    console.print()
    console.print("[bold]  Onboard progress[/bold]")
    console.print()
    console.print(table)

    console.print()


def print_help() -> None:
    """Usage/options text for `--help`/`-h`."""
    console.print()
    console.print("[bold]Tubematic onboard wizard[/bold]")
    console.print()
    console.print("  A sequential setup wizard: each step's questions (if any) are asked")
    console.print("  right before that step's own action runs. Completed steps are")
    console.print("  skipped on re-runs. Container builds always run last.")
    console.print()
    console.print("[bold]Usage[/bold]")
    console.print("  python onboard.py [OPTIONS]")
    console.print()
    console.print("[bold]Options[/bold]")
    options = [
        ("(no flags)", "Run the wizard with the minimal question set"),
        ("--status", "Show step-done progress table and exit"),
        ("--steps", "List every step and exactly what it prompts for, then exit"),
        ("--step <key>", "(Re-)ask and (re-)apply just this one step, regardless of done state"),
        ("--install-agent <name>", "Install an agent (supported: claude, codex, opencode): checks its login, "
                                   "validates its models, deploys skills and commands. Re-run "
                                   "it to update — after skills change or the CLI is upgraded. "
                                   "Nothing runs until at least one agent is installed."),
        ("--uninstall-agent <name>", "Remove the skills, commands and MCP registration an "
                                     "install deployed, and mark the agent uninstalled. Its "
                                     "workspace and the shared poll logs are kept."),
        ("--list-agents", "List the supported agents and the installed ones, then exit"),
        ("--set-password", "Set or change the dashboard password. Changing it signs every "
                           "dashboard session out. Run it before upgrading from 1.2.x."),
        ("--rotate-tokens", "Replace the three service tokens, restart the services that "
                            "read them, and have OpenCode reload. Waits for in-flight work "
                            "like upgrade.py; --force proceeds anyway."),
        ("--force", "Re-run every step regardless of done state"),
        ("--install-mode <dev|release>", "Override the auto-detected install mode. Auto-detect "
                                         "picks release when renderer/Dockerfile is absent (a "
                                         "release tarball ships no source trees) and dev "
                                         "otherwise. Release installs pull container images "
                                         "instead of building them and don't require Node/npx."),
        ("--allow-skipping", "Let required settings (the ElevenLabs and OpenAI keys) be left "
                             "blank at the prompt. Without it the wizard re-asks "
                             "until they are supplied, since the pipeline cannot run without "
                             "them. The OpenAI key is still needed for the install "
                             "configuration step to finish."),
        ("--disable-verification", "Don't check API keys against their provider as they are "
                                   "typed. A malformed paste is still rejected locally."),
        ("--full-questionnaire", "Ask every question. By default the wizard asks only the "
                                 "questions a first install has to answer and uses defaults for "
                                 "the rest — all editable later on the Settings dashboard. "
                                 "Combines with --step to get one step's full set, and with "
                                 "--install-agent to be asked that agent's effort level."),
        ("--dry-run", "Ask the same questions, but apply nothing — no files written, "
                       "no containers built or started. Prerequisite failures warn instead of "
                       "blocking."),
        ("--help, -h", "Show this message and exit"),
    ]
    for flag, desc in options:
        console.print(f"  [cyan]{flag:<23}[/cyan] {desc}")
    console.print()
    console.print("[bold]Step keys[/bold] [dim](for --step)[/dim]")
    console.print("  " + ", ".join(step.key for step in STEP_DEFS))
    console.print()
    console.print("[bold]Examples[/bold]")
    for example in [
        "python onboard.py",
        "python onboard.py --dry-run",
        "python onboard.py --status",
        "python onboard.py --steps",
        "python onboard.py --step install_config",
        "python onboard.py --full-questionnaire",
        "python onboard.py --step pipeline_settings --force",
        "python onboard.py --install-agent <agent>",
        "python onboard.py --list-agents",
        "python onboard.py --uninstall-agent <agent>",
    ]:
        console.print(f"  [dim]$[/dim] {example}")
    console.print()


def _print_step_detail(step, heading: str) -> None:
    console.print()
    console.print(f"[bold]  {heading}[/bold] — {step.label}")
    console.print(f"     [dim]{step.description}[/dim]")
    if step.builds_or_starts:
        console.print("     [yellow]builds/starts containers[/yellow]")
    # full=True: this lists what a step *can* ask, so it must not depend
    # on which questionnaire a later run happens to use. Advanced fields
    # are marked instead of hidden, keeping this output honest about
    # "exactly what it prompts for" under both modes.
    prompts = fields_for_step(step.key, full=True)
    if not prompts:
        console.print("     [dim](no prompts — action only)[/dim]")
    for f in prompts:
        choice_note = f"  choices: {', '.join(f.choices)}" if f.choices else ""
        adv_note = " — advanced, only with --full-questionnaire" if f.advanced else ""
        cond_note = " — only if the workspace already exists" if f.condition else ""
        console.print(
            f"     • {f.label}  [dim]({f.kind}){choice_note}{adv_note}{cond_note}[/dim]"
        )
    if step.consumes:
        console.print(f"     [dim]also reads: {', '.join(step.consumes)}[/dim]")


def print_steps() -> None:
    """Every step and exactly what it contains — the prompts/options in it."""
    console.print()
    console.print("[bold]  Onboard steps[/bold]")
    for idx, step in enumerate(STEP_DEFS, start=1):
        _print_step_detail(step, f"{idx}. {step.key}")
    console.print()


def print_prereq(dry_run: bool, mode: str = "dev") -> bool:
    """Print prerequisite results. Returns whether it's safe to proceed —
    a real run blocks on any error; --dry-run only warns, since the point
    of --dry-run is previewing the wizard even on a machine that isn't
    fully set up yet."""
    console.print()
    console.print("[bold]Prerequisites[/bold]")
    errors = 0
    for item in check_prerequisites(mode=mode):
        if item.ok:
            console.print(f"  [green]✔[/green]  {item.label}")
        elif item.severity == "warning":
            console.print(f"  [yellow]![/yellow]  {item.label}" + (f"  [dim]{item.hint}[/dim]" if item.hint else ""))
        else:
            errors += 1
            console.print(f"  [red]✘[/red]  {item.label}" + (f"  [dim]{item.hint}[/dim]" if item.hint else ""))
    if errors and not dry_run:
        console.print(f"\n[red]{errors} blocking issue(s) — fix and re-run.[/red]\n")
        return False
    if errors and dry_run:
        console.print(f"\n[yellow]{errors} issue(s) would block a real run — continuing anyway under --dry-run.[/yellow]")
    return True


def print_verify() -> None:
    console.print()
    console.print("[bold]Installation check[/bold]")
    result = check_installation()
    failed = 0
    for group, items in result.items():
        console.print(f"[bold]{group}[/bold]")
        for item in items:
            if item.ok:
                glyph, style = "✔", "green"
            else:
                glyph, style = "!", "yellow"
                if item.severity == "error":
                    failed += 1
            hint = f"  [dim]← {item.hint}[/dim]" if item.hint and not item.ok else ""
            console.print(f"  [{style}]{glyph}[/{style}]  {item.label}{hint}")
    console.print()
    if failed:
        console.print(f"[yellow]{failed} check(s) need attention — see hints above.[/yellow]\n")
    else:
        console.print("[green]All checks passed.[/green]\n")


def run_wizard(*, dry_run: bool = False, force_all: bool = False, step_key: str | None = None,
               full_questionnaire: bool = False, allow_skipping: bool = False,
               verify_keys: bool = True, install_mode: str | None = None) -> None:
    """The interactive wizard — also the --dry-run preview. Iterates steps
    in order; a step already marked done is skipped unless --force (all
    steps) or --step (this one specifically) target it. A not-skipped
    step's questions (onboard/prompt.py, via config.py's fields_for_step)
    are asked immediately before its own action runs — no separate
    collect-everything-then-apply phase, so builds land last only because
    `renderer`/`dashboard` are last in STEP_DEFS and have no prompts of
    their own (see onboard/steps.py).

    `install_mode` is the --install-mode CLI override, or None to
    auto-detect (dev checkout vs. release tarball — TMDEV-91 Phase 2). The
    resolved mode is reported here and stashed on cfg.values so every
    apply_* action agrees on it, then recorded in .onboard-state.json so a
    later run (and "why didn't it rebuild?") can be answered from disk.
    """
    # Deferred: prompt.py imports `console` from this module.
    from onboard.prompt import PromptOptions, prompt_step
    opts = PromptOptions(allow_skipping=allow_skipping, verify_keys=verify_keys)

    state = load_state()
    mode = resolve_install_mode(install_mode, recorded=state.get("install_mode"))
    console.print()
    if install_mode:
        detected = " (--install-mode)"
    elif not install_mode and state.get("install_mode") == mode:
        detected = " (recorded from a previous run)"
    else:
        detected = " (auto-detected)"
    console.print(f"[bold]Install mode:[/bold] {mode}{detected}")
    if mode == "release":
        console.print("  [dim]Release install — containers are pulled, not built.[/dim]")

    if not print_prereq(dry_run, mode):
        return

    if not verify_keys:
        console.print()
        console.print("  [yellow]![/yellow]  [dim]--disable-verification: API keys are stored as "
                      "typed, without being checked against their provider.[/dim]")
    if allow_skipping:
        console.print()
        console.print("  [yellow]![/yellow]  [dim]--allow-skipping: required settings may be left "
                      "blank. The install may not be able to voice or render.[/dim]")

    cfg = OnboardConfig.load()
    cfg.values["install_mode"] = mode
    state["install_mode"] = mode
    if not dry_run:
        save_state(state)
    steps = [STEP_BY_KEY[step_key]] if step_key else STEP_DEFS
    total = len(steps)
    targeted = step_key is not None

    if not full_questionnaire:
        # Counted over the steps this invocation will actually run, not over
        # the whole field registry: with --step X only that step's questions
        # are in play, and on-demand steps aren't in play at all (TMDEV-79).
        skipped = sum(
            len(fields_for_step(s.key, full=True)) - len(fields_for_step(s.key))
            for s in steps
        )
        if skipped:
            console.print()
            console.print(
                f"  [dim]Minimal questionnaire — {skipped} further setting(s) use their defaults "
                "and are editable later on the Settings dashboard.[/dim]"
            )
            console.print("  [dim]Re-run with --full-questionnaire to be asked all of them.[/dim]")

    rep = PlainReporter(dry_run=dry_run)
    ex = Executor(dry_run=dry_run, reporter=rep)

    for idx, step in enumerate(steps, start=1):
        done = is_done(state, step.key)
        if done and not force_all and not targeted:
            console.print(f"  [dim][{idx}/{total}] {step.label}  ✔ skipped (already done)[/dim]")
            continue

        console.print()
        console.print(Rule(f"[bold] [{idx}/{total}] {step.label} [/bold]", style="blue"))
        try:
            prompt_step(step, cfg, full=full_questionnaire, opts=opts)
        except SystemExit:
            console.print("\n[dim]Onboard cancelled.[/dim]\n")
            return

        if step.key == "prerequisites":
            # Already checked (and, under --dry-run, already downgraded to
            # warnings) by print_prereq above — running apply_prerequisites
            # here too would both duplicate that output and hard-fail on
            # the same errors print_prereq just decided to let through.
            pass
        else:
            try:
                ACTIONS[step.key](cfg, ex, rep)
            except Exception as e:
                console.print(f"[red]{step.label} failed: {e}[/red]")
                return

        if not dry_run:
            mark_done(state, step.key)
            save_state(state)

    print_verify()
    if not any(not a.get("archived_at") for a in read_agents()):
        # The project is set up, but cron has nothing to run yet: every tick
        # will log "No agent installed" until this is done.
        console.print("[bold]Next:[/bold] install an agent — nothing runs until one exists:")
        console.print("  [cyan]python onboard.py --install-agent <agent>[/cyan]\n")
