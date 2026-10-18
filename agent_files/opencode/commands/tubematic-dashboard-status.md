Check whether the Tubematic containers are running.

**You cannot run shell commands from the Tubematic agent workspace** — the install denies
the `shell` tool there, so `docker compose ps` is not available to you. Use the health
endpoints instead, which `webfetch` can reach:

  http://localhost:4000/health   → tubematic-api (Flask, :4000)
  http://localhost:4100/health   → tubematic-mcp (the agent's tools, :4100)

They are separate containers, so either can be down while the other is fine.

Report:
- Whether tubematic-api answered → URL: http://localhost:4000
- Whether tubematic-mcp answered
- The dashboard at http://localhost:3000 (fetch it; a response means the container is up)
- tubematic-renderer (the render worker) exposes no port and no health endpoint, so it
  cannot be checked this way. Say so rather than guessing, and tell the user to run
  `docker compose ps` themselves if they need to know.

If nothing answers, tell the user to run: docker compose up -d
