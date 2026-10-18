"""questionary-driven interactive prompting.

A step's questions (onboard/config.py's `fields_for_step`) are asked once,
immediately before that step's action runs — see `run_wizard` in
onboard/plain.py. There is no separate "collect everything, then apply"
phase (see onboard/config.py's `OnboardConfig` docstring for why that's
deliberate), so this module only needs to turn one Field into one
questionary prompt and read the answer back.
"""
import json
from dataclasses import dataclass
from functools import partial

import questionary
from questionary import Style

from onboard import api_keys
from onboard.config import (
    DEFAULT_DICTIONARY_MODEL, DICTIONARY_COMPATIBLE_MODELS,
    Field, MAX_VOICES, _agent_model, _parse_voices, fields_for_step,
)
from onboard.executor import Reporter
from onboard.plain import (
    MUTED as MUTED_HINT, close_field_frame, console, open_field_frame, rail,
    render_step_summary,
)


# Kept here rather than in plain.py so that --status/--steps, which import
# plain.py, stay free of the interactive prompt library. The hex values mirror
# plain.py's rich palette so the panels and the prompts match (TMDEV-79).
ASK_STYLE = Style([
    ("qmark",       "fg:#88c0d0 bold"),
    ("question",    "fg:#eceff4 bold"),
    ("answer",      "fg:#a3be8c bold"),
    ("pointer",     "fg:#88c0d0 bold"),
    ("highlighted", "fg:#88c0d0 bold"),
    ("selected",    "fg:#a3be8c"),
    ("separator",   "fg:#4c566a"),
    ("instruction", "fg:#7b88a1 italic"),
    ("text",        "fg:#d8dee9"),
    ("disabled",    "fg:#4c566a italic"),
])

# The question line is rendered inside an open box (onboard/plain.py's
# open_field_frame), so the qmark carries the left rail. questionary offers no
# other hook for prefixing the line it draws.
QMARK = "│ ›"
POINTER = "❯"


@dataclass(frozen=True)
class PromptOptions:
    """Per-run switches that change how a question is asked, not what is asked.

    Passed down explicitly rather than read from module state so the enforcement
    below stays unit-testable without a terminal.
    """
    # --allow-skipping: accept blank for a `required` field, i.e. the pre-TMDEV-80
    # behaviour. The escape hatch for someone who cannot supply a key yet. The
    # OpenAI key stays required regardless: apply_install_config refuses to
    # finish without it (TMDEV-165).
    allow_skipping: bool = False
    # --disable-verification: don't probe keys against their provider. Local
    # malformed-paste rejection stays on — that guards what gets *stored* and is
    # not a network check.
    verify_keys: bool = True


DEFAULT_PROMPT_OPTIONS = PromptOptions()


def _skipped_check(_key: str) -> api_keys.KeyCheck:
    """Stand-in checker used by --disable-verification.

    Returning UNKNOWN rather than bypassing resolve_secret entirely keeps the
    malformed-paste guard (trailing newline, non-ASCII) running, since that is
    about the value being storable at all, not about the provider accepting it.
    """
    return api_keys.KeyCheck(
        api_keys.UNKNOWN,
        "Verification disabled (--disable-verification) — stored as typed.",
    )

# Key hints, per prompt kind. questionary renders these next to the question,
# so they document controls that are otherwise invisible. The repeat-until-blank
# "voices" kind is absent on purpose: ask_field loops and issues a fresh
# questionary.text per entry, so an instruction there would repeat on every
# line — its explanation lives in the field's help panel instead.
HINTS = {
    "select":   "(↑↓ to move, enter to confirm)",
    "checkbox": "(↑↓ to move, space to toggle, enter to confirm)",
    "text":     "(type your answer, enter to confirm)",
    "int":      "(a number, enter to confirm)",
}
SECRET_HINT_SET = "(enter to keep the current value)"
SECRET_HINT_UNSET = "(paste the key, or enter to leave it unset)"
SECRET_HINT_REQUIRED = "(required — paste the key)"


class _PreviewReporter(Reporter):
    """Prints via the same rich console/glyph style as everywhere else, for
    the read-only workspace preview below — not routed through the
    Apply-phase Executor, since nothing here mutates anything."""

    def ok(self, msg: str) -> None:
        console.print(f"  [green]✔[/green]  {msg}")

    def info(self, msg: str) -> None:
        console.print(f"  [blue]→[/blue]  {msg}")

    def warn(self, msg: str) -> None:
        console.print(f"  [yellow]![/yellow]  {msg}")

    def fail(self, msg: str, hint: str = "") -> None:
        raise RuntimeError(msg)


def _adapt_validator(fn):
    if fn is None:
        return None

    def _validate(value: str):
        err = fn(value)
        return True if err is None else err

    return _validate


def _report_key_check(status: str, detail: str, *, may_leave_blank: bool) -> None:
    """One line per validation attempt, in the same glyph vocabulary as the
    rest of the wizard. `detail` is the provider's own wording (or a fixed
    string where the provider's would echo key material) — never the key.

    `may_leave_blank` keeps the rejection hint honest. Blank input on a secret
    means "keep the current value", so it is only a way *out* of the retry
    loop when there is no current value to keep — otherwise Ctrl-C is the only
    exit, and saying otherwise would send the user in circles.
    """
    if status == api_keys.VALID:
        rail("✔  Key verified.", style="#a3be8c")
    elif status == api_keys.UNKNOWN:
        rail(f"!  {detail}", style="#ebcb8b")
    else:
        rail(f"✘  {detail}", style="#bf616a")
        blank = "blank to leave it unset, or " if may_leave_blank else ""
        rail(f"Enter a working key, {blank}Ctrl-C to abort onboarding.")


def _require_or_retry(f: Field, opts: "PromptOptions") -> bool:
    """Whether a blank answer to `f` must be re-asked. Prints the reason."""
    if not f.required or opts.allow_skipping:
        return False
    rail("Required — the pipeline cannot run without this.", style="#bf616a")
    rail("Re-run with --allow-skipping to leave it unset.", style=MUTED_HINT)
    return True


def ask_field(f: Field, current_value: str, all_values: dict,
              opts: "PromptOptions" = DEFAULT_PROMPT_OPTIONS) -> str:
    """Ask one question, returning the answer (or the current value if the
    user just hits Enter on a field that supports that shorthand)."""
    if f.kind == "secret":
        def _ask() -> str:
            if current_value:
                rail("Already set — press Enter to keep, or type to replace.")
            if current_value:
                hint = SECRET_HINT_SET
            elif f.required and not opts.allow_skipping:
                hint = SECRET_HINT_REQUIRED
            else:
                hint = SECRET_HINT_UNSET
            val = questionary.password(
                f"{f.label}:", instruction=hint, style=ASK_STYLE, qmark=QMARK,
            ).ask()
            if val is None:
                raise SystemExit(0)
            return val if val else current_value

        def _checked(key: str) -> api_keys.KeyCheck:
            if not opts.verify_keys:
                return _skipped_check(key)
            # The key never reaches the spinner text — only the field label.
            with console.status(f"[yellow]Verifying {f.label}…[/yellow]", spinner="dots"):
                return f.key_check(key)

        # A rejected key is a hard gate: resolve_secret re-asks until the
        # service stops rejecting it. Everything the service does not
        # positively reject — a timeout, a 5xx, an unrecognised status — comes
        # back UNKNOWN and is accepted with a warning, so an offline install
        # still completes. The outer loop is the separate `required` gate: a
        # *blank* answer never reaches the network at all (resolve_secret
        # returns it untouched), so blankness has to be caught out here.
        may_blank = not current_value and not (f.required and not opts.allow_skipping)
        report = partial(_report_key_check, may_leave_blank=may_blank)
        while True:
            val = _ask()
            if f.key_check is not None:
                val = api_keys.resolve_secret(_checked, val, _ask, report)
            if val or not _require_or_retry(f, opts):
                return val

    if f.kind == "select":
        choices = f.dynamic_choices(all_values) if f.dynamic_choices else f.choices
        if not choices:
            # dynamic_choices can legitimately come back empty (e.g. no
            # voices were entered) — nothing to pick from, so skip the
            # prompt rather than handing questionary an empty list.
            return ""
        default = current_value if current_value in choices else (choices[0] if choices else None)
        val = questionary.select(
            f"{f.label}:", choices=choices, default=default,
            instruction=HINTS["select"], style=ASK_STYLE, qmark=QMARK, pointer=POINTER,
        ).ask()
        if val is None:
            raise SystemExit(0)
        return val

    if f.kind == "checkbox":
        try:
            selected = set(json.loads(current_value)) if current_value else set()
        except (json.JSONDecodeError, TypeError):
            selected = set()
        # Not `opts` — that name is the PromptOptions parameter.
        boxes = [questionary.Choice(c, checked=c in selected) for c in f.choices]
        val = questionary.checkbox(
            f"{f.label}:", choices=boxes,
            instruction=HINTS["checkbox"], style=ASK_STYLE, qmark=QMARK, pointer=POINTER,
        ).ask()
        if val is None:
            raise SystemExit(0)
        return json.dumps(val)

    if f.kind == "voices":
        # Repeat-until-blank name+id entry, capped at MAX_VOICES — one
        # {name, voice_id} pair per entry. Re-running this step
        # must not silently wipe a roster the dashboard has since grown or
        # edited (same clobber this field's design was built to avoid on the
        # default-voice setting), so a blank first answer keeps the existing
        # roster unchanged instead of clearing it — entering at least one
        # voice replaces the list wholesale (add/edit/remove afterwards is
        # the dashboard's job, not this prompt's).
        while True:
            result = _ask_voices(current_value)
            if result is not None:
                return result
            if not _require_or_retry(f, opts):
                return "[]"

    if f.kind == "models":
        # An agent's model list (--install-agent). Repeat-until-blank like the
        # voice roster, but every entry is probed against the installed agent
        # CLI (f.key_check) before it is kept: the dashboard offers this list
        # as-is and the API rejects anything outside it, so an unchecked name
        # would surface only hours later, as a cron tick that does nothing.
        while True:
            result = _ask_models(f, current_value, all_values, opts)
            if result is not None:
                return result
            if not _require_or_retry(f, opts):
                return "[]"

    # text / int
    val = questionary.text(
        f"{f.label}:", default=current_value, validate=_adapt_validator(f.validator),
        instruction=HINTS.get(f.kind, HINTS["text"]), style=ASK_STYLE, qmark=QMARK,
    ).ask()
    if val is None:
        raise SystemExit(0)
    return val


def _ask_voices(current_value: str) -> str | None:
    """One pass of the roster prompt.

    None means "nothing was entered and there was no existing roster to keep";
    the caller decides whether that is acceptable or has to be re-asked.
    """
    existing = _parse_voices(current_value)
    if existing:
        rail("Current voices:")
        for ev in existing:
            rail(f"  - {ev['name']} ({ev['voice_id']}, {ev['model_id']})")
    voices = []
    while len(voices) < MAX_VOICES:
        finish_hint = "keep the list above unchanged" if not voices and existing else "finish"
        name = questionary.text(
            f"  Voice #{len(voices) + 1} name (or Enter to {finish_hint}):",
            style=ASK_STYLE, qmark=QMARK,
        ).ask()
        if name is None:
            raise SystemExit(0)
        if not name:
            break
        voice_id = questionary.text(
            f"  Voice #{len(voices) + 1} ElevenLabs ID:", style=ASK_STYLE, qmark=QMARK,
        ).ask()
        if voice_id is None:
            raise SystemExit(0)
        if not voice_id:
            rail("Empty voice ID — skipping this entry.", style="#ebcb8b")
            continue
        # The model follows the voice (TMDEV-121). Default to what this voice
        # already had, else the previous voice's model, so a roster on one
        # model is a string of Enters.
        known = {ev["voice_id"]: ev["model_id"] for ev in existing}
        default_model = known.get(voice_id) or (voices[-1]["model_id"] if voices
                                                else DEFAULT_DICTIONARY_MODEL)
        model_id = questionary.select(
            f"  Voice #{len(voices) + 1} ElevenLabs model:",
            choices=DICTIONARY_COMPATIBLE_MODELS, default=default_model,
            instruction=HINTS["select"], style=ASK_STYLE, qmark=QMARK, pointer=POINTER,
        ).ask()
        if model_id is None:
            raise SystemExit(0)
        voices.append({"name": name, "voice_id": voice_id, "model_id": model_id})
    if not voices:
        return current_value if existing else None
    return json.dumps(voices)


def _parse_models(raw: str | None) -> list:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [m for m in parsed if isinstance(m, str) and m.strip()]


def _model_ok(model: str, check) -> bool:
    """Run the model probe, if any, and report it on the rail. Only a positive
    rejection drops a model — an unverifiable one is kept with a warning, the
    same rule resolve_secret applies to API keys."""
    if check is None:
        return True
    with console.status(f"[yellow]Checking {model}…[/yellow]", spinner="dots"):
        result = check(model)
    if result.status == api_keys.INVALID:
        rail(f"✘  {result.detail}", style="#bf616a")
        return False
    if result.status == api_keys.UNKNOWN:
        rail(f"!  {result.detail}", style="#ebcb8b")
        return True
    rail(f"✔  {result.detail or model + ' verified.'}", style="#a3be8c")
    return True


def _ask_models(f: Field, current_value: str, all_values: dict,
                opts: "PromptOptions") -> str | None:
    """One pass of the model-list prompt.

    None means nothing usable was entered and no stored list survived, so the
    caller decides whether to re-ask. Suggestions come from f.dynamic_choices;
    with none, the prompt is plain free text — suggestions help, they never
    gate what can be typed.
    """
    existing = _parse_models(current_value)
    choices = f.dynamic_choices(all_values) if f.dynamic_choices else []
    check = f.key_check if (opts.verify_keys and f.key_check is not None) else None
    if existing:
        rail("Current models (the first is the default): " + ", ".join(existing))
    models: list = []
    while True:
        finish = "keep the list above" if not models and existing else "finish"
        label = f"  Model #{len(models) + 1} (or Enter to {finish}):"
        if choices:
            val = questionary.autocomplete(label, choices=choices, style=ASK_STYLE,
                                           qmark=QMARK).ask()
        else:
            val = questionary.text(label, style=ASK_STYLE, qmark=QMARK).ask()
        if val is None:
            raise SystemExit(0)
        val = val.strip()
        if not val:
            break
        shape_error = _agent_model(val)
        if shape_error:
            rail(f"✘  {shape_error}", style="#bf616a")
            continue
        if val in models:
            rail("Already in the list.", style="#ebcb8b")
            continue
        if _model_ok(val, check):
            models.append(val)
    if models:
        return json.dumps(models)
    if not existing:
        return None
    # Keeping the stored list still re-checks it. Validation is point-in-time,
    # and re-running --install-agent after a CLI upgrade is how a model the CLI
    # has since retired gets dropped instead of silently carried forward.
    kept = [m for m in existing if _model_ok(m, check)]
    return json.dumps(kept) if kept else None


def prompt_step(step, cfg, *, full: bool = False,
                opts: PromptOptions = DEFAULT_PROMPT_OPTIONS) -> None:
    """Ask every question this step owns (onboard/config.py's
    fields_for_step), writing answers straight into cfg.values.

    `full` is --full-questionnaire: False (the default) asks only the minimal
    set and leaves every `advanced` field on the value load_current_values()
    already pre-filled (TMDEV-74).
    """
    # Conditions are evaluated per field, as each one is reached, NOT once up
    # front — so `values=None` here is deliberate. A field gated on an answer
    # given earlier in this same step (POSTFORME_API_KEY on PUBLISHING_ENABLED)
    # would otherwise be filtered out before that answer exists, and the
    # question would silently never be asked.
    prompt_fields(fields_for_step(step.key, full=full), cfg, opts=opts)


def prompt_fields(candidates: list, cfg, *, opts: PromptOptions = DEFAULT_PROMPT_OPTIONS,
                  before_field=None) -> None:
    """Ask `candidates` in order, each in its own frame, skipping any whose
    condition does not hold at the moment it is reached.

    `before_field(field)` runs just before a field's frame opens, for context
    a question needs — --install-agent uses it to preview an existing
    workspace before asking whether to wipe it.
    """
    if not candidates:
        return

    def _wanted(field) -> bool:
        return field.condition is None or field.condition(cfg.values)

    asked = []
    for index, f in enumerate(candidates):
        if not _wanted(f):
            continue
        if before_field is not None:
            before_field(f)
        asked.append(f)
        # The denominator counts what is asked so far plus what still looks
        # like it will be asked, recomputed each time. Answering a gate can
        # therefore add a question mid-step — the count grows by one rather
        # than leaving a gap, which is the honest rendering of "you enabled a
        # feature that needs one more answer".
        total = len(asked) + sum(1 for later in candidates[index + 1:] if _wanted(later))
        open_field_frame(f, len(asked), total)
        try:
            cfg.values[f.key] = ask_field(
                f, cfg.values.get(f.key, f.default), cfg.values, opts)
        finally:
            # Also on Ctrl-C (ask_field raises SystemExit): an abandoned run
            # should not leave a half-drawn box as its last output.
            close_field_frame()

    # Only what was actually asked: the summary prints to scrollback, and
    # listing a skipped field would claim an answer nobody gave.
    render_step_summary(asked, cfg.values)


def ask_new_password() -> str:
    """The dashboard password, asked twice and hidden (TMDEV-152).

    Re-asks until the two entries match and the password is long enough,
    rather than storing a typo nobody can log in with. Cancel exits.
    """
    from tubematic_core.auth import MIN_PASSWORD_LEN, check_password_strength
    while True:
        first = questionary.password(
            "Dashboard password:", instruction=f"(at least {MIN_PASSWORD_LEN} characters)",
            style=ASK_STYLE, qmark=QMARK,
        ).ask()
        if first is None:
            raise SystemExit(0)
        try:
            check_password_strength(first)
        except ValueError as e:
            rail(f"{e}.", style="#bf616a")
            continue
        again = questionary.password("Repeat it:", style=ASK_STYLE, qmark=QMARK).ask()
        if again is None:
            raise SystemExit(0)
        if again != first:
            rail("The two entries differ — try again.", style="#bf616a")
            continue
        return first
