"""Script formulas as data (TMDEV-211): one file per formula, checked at import.

The script-writing skill's reference files are rendered from these files, the
script write checks a recorded formula and its hook types against them, and
the band warning reads each formula's word band. A file that loads with a gap
in it would therefore fail far from its cause: as a skill file with a hole, or
as a warning that never fires.
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


def _valid() -> dict:
    return copy.deepcopy(tf.FORMULAS["broken-expectation"])


def _check(data, stem="broken-expectation"):
    return tf._check_formula(pathlib.Path(f"{stem}.json"), data)


def test_the_ten_core_formulas_load_in_order():
    assert set(tf.FORMULAS) == CORE
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
    # Dialogue formulas need a voice per segment, which the pipeline does not
    # have. One slipping in would produce a script nobody can voice.
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
    assert set(out["formulas"][0]) == {"id", "label", "family", "line", "words"}
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
    (lambda d: d["hooks"][0].update(type="shout"), "hooks[0].type"),
    (lambda d: d["hooks"][1].update(type=d["hooks"][0]["type"]), "different type"),
    (lambda d: d.update(hooks=d["hooks"][:2]), "at least 3"),
])
def test_a_malformed_formula_is_refused_with_the_reason(mutate, message):
    data = _valid()
    mutate(data)
    with pytest.raises(tf.FormulaError) as err:
        _check(data)
    assert message in str(err.value)


def test_the_decision_table_has_one_row_per_formula():
    table = tf.decision_table_markdown()
    rows = [line for line in table.splitlines()[2:] if line.strip()]
    assert len(rows) == len(tf.FORMULAS)
    for f in tf.FORMULAS.values():
        assert f"(`{f['id']}`)" in table
        assert f"{f['words'][0]} to {f['words'][1]}" in table


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
