"""Test helper: an angle a research proposal can be filed with (TMDEV-214).

create_video refuses a curriculum, trending or mining topic that carries no
angle, so every test that files one for another reason passes this along.
"""

ANGLE = {
    "angle": "The request finishes before the page it asked for has been built.",
    "angle_kind": "process",
    "angle_score": 7,
}


def mined(topic, score=8, **over) -> dict:
    """One candidate as the mining model returns it, angle included."""
    return {"topic": topic, "producibility_score": score, **ANGLE, **over}
