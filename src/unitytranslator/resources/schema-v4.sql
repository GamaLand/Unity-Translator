-- İnceleme taslağı çeviri/onay değildir; kaynak ve iş sürümüne bağlıdır.
CREATE TABLE editor_drafts(
 unit_id TEXT NOT NULL UNIQUE REFERENCES text_units,
 source_revision TEXT NOT NULL REFERENCES source_revisions,
 base_version INTEGER NOT NULL CHECK(base_version >= 0),
 revision INTEGER PRIMARY KEY AUTOINCREMENT,
 text TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
