CREATE TABLE jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('prototype','pilot','bulk')),
 status TEXT NOT NULL CHECK(status IN ('queued','running','pausing','paused','completed',
 'completed_with_errors','cancelled','failed')), profile_json TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pause_requested INTEGER NOT NULL DEFAULT 0,
 cancel_requested INTEGER NOT NULL DEFAULT 0, report_seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE job_items(job_id TEXT NOT NULL REFERENCES jobs, unit_id TEXT NOT NULL REFERENCES text_units,
 source_revision TEXT NOT NULL REFERENCES source_revisions, work_version INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','processing','completed','failed','skipped','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0, claim_id TEXT, error_code TEXT,
 result_revision TEXT REFERENCES translation_revisions,
 PRIMARY KEY(job_id,unit_id));
CREATE INDEX job_pending ON job_items(job_id,status);
CREATE TABLE translation_runs(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs,
 unit_id TEXT NOT NULL REFERENCES text_units, source_revision TEXT NOT NULL REFERENCES source_revisions,
 attempt INTEGER NOT NULL, metadata_json TEXT NOT NULL, status TEXT NOT NULL,
 elapsed_seconds REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 UNIQUE(job_id,unit_id,attempt));
CREATE TABLE glossary_versions(id TEXT PRIMARY KEY, rules_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE style_versions(id TEXT PRIMARY KEY, styles_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE project_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
