List all available Tubematic slash commands.

Display the following table:

| Command | What it does |
|---|---|
| `/tubematic` | List all available Tubematic commands (this command) |
| `/tubematic-status` | Show current pipeline status — video counts by stage, spend, API/render worker health |
| `/tubematic-submit-new-job` | Score a topic and create a new video job (strategy=manual) |
| `/tubematic-add-topic` | Add a curriculum seed domain for scheduled research |
| `/tubematic-pause-domain` | Pause topic generation for a curriculum seed domain |
| `/tubematic-resume-domain` | Resume topic generation for a paused seed domain |
| `/tubematic-list-strategies` | Show active research modes (curriculum/trending/mining) |
| `/tubematic-set-strategy` | Update active research modes |
| `/tubematic-pause` | Pause the pipeline — agent will stop advancing videos |
| `/tubematic-resume` | Resume the pipeline after a pause |
| `/tubematic-dashboard-status` | Check whether API (:4000), render worker, and dashboard (:3000) containers are running |
| `/tubematic-register-mcp` | Re-register the MCP server (use after moving the installation or reinstalling) |
| `/tubematic-troubleshooting` | Work out what is wrong with the install and, if it is a bug, draft a redacted issue report (a skill — it never posts anything itself) |

After the table, add a one-line note:
"Run any command by typing it in the prompt, optionally followed by arguments (e.g. `/tubematic-submit-new-job how git rebase works`)."
