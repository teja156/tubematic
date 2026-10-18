"""Executor is the single dry-run choke point: in dry mode it must record
intents and perform zero real mutations; in live mode it must actually do
the thing."""
from onboard.executor import Executor


def test_dry_run_performs_zero_mutations(tmp_path):
    ex = Executor(dry_run=True)
    target_file = tmp_path / "sub" / "f.txt"
    target_dir = tmp_path / "newdir"
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello")
    dst = tmp_path / "dst"

    r = ex.run(["true"])
    ex.write_file(target_file, "content")
    ex.mkdir(target_dir)
    ex.touch(tmp_path / "touched")
    ex.copy_file(src / "a.txt", tmp_path / "copied.txt")
    ex.copytree(src, dst)
    ex.chown(src, 0, 0)
    ex.sqlite_write(tmp_path / "db.sqlite", lambda con: con.execute("CREATE TABLE t (x)"), "create t")
    cr = ex.crontab_write("fake crontab content\n")

    assert r.returncode == 0
    assert cr.returncode == 0
    assert not target_file.exists()
    assert not target_dir.exists()
    assert not (tmp_path / "touched").exists()
    assert not (tmp_path / "copied.txt").exists()
    assert not dst.exists()
    assert not (tmp_path / "db.sqlite").exists()

    # Every mutating call recorded an intent.
    assert len(ex.intents) == 9
    kinds = [i.kind for i in ex.intents]
    assert kinds == ["run", "write_file", "mkdir", "touch", "copy_file", "copytree",
                      "chown", "sqlite_write", "crontab_write"]


def test_live_run_actually_mutates(tmp_path):
    ex = Executor(dry_run=False)
    target_file = tmp_path / "f.txt"
    ex.write_file(target_file, "hello")
    assert target_file.read_text() == "hello"

    target_dir = tmp_path / "d"
    ex.mkdir(target_dir)
    assert target_dir.is_dir()

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")
    dst = tmp_path / "dst"
    ex.copytree(src, dst)
    assert (dst / "a.txt").read_text() == "x"

    db_path = tmp_path / "db.sqlite"
    ex.sqlite_write(db_path, lambda con: con.execute("CREATE TABLE t (x)"), "create t")
    assert db_path.exists()

    assert ex.intents == []  # live mode never records intents
