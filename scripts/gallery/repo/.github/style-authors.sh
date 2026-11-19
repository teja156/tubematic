#!/usr/bin/env bash
# Who submitted each style: the GitHub account behind the commit that first added styles/<id>, so
# the gallery shows a name GitHub vouches for, never the one a package writes for itself. That is
# the author of the merged pull request the commit came in with, or, for a commit pushed straight to
# main, the commit's linked account. A style with neither keeps its package's name (left out here).
# Usage: bash .github/style-authors.sh <styles dir> <out.json>; needs the full history (fetch-depth 0).
set -euo pipefail
exec python3 -c '
import json, os, pathlib, subprocess, sys, urllib.error, urllib.request

styles, out = pathlib.Path(sys.argv[1]), sys.argv[2]
api = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
repo = os.environ["GITHUB_REPOSITORY"]
headers = {"Accept": "application/vnd.github+json"}
if os.environ.get("GH_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]


def get(path):
    try:
        with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"::warning::{path}: HTTP {exc.code}")
        return None


authors = {}
for entry in sorted(styles.iterdir()):
    sid = entry.stem if entry.suffix == ".json" else entry.name
    if entry.name.startswith("."):
        continue
    added = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", str(entry)],
                           check=True, capture_output=True, text=True).stdout.split()
    if not added:
        continue
    sha = added[-1]   # oldest first-add: the original submission, not a later re-add
    pulls = get(f"/repos/{repo}/commits/{sha}/pulls") or []
    login = next((p["user"]["login"] for p in pulls if p.get("merged_at") and p.get("user")), None)
    if login is None:
        login = ((get(f"/repos/{repo}/commits/{sha}") or {}).get("author") or {}).get("login")
    if login:
        authors[sid] = login
        print(f"{sid}: {login}")
    else:
        print(f"::notice::{sid}: no GitHub account found for {sha}; the package names its author")

pathlib.Path(out).write_text(json.dumps(authors, indent=1, sort_keys=True) + "\n")
' "$@"
