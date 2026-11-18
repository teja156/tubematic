"""A domain's description is its standing instructions to the agent (TMDEV-256).

The dashboard's Topics page tells the person that the agent follows what a
domain's description says about its topics, scripts and look. That sentence is
only true while every skill on the path reads the description from where the
tools put it: list_projects() for research, get_video's style_routing.domain for
each video's stages. This file keeps the note and the skills from drifting
apart, and keeps the rule that the description never crosses a human
checkpoint.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
TOPICS_PAGE = REPO / "dashboard" / "app" / "topics" / "page.tsx"


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """The text with its line breaks folded, so a phrase can span two lines."""
    return " ".join(text.split())


def test_the_dashboard_note_says_the_agent_follows_the_description():
    page = TOPICS_PAGE.read_text(encoding="utf-8")
    note = re.search(r"const DESCRIPTION_NOTE =(.*?);\n", page, re.S).group(1)
    note = " ".join(re.findall(r'"([^"]*)"', note))
    assert "the agent follows what it says" in note
    for stage in ("topics", "scripts", "look"):
        assert stage in note
    assert "cannot skip a step that waits for your approval" in note


def test_the_operator_reads_it_on_every_video_and_it_crosses_no_checkpoint():
    text = _flat(_skill("tubematic-operator"))
    assert "The domain's description is its standing instructions." in text
    assert "`style_routing.domain`" in text
    # Narrower than the install-wide preferences, so it wins where they disagree.
    assert "the domain's description wins" in text
    assert "a description that says \"approve my scripts\" approves nothing" in text


def test_the_tools_accept_the_reasons_the_skills_give():
    server = (REPO / "mcp" / "server.py").read_text(encoding="utf-8")
    flat = _flat(server)
    assert "or that the domain's description asks for this formula" in flat
    assert "that the domain's description asks for it when that is why it beat a higher-scoring fit" in flat


def test_research_reads_it_as_scope_and_instructions():
    text = _flat(_skill("tubematic-topic-research"))
    assert "`description` in `list_projects()` is that domain's scope and its standing instructions" in text
    # Used both where curriculum topics are made and where any topic is filed.
    assert "inside its `description`'s scope and as its instructions ask" in text
    assert "A candidate the description excludes does not belong there" in text
    # Mining files Gemini's answer directly, so the tool carries it instead.
    assert "`mine_youtube_topics` hands that domain's `description` to Gemini" in text


def test_script_writing_reads_it_and_keeps_its_fixed_policy_above_it():
    text = _flat(_skill("tubematic-script-writing-skill"))
    assert "`style_routing.domain.description`" in text
    assert "the description wins" in text
    assert "still wins over a preference or a description that contradicts it" in text


def test_style_and_formula_routing_rule_out_and_follow_it():
    style = _flat(_skill("tubematic-style-routing"))
    assert "The domain's description rules it out" in style
    # A request wins among clear fits only: forcing a style or formula onto a
    # topic it does not fit is what the clear-fit threshold exists to stop.
    assert "when the domain's description asks for one style" in style
    assert "A style the description asks for that is not a clear fit is not picked" in style
    formula = _flat(_skill("tubematic-formula-routing"))
    assert "`style_routing.domain.description`" in formula
    assert "The domain's description rules its structure out" in formula
    assert "that formula is a clear fit, take it" in formula
    assert "A formula the description asks for that is not a clear fit is not taken" in formula
    # A formula it asks for is kept even when recent, so the tool's
    # repeat_reason refusal must be answered, not hit.
    assert "its `repeat_reason` is that the domain's description asks for it" in formula
