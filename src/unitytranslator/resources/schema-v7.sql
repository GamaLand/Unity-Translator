-- Lookup indexes only: records, identities, approvals and history stay unchanged.
CREATE INDEX source_revisions_unit ON source_revisions(unit_id,created_at,id);
CREATE INDEX translation_revisions_source ON translation_revisions(source_revision,created_at);
-- Review order only; no leading active column, so full-table counts keep their scan.
CREATE INDEX units_review_order ON text_units(original_key,unit_id);
