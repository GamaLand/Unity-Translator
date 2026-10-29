# Experimental runtime components

## Unity components and boundaries

The Python application prepares approved data and an additive file plan. The I2 Mono
C# plugin applies that data in memory after checking Unity/game fingerprints and source
text hashes. The protected BepInEx preloader and Doorstop bootstrap load the plugin.
Krypta uses a separately pinned plugin described below. These are separate components: a readable source is not proof that a loader is compatible.

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

## Krypta FM scoped runtime

The pinned Unity 2022.3.10f1/Mono profile has 449 fields across 34 TextAssets and one
fixed journal literal grid, with two explicit exclusions. It is not full-game coverage.
The plugin applies reconstructed approved payloads in memory, not modified Unity
assets. Source namespace, payload hashes, profile/schema versions and exact revisions
remain part of the contract. Unapproved slots retain verified source text.

### Fixed consumers

| Consumer | Memory change |
| --- | --- |
| `TranslateManager.LoadTranslationFile` | Replace the reviewed English TextAsset reference before parsing |
| `PostInfoManager.SetPostsLanguage` | Replace reviewed English forum/key-post/message entries before copying |
| `SubtitlesManager.SetSubsLanguage` | Replace reviewed English subtitle entries before locale selection |
| `SubtitlesManager.PrepareSubList` | Check selected references against approved replacements |
| `Journal.Start` | Validate/clone the fixed English 4x3 objective array and retain the original private field for rollback |

Targets are literals in compiled code, bound to the reviewed assembly. Profiles,
imports and model strings cannot choose reflection targets. Preserve Polish and
unrelated fields. Check asset names, original UTF-8 hashes and line schemas before
constructing replacement objects. Ambiguous names, unexpected text, incomplete data
or wrong builds stop application. Do not patch native TextAsset accessors.

Validate a complete consumer replacement before assigning fields. Keep original
references for rollback; release only owned replacement objects. The journal hook
restores its private field through a compiled literal. Payload size/count/depth,
duplicate JSON fields, schemas and record shapes are bounded/validated. Logs use
fixed codes/counts without copying game text into the game directory.

`journal_grid.py` statically reads seven English objective literals. Profile revision
2 integrates them into the same bounded worker and review/export flow; the earlier
442 TextAsset record states survived re-extraction. Kits must explicitly support the
journal schema. The hook has synthetic coverage, not observed journal display.

### Preparation and installation

`krypta_trial.py` can stage an explicitly selected candidate preview containing
unapproved translations; its labels must make that clear. Preparation grants neither
approval nor installation authority. Installation rechecks review/runtime hashes,
source/translation revisions, current approvals, drafts and the identical approved
payload. Normal activation rejects the experimental adapter; the explicit reviewed
experimental UI path requires readiness tied to the observed plugin hash. A new kit
cannot inherit that readiness.

The external runtime keeps plugin, payload, loader, logs and notices in the project.
Its reviewed game plan adds only non-conflicting `winhttp.dll` and `doorstop_config.ini`
through the shared inventory/process/receipt service. Small approved-selection export
uses the same Krypta exporter, not I2 metadata assumptions. It is not an installation.
See [Installation](installation.md) for the separate shareable portable variant and
[Compatibility](compatibility.md) for observed and deferred checks. No prior trial
permits an additional game launch.

### Build and checks

```powershell
dotnet run --project adapters/kryptafm/tests/CoreTests.csproj
dotnet run --project adapters/kryptafm/tests/PluginTests.csproj
python -m pytest tests/test_krypta_trial.py tests/test_textasset_pipeline.py
```

The recorded strict-data and plugin suites cover 18 and 27 synthetic scenarios,
respectively, with stand-in game/Unity/loader types. Compilation reads proprietary
references as metadata only. Those references never enter public archives.
`tools/build_kryptafm.py` builds the plugin; `tools/build_krypta_kit.py` collects pinned
offline components, licenses and sources. That kit now includes this consolidated
runtime reference. Existing kits/source archives remain immutable.

Use `prepare_protected_preloader.py --temporary` when build tooling would otherwise
write into extracted source trees; keep source-inventory checks strict. Record native
UnityPlayer, managed-reference, compiler, loader, plugin, configuration and source
archive hashes separately. I2 compatibility and ABI never establish Krypta support.

## Other engines

These BepInEx/Doorstop components are Unity-specific. Ren'Py's native-file export
and translated-copy ZIP do not load them. Their design and acceptance gates live in
[Development](development.md#renpy-native-template-integration); Unreal remains deferred research.
