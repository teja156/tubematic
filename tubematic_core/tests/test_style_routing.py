"""Auto's style routing (TMDEV-203): the candidate list and the topic set.

Routing itself is the agent's judgement, made by the tubematic-style-routing
skill from data, so no test here can run it; scripts/eval_style_routing.py
does, by hand. What CI can hold is everything around that judgement:

- the candidate list is read from the packs (a new pack is a candidate with no
  edit anywhere) and its gates match the ones that refuse a choice;
- the fixed topic set names only real outcomes, and every pack is the expected
  answer for enough topics that the eval measures it. A new pack fails here
  until its ticket adds its topics, which is what keeps the set growing with
  the packs instead of going stale.
"""
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import visual_styles as tvs  # noqa: E402

CASES_PATH = pathlib.Path(__file__).resolve().parent / "fixtures" / "style_routing_cases.json"
CASES = json.loads(CASES_PATH.read_text())["cases"]
MIN_CASES_PER_OUTCOME = 3


def _by_id(**kw):
    return {c["id"]: c for c in tvs.routing_candidates(**kw)}


# ── the candidate list ───────────────────────────────────────────────────────

def test_every_pack_and_mixed_scenes_is_a_candidate_in_pack_order():
    ids = [c["id"] for c in tvs.routing_candidates(True, "working", False)]
    assert ids == list(tvs.PACKS) + [tvs.SCENES]
    assert tvs.ROUTE_CHOICES == tuple(ids)


def test_a_new_pack_becomes_a_candidate_with_no_other_edit(monkeypatch):
    extra = json.loads((tvs.PACKS_DIR / "stick.json").read_text())
    extra.update(id="zz_new", label="New Style", order=999)
    monkeypatch.setitem(tvs.PACKS, "zz_new", tvs._check_pack(pathlib.Path("zz_new.json"), extra))
    ids = [c["id"] for c in tvs.routing_candidates(True, "working", False)]
    assert ids[-2:] == ["zz_new", tvs.SCENES]


def test_each_candidate_carries_its_routing_block_and_cost():
    for c in tvs.routing_candidates(True, "working", False):
        for key in ("best_for", "avoid_for", "signals", "moods", "images"):
            assert key in c["routing"], (c["id"], key)
        assert c["images"] == c["routing"]["images"]
        assert c["authoring_skill"]
    assert _by_id(openai_key_set=True, gpu_status="working", has_mascot=False)["system_flow"]["images"] == 0


@pytest.mark.parametrize("key, gpu, mascot, unavailable", [
    (True, "working", False, {}),
    (False, "working", False, {"illustrated": "needs an OpenAI key", "under_the_hood": "needs an OpenAI key"}),
    (True, "unknown", False, {"cartoon_3d": "GPU not tested yet"}),
    (True, "not_usable", False, {"cartoon_3d": "needs a working GPU"}),
    (True, "working", True, {"cartoon_3d": tvs.MASCOT_EXCLUDES_3D, "under_the_hood": tvs.MASCOT_EXCLUDED}),
])
def test_the_gates_match_what_refuses_the_choice(key, gpu, mascot, unavailable):
    rows = _by_id(openai_key_set=key, gpu_status=gpu, has_mascot=mascot)
    got = {sid: r["unavailable_reason"] for sid, r in rows.items() if not r["available"]}
    assert got == unavailable
    assert rows[tvs.SCENES]["available"]  # the fallback is always there


def test_a_candidate_list_never_shares_state_with_the_packs():
    rows = tvs.routing_candidates(True, "working", False)
    rows[0]["routing"]["best_for"].append("mutated")
    rows[-1]["routing"]["signals"].append("mutated")
    again = tvs.routing_candidates(True, "working", False)
    assert "mutated" not in again[0]["routing"]["best_for"]
    assert "mutated" not in tvs.PACKS[again[0]["id"]]["routing"]["best_for"]
    assert "mutated" not in again[-1]["routing"]["signals"]
    assert "mutated" not in tvs.SCENES_ROUTING["signals"]


def test_route_labels():
    assert tvs.route_label(tvs.SCENES) == "Mixed scenes"
    assert tvs.route_label("system_flow") == "System Flow"


def test_scenes_cannot_be_a_pack():
    data = json.loads((tvs.PACKS_DIR / "stick.json").read_text())
    data["id"] = tvs.SCENES
    with pytest.raises(tvs.PackError, match="mixed scene system"):
        tvs._check_pack(pathlib.Path("scenes.json"), data)


# ── the fixed topic set ──────────────────────────────────────────────────────

def test_every_case_names_only_real_outcomes():
    for case in CASES:
        assert case["title"].strip() and case["brief"].strip()
        assert case["expect"], case["title"]
        for sid in case["expect"] + case["ok"]:
            assert sid in tvs.ROUTE_CHOICES, (case["title"], sid)
        assert not set(case["expect"]) & set(case["ok"]), case["title"]


def test_titles_are_unique():
    titles = [c["title"] for c in CASES]
    assert len(titles) == len(set(titles))


@pytest.mark.parametrize("outcome", tvs.ROUTE_CHOICES)
def test_every_outcome_is_the_expected_answer_for_enough_topics(outcome):
    n = sum(1 for c in CASES if c["expect"][0] == outcome)
    assert n >= MIN_CASES_PER_OUTCOME, (
        f"{outcome!r} is the first expectation of {n} topics in {CASES_PATH.name}; add at least "
        f"{MIN_CASES_PER_OUTCOME} so the routing eval measures it (see "
        "docs/developer/test-suites/style-routing.md)")
