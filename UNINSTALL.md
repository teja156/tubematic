# Tubematic — Uninstall

`uninstall.py` removes Tubematic in nine steps — containers, Docker volumes, the database, job files,
generated scenes, each agent's skills and MCP registration, the cron entry, files an older version
left behind, and finally the `~/.tubematic-data/` data root. Every step asks first, and every step
that deletes your data defaults to **no**; only the last one can delete your rendered videos, and it
says how many are at stake. Run it from the install directory:

```bash
python3 uninstall.py            # --yes confirms every step without asking
```

To remove a single agent and keep the project, use `python3 onboard.py --uninstall-agent <agent>`
instead.

- **What each step removes, and what is left behind:**
  [Installing — Uninstalling](docs/user-guide/02-installing.md#uninstalling).
- **A full wipe, images and install directory included:**
  [Removing everything](docs/user-guide/02-installing.md#removing-everything).
- **Freeing space or clearing data without uninstalling:**
  [Cleaning up without uninstalling](docs/user-guide/02-installing.md#cleaning-up-without-uninstalling).
- **Going back to an older version instead:**
  [Upgrading — Rollback policy](docs/user-guide/07-upgrading.md#rollback-policy).
