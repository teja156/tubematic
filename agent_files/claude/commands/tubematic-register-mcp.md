Register (or re-register) the Tubematic MCP server with Claude Code.

The MCP server runs in its own `tubematic-mcp` container and is accessible at
`http://localhost:4100/mcp`. Every request to it must carry the install's MCP token, which
Claude Code fetches through a small helper script on each connection. Make sure the containers
are running before registering.

If the MCP is already registered, notify the user and do not continue. Only try to re-register if user explicitly asks for it.

Steps:

1. Verify the containers are up:
   Run: docker compose ps
   If tubematic-mcp is not running: docker compose up -d

2. Re-run the installer from the Tubematic install directory. It registers the server with its
   token helper at the scope the agent was installed with, and also refreshes the skills and
   commands:

     python onboard.py --install-agent claude

3. Only if the user wants to register by hand, give them this, with `<install>` replaced by the
   Tubematic install directory (`claude mcp add` refuses a name that already exists, hence the
   remove first). Drop `--scope user` from both lines for a project-scope install, run inside the
   agent workspace:

     claude mcp remove --scope user tubematic
     claude mcp add-json --scope user tubematic '{"type":"http","url":"http://localhost:4100/mcp","headersHelper":"<install>/.venv/bin/python3 <install>/scripts/mcp_auth_header.py"}'

4. Confirm to the user that the server has been registered and that they should restart Claude Code
   (or reload the window with Cmd+Shift+P → Reload Window) to pick it up.

5. Verify with: claude mcp list

If registration fails, check that the MCP container is healthy:
  docker compose ps
  curl http://localhost:4100/health
If it is healthy but `claude mcp list` reports a 401, the token helper cannot read
`~/.tubematic-data/secrets/mcp_token`: re-run the installer from step 2.
