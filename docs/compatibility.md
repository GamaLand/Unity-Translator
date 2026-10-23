# Compatibility

Current version: UnityTranslator 0.4.0. The previous published validation baseline
is 0.1.0 RC7, validated on 16 October 2026. Current Krypta evidence is scoped below.
Source additions described below were validated locally on 23 October 2026; they do
not replace published RC7 artifacts or establish new installation support.

## Current support

| Capability | Current status |
| --- | --- |
| Desktop application | Windows x64, Python 3.12 and PySide6 Widgets |
| Model connection | Existing local LM Studio or llama.cpp HTTP endpoint; server/model start is manual |
| Source extraction | Identified I2 Localization structures through UnityPy; a narrow Unity 2017 Mono metadata fallback |
| Krypta FM text sources | Reviewed Unity 2022.3.10f1/Mono build: 442 fields from 34 TextAssets plus 7 journal objective fields from one pinned literal grid; 449 fields total |
| TextAsset export | Staged approved payload files in the project, with original control fields and source hash checks |
| Krypta FM installation | Normal UI installation unsupported; separate experimental reviewed trial, with only a three-label menu pilot observed in-game |
| Translation languages | Editable language tags, 32 suggestions, independent of the eight interface languages |
| Runtime application | Experimental Mono/I2 plugin with matching game, Unity, managed-reference and binary fingerprints |
| Reference game | An identified build of Warhammer 40,000: Mechanicus |
| Shareable patches | Self-contained runtime; recipient needs no UnityTranslator, Python or model |
| JSON import/export | Translation project interchange; not a generic game JSON reader |
| Generic JSON/CSV/XML game files | Planned; not implemented |
| Unity Localization String Tables | Planned; not implemented |
| General AssetBundle/Addressables traversal | Planned; not implemented |
| IL2CPP runtime application | Not implemented |
| Unreal Engine | Outside the Unity roadmap |

Mono/IL2CPP describe code execution backends. Asset containers and localization
systems are separate concerns. A Mono directory, a `.json` extension or an `.assets`
file alone does not establish translation or installation support. The current game
profile is a discovery hint; the runtime kit's fingerprints remain an additional gate.

## What was verified

The reference game's main menu and Turkish glyphs were verified by the user. RC7's
packaged reader extracted 6,737 French records without errors and without changing
the source asset hash. Synthetic tests cover non-English sources, English targets,
Japanese/Italian/Arabic/Brazilian-Portuguese pairs, regional ambiguity, approvals,
source hashes, memory rollback and right-to-left state selection.

These results do not verify all game scenes, every language's rendering, another
build of the reference game or another Unity game. The standalone synthetic check
ran on a development machine with an isolated PATH, not on a clean Windows VM.
A physical llama.cpp server test and clean Windows validation remain deferred.

## Language limits

The Krypta FM profile requires English as its source language. Locale mappings are
bound to reviewed serialized references and managed metadata fingerprints, not filename
suffixes. It covers menu, forum/message, key-post and subtitle payloads in three
sharedassets containers. A shared locale source and a malformed forum source are
explicitly excluded; per-source coverage appears in the extraction/export manifests.
Serialized UI labels outside the menu file, user profiles, textures
and hard-coded assembly strings are outside this profile. Extraction/export support
does not mean complete game coverage. The bounded local export check used synthetic
fixture approvals in a private QA project. A later user-reviewed three-label menu
pilot rendered Turkish text, including `ş`, `ç` and `ı`, in the actual game, and original
hashes matched after exit. A separate live local-model pilot produces unapproved
candidates. Settings/language switching, scene reload, other runtime consumers and
full-game Turkish gameplay remain unverified. Profile revision 2 adds seven English
journal objective literals from the pinned constructor's 4x3 grid. Existing TextAsset
source identities, revisions, drafts and approvals remain intact. The fixed journal
runtime hook compiles and passes synthetic rollback tests but is unverified in-game.

The selected source language must exist in the source data. Exact tags are preferred;
an unambiguous base-language fallback is permitted. An explicit region never silently
selects a different region. Missing/ambiguous columns are rejected. The model must
support the selected pair. Existing custom styles remain user data; review old
language-specific rules before using a different target language.

Existing target font/asset references are retained. No fonts are downloaded or
injected. Font coverage, shaping, right-to-left layout, text overflow and plural
categories still need game-specific review. Existing I2 plural branch structures are
preserved; this is not automatic plural-rule conversion. Semantic negation/condition
heuristics currently cover English-to-Turkish only; universal checks apply to all pairs.

## Reporting a new game

Include the game/version, runtime indicators, detected localization system, a sanitized
compatibility report and the failing step. Do not upload game assets, DLLs, models,
translation databases, personal paths or extracted copyrighted text to the public repo.
An unsupported installation must not fall back to replacing original game files.
See the [roadmap](roadmap.md) for the acceptance gates for new adapters and profiles.
