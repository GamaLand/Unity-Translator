# Release validation

## 0.4.0: third feature update after the initial release

The current application and package version is 0.4.0. This update includes built-in
reader/deployment contracts, backed-up schema-5 source ownership, the bounded
449-field Krypta FM profile, approved game-text exports and adapter-aware small
runtime-data selections. Explicit LM Studio reasoning control remains model-specific.

601 Python tests passed with one skip; Ruff and mypy passed. Krypta's synthetic C#
checks cover 18 data and 27 plugin lifecycle scenarios without executing game assemblies.
The standalone development-machine UI and 449-field extraction checks passed with
original game hashes unchanged. Matching application/dependency sources and notices
accompany local Windows packages; no public binary release is implied by a source push.

Only the earlier three-label Krypta menu trial was observed in-game. The newer
journal-capable runtime, remaining consumer/language/reload checks, clean Windows
and physical llama.cpp validation remain deferred. Normal Krypta installation stays
disabled until its separate evidence gate passes. M3/M4 remain planned.

## Published baseline: 0.1.0 RC7

Validated on 16 October 2026 before the repository cleanup:

- 481 Python tests passed; one test was skipped.
- Ruff and mypy passed.
- C# checks covered legacy/v2 JSON, source hashes, multilingual language columns,
  existing targets/fonts, regional ambiguity, RTL state and rollback.
- The Windows package passed the development-machine synthetic Qt review, draft,
  Unicode, installation, export and worker checks with an isolated PATH.
- The packaged reader extracted 6,737 French records from the reference installation
  without errors; the source file hash was unchanged. No game was launched by this check.
- The user verified the reference game's translated main menu and Turkish characters.

These results do not establish clean-Windows compatibility, all scenes/languages,
another game build, a physical llama.cpp endpoint or a second supported game.

## Repository cleanup after RC7

The source uses `guide/` for its eight user guides. Help links, wheel/sdist inclusion,
source-archive inspection and future Windows packaging must follow that path. Published
RC7 ZIPs remain immutable and may retain the earlier guide directory name. Source-tree
cleanup is not a new runtime compatibility claim or a rebuilt Windows release.

Legacy prototype/release diaries have been consolidated into current compatibility,
installation, quality, runtime and development documents. SQL migrations, protected
format fixtures, source/licensing tools and original third-party notices are retained.
New roadmap items remain planned until implementation and their acceptance gates pass.

Use the current check outputs when evaluating a subsequent source commit. Do not reuse
the RC7 count above as proof that later changes passed. The public source archive must
exclude local AI instructions, real game/model data, user projects and build caches.


### Cleanup verification, 16 October 2026

488 Python tests passed with one skip; Ruff and mypy passed. All three C# suites
passed, including the 14 diagnostics and six portable-guard scenarios. The eight
locale UI checks exercise the actual help action against `guide/`; seven CLI help
checks run without game/server input. The offline documentation checker validates
27 public Markdown files, 67 local links and eight guide files. Source archives were
built in a separate audit directory and inspected for guide/catalog inclusion and
private data. Published RC7 archives and their matching source assets were preserved.
