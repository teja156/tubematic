#!/usr/bin/env bash
# kasm_workspace/build.sh
#
# Builds the published Tubematic Kasm Workspace image: the same Docker-in-
# Docker desktop as kasm_workspace_testing/, but with NO Tubematic source in
# it. The launch form picks a version and the baked bootstrap downloads it into
# the session, so this image is rebuilt only when the base image or the
# tooling changes -- never per Tubematic release.
#
# Usage:
#   ./build.sh [--image NAME] [--push] [--no-cache] [tag]
#
# tag defaults to 1.19.0, the Kasm release line the image targets. NAME
# defaults to tubematic/tubematic-kasm-workspace (a local name); CI passes
# ghcr.io/<owner>/tubematic-kasm-workspace with --push.
#
# The build context is image/ alone: there is no repository to stage, which is
# why this script has none of kasm_workspace_testing/build.sh's worktree
# selection.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTEXT_DIR="$SCRIPT_DIR/image"
DOCKERFILE="$SCRIPT_DIR/dockerfile_tubematic_kasm_workspace"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo -e "\n${BLUE}${BOLD}▶ $*${NC}"; }
ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
die()  { echo -e "\n${RED}${BOLD}Error:${NC} $*" >&2; exit 1; }

TAG="1.19.0"
NAME="tubematic/tubematic-kasm-workspace"
NOCACHE=false
PUSH=false
while [ $# -gt 0 ]; do
    case "$1" in
        --no-cache) NOCACHE=true ;;
        --push)     PUSH=true ;;
        --image)    shift; [ $# -gt 0 ] || die "--image needs a value"; NAME="$1" ;;
        --image=*)  NAME="${1#*=}" ;;
        -*)         die "unknown option: $1" ;;
        *)          TAG="$1" ;;
    esac
    shift
done
IMAGE="$NAME:$TAG"

command -v docker >/dev/null 2>&1 || die "docker is required on PATH"
[ -f "$DOCKERFILE" ] || die "missing $DOCKERFILE"

step "Building $IMAGE"
BUILD_ARGS=(-f "$DOCKERFILE" -t "$IMAGE"
    --label "org.opencontainers.image.source=https://github.com/teja156/tubematic"
    --label "org.opencontainers.image.description=Tubematic Kasm Workspace: installs a Tubematic release at session launch"
    "$CONTEXT_DIR")
[ "$NOCACHE" = true ] && BUILD_ARGS=(--no-cache "${BUILD_ARGS[@]}")
docker build "${BUILD_ARGS[@]}"
ok "Built $IMAGE"

if [ "$PUSH" = true ]; then
    step "Pushing $IMAGE"
    docker push "$IMAGE"
    ok "Pushed $IMAGE"
fi

echo ""
echo -e "${GREEN}${BOLD}Done.${NC} ${DIM}Image:${NC} $IMAGE"
echo -e "${DIM}See kasm_workspace/README.md for the registry entry and session sizing.${NC}"
echo ""
