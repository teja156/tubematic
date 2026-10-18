#!/usr/bin/env bash
# prepare_for_install.sh
#
# Removes dev-session artifacts from a copied project directory so that
# install.py can be tested from a clean state.
#
# Run this only in a COPY of the project, not the main dev directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}Tubematic — Prepare for Install Test${NC}"
echo "========================================"
echo -e "${DIM}Clears dev-session artifacts so install.py starts clean.${NC}"
echo ""

# Items to delete (paths relative to repo root)
ITEMS=(
    ".env"
    ".onboard-state.json"
    "logs"
    "transcripts"
    ".claude/settings.local.json"
    ".claude/commands"
)

# ── Print what will be affected ─────────────────────────────────────────────

echo -e "${YELLOW}The following will be permanently deleted:${NC}"
echo ""

ANY_PRESENT=false
for item in "${ITEMS[@]}"; do
    if [ -e "$item" ]; then
        echo -e "  ${RED}✗${NC}  $item"
        ANY_PRESENT=true
    else
        echo -e "  ${DIM}·  $item  (not present)${NC}"
    fi
done

PYCACHE_COUNT=$(find . -type d -name "__pycache__" -not -path "./.git/*" 2>/dev/null | wc -l | tr -d ' ')
if [ "$PYCACHE_COUNT" -gt 0 ]; then
    echo -e "  ${RED}✗${NC}  __pycache__/  (${PYCACHE_COUNT} directories)"
    ANY_PRESENT=true
fi

echo ""

if [ "$ANY_PRESENT" = false ]; then
    echo -e "${GREEN}Nothing to clean — directory already looks fresh.${NC}"
    echo ""
    exit 0
fi

# ── First confirmation ───────────────────────────────────────────────────────

echo -e "${BOLD}Are you sure you want to delete all of the above?${NC}"
read -r -p "  Type 'y' to confirm: " REPLY1
echo ""

if [[ ! "$REPLY1" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# ── Second confirmation ──────────────────────────────────────────────────────

echo -e "${RED}${BOLD}Second confirmation required.${NC}"
echo -e "${RED}This cannot be undone. Type 'yes' (exactly) to proceed:${NC}"
read -r -p "  " REPLY2
echo ""

if [[ "$REPLY2" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

# ── Delete ───────────────────────────────────────────────────────────────────

echo "Deleting..."
echo ""

for item in "${ITEMS[@]}"; do
    if [ -e "$item" ]; then
        rm -rf "$item"
        echo -e "  ${RED}deleted${NC}  $item"
    fi
done

if [ "$PYCACHE_COUNT" -gt 0 ]; then
    find . -type d -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
    echo -e "  ${RED}deleted${NC}  __pycache__ (${PYCACHE_COUNT} directories)"
fi

echo ""
echo -e "${GREEN}${BOLD}Done.${NC} Ready to run:  python onboard.py"
echo ""
