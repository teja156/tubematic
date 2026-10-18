#!/usr/bin/env bash
# vqa/watch_bootstrap.sh
#
# Launched once, in the background, from vqa/custom_startup.sh — before
# kasm_startup's own supervisord-launch loop, so it never interacts with
# that loop's retry logic. Waits for the VQA bootstrap log to appear, then
# opens an xfce4-terminal tailing it.
#
# Purely a viewer: kasm_post_run_user.sh (the actual bootstrap) runs via its
# own Kasm-invoked hook regardless of whether this script ever finds the
# log, opens a window, or the window gets closed.

set -uo pipefail

LOG_FILE="/home/kasm-user/tubematic/vqa/logs/bootstrap.log"

for _ in $(seq 1 600); do
    [ -f "$LOG_FILE" ] && break
    sleep 1
done

/usr/bin/desktop_ready 2>/dev/null || true

if [ -f "$LOG_FILE" ]; then
    xfce4-terminal --title="VQA Bootstrap status: tail -f \"$LOG_FILE\"" \
        --command="bash -c 'tail -f \"$LOG_FILE\"; exec bash'"
else
    # Not a failure of bootstrap itself — kasm_post_run_user.sh is a
    # separate, externally-invoked hook this script has no control over.
    # Still open a terminal rather than silently doing nothing, so there's
    # some visible signal that the log never showed up.
    xfce4-terminal --hide-menubar --title="Tubematic VQA Bootstrap" \
        --command="bash -c 'echo \"No bootstrap log appeared at $LOG_FILE after 10 minutes.\"; echo \"kasm_post_run_user.sh may not have run yet, or at all — check the workspace registration.\"; exec bash'"
fi
