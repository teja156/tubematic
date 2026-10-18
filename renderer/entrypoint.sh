#!/bin/sh
set -e

# The container runs as root, but /data, /jobs, and /output_videos are host
# bind mounts, so every file it writes lands root-owned. The host user still
# has to read and write the SQLite DB (onboard.py seeds it; status.py reads
# it), and WAL mode means even a pure *reader* must write the -shm file — so
# permissions have to be widened somehow.
#
# Since TMDEV-73 that database also holds the API keys, so "world-writable"
# is no longer an acceptable default. Prefer the host user's group, taken
# from the bind mount itself, and fall back to the old behaviour only when
# the mount is root-owned — which happens when dockerd auto-creates a missing
# bind-mount source. Both the umask and the chmod key off the *same* probe:
# umask 002 under a root-owned /data would lock the host user out entirely,
# which is the exact failure this block exists to prevent.
#
# The shared logs directory gets the same treatment (TMDEV-94). It has a writer
# that is not a container: scripts/poll.py runs from cron as the host user and
# appends poll.<date>.jsonl beside the services' own files. If the directory is
# root-owned, the poller cannot create its file and every poll entry silently
# drops off the dashboard's Logs page. Setgid keeps the files the containers
# create there in the host group as well.
DB="${TUBEMATIC_DB:-/data/tubematic.db}"
DATA_DIR="$(dirname "$DB")"
LOG_DIR="${TUBEMATIC_LOG_DIR:-/logs}"
HOST_GID="$(stat -c %g "$DATA_DIR" 2>/dev/null || echo 0)"

if [ "$HOST_GID" != "0" ]; then
    umask 002
    chgrp "$HOST_GID" "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true
    chmod 0660        "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true
    # New WAL/SHM files inherit the group instead of landing root:root.
    chmod g+s "$DATA_DIR" 2>/dev/null || true
    chgrp "$HOST_GID" "$LOG_DIR" 2>/dev/null || true
    # rwx, not just w: without search (x) the group cannot create a file in
    # the directory at all, and without read poll.py cannot list it to prune.
    chmod g+rwxs      "$LOG_DIR" 2>/dev/null || true
else
    umask 000
    chmod a+rw "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true
    chmod a+rwx "$LOG_DIR" 2>/dev/null || true
    echo "entrypoint: $DATA_DIR is root-owned — falling back to world-writable DB" \
         "permissions. Fix with: sudo chown -R \$(id -u):\$(id -g) mounted/" >&2
fi

# Run the one process this container owns, passed as arguments (TMDEV-87).
#
# This script used to background Flask and exec the MCP server, so a single
# container ran two processes. That made supervision unreliable: if Flask died,
# PID 1 (MCP) kept running, the container stayed up, and `restart:
# unless-stopped` had nothing to act on — a dead dashboard behind a container
# that looked alive. Flask and MCP now have a service each and this script is
# the shared permission preamble for both, rather than a process launcher.
#
# tubematic-renderer deliberately does NOT come through here — its compose
# `command:` replaces the Dockerfile CMD outright, and worker.py sets its own
# os.umask(0).
exec "$@"
