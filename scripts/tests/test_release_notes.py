"""Tests for scripts/release_notes.py — the release-notes extractor."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import release_notes


def _notes(tmp_path, body: str) -> Path:
    p = tmp_path / "notes.md"
    p.write_text(body)
    return p


def test_extracts_the_matching_section_without_its_heading(tmp_path):
    f = _notes(tmp_path, "# Release Notes\n\n## v1.2.3\n\n### Added\n\n- A thing.\n")
    out = release_notes.extract("1.2.3", f)
    assert "- A thing." in out
    assert "## v1.2.3" not in out


def test_a_v_prefixed_argument_resolves_the_same_section(tmp_path):
    """The git tag carries the v and the VERSION file does not; both spellings
    reach this from different callers."""
    f = _notes(tmp_path, "## v1.2.3\n\n- A thing.\n")
    assert release_notes.extract("v1.2.3", f) == release_notes.extract("1.2.3", f)


def test_a_later_version_section_stops_the_extract(tmp_path):
    f = _notes(tmp_path, "## v2.0.0\n\n- Newer.\n\n## v1.2.3\n\n- Older.\n")
    out = release_notes.extract("1.2.3", f)
    assert "Older." in out and "Newer." not in out


def test_a_horizontal_rule_stops_the_extract(tmp_path):
    f = _notes(tmp_path, "## v1.2.3\n\n- A thing.\n\n---\n\nUnrelated trailing prose.\n")
    out = release_notes.extract("1.2.3", f)
    assert "A thing." in out and "Unrelated" not in out


def test_a_missing_section_is_an_error_naming_the_version(tmp_path):
    f = _notes(tmp_path, "## v1.2.3\n\n- A thing.\n")
    with pytest.raises(release_notes.ReleaseNotesError, match=r"no `## v9\.9\.9` section"):
        release_notes.extract("9.9.9", f)


def test_an_unfilled_skeleton_counts_as_missing(tmp_path):
    """The failure this guards is not a forgotten file -- it is a skeleton
    pasted in and left empty, which looks written and says nothing."""
    f = _notes(tmp_path, "## v1.2.3\n\n### Added\n- \n\n### Fixed\n- \n")
    with pytest.raises(release_notes.ReleaseNotesError, match="empty or still the unfilled"):
        release_notes.extract("1.2.3", f)


def test_a_prerelease_falls_back_to_its_base_version(tmp_path):
    """1.2.3-rc.1 is a candidate FOR 1.2.3, so it publishes that version's
    notes. Requiring a section per rehearsal tag is how a check gets worked
    around rather than satisfied."""
    f = _notes(tmp_path, "## v1.2.3\n\n- A thing.\n")
    assert "A thing." in release_notes.extract("1.2.3-rc.1", f)


def test_a_prerelease_with_its_own_section_wins_over_the_base(tmp_path):
    f = _notes(tmp_path, "## v1.2.3-rc.1\n\n- Candidate only.\n\n## v1.2.3\n\n- Final.\n")
    out = release_notes.extract("1.2.3-rc.1", f)
    assert "Candidate only." in out and "Final." not in out


def test_a_prerelease_whose_base_is_also_missing_names_both(tmp_path):
    f = _notes(tmp_path, "## v1.2.3\n\n- A thing.\n")
    with pytest.raises(release_notes.ReleaseNotesError, match=r"nor `## v7\.7\.7`"):
        release_notes.extract("7.7.7-rc.1", f)


def test_a_missing_file_is_an_error_not_a_crash(tmp_path):
    with pytest.raises(release_notes.ReleaseNotesError, match="cannot read"):
        release_notes.extract("1.2.3", tmp_path / "nope.md")


def test_the_real_page_has_written_notes_for_the_current_version():
    """The page shipped in this repo must satisfy its own rule -- otherwise
    the pre-flight check fails only at release time."""
    from tubematic_core.version import DEV_VERSION
    repo_root = Path(__file__).resolve().parents[2]
    notes = repo_root / release_notes.DEFAULT_NOTES_FILE
    version = (repo_root / "VERSION").read_text().strip()
    if version == DEV_VERSION:
        # The development branch has no number of its own; the page's newest
        # section is the release it is heading towards, so that is the one
        # that must be written.
        version = next(m.group("version") for line in notes.read_text().splitlines()
                       if (m := release_notes._HEADING_RE.match(line)))
    body = release_notes.extract(version, notes)
    assert body.strip()


# ── release_line (lives in tubematic_core.version; exercised here because the
#     release toolchain is what consumes it) ────────────────────────────────

def test_release_line_groups_patches_onto_one_branch():
    """1.0.1 and 1.0.2 are later TAGS on release/1.0.x, not branches of their
    own -- that is the whole point of the line model."""
    from tubematic_core.version import release_line
    assert release_line("1.0.0") == "release/1.0.x"
    assert release_line("1.0.1") == "release/1.0.x"
    assert release_line("1.0.9") == "release/1.0.x"
    assert release_line("1.1.0") == "release/1.1.x"
    assert release_line("2.3.9") == "release/2.3.x"


def test_release_line_ignores_a_prerelease_suffix():
    """A candidate belongs to the line it is a candidate for."""
    from tubematic_core.version import release_line
    assert release_line("1.0.0-rc.1") == "release/1.0.x"


def test_release_line_refuses_the_development_branch_marker():
    """The development branch belongs to no line; answering with one would
    point a maintainer at a branch that must never be tagged from develop."""
    import pytest
    from tubematic_core.version import DEV_VERSION, release_line
    with pytest.raises(ValueError):
        release_line(DEV_VERSION)


def test_release_line_never_names_a_point_release():
    """The failure this naming prevents: a branch called release/v1.0.0 that
    later contains 1.0.1 no longer describes its own contents."""
    from tubematic_core.version import release_line
    for v in ("1.0.0", "1.0.1", "2.3.9"):
        assert release_line(v).endswith(".x")
        assert "v" not in release_line(v).split("/", 1)[1]
