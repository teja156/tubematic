# Upgrading

How to move an install to a newer version of Tubematic. Your videos, settings and API keys carry
over.

The dashboard shows a banner when a newer release is out. See
[The update banner](04-dashboard.md#the-update-banner).

---

## Before you upgrade

1. Read the [Release Notes](../release-notes.md) for the version you are moving to, and for each
   version you skip. The **Upgrade notes** of each list anything you must do by hand.
2. Pause the pipeline with the switch on the **Settings** page, and wait for running work to
   finish. `upgrade.py` refuses to start while a render, a voicing, an agent session or an upload is
   running.
3. If the install matters to you, copy `~/.tubematic-data/data/tubematic.db` somewhere safe.

## Upgrade a release install

Download the new release into a new directory, beside the old one, and run `upgrade.py` from the new
one:

```bash
curl -LO https://github.com/teja156/tubematic/releases/download/v2.2.0/tubematic-v2.2.0.tar.gz
curl -LO https://github.com/teja156/tubematic/releases/download/v2.2.0/CHECKSUMS.txt
sha256sum -c CHECKSUMS.txt --ignore-missing
tar xzf tubematic-v2.2.0.tar.gz
cd tubematic-v2.2.0
python3 upgrade.py
```

Use the version you are moving to in place of `v2.2.0`.

Keep the old directory until `upgrade.py` finishes. Your scheduled job runs from the old directory
until `upgrade.py` points it at the new one. When it finishes, `upgrade.py` names the old directory
as safe to delete.

Your data is in `~/.tubematic-data/`, outside both directories, so you copy nothing across.

## Upgrade a source install

```bash
cd tubematic            # your checkout
git fetch --tags
git checkout vX.Y.Z     # the version you are moving to
python3 upgrade.py
```

## What `upgrade.py` does

It asks no questions, so you can run it over SSH or from a script.

1. Checks that the upgrade can go ahead. See [When it stops](#when-it-stops).
2. Pulls the new images, or builds them on a source install. The old version keeps running
   meanwhile.
3. Checks again that no work is running, then stops all five containers.
4. Starts the new version. As the containers start, they back up the database and then update it.
5. Points your scheduled job at this directory.
6. Copies this version's skills and commands to each installed agent.
7. Prints the version, the state of each container and the scheduled job.
8. Removes the previous version's images, once everything above has succeeded. See
   [Old images](#old-images).

### Old images

The images `upgrade.py` removes are the Tubematic images that no Tubematic container uses. On a
release install they are the older `tubematic-backend` and `tubematic-dashboard` tags. On a source
install they are the untagged images that earlier builds left.

- It removes them one at a time and does not force a removal. If Docker refuses an image because a
  container still uses it, the upgrade warns and still succeeds.
- It reports the space freed, and measures disk use again for the dashboard's
  [disk figure](04-dashboard.md#the-disk-figure).
- An upgrade that needs attention (a failed health check, or an agent left without its MCP
  registration) keeps the old images, so going back costs nothing. The next successful upgrade
  removes them.
- Docker's build cache stays.

## When it stops

`upgrade.py` checks these before it changes anything. Each message says what to do.

| It stops when | Do this |
|---|---|
| Work is running: a render, a voicing, an agent session or an upload | Pause the pipeline, wait, and run it again. `--force` goes ahead, and that work is lost |
| No dashboard password is set | Run `python3 onboard.py --set-password` from the new directory, then run it again |
| No OpenAI key is stored | Add one on **Settings → API Keys** in the running version, then run it again |
| A scene the agent wrote imports a component this version removed | Delete or fix the files it lists, under `~/.tubematic-data/scenes/generated/`, then run it again |
| A scene the agent wrote cannot be read by your user | Run the `sudo find … chmod 664` command it prints, then run it again |
| The GPU you chose is gone, or the NVIDIA Container Toolkit is | Run `python3 onboard.py --step gpu`, then run it again |
| The remote-renderers file cannot be read | Run `python3 onboard.py --step renderers`, then run it again |
| The database is newer than this version | You are running an older version than the one installed. See [Rollback policy](#rollback-policy) |
| A prerequisite is missing | Fix what it names. See [Prerequisites](02-installing.md#prerequisites) |

The check for removed components leans towards stopping. It can stop for a scene that builds an
import path out of pieces, or one that it cannot read. The message names each file and the reason.

If `upgrade.py` stops after it has pulled the new images, nothing was stopped. Fix the cause and
run it again. The second run is quick.

## After the upgrade

1. Check the version in the dashboard's top bar. It shows the version that is running.
2. Run `python3 upgrade.py --check`. It reports the same state and changes nothing.
3. Restart any agent session you have open, so it picks up the new tools and skills.
4. Upgrade each [remote renderer](11-remote-renderers.md#upgrading), if you have any. A renderer on
   the old version takes no work.
5. Delete the old install directory, once `upgrade.py` has named it.

If `upgrade.py` says an agent has no working tool registration, run
`python3 onboard.py --install-agent <agent>` for that agent. Until you do, that agent does nothing.

The [Command Reference](15-command-reference.md#upgradepy) lists the flags.

---

## Backups

When an upgrade changes the database, the new version copies the database first, to
`~/.tubematic-data/backups/tubematic-before-v<version>-<timestamp>.db`.

- An upgrade that does not change the database makes no backup.
- The backup holds the database only. It does not hold your rendered videos or the videos' working
  files, which an upgrade does not touch.
- An upgrade often writes two backup files. Both are valid.
- Tubematic does not delete old backups. Remove them yourself when they take too much space.

A backup holds your API keys in plain text, as the database does.

## Rollback policy

Tubematic upgrades in one direction. An older version cannot be relied on to read a database that
a newer version has changed, so going back means restoring the backup taken before the upgrade.

Restoring a backup discards everything recorded since the upgrade: new videos, comments and setting
changes. Files rendered since then stay on disk, with no record pointing at them.

1. Stop Tubematic, from the directory of the version you are leaving:

   ```bash
   python3 scripts/service.py stop
   ```

   If you are going back to a version before 2.1.0, also remove the worker container, which older
   versions do not know about:

   ```bash
   docker rm -f tubematic-worker
   ```

   Versions before 2.1.0 cannot use remote renderers. Remove each one on its own machine with
   `python3 tubematic_remote_renderer.py remove`.

2. Restore the backup, if the upgrade made one. The backup file belongs to root, so copy it with
   `sudo`:

   ```bash
   sudo cp ~/.tubematic-data/backups/tubematic-before-vX.Y.Z-<timestamp>.db ~/.tubematic-data/data/tubematic.db
   rm -f ~/.tubematic-data/data/tubematic.db-wal ~/.tubematic-data/data/tubematic.db-shm
   ```

   If the upgrade made no backup, it did not change the database. Skip this step.

3. Go back to the older version's directory. On a release install, use the directory you kept, or
   download and extract that release again. On a source install, run `git checkout v<old>`.

   A successful upgrade removed the older version's images. Step 4 pulls them again on a release
   install and rebuilds them on a source install, which takes time and needs nothing from you.

4. Start the older version from there:

   ```bash
   python3 upgrade.py
   ```

   This also points your scheduled job back at that directory.

## Version numbers

Versions are written `MAJOR.MINOR.PATCH`.

| Part | Changes when |
|---|---|
| Patch | Something is fixed. `upgrade.py` handles everything |
| Minor | Something is added. Existing installs keep working as they are |
| Major | You have to do something by hand before or after upgrading, or something you relied on was removed |

Whatever the size of the step, read the Upgrade notes first, and follow the rollback policy above to
go back.

How releases are built is in [Releases](../developer/18-releases.md).
