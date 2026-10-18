#!/usr/bin/env bash
# kasm_workspace/image/kasm_post_run_root.sh
#
# Baked over the base image's /dockerstartup/kasm_post_run_root.sh stub. Kasm's
# agent runs it as root, from outside the container, after every session start
# (proven on the testing workspace: it fires with no Docker Exec Config). Its
# timing is the agent's, not ours, so it does one thing and returns at once:
# it backgrounds a wait for the desktop, then opens the installer terminal on
# the user's display, as the session user.
#
# Why the root hook and not kasm_post_run_user.sh, which would need no
# privilege drop: the root hook is the only one with evidence of automatic
# invocation. Swapping is a small change if a live session ever proves the
# user hook fires too.
#
# Everything the installer writes must be owned by the session user (uid
# 1000), never root: the extracted tree, ~/.tubematic-data, the onboarding
# state, the compose bind sources. So the terminal -- and therefore the
# install -- runs as kasm-user, never as root.
#
# The launch-form selections are NOT read here. The bootstrap reads them, so a
# bad selection is reported in the window the user is looking at.
#
# Runs as root, so $HOME is /root: the session user's home is hardcoded.

set -uo pipefail  # not -e: a failed step is logged, never a silent exit

KASM_USER="kasm-user"
KASM_USER_HOME="/home/kasm-user"
LOG_FILE="$KASM_USER_HOME/.tubematic-workspace.log"

# Bound on the desktop wait. /usr/bin/desktop_ready is an unbounded `until`
# loop; a session whose desktop never comes up must not leave this waiting
# forever.
DESKTOP_WAIT_SECS=600
# desktop_ready-style detection returns on a mere xfce4-session PID, mid
# startup, so the first window can fail to land. Retry a few times.
LAUNCH_ATTEMPTS=3
# A launch has landed if the terminal is still running this long after it
# started; --disable-server below ties the process to its window.
LANDED_AFTER_SECS=5

# Created by root, so hand it to the session user before writing: a root-owned
# file in a persisted profile is the leftover that breaks host-side scripts.
touch "$LOG_FILE" 2>/dev/null && chown 1000:1000 "$LOG_FILE" 2>/dev/null
exec >>"$LOG_FILE" 2>&1

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

open_installer() {
    local waited=0
    until pidof xfce4-session >/dev/null 2>&1; do
        if [ "$waited" -ge "$DESKTOP_WAIT_SECS" ]; then
            log "Gave up waiting for the desktop after ${DESKTOP_WAIT_SECS}s; no installer window opened."
            log "Open it from the desktop launcher, or run: tubematic-installer"
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    log "Desktop session found after ${waited}s."
    sleep 3  # let the window manager and panel settle

    local attempt pid
    for attempt in $(seq 1 "$LAUNCH_ATTEMPTS"); do
        # DISPLAY is passed explicitly rather than trusted to reach the
        # agent's exec through the image ENV.
        runuser -u "$KASM_USER" -- env DISPLAY=:1 HOME="$KASM_USER_HOME" \
            xfce4-terminal --disable-server --title "Tubematic installer" \
            --geometry 120x36 -x tubematic-installer &
        pid=$!
        sleep "$LANDED_AFTER_SECS"
        if kill -0 "$pid" 2>/dev/null; then
            log "Installer window opened (attempt $attempt)."
            return 0
        fi
        wait "$pid"
        log "Installer window did not stay open (attempt $attempt, exit $?); retrying."
        sleep 3
    done
    log "Could not open the installer window after $LAUNCH_ATTEMPTS attempts."
    log "Open it from the desktop launcher, or run: tubematic-installer"
    return 1
}

if [ "${1:-}" = "--open-installer" ]; then
    open_installer
    exit $?
fi

log "=== tubematic workspace launch hook (running as $(id -un)) ==="
# Re-run as a detached session leader so the hook returns promptly and the
# wait outlives the agent's exec: whether the Kasm agent waits for this hook
# to exit is not known, and blocking here could stall session startup.
setsid "$0" --open-installer </dev/null >>"$LOG_FILE" 2>&1 &
log "Installer launch backgrounded; hook done."
exit 0
