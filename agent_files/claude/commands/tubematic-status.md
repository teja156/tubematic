Show the current Tubematic pipeline status.

Call the MCP tools:
  tubematic:get_pipeline_status()
  tubematic:list_videos()

Format and display:
- Whether the pipeline is paused
- Count of videos at each status (TOPIC_PROPOSED, TOPIC_APPROVED, SCRIPT_READY, VOICING, VOICE_READY, RENDER_QUEUED, RENDERING, REVISION_REQUESTED, VIDEO_READY, VIDEO_APPROVED, SCHEDULED, PUBLISHING, PUBLISHED, FAILED, etc.)
- Highlight any statuses waiting for human action: TOPIC_PROPOSED, SCRIPT_READY, VIDEO_READY
- This month's spend, from get_pipeline_status's `spend`: the dollar total (at API list prices — it ignores subscriptions), the videos / research split, any unpriced calls as a count beside the total, and ElevenLabs usage in plan credits (never dollars)
- Whether the API and render worker containers are healthy/running: docker compose ps

Also check API health:
  curl -s http://localhost:4000/health

If MCP tools are unavailable, tell the user to run: claude mcp list
