"""Insert scenes in the skills. A video has one main style and may carry short
insert scenes (System Flow, Terminal Doc) inside segments its script marks.

The skills that make such a video are separate files read at separate steps,
so each must agree with the others and with the server: the operator runs
insert routing between style routing and formula routing, the script writer
keeps the marks within the rules update_video enforces, every main style that
takes inserts sends its author to tubematic-inserts, and the insert styles'
own skills say what an insert leaves out. A skill that misses one of these
teaches the agent a step the server refuses, or skips one it needs.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import inserts as tinserts  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402
import system_flow as sf  # noqa: E402
import terminal_doc as td  # noqa: E402


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _flat(name: str) -> str:
    return " ".join(_skill(name).split())


def _row(text: str, start: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(start))


# --- the operator -----------------------------------------------------------

def test_the_operator_routes_inserts_between_the_style_and_the_formula():
    row = _row(_skill("tubematic-operator"), "| `TOPIC_APPROVED` | **First")
    order = [row.index(s) for s in ("tubematic-style-routing", "tubematic-insert-routing",
                                    "tubematic-formula-routing", "tubematic-script-writing-skill")]
    assert order == sorted(order)
    assert "`insert_routing.decided` is `false`" in row


def test_the_operator_treats_system_flow_and_terminal_doc_as_insert_styles():
    text = _skill("tubematic-operator")
    row = _row(text, "| `VOICE_READY` | **Invoke")
    assert "tubematic-inserts" in row
    assert "**A System Flow video**" not in row and "**A Terminal Doc video**" not in row
    assert "legacy" in row.lower()
    flat = " ".join(text.split())
    assert "`system_flow` replaces" not in flat and "`terminal_doc` replaces" not in flat
    assert "`system_flow` and `terminal_doc` are **insert styles**" in flat


# --- the script writer ------------------------------------------------------

def test_the_script_writer_keeps_the_marks_inside_the_rules_update_video_enforces():
    text = _flat("tubematic-script-writing-skill")
    marks = text[text.index("### Insert marks"):text.index("### No stage directions")]
    for rule in ("Never the first or the last segment", "Never two marked segments in a row",
                 "Never the segment that carries the payoff", "`insert_styles` is `[]` or `None`",
                 "only an id in `insert_styles`", "insert_routing.candidates", "`script` text"):
        assert rule in marks, rule
    assert f"about {tinserts.TARGET_SECONDS:.0f} seconds spoken" in marks
    # the warning it names is the one the server returns for a long marked segment
    long_seg = [{"voice": "word " * 60, "insert": "system_flow"}]
    assert [w["id"] for w in tinserts.mark_warnings(long_seg)] == ["insert_long"]
    assert "`insert_long`" in marks


def test_the_script_writers_segment_shape_names_the_insert_key():
    text = _skill("tubematic-script-writing-skill")
    shape = text[text.index("### The segments list"):text.index("### Insert marks")]
    assert "- **`insert`** — optional" in shape


# --- the main styles' authors -----------------------------------------------

def _hosting_authoring_skills() -> set:
    skills = {"tubematic-scene-config"}  # auto: the mixed scene system hosts inserts
    for sid, pack in tvs.PACKS.items():
        if pack["role"] == "main" and tvs.hosts_inserts(sid).get("host"):
            skills.add(pack["authoring_skill"])
    return skills


def test_every_main_style_that_takes_inserts_sends_its_author_to_the_inserts_skill():
    skills = _hosting_authoring_skills()
    assert {"tubematic-whiteboard", "tubematic-bean-explainer", "tubematic-storybook-atlas",
            "tubematic-under-the-hood", "tubematic-case-file-story"} <= skills
    for name in skills:
        text = _flat(name)
        assert "invoke the **tubematic-inserts** skill" in text, name
        assert "any `inserts`" in text, name


def test_case_file_story_keeps_inserts_off_its_cards_and_its_ending():
    text = _flat("tubematic-case-file-story")
    step = text[text.index("## Inserts"):text.index("## Step 6")]
    for phrase in ("only over shots before the term card", "never over a card", "never in the choice"):
        assert phrase in step, phrase


def test_the_scene_system_draws_a_marked_diagram_beat_as_the_insert():
    text = _flat("tubematic-scene-config")
    assert "marked as a `system_flow` insert is drawn by the insert" in text
    assert "no scene starts inside an insert's window" in text


def test_cartoon_3d_takes_no_inserts():
    assert not tvs.hosts_inserts("cartoon_3d").get("host")
    text = _flat("tubematic-cartoon3d")
    assert "takes no insert scenes" in text
    assert "tubematic-inserts" not in text


# --- the insert styles' own skills ------------------------------------------

def test_the_insert_styles_skills_open_with_an_as_an_insert_section():
    for sid in tvs.INSERT_STYLES:
        name = tvs.PACKS[sid]["authoring_skill"]
        text = _skill(name)
        assert text.index("## As an insert") < text.index("## What you are making"), name
        section = " ".join(text[text.index("## As an insert"):text.index("## What you are making")].split())
        for phrase in ("tubematic-inserts", "one entry of the config's `inserts`, not a scene",
                       "insert's `startFrame`", "Leave `subtitles` alone", "No mascot cue"):
            assert phrase in section, (name, phrase)
        # the legacy whole video still takes the whole skill
        assert "legacy whole video" in text, name


def test_the_as_an_insert_sections_state_the_validators_limits():
    flow = _skill("tubematic-system-flow")
    flow = " ".join(flow[flow.index("## As an insert"):].split())
    assert f"At most {sf.MAX_INSERT_BOARDS} boards" in flow
    term = _skill("tubematic-terminal-doc")
    term = " ".join(term[term.index("## As an insert"):term.index("## What you are making")].split())
    assert f"At most {td.MAX_INSERT_BEATS} beats" in term
    assert "No `customMoves`" in term and "No `skin`" in term
    assert f"at least {td.TIMING['readMargin']} frames before it" in term


# --- the index and the ticket rule ------------------------------------------

def test_the_skills_readme_lists_the_insert_skills():
    readme = (SKILLS / "README.md").read_text(encoding="utf-8")
    for name in ("tubematic-insert-routing", "tubematic-inserts"):
        assert f"| `{name}/` |" in readme, name


def test_the_skills_that_teach_inserts_carry_no_ticket_id():
    names = {"tubematic-operator", "tubematic-script-writing-skill", "tubematic-cartoon3d",
             "tubematic-insert-routing", "tubematic-inserts",
             *_hosting_authoring_skills(), *(tvs.PACKS[s]["authoring_skill"] for s in tvs.INSERT_STYLES)}
    for name in names:
        assert not re.search(r"\b(TMDEV|VQA|EXQA)-\d+", _skill(name)), name


def test_photo_explainer_draws_no_diagram_scene_of_its_own():
    """Its diagrams are System Flow inserts, or a labelled photograph when there
    is no insert (TMDEV-225)."""
    text = (SKILLS / "tubematic-scene-config" / "SKILL.md").read_text()
    rule = text.split("Under `motion_graphics` (Photo Explainer) a DIAGRAM beat is not yours to draw")[1][:600]
    assert "system_flow" in rule and "HYBRID" in rule and "Never a vector diagram scene" in rule
