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
    for arg in ("reason=", "runner_up=", "repeat_reason=", "learned_mode="):
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
    assert "the tool refuses, the script is rewritten in that formula" in text


def test_the_skill_handles_every_refusal_the_tool_makes():
    text = _text()
    for case in ("already picked", "the style is not decided", "not available",
                 "a recent formula with no `repeat_reason`", "has no `formula_routing`",
                 "the domain's watch figures changed since you read `get_video`"):
        assert case in text, case


def test_the_angle_is_used_when_there_is_one_and_never_required():
    text = _text()
    assert "`angle_formula`" in text
    assert "All three are `\"\"` when the topic has no angle" in text


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


def test_a_revision_picks_for_a_video_with_no_formula_and_respects_a_choice():
    part = _text()[_text().index("## A revision"):_text().index("## Worked example")]
    assert "The video has no formula this version knows" in part
    assert "your comment says the\n  chosen formula was kept" in part


def test_rotation_is_skipped_beside_a_persons_choice():
    assert "When `formula_routing.choice` is set, skip this rotation step" in _text()


def test_the_operator_names_the_routing_skill_on_a_script_revision():
    operator = (SKILLS / "tubematic-operator" / "SKILL.md").read_text(encoding="utf-8")
    row = next(line for line in operator.splitlines() if "**Script revision**" in line)
    assert "tubematic-formula-routing" in row and "formula_routing.choice" in row


def test_a_pick_in_a_revision_always_goes_back_to_a_person():
    part = _text()[_text().index("## A revision"):_text().index("## Worked example")]
    assert "only for a script revision" in part
    assert "never take a video on to voicing or scenes after a pick in a revision" in part


def test_a_dropped_formula_sends_a_revision_to_the_router():
    # A stored formula this version lacks cannot be kept; every skill on the
    # revision path points to the router for it.
    writer = (SKILLS / "tubematic-script-writing-skill" / "SKILL.md").read_text(encoding="utf-8")
    operator = (SKILLS / "tubematic-operator" / "SKILL.md").read_text(encoding="utf-8")
    assert "unless it is not among\n     `formula_routing.candidates`" in writer
    assert "not among `formula_routing.candidates`" in operator
    assert "not among the candidates" in _text()


def test_learned_points_go_only_to_formulas_that_already_fit():
    # TMDEV-217: a formula that does not fit the topic is never picked for how
    # other videos did. The clear-fit line is drawn before the points are added.
    text = _text()
    assert "## Step 3b: Add what this install's viewers say" in text
    assert "**only to the clear fits**, add each one's `learned.points`" in text
    assert "decided by the Step 3\npoints alone, before this step" in text
    assert text.index("A candidate is a **clear fit**") < text.index("## Step 3b")
    assert "- [ ] `learned.points` added to the clear fits only, and to nothing else" in text


def test_the_skill_knows_both_learning_modes_and_an_older_server():
    text = _text()
    for phrase in ('`"learned"` mode', '`"explore"` mode', "`formula_routing.learned`",
                   "take the points as they are", "has no `learned`",
                   "How well a formula holds viewers\n   is never a `repeat_reason`"):
        assert phrase in text, phrase


def test_the_skill_states_the_points_the_server_gives():
    from tubematic_core import watch
    text = _text()
    assert watch.LEARNED_POINTS == {"better": 2, "worse": -1} and watch.EXPLORE_POINTS == 2
    assert watch.EXPLORE_EVERY == 4
    assert "clearly better than the domain's\n  videos as a whole has 2" in text
    assert "clearly worse has -1" in text
    assert "every fourth pick in a domain with figures" in text
    for standing in (*watch.STANDINGS, watch.THIN):
        assert f"`{standing}`" in text, standing
