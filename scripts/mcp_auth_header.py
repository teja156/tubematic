#!/usr/bin/env python3
"""Print the MCP server's Authorization header as JSON (TMDEV-152).

Claude Code (`headersHelper`) and Codex (`http_headers_helper`) run this on every
connection to the tubematic MCP server, so the token stays in its own file
(~/.tubematic-data/secrets/mcp_token) and never in an agent's config, and a
rotated token is picked up with no re-registration. OpenCode reads the same file
through its `{file:}` substitution instead.

Exits non-zero, printing why on stderr, when the token cannot be read: the CLI
then sends no header and the server answers 401, which is the visible failure.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tubematic_core.auth import SecretMissing, read_secret  # noqa: E402


def main() -> int:
    try:
        token = read_secret("mcp_token")
    except SecretMissing as e:
        print(f"tubematic: {e}. Run: python onboard.py (or upgrade.py) to create it.",
              file=sys.stderr)
        return 1
    print(json.dumps({"Authorization": f"Bearer {token}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
