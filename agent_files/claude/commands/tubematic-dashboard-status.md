Check whether the Tubematic containers are running.

Run:
  docker compose ps

Report:
- Whether tubematic-api (Flask, :4000) is up → URL: http://localhost:4000
- Whether tubematic-mcp (the agent's tools, :4100) is up
- Whether tubematic-worker (publishing, Auto Pilot, notifications; no exposed port) is up
- Whether tubematic-renderer (renders videos; no exposed port) is up
- Whether tubematic-dashboard (:3000) is up → URL: http://localhost:3000

Also check both health endpoints — they are separate containers, so either can
be down while the other is fine:
  curl -s http://localhost:4000/health
  curl -s http://localhost:4100/health

Show the result. If containers are not running, tell the user to run, from the Tubematic install
directory: python3 scripts/service.py start
