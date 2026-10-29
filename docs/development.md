# Development

Updated: 29 October 2026. This is the single architecture, implementation plan and
roadmap reference. [Compatibility](compatibility.md) records actual support;
requirements marked **planned** do not enable a capability.

## Current architecture

The checkout is UnityTranslator 0.5.0. Python 3.12 owns project state, translation,
validation and deployment. PySide6 Widgets calls `ApplicationSession` through the
Qt bridge. An independent asyncio thread owns SQLite and job state; model HTTP
requests do not hold transactions open. Minimizing the window does not pause work.
Unity parsing uses bounded worker processes. Crash isolation is not an OS sandbox.
Extraction never executes game assemblies.

| Location under `src/unitytranslator/` | Responsibility |
| --- | --- |
| `application.py`, `__main__.py` | Shared session commands and CLI entry point |
| `domain.py`, `repository.py`, `resources/schema-v*.sql` | Records, revisions, source ownership and migrations |
| `jobs.py`, `providers.py`, `policy.py`, `validation.py` | Durable queue, local HTTP, glossary/style and format checks |
| `discovery.py`, `profiles.py`, `i2*.py`, `managed_schema.py` | Current Unity discovery and I2 reading |
| `source_contracts.py`, `reader_adapters.py`, `capabilities.py` | Bundled readers, snapshots and independent capability reports |
| `engines.py`, `renpy_dialects.py` | Bounded engine/input evidence and audited static source behavior; no engine execution |
| `renpy_templates.py`, `renpy_scripts.py`, `renpy_python.py`, `renpy_say.py`, `renpy_archive.py`, `renpy_format.py`, `renpy_export.py`, `workers/renpy*_probe.py` | Static templates, original scripts and `_ren.py` views, fixed say structure, RPA indexes, text protection and approved staging |
| `krypta_profile.py`, `journal_grid.py`, `textasset_layouts.py`, `textasset_export.py` | Pinned Krypta sources, literal grid and staged payload export |
| `worker_process.py`, `report_stream.py`, `workers/` | Bounded JSON/framed reader IPC, timeout and cancellation |
| `deployment.py`, `installation.py`, `runtime_*.py`, `krypta_runtime.py`, `krypta_trial.py`, `shareable.py` | Reviewed additive deployment and runtime/package variants |
| `editor_drafts.py`, `review_selection.py`, `portable.py`, `reports.py` | Review, history interchange, drafts and reporting |
| `ui/`, `resources/locales/` | Qt presentation and eight offline interface catalogs |

`guide/` contains localized user guides; `adapters/` contains Unity runtime C# sources,
synthetic checks and notices; `tools/` contains checks, source tracing and packaging.
Modules are mostly flat. Introduce narrow wrappers and migrate call sites gradually;
do not rename the package or reorganize all source folders to add one engine.

### Existing extension points and gaps

`SourceReader` already defines `probe`/`extract`; `ReaderRegistry` explicitly bundles
I2, Krypta and Ren'Py readers. `ReaderResult` carries complete source-scoped snapshots.
`DeploymentAdapter` wraps the existing installation services. Profiles cannot select
imports, commands or reflection targets. Do not rebuild these foundations.

The initial engine boundary is implemented: `discovery.scan` retains its legacy
Unity keys and adds a versioned `engine_report` with deterministic hints, ambiguity
and explicit inspection selection. Ren'Py inputs are classified separately as loose
scripts, template candidates, archives or compiled scripts, without executing them.
Neither directory hints nor archive signatures establish localization support.
CLI scan/probe/extract accept `--engine auto|unity|renpy`; the shared session accepts
the same selection. Overrides grant inspection only. Ren'Py files cannot reach the
Unity worker, and unknown deployment kinds are refused instead of falling through
to I2. Ren'Py/mixed-engine roots cannot select a Unity installation adapter.

`SourceDescriptor` retains its numeric `source_object` for compatibility; Ren'Py uses
the documented not-applicable sentinel `-1`, one logical source per file. It accepts
`protected-i2-v4`, `literal-lines-v1` and `renpy-text-v1` explicitly.
`result_from_report` still associates records using file/object pairs. Native Ren'Py
staging requires a separate explicit language mapping and current approvals;
a reader or exporter does not grant deployment.

### Persistence and identity

Schema 5 records logical sources and immutable snapshot descriptors. Schema-4 inputs,
portable project formats, legacy I2 IDs and runtime v1/v2 payloads remain supported
compatibility inputs. I2 IDs derive from the existing `i2-v1`/source-set/term-key
contract; do not regenerate them. Current TextAsset positional IDs include the full
payload fingerprint: edits/reordering produce new records while old states survive
as inactive history. Preserve this conservative behavior for existing projects.

A complete multi-source set activates atomically. An update affects only its source
scope; failed/partial discovery cannot replace an active complete set. Metadata
conflicts and duplicate identities fail closed. If new engine fields require storage,
add the next numbered migration with a consistent SQLite backup and a transaction;
do not retrofit old migrations or require a new schema merely for cosmetic labels.
Test reopening old projects with drafts, approvals, jobs and deployment receipts.
Historical metadata stays verbatim. Imports preserve history but never grant new
local approvals, executable jobs or deployment authority. Restored source-dependent
exports require current local source verification.

Portable format 3 preserves source descriptors and unit ownership for projects with
Ren'Py sources; existing non-Ren'Py exports remain format 2 and formats 1/2 remain
readable. Restoring format 3 retains its explicit text rules but creates no verified
local source snapshots or local approvals. Ren'Py ownership cannot be downgraded
to a legacy format. This adds no SQLite migration: schema 5 stores the validated
descriptors without changing its columns or rewriting historical records.

## Shared translation and review

All engines use the same providers, queue, policies, pilot, validation, editing and
approval services. A format is selected explicitly by source metadata throughout
generation, caching, drafts, manual edits, approval, import and export. There is no
fallback from an unknown format to I2 or literal text. Cache/pilot identities include
source/context, model/profile, glossary/style and format versions.

The pipeline masks supported tokens, checks bounded response JSON and exact record
IDs, then restores verified tokens. Duplicate keys, missing/extra records, truncation,
tool calls and invalid values are rejected with bounded retries. Model output never
chooses a path, command, executable or interpolation expression.

I2 uses `protected-i2-v4`; TextAsset uses `literal-lines-v1`; native Ren'Py templates
use `renpy-text-v1`. I2 recognizes its tested
parameter/rich-text grammar and plural branches; these rules do not apply to Ren'Py.
Current multilingual review checks are `review-multilingual-v5`. The implementation
and fixtures define the authoritative grammar. Preserve line endings and exact
protected tokens. Unknown syntax is diagnosed rather than silently rewritten.
I2 plural branches retain their source structure/order and require human review;
this does not convert target-language plural rules.

Every language pair receives applicable format, unchanged-text, number, percentage
and glossary checks with language-aware case handling. English-to-Turkish has extra
narrow negation/condition hints. Automatic checks cannot prove meaning, tone, font
coverage, shaping or layout. Equal source text does not force equal translations.

A reviewed pilot enables bulk generation only for its matching source/profile state.
An interrupted pilot can also be reviewed after cancellation if the complete required
sample was attempted, at least one result completed, and no requests remain active.
Its cancelled status, failed/unfinished records, revisions and individual approvals
remain unchanged. Too-small/unattempted samples and changed sources cannot unlock
bulk generation. Pilot reports expose this backend eligibility, show outstanding
counts and offer refresh so an earlier running snapshot does not hide the current state.
Bulk readiness distinguishes changed sources, changed profile fields and missing review.
The user may explicitly select the exact settings of a reviewed pilot for current
sources, including its pinned glossary/style versions or the historical unset values.
This changes only future-job settings; policy versions, impacts, translations and
approvals remain intact. Selection requires a current project, explicit confirmation,
no active extraction/job, and valid pinned policy versions. It neither grants a new
pilot review nor authorizes changed settings against an older pilot. New glossary/style
settings still require their own matching pilot. Reasoning-option changes refresh readiness.
It approves no individual translation. Approval binds exact source/translation
revisions. Generation and imports never replace current approvals automatically.
Changed source text invalidates approval. Editor drafts have optimistic versions;
unfinished drafts block affected export/installation selections. Page approval uses
eligible reviewed records; whole-project approval retains its two confirmations and
atomic preview revalidation. Legacy confirmation payloads are protocol data.

Jobs allow 1-16 concurrent requests. Pause stops new claims and saves in-flight
results; cancellation closes client tasks. Recovery retains attempts and revisions.
Request timeout or queue delay differs from window focus. The optional LM Studio
`reasoning_effort="none"` is request-scoped; other providers reject it. Default
profile serialization omits the field for compatibility. Requested settings do not
prove server behavior; no model/server starts or downloads automatically.

## Ren'Py native-template integration

### Feasibility and first supported input

Ren'Py provides native dialogue translation blocks and string `old`/`new` tables.
This makes a bounded native-template adapter a practical first step. It does not
make every installed Ren'Py game readable. The following scope is a design decision;
the reader, versioned text rules and staged native export are implemented for the
subset below. Original-folder installation is unsupported; the separate translated-copy
ZIP requires a matching pinned build and a reviewed recipient plan.

Original-source reading now verifies the relevant lexer, parser, label/block,
native-ID and source-order function contracts as bounded syntax trees. The audited
behavior family comes from pinned upstream 8.1.2 and 8.3.6 source comparisons;
version text alone does not enable it. Unknown or altered contracts fail with the
specific missing behavior. The old exact 8.1.2 profile remains available when engine
source is absent, preserving prior projects without enabling new source dialects.
Python 2 source semantics remain unverified. Native templates have their own grammar
gate. The ZIP runtime gate remains exact 8.1.2.23090503 pending separate evidence.

| Input | First Ren'Py milestone |
| --- | --- |
| Loose native `game/tl/<language>/*.rpy` templates | Implemented strict subset; selecting one file reads the complete language folder |
| Existing populated template translations | Shown read-only in history with language/file provenance; never selected, assigned a target language or approved automatically |
| Loose original `.rpy` scripts | Audited symbolic-source behavior family, with the legacy pinned profile retained; reads the complete supported source scope |
| `_ren.py` | Separate verified block-conversion contract, original byte/span mapping and explicit literal keys; Python is never executed |
| `.rpa` archives | Bounded RPA-3.0 primitive indexes and source/compiled pairs; audited source order permits a disjoint basename union; overlapping sources refuse reading |
| `.rpyc` compiled scripts | Detect/report only; no unpickling, engine import, decompilation or execution |
| Python, screen/style code, images, audio, custom text generators | Report exclusions; do not translate arbitrary literals or run code |

An absent template is an actionable limitation, not an empty successful extraction.
Original sources can also supply the bounded behavior-verified subset below.
Do not run Ren'Py's launcher, translation generator or dynamic string-capture mode
against a game to manufacture input. Extensions need their own grammar,
mapping to native translation identifiers and coverage evidence. Do not substitute
string-table fallback for dialogue translation without declaring its changed semantics.

The current parser accepts UTF-8 with an optional BOM, single- or double-quoted
single-line literals, narration or one ASCII symbolic speaker with optional ASCII
character attributes, removals and temporary `@` attributes, exactly four-space
statement indentation, paired original say comments, and `old`/`new` tables. Literal
escapes are `\\`, `\"`, `\'`, `\n`, legacy `\r` and fixed `\u000d`; new output
uses `\u000d` for carriage returns. Dialogue literals collapse raw repeated spaces
before decoding and use escaped spaces to preserve them; `old`/`new` literals use
Python string-literal space rules. These distinct fixed grammars match the pinned
engine. A fixed `nointeract` suffix is supported; source comments and target statements
must have identical structure. Other escapes, triple quotes,
expressions, other suffixes, Python, screen/style code, duplicate keys in one
file and incomplete blocks reject the whole source set. The original bytes and
character spans remain in source snapshots. Native IDs must be unique across files;
conflicting global string candidates reject extraction. Source-location comments
grant no filesystem access. Changed dialogue structure invalidates affected approvals.

Template reader bounds are 128 files, 2 MiB per file, 8 MiB total, 4,096 directory entries,
16 directory levels and 10,000 records per file. The shared worker enforces timeout,
cancellation and 32 MiB IPC limits; the parent reparses bounded current bytes against
the worker result. Previously active missing templates or another active template
language set block activation, preserving existing history instead of resetting it.

### Original-source behavior family

The bundled `renpy-scripts` reader parses original UTF-8 bytes as data. It accepts
single-line narration and ASCII symbolic speakers with character/temporary attributes,
`nointeract`, explicit IDs, local labels,
alternate labels and local/dotted call-from labels. Hidden labels retain their
parser scope without replacing the translator's preceding label. Native dialogue
IDs use the audited canonical say/label/MD5/serial-allocation rules. Explicit literal `_()` calls and
direct menu choices/captions use global string keys; dialogue does not fall back
to string tables. Screens and Python blocks contribute only explicit literal `_()`
keys. Comments, quoted examples and arbitrary literals cannot introduce statements.
Menu say statements before choices retain implicit `nointeract`; say statements
after choices or mixed with captions reject the set because lexical processing
does not prove the engine's reordered serial allocation. Other suffixes, voice/nvl groups,
multiline/backtick/raw literals and unsupported text syntax are excluded with counts.
Custom statement registration refuses the source set. Private-name munging (`__`)
is diagnosed and excluded until its configuration-dependent mapping is verified.
Tabs inside comments are opaque; tabs outside comments/literals refuse reading,
and unsupported text controls are excluded. This is not a general parser or
compiled-script reader.

One complete original-source scope owns one logical source with object sentinel `-1`;
original member bytes, hashes, offsets, native IDs and location occurrences stay in
its snapshot. Selection covers all supported loose/archived sources. Audited
`_ren.py` views retain original line/character spans; the old conversion refuses a
BOM, while the verified newer form handles it. Archives require matching RPC2
source footers, including the `_ren.py` to `.rpyc` basename mapping. No executable
object is opened. Effective source basenames follow the audited loader's order;
overlapping paths or `.rpy`/`_ren.py` basenames fail instead of guessing priority.
Mixed scopes retain per-member container provenance. The legacy source profile
still refuses multiple containers. Compiled-only omissions remain visible.

Original input is staged as a bounded inventory, then read/parsed one member at a
time: 2,048 members, 2 MiB per member, 32 MiB total, 100,000 records, 250,000 text
occurrences and four million aggregate lexical tokens. Per-file line/token limits,
128 source archives, 200,000 aggregate archive entries and 128 MiB compiled-footer
evidence remain bounded. Container hashes check cancellation while reading.
Native identifiers are bounded at 2,000 characters and aggregate review context at
64 MiB. Repeated dialogue uses monotonic per-member serial allocation to avoid
rescanning earlier serials; source ordering and native IDs remain unchanged.
Framed `reader-report-v1` transfer limits each frame to 256 KiB and the operation
to 256 MiB, with explicit depth/node/frame/string budgets and a terminal digest.
Truncation, changed order, duplicate paths and cancellation never return a partial
source set. The parent releases the worker object before independently rebuilding
the current report and comparing its canonical digest. No report is accepted on
the worker's authority alone.

Existing logical source anchors survive new earlier-sorting filenames and new
disjoint containers. Missing prior members/anchors or another input profile cannot
silently retire the source set. These changes require no persistence migration.

The same revisions, pilot/queue, approval, portable format 3 and native exporter serve
both readers. Fixed symbolic-say grammar `renpy-symbolic-say-v2` is recorded separately
from historical parser/identity versions in snapshots, reports and output manifests.
Unchanged plain statements retain IDs, context and approvals; structural changes
invalidate affected approvals. Recipient validation compares attributes and interaction
mode as well as the speaker and protected text. Review caches derived context by
immutable local snapshot, retaining hashes/locations/say attributes rather than
original byte payloads; new snapshots invalidate it. Export authority is never cached.
Export re-probes the complete source selection and fingerprints before
and after staging, preserves exact current approvals and emits fixed native grammar.
Original member paths never choose output filenames or executable behavior.

### Detection, contracts and service routing

Add a built-in engine probe above Unity discovery. Report `engine`, version evidence,
container kind, localization format and uncertainties separately. Ren'Py directory
names/extensions are hints; bounded content inspection establishes a template source.
`auto` detection must report ambiguity and allow an explicit engine selection. Manual
selection chooses inspection only and cannot grant installation. Leave existing Unity
projects and legacy report keys unchanged; version any extended report contract.

Reuse `ReaderContext`, `SourceDescriptor`, `SourceSnapshot`, `ReaderResult` and the
explicit registry. Extend validated metadata for non-Unity records deliberately:
prefer a documented not-applicable sentinel for `source_object` when one logical
source per file suffices. If multiple logical sources share a file, update the
file/object association in `result_from_report` before using them. Never overload a
Unity object ID with a line number or translation hash. Persist engine/profile scope
without reclassifying legacy projects from a directory hint.

Add explicit reader/export/deployment dispatch for Ren'Py. Unknown adapters must
refuse deployment; they must never fall through to `I2DeploymentAdapter`. Unity kit
lookup, loader/process assumptions and I2-specific export metadata must stay out of
the Ren'Py route. UI and CLI call the same services and use stable reason codes,
with English fallback diagnostics and localized presentation.

### Static parser and record identity

Use a bounded tokenizer/parser, not regex replacement across script files. First
support simple generated dialogue blocks with literal speakers/narration and
`translate <language> strings` pairs of quoted literals. Support a tested literal
subset with explicit escape/newline rules; reject unsupported multiline forms,
expressions, dialogue attributes or statement structure until covered by fixtures.
Bound file counts, individual/total bytes, parser nesting, IPC size and elapsed time;
check cancellation and source hashes before/after reads. All paths stay under the
selected root with the existing link/path-escape protections. Keep a source-span
representation and preserve original encoding/BOM, newline style,
comments, indentation and all unselected bytes in the project snapshot.

Generated dialogue templates often keep original text in comments and an empty
translated say statement. Accept only the documented paired-comment form. Require
an unambiguous literal correspondence, statement count and matching speaker shape;
do not mistake an existing target translation for the source. Source-location comments
are display context only, never trusted paths or permission to read another file.
Arbitrary Python, `init`, `translate python`, style blocks, executable expressions,
unknown tags and structurally ambiguous blocks are excluded with reasons. Block
export for an ambiguous source; do not label it a complete result after skipping errors.

Namespace IDs with adapter/parser version, normalized game-relative logical source and
record kind. Dialogue identity uses the native translate identifier plus verified
statement slot; string-table identity uses the exact decoded `old` key including
`{#context}`. Keep source revision hashes separate. Preserve distinct dialogue
contexts even when their visible strings match. Detect duplicate native IDs across
files and conflicting global string mappings across the selected language set.
Repeated identical string keys may share one reviewed mapping with all occurrences
recorded; conflicting translations block export rather than choosing the first.

File relocation or block-ID changes must not silently inherit approvals. Stable IDs
preserve approval only when the source/context and structural mapping remain valid.
Statement insertion, removal or reordering invalidates ambiguous slots; retain old
drafts/revisions as history. Re-extraction commits one complete selected source set
atomically, scoped to the Ren'Py adapter/profile. Missing files and partial reads are
reported before activation. Never merge sources solely by visible source text.

### Ren'Py text protection

Use the explicit versioned Ren'Py format rule `renpy-text-v1` through
every shared call path, including descriptor validation and portable interchange.
Preserve complete interpolation tokens such as `[name]`, indexed expressions and
conversion/format suffixes as opaque data; never evaluate them. Handle nested
brackets, escapes, `[[`/`{{`, text-tag structure/arguments and `{#context}` according
to the supported grammar. Source tokens cannot be changed or invented by the model.

Define a strict allowlist of supported tags with tested pairing/order rules and
explicit treatment of control tags such as pauses, waits and no-wait. Unknown/custom
constructs need diagnostics. Preserve source-authored executable interpolation and
link targets exactly; untrusted translations cannot introduce new bracket expressions,
tags, links, paths or script statements. Literal brackets/braces require explicit
escaping under the format contract, including in manual edits and imports. Keep
Ren'Py string serialization separate from token protection to avoid double escaping.

`renpy-text-v1` is now implemented in generation, review, edits, drafts, approval and
portable ownership. It preserves the exact ordered token sequence, including nested
opaque interpolation with quoted index expressions, `[[`, `{{`, `%%`, line breaks
and `{#context}`. The tag allowlist covers explicitly paired `b`, `i`, `u`, `s`,
`alt`, `noalt`, `color`, `outlinecolor`, `size`, `alpha`, `cps`, `k`, `font`, `a`;
standalone `w`, `p`, `nw`, `fast`, `done`, `image`, `space`, `vspace` have constrained
arguments. Unknown tags, implicit tag closure, dynamic tag arguments and ruby text
are outside this subset. Interpolation/tag nesting is bounded to 32 levels, tokens
to 8,192 characters and text to 1,000,000 characters. Fixtures follow the upstream
8.5.4 documentation, not a claim that a particular engine build has been run.

### Export and separate deployment gate

Stage a fresh tree under the project, with native `.rpy` translation files, a manifest
of source hashes/parser versions/coverage and exact approved revisions. Require an
explicit mapping from project language tags to Ren'Py language directory identifiers;
`tr` and a game's `turkish` identifier are not interchangeable. Ren'Py's default
`None` language is not an ISO source-language code. Never infer English from it.

Serialize only allowlisted translation statements using fixed emitter logic and
quoted string literals. Never copy executable template blocks into generated output.
Keep the byte-preserved source snapshot separate from the installation candidate.
Export to a separately chosen target language namespace; the supplied template
folder is a read-only input and must never be replaced during installation.
Only approved replacements are applied: retain the verified original source for
unapproved dialogue slots and omit unapproved string mappings; do not ship empty
template placeholders or preexisting unreviewed target translations as approved output.
Reparse output, verify token/structure invariants and current source hashes, and
publish atomically into a new directory. A changed source/draft/approval blocks staging.

An additive `game/tl/<language>/` tree is a candidate installation route, not a
compatibility guarantee. Conflicts may exist in loose files or archive contents and
native IDs, not just at the destination path. If a clean target namespace cannot be
verified (including relevant archives), installation remains unknown/unsupported.
Native files also need a usable language-selection path. Verify the game's existing
language menu or another separately designed user-controlled route; do not inject
arbitrary startup Python or force a persistent language silently.

Ren'Py may compile `.rpy` into `.rpyc` and produce runtime files. Before enabling
deployment, establish version-specific sidecar/cache behavior, original-file hash
effects, process detection and rollback/removal semantics on a synthetic Ren'Py
fixture and a selected real build. Define exact owned additions in the plan/receipt.
A same-name generated file is not ownership proof; unknown or modified sidecars are
preserved. Do not delete by extension or broadly exclude caches from inventories.
If the no-original-writes/ownership contract cannot hold, original-root deployment
remains blocked. The separate translated-copy recipient installer uses its own
reviewed plan around the shared native export pipeline. Original-root deployment
would require the shared reviewed-plan service once its gate is proved; do not
reuse Unity loaders or the current Unity shareable ZIP installer for Ren'Py.

The implemented exporter rereads the complete source set through the bounded native
reader and compares local snapshot bytes, source identities and structural revisions.
It requires exact current approvals and rejects native editor drafts. Imported source
descriptors alone cannot establish local export authority.

The caller maps the project's target language to a non-default native identifier
different from the input namespace. Files use fixed generated names under a fresh
project `exports/renpy-<id>/game/tl/<identifier>/` tree. UTF-8/LF output is reparsed;
byte-preserved input snapshots remain separate. Unselected dialogue blocks are omitted;
in selected blocks, unselected slots retain source text. Unapproved string keys are
omitted. Global keys are emitted once with all occurrences recorded; conflicting
approved mappings block even an explicit subset export.

Large output is sharded by complete translation blocks and paired string entries.
The target is 1 MiB/4,000 records per shard; a single intact block may use the
2 MiB/10,000-record file bound. The export is capped at 512 files/64 MiB. Unsharded
outputs keep their names and manifest format 1; sharded outputs use numbered fixed
names and manifest format 2 with a per-source `files` list. Recipient ZIPs accept
both formats, compare protected structure across all payloads, and reject duplicate
native IDs/string keys across files. ZIP manifests are bounded at 32 MiB.

The manifest binds the language mapping, input hashes, exact approvals, parser/text
versions, emitted/fallback/omitted coverage and exclusions. Final source, database,
output and manifest checks precede atomic directory publication. Failed exports retain
only a pending directory; existing exports are never replaced. This does not prove
load order, language activation, fonts or installation support in a game.

### UI and CLI

| Surface | Implemented behavior and remaining limits |
| --- | --- |
| Project | Independent source/target tags; Texts chooses an inspection engine and Export requires an explicit native target identifier |
| Texts / discovery | Desktop engine/template candidates; reports retain input/container evidence and coverage/exclusions with independent capability results |
| Review | File/block/speaker context, source keys and format diagnostics; existing drafts/history/pilot/approval; template text is read-only provenance |
| Export | Separate project JSON, Unity payload/runtime, native Ren'Py and translated-copy ZIP actions; native actions flush drafts and require current approvals |
| Apply to game | Native Ren'Py installation remains unsupported; no Unity fallback or native file plan is offered |
| CLI | Shared scan/probe/extract plus `export-renpy` and `export-renpy-zip` with explicit `--language <identifier>`; old commands/options/report keys remain supported |

Keep advanced engine details out of the ordinary translation flow unless they explain
a choice or blocker. Add all new UI messages to the eight catalogs and update guides
when the feature exists; do not present planned controls as already available.

### Translated-copy installation ZIP

`renpy_package.py` wraps the same authoritative native exporter. For the pinned
8.1.2 build with one root game EXE, it inventories required immutable build files,
checks the target namespace in loose files and archives, freezes current approvals
and revalidates inputs, drafts and staged ZIP bytes before publishing a fresh file.
The ZIP ships approved text, fixed installer/launcher source and its MIT notice;
no game assets, binaries, model, project, save data or absolute sender path is included.
Unapproved source string text is omitted from package evidence.

The bundled `renpy-copy.ps1` creates a new independent recipient copy. Its concrete
plan binds original/output paths, manifest hash and every required build/payload/helper
file. A changed plan hash, existing target, wrong build, running game, link/reparse
path or native grammar/token mismatch refuses installation. Writes use create-new
handles, identity checks, held parent directories and a flushed journal recording
identity before each write. The immutable start marker, reviewed plan and final
receipt are separate new files; incomplete copies remain for recovery. Installation
never starts the game and never alters an existing original-file inventory.

The new-copy scope explicitly omits `game/saves`, `game/cache`, root runtime logs
and PEP 3147 `__pycache__` bytecode, preserving flat source-less `.pyc` modules.
These are omissions from a new copy, not broader exclusions for an existing game
inventory. [PEP 3147](https://peps.python.org/pep-3147/#case-3-pycache-foo-magic-pyc-with-no-source)
defines why orphaned cache entries are not source-less modules.
`Play-Translated.cmd` is a separate explicit user action: it checks the installed
copy, selects `RENPY_LANGUAGE`, redirects saves/logs inside the copy and requests
`PYTHONDONTWRITEBYTECODE`. The observed embedded runtime still created Python caches;
these, the game-local persistent mirror and `.rpyc` generation
stay inside the copy. No startup Python is injected.

`Remove.cmd` has its own reviewed plan and deletes only unchanged receipt-bound copy
files using identity/link/hash checks on the deletion handle. Modified or unknown
runtime files and receipts remain; it reports retained runtime data rather than
claiming a clean directory. This route requires space for a full copy. Original-root
native installation remains unsupported; namespace/style/font and gameplay evidence
must still be scoped to the observed game. A recipient ZIP does not grant approvals
or enable any Unity deployment fallback.

## Ren'Py roadmap

Implementation must also extend source/package privacy checks for Ren'Py inputs,
keeping real scripts/archives/compiled data private while allowing identified synthetic
fixtures. Dependency additions need pinned provenance and matching notices/sources.

R0-R2 implement the initial template-based, export-only increment with synthetic
verification. R4 includes the audited original-source behavior family, `_ren.py`,
large sets and disjoint containers; overlapping load order and compiled-only input
remain planned. R3 has an experimental
translated-copy route; original-folder deployment remains open.
Read-only inspection of the user-selected Invulnerable 1.10 build
found static Ren'Py 8.1.2.23090503 version evidence and an RPA-3.0 archive, with no
loose translation templates. A bounded RPA-3.0 primitive-index interpreter now
reports member counts/types during discovery and reads individual bounded members
as bytes. It never unpickles objects, imports scripts or writes archive-selected
paths. Other archive variants, fragmented members and executable pickle opcodes
are rejected. The separate original-source adapter reads supported members into
the shared review pipeline. These static checks do not execute the engine.
A separately authorized isolated-copy runtime pilot is recorded
in Compatibility; it does not establish original-folder deployment support.

| Gate | Deliverable and acceptance |
| --- | --- |
| R0: engine boundary | Implemented versioned evidence, bounded input classification, CLI/session/desktop inspection selection and unsupported deployment dispatch. Synthetic ambiguous/unknown/mixed-engine cases and legacy Unity regressions verify isolation. |
| R1: template reader and format | Implemented strict native-template subset, bounded/cancellable worker, source-scoped IDs and Ren'Py token rules. Synthetic fixtures cover comments, escapes, duplicates, malformed/unsupported syntax, missing/partial sources, shared pilot/review, portable ownership and approval invalidation. Real-game template extraction remains unverified. |
| R2: shared workflow and export | Implemented shared pilot/queue/review/drafts/history, read-only template provenance and approved staging with language mapping/coverage. Synthetic round trips, syntax injection, token preservation, stale revisions, mid-staging tampering, restored ownership, multi-file conflicts and UI draft flushing are checked; source hashes remain unchanged. No installation is inferred. |
| R3: additive installation | Experimental matching-build translated-copy ZIP uses reviewed create-new plans, recipient build checks, independent saves/logs and ownership-checked removal that preserves runtime data. Windows/Qt synthetic tests and one actual archived-source-to-ZIP preferences-label field test verify the copy route; real-copy removal was not performed. Original-folder deployment and broader gameplay remain deferred. Explicit install/launch actions stay separate. |
| R4: wider Ren'Py input | Implemented audited static source behavior, symbolic attributes, `_ren.py`, bounded large sets, disjoint loose/archive unions and sharded output. Unknown contracts, overlapping containers, multiline dialogue and compiled-only games remain unsupported. Never deserialize executable objects to read scripts. |

R0-R2 define the first export-capable increment. R3 evidence must describe the
actual copy/original installation route. A synthetic template test is not evidence
for a particular commercial game, engine release, font or all scenes. No game input
is needed to implement synthetic infrastructure; missing real-game evidence blocks
only the corresponding compatibility/installation claim.

### Broader Ren'Py support (planned)

The next milestone is reusable support across games and verified engine families,
not another exact-build exception. Keep one extraction/review/export pipeline and
extend bundled readers. Invulnerable remains a regression reference; the inspected
LR2 8.3.6 layout supplies a second, larger and mixed-source compatibility target.
Neither game defines the general grammar. The first syntax increment (symbolic
attributes and `nointeract`), audited source-family inspection, `_ren.py` views,
incremental large-set reading, framed transfer and block-preserving output shards
are implemented. The complete milestone, especially wider runtime families and
overlapping/mod source resolution, remains planned.

Discovery classifies loose and archived `_ren.py` separately; verified conversion
and source/compiled pairing enable only its static supported subset. Ordinary
Python is not a text input. Source package privacy checks exclude `_ren.py` and
include the upstream source-behavior notice. Copy packaging refuses private
repository, AI-tooling or credential metadata instead of silently adding exclusions.

**Compatibility decisions.** Detect engine version as evidence, then classify
container, source dialect and syntax features. Treat template parsing, original-source
reading, native dialogue-ID reconstruction, translation, export and installation as
separate capabilities. A supported template grammar need not inherit an unrelated
original-source version gate. Unknown engine versions must not automatically imply
unreadable literal text; conversely, readable candidates do not establish valid
native IDs or deployable output. Report the specific unsupported feature or missing
evidence. Do not replace the exact-version check with unconditional acceptance.

For genuinely version-dependent operations, establish documented behavior families
from pinned upstream source and synthetic vectors, initially comparing the existing
8.1.2 behavior with 8.3.6. Investigate Ren'Py 7 separately before claiming a 7/8 range.
Record which canonicalization, escapes, label/block grouping, serial allocation and
runtime rules differ, including patches that actually change those contracts.
Use a shared implementation when behavior agrees, and explicit dialect branches
when it differs. Version overrides permit inspection only. Package fingerprints
still bind each recipient ZIP to its author's exact source build; broader reader
compatibility does not make a patch interchangeable between game builds.

**Source coverage.** Extend the data-only parser for common character attributes,
temporary attributes, menu `nointeract`, multiline literals and supported say suffixes
in separately tested increments. Preserve source-authored statement structure and
opaque interpolation; emit only fixed grammar, never model-selected syntax. Verify
native identifiers and block grouping before enabling dialogue export. Do not
substitute global `old`/`new` keys for dialogue that lacks a verified mapping.
Unknown/custom statements and dynamic text require explicit diagnostics and coverage
counts, not arbitrary literal harvesting or an empty successful extraction.

`_ren.py` is classified separately from both `.rpy` and generic Python. Its bounded
reader verifies the static block-conversion contract and preserves original spans.
Importing modules, executing Python, evaluating expressions or deserializing
engine objects remains forbidden. Ordinary `.py` strings and compiled-only `.rpyc`
remain unsupported unless a separate safe, verified reading contract is implemented.
Missing text must remain visible even if another part of a mixed source set is readable.

**Scale and source resolution.** Replace the pilot's aggregate 128-file/8-MiB/10,000-record
constraints with bounded incremental parsing and chunked worker/snapshot transfer.
The original-source implementation now provides this increment with the explicit
bounds above; template-folder and portable interchange bounds remain separate.
Keep per-operation memory, decompression, file, nesting, time and cancellation budgets;
do not merely remove limits or make them unbounded. Stage a complete inventory before
atomic activation. Resolve loose/archive/mod overlaps using verified load-order rules,
with duplicate/conflict detection across the entire effective source set. Multiple
archives or overrides must not silently omit sources or choose guessed precedence.
Native output now preserves complete blocks across bounded shards. The verified
disjoint source union does not establish precedence for overlaps. Large-set
failure/cancellation must preserve the previous active snapshot and all user work.

**Continuity and presentation.** Preserve existing plain-source IDs and revisions when
their semantic mapping is unchanged. Version parser/dialect evidence independently
of stable unit identity where possible. If mapping changes, retain history and
invalidate only affected approvals; use a numbered transactional persistence migration
with a consistent backup if storage changes. Never reset projects to accommodate a
new reader. UI/CLI must distinguish supported, unsupported and unverified capabilities,
show coverage omissions, and keep limits separate from format incompatibility.
Human review, draft flushing and exact approval checks remain mandatory.

**Installation.** Broader reading must not bypass native output validation, clean
namespace checks, explicit language activation or current reviewed file plans.
Extend the separate-copy ZIP by tested runtime behavior families. Include source
dialect/feature evidence in the manifest and verify it at export and recipient time.
Inspect development/mod folders for private repository, tooling and user data before
defining a copy scope; proposed omissions must be explicit in the new-copy plan,
never silently broaden existing inventories. Original-root installation remains
unsupported. Game launch and runtime pilots require applicable explicit user action.

| Order | Acceptance before declaring broader support |
| --- | --- |
| 1. Compatibility model | Feature/dialect decisions replace the blanket build gate with explicit reasons. Existing pinned behavior stays covered; unsupported/unknown versions cannot obtain deployment authority through an override. |
| 2. Reader coverage and scale | Synthetic fixtures cover attributes, menu groups, escapes, multiline text, `_ren.py` classification, large sets, chunk boundaries, collisions and verified overlay order. Unsupported forms are counted; failure never activates partial results. |
| 3. Identity and export | Native-ID vectors match pinned upstream behavior for each claimed family. Re-extraction preserves unchanged work; changed mappings retain history. Sharded output reparses, preserves tokens/blocks and rejects source/draft/approval races. |
| 4. ZIP and runtime | Recipient validators agree with the exporter for each enabled dialect. Synthetic reviewed install/remove checks pass. Separately authorized copy pilots verify language activation, representative dialogue/UI, saves/cache behavior and unchanged originals; evidence is scoped per runtime/build. |
| 5. Regression and delivery | Ruff/mypy/pytest and relevant C# checks pass, legacy Unity/native projects retain state, and UI/help/eight guides plus source/package/privacy audits match actual capabilities. No untested universal support or full-game claim. |

Do not call the broader milestone complete after adding a second version allowlist
or enlarging constants alone. Demonstrate reusable behavior across distinct source
layouts, including a large mixed-source case, and report remaining feature gaps.
Keep real games, extracted text and user projects out of public fixtures and archives.
Implementation and test evidence must update this document, Compatibility and
Installation rather than creating a parallel roadmap or progress diary.

### Deferred engine expansion

After the Ren'Py gates, resume broader Unity methods: explicit JSON/CSV schemas,
another I2 profile, additional TextAsset layouts, Unity Localization String Tables
and bounded AssetBundle/Addressables resolution. JSON/CSV must preserve keys, types,
locale mappings, ordering, non-text fields and encoding under reviewed schemas;
project JSON interchange is not a game-file reader. IL2CPP deployment needs its own
ABI/loader/lifecycle design. Never infer it from Mono extraction.

Unreal is a later feasibility investigation of engine versions, localization
resources, packaging, encryption and additive loading constraints. It is not part
of Ren'Py implementation and has no promised installer. OCR, voices, model training,
automatic downloads, mandatory cloud accounts and arbitrary external plugins remain
outside this plan. Keep engine additions data-driven without executable profiles.

### Official Ren'Py references

The native-template and language-routing assumptions above were checked against
[Ren'Py translation documentation](https://www.renpy.org/doc/html/translation.html).
The protection contract must follow [Ren'Py text syntax](https://www.renpy.org/doc/html/text.html).
[Distribution/archive documentation](https://www.renpy.org/doc/html/build.html#archives)
explains why loose files cannot represent every shipped game. These are current
upstream references, not a verified application compatibility range; pin the exact
upstream version/source used for implementation fixtures.

Symbolic-say canonical vectors reference the pinned
[8.1.2 Say implementation](https://github.com/renpy/renpy/blob/8.1.2.23090503/renpy/ast.py)
and its
[translation ID allocation](https://github.com/renpy/renpy/blob/8.1.2.23090503/renpy/translation/__init__.py).
The audited comparison also includes both tags' lexer, parser and script loader.
`renpy_dialects.py` verifies bounded, non-executable AST fingerprints of the critical
declarations; comments, docstrings and source locations do not change those contracts.
Missing, duplicated or changed declarations refuse the original-source reader.
These are source-reading contracts, not a complete engine or runtime audit.

| Compared behavior | Shared subset or explicit difference |
| --- | --- |
| Say canonicalization and IDs | Supported symbolic shapes share quoting, label/MD5 and serial allocation. The [8.3.6 Say implementation](https://github.com/renpy/renpy/blob/8.3.6.25022803/renpy/ast.py) optionally includes explicit identifiers; canonical ID construction omits that suffix. |
| Translation grouping | Modern `TranslateSay` combination happens after identifier creation; both restructuring contracts are verified. |
| Labels and menus | Label, menu, local/from-label and supported menu-say ordering rules are checked against both parser contracts. Dynamic or ambiguous forms are excluded. |
| Lexer and attributes | The modern lexer reserves extra image keywords. Private-name munging is excluded; logical statements retain bracket and continuation boundaries. |
| `_ren.py` | Both fixed block converters preserve source spans; the newer converter accepts a UTF-8 BOM. Neither executes Python. |

See the pinned [8.1.2 lexer](https://github.com/renpy/renpy/blob/8.1.2.23090503/renpy/lexer.py),
[8.3.6 parser](https://github.com/renpy/renpy/blob/8.3.6.25022803/renpy/parser.py),
[translation restructuring](https://github.com/renpy/renpy/blob/8.3.6.25022803/renpy/translation/__init__.py)
and [script conversion/loading](https://github.com/renpy/renpy/blob/8.3.6.25022803/renpy/script.py).
Ren'Py 7/Python 2 text semantics, unknown contracts and wider runtime behavior remain
unverified. Preserve the bundled upstream license/provenance notice.

## Setup and validation

```powershell
uv sync --locked --extra ui
uv run --locked --extra ui unitytranslator gui
uv run --locked --extra ui python tools/check.py
uv run --locked --extra ui python tools/check.py --with-dotnet
uv run python tools/check_documentation.py
uv build
uv run python tools/check_distribution.py
```

Use targeted synthetic fixtures first, then Ruff/mypy/pytest and relevant C# checks
for shared changes. C# projects require their compatible .NET SDK. `tools/check.py`
allocates a new `.cache/` test directory; never use a running application's directory
as pytest `--basetemp`. Do not repeat broad tests without new changes/failures.
CI uses no real games, user projects or models. Clean Windows, physical llama.cpp,
language rendering and gameplay need their own evidence; existing results are in
[Compatibility](compatibility.md). This documentation reorganization is not a new
runtime validation or release.

## Localization, packaging and repository layout

Use English developer identifiers, CLI help, contracts, comments and public docs.
Keep native-language guides and UTF-8 catalogs. `tr(...)` labels preserve `{p1}`/Qt
tokens. Never translate game strings, IDs, model names, paths or persisted confirmation
values as interface labels. Legacy diagnostics require compatibility tests before
rewriting. The default interface language is English; changes apply on restart.
Project languages are independent. Tests may set `UNITYTRANSLATOR_UI_LANGUAGE` and
`UNITYTRANSLATOR_CONFIG_HOME` to isolate locale/preferences.

Source help uses `guide/`; wheels bundle `resources/guides/`; new Windows packages
ship `guide/`. Preserve all eight guides. Package/CLI/module names stay `unitytranslator`
until a separate compatible rebranding plan is approved. Keep docs in `docs/`, runtime
source/notices in `adapters/`, and local AI notes/build/game/user data out of public
archives. Local GOAL/AGENTS are short navigation/rules, not duplicate designs.

In the source tree, `docs/README.md` is the documentation index. Design/roadmap/review rules live
here, observed support/release evidence in [Compatibility](compatibility.md), normal
and shareable installation in [Installation](installation.md), Unity runtime internals
in [Runtime components](runtime-components.md), and build steps in
[Windows packaging](windows-package.md). Do not add separate milestone/session diaries.
Legal notices and component provenance remain separate because distribution needs them.

When moving documents, update `tools/package_notices.py` and component-source lists
such as `tools/build_krypta_kit.py` and `tools/package_portable_kit.py`. Check links and guide resolution, build wheel/sdist
in a new output directory, audit privacy and inspect a source ZIP. Never modify
published artifacts or relabel old executables. Preserve matching licenses and source
archives. `.gitignore` does not untrack files; review the index before committing.
No documentation/build task implies commit, push, tag, publication or game install.
