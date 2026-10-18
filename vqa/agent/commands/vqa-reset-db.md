Reset the VQA pipeline database and every video artifact back to a clean seeded state.

User's input: $ARGUMENTS (optional: "db-only" to keep rendered videos/job files/scenes and reset
only the database)

**This is destructive and irreversible — every video, script, rendered mp4, and generated scene
in this environment is deleted.** Before running anything, confirm explicitly with the user:
state plainly that this deletes all current videos and cannot be undone, and wait for an explicit
yes. Do not run this from your own judgment mid-task, and do not treat an ambiguous or implied
"sure, whatever" as confirmation — ask directly if there's any doubt.

Once confirmed, run:

  `/opt/tubematic/.venv/bin/python "$(ls -d ~/tubematic 2>/dev/null || echo /opt/tubematic)"/vqa/reset_db.py --yes` (normal reset — also clears
  `~/.tubematic-data/jobs/`, `~/.tubematic-data/output_videos/`, `~/.tubematic-data/scenes/generated/`)

  or, if the user asked to keep existing renders and only reset the database:

  `/opt/tubematic/.venv/bin/python "$(ls -d ~/tubematic 2>/dev/null || echo /opt/tubematic)"/vqa/reset_db.py --yes --db-only`

Report what was cleared (the command's own output lists how many items were removed from each
directory). After this, the environment is back to exactly its first-launch state: one project
(`proj_vqa`), no videos, and the default settings from `vqa/make_seed_db.py`.
