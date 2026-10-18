Show active topic research strategies.

Call the MCP tool:
  tubematic:get_research_strategies()

Display the result. Explain the three strategies to the user:
- curriculum: builds on previously published topics — logical next videos in a series
- trending: finds currently popular topics in your niche via web search
- mining: sends the YouTube URLs configured on the dashboard to Gemini, which watches them and names concepts worth their own video

Show which strategies are currently active and when research last ran.

If none are set, the default is all three. If `mining_available` is false, no Gemini
API key is stored: mining is off whatever was selected, and comes back once a key is
added on the Settings dashboard.
