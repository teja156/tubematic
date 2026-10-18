Register (or re-register) the Tubematic MCP server with OpenCode.

The MCP server runs in its own `tubematic-mcp` container and is accessible at
`http://localhost:4100/mcp`. Every request to it must carry the install's MCP token, which
OpenCode reads from `~/.tubematic-data/secrets/mcp_token` itself. Make sure the containers are
running before registering.

If the MCP is already registered, notify the user and do not continue. Only try to re-register
if the user explicitly asks for it.

**Read this first: you cannot perform this yourself.** The Tubematic agent workspace denies
the `shell`, `edit` and `write` tools, so you cannot run `opencode mcp add`, reload OpenCode,
or edit a config file from there — and a denied tool cannot be approved interactively either.
Your job is to work out what is wrong and hand the user the exact commands to run.

1. Check the containers by fetching `http://localhost:4100/health` and
   `http://localhost:4000/health` (`webfetch` is available to you; `docker compose ps` is not).
   If nothing answers, the fix is `docker compose up -d`, not registration.

2. Tell the user to re-run the installer, which is the correct fix and the only one that also
   refreshes the skills and commands, adds the token header, and — unlike a bare `mcp add` —
   turns Code Mode off:

     python onboard.py --install-agent opencode

3. Only if they want to do it by hand, give them the steps for their scope, with `<home>`
   replaced by their absolute home directory (the header names the token **file**, which
   OpenCode reads itself, so the token never appears in the config):

     # user scope
     opencode mcp add tubematic --global --url http://localhost:4100/mcp --header "Authorization=Bearer {file:<home>/.tubematic-data/secrets/mcp_token}"
     # project scope, run inside the agent workspace
     opencode mcp add tubematic --url http://localhost:4100/mcp --header "Authorization=Bearer {file:<home>/.tubematic-data/secrets/mcp_token}"

   Then, in the config file that command reports writing, add `"codemode": false` to the
   `tubematic` entry. Without it the Tubematic tools are hidden behind OpenCode's
   `search`/`execute` sandbox and cannot be called by name:

     "mcp": { "servers": { "tubematic": { "codemode": false } } }

   Then:

     opencode reload
     opencode mcp list

   Expect `✓ tubematic  connected`; "needs authentication" means the token file could not be
   read or no longer matches the server — re-run the installer. Immediately after a config
   change or a service restart
   this can report "No MCP servers configured" for a few seconds — wait and run it again
   before concluding anything. The config file is the authoritative answer.
