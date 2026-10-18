"""onboard/plain.py regression tests.

Covers two real bugs a code review caught in the questionary-pivot rewrite:
1. print_steps() used to render step.consumes (descriptive-only metadata)
   as if it were the actual prompt list, badly overcounting/undercounting
   real prompts for several steps.
2. run_wizard(dry_run=True) used to hard-abort on a blocking prerequisite
   error even though print_prereq() had just decided to continue anyway —
   apply_prerequisites() re-checked the same items and called rep.fail(),
   which raises regardless of dry_run.
"""
import io
from unittest.mock import patch

from rich.console import Console

from onboard.checks import CheckItem
from onboard.config import fields_for_step
from onboard.steps import STEP_DEFS


def _captured_steps_output():
    buf = io.StringIO()
    with patch("onboard.plain.console", Console(file=buf, width=200)):
        from onboard.plain import print_steps
        print_steps()
    return buf.getvalue()


def test_print_steps_prompt_bullets_match_fields_for_step():
    output = _captured_steps_output()
    blocks = output.split("\n\n")
    for step in STEP_DEFS:
        block = next(b for b in blocks if f". {step.key} —" in b)
        # print_steps lists everything a step *can* ask, marking the
        # advanced ones — hence full=True (TMDEV-74).
        expected = fields_for_step(step.key, full=True)
        bullet_lines = [ln for ln in block.splitlines() if ln.strip().startswith("•")]
        assert len(bullet_lines) == len(expected), (
            f"{step.key}: expected {len(expected)} prompts, rendered {len(bullet_lines)}"
        )
        if expected:
            assert "(no prompts — action only)" not in block
        else:
            assert "(no prompts — action only)" in block


def test_run_wizard_dry_run_survives_hard_prerequisite_failure():
    """A machine failing a hard prerequisite (e.g. Docker not installed)
    must still let --dry-run walk the wizard, per print_prereq's own
    docstring and INSTALL.md/USAGE.md's documented --dry-run behavior."""
    hard_failure = [CheckItem("Docker installed", False, hint="install Docker")]
    with patch("onboard.checks.check_prerequisites", return_value=hard_failure), \
         patch("onboard.checks.check_installation", return_value={"SERVICES": [], "AGENT": []}):
        from onboard import plain
        # Must not raise — this is exactly the scenario that used to abort.
        plain.run_wizard(dry_run=True, step_key="prerequisites")


# ── Step summary rendering (TMDEV-79) ──────────────────────────────────────

def _summary_output(fields, values):
    import io
    from rich.console import Console
    from unittest.mock import patch
    buf = io.StringIO()
    with patch("onboard.plain.console", Console(file=buf, width=200)):
        from onboard.plain import render_step_summary
        render_step_summary(fields, values)
    return buf.getvalue()


def test_step_summary_never_prints_a_secret_value():
    """This panel is printed to the terminal and stays in scrollback, so a
    leaked key would persist in the user's history."""
    from onboard.config import FIELDS_BY_KEY
    field = FIELDS_BY_KEY["ELEVENLABS_API_KEY"]
    out = _summary_output([field], {"ELEVENLABS_API_KEY": "sk-super-secret-value"})
    assert "sk-super-secret-value" not in out
    assert "secret" not in out.lower() or "••" in out
    assert "••" in out


def test_step_summary_marks_an_unset_secret_distinctly():
    from onboard.config import FIELDS_BY_KEY
    out = _summary_output([FIELDS_BY_KEY["OPENAI_API_KEY"]], {"OPENAI_API_KEY": ""})
    assert "not set" in out
    assert "••" not in out


def test_step_summary_renders_a_plain_answer():
    from onboard.config import FIELDS_BY_KEY
    out = _summary_output([FIELDS_BY_KEY["POLL_INTERVAL_MINS"]], {"POLL_INTERVAL_MINS": "15"})
    assert "15" in out


def test_step_summary_lists_an_agents_models():
    from onboard.config import Field
    field = Field("AGENT_MODELS", "Models", kind="models", help="h")
    out = _summary_output([field], {"AGENT_MODELS": '["sonnet", "claude-opus-5"]'})
    assert "sonnet, claude-opus-5" in out
    assert "[" not in out.split("Models")[1].splitlines()[0]


# ── Question framing (TMDEV-79 follow-up) ──────────────────────────────────

def _framed_output(field, number=1, total=3):
    import io
    from rich.console import Console
    from unittest.mock import patch
    buf = io.StringIO()
    with patch("onboard.plain.console", Console(file=buf, width=90)):
        from onboard.plain import close_field_frame, open_field_frame
        open_field_frame(field, number, total)
        close_field_frame()
    return buf.getvalue()


def test_question_frame_is_titled_what_this_is_for():
    from onboard.config import FIELDS_BY_KEY
    out = _framed_output(FIELDS_BY_KEY["POLL_INTERVAL_MINS"])
    assert "What's this for?" in out
    assert "Why we ask" not in out


def test_question_frame_encloses_help_progress_and_closes():
    """The question, its explanation and the input must read as one group —
    every line on the rail, and a closed bottom edge once answered."""
    from onboard.config import FIELDS_BY_KEY
    out = _framed_output(FIELDS_BY_KEY["POLL_INTERVAL_MINS"], number=2, total=3)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines[0].startswith("╭─")
    assert lines[0].rstrip().endswith("╮")
    assert "question 2 of 3" in lines[0]
    assert all(ln.startswith("│") for ln in lines[1:-1]), lines
    assert lines[-1].startswith("╰") and lines[-1].rstrip().endswith("╯")


def test_the_prompt_line_continues_the_frame_rail():
    """questionary draws its own line, so the only hook for the left border is
    the qmark — if it stops carrying one the box breaks open."""
    from onboard.prompt import QMARK
    assert QMARK.startswith("│")
