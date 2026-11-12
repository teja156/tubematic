"""What the agent is told about a topic's angle (TMDEV-214).

The server refuses a research proposal with no angle, so the text an agent
reads has to say what an angle is, in the server's own terms. The kinds and
the score in the topic-research skill are generated from
tubematic_core/angles.py; the first tests keep them equal. The rest pin the
instructions that make the rule hold end to end:

- research finds an angle or drops the subject, and says what it dropped;
- a video picked up with no angle gets one before its script, and one a
  person approved is left alone;
- the script writer reads the angle;
- a person's own topic is never refused for lacking one.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import gen_angle_reference as gen  # noqa: E402
from tubematic_core import angles as tangles  # noqa: E402

FIELDS = ("angle", "angle_kind", "angle_score")


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _command(agent: str) -> str:
    return (REPO / "agent_files" / agent / "commands" /
            "tubematic-submit-new-job.md").read_text(encoding="utf-8")


# --- generated from the data ---------------------------------------------

def test_the_research_skills_angle_reference_matches_the_data():
    assert not gen.stale(), "run: python3 scripts/gen_angle_reference.py"
    assert tangles.reference_markdown() in _skill("tubematic-topic-research")


def test_the_check_notices_a_hand_edit(tmp_path, monkeypatch):
    fake = tmp_path / "SKILL.md"
    fake.write_text(_skill("tubematic-topic-research"), encoding="utf-8")
    monkeypatch.setattr(gen, "SKILL", fake)
    monkeypatch.setattr(gen, "REPO", tmp_path)
    assert gen.main(["--check"]) == 0
    fake.write_text(fake.read_text().replace("| **Paradox** (`paradox`)", "| **Puzzle** (`paradox`)"))
    assert gen.main(["--check"]) == 1
    assert gen.main([]) == 0
    assert gen.main(["--check"]) == 0


# --- research ------------------------------------------------------------

def test_research_passes_the_angle_to_create_video():
    text = _skill("tubematic-topic-research")
    for field in FIELDS:
        assert f"`{field}`" in text


def test_research_drops_a_subject_with_no_angle_and_never_invents_one():
    text = _skill("tubematic-topic-research")
    assert "is not proposed" in text
    assert "never invented" in text


def test_research_ends_with_a_summary_that_names_what_it_dropped():
    text = _skill("tubematic-topic-research")
    summary = text[text.index("## Run summary"):]
    assert "no angle" in summary
    assert "not_filed" in summary
    # The poller logs only the start of the agent's final message, so the
    # dropped list, which nothing else records, comes before the filed one.
    assert summary.index("**Dropped**") < summary.index("**Filed**")


def test_research_tells_a_missing_score_from_a_drop():
    """create_video refuses a left-out score with its own message. Read as a
    drop, it would lose a subject that had an angle."""
    text = _skill("tubematic-topic-research")
    assert "angle_score was not passed" in text
    assert "call again with the number" in text


def test_the_operator_never_writes_none_as_an_angle():
    text = _skill("tubematic-operator")
    row = next(line for line in text.splitlines() if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert "do not call `update_video` for the angle" in row


def test_research_no_longer_leaves_the_angle_in_a_comment_only():
    assert "with the hook angle and score rationale" not in _skill("tubematic-topic-research")


def test_the_research_examples_name_no_installs_domains():
    """The skill ships to every install. Its worked angles use subjects the
    skill already used as examples, never one install's domain names."""
    text = _skill("tubematic-topic-research")
    for name in ("Scams", "Git Internals", "Animal Superpowers", "Ordinary Lives"):
        assert name not in text


# --- pickup and revision -------------------------------------------------

def test_the_operator_fills_a_missing_angle_before_the_style_and_the_script():
    text = _skill("tubematic-operator")
    row = next(line for line in text.splitlines() if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert row.index("angle") < row.index("tubematic-style-routing") < row.index(
        "tubematic-script-writing-skill")
    for field in FIELDS:
        assert f"{field}=" in row
    assert "never refuse" in row.lower() or "never stop" in row.lower()


def test_the_operator_leaves_an_approved_angle_alone():
    text = _skill("tubematic-operator")
    row = next(line for line in text.splitlines() if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert "already has" in row


def test_the_operator_says_a_topic_has_no_angle_once():
    """A video can wait at TOPIC_APPROVED across several sessions. Each one
    sees an empty angle, and each would add the same comment."""
    text = _skill("tubematic-operator")
    row = next(line for line in text.splitlines() if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert "Say it once" in row


def test_the_research_skill_says_what_applies_to_one_existing_topic():
    """The operator and the submit command send a session to The angle for a
    single topic. The section's research rule (drop the subject) must not
    read as applying there."""
    text = _skill("tubematic-topic-research")
    section = text[text.index("## The angle"):text.index("## Producibility Scoring")]
    assert "one existing topic" in section
    assert "Nothing is dropped and no score floor applies" in section


def test_a_topic_revision_can_rewrite_the_angle():
    text = _skill("tubematic-operator")
    row = next(line for line in text.splitlines() if "**Topic revision**" in line)
    assert "angle" in row


# --- the script writer ---------------------------------------------------

def test_the_script_writer_reads_the_angle_and_builds_its_openings_on_it():
    # The formula is picked before the script (the formula router reads
    # angle_formula); the writer reads the angle for its openings.
    text = _skill("tubematic-script-writing-skill")
    step1 = text[text.index("## Step 1"):text.index("## Step 2")]
    assert "`angle`" in step1 and "`angle_formula`" in step1
    openings = text[text.index("### Three openings, then one"):text.index("### Segments")]
    assert "angle" in openings


def test_the_formula_router_reads_the_angle_and_still_works_without_one():
    text = _skill("tubematic-formula-routing")
    step1 = text[text.index("## Step 1"):text.index("## Step 2")]
    assert "`angle_kind`" in step1 and "`angle_formula`" in step1
    assert "no angle" in step1 and "from the topic alone" in step1
    step3 = text[text.index("## Step 3"):text.index("## Step 4")]
    assert "`angle_formula`" in step3


def test_a_rewritten_angle_sends_a_script_revision_through_the_router():
    text = _skill("tubematic-operator")
    row = next(line for line in text.splitlines() if "**Script revision**" in line)
    assert row.index("rewrite the angle first") < row.index("tubematic-formula-routing")
    assert "the angle was rewritten for this revision" in row


# --- a person's own topic ------------------------------------------------

def test_the_two_submit_commands_are_the_same_file():
    assert _command("claude") == _command("opencode")


def test_submit_new_job_passes_an_angle_and_never_refuses_for_lacking_one():
    text = _command("claude")
    for field in FIELDS:
        assert f"{field}=" in text
    assert "never refuse" in text.lower()
