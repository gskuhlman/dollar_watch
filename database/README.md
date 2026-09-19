# Dollar Watch database definition

This directory is **release-owned** and may be replaced by every software update.
It contains the schema/migration instructions only.

The live database is **runtime-owned** and lives at `data/dashboard.sqlite` by default.
The release ZIP intentionally contains no `data/` directory, so extracting a new
release over an existing installation cannot replace the live database or policy cache.

On startup Dollar Watch:
1. resolves the persistent data path from the installation root (or an environment override),
2. opens the existing SQLite file,
3. creates a pre-migration SQLite backup when a release migration is pending,
4. applies only migrations not recorded in `schema_migrations`, and
5. continues using the same database for snapshots, settings, verification history and alerts.

Environment overrides remain supported:
- `DOLLAR_WATCH_DATA_DIR`
- `DOLLAR_DASHBOARD_DB`
- `DOLLAR_POLICY_CACHE`
