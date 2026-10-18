#!/usr/bin/env bash
# vqa/build.sh
#
# Builds the Kasm Workspace image for the Tubematic VQA (video quality
# assessment) environment (TMDEV-68): a Docker-in-Docker workspace, based on
# kasmweb/ubuntu-noble-dind, with the tubematic source staged in and
# pre-configured — no dashboard, no cron, no onboarding wizard at launch.
# Fork of kasm_workspace_testing/build.sh; see vqa/README.md for the full design.
#
# Usage:
#   ./vqa/build.sh [tag] [--no-cache] [--worktree <path|branch|dirname>]
#
# tag defaults to "latest". Resulting image: tubematic/tubematic-vqa-env:<tag>
#
# The image is built from ONE git worktree, chosen interactively unless
# --worktree names it. See the "Worktree selection" block below.
#
# Note: this only builds the Kasm image itself. There is no Docker daemon
# available during a Kasm image build (dockerd only starts at session
# runtime), so tubematic-api/tubematic-renderer are NOT built here — that
# happens inside the running session via vqa/kasm_post_run_user.sh, on every launch
# (chosen: no /var/lib/docker persistence for VQA — see vqa/README.md).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTEXT_DIR="$SCRIPT_DIR/build-context"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo -e "\n${BLUE}${BOLD}▶ $*${NC}"; }
ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
die()  { echo -e "\n${RED}${BOLD}Error:${NC} $*" >&2; exit 1; }

TAG="latest"
NOCACHE=false
WORKTREE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-cache)   NOCACHE=true ;;
        --worktree)   shift; [ $# -gt 0 ] || die "--worktree needs a value"; WORKTREE="$1" ;;
        --worktree=*) WORKTREE="${1#*=}" ;;
        *)            TAG="$1" ;;
    esac
    shift
done
IMAGE="tubematic/tubematic-vqa-env:$TAG"

command -v docker >/dev/null 2>&1 || die "docker is required on PATH"
command -v rsync  >/dev/null 2>&1 || die "rsync is required on PATH"
command -v git    >/dev/null 2>&1 || die "git is required on PATH"

# ── Worktree selection ──────────────────────────────────────────────────────
#
# Everything the image is made of comes from ONE chosen worktree: the app
# source, the Dockerfile, and the startup hooks that Dockerfile copies in. So
# the built env is genuinely "that branch" rather than a mix of two trees.
#
# Only worktrees are offered, never bare branches. A worktree is a real
# checkout, so staging keeps its exact existing semantics — tracked files plus
# untracked-but-not-ignored ones, including uncommitted work. A branch with no
# worktree could only be staged from its committed tip, silently dropping
# anything uncommitted; that is deliberately out of scope.
#
# Keep in sync with kasm_workspace_testing/build.sh.

WT_PATHS=(); WT_LABELS=(); WT_HEADS=()
_wt_path=""; _wt_head=""; _wt_branch=""; _wt_bare=false

# Records in `git worktree list --porcelain` are blank-line separated and a
# `worktree` line opens each one, so flush on that line and once more at EOF.
_wt_flush() {
    # A `bare` entry has no files to stage; a missing directory is a stale
    # (prunable) entry. Skip both rather than offering an unbuildable choice.
    if [ -n "$_wt_path" ] && [ "$_wt_bare" != true ] && [ -d "$_wt_path" ]; then
        WT_PATHS+=("$_wt_path")
        if [ -n "$_wt_branch" ]; then
            WT_LABELS+=("${_wt_branch#refs/heads/}")
        else
            WT_LABELS+=("(detached)")
        fi
        WT_HEADS+=("${_wt_head:0:7}")
    fi
    _wt_path=""; _wt_head=""; _wt_branch=""; _wt_bare=false
}

# Read line-by-line rather than splitting on whitespace, so worktree paths
# containing spaces survive intact.
while IFS= read -r line; do
    case "$line" in
        "worktree "*) _wt_flush; _wt_path="${line#worktree }" ;;
        "HEAD "*)     _wt_head="${line#HEAD }" ;;
        "branch "*)   _wt_branch="${line#branch }" ;;
        bare)         _wt_bare=true ;;
    esac
done < <(git -C "$REPO_ROOT" worktree list --porcelain)
_wt_flush

[ "${#WT_PATHS[@]}" -gt 0 ] || die "no usable git worktrees found under $REPO_ROOT"

# The worktree this script itself lives in — the default, and the fallback
# when there is no TTY to prompt on. Resolved through git rather than by
# string-comparing $REPO_ROOT, which may differ by symlink or trailing slash.
CURRENT_WT="$(git -C "$REPO_ROOT" rev-parse --show-toplevel)"
WT_DEFAULT=0
for i in "${!WT_PATHS[@]}"; do
    if [ "${WT_PATHS[$i]}" = "$CURRENT_WT" ]; then WT_DEFAULT="$i"; fi
done

# Resolve a --worktree value to an index, strictly: exact path (raw or
# canonicalized), then branch name, then directory basename. Anything that
# matches nothing or matches more than one is fatal — silently falling back to
# the current worktree would bake the wrong branch into the image unnoticed.
WT_INDEX=""
_wt_resolve() {
    local want="$1" want_abs="" i
    local -a matches=()
    if [ -d "$want" ]; then want_abs="$(cd "$want" && pwd -P)"; fi
    for i in "${!WT_PATHS[@]}"; do
        if [ "${WT_PATHS[$i]}" = "$want" ] || { [ -n "$want_abs" ] && [ "${WT_PATHS[$i]}" = "$want_abs" ]; }; then
            matches+=("$i")
        fi
    done
    if [ "${#matches[@]}" -eq 0 ]; then
        for i in "${!WT_PATHS[@]}"; do
            if [ "${WT_LABELS[$i]}" = "$want" ]; then matches+=("$i"); fi
        done
    fi
    if [ "${#matches[@]}" -eq 0 ]; then
        for i in "${!WT_PATHS[@]}"; do
            if [ "${WT_PATHS[$i]##*/}" = "$want" ]; then matches+=("$i"); fi
        done
    fi
    case "${#matches[@]}" in
        1) WT_INDEX="${matches[0]}" ;;
        0) die "--worktree '$want' matched no worktree (run 'git worktree list' to see them)" ;;
        *) die "--worktree '$want' is ambiguous — matched ${#matches[@]} worktrees. Pass a full path." ;;
    esac
}

if [ -n "$WORKTREE" ]; then
    _wt_resolve "$WORKTREE"
elif [ -t 0 ]; then
    _wt_width=0
    for i in "${!WT_LABELS[@]}"; do
        if [ "${#WT_LABELS[$i]}" -gt "$_wt_width" ]; then _wt_width="${#WT_LABELS[$i]}"; fi
    done
    echo ""
    echo -e "${BOLD}Available worktrees:${NC}"
    for i in "${!WT_PATHS[@]}"; do
        _wt_marks=""
        if [ "$i" -eq "$WT_DEFAULT" ]; then _wt_marks="  (current)"; fi
        # Uncommitted work in the chosen tree gets baked into the image and
        # cannot be recovered from the tag afterwards, so flag it up front.
        if [ -n "$(git -C "${WT_PATHS[$i]}" status --porcelain 2>/dev/null)" ]; then
            _wt_marks="$_wt_marks  *uncommitted"
        fi
        printf "  %d) %-*s  %s  ${DIM}%s${NC}%s\n" \
            "$((i + 1))" "$_wt_width" "${WT_LABELS[$i]}" "${WT_HEADS[$i]}" \
            "${WT_PATHS[$i]}" "$_wt_marks"
    done
    while true; do
        printf "\nBuild which worktree into the image? [%d]: " "$((WT_DEFAULT + 1))"
        # `read` returns non-zero on EOF; without this a Ctrl-D would exit
        # silently under `set -e` and look like a successful no-op.
        read -r _wt_reply || die "no selection (stdin closed)"
        if [ -z "$_wt_reply" ]; then _wt_reply="$((WT_DEFAULT + 1))"; fi
        if [[ "$_wt_reply" =~ ^[0-9]+$ ]] && [ "$_wt_reply" -ge 1 ] && [ "$_wt_reply" -le "${#WT_PATHS[@]}" ]; then
            WT_INDEX="$((_wt_reply - 1))"
            break
        fi
        echo -e "  ${RED}Enter a number between 1 and ${#WT_PATHS[@]}.${NC}"
    done
else
    WT_INDEX="$WT_DEFAULT"
    echo -e "\n${DIM}stdin is not a TTY — not prompting; using this script's own worktree.${NC}"
fi

SOURCE_DIR="${WT_PATHS[$WT_INDEX]}"
SOURCE_LABEL="${WT_LABELS[$WT_INDEX]}"
DOCKERFILE="$SOURCE_DIR/vqa/dockerfile_tubematic_vqa"
[ -f "$DOCKERFILE" ] || die "$SOURCE_LABEL has no vqa/dockerfile_tubematic_vqa (looked in $SOURCE_DIR)"

echo ""
echo -e "${BOLD}Tubematic — VQA Kasm Image Build${NC}"
echo "===================================="
echo -e "${DIM}Image:  $IMAGE${NC}"
echo -e "${DIM}Source: $SOURCE_LABEL — $SOURCE_DIR${NC}"

# ── Stage a filtered copy of the repo into the build context ────────────────
#
# Source of truth is git itself, not a hand-maintained exclude list: every
# tracked file plus every untracked-but-not-ignored file is staged, so
# anything in .gitignore (.env, HANDOFF.md, mounted/, node_modules, vqa/logs,
# vqa/seed, etc.) never enters the build context, let alone the built image.
# Same pattern as kasm_workspace_testing/build.sh.
#
# $CONTEXT_DIR deliberately stays under this script's own directory even when
# building another worktree — the build never writes into a tree it was only
# asked to read. `docker build -f` may point outside the context.
step "Staging filtered source into build context"
rm -rf "$CONTEXT_DIR"
mkdir -p "$CONTEXT_DIR/tubematic"
git -C "$SOURCE_DIR" ls-files -z --cached --others --exclude-standard | \
    rsync -a --from0 --files-from=- "$SOURCE_DIR/" "$CONTEXT_DIR/tubematic/"
ok "Staged $SOURCE_DIR -> $CONTEXT_DIR/tubematic"

cleanup() { rm -rf "$CONTEXT_DIR"; }
trap cleanup EXIT

# ── Build ─────────────────────────────────────────────────────────────────
step "Building VQA Kasm image"
BUILD_ARGS=(-f "$DOCKERFILE" -t "$IMAGE" "$CONTEXT_DIR")
[ "$NOCACHE" = true ] && BUILD_ARGS=(--no-cache "${BUILD_ARGS[@]}")
docker build "${BUILD_ARGS[@]}"
ok "Built $IMAGE"

echo ""
echo -e "${GREEN}${BOLD}Done.${NC}"
echo -e "${DIM}Image:${NC} $IMAGE"
echo -e "${DIM}Built from:${NC} $SOURCE_LABEL — $SOURCE_DIR"
echo -e "${DIM}Next steps:${NC} register $IMAGE as a Kasm workspace image (Persistent Profile"
echo -e "${DIM}Path + privileged run config — both mandatory; no .env mapping needed, see${NC}"
echo -e "${DIM}vqa/README.md), then launch a session. kasm_post_run_user.sh brings the stack up${NC}"
echo -e "${DIM}automatically — no onboard.py, no manual steps inside the session.${NC}"
echo ""
