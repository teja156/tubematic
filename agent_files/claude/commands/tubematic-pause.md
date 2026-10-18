Pause the Tubematic pipeline.

While paused, the scheduled poller starts no new pipeline or research session.
Sessions already running finish, and pending script profiles are still built.
Human checkpoint approvals in the dashboard still work normally. Auto Pilot, if it is on,
approves and posts nothing while the pipeline is paused.

Call the MCP tool:
  tubematic:pause_pipeline()

Confirm to the user: "The pipeline is now paused. Use /tubematic-resume to resume."
