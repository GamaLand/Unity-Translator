# Experimental runtime components

## Components and boundaries

The Python application prepares approved data and an additive file plan. The I2 Mono
C# plugin applies that data in memory after checking Unity/game fingerprints and source
text hashes. The protected BepInEx preloader and Doorstop bootstrap load the plugin.
These are separate components: a readable source is not proof that a loader is compatible.

`runtime-kit-catalog.json` and `portable-runtime-kit-catalog.json` pin the normal and
portable bundles separately. `adapters/i2mono/loader-components.json` records upstream
provenance. Runtime binaries, upstream source caches and proprietary game references
are not committed to the source repository.

## Payload and language selection

Runtime JSON v2 contains an explicit source language and target language/name. The
plugin also reads legacy v1 payloads with an implicit English source. The parser has
fixed schemas, bounded depth/size/record counts and rejects unknown or duplicate fields.
Only current approved revisions are exported, with a limit of 100,000 records and
64 MiB. The selected source column must be unique and its term hashes must match
before any write. An existing source column cannot be overwritten as the target.

Untranslated target text falls back to the source. Existing target font/asset
references are retained. Language/culture, RTL and joined-word state are set in I2
memory rather than through a persistent language-preference API. Language lists,
term arrays, touch fields, flags and prior language state are restored on failure;
incomplete rollback is reported as failure. Scene replacement sources are checked
again; the same source object is not repeatedly rewritten.

## Protected preloader

The stock loader can create persistent interop/shim DLLs and game-root logs. The
protected build removes the registered shim paths and redirects bounded, create-new
diagnostics into its external runtime. Its guard rejects an absent/overlapping runtime
identity. The separately cataloged portable guard accepts only the owned
`UnityTranslatorPatch` layout and marker; editing an INI is not a substitute.

Configuration, cache and logging paths are prepared in the owned runtime tree.
Diagnostics are optional local data and are not telemetry. Path checks and static CIL
analysis do not prove freedom from every concurrent path change or native side effect.
See [installation.md](installation.md) for the inventory/ownership boundary.

## Build and source correspondence

Use `tools/build_i2mono.py` with explicit managed-reference, BepInEx-core and compiler
paths. References are statically read and their hashes must remain unchanged; the game
assemblies are not executed or distributed. Compile into a temporary output and publish
only a successful build with matching evidence.

`tools/prepare_protected_preloader.py`, `tools/audit_protected_preloader.py` and
`tools/stage_protected_source.py` prepare and audit registered upstream modifications.
`tools/stage_loader_support.py` and `tools/build_runtime_kit.py` include dependency
licenses and corresponding sources. `tools/package_portable_kit.py` produces the
separately traced portable bundle. Do not remove these tools as obsolete prototypes:
they form the runtime provenance/build chain.

The [component audit](loader-component-audit.md), [protected source trace](protected-source-trace.md)
and [source-access document](SOURCE-ACCESS.md) retain the detailed ownership and
redistribution information. Original license texts and owners must remain unchanged.
Updating plugin source requires rebuilding the matching binary, source archive,
notices and catalogs before claiming a new binary release. Never just update a hash
catalog to make an unrelated DLL pass validation.
