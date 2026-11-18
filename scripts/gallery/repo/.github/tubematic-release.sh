#!/usr/bin/env bash
# Which Tubematic reviews and publishes this gallery: the newest published release (highest version,
# drafts and prereleases skipped), so nothing here is edited when Tubematic releases. Writes `ref`
# (the tag to check out) and `image` (the backend image that renders examples) to $GITHUB_OUTPUT.
# 2.4.0 is the first release with scripts/gallery.py and external-style rendering: while the newest
# release is older, the scripts come from develop and `image` is empty, so no example is rendered.
set -euo pipefail
FLOOR=2.4.0
URL=${TUBEMATIC_RELEASES_URL:-https://api.github.com/repos/teja156/tubematic/releases?per_page=100}
auth=()
if [ -n "${GH_TOKEN:-}" ]; then auth=(-H "Authorization: Bearer $GH_TOKEN"); fi
curl -fsSL "${auth[@]}" "$URL" | python3 -c '
import json, os, re, sys
floor = tuple(int(x) for x in sys.argv[1].split("."))
best = None
for release in json.load(sys.stdin):
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", release.get("tag_name") or "")
    if m and not release.get("draft") and not release.get("prerelease"):
        version = tuple(int(x) for x in m.groups())
        best = version if best is None else max(best, version)
with open(os.environ["GITHUB_OUTPUT"], "a") as out:
    if best is not None and best >= floor:
        v = ".".join(map(str, best))
        out.write(f"ref=v{v}\nimage=ghcr.io/teja156/tubematic-backend:{v}\n")
        print(f"Reviewing with Tubematic v{v}")
    else:
        out.write("ref=develop\nimage=\n")
        print(f"::notice::The newest Tubematic release predates {sys.argv[1]}: scripts from develop, no example render")
' "$FLOOR"
