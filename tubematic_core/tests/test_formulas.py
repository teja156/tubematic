"""Script formulas as data (TMDEV-211, TMDEV-213): one file per formula, checked
at import.

The script-writing skill's reference files are rendered from these files, the
script write checks a recorded formula and its hook types against them, the
band warning reads each formula's word band, and the router's candidate list
is built from them. A file that loads with a gap in it would therefore fail
far from its cause: as a skill file with a hole, a warning that never fires,
or a formula Auto can never pick.
"""
import copy
import json
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import formulas as tf  # noqa: E402

CORE = {"paradox-mechanism-reframe", "broken-expectation", "follow-the-flow", "myth-break-model",
        "why-dont-they-just", "incident-file", "scheme-machine", "anomaly-file", "scene-story",
        "escalating-ladder"}
# Shipped as data, off for Auto until the setting turns them on.
EXPERIMENTAL = {"normal-world-exploit", "result-then-rewind", "stake-first-list", "news-take",
                "prize-and-barrier", "strange-sight", "test-case", "contender-champion"}


def _valid() -> dict:
    return copy.deepcopy(tf.FORMULAS["broken-expectation"])


def _check(data, stem="broken-expectation"):
    return tf._check_formula(pathlib.Path(f"{stem}.json"), data)


def test_the_core_and_the_experimental_formulas_load_in_order():
    assert set(tf.FORMULAS) == CORE | EXPERIMENTAL
    assert {fid for fid, f in tf.FORMULAS.items() if f["experimental"]} == EXPERIMENTAL
    # The core formulas come first, so a list cut short still holds them.
    assert set(list(tf.FORMULAS)[:len(CORE)]) == CORE
    orders = [f["order"] for f in tf.FORMULAS.values()]
    assert orders == sorted(orders)
    assert set(tf.FORMULAS) == {p.stem for p in tf.FORMULAS_DIR.glob("*.json")}


def test_every_formula_offers_three_openings_of_different_types():
    for f in tf.FORMULAS.values():
        types = [h["type"] for h in f["hooks"]]
        assert len(types) >= 3 and len(set(types)) == len(types), f["id"]
        assert set(types) <= set(tf.HOOK_TYPES), f["id"]


def test_every_band_sits_inside_the_ceiling_and_beats_cover_the_whole_script():
    for f in tf.FORMULAS.values():
        lo, hi = f["words"]
        assert tf.WORD_FLOOR <= lo < hi <= tf.WORD_CEILING, f["id"]
        assert f["beats"][0]["from"] == 0 and f["beats"][-1]["to"] == 100, f["id"]
        for a, b in zip(f["beats"], f["beats"][1:]):
            assert a["to"] == b["from"], f["id"]


def test_no_formula_needs_a_second_voice():
    # A dialogue formula needs a second roster voice, and no formula field says
    # so yet: on an install with one voice, routing could pick a script nobody
    # can voice. The field comes with the first two-voice formula.
    for f in tf.FORMULAS.values():
        text = json.dumps(f).lower()
        assert "second voice" not in text and "dialogue" not in text, f["id"]


def test_the_files_carry_no_ticket_id_and_no_link():
    # They are rendered into skill files that ship in the release archive.
    for path in tf.FORMULAS_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(TMDEV|VQA|EXQA)-\d+", text), path.name
        assert "http://" not in text and "https://" not in text, path.name
        assert "—" not in text, path.name


def test_word_band_and_label_answer_for_known_unknown_and_blank():
    assert tf.word_band("broken-expectation") == (130, 200)
    assert tf.word_band("") is None and tf.word_band(None) is None
    assert tf.word_band("retired-formula") is None
    assert tf.label("scene-story") == "Scene Story"
    assert tf.label("retired-formula") == "retired-formula"
    assert tf.label("") == ""


def test_public_list_names_every_formula_and_hook_type():
    out = tf.public_list()
    assert [f["id"] for f in out["formulas"]] == list(tf.FORMULAS)
    assert set(out["formulas"][0]) == {"id", "label", "family", "line", "words", "experimental"}
    assert [f["id"] for f in out["formulas"] if f["experimental"]] == \
        [fid for fid in tf.FORMULAS if fid in EXPERIMENTAL]
    assert [h["id"] for h in out["hook_types"]] == list(tf.HOOK_TYPES)


def test_the_valid_formula_passes_the_check():
    assert _check(_valid())["id"] == "broken-expectation"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.update(id="other"), "must equal the file name"),
    (lambda d: d.pop("ending"), "exactly the keys"),
    (lambda d: d.update(extra=1), "exactly the keys"),
    (lambda d: d.update(order=True), "order"),
    (lambda d: d.update(family="voices"), "family"),
    (lambda d: d.update(label="  "), "label"),
    (lambda d: d.update(best_for=[]), "best_for"),
    (lambda d: d.update(pitfalls=["ok", ""]), "pitfalls"),
    (lambda d: d.update(words=[130, 500]), "words"),
    (lambda d: d.update(words=[200, 130]), "words"),
    (lambda d: d.update(words=[10, 130]), "words"),
    (lambda d: d["beats"][2].update({"from": 30}), "beats[2]"),
    (lambda d: d["beats"][-1].update(to=95), "100 percent"),
    (lambda d: d["beats"][0].update(job=""), "beats[0]"),
    (lambda d: d.update(beats=d["beats"][:2]), "at least three"),
    (lambda d: d["beats"][0].update(name="x" * 61), "at most 60"),
    (lambda d: d["beats"][1].update(name=d["beats"][0]["name"]), "share a name"),
    (lambda d: d["beats"][0].update(job="one | two"), "one line"),
    (lambda d: d.update(ending="line one\nline two"), "one line"),
    (lambda d: d["hooks"][0].update(type="shout"), "hooks[0].type"),
    (lambda d: d["hooks"][1].update(type=d["hooks"][0]["type"]), "different type"),
    (lambda d: d.update(hooks=d["hooks"][:2]), "at least 3"),
    (lambda d: d.pop("first_frame"), "exactly the keys"),
    (lambda d: d.update(first_frame=" "), "first_frame"),
    (lambda d: d["beats"][0].update(extra=1), "optionally, role"),
    (lambda d: d["beats"][0].update(role="climax"), "beats[0].role"),
    (lambda d: d["beats"][0].update(role="turn"), "at most one beat may be the turn"),
    (lambda d: [b.pop("role", None) for b in d["beats"] if b.get("role") == "payoff"],
     "exactly one beat must be the payoff"),
    (lambda d: d["beats"][0].update(role="payoff"), "exactly one beat must be the payoff"),
    (lambda d: d.update(experimental="no"), "experimental"),
    (lambda d: d.pop("experimental"), "exactly the keys"),
    (lambda d: d.update(signals=[]), "signals"),
    (lambda d: d.update(styles=["system_flow", "no_such_style"]), "styles"),
    (lambda d: d.update(styles=["system_flow", "system_flow"]), "styles"),
    (lambda d: d.update(styles="system_flow"), "styles"),
    (lambda d: d.update(styles=["auto"]), "styles"),
])
def test_a_malformed_formula_is_refused_with_the_reason(mutate, message):
    data = _valid()
    mutate(data)
    with pytest.raises(tf.FormulaError) as err:
        _check(data)
    assert message in str(err.value)


def test_every_style_a_formula_names_is_a_style_pack():
    # Checked at import too; this names the file when a pack is renamed.
    from tubematic_core import visual_styles as tvs
    for f in tf.FORMULAS.values():
        assert set(f["styles"]) <= set(tvs.PACKS), f["id"]


def test_a_formula_may_suit_no_style_in_particular():
    data = _valid()
    data["styles"] = []
    assert _check(data)["styles"] == []


def test_a_reference_file_carries_every_part_of_its_formula():
    f = tf.FORMULAS["incident-file"]
    text = tf.reference_markdown(f)
    assert text.startswith("# Incident File\n")
    assert "`formula_id`: `incident-file`" in text
    assert "190 to 240 words" in text
    for beat in f["beats"]:
        assert f"| {beat['name']} | {beat['from']} to {beat['to']}% |" in text
    for hook in f["hooks"]:
        assert f"(`{hook['type']}`)" in text and hook["shape"] in text
    for part in (f["holds"], f["ending"], f["template"], *f["pitfalls"]):
        assert part in text


def test_every_formula_marks_its_payoff_late_and_at_most_one_turn():
    # The scene author puts the strongest picture on the payoff and a visible
    # change on each turn and re-opening; a formula without them gives the
    # picture checks nothing to look for.
    for f in tf.FORMULAS.values():
        roles = [b.get("role") for b in f["beats"]]
        assert roles.count("payoff") == 1 and roles.count("turn") <= 1, f["id"]
        payoff = next(b for b in f["beats"] if b.get("role") == "payoff")
        assert payoff["from"] >= tf.PAYOFF_FROM_MIN, f["id"]
        assert f["first_frame"].strip(), f["id"]


def test_a_payoff_in_the_first_half_is_refused():
    data = _valid()
    for b in data["beats"]:
        b.pop("role", None)
    data["beats"][1]["role"] = "payoff"
    with pytest.raises(tf.FormulaError) as err:
        _check(data)
    assert "50 percent or later" in str(err.value)


def test_beat_roles_and_first_frame_answer_for_known_unknown_and_blank():
    assert tf.beat_roles("broken-expectation") == {
        "Wrong suspect 1": "reopen", "Wrong suspect 2": "reopen", "Turn": "turn",
        "Root cause": "payoff"}
    assert tf.beat_roles("") == {} and tf.beat_roles("retired-formula") == {}
    assert tf.first_frame("broken-expectation").startswith("The failure happening")
    assert tf.first_frame(None) == "" and tf.first_frame("retired-formula") == ""


def test_a_reference_file_names_each_beat_duty_and_the_first_frame():
    f = tf.FORMULAS["paradox-mechanism-reframe"]
    text = tf.reference_markdown(f)
    assert "| Turn | 55 to 65% |" in text and tf.BEAT_ROLES["turn"] + " |" in text
    assert "## First frame" in text and f["first_frame"] in text


def test_hook_types_of_a_formula():
    assert tf.hook_types("broken-expectation") == ("problem", "myth", "question")
    assert tf.hook_types("") == () and tf.hook_types("retired-formula") == ()
