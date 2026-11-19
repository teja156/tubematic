#!/usr/bin/env bash
# Who submitted each style: the author of the merged pull request that added it, so the gallery
# shows a name GitHub vouches for, never the one a package writes for itself. A commit's linked
# account is not used: GitHub finds it from the commit's email, which anyone can write. The addition
# is that of the style's marker (style.json, or the pointer), followed across renames, and the most
# recent one, so a style deleted and re-added belongs to whoever re-added it. A style with no merged
# pull request, or whose lookup fails, keeps its package's name (left out here).
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
    marker = entry if entry.suffix == ".json" else entry / "style.json"
    added = subprocess.run(["git", "log", "--follow", "--diff-filter=A", "--format=%H", "--", str(marker)],
                           check=True, capture_output=True, text=True).stdout.split()
    if not added:
        continue
    sha = added[0]   # newest first: the addition of the style as it is now
    pulls = get(f"/repos/{repo}/commits/{sha}/pulls") or []
    login = next((p["user"]["login"] for p in pulls
                  if isinstance(p, dict) and p.get("merged_at") and isinstance(p.get("user"), dict)), None)
    if login:
        authors[sid] = login
        print(f"{sid}: {login}")
    else:
        print(f"::notice::{sid}: no merged pull request found for {sha}; the package names its author")

pathlib.Path(out).write_text(json.dumps(authors, indent=1, sort_keys=True) + "\n")
' "$@"
