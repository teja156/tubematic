"""No tracked text file holds a leftover merge-conflict marker.

A merge once committed `<<<<<<< HEAD` ... `>>>>>>> develop` into a public docs page, and nothing
failed: the docs checker reads names and links, not structure. The docs site published it.
"""
import pathlib
import re
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]
MARKER = re.compile(rb"^(<{7} |>{7} |\|{7} )", re.M)


def test_no_tracked_file_has_a_conflict_marker():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True,
                           capture_output=True).stdout.split(b"\0")
    hits = []
    for name in filter(None, files):
        path = REPO / name.decode()
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        data = path.read_bytes()
        if b"\0" in data[:4096]:
            continue  # binary
        if MARKER.search(data):
            hits.append(name.decode())
    assert hits == []
