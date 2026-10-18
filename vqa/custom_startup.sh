#!/usr/bin/env bash
# vqa/custom_startup.sh
#
# Overwrites the base image's $STARTUPDIR/custom_startup.sh — this is the
# exact file the kasm_workspace/ image (this repo's other Kasm environment)
# deliberately avoids touching, after an earlier attempt in this repo's
# history (00099ff/a69cd1c/7abf2d0) edited it, hit a race, and was reverted.
# That incident was from inserting logic INSIDE the process-supervision
# while-loop below (auto-launching onboard.py, re-entering on every loop
# iteration until supervisord became visible to pgrep — the race). The one
# addition below is deliberately kept OUTSIDE that loop and backgrounded, so
# it can only ever run once and never interacts with the loop's own
# supervisord-launch retry logic.
#
# Everything below the shebang, except the clearly-marked addition, is
# byte-for-byte identical to kasmweb/ubuntu-noble-dind:1.19.0-rolling-daily's
# own $STARTUPDIR/custom_startup.sh (diffed against a fresh pull of that
# image to confirm) — verify against a fresh base-image pull before ever
# changing anything outside the marked block; this file being wrong disables
# Docker-in-Docker entirely (dockerd is what START_COMMAND launches via
# supervisord).
set -ex
START_COMMAND="/usr/bin/supervisord"
PGREP="supervisord"
DEFAULT_ARGS="-n"
ARGS=${APP_ARGS:-$DEFAULT_ARGS}

options=$(getopt -o gau: -l go,assign,url: -n "$0" -- "$@") || exit
eval set -- "$options"

while [[ $1 != -- ]]; do
    case $1 in
        -g|--go) GO='true'; shift 1;;
        -a|--assign) ASSIGN='true'; shift 1;;
        -u|--url) OPT_URL=$2; shift 2;;
        *) echo "bad option: $1" >&2; exit 1;;
    esac
done
shift

# Process non-option arguments.
for arg; do
    echo "arg! $arg"
done

FORCE=$2

# --- TMDEV-68 addition: auto-open a terminal tailing the VQA bootstrap log ---
# Launched exactly once, in the background, before kasm_startup's own loop
# begins — never touches that loop's supervisord-launch retry logic. Runs
# from /opt/tubematic (image-owned, always present at container start) not
# ~/tubematic (the working tree, which doesn't exist yet at this point —
# kasm_post_run_user.sh is what creates it, and that's a separate hook Kasm
# invokes after this script, not something this script waits for or calls).
/opt/tubematic/vqa/watch_bootstrap.sh &
# --- end TMDEV-68 addition ---

kasm_startup() {
    if [ -n "$KASM_URL" ] ; then
        URL=$KASM_URL
    elif [ -z "$URL" ] ; then
        URL=$LAUNCH_URL
    fi

    if  [ -z "$DISABLE_CUSTOM_STARTUP" ] ||  [ -n "$FORCE" ]  ; then

        echo "Entering process startup loop"
        set +x
        while true
        do
            if ! pgrep -x $PGREP > /dev/null
            then
                /usr/bin/filter_ready
                /usr/bin/desktop_ready
                set +e
                sudo /usr/bin/supervisord -n &
                set -e
            fi
            sleep 1
        done
        set -x
    
    fi

} 

kasm_startup
