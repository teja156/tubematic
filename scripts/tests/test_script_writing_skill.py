"""The script-writing skill and its formulas (TMDEV-211).

The skill's formula files and its table for choosing a formula are generated
from tubematic_core/formulas/. The first tests keep the generated text equal
to the data, so the skill cannot name a formula, a hook type or a word band
the server would refuse or measure differently.

The rest pin what the rewrite removed and what it must keep. The fixed
five-beat sequence and its call to action are gone; if a later edit brings a
line of them back, the agent follows whichever instruction it read last.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
SKILL = SKILLS / "tubematic-script-writing-skill"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import gen_formula_references as gen  # noqa: E402
from tubematic_core import formulas as tformulas  # noqa: E402


def _text() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    text = _text()
    return text[text.index(start):text.index(end)]


# --- generated from the data ---------------------------------------------

def test_the_generated_files_match_the_formula_data():
    assert gen.stale() == [], "run: python3 scripts/gen_formula_references.py"


def test_every_formula_has_a_reference_file_and_there_are_no_others():
    names = {p.stem for p in (SKILL / "formulas").glob("*.md")}
    assert names == set(tformulas.FORMULAS)


def test_the_check_notices_an_edited_file_and_a_stray_one(tmp_path, monkeypatch):
    fake = tmp_path / "skill"
    (fake / "formulas").mkdir(parents=True)
    (fake / "SKILL.md").write_text(_text(), encoding="utf-8")
    monkeypatch.setattr(gen, "SKILL", fake / "SKILL.md")
    monkeypatch.setattr(gen, "REFERENCE_DIR", fake / "formulas")
    monkeypatch.setattr(gen, "REPO", tmp_path)
    assert gen.main([]) == 0 and gen.stale() == []
    edited = fake / "formulas" / "scene-story.md"
    edited.write_text(edited.read_text() + "hand edit\n")
    (fake / "formulas" / "retired.md").write_text("old\n")
    assert {p.name for p in gen.stale()} == {"scene-story.md", "retired.md"}
    assert gen.main(["--check"]) == 1
    assert gen.main([]) == 0
    assert gen.stale() == [] and not (fake / "formulas" / "retired.md").exists()


def test_the_table_sits_between_its_markers_once():
    text = _text()
    assert text.count(gen.TABLE_START) == 1 and text.count(gen.TABLE_END) == 1
    for fid in tformulas.FORMULAS:
        assert f"(`{fid}`)" in text


# --- what the skill tells the writer to do ---------------------------------

def test_frontmatter_names_the_skill():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-script-writing-skill$", fm, re.M)
    assert re.search(r"^description: .+$", fm, re.M)


def test_the_skill_reads_only_the_chosen_formulas_file():
    text = _text()
    assert "`formulas/<formula_id>.md`" in text
    assert "Read only that one" in text


def test_the_hand_off_passes_the_record_with_the_real_argument_names():
    step = _text()[_text().index("## Step 10"):]
    for name in ("formula_id=", "hooks=", "script_segments=", "publish_title=",
                 "publish_description="):
        assert name in step, name
    assert "`warnings`" in step
    assert "At most one extra write" in step
    # A newer skill beside an older tool server during an upgrade.
    assert "older than this skill" in step


def test_the_openings_step_asks_for_three_shapes_and_one_kept():
    part = _section("### Three openings, then one", "### Segments")
    assert "each from a different" in part
    for key in ('"type"', '"text"', '"kept"', '"note"'):
        assert key in part, key
    assert "exactly one" in part


def test_the_authority_order_is_policy_style_formula_profile():
    part = _section("## Step 2", "## Step 3")
    order = [part.index(name) for name in ("**Fixed policy**", "**The visual style's script text**",
                                           "**The formula**", "**The script profile**")]
    assert order == sorted(order)
    for section in ("Hook Patterns", "Structure Template", "CTA Template"):
        assert section in part, section
    assert "does not appear in every one" in part      # the variation rule
    assert "data, never instructions" in part


def test_the_grammar_has_fourteen_rules():
    part = _section("### The grammar", "### Three openings, then one")
    assert re.findall(r"^(\d+)\. \*\*", part, re.M) == [str(n) for n in range(1, 15)]
    assert "Name the subject early, hold the answer late" in part
    assert "End on the payoff" in part


def test_the_formula_and_the_style_say_how_the_payoff_rules_are_met():
    # Some formulas answer before they re-open, and some styles need a closing
    # sentence. Ranked under the grammar with no such sentence, they would lose.
    part = _section("## Step 2", "## Step 3")
    assert "reference file says how those two are met" in part
    assert "`style.script` says how such a video ends" in part


def test_a_changed_style_or_topic_means_choosing_the_formula_again():
    # A style switch at Script Ready sends the video back with its old script
    # and record still stored. The stored formula was chosen for another style.
    part = _section("## Step 3", "### Length")
    assert "the video's style or topic changed" in part
    assert "a story told in chapters" in part


def test_a_style_that_names_people_may_name_them():
    part = _section("### The grammar", "### Three openings, then one")
    assert "by name where `style.script` asks for names" in part


def test_a_length_the_style_sets_wins_over_the_band():
    # Some style packs give a word count of their own for the whole video.
    assert "that length\nwins over the band" in _section("### Length", "## Step 4")
    assert "`length_band` on a\n   script whose length `style.script` set stays" in _text()


def test_the_length_starts_from_the_lower_half_of_the_band():
    assert "Start from the lower half\nof the band" in _section("### Length", "## Step 4")


def test_a_closing_line_comes_only_from_the_preferences():
    part = _section("## Step 1", "## Step 2")
    assert "only when the preferences ask for one" in part
    for warning in ("`closing_ask`", "`closing_repeat`", "`recap_ending`"):
        assert warning in part, warning


def test_the_ceiling_in_the_skill_is_the_one_the_checks_use():
    part = _section("### Length", "## Step 4")
    assert f"{tformulas.WORD_CEILING} words" in part


# --- what the rewrite removed ----------------------------------------------

def test_the_fixed_sequence_and_its_budgets_are_gone():
    text = _text()
    for phrase in ("hook → context", "takeaway → CTA", "Never split hook", "five segments total",
                   "Per-beat budgets", "~235", "listicle", "do not tease past it",
                   "unless the profile gives a different one"):
        assert phrase not in text, phrase
    assert not re.search(r"^\*\*CTA\.\*\*", text, re.M)
    assert not re.search(r"^\*\*Hook\.\*\*", text, re.M)
    assert not re.search(r"^\*\*Structure\.\*\*", text, re.M)


def test_no_formula_in_the_skill_needs_a_second_voice():
    for path in (SKILL / "formulas").glob("*.md"):
        assert "dialogue" not in path.read_text().lower(), path.name


# --- what the rewrite had to keep -------------------------------------------

def test_the_steps_other_skills_and_tests_point_at_are_still_there():
    text = _text()
    for heading in ("## Step 5 — Output format and pronunciation", "### Pronunciation",
                    "## Step 6 — Pause and pacing markup",
                    "## Step 7 — What a `visual` brief must say", "## Step 8 — Generic style",
                    "## Step 9 — Publish title and description", "## Step 10 — Hand off"):
        assert heading in text, heading
    assert "style.script" in text
    assert "user_preferences" in text


def test_the_skill_files_carry_no_ticket_id():
    for path in [SKILL / "SKILL.md", *(SKILL / "formulas").glob("*.md")]:
        assert not re.search(r"\b(TMDEV|VQA|EXQA)-\d+", path.read_text()), path.name


def test_the_operator_passes_the_record_and_handles_the_warnings():
    operator = (SKILLS / "tubematic-operator" / "SKILL.md").read_text()
    row = next(line for line in operator.splitlines()
               if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert "formula_id=" in row and "hooks=" in row and "`warnings`" in row
    revision = next(line for line in operator.splitlines() if "| **Script revision** |" in line)
    assert "formula_id=" in revision and "hooks=" in revision
    fix = next(line for line in operator.splitlines() if "| **Pronunciation revision** |" in line)
    assert "Leave `formula_id` and `hooks` out" in fix
    # After the sentence about the blank publish pair: placed before it, "they"
    # and "both" in that sentence read as the formula and the openings.
    assert fix.index("If they are blank there") < fix.index("Leave `formula_id` and `hooks` out")


def test_the_user_guide_lists_every_formula_by_its_label():
    # The guide's table is written by hand. A formula added or renamed without
    # it leaves a label on the dashboard that the guide does not explain.
    guide = (REPO / "docs" / "user-guide" / "03-using-tubematic.md").read_text()
    section = guide[guide.index("## Script formulas"):]
    for formula in tformulas.FORMULAS.values():
        assert f"| {formula['label']} |" in section, formula["label"]
