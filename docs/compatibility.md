# Compatibility

Baseline: UnityTranslator 0.1.0 RC7, validated on 16 October 2026.

## Current support

| Capability | Current status |
| --- | --- |
| Desktop application | Windows x64, Python 3.12 and PySide6 Widgets |
| Model connection | Existing local LM Studio or llama.cpp HTTP endpoint; server/model start is manual |
| Source extraction | Identified I2 Localization structures through UnityPy; a narrow Unity 2017 Mono metadata fallback |
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
