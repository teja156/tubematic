"""0031 — the rollback fence for external styles (TMDEV-252).

From this version a video can be in an installed external style: its
videos.visual_style is an `ext_...` id. 2.3.x knows no such style and would
render that video blank.

This migration changes no data. Its only effect is the schema version: the
upgrade that applies it takes the automatic pre-migration backup, and 2.3.x's
upgrade.py refuses a database newer than it understands. Going back to 2.3.x
therefore means restoring that backup (Rollback policy in
docs/user-guide/07-upgrading.md), which holds no external-style video.

One-way.

*** THIS FILE HAS SHIPPED ONCE MERGED. DO NOT EDIT IT. ***
"""


def up(con):
    pass
