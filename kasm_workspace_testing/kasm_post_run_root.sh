#!/usr/bin/env bash
# kasm_workspace_testing/kasm_post_run_root.sh
#
# Overwrites the base image's /dockerstartup/kasm_post_run_root.sh stub (a
# one-line echo) — Kasm's own root-context hook, invoked automatically after
# session start. Deployed as a File Mapping on the workspace, not baked into
# the image, so it MUST be mapped with "is_executable": true; mapped files are
# root-owned with no exec bit by default, and an inert hook looks exactly like
# Kasm never invoking one.
#
# Reads the launch-form selections written by launch_config.json's file_mapping
# and deletes the directories the tester asked to start clean without. Nothing
# else: no recreation, no onboarding, no stack management.
#
# AFTER A DATA WIPE, RE-RUN `python3 onboard.py` BEFORE STARTING THE STACK.
# Nothing here recreates ~/.tubematic-data. docker-compose.yml binds its four
# subdirectories by `device:` path, and dockerd auto-creates a missing bind
# source as root — invisible to the containers, fatal to host-side scripts, and
# unfixable by `mkdir -p`. onboard.py's `directories` step creates them owned
# by the session user, which is the only clean way back.
#
# Runs as root, so $HOME is /root — the session user's home is hardcoded below.
# jq is deliberately not used: it is not installed in this image (the Kasm docs'
# own example assumes it). python3 is present in the base image.

set -uo pipefail  # deliberately not -e: every branch below reports its own
                  # outcome, and a mid-script exit would leave the tester with
                  # no record of which directory was or wasn't deleted.

KASM_USER_HOME="/home/kasm-user"
SELECTIONS="/tmp/launch_selections.json"
LOG_FILE="$KASM_USER_HOME/.tubematic-launch-reset.log"

# Created by root, so hand it back to the session user — a root-owned file in
# the persisted profile is the exact class of leftover that breaks host-side
# scripts later.
touch "$LOG_FILE" 2>/dev/null && chown 1000:1000 "$LOG_FILE" 2>/dev/null
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# Deletes $target only on an explicit "yes". Every refusal is logged and
# non-fatal — this hook never blocks a session from starting.
delete_if_selected() {
    local answer="$1" target="$2" label="$3"

    if [ "$answer" != "yes" ]; then
        log "$label: keeping $target (selection: '${answer:-<unset>}')"
        return
    fi

    if [ ! -e "$target" ]; then
        log "$label: nothing to delete, $target does not exist"
        return
    fi

    if [ -L "$target" ] || [ ! -d "$target" ]; then
        log "REFUSED $label: $target is not a plain directory. Remove it by hand if that is intended."
        return
    fi

    # The -L test above covers a symlinked target; this covers a symlinked
    # ancestor, where the literal path below no longer names what it appears
    # to. Belt-and-braces — not reachable in normal operation.
    local resolved
    resolved="$(readlink -f "$target")"
    if [ "$resolved" != "$target" ]; then
        log "REFUSED $label: $target resolves to $resolved, outside its expected location."
        return
    fi

    log "$label: deleting $target ..."
    if rm -rf "$target"; then
        log "$label: deleted $target"
    else
        log "ERROR $label: rm -rf failed on $target"
    fi
}

log "=== tubematic launch-form reset hook (running as $(id -un)) ==="

if [ ! -f "$SELECTIONS" ]; then
    log "No launch selections at $SELECTIONS — deleting nothing."
    exit 0
fi

# One parse, two answers. Any failure here means the selections are unreadable,
# and an unreadable selection is never treated as consent to delete.
selections="$(python3 - "$SELECTIONS" <<'PY'
import json
import sys

KEYS = ("delete_tubematic_data", "delete_tubematic_agent")

with open(sys.argv[1]) as handle:
    data = json.load(handle)
if not isinstance(data, dict):
    raise SystemExit("launch selections is not a JSON object")
print(" ".join(str(data.get(key, "")).strip().lower() for key in KEYS))
PY
)"
if [ $? -ne 0 ]; then
    log "Could not read $SELECTIONS — deleting nothing."
    exit 0
fi

read -r delete_data delete_agent <<<"$selections"

delete_if_selected "${delete_data:-}"  "$KASM_USER_HOME/.tubematic-data"  "Tubematic data"
delete_if_selected "${delete_agent:-}" "$KASM_USER_HOME/.tubematic-agent" "Tubematic agent directory"

log "=== reset hook done ==="
exit 0
