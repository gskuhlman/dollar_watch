-- Read-only performance indexes for long-lived history.
CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at ON snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_verification_checks_created_at ON verification_checks(created_at);
CREATE INDEX IF NOT EXISTS idx_verification_queue_status ON verification_queue(status);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
