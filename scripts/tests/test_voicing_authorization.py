"""Pins the wording that lets an unattended agent voice a VOICING video (TMDEV-112).

An agent in a cron run refused generate_voice on a video already in VOICING,
asking for "explicit human approval" of the ElevenLabs spend and of sending the
script to a third party — approval the human gave one step earlier, by moving
the video out of SCRIPT_READY. VOICING is agent-workable, so every tick picked
the video up and refused again: a wedge, not a delay.

The cause was prose, so the fix is prose, and prose cannot be unit-tested for
effect — only pinned, so it is not quietly reverted. Two halves, both needed:

  * the VOICING path (first voice, and the re-voice after a pronunciation fix)
    must say outright that it is already authorized, in the operator skill and
    in the poll prompt, which is the context where no human can answer;
  * the SCRIPT_READY checkpoint must stay — scoped to what it guards (moving a
    video *into* VOICING), not read as a blanket ban on generate_voice.

Each assertion was run against the pre-fix text and confirmed to fail first.
"""
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from poll import build_pipeline_prompt

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_OPERATOR = _ROOT / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md"


def _skill() -> str:
    return _OPERATOR.read_text()


def _section(heading: str) -> str:
    """One `## ` section of the operator skill, heading included."""
    text = _skill()
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


def _row(status: str, section: str = "## Per-Status Workflow") -> str:
    """The table row for `status` in the given section."""
    for line in _section(section).splitlines():
        if line.startswith(f"| `{status}` |"):
            return line
    raise AssertionError(f"no `{status}` row in {section!r}")


# ── The VOICING path says it is already authorized ───────────────────────────

def test_voicing_row_says_reaching_voicing_is_the_approval():
    row = _row("VOICING")
    assert "is the approval" in row
    assert "Do not ask for approval again" in row


def test_voicing_row_covers_spend_and_third_party_disclosure():
    """The refusal named both: the paid call, and "disclosure" of an unpublished
    script to ElevenLabs. Nothing addressed the second, so the agent fell back
    on its own default. Both have to be named or the uncovered one still stops it."""
    row = _row("VOICING")
    assert "spend" in row
    assert "sending the script to ElevenLabs" in row


def test_voicing_row_says_a_refusal_wedges_the_video():
    """The cost of the refusal, stated where the decision is made — caution
    reads as free when nothing says what it breaks."""
    assert "wedges the video" in _row("VOICING")


def test_the_revoice_after_a_pronunciation_fix_is_authorized_too():
    """The pronunciation row sets VOICING itself and calls generate_voice again.
    Without this, the same refusal appears on every pronunciation fix."""
    row = next(l for l in _section("## Handling REVISION_REQUESTED").splitlines()
               if l.startswith("|") and "**Pronunciation revision**" in l)
    assert "already authorized" in row
    assert "do not ask for approval again" in row


# ── The SCRIPT_READY checkpoint stays, but scoped ────────────────────────────

def _checkpoints() -> str:
    return _section("## Human Checkpoints")


def test_the_script_ready_checkpoint_still_exists():
    """The guard between an agent and unapproved paid voicing. The bug was its
    scope, not its existence — weakening it is not the fix."""
    section = _checkpoints()
    assert "- **`SCRIPT_READY`**" in section
    assert "do NOT move a `SCRIPT_READY` video into `VOICING`" in section


def test_the_checkpoint_is_no_longer_a_blanket_ban_on_generate_voice():
    """The pre-fix bullet — the loudest line on the page, one paragraph above
    the instruction it contradicted."""
    assert "do NOT call `generate_voice`. ElevenLabs" not in _checkpoints()


def test_the_checkpoint_heading_names_the_move_not_the_tool():
    heading = _checkpoints().splitlines()[0]
    assert heading != "## Human Checkpoints — NEVER Cross Without Approval"
    assert "Out Of" in heading


def test_generate_voice_error_leaves_the_status_alone():
    """Re-writing VOICING onto a VOICING video changes nothing but updated_at,
    which is the clock the render worker's stall alert measures — a refusing
    agent told to "stay put" this way would keep resetting its own alarm."""
    errors = _section("## Error Handling")
    line = next(l for l in errors.splitlines() if "**`generate_voice` error**" in l)
    assert "do not call `set_video_status`" in line


# ── The poll prompt — the context where no human can answer ──────────────────

def test_poll_prompt_still_stops_at_both_checkpoints():
    for status in ("TOPIC_APPROVED", "VOICING", "VOICE_READY", "REVISION_REQUESTED"):
        prompt = build_pipeline_prompt("vid-1", status)
        assert "Stop at human checkpoints (SCRIPT_READY, VIDEO_READY)" in prompt


def test_poll_prompt_says_voicing_is_not_a_checkpoint():
    for status in ("VOICING", "REVISION_REQUESTED"):
        prompt = build_pipeline_prompt("vid-1", status)
        assert "VOICING is not a checkpoint" in prompt
        assert "pre-authorized" in prompt
        assert "sending the script to ElevenLabs" in prompt


def test_poll_prompt_covers_the_revoice():
    assert "re-voice" in build_pipeline_prompt("vid-1", "REVISION_REQUESTED")


# ── The tool itself ──────────────────────────────────────────────────────────

def test_generate_voice_docstring_says_voicing_is_the_authorization():
    """The tool description is agent-visible on every session, skill or not."""
    source = (_ROOT / "mcp" / "server.py").read_text()
    start = source.index("def generate_voice(")
    doc = source[start:source.index('"""', source.index('"""', start) + 3)]
    assert "no further approval" in doc
