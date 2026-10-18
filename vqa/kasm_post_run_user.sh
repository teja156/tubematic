#!/usr/bin/env bash
# vqa/kasm_post_run_user.sh
#
# Overwrites the base image's /dockerstartup/kasm_post_run_user.sh stub —
# Kasm's own hook, invoked automatically as kasm-user after session start,
# independent of anything in custom_startup.sh/vnc_startup.sh. Runs once per
# session; idempotent — safe if Kasm ever invokes it more than once.
#
# Reconciles the split between the image-owned pristine copy at /opt/tubematic
# and the persisted working tree under $HOME. Pipeline data (the DB, job
# files, generated scenes, rendered mp4s, and the settings table holding the
# API keys) lives separately again, in ~/.tubematic-data — still under $HOME,
# so the persistent profile keeps it across session teardown. See
# vqa/README.md for the full code/state split rationale.

set -uo pipefail  # deliberately not -e: each step below handles its own
                   # failure explicitly, since a mid-script `exit` here would
                   # leave the session silently half-bootstrapped with no
                   # indication in the Kasm UI itself — every failure path
                   # logs a clear reason before exiting.

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

OPT_ROOT="/opt/tubematic"
WORK_ROOT="${HOME:-/home/kasm-user}/tubematic"
# Pipeline data root — must match docker-compose.yml's ${HOME}/.tubematic-data
# volume devices (TMDEV-76). Outside $WORK_ROOT, so the working-tree rsync
# cannot reach it; still under $HOME, so the Kasm persistent profile keeps it.
DATA_ROOT="${HOME:-/home/kasm-user}/.tubematic-data"
LOG_DIR="$WORK_ROOT/vqa/logs"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/bootstrap.log"
exec > >(tee -a "$LOG_FILE") 2>&1

log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
fail() { log "FATAL: $*"; exit 1; }

log "=== tubematic VQA bootstrap starting (as $(id -un)) ==="

# wait for desktop to be ready
/usr/bin/desktop_ready

# ── 1. Wait for dockerd ──────────────────────────────────────────────────
log "Waiting for dockerd..."
docker_ready=false
for _ in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then
        docker_ready=true
        break
    fi
    sleep 2
done
if [ "$docker_ready" != true ]; then
    fail "dockerd did not become ready within 120s. Check docker-socket group membership" \
         " (dockerfile_tubematic_vqa's 'usermod -aG docker kasm-user' step)."
fi
log "dockerd ready"

# ── 2. Reconcile the working tree ────────────────────────────────────────
# Gate the code refresh on a build stamp so a genuine image rebuild replaces
# code, but relaunching the *same* image leaves a tester's in-session edits
# under $WORK_ROOT alone. Excluded unconditionally: .venv/,
# and vqa/logs/ (persisted state or session-specific, never something the
# image should overwrite), plus vqa/seed/ and vqa/skills-cache/ (read
# directly from $OPT_ROOT in steps 3 and 7 below — never from $WORK_ROOT —
# so copying them into the working tree would just be wasted space).
IMAGE_STAMP="$(cat "$OPT_ROOT/vqa/.image-id" 2>/dev/null || echo "unknown")"
WORK_STAMP_FILE="$WORK_ROOT/.vqa-image-id"
WORK_STAMP="$(cat "$WORK_STAMP_FILE" 2>/dev/null || echo "")"

if [ "$IMAGE_STAMP" != "$WORK_STAMP" ]; then
    log "Image changed ($WORK_STAMP -> $IMAGE_STAMP) — refreshing working tree at $WORK_ROOT"
    mkdir -p "$WORK_ROOT"

    # Sentinel for the post-rsync check below: was there already real,
    # persisted data here before this refresh? Checked before rsync runs.
    db_existed_before=false
    [ -f "$DATA_ROOT/data/tubematic.db" ] && db_existed_before=true

    # The rsync below deliberately runs without --delete (that is what keeps
    # the tree consistent), which means a file REMOVED from the repo is
    # never removed from an already-persisted working tree — a deleted skill
    # lingers forever, and a renamed one leaves both copies live. For most of
    # the tree that is merely untidy; for these three directories it is a
    # correctness bug, because step 3 below copies whatever it finds here
    # straight into ~/.claude, so a stale skill/command stays visible to the
    # agent indefinitely. Clear them first and let the rsync repopulate them
    # from the image, so they track the image exactly. Safe: this only runs
    # on the refresh path, which already replaces these files by content, and
    # a failed rsync exits below without writing the stamp — so the next
    # launch retries the whole step rather than leaving them missing.
    rm -rf "$WORK_ROOT/agent_files/skills" \
           "$WORK_ROOT/agent_files/claude/commands" \
           "$WORK_ROOT/vqa/agent/commands"

    # --no-o --no-g: /opt/tubematic is chown -R 1000:0 at image-build time
    # (root doing the chown), but this script runs as kasm-user (uid 1000) —
    # without these flags rsync's default -o/-g tries to chgrp/chown the
    # destination to match the source, which this uid may not be permitted
    # to do. The invoking user should own its own persisted tree regardless,
    # so preserving source ownership is never actually wanted here.
    if rsync -a --no-o --no-g \
        --exclude '.venv/' \
        --exclude 'vqa/logs/' \
        --exclude 'vqa/seed/' \
        --exclude 'vqa/skills-cache/' \
        "$OPT_ROOT/" "$WORK_ROOT/"
    then
        # $DATA_ROOT holds irreplaceable session state — every rendered video
        # and the whole pipeline DB for this persisted profile. Since TMDEV-76
        # it sits outside $WORK_ROOT entirely, so the rsync above structurally
        # cannot reach it; that is a stronger guarantee than the --exclude
        # flag it used to rest on, which was one careless edit away from
        # breaking. The check below is kept anyway: it costs nothing, and the
        # failure it catches (seeding a fresh empty DB over a real one) is
        # silent and irreversible. Stop rather than risk it.
        if [ "$db_existed_before" = true ] && [ ! -f "$DATA_ROOT/data/tubematic.db" ]; then
            fail "$DATA_ROOT/data/tubematic.db existed before this working-tree refresh and" \
                 " is gone after it. Refusing to" \
                 " continue rather than risk seeding over lost data. This needs investigation" \
                 " before this session touches the data root any further."
        fi
        echo "$IMAGE_STAMP" > "$WORK_STAMP_FILE"
        log "Working tree refreshed"
    else
        # Do NOT write the stamp on failure — this script deliberately runs
        # without -e (see the top-of-file note), so a failed rsync would
        # otherwise fall through to writing a now-current stamp anyway, and
        # the next launch would see it as current and never retry.
        fail "rsync from $OPT_ROOT to $WORK_ROOT failed — working tree not refreshed, stamp not updated"
    fi
else
    log "Working tree already current (stamp $IMAGE_STAMP) — leaving as-is"
fi

# ── 3. Refresh Claude Code config (every launch, idempotent) ────────────
# Re-copying skills/commands unconditionally on every launch — not gated on
# the image-stamp check above — is what makes a Kasm persistent profile safe
# to use at all: without this, an already-persisted ~/.claude/skills would
# permanently shadow whatever a later image rebuild changed.
#
# Both directories are wiped, not merged into, for the same reason: the
# per-skill `rm -rf` below only refreshes skills that still exist upstream,
# so a skill or command DELETED or RENAMED in the repo would otherwise
# survive here forever on a persisted profile — the agent would keep seeing
# a stale skill (or both halves of a rename) with nothing to indicate why.
# These two directories are wholly image-owned: everything in them is
# repopulated from $WORK_ROOT/$OPT_ROOT immediately below, so there is
# nothing here to preserve. NOTE: this does mean a skill or command
# hand-installed into ~/.claude inside a session does not survive a relaunch
# — put it in the repo and rebuild instead, which is already how this
# environment expects changes to be made (see vqa/README.md).
log "Refreshing Claude Code skills, commands, and MCP registration..."
# The wipe below is unconditional, but step 2's repopulate is gated on the
# image stamp — so the two can disagree. If the working tree's skills are
# missing while its stamp says current (someone deleted them by hand in a
# session; a genuine crash mid-refresh leaves the stamp stale instead, so
# step 2 would have re-run), wiping ~/.claude/skills would hand the agent a
# session with no tubematic skills at all and nothing to say why. Stop first.
[ -d "$WORK_ROOT/agent_files/skills" ] || \
    fail "no skills found at $WORK_ROOT/agent_files/skills, but the working tree is marked" \
         " current (stamp $IMAGE_STAMP). Refusing to clear ~/.claude/skills and leave this" \
         " session with none. Fix: rm -f '$WORK_STAMP_FILE' and relaunch to force a refresh."
rm -rf "$HOME/.claude/skills" "$HOME/.claude/commands"
mkdir -p "$HOME/.claude/skills" "$HOME/.claude/commands"

for skill_dir in "$WORK_ROOT/agent_files/skills"/*/; do
    [ -d "$skill_dir" ] || continue
    name="$(basename "$skill_dir")"
    rm -rf "$HOME/.claude/skills/$name"
    cp -r "$skill_dir" "$HOME/.claude/skills/$name"
done
if [ -d "$OPT_ROOT/vqa/skills-cache/.claude/skills" ]; then
    for skill_dir in "$OPT_ROOT/vqa/skills-cache/.claude/skills"/*/; do
        [ -d "$skill_dir" ] || continue
        name="$(basename "$skill_dir")"
        rm -rf "$HOME/.claude/skills/$name"
        cp -r "$skill_dir" "$HOME/.claude/skills/$name"
    done
else
    # Now unconditionally true rather than hypothetical: ~/.claude/skills was
    # cleared just above, so a previously-persisted copy of these can no
    # longer paper over a cache missing from the image.
    log "WARNING: no remotion skills cache at $OPT_ROOT/vqa/skills-cache — the remotion" \
        " skills are absent from this session and tubematic-scene-config's Step 0" \
        " dependency (remotion-best-practices) will be missing. The image build is incomplete."
fi

for cmd_dir in "$WORK_ROOT/agent_files/claude/commands" "$WORK_ROOT/vqa/agent/commands"; do
    [ -d "$cmd_dir" ] || continue
    cp "$cmd_dir"/*.md "$HOME/.claude/commands/" 2>/dev/null || true
done

# Statusline: context-window usage + 5h/7d rate-limit bars (TMDEV-68) — see
# vqa/statusline.py's own docstring for the JSON-schema/design rationale.
# Re-copied every launch, same as skills/commands above, so an image rebuild
# that changes the script is never shadowed by a stale persisted copy.
cp "$WORK_ROOT/vqa/statusline.py" "$HOME/.claude/statusline.py"
chmod +x "$HOME/.claude/statusline.py"
python3 - "$HOME" <<'PYEOF'
import json
import sys
from pathlib import Path

home = Path(sys.argv[1])
settings_file = home / ".claude" / "settings.json"
data = {}
if settings_file.exists():
    try:
        data = json.loads(settings_file.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
data["statusLine"] = {"type": "command", "command": str(home / ".claude" / "statusline.py")}
settings_file.parent.mkdir(parents=True, exist_ok=True)
settings_file.write_text(json.dumps(data, indent=2))
PYEOF

# timeout: a never-authenticated/first-run Claude Code CLI is exactly the
# case where this could hang instead of erroring — and unlike a failure, a
# hang here would never reach step 8's `docker compose up`, turning a
# degraded environment into a dead one.
# Re-registered on every launch, never skipped when present: the server needs
# its token, which Claude Code fetches through a helper that reads the token
# file (headersHelper), and a registration persisted from an older image
# carries no helper at all. `claude mcp add` refuses an existing name, hence
# the remove first.
timeout 30 claude mcp remove --scope user tubematic >/dev/null 2>&1 || true
timeout 30 claude mcp add-json --scope user tubematic \
    "{\"type\":\"http\",\"url\":\"http://localhost:4100/mcp\",\"headersHelper\":\"python3 $WORK_ROOT/scripts/mcp_auth_header.py\"}" \
    || log "WARNING: claude mcp add-json failed or timed out — tubematic tools will not be visible"

python3 - "$WORK_ROOT" <<'PYEOF'
import json
import sys
from pathlib import Path

workspace = sys.argv[1]
trust_file = Path.home() / ".claude.json"
data = {}
if trust_file.exists():
    try:
        data = json.loads(trust_file.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
projects = data.setdefault("projects", {})
entry = projects.setdefault(workspace, {})
entry.setdefault("hasTrustDialogAccepted", True)
entry.setdefault("allowedTools", [])
entry.setdefault("mcpServers", {})
trust_file.write_text(json.dumps(data, indent=2))
PYEOF
log "Claude Code config refreshed"

# ── 4. Move into the working tree ────────────────────────────────────────
# docker-compose.yml binds device: ${HOME}/.tubematic-data/..., an absolute
# invocation cwd — this is what puts every bind mount inside the persisted
# tree. (There is no env_file any more; keys live in the settings table.)
cd "$WORK_ROOT" || fail "could not cd into $WORK_ROOT"

# ── 5. Ensure the data root exists and is writable by this user ──
# The local Docker volume driver will not create device: targets itself, and
# there is no onboard.py here to have done this already.
mkdir -p "$DATA_ROOT"/jobs "$DATA_ROOT"/data "$DATA_ROOT"/output_videos \
         "$DATA_ROOT"/scenes/generated

# tubematic-api/tubematic-renderer run as root inside their containers, and
# a bind mount's source directory gets auto-created by dockerd (also root)
# if it's ever missing at compose-up time — either path can leave content
# under the data root root-owned on the host. That's invisible to the containers
# themselves (root bypasses permission checks entirely) but blocks host-side
# tools that need to write here too, like vqa/stage_script.py's per-video
# job directory (confirmed live: root:root mode 755 on the jobs dir from an
# earlier session made `mkdir <data root>/jobs/<video_id>` fail for kasm-user
# with a plain permission error). kasm-user can never fix root-owned files
# itself (chown requires owning the file or being root) — this base image
# grants kasm-user full passwordless sudo specifically for cases like this,
# so self-heal ownership unconditionally on every launch rather than only
# mkdir-ing paths that don't exist yet, which would leave a profile that
# picked up root-owned content once stuck that way forever.
sudo chown -R kasm-user:kasm-user "$DATA_ROOT" \
    || log "WARNING: sudo chown on $DATA_ROOT failed — host-side tools (stage_script.py," \
           " review_video.py) may hit permission errors writing into container-created paths"
log "$DATA_ROOT ready"

# Service tokens (TMDEV-152): Compose refuses to start a service whose token
# file is missing, and the MCP helper above reads mcp_token. Existing tokens
# are kept, so a relaunch changes nothing. After the chown above, which would
# otherwise not matter here: the files are created as this user.
PYTHONPATH="$WORK_ROOT" python3 -m tubematic_core.auth ensure \
    || fail "could not create the service tokens in $DATA_ROOT/secrets"

# ── 6. Seed the DB only if absent ────────────────────────────────────────
# Never overwrite — this is what lets the persisted DB carry prior work
# (previous videos, their statuses) forward across relaunches.
if [ -f "$DATA_ROOT/data/tubematic.db" ]; then
    log "DB already present at $DATA_ROOT/data/tubematic.db — leaving as-is"
else
    if [ -f "$OPT_ROOT/vqa/seed/tubematic.db" ]; then
        cp "$OPT_ROOT/vqa/seed/tubematic.db" "$DATA_ROOT/data/tubematic.db"
        log "Seeded DB from $OPT_ROOT/vqa/seed/tubematic.db"
    else
        fail "no seed DB at $OPT_ROOT/vqa/seed/tubematic.db — image build is incomplete"
    fi
fi

# ── 7. Bring up the stack (no dashboard) ─────────────────────────────────
log "Building tubematic-api..."
if ! docker compose build tubematic-api; then
    fail "docker compose build tubematic-api failed — see output above"
fi
log "Starting tubematic-api + tubematic-mcp + tubematic-renderer..."
if ! docker compose up -d tubematic-api tubematic-mcp tubematic-renderer; then
    fail "docker compose up failed — see output above"
fi

# ── 8. Wait for health ───────────────────────────────────────────────────
# Flask and MCP are separate containers with separate health endpoints, so
# both are waited on: a healthy Flask says nothing about whether the agent's
# tools are reachable, which is the whole point of the split.
for svc in tubematic-api:4000 tubematic-mcp:4100; do
    name="${svc%%:*}"
    port="${svc##*:}"
    log "Waiting for $name health..."
    healthy=false
    for _ in $(seq 1 60); do
        if curl -fs "http://localhost:$port/health" >/dev/null 2>&1; then
            healthy=true
            break
        fi
        sleep 5
    done
    if [ "$healthy" != true ]; then
        fail "$name did not become healthy within 300s — check 'docker compose logs $name'"
    fi
done

# ── 9. Report missing API keys (warn only) ───────────────────────────────
# Keys used to arrive as a Kasm-mapped .env, and this hook hard-failed without
# one. Since TMDEV-73 they live in the settings table, which sits in the
# persistent profile — so they are entered once and survive every relaunch.
# Deliberately a warning, not a fail: a keyless box is still useful for
# staging scripts and DB inspection, and a dead bootstrap is not.
# python3, not the sqlite3 CLI — this image installs python3 but not
# sqlite3-the-binary, and stdlib sqlite3 is always available.
missing="$(python3 -c '
import sqlite3, sys
try:
    con = sqlite3.connect(sys.argv[1])
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
except Exception:
    rows = {}
print(" ".join(k for k in ("gemini_api_key", "elevenlabs_api_key", "openai_api_key")
               if not rows.get(k)))
' "$DATA_ROOT/data/tubematic.db" 2>/dev/null || true)"
if [ -n "$missing" ]; then
    log "WARNING: no API key configured for: $missing"
    log "  Nothing can be voiced, illustrated or reviewed until they are set. From a terminal here:"
    log "    cd $WORK_ROOT && python3 vqa/edit_settings.py \\"
    log "        --set gemini_api_key=... --set elevenlabs_api_key=... --set openai_api_key=..."
    log "  They persist in this workspace's profile — you only enter them once."
fi

log "=== VQA environment ready ==="
log "Rendered videos land at: $DATA_ROOT/output_videos/proj_vqa/<video_id>.mp4"
log "Open Claude Code from $WORK_ROOT and run /vqa-new-video \"<topic>\" to start."
