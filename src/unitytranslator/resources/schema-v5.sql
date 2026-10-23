-- Source ownership is metadata; legacy unit IDs, revisions and approvals stay intact.
CREATE TABLE source_descriptors(
 id TEXT PRIMARY KEY,
 adapter_id TEXT NOT NULL,
 profile_id TEXT NOT NULL,
 schema_version TEXT NOT NULL,
 source_file TEXT NOT NULL,
 source_object INTEGER NOT NULL,
 source_language TEXT NOT NULL,
 descriptor_json TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
INSERT INTO source_descriptors
 SELECT 'legacy-file-v1:' || source_file, 'i2', 'legacy-i2', 'i2-v1', source_file,
 -1, (SELECT source_language FROM project),
 json_object('logical_id','legacy-file-v1:' || source_file,'adapter_id','i2',
 'profile_id','legacy-i2','schema_version','i2-v1','source_file',source_file,
 'source_object',-1,'source_language',(SELECT source_language FROM project),
 'fingerprint','','format_rules','protected-i2-v4','asset_name','','payload_fingerprint',''), 1
 FROM text_units GROUP BY source_file;
ALTER TABLE text_units ADD COLUMN logical_source_id TEXT REFERENCES source_descriptors(id);
UPDATE text_units SET logical_source_id='legacy-file-v1:' || source_file;
CREATE INDEX units_logical_source ON text_units(logical_source_id,active);
CREATE TABLE snapshot_sources(
 snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
 source_id TEXT NOT NULL REFERENCES source_descriptors(id),
 descriptor_json TEXT NOT NULL,
 PRIMARY KEY(snapshot_id,source_id)
);
-- Historical snapshot_units and metadata_json are kept verbatim. Current file
-- ownership cannot reconstruct past locations after a legacy source relocation.
