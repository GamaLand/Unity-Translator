-- Optional local reviewer findings. A row only adds issue codes to one immutable
-- translation revision; text, revisions, stored issues, statuses and approvals stay unchanged.
CREATE TABLE local_reviews(
 id TEXT PRIMARY KEY,
 unit_id TEXT NOT NULL REFERENCES text_units,
 translation_revision TEXT NOT NULL REFERENCES translation_revisions,
 reviewer_key TEXT NOT NULL,
 reviewer_json TEXT NOT NULL,
 issues_json TEXT NOT NULL,
 note TEXT NOT NULL,
 metadata_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(translation_revision,reviewer_key)
);
CREATE INDEX local_reviews_unit ON local_reviews(unit_id,created_at);
