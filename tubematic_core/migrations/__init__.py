"""Versioned schema migrations.

Files are named NNNN_<name>.sql or NNNN_<name>.py and applied in ascending
numeric order by tubematic_core.db.migrate().

ONCE A MIGRATION HAS SHIPPED IN A RELEASE IT IS IMMUTABLE. Changing one
silently diverges every database that already applied it from every database
that has not. New schema work means a new file.
"""
