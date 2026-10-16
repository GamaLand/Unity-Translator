CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE project(id TEXT PRIMARY KEY, source_language TEXT NOT NULL,
 target_language TEXT NOT NULL, game_path TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE source_snapshots(id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
 metadata_json TEXT NOT NULL);
CREATE TABLE text_units(unit_id TEXT PRIMARY KEY, original_key TEXT NOT NULL,
 source_file TEXT NOT NULL, source_object INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 source_revision TEXT);
CREATE TABLE source_revisions(id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES text_units,
 source_language TEXT NOT NULL, source_text TEXT NOT NULL, source_hash TEXT NOT NULL,
 category TEXT NOT NULL, context TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE snapshot_units(snapshot_id TEXT NOT NULL REFERENCES source_snapshots,
 unit_id TEXT NOT NULL REFERENCES text_units, source_revision TEXT NOT NULL REFERENCES source_revisions,
 PRIMARY KEY(snapshot_id,unit_id));
CREATE TABLE translation_revisions(id TEXT PRIMARY KEY,
 source_revision TEXT NOT NULL REFERENCES source_revisions, target_language TEXT NOT NULL,
 text TEXT NOT NULL, origin TEXT NOT NULL CHECK(origin IN ('model','manual','import')),
 metadata_json TEXT NOT NULL, issues_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE work_items(unit_id TEXT PRIMARY KEY REFERENCES text_units,
 status TEXT NOT NULL CHECK(status IN ('pending','processing','translated','validation_error',
 'needs_review','approved')), translation_revision TEXT REFERENCES translation_revisions,
 approved_source TEXT REFERENCES source_revisions,
 approved_translation TEXT REFERENCES translation_revisions, version INTEGER NOT NULL DEFAULT 0);
CREATE INDEX source_category ON source_revisions(category);
CREATE INDEX work_status ON work_items(status);
