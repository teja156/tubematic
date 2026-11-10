# Tubematic: Uninstall

`uninstall.py` removes Tubematic in nine steps and asks before each one. The steps that delete your
database, your videos' working files and your rendered videos default to no. Run it from the install
directory:

```bash
python3 uninstall.py            # --yes answers yes to every step
```

- What each step removes, and what the uninstaller leaves behind:
  [Command Reference](docs/user-guide/15-command-reference.md#uninstallpy).
- Removing the images and the install directory afterwards:
  [Uninstalling](docs/user-guide/02-installing.md#uninstalling).
- Removing one agent and keeping Tubematic:
  [Agents](docs/user-guide/12-agents.md#uninstall-an-agent).
- Going back to an older version:
  [Rollback policy](docs/user-guide/07-upgrading.md#rollback-policy).
