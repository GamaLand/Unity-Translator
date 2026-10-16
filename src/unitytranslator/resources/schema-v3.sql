CREATE TABLE policy_impacts(unit_id TEXT PRIMARY KEY REFERENCES text_units,
 glossary_version TEXT REFERENCES glossary_versions, style_version TEXT REFERENCES style_versions,
 reason TEXT NOT NULL, created_at TEXT NOT NULL);
ALTER TABLE job_items ADD COLUMN candidate_only INTEGER NOT NULL DEFAULT 0;
