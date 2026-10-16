# Roadmap: multi-game Unity translation

Status: planned work after the multilingual RC7 baseline. This document is a product
roadmap, not a list of supported formats. Current support is in [compatibility.md](compatibility.md).

## Next milestone

Deliver built-in adapter contracts, evidence-based compatibility reporting, structured
JSON/CSV game-source readers, staged exports and a second verified I2 game profile.
Reuse the existing translation queue, model providers, SQLite revisions, glossary,
review/drafts and approval system. Do not build a second translation pipeline.

### 1. Separate detection from capability

Represent runtime (Mono/IL2CPP), container (loose file/serialized asset/bundle) and
localization system (I2/Unity Localization/custom table) independently. Report extraction,
translation, export and installation capabilities separately, with `supported`,
`unsupported` or `unknown` plus reasons, evidence and adapter/profile versions.
A filename or directory hint alone must never enable an installer.

### 2. Introduce built-in contracts without breaking existing projects

Define reader probe/extract contracts and deployment probe/prepare contracts. Register
only bundled adapters; data profiles cannot import Python, execute commands or choose
reflection targets. Wrap the existing I2 path first. Keep its stable identities,
approvals, pilot behavior, original inventories and removal receipts compatible.

Define source-scoped snapshots and stable identities before ingesting multiple files.
The current ingest path must not deactivate one file's records when another is read.
Any required SQLite migration needs a consistent backup, transactional changes,
old-project tests and an explicit schema/version transition.

### 3. Read and export JSON/CSV safely

Require an explicit reviewed schema/profile or field mapping: record key, source text,
locale columns/JSON paths and optional context/category. Never translate arbitrary
string values in configuration files. Preserve IDs, metadata, value types, row order,
encoding/BOM/newlines and protected variables. Reject duplicate keys/headers, ambiguous
IDs, malformed encodings and unsupported structures with actionable diagnostics.

Write translated files only to the separate project's export directory. Round-trip
fixtures must prove that non-translatable content is retained. A generated file is
not an installable patch when the game would require replacing an existing file.
Enable installation only for a verified additive language/mod location or a separately
verified runtime adapter. Label manual exports and unsupported installation clearly.

### 4. Add another I2 game profile

A profile records evidence, supported source schema, runtime requirements and matching
fingerprints. Another game requires its own probe and bounded runtime check, not a
relaxed global fingerprint check. If a second installation is unavailable, synthetic
profile coverage may ship but actual support stays unverified. Real game data is never
added to CI or public fixtures.

## Acceptance gates

- Existing RC7 projects reopen without losing revisions, drafts, approvals or receipts.
- Reader selection is deterministic and unknown sources remain unsupported/unknown.
- JSON/CSV synthetic fixtures cover malformed inputs, multilingual data, duplicate IDs,
  metadata retention, source changes, multiple sources and read-only source hashes.
- Exported files contain only current approved translations and original metadata.
- UI and CLI use the same services and display independent capability results.
- Unsupported installers cannot be reached through UI state, imports or profile data.
- Documentation and build artifacts describe only tested support.
- A representative second-game check is bounded and user-led; no automatic game start.

## Later milestones

1. XML and TextAsset readers with format-specific field mapping and protection rules.
2. Unity Localization String Tables and validated AssetBundle/Addressables dependencies.
3. More I2 versions and community-contributed, data-only game profiles.
4. A separately designed IL2CPP application backend, with its own loader, ABI and
   lifecycle tests. Mono extraction support does not establish IL2CPP installation.
5. Optional additive font resources and better plural/layout diagnostics, with explicit
   per-game evidence. Never replace an original font or download assets automatically.

Unreal support, OCR, voice translation, model training, cloud accounts and arbitrary
third-party plugin execution remain outside this milestone. Performance/quality claims
require measurements; broad manual game-test loops are not a default development step.
