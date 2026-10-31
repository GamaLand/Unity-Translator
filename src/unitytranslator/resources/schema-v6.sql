-- Frozen source evidence for optional contextual jobs; old jobs remain isolated.
CREATE TABLE job_context_sources(
 job_id TEXT NOT NULL REFERENCES jobs(id),
 source_id TEXT NOT NULL REFERENCES source_descriptors(id),
 snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id),
 descriptor_json TEXT NOT NULL,
 metadata_digest TEXT NOT NULL,
 PRIMARY KEY(job_id,source_id)
);
