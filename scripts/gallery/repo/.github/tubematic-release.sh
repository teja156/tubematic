#!/usr/bin/env bash
# Which Tubematic reviews and publishes this gallery: the newest published release (highest version,
# drafts and prereleases skipped), so nothing here is edited when Tubematic releases. Writes `ref`
# (the tag to check out) and `image` (the backend image that renders examples) to $GITHUB_OUTPUT.
# 2.4.0 is the first release with scripts/gallery.py and external-style rendering: while the newest
# release is older, the scripts come from develop and `image` is empty, so no example is rendered.
set -euo pipefail
exec python3 -c '
import json, os, re, sys, urllib.request

FLOOR = (2, 4, 0)
url = os.environ.get("TUBEMATIC_RELEASES_URL") or "https://api.github.com/repos/teja156/tubematic/releases?per_page=100"
headers = {"Accept": "application/vnd.github+json"}
if os.environ.get("GH_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]

best = None
while url:  # every page: GitHub lists at most 100 releases per page, newest first by date
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
        releases = json.load(resp)
        nxt = re.search(r"<([^>]+)>;\s*rel=\"next\"", resp.headers.get("Link") or "")
    for release in releases:
        m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", release.get("tag_name") or "")
        if m and not release.get("draft") and not release.get("prerelease"):
            version = tuple(int(x) for x in m.groups())
            best = version if best is None else max(best, version)
    url = nxt.group(1) if nxt else None

with open(os.environ["GITHUB_OUTPUT"], "a") as out:
    if best is not None and best >= FLOOR:
        v = ".".join(map(str, best))
        out.write(f"ref=v{v}\nimage=ghcr.io/teja156/tubematic-backend:{v}\n")
        print(f"Reviewing with Tubematic v{v}")
    else:
        out.write("ref=develop\nimage=\n")
        print("::notice::The newest Tubematic release predates 2.4.0: scripts from develop, no example render")
'
