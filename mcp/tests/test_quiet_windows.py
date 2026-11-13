"""mcp/quiet_windows.py: the windows a stillness rule skips."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import quiet_windows as qw  # noqa: E402


def _w(*spans):
    return [{"startFrame": a, "endFrame": b} for a, b in spans]


def test_a_gap_of_a_pause_or_more_between_words_is_a_silent_window():
    words = _w((0, 10), (14, 20), (1265, 1275), (1086 - 90, 1176))
    # 4 frames is breathing; the stretch after "1176" up to the next word is a pause
    assert qw.silent_windows(words) == [(20, 996), (1176, 1265)]
    assert qw.silent_windows(_w((0, 10), (22, 30))) == [(10, 22)]
    assert qw.silent_windows(_w((0, 10), (21, 30))) == []


def test_a_malformed_or_missing_word_list_has_no_silences():
    assert qw.silent_windows(None) == [] and qw.silent_windows([{"word": "x"}, 3]) == []


def test_windows_merge_sorted_and_without_overlap():
    assert qw.merged([(10, 20), (5, 12)], [(30, 40)], None) == [(5, 20), (30, 40)]
    assert qw.merged() == []
