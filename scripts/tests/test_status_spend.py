"""status.py's spend summary (TMDEV-107).

The CLI summary used to add three per-video cost columns that nothing had
written since the usage ledger replaced them. It now reads the ledger, and it
must keep the same honesty rules the dashboard does: unpriced calls are called
out rather than counted as $0, ElevenLabs is credits, and a database that has
not been migrated yet says so instead of crashing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import status  # noqa: E402
from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import usage as tusage  # noqa: E402


def test_the_summary_reads_the_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    db_file = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db_file)
    monkeypatch.setattr(status, "DB_FILE", db_file)
    tusage.record_usage(db_file, service="anthropic", model="claude-sonnet-5",
                        operation="agent_pipeline", reported_cost_usd=1.25, videos=["v1"])
    tusage.record_usage(db_file, service="elevenlabs", model="eleven_v3", operation="voice",
                        units={"credits": 1240}, videos=["v1"])
    tusage.record_usage(db_file, service="gemini", model="gemini-9-flash", operation="mining",
                        units={"input": 5})

    status.show_cost_summary()

    out = capsys.readouterr().out
    assert "$1.25" in out
    assert "1 unpriced call" in out
    assert "1,240 credits" in out
    assert "API list prices" in out


def test_an_unmigrated_database_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(status, "DB_FILE", tmp_path / "data" / "empty.db")
    status.show_cost_summary()
    assert "No usage ledger yet" in capsys.readouterr().out
