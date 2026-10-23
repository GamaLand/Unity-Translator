# Roadmap: multi-game Unity translation

Status: implementation started after the multilingual RC7 baseline. This document is a product
roadmap, not a list of supported formats. Current support is in [compatibility.md](compatibility.md).
Updated: 23 October 2026. M1 contracts/source ownership and the reviewed M2
TextAsset extraction/staging path are implemented in this checkout. M3/M4 remain planned.

The built-in registry wraps the existing I2 path and a fingerprint-bound Krypta FM
reader. Schema 5 migrates legacy projects with a consistent backup, preserving IDs,
revisions, drafts, approvals, jobs and receipts. Complete source sets activate
atomically; independent TextAssets in the same container have separate ownership.
Shared UI/CLI reports retain legacy discovery fields and separate four capabilities.

For the reviewed Krypta FM build, the bounded reader extracts 442 English fields
from 34 menu, forum/message, key-post and subtitle TextAssets across three containers,
plus seven journal objective literals from the pinned constructor's 4x3 array.
Profile revision 2 therefore has 449 fields across 35 logical sources. The original
442 record states were preserved in the local expansion check.
Two reviewed source exclusions are explicit: a shared locale reference and a malformed
forum payload. Other serialized UI, user profiles and texture text remain
outside this profile. Local extraction/staged export checks preserved all input hashes;
the QA export used synthetic fixture approvals in a separate project. This is not
complete game text coverage. Normal installation remains unsupported; a separate
experimental three-label menu trial was observed in-game. The newer journal-capable
runtime has passed compile/synthetic checks but has not been tested in-game.

## Next milestone

Deliver built-in adapter contracts, evidence-based compatibility reporting and
source-scoped persistence first (M1), then TextAsset extraction and staged exports
using Krypta FM as the first custom-format target (M2). Follow with structured
JSON/CSV game-source readers (M3) and a second verified I2 game profile (M4).
Reuse the existing translation queue, model providers, SQLite revisions, glossary,
review/drafts and approval system. Do not build a second translation pipeline.

### 1. Separate detection from capability (M1)

Represent runtime (Mono/IL2CPP), container (loose file/serialized asset/bundle) and
localization system (I2/Unity Localization/custom table) independently. Report extraction,
translation, export and installation capabilities separately, with `supported`,
`unsupported` or `unknown` plus reasons, evidence and adapter/profile versions.
A filename or directory hint alone must never enable an installer.
Distinguish a candidate container from a verified text source. Report unavailable type
trees, unsupported schemas and no matching localization reader separately; expose
actionable reasons instead of treating every empty extraction as the same failure.

### 2. Introduce built-in contracts without breaking existing projects (M1)

Define reader probe/extract contracts and deployment probe/prepare contracts. Register
only bundled adapters; data profiles cannot import Python, execute commands or choose
reflection targets. Wrap the existing I2 path first. Keep its stable identities,
approvals, pilot behavior, original inventories and removal receipts compatible.

Define source-scoped snapshots and stable identities before ingesting multiple files.
The current ingest path must not deactivate one file's records when another is read.
Any required SQLite migration needs a consistent backup, transactional changes,
old-project tests and an explicit schema/version transition.
Complete this persistence gate before M2 or any other multi-source reader.

### 3. Read TextAssets and custom line formats first (M2)

Read-only inspection of a local Krypta FM build found Unity 2022.3.10f1/Mono and
custom text sources rather than a verified I2 source. Menu TextAssets occur in
`sharedassets0.assets`; forum/message/subtitle sources occur in `sharedassets1.assets`
and `sharedassets2.assets`. Sampled content uses custom line layouts, not JSON/CSV.
That initial inspection alone did not establish complete coverage or installation
support; the implemented extraction scope is listed above. Keep real assets, assemblies, extracted text and local reports
out of the repository and public fixtures.

Separate bounded serialized-container discovery and TextAsset payload reading from
format-specific parsing. Inspect candidate containers with size/count limits and
cancellation in the existing worker boundary. Do not depend on a scene file containing
all text, execute game assemblies or add general bundle traversal to this milestone.

Start with explicit built-in parsers for menu, forum/message and subtitle layouts.
Review how the game consumes these layouts before fixing the schemas. Profiles select
validated data mappings; they cannot supply parser code or reflection targets. Verify
locale mappings from source references and schema evidence, not filename suffixes
alone. Report excluded or unresolved sources so partial discovery cannot imply full
game coverage.

Translate only declared text fields. Preserve section markers, IDs, dates, control
tokens, line order, empty lines, encoding/BOM/newlines and any timing or reference
fields identified by the schema. A generic "translate every line" path is insufficient.
Use container/source identity plus verified record keys; positional layouts need a
versioned identity policy that detects insertions/reordering without silently moving
approvals to different strings.

Feed extracted records into the existing translation/review pipeline. Reconstruct
approved payloads only in the separate project export directory, with source hashes,
schema/profile versions and source-to-payload mappings. These are staged payloads,
not rewritten Unity assets or an installable patch. Validate non-text structure and
reject stale source fingerprints or approval revisions before publishing exports.

### 4. Read and export JSON/CSV safely (M3)

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

### 5. Add another I2 game profile (M4)

A profile records evidence, supported source schema, runtime requirements and matching
fingerprints. Another game requires its own probe and bounded runtime check, not a
relaxed global fingerprint check. If a second installation is unavailable, synthetic
profile coverage may ship but actual support stays unverified. Real game data is never
added to CI or public fixtures.
Krypta FM is the custom TextAsset target; it does not satisfy the second-I2 gate.

### 6. Verify deployment separately

The user's Turkish-gameplay goal now includes this gate. The scoped
[Krypta FM runtime design](krypta-runtime-design.md) has a compiled experimental
candidate and a user-reviewed three-label menu pilot observed in-game. Original
hashes matched after exit. Other consumers and lifecycle checks remain unverified.

For Krypta FM, investigate an additive mod/language location or a dedicated runtime
adapter only after source formats and staged exports are verified. The existing
Mechanicus/I2 runtime is not evidence of compatibility. Record the exact blocker if
no safe additive route exists; never replace, rename or delete an original asset.
Runtime implementation requires its own scoped design and evidence gate.

Any later installation requires matching game/build/runtime fingerprints, current
approved revisions and a reviewed concrete create-new file plan. Retain original
inventories and ownership receipts. This roadmap authorizes no game launch or install.

## Acceptance gates

- Existing RC7 projects reopen without losing revisions, drafts, approvals or receipts.
- Reader selection is deterministic and unknown sources remain unsupported/unknown.
- M1 migrations and source-scoped updates preserve other sources, approvals and drafts;
  failed or partial reads cannot activate an incomplete replacement source set.
- M2 synthetic fixtures cover all declared line layouts, control fields, empty lines,
  Unicode, encoding/newlines, malformed data, locale ambiguity, identity changes and
  bounded worker cancellation. Round trips retain non-text content and source hashes.
- A bounded local Krypta FM check records per-source counts, exclusions, schema evidence
  and unchanged source hashes. A menu-only result cannot establish full-game coverage.
- JSON/CSV synthetic fixtures cover malformed inputs, multilingual data, duplicate IDs,
  metadata retention, source changes, multiple sources and read-only source hashes.
- Exported files contain only current approved translations and original metadata.
- Stale sources or approval revisions block export. Staged TextAsset payloads are
  clearly distinguished from installable game assets.
- UI and CLI use the same services and display independent capability results.
- Unsupported installers cannot be reached through UI state, imports or profile data.
- Documentation and build artifacts describe only tested support.
- A representative second-game check is bounded and user-led; no automatic game start.

## Later milestones

The separate Krypta memory runtime now has a compiled candidate, synthetic data and
lifecycle tests, a statically audited protected loader, and experimental reviewed-plan
preparation. Only the three-label menu pilot has been observed in-game; normal
installation support is not enabled.
Candidate previews do not establish translation approval. See the
[runtime design](krypta-runtime-design.md) for the pilot and review gates.

1. XML and additional TextAsset schemas beyond the explicitly validated M2 layouts.
2. Unity Localization String Tables and validated AssetBundle/Addressables dependencies.
3. More I2 versions and community-contributed, data-only game profiles.
4. A separately designed IL2CPP application backend, with its own loader, ABI and
   lifecycle tests. Mono extraction support does not establish IL2CPP installation.
5. Optional additive font resources and better plural/layout diagnostics, with explicit
   per-game evidence. Never replace an original font or download assets automatically.

Unreal support, OCR, voice translation, model training, cloud accounts and arbitrary
third-party plugin execution remain outside this milestone. Performance/quality claims
require measurements; broad manual game-test loops are not a default development step.
