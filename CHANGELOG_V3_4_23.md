# V3.4.23 — persistent runtime database and release migrations

- Release ZIPs no longer contain `data/` or any mutable runtime state.
- `data/dashboard.sqlite` is now explicitly persistent installation state and is resolved from the Dollar Watch install root, not the shell working directory.
- `data/official_policy_cache.json` follows the same persistent-path rule and is no longer packaged/reset by releases.
- Added `database/migrations/` for release-owned schema definition and indexed migration history.
- Added `schema_migrations` audit records. Only unapplied migrations run.
- Before an existing database receives pending migrations, Dollar Watch creates a consistent SQLite backup under `data/backups/` using SQLite's backup API (WAL-safe).
- Existing pre-V3.4.23 databases are migrated in place. No snapshot/settings/evidence tables are dropped or replaced.
- Added `DOLLAR_WATCH_DATA_DIR` as a persistent-directory override; existing `DOLLAR_DASHBOARD_DB` and `DOLLAR_POLICY_CACHE` overrides remain supported.
- Windows/Linux launchers anchor themselves to the installation directory.
- Data Health now displays the absolute database path, database size, snapshot count, oldest/newest snapshot, migration version, and latest pre-migration backup, with a warning when history is unexpectedly sparse.
- Analytical schema remains 3.4.1; score model remains 3.4.3. No regime scoring, trigger, portfolio, or fixed-horizon math changes.
