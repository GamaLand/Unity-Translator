# Krypta FM experimental memory runtime design

Status: experimental implementation and a limited local menu pilot, 23 October 2026.
A user-reviewed three-label Turkish menu pilot was installed and observed in-game;
the original inventory matched after the user closed the game. The user requested Turkish gameplay after the
TextAsset extraction/staging work. This design is a separate deployment gate;
staged export support does not establish installation compatibility.

The separate plugin compiles against the reviewed local game references without
executing them. The strict data core has 18 synthetic checks and the actual plugin
code has 27 lifecycle checks using stand-in Unity/game/loader types. A separately
rebuilt protected preloader passes its static write-policy audit. These checks do
not establish full gameplay support. The local pilot additionally demonstrated
startup, menu replacement and the rendered Turkish characters `ş`, `ç` and `ı`.
Settings/language switching, scene reload and forum/message/subtitle application
remain unverified: the UI automation helper refused input after detecting user input.
The menu trial used the earlier TextAsset-only binary. Its two unchanged owned game
additions were removed after the completed test; original hashes still matched.
The separately built journal-capable candidate is unverified in-game.
The export tab's small approved-selection action dispatches Krypta records to the
same fingerprint/revision-checked game-text exporter. It does not apply I2 snapshot
metadata checks to Krypta sources. The resulting data is still not an installation
package and does not establish runtime compatibility.

`krypta_trial.py` stages an experimental external runtime and an exact two-file
create-new plan through the shared deployment service. An explicitly selected
candidate review may contain unapproved translations, clearly labeled as such;
preparation neither approves nor installs them. Installation requires explicit
review, unchanged review/runtime hashes, the same source/translation revisions,
current approvals without unfinished drafts, and an identical approved payload.
Normal activation rejects the experimental adapter. The general UI installation
capability remains unsupported pending the remaining consumer/lifecycle checks.

The standalone EXE also extracted the pinned 442 fields from 34 sources with the
legacy `level0` selection into a new isolated project. `journal_grid.py` separately
reads seven additional English objective literals from a fixed constructor shape.
Profile revision 2 integrates them into the same bounded worker, revision/review and
staged export pipeline: 449 fields across 34 TextAssets and one journal literal grid.
The existing 442 record states were preserved in the local re-extraction check.
The compiled journal hook replaces only the English 4x3 array in memory and restores
the private field through a compiled literal on rollback. It has not been tested
in-game. A kit must explicitly support the journal schema; an older kit is rejected
before preparing a journal payload.

Developer checks (synthetic only):

```powershell
dotnet run --project adapters/kryptafm/tests/CoreTests.csproj
dotnet run --project adapters/kryptafm/tests/PluginTests.csproj
python -m pytest tests/test_krypta_trial.py tests/test_textasset_pipeline.py
```

`tools/build_kryptafm.py` builds only the plugin. `tools/build_krypta_kit.py`
collects separately pinned offline components, their matching licenses and source
archives. Proprietary compiler references and personal paths are not included.
Use `prepare_protected_preloader.py --temporary` when workspace tooling writes
build artifacts into extracted source trees; the source inventory check stays strict.

## Scope and identity

Target only the reviewed Unity 2022.3.10f1/Mono build identified by the bundled
TextAsset profile and its assembly/scene fingerprints. Record the native UnityPlayer,
managed references, compiler, loader, plugin, source archives and runtime configuration
hashes separately. Never relax the Mechanicus/I2 fingerprints or use its payload ABI.

The first runtime candidate consumes current approved TextAsset reconstructions.
Preserve source namespace, original payload hashes, profile/schema versions and exact
translation revisions. Unapproved slots retain their source text. A payload is data,
not a source of commands, reflection targets, executable code or arbitrary paths.
The 35-source/449-field profile and its two exclusions are not complete game coverage.

## Fixed game consumers

Static inspection identified these built-in patch points:

| Consumer | Candidate memory change |
| --- | --- |
| `TranslateManager.LoadTranslationFile` | Replace only its English TextAsset reference before parsing into the existing string array |
| `PostInfoManager.SetPostsLanguage` | Replace only reviewed English forum, key-post and message list entries before the game copies them |
| `SubtitlesManager.SetSubsLanguage` | Replace reviewed English subtitle list entries before locale selection |
| `SubtitlesManager.PrepareSubList` | Verify that selected subtitle references are the approved memory replacements |
| `Journal.Start` | Validate and clone only the fixed English 4x3 objective array; restore the original private field on rollback |

Patch targets must be literals in compiled code bound to the reviewed assembly. They
cannot be selected by profile/import/model strings. Preserve the Polish choice and
unrelated game fields. Verify asset names, original UTF-8 text hashes and explicit
line schemas before constructing replacement TextAssets in memory. Ambiguous names,
unexpected source text, incomplete payloads or a wrong build stop application. Never
patch native TextAsset accessors or persist modified Unity assets.

Validate a complete consumer replacement before assigning any of its fields. Keep
original references for rollback if a hook fails and release only runtime-owned
replacement objects. Bound payload size/count/depth and reject duplicate JSON fields,
unknown schemas and unexpected record shapes. Log fixed diagnostic codes and counts,
without copying game text or arbitrary exception details into the game directory.

## Loader and file plan

Build a separate plugin against Krypta FM references read as metadata only. Compile
and audit the protected external preloader against this build; cached component
sources and original licenses must match the delivered binaries. The existing
protected preloader guards are a safety implementation input, not proof of Unity
2022 startup compatibility. Inspect actual boot behavior only after the installation
and game-start review gate.

Prefer the existing external-runtime model: keep plugin, approved payload, loader
core, logs and corresponding-source notices in the separate project. A concrete
create-new game plan may add only the verified native bootstrap and its configuration
if no file conflicts exist. Use the existing deployment inventory, process-closed
checks, plan revision/hash review, ownership receipt and unchanged-owned-file removal.
Do not reset inventories, broaden exclusions or replace another loader. Imported
approval history never authorizes an installation.

## Validation and review

1. Synthetic C# tests must cover strict payload parsing, schema/control preservation,
   original hash matching, duplicate identities, replacement rollback and no file writes.
2. Static compile/reference and loader audits must preserve all original game hashes.
   Proprietary reference DLLs never enter source archives or distributions.
3. Prepare a small, concrete Turkish menu pilot, its exact candidate revisions and
   file/hash plan. Do not mark generated translations human-approved automatically.
4. Obtain review of the actual translations and create-new plan before installation.
   Obtain an applicable explicit action before starting the game. Test menu application,
   source/target switching, scene reload, Turkish glyphs and original-file hashes.
5. Investigate missing glyphs from evidence. Any fallback font must be an additive
   runtime resource; never replace a game font or download a font automatically.
6. Only after runtime and pilot evidence pass should installation capability change
   from unsupported. A failed or unavailable runtime check remains an explicit blocker.

Normal and portable loader variants remain separate. Full-game coverage, translated
textures, voices and excluded malformed sources are not proved by a successful menu
pilot. See [compatibility](compatibility.md), [installation](installation.md) and the
[roadmap](roadmap.md) for the broader evidence boundaries.
