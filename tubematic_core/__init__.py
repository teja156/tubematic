"""Code shared by every Tubematic Python process.

Deliberately tiny, and deliberately not a dumping ground. Until this package
existed the four processes (Flask, MCP, the render worker and the host-side
cron poller) had no shared import root at all: renderer/api/ and mcp/ are
COPY'd into unrelated directories in the image, and scripts/ runs on the host.
Everything they had in common was hand-duplicated behind "Keep in sync"
comments, which is fine for a constant and much less fine for a secret
redactor.

Only add something here when a copy of it would be genuinely dangerous to let
drift. Constants that merely repeat should keep using the existing convention.
"""
