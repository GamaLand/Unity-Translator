# Compatibility

Current version: UnityTranslator 0.6.1. The previous published validation baseline
is 0.1.0 RC7, validated on 16 October 2026. Current Krypta evidence is scoped below.
Source additions described below were validated locally on 23 October 2026; they do
not replace published RC7 artifacts. Krypta installation evidence is scoped below.

## Current support

| Capability | Current status |
| --- | --- |
| Desktop application | Windows x64, Python 3.12 and PySide6 Widgets |
| Model connection | Existing local LM Studio or llama.cpp HTTP endpoint; server/model start is manual |
| Source extraction | Identified I2 Localization structures through UnityPy; a narrow Unity 2017 Mono metadata fallback |
| Krypta FM text sources | Reviewed Unity 2022.3.10f1/Mono build: 442 fields from 34 TextAssets plus 7 journal objective fields from one pinned literal grid; 449 fields total |
| TextAsset export | Staged approved payload files in the project, with original control fields and source hash checks |
| Krypta FM installation | Reviewed experimental UI installation for the pinned en→tr build; limited runtime observation accepted by the user, with remaining screens checked manually |
| Translation languages | Editable language tags, 32 suggestions, independent of the eight interface languages |
| Runtime application | Experimental Mono/I2 plugin with matching game, Unity, managed-reference and binary fingerprints |
| Reference game | An identified build of Warhammer 40,000: Mechanicus |
| Shareable patches | Pinned I2 and Krypta en→tr builds; self-contained runtime, reviewed file plan, no UnityTranslator/Python/model required for recipients |
| JSON import/export | Translation project interchange; not a generic game JSON reader |
| Generic JSON/CSV/XML game files | Planned; not implemented |
| Unity Localization String Tables | Planned; not implemented |
| General AssetBundle/Addressables traversal | Planned; not implemented |
| IL2CPP runtime application | Not implemented |
| Ren'Py | Native templates and audited static `.rpy`/`_ren.py`/RPA-3.0 sources, shared review and sharded staging. New ZIPs add approved text/helpers to the matching 8.1.2.23090503 game without copying it. Windows recipient checks are synthetic; real original-folder launch/removal remains unverified. Legacy full-copy ZIPs and their limited copy pilots retain their earlier scope. |
| Unreal Engine | Planned testing and implementation after broader Unity/Ren'Py support; no current support |
| Godot | Planned testing and implementation after broader Unity/Ren'Py support; no current support |

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
Krypta shareable packages use the same scoped plugin with the separately guarded
portable preloader. Synthetic recipient install/remove and source/ownership checks
do not establish in-game validation of this portable combination. The observed
Krypta trial used the external project runtime.

## Language limits

Version 0.6.1 fixes repeated full-inventory pilot sorts and preparation shutdown.
Read-only inspection of the user-selected large Ren'Py project found 93,937 pending
units, a queued 200-record pilot and no model attempts, translations or drafts. On
a private consistent diagnostic copy, the old selector reached only 37 queries in
30 seconds before the diagnostic stopped it; the single-pass selector prepared
the same-size sample in 0.73 seconds. Full cold source-context/queue preparation
completed in 17.7 seconds with zero model attempts. These are local preparation
measurements; all 200 selected identities and their queue order matched the original
saved pilot. They are not model throughput or a universal latency bound. The original
project and game were not opened for writing or translated during diagnosis.
Synthetic checks cover busy Python/SQL preparation, immediate cancellation before
backend dispatch, safe shutdown, rollback, retained old jobs and resumed cold-context
cancellation. Existing identities, approvals, drafts and schema 6 stay unchanged.

Version 0.6.0 offers optional, source-only neighbouring dialogue context. Synthetic
checks establish consecutive Ren'Py source-segment and within-template-block
ordering, branch/flow/exclusion barriers, filtered/paged review, bounded reference
requests and unchanged output validation. Unity/I2, current TextAsset layouts and
imported-only sources retain isolated translation because narrative order is not
proven. This is not a full playthrough order or a verified naturalness improvement.
The evaluation and continuation rules are in
[Development](development.md#source-order-and-neighbouring-dialogue-context).

On 31 October, the shared queue compared eight synthetic English-to-Turkish targets
in isolated/context modes on the user's already-loaded llama.cpp
`Hauhaucs/Gemma4_26B_A4B_Uncensored_HauhauCS_Balanced_IQ3_M` model, with an 8,704-token
server slot, temperature zero and JSON schema. At 2,048 output tokens, isolated mode
completed six targets and context mode seven; remaining failures were truncations.
Repeating both modes at 4,096 output tokens completed all eight without retries,
schema/token errors, tool calls or truncation. Each contextual request retained both
neighbours. Total measured times were 66.6/68.6 seconds; concurrent development work
and this tiny sample prevent performance or error-rate generalization.
Context resolved a metal-versus-leadership ambiguity and clarified phone/injury
references, but a figurative coldness case remained literal in the second comparison
and awkward target grammar remained. This supports optional use, not a quality
guarantee. Source-only malicious-instruction dialogue did not add output records;
interpolation, rich-text markers, numbers and negation survived the completed stress
target. No game text, existing project, server startup, model loading, download,
installation, game launch or translation approval was involved.

Synthetic review checks cover filtered bulk approval of exact source copies across
page boundaries and returning empty translations to Pending without deleting
history or starting generation. Draft/queued/processing exclusions, explicit
confirmation, stale preview rejection and the compact localized menu are checked.
These actions do not establish translation quality or approve records automatically.
Additional synthetic checks cover empty records shared by multiple paused queues,
version-based skipping on resume, preserved job/attempt history and atomic rejection
when those queues or drafts change after preview.

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
hashes matched after exit. A later trial applied 449 current approved translations
with the journal-capable binary. Startup/menu, options, transition into gameplay,
pause and Turkish subtitles were observed, and original hashes matched after user exit.
The user accepted this limited observation and will inspect remaining translation quality.
Forum/journal display, language switching, scene reload and full-game coverage remain
unverified. A long settings label overlapped its explanation; control-help labels
outside the profile remained English. Profile revision 2 adds seven English
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
See the [Ren'Py roadmap and later engine work](development.md#renpy-roadmap) for the acceptance gates for new adapters and profiles.

## Release evidence (historical)

This consolidates the former release audit. Each row describes checks recorded for
that version, not tests rerun for this documentation change or proof about later
code. Published artifacts and matching source/license archives remain immutable.

| Version / event | Recorded evidence and limits |
| --- | --- |
| 0.6.1 local candidate | Single-pass representative pilot selection, visible preparation stages and cooperative cancel/close without starting a late model request. All 200 identities/order matched the original pilot in a private diagnostic copy. Ruff/mypy, 1,020 Python tests (one skipped), relevant synthetic C# checks, eight catalogs/guides and the new standalone isolated-PATH smoke check passed. The original 93,937-record project remained pending with its one queued pilot and zero model attempts, translations or drafts. No game launch/install or real-game translation ran. |
| 0.6.0 local candidate | Optional Ren'Py source windows, safe source ordering and backed-up schema-6 job evidence. Ruff/mypy passed; the full Python run passed 1,010 tests with one skipped, and the final context/cache suite passed 38 targeted checks. Relevant synthetic C# suites passed. The new Windows package passed the isolated-PATH Qt/edit/draft/approval/export/worker smoke check on the development machine. Source/wheel privacy and guide audits passed. The small llama.cpp comparison above is not universal quality, performance, gameplay or clean-Windows evidence. No release publication is implied. |
| 0.5.0 | Shareable I2 and pinned Krypta en-to-tr packages. Synthetic recipient install/remove, relocation, links, changed files, wrong builds, tampering, plan approval and Qt export checks. Both kits' sources/licenses and shared core hash agreement are required. Portable Krypta gameplay and clean Windows remain deferred. |
| 0.4.2 | Reviewed experimental Krypta UI install/remove, readiness bound to the observed plugin hash. A user-approved 449-translation trial showed startup/menu, options, transition into gameplay, pause and subtitles; original hashes matched after exit. Remaining consumers/quality/lifecycle checks were retained by the user. Its then-I2-only ZIP limitation was superseded by 0.5.0. |
| 0.4.1 | Completed projects no longer queue empty pilot jobs; stale requests preserve approvals. Adapter-aware small/runtime-data exports remain distinct from installable ZIPs. Shareable ZIPs were I2-only at that version. |
| 0.4.0 | Built-in contracts, backed-up schema-5 ownership, scoped 449-field Krypta pipeline and approved exports. Recorded 601 Python tests passed, one skipped; Ruff/mypy passed; Krypta C# suites covered 18 data and 27 lifecycle scenarios. Development-machine standalone UI/extraction checks retained original hashes. Runtime evidence at that time was only the earlier three-label menu pilot; later observation belongs to 0.4.2. |
| 0.1.0 RC7, 16 October 2026 | 481 Python tests passed, one skipped; Ruff/mypy and C# payload/hash/language/rollback checks passed. Development-machine synthetic Qt checks covered review, drafts, Unicode, install/export and workers with isolated PATH. Packaged extraction read 6,737 French records without changing the source hash. The user verified the reference game's main menu and Turkish glyphs. |
| Cleanup after RC7, 16 October 2026 | 488 Python tests passed, one skipped; Ruff/mypy and the then-three C# suites passed, including 14 diagnostics and six portable-guard scenarios. Eight localized help actions and seven CLI help checks passed. The then-27 public Markdown files/67 links and source archives were audited. These are historical counts; current layout uses the consolidated documents. |

The cleanup moved user guides to `guide/` and synchronized help, wheel/sdist and
future Windows packaging. Older RC7 ZIPs may keep their original layout. Source
archives excluded local AI instructions, real game/model data, user projects and
build caches. Historical manual evidence never authorizes a new game launch.

## Next support boundary

Original-source reading now uses audited source behavior instead of an exact version
allowlist. Critical canonicalization, ID/grouping, lexer/parser and source-loading
declarations were compared in official 8.1.2.23090503 and 8.3.6.25022803 sources.
An unknown version with matching contracts can be read; missing or changed contracts
refuse reading. The legacy 8.1.2 profile remains for layouts without engine source.
This does not establish a continuous version range or Ren'Py 7/Python 2 support.
The recipient ZIP retains its separate exact 8.1.2.23090503 runtime gate.

The static subset supports symbolic attributes/removals, temporary `@` attributes,
`nointeract`, explicit literal UI/menu keys and verified `_ren.py` block conversion.
A menu say before choices retains implicit `nointeract`; reordered or caption-mixed
forms refuse reading. Disjoint loose/archive unions retain provenance and reject
overlapping paths/effective basenames. Compiled-only input, dynamic text, multiline
dialogue, voice/nvl groups and image labels remain unsupported. Exclusions are counted.

Synthetic checks cover native-ID vectors, logical multiline expressions and opaque
block boundaries, source/approval continuity, complete-scope failure, over 32 MiB
framed reports, incremental limits and block-preserving native shards. Recipient
checks reject cross-file ID/key conflicts and structure/token injection. An old
project's anchor remains stable when a new filename sorts earlier. Native staging
does not grant installation authority; the
[broader milestone](development.md#broader-renpy-support-planned), including wider
runtime families and overlapping/mod resolution, remains incomplete.

Ren'Py discovery reports engine hints, input/container kind and bounded static version
evidence separately from extraction, translation, export and installation support.
Mixed-engine auto detection requires an explicit inspection selection; this grants
no installation authority. Real-game inspection on 28 October 2026 found an RPA-3.0
archive and static Ren'Py 8.1.2.23090503 version evidence in the user-selected
Invulnerable 1.10 build. No loose `game/tl` templates were present. Bounded literal
index inspection found 2,776 members, including 84 `.rpy` and 84 `.rpyc` files;
only default-language common `.rpym`/`.rpymc` translation modules were present.
Selected source members were read as bytes without engine execution or object
deserialization. The active main menu uses image buttons; its visible labels are
image assets. The text-based `main_menu3` screen is a separate backup. Preferences
contains explicit translatable UI strings. No extraction into a game project,
installation, launch or gameplay was verified by these static checks.

Ren'Py reading supports a strict subset of existing native translation templates
through a bounded worker. Synthetic tests cover paired-comment dialogue, string
tables, token injection rejection, shared pilot/review, source/structure changes and
portable ownership without imported approvals becoming local approvals. This proves
neither full script coverage nor universal Ren'Py input support.
Native export tests cover exact approved revisions, explicit project/native language
mapping, dialogue fallback, omitted unapproved strings, global string conflicts and
rejection of source/draft/approval/output changes during staging. Outputs are reparsed
with the strict grammar and source hashes remain unchanged. The desktop exposes the
same exporter, displays template candidates as read-only provenance and flushes editor
drafts before export. These checks prove local staging, not engine loading or gameplay.
At the initial pinned-reader increment, the original-source reader extracted 9,259 records from the supplied
archive: 8,809 plain dialogue records and 450 explicit UI/menu keys. All 84 source
members matched their RPC2 source-footer digest; all 8,809 generated dialogue IDs
were present as compiled pickle string literals. That static evidence did not
deserialize objects or execute scripts. The archive hash remained unchanged. A new
private project held all records pending and had no real-game translation job.
Reported exclusions include 36 multiline/backtick literals, 38 noninteractive menu
say statements, 12 unsupported source literals, 177 says without a usable label,
1,164 unsupported say prefixes with character attributes, 31 unsupported suffixes
and one unsupported text syntax occurrence. Image-menu text
is outside text extraction. Other versions and multiple containers were unsupported
at that increment. Compiled-only input and overlapping load order remain unsupported.
RPA index inspection alone grants no deployment support.
No Ren'Py engine-version range, full-game coverage or original-root
installation/removal has been verified. See the
[design and acceptance gates](development.md#renpy-native-template-integration).

Three synthetic original-source records were sent through the real shared queue to
the user's existing local `gemma4-12b-qat-uncensored-hauhaucs-balanced` model in LM
Studio. A 512-token output budget truncated two responses; retrying those records
with 2,048 output tokens and requested `reasoning_effort="none"` completed them.
Final candidates preserved interpolation/tags/newlines and remained unapproved.
No model/server was started or downloaded and no bulk game translation ran.

A read-only inspection of a second local layout, LR2, found static Ren'Py
8.3.6.25022803 evidence, 588 loose `.rpy` files totaling 18,701,812 bytes,
289 `_ren.py` files and 877 `.rpyc` files, with no `game/tl` directory.
The initial reader refused this layout at its exact-version check; the then-128-file/
8-MiB bounds and unsupported `_ren.py` dialect were additional gaps. The current
reader verifies the installed source behavior and handles this large mixed source
layout. This supplies static reading evidence only; no new runtime compatibility,
game translation, installation or launch is implied.

On 29 October, the expanded reader processed all 877 LR2 source members into
93,937 pending records: 91,654 dialogue IDs and 2,283 global string keys. All 91,654
dialogue IDs appeared as Unicode literals in the matching RPC2 post-transformation
slot, with original-source footer digests checked. This was bounded inert opcode
inspection, without object deserialization or engine execution; literal presence
does not prove complete runtime behavior. Every tracked source, compiled script and
engine-source hash and the input inventory remained unchanged. The separate private
project contains no translation revisions, jobs or approvals. Checks exposed and
fixed commented block-header and multiline-expression false positives before the
project was activated. Reported omissions include 249 multiline/backtick literals,
262 unsupported say suffixes, 731 unsupported say literals, 19,150 unsupported
prefixes, 377 says without a usable label, eight private-name forms and unsupported
call/label mappings. These counts describe excluded syntax occurrences, not unique
missing translations or a full-game coverage percentage.

An earlier Ren'Py expansion regression run passed Ruff, mypy, 880 Python tests (one skipped)
and the relevant synthetic C# suites. The eight guides and public document links
were checked. This is development-checkout evidence, not a newly published binary.

The translated-copy ZIP has synthetic Windows checks for exact plan binding,
wrong builds/targets, native fixed grammar, nested interpolation, Unicode, token
injection, identity/link/hash removal and preservation of modified/unknown runtime
files. Qt/CLI checks use the same exporter and draft/approval gates. The package
contains no original game files or saves. It requires a matching local build and
space for a full independent copy.

On 29 October, the actual archive reader supplied a separate QA project's one
explicitly user-approved `Display` to `Ekran` record to this ZIP exporter. The user
reviewed its concrete 1,204-build-file copy plan. The package's own recipient
installer completed it and its installed launcher selected Turkish. Options rendered
`Ekran`, then main-menu Quit closed the copy normally. After exit, all 1,347 original
files and inventory membership matched; all 1,210 receipt-owned copy files remained
unchanged. Runtime files, including the 988-byte `.rpyc`, local persistent mirror,
separate saves/logs and Python/script caches, were new files in the copy. The requested
Python no-bytecode environment flag did not prevent these embedded-runtime caches.
The compiled sidecar's source footer matched, but it was not adopted as an owned
addition. Real-copy removal was not run; modified/unknown preservation has synthetic
checks. This proves the one-label archive/read/review/ZIP/install/launch path, not
full-game text, fonts or original-root installation. The main translation project
remained pending with no game translation job. Later literal-serialization refinements
for dialogue escaped spaces versus Python-style string tables were checked with
synthetic exporter/Windows recipient tests; the one-label field ZIP predates those
refinements and its string payload is unaffected. The earlier manually prepared pilot
below is separate evidence.

An earlier explicitly reviewed one-label field pilot ran on a separate full
copy of Invulnerable 1.10. A manually prepared native template for the confirmed
preferences key passed through the shared revision/approval/export pipeline; this
was not automatic archive source extraction. The user confirmed `Display` rendered
as `Ekran` and closed the game. The exact 130-byte create-new addition had a reviewed
plan and a local identity/hash receipt. All 1,347 original files and inventory
membership matched after exit. The copy gained the `.rpy` and a 986-byte `.rpyc`;
127 pre-existing copied files changed: two Ren'Py caches, the copy's local persistent
save and 124 engine Python bytecode caches. Explicit `--savedir` and log routing
created separate saves/logs but did not prevent the local persistent mirror.
These observations block an original-root no-original-writes claim; no removal was
attempted. Other text, glyphs, scenes and image-menu localization remain unverified.


## Additive Ren'Py ZIP checks

New installation ZIPs use one original-game selection and add only reviewed text,
a fixed launcher and per-package receipt/support records. Synthetic Windows checks
cover unchanged original bytes, exact new-file plans, normal-save launch review
without starting a game, build/input conflicts, ownership-safe removal and refusal
when unowned compiled translation sidecars could keep a removed translation active.
Legacy copy-package checks remain. Original-folder gameplay and automatic ownership
of engine-generated sidecars remain unverified; copy-pilot observations above do
not establish these capabilities.
