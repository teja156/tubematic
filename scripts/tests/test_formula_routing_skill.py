"""The formula-routing skill (TMDEV-213). A video's script formula is picked
with it, after the style and before the script, from the candidates get_video's
formula_routing lists.

The rule this file exists to keep: the skill reads the formulas from data and
names none of them but its two fallbacks, so a new formula is pickable the day
it ships with no edit to the skill. A skill that named formulas would quietly
prefer the ones it knew about. It must also agree with the tool it calls, with
the server's refusals, and with the operator that hands videos to it.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
SKILL = SKILLS / "tubematic-formula-routing"
sys.path.insert(0, str(REPO))

from tubematic_core import formulas as tf  # noqa: E402

# Named in the skill because they are what it falls back to when nothing fits
# and when the tool server is too old to list candidates.
FALLBACKS = ("follow-the-flow", "scene-story")


def _text() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-formula-routing$", fm, re.M)
    assert re.search(r"^description: .+$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_skill_names_no_formula_but_its_fallbacks():
    text = _text().lower()
    for fid, formula in tf.FORMULAS.items():
        if fid in FALLBACKS:
            continue
        assert not re.search(rf"\b{re.escape(fid)}\b", text), fid
        assert formula["label"].lower() not in text, formula["label"]


def test_the_fallbacks_are_core_formulas_of_the_two_kinds():
    text = _text()
    for fid in FALLBACKS:
        assert f"`{fid}`" in text
        assert fid in tf.FORMULAS and not tf.FORMULAS[fid]["experimental"], fid
    assert tf.FORMULAS["follow-the-flow"]["family"] == "explain"
    assert tf.FORMULAS["scene-story"]["family"] == "story"


def test_the_skill_reads_every_field_the_candidates_carry():
    text = _text()
    candidate = tf.routing_candidates()[0]
    for field in candidate:
        assert f"`{field}`" in text, field
    for field in ("formula_routing.candidates", "formula_routing.decided",
                  "formula_routing.recent", "formula_routing.choice", "style_routing.decided",
                  "style.script"):
        assert field in text, field


def test_the_skill_calls_the_tool_with_its_real_arguments_and_limit():
    text = _text()
    assert "choose_script_formula(video_id, formula=" in text
    for arg in ("reason=", "runner_up=", "repeat_reason="):
        assert arg in text, arg
    assert f"at most {tf.REASON_MAX_CHARS} characters" in text
    for key in ("`formula_pick`", "`chosen_by`", "`reference`"):
        assert key in text, key


def test_rotation_is_the_window_the_server_enforces():
    text = _text()
    assert tf.ROTATION_WINDOW == 2
    assert "previous two videos" in text
    assert "`repeat_reason`" in text


def test_a_persons_choice_is_routed_around_never_overridden():
    text = _text()
    assert "pass your own best formula" in text
    assert "Never pass the person's choice just because it is theirs" in text
    assert "the tool refuses, and the script is rewritten in that formula" in text


def test_the_skill_handles_every_refusal_the_tool_makes():
    text = _text()
    for case in ("already picked", "the style is not decided", "not available",
                 "a recent formula with no `repeat_reason`", "has no `formula_routing`"):
        assert case in text, case


def test_the_angle_is_used_when_there_is_one_and_never_required():
    text = _text()
    assert "`angle_formula`" in text
    assert "When `get_video` carries an `angle`" in text


def test_the_operator_runs_it_after_the_style_and_before_the_script():
    operator = (SKILLS / "tubematic-operator" / "SKILL.md").read_text(encoding="utf-8")
    row = next(line for line in operator.splitlines() if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert (row.index("tubematic-style-routing") < row.index("tubematic-formula-routing")
            < row.index("tubematic-script-writing-skill"))
    assert "formula_routing.decided" in row and "choose_script_formula" in row


def test_the_uninstaller_and_the_readme_know_the_skill():
    assert '"tubematic-formula-routing"' in (REPO / "uninstall.py").read_text()
    assert "`tubematic-formula-routing/`" in (SKILLS / "README.md").read_text(encoding="utf-8")


def test_the_skill_carries_no_ticket_id():
    assert not re.search(r"\b(TMDEV|VQA|EXQA)-\d+", _text())
