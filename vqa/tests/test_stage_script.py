"""Tests for vqa/stage_script.py — staging the script + broll and the
ElevenLabs-bound text as plain-text files for human review."""
import shutil
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "vqa"))

from stage_script import stage_script  # noqa: E402


class FakeMcpServer:
    """Minimal stand-in for mcp/server.py's private-function surface.

    Deliberately trivial (no-op) transform functions: the point of these
    tests is stage_script.py's own orchestration (call order, file paths,
    error handling), not whether phoneme-stripping/respell/lexicon
    substitution behave correctly — that's mcp/server.py's own 270-test
    suite's job. The one subprocess test below imports the REAL
    mcp/server.py and proves the two actually integrate correctly.
    """

    ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

    def __init__(self, video, settings=None):
        self._video = video
        self._settings = settings or {}

    @contextmanager
    def _conn(self):
        yield None

    def _fetch_video(self, con, video_id):
        if video_id != self._video.get("id"):
            return None
        return dict(self._video)

    def _get_setting(self, key, default=""):
        return self._settings.get(key, default)

    def _get_lexicon(self):
        return self._settings.get("pronunciation_lexicon", [])

    def _join_segment_voice(self, segments):
        return " ".join(seg["voice"].strip() for seg in segments)

    def _build_tts_text(self, joined, mode, lexicon):
        return joined

    def _check_ipa_model(self, text, model_id, voice_label=""):
        return self._settings.get("ipa_error")

    def _check_phoneme_model(self, text, model_id, voice_label=""):
        return self._settings.get("phoneme_error")

    def _resolve_voice(self, video_voice_id):
        if self._settings.get("no_voice"):
            return None
        return {"name": "Rachel", "voice_id": video_voice_id or "r1",
                "model_id": "eleven_multilingual_v2", "source": "install"}

    def _pronunciation_mode_for_model(self, model_id):
        return "respell"


_SEGMENTS = [
    {"id": "intro", "voice": "Binary search is fast.", "visual": "Show a sorted array."},
    {"id": "compare", "voice": "Look at the middle element.", "visual": "Highlight it."},
]


def _video(video_id="vid_test", status="VOICING", segments=_SEGMENTS):
    return {"id": video_id, "status": status, "script_segments": segments}


class TestStageScript:
    def test_broll_file_formats_each_segment(self, tmp_path):
        broll_path, _ = stage_script("vid_test", tmp_path, mcp_server=FakeMcpServer(_video()))
        content = broll_path.read_text()
        assert "Segment 1 (id: intro)" in content
        assert "VOICE:  Binary search is fast." in content
        assert "VISUAL: Show a sorted array." in content
        assert "Segment 2 (id: compare)" in content
        assert "VOICE:  Look at the middle element." in content
        assert "VISUAL: Highlight it." in content

    def test_broll_file_handles_empty_visual(self, tmp_path):
        segments = [{"id": "a", "voice": "Hello.", "visual": ""}]
        broll_path, _ = stage_script(
            "vid_test", tmp_path, mcp_server=FakeMcpServer(_video(segments=segments))
        )
        assert "VISUAL: (none)" in broll_path.read_text()

    def test_tts_text_file_written(self, tmp_path):
        _, tts_path = stage_script("vid_test", tmp_path, mcp_server=FakeMcpServer(_video()))
        assert tts_path.read_text().strip() == "Binary search is fast. Look at the middle element."

    def test_files_written_under_correct_job_dir(self, tmp_path):
        broll_path, tts_path = stage_script(
            "vid_abc123", tmp_path, mcp_server=FakeMcpServer(_video(video_id="vid_abc123"))
        )
        expected_dir = tmp_path / "jobs" / "vid_abc123"
        assert broll_path == expected_dir / "script_with_broll.txt"
        assert tts_path == expected_dir / "tts_text.txt"

    def test_unknown_video_id_errors(self, tmp_path):
        with pytest.raises(SystemExit, match="No video found"):
            stage_script("vid_nope", tmp_path, mcp_server=FakeMcpServer(_video()))

    def test_no_script_segments_errors_naming_status(self, tmp_path):
        video = _video(status="TOPIC_APPROVED", segments=None)
        with pytest.raises(SystemExit, match="no script_segments yet.*TOPIC_APPROVED"):
            stage_script("vid_test", tmp_path, mcp_server=FakeMcpServer(video))

    def test_a_script_generate_voice_would_refuse_is_not_staged(self, tmp_path):
        """tts_text.txt is the pre-spend review artifact: staging IPA that
        generate_voice will refuse on this model would show text never sent."""
        fake = FakeMcpServer(_video(), settings={"ipa_error": "voice text uses <ipa> tags"})
        with pytest.raises(SystemExit, match="<ipa>"):
            stage_script("vid_test", tmp_path, mcp_server=fake)
        assert not (tmp_path / "jobs" / "vid_test").exists()

    def test_phoneme_tags_its_voice_would_strip_are_not_staged(self, tmp_path):
        fake = FakeMcpServer(_video(), settings={"phoneme_error": "voice text uses <phoneme> tags"})
        with pytest.raises(SystemExit, match="<phoneme>"):
            stage_script("vid_test", tmp_path, mcp_server=fake)
        assert not (tmp_path / "jobs" / "vid_test").exists()

    def test_a_video_with_no_voice_is_not_staged(self, tmp_path):
        """No voice means no model to derive the pronunciation from, and
        generate_voice would refuse before spend too."""
        fake = FakeMcpServer(_video(), settings={"no_voice": True})
        with pytest.raises(SystemExit, match="no voice"):
            stage_script("vid_test", tmp_path, mcp_server=fake)

    def test_rerunning_overwrites_both_files(self, tmp_path):
        stage_script("vid_test", tmp_path, mcp_server=FakeMcpServer(_video()))
        different_segments = [{"id": "only", "voice": "Different text.", "visual": "Different visual."}]
        broll_path, tts_path = stage_script(
            "vid_test", tmp_path,
            mcp_server=FakeMcpServer(_video(segments=different_segments)),
        )
        assert "Different text." in tts_path.read_text()
        assert "Different visual." in broll_path.read_text()

    @pytest.mark.parametrize("bad", ["../outside", "ABSOLUTE", "..", ".", "a/b"])
    def test_an_existing_row_with_an_escaping_id_writes_nothing_outside_jobs(self, tmp_path,
                                                                              bad):
        """A row filed before ids were checked (or tampered with) is found in
        the database, so the lookup is no guard. The job dir is derived
        through tubematic_core.jobfiles, which refuses the id."""
        root = tmp_path / "data"
        (root / "jobs").mkdir(parents=True)
        if bad == "ABSOLUTE":
            bad = str(tmp_path / "abs")
        before = sorted(str(p) for p in tmp_path.rglob("*"))
        with pytest.raises(SystemExit, match="cannot stage"):
            stage_script(bad, root, mcp_server=FakeMcpServer(_video(video_id=bad)))
        assert sorted(str(p) for p in tmp_path.rglob("*")) == before

    def test_a_job_dir_symlinked_elsewhere_is_refused(self, tmp_path):
        root = tmp_path / "data"
        (root / "jobs").mkdir(parents=True)
        (root / "jobs" / "vid_b").mkdir()
        (root / "jobs" / "vid_test").symlink_to(root / "jobs" / "vid_b")
        with pytest.raises(SystemExit, match="cannot stage"):
            stage_script("vid_test", root, mcp_server=FakeMcpServer(_video()))
        assert list((root / "jobs" / "vid_b").iterdir()) == []

    def test_a_symlinked_output_file_is_refused(self, tmp_path):
        root = tmp_path / "data"
        job = root / "jobs" / "vid_test"
        job.mkdir(parents=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("keep me")
        (job / "tts_text.txt").symlink_to(victim)
        with pytest.raises(SystemExit, match="cannot stage"):
            stage_script("vid_test", root, mcp_server=FakeMcpServer(_video()))
        assert victim.read_text() == "keep me"

    def test_a_legacy_id_with_a_dot_still_stages(self, tmp_path):
        broll_path, _ = stage_script("a.b", tmp_path, mcp_server=FakeMcpServer(_video(video_id="a.b")))
        assert broll_path == tmp_path / "jobs" / "a.b" / "script_with_broll.txt"


class TestRealMcpServerIntegration:
    """Copies vqa/stage_script.py + mcp/server.py (its one real dependency,
    no further intra-repo imports) into an isolated tree, seeds a real DB
    with a lexicon substitution in play, and runs via subprocess — proving
    (a) the real mcp/server.py private functions are wired correctly, not
    just the fake's trivial stand-ins, and (b) stage_script.py resolves its
    own location from __file__, not cwd (same regression the review_video.py
    suite guards — the /opt vs ~/tubematic split depends on this)."""

    def test_real_derivation_and_root_resolution(self, tmp_path):
        isolated = tmp_path / "isolated_tree"
        (isolated / "vqa").mkdir(parents=True)
        (isolated / "mcp").mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "vqa" / "stage_script.py", isolated / "vqa" / "stage_script.py")
        shutil.copy2(REPO_ROOT / "mcp" / "server.py", isolated / "mcp" / "server.py")
        # The shared tubematic_core package. An isolated tree has to bring it
        # like any other import: in the container it arrives on PYTHONPATH
        # (/app/lib), which this reconstruction deliberately does not have.
        shutil.copytree(REPO_ROOT / "tubematic_core", isolated / "tubematic_core",
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))

        # The data root is HOME-relative (TMDEV-76) and deliberately NOT
        # inside `isolated` — the script must read the tree the containers
        # write to, not one beside itself or under cwd.
        fake_home = tmp_path / "home"
        db_path = fake_home / ".tubematic-data" / "data" / "tubematic.db"
        db_path.parent.mkdir(parents=True)
        con = sqlite3.connect(str(db_path))
        con.execute("""
            CREATE TABLE videos (
                id TEXT PRIMARY KEY, project_id TEXT, topic TEXT, strategy TEXT DEFAULT 'manual',
                producibility_score INTEGER DEFAULT 0, status TEXT, title TEXT DEFAULT '',
                script TEXT DEFAULT '', voice_file_path TEXT DEFAULT '', timeline_path TEXT DEFAULT '',
                scene_config_path TEXT DEFAULT '', video_path TEXT DEFAULT '', video_version INTEGER DEFAULT 1,
                gemini_feedback TEXT DEFAULT '', youtube_url TEXT DEFAULT '', voice_id TEXT DEFAULT '',
                cost_cents_elevenlabs INTEGER DEFAULT 0, cost_cents_gemini INTEGER DEFAULT 0,
                cost_cents_claude INTEGER DEFAULT 0, ai_review_count INTEGER DEFAULT 0,
                render_fail_count INTEGER DEFAULT 0, script_segments TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)
        con.execute("CREATE TABLE comments (id INTEGER PRIMARY KEY, video_id TEXT, author TEXT, content TEXT, created_at TEXT)")
        con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        import json as _json
        segments = [{"id": "a", "voice": 'The gene Vhagar is <ipa ph="ɪmˈpɔːrtənt">important</ipa>.',
                     "visual": "Zoom in."}]
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, script_segments, created_at, updated_at) "
            "VALUES ('vid_real', 'proj_vqa', 'topic', 'VOICING', ?, datetime('now'), datetime('now'))",
            (_json.dumps(segments),),
        )
        # A lexicon entry that only takes effect if the REAL _apply_lexicon runs —
        # the fake's no-op version above would leave "Vhagar" unsubstituted.
        con.execute(
            "INSERT INTO settings (key, value) VALUES ('pronunciation_lexicon', ?)",
            (_json.dumps([{"term": "Vhagar", "respell": "Vah-gar"}]),),
        )
        # On eleven_v3 the real _build_tts_text writes an <ipa> tag as "/.../".
        # The model is the voice's own, so the video's (default) voice is on v3.
        con.execute("INSERT INTO settings (key, value) VALUES ('elevenlabs_voices', ?)", (
            _json.dumps([{"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"}]),))
        con.execute("INSERT INTO settings (key, value) VALUES ('elevenlabs_voice_id', 'a1')")
        con.commit()
        con.close()

        result = subprocess.run(
            [sys.executable, str(isolated / "vqa" / "stage_script.py"), "vid_real"],
            cwd="/",  # deliberately not `isolated` — proves resolution isn't cwd-based
            capture_output=True,
            text=True,
            # PYTHONPATH mirrors the container, where the shared package sits at
            # /app/lib (renderer/Dockerfile). Pointed at the isolated root, not the
            # repo, so the test still proves nothing is read from outside this tree.
            env={"PATH": "/usr/bin:/bin", "HOME": str(fake_home),
                 "PYTHONPATH": str(isolated)},
        )

        assert result.returncode == 0, result.stderr
        tts_text = (fake_home / ".tubematic-data" / "jobs" / "vid_real" / "tts_text.txt").read_text()
        assert "Vah-gar" in tts_text, "real _apply_lexicon should have substituted the term"
        assert "Vhagar" not in tts_text
        assert '"/ɪmˈpɔːrtənt/".' in tts_text, "real _build_tts_text should have rewritten <ipa>"
