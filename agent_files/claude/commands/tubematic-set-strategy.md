Update active topic research strategies.

User provided: $ARGUMENTS

If $ARGUMENTS is empty, ask: "Which strategies do you want active? Options: curriculum, trending, mining (comma-separated)"

Parse $ARGUMENTS as a comma-separated list. Valid values: curriculum, trending, mining.

Call the MCP tool with the parsed list:
  tubematic:set_research_strategies(strategies=[...])

Then confirm by calling:
  tubematic:get_research_strategies()

Tell the user which strategies are now active and that they take effect on the next research run.

If an invalid strategy name is given, explain the valid options and do not update.

If the tool returns an `error` (mining is refused while no Gemini API key is stored),
relay it to the user as written — the strategies were not changed.
