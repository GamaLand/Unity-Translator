# Development

Updated: 14 November 2026. This is the single architecture, implementation plan and
roadmap reference. [Compatibility](compatibility.md) records actual support;
requirements marked **planned** do not enable a capability.

## Current architecture

The checkout is UnityTranslator 0.7.0. Python 3.12 owns project state, translation,
validation and deployment. PySide6 Widgets calls `ApplicationSession` through the
Qt bridge. An independent asyncio thread owns SQLite and job state; model HTTP
requests do not hold transactions open. Minimizing the window does not pause work.
Unity parsing uses bounded worker processes. Crash isolation is not an OS sandbox.
Extraction never executes game assemblies.

| Location under `src/unitytranslator/` | Responsibility |
| --- | --- |
| `application.py`, `commands.py`, `__main__.py` | Shared session, declarative command registry with typed payloads and guards, and CLI entry point |
| `domain.py`, `repository.py`, `resources/schema-v*.sql` | Records, revisions, source ownership and migrations |
| `jobs.py`, `providers.py`, `policy.py`, `validation.py` | Durable queue, local HTTP, glossary/style and format checks |
| `dialogue_context.py` | Verified source segments, bounded reference windows and frozen job evidence |
| `discovery.py`, `profiles.py`, `i2*.py`, `managed_schema.py` | Current Unity discovery and I2 reading |
| `source_contracts.py`, `reader_adapters.py`, `capabilities.py` | Bundled readers, snapshots and independent capability reports |
| `engines.py`, `renpy_dialects.py` | Bounded engine/input evidence and audited static source behavior; no engine execution |
| `renpy_templates.py`, `renpy_scripts.py`, `renpy_python.py`, `renpy_say.py`, `renpy_archive.py`, `renpy_format.py`, `renpy_export.py`, `workers/renpy*_probe.py` | Static templates, original scripts and `_ren.py` views, fixed say structure, RPA indexes, text protection and approved staging |
| `krypta_profile.py`, `journal_grid.py`, `textasset_layouts.py`, `textasset_export.py` | Pinned Krypta sources, literal grid and staged payload export |
| `worker_process.py`, `report_stream.py`, `workers/` | Bounded JSON/framed reader IPC, timeout and cancellation |
| `deployment.py`, `installation.py`, `runtime_*.py`, `krypta_runtime.py`, `krypta_trial.py`, `shareable.py` | Reviewed additive deployment and runtime/package variants |
| `editor_drafts.py`, `review_selection.py`, `translation_memory.py`, `portable.py`, `reports.py` | Review, explicit translation memory reuse, history interchange, drafts and reporting |
| `diagnostics.py` | English reason-code diagnostics, bridge failures and legacy message aliases |
| `ui/`, `ui/pages/`, `resources/locales/` | Qt presentation, per-page completion controllers and eight offline interface catalogs |

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
`protected-i2-v4`, `literal-lines-v1`, `renpy-text-v1` and `renpy-text-v2` explicitly.
`result_from_report` still associates records using file/object pairs. Native Ren'Py
staging requires a separate explicit language mapping and current approvals;
a reader or exporter does not grant deployment.

### Persistence and identity

Schema 8 adds `local_reviews`, optional local reviewer codes bound to one translation
revision and reviewer; it changes no existing row. Schema 7 adds lookup indexes only:
revisions by unit and by source revision, plus a review-order index on original key
without a leading `active` column so full-table counts keep their scan. It changes no
stored record, identity or history. Migrations
come from one ordered table bounded by `LATEST_SCHEMA`; each step keeps its backup.
Schema 6 adds frozen source bindings for optional dialogue-context jobs; schema 5
records logical sources and immutable snapshot descriptors. Schema-4 inputs,
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

I2 uses `protected-i2-v4`; TextAsset uses `literal-lines-v1`; Ren'Py sources use
`renpy-text-v1` or, for new projects, `renpy-text-v2`. I2 recognizes its tested
parameter/rich-text grammar and plural branches; these rules do not apply to Ren'Py.
Current multilingual review checks are `review-multilingual-v6`. The implementation
and fixtures define the authoritative grammar. Preserve line endings and exact
protected tokens. Unknown syntax is diagnosed rather than silently rewritten.
I2 plural branches retain their source structure/order and require human review;
this does not convert target-language plural rules.

Every language pair receives applicable format, unchanged-text, number, percentage
and glossary checks with language-aware case handling, and length ratios by category.
English to Turkish, German, French, Spanish, Portuguese, Russian and Chinese has
conservative negation/condition hints; German, French, Spanish, Portuguese and
Russian to English has strict negation hints. Automatic checks cannot prove meaning, tone, font
coverage, shaping or layout. Equal source text does not force equal translations.

A reviewed pilot enables bulk generation for matching sources and model/generation
settings; glossary/style versions are excluded from this gate. All queue modes use
the project's current saved glossary and style at the start of each attempt,
including retries and resumed jobs. Saving both policies is atomic. In-flight
requests finish with their captured versions; later requests use the new versions
without another pilot. Attempt profiles and translation revision metadata record
the exact versions used. Original job profiles and policy versions remain immutable.
Policy changes mark affected records for review; existing translations, drafts and
approvals are preserved and regeneration remains an explicit action.
An interrupted pilot can also be reviewed after cancellation if the complete required
sample was attempted, at least one result completed, and no requests remain active.
Its cancelled status, failed/unfinished records, revisions and individual approvals
remain unchanged. Too-small/unattempted samples and changed sources cannot unlock
bulk generation. Pilot reports expose this backend eligibility, show outstanding
counts and offer refresh so an earlier running snapshot does not hide the current state.
Bulk readiness distinguishes changed sources, changed profile fields and missing review.
The user may explicitly select the model/generation settings of a reviewed pilot
for current sources. This keeps current saved glossary/style selections, policy
versions, impacts, translations and approvals. Selection requires a current project,
explicit confirmation and no active extraction/job. It neither grants a new pilot
review nor authorizes changed model/generation settings against an older pilot.
Reasoning-option changes refresh readiness.
It approves no individual translation. Approval binds exact source/translation
revisions. Generation and imports never replace current approvals automatically.
Changed source text invalidates approval. Editor drafts have optimistic versions;
unfinished drafts block affected export/installation selections. Page approval uses
eligible reviewed records; whole-project approval retains its two confirmations and
atomic preview revalidation. Legacy confirmation payloads are protocol data.

Review pages can explicitly regenerate up to 200 visible filtered records through
the existing bulk queue and matching reviewed-pilot gate. Drafts and processing
records are excluded in the desktop; the backend atomically rechecks project,
source/translation revisions, work versions and drafts before creating the job.
New jobs retain earlier attempts and translations in history; approved records
receive candidate-only revisions. No filter-wide expansion or inventory reset occurs.

Review also has a compact Bulk actions menu with two explicit operations across
all pages matching the current search/status/category/policy-impact filters: approve
nonempty translations exactly equal to the source, or return empty translations to
Pending. A count, exclusions and bounded examples precede confirmation. Identical
text is never approved automatically; the dialog states that untranslated sentences
also match. Drafts, processing/queued records, existing approvals and invalid or
stale translation mappings are excluded. Returning empty records changes only their
work state/current empty pointer and increments the work version; revisions, drafts,
policy impacts and job history remain. It sends no model requests. A later bulk job
uses the existing reviewed-pilot gate. Project-bound single-use previews are fully
revalidated in one transaction, including policy versions, before either operation.
Existing page and whole-project approval flows retain their confirmation contracts.
For returning empty records only, queued entries in paused jobs do not block the
operation. The preview reports their affected record count and freezes their queue
identities. Resetting increments the work version, so the existing claim guard skips
those stale entries if the old jobs resume. Jobs and attempt history are not reset.
Other queue entries still block the action. Empty selections distinguish no matches
from matching records excluded by status, draft, approval or queue protections.

Jobs allow 1-36 concurrent requests, with a default of one. The UI and backend share
the same bound; concurrency is an execution setting and does not alter the reviewed
generation profile. Existing jobs retain their saved model/generation settings. Desktop
start/resume checks the selected provider, normalized endpoint and model against
that saved profile before claiming records or sending HTTP requests; a mismatch
requires restoring the job's settings or preparing a new pilot. Legacy session
callers without a model selection retain the saved-profile behavior.
Pause stops new claims and saves in-flight
results; cancellation closes client tasks. Recovery retains attempts and revisions.
Only the explicit Cancel action cancels a job. Closing the app, switching projects or a
cooperative shutdown pauses it, keeping an earlier automatic reason or else recording
`shutdown`, requeues claimed records and returns the attempt of a request that was cut
off; reopening never resumes it. HTTP 429 and 5xx replies without a specific reason are
`server_unavailable`. That code and `connection` keep their run history but refund the
record's three-attempt budget. A record whose own latest five runs are outages, counted
across resumes, is failed and left Pending for a later job; an outage on the only
remaining record therefore fails it rather than pausing. Otherwise the job pauses when
consecutive outages across all workers reach four plus the number of parallel requests
and span more than one record; a success or any other error resets that count. Records
in a current outage are claimed last without sorting the queue. Timeouts still spend
attempts. Retries wait with jittered exponential backoff while keeping their claim, so
no other worker retries at once. Run numbers, reported retries and pilot sample coverage
follow run history rather than the refundable budget; job reports count outage attempts
separately and leave them out of request timings. A pending pause keeps its first reason
and an active run stays `pausing` until its workers finish.
Request timeout or queue delay differs from window focus. The profile's
`reasoning_effort` is `default` (server behaviour), `none` or `adaptive`. `none` sends
`reasoning_effort="none"`, and for llama.cpp also `chat_template_kwargs.enable_thinking=false`,
because templates such as Gemma's enable thinking for any system prompt. `adaptive`
(llama.cpp only, policy `adaptive-v1`) sends a per-record `thinking_budget_tokens` of 64
plus the source length, half the length of included dialogue references and 64 per
reference, capped at 1,024. Dialogue references are fitted first; the budget is then
reduced to the remaining safe context instead of dropping references or failing, and the
reduction is recorded. The budget is added to `max_tokens` and to the safe context
estimate, so thinking cannot consume the answer's output budget. Results and job reports
record the mode, budget and the size of separately returned reasoning, never its text;
report metrics include failed attempts such as `output_truncated`.
Unsupported combinations are refused before any request. Default profile serialization
omits the field for compatibility, and a changed mode needs a matching reviewed pilot. Requested settings do not
prove server behavior; no model/server starts or downloads automatically.
The synthetic connection test uses the selected context, output and temperature
settings. llama.cpp model discovery reads the running per-slot `meta.n_ctx`, never
the model's training context. Client context settings do not resize server slots;
server context and parallel-slot configuration must provide the requested budget.

### Source order and neighbouring dialogue context

Version 0.6.0 adds the optional `source-window-v1` generation setting. It is off by
default, and absent from legacy profile JSON. All engines still use one queue,
provider, validation and review pipeline. Enable **Use verified neighbouring
dialogue** in advanced model settings to order review pages/new jobs by evidenced
source segments and provide at most two preceding/two following source utterances.
Pilots remain representative category/length samples; only their execution order
changes. Independent requests may finish out of order.

Pilot selection reads the eligible category/length-ordered inventory once, retaining
the earlier deterministic sampling and exclusions. It does not repeat the full sort
for every sampled offset. Cold context reconstruction finishes before the short
atomic queue transaction. Preparation reports its sample/context stages before any
HTTP request, prevents duplicate starts and supports immediate UI cancellation.
The Qt bridge sets thread-safe cancellation/shutdown events before queuing backend
commands; bounded Python checks and a preparation-only SQLite progress handler let
the busy backend stop, roll back an unfinished queue and close safely. SQLite stays
on its owning thread. A cancelled reconstruction cannot become a cached unknown-order
fallback. Closing never starts a late prepared job, and cancellation of a new
preparation cannot cancel the previously selected job. Resumed cold-context jobs
settle cancellation through the existing queue; source/review history is preserved.

**Evidence boundary.** `dialogue_context.py` reconstructs accepted Ren'Py records
from complete local snapshot bytes and compares their identities/text/block/slots.
Original-source neighbours must be consecutive accepted say statements at the same
indentation in the same member. Every other logical statement is a barrier:
labels, conditions, menu headers/choices, jumps, calls, returns, loops, Python,
presentation commands, unknown syntax and excluded/empty dialogue. Indent changes
and `_ren.py` conversion markers also cut segments. Blank lines and comments do not.
This deliberately supplies local source context, never a claimed playthrough or
guessed cross-file control-flow graph. Template-only input proves adjacency only
between slots in the same native translation block; location comments cannot link
blocks or authorize reads. Global string keys retain multiple-occurrence semantics
and receive no arbitrarily chosen dialogue window.

Unity/I2 term keys, categories, asset/table order and TextAsset line positions do
not establish a conversation. These currently retain isolated translation, as do
missing, imported-only or incompatible snapshot mappings. A future bundled reader
must separately prove conversation/subtitle relationships before enabling windows.
No executable game inspection or per-game ordering heuristic is introduced.

**Request and state contracts.** References contain source text, speaker and relative
position as reference-only JSON data. They never become additional output targets,
translations, drafts or instructions. Existing exact-ID, token, format and fixed
native-output checks apply unchanged. Each window has a four-utterance/8-KiB cap;
the provider removes whole, farthest references deterministically until the existing
conservative message/schema/output budget fits. If none fit, the original isolated
prompt is used; target text and output allowance are never shortened. Review shows
the candidate window and warns that request budgeting may reduce it. Attempt and
translation metadata record policy version, frozen snapshot, reference identities,
actual request digest, reference count and budget omissions. Pilot reports include
reference/fallback/budget metrics alongside format failures, retries and latency.

Schema 6 transactionally adds `job_context_sources` after a consistent schema-5
backup. Jobs freeze local source bindings; retries/resume/concurrency use the same
source-only evidence, independent of previous translation completion. Changed
neighbourhoods prevent resumed jobs and in-flight acceptance; a matching new pilot
is required for bulk work. Identical re-extraction retains the context fingerprint.
Context policy/evidence participate in pilot identity; request digests distinguish
effective windows. Derived indexes and review order are connection-local caches,
not source revisions. Stable IDs, historical context, drafts, translations,
approvals, old job profiles, portable formats and installation receipts are not
rewritten. Context changes never regenerate or approve existing work automatically.

**Evaluation and expansion gate.** Run `tests/test_dialogue_context.py` first, then
shared Ruff/mypy/pytest, relevant C# checks and package/help audits. Fixtures cover
branch/menu/loop separation, flow and excluded-syntax barriers, comments, file and
conversion boundaries, template slots, repeated keys, source-order pagination and
filtered reference independence, injection, budgets, snapshot changes, identical
re-extraction, concurrent completion, retry/reopen, portable fallback and backed-up
legacy migration. Review an isolated-versus-context pilot on synthetic ambiguity,
pronouns, speaker voice and terminology before claiming naturalness improvements;
compare schema/token failures, retries, truncation and latency as well as human
judgment. Synthetic transport checks prove routing and invariants, not model quality.
Keep isolated mode available and do not enable uncertain source capabilities.

The scope follows official [Ren'Py translation units](https://www.renpy.org/doc/html/translation.html#translation-units),
[control flow](https://www.renpy.org/doc/html/label.html) and the
[I2 language-source model](https://www.inter-illusion.com/assets/I2LocalizationManual/LanguageSources.html).
This feature adds no extraction, runtime or installation capability.

## Ren'Py native-template integration

### Feasibility and first supported input

Ren'Py provides native dialogue translation blocks and string `old`/`new` tables.
This makes a bounded native-template adapter a practical first step. It does not
make every installed Ren'Py game readable. The following scope is a design decision;
the reader, versioned text rules and staged native export are implemented for the
subset below. The default recipient ZIP adds text and helpers to the original folder
without copying or overwriting existing files; it requires a matching pinned build
and a reviewed create-new plan. Legacy translated-copy packages remain supported.

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
The script worker returns only a strict `reader-digest-v1` result of at most 64 KiB:
its report's canonical digest and record, source, member and exclusion counts. The
parent independently rebuilds the current report and compares digest and counts; a
mismatch names both record counts. Truncation, changed order, duplicate paths and
cancellation never return a partial source set, and no report is accepted on the
worker's authority alone. Framed `reader-report-v1` transfer (256 KiB frames, 256 MiB
per operation, depth/node/frame/string budgets and a terminal digest) remains
available for report-transferring workers; no bundled reader uses it now.
Parsed RPA indexes are cached in memory per archive path, device, file ID, size and
modification time, for up to one complete probe (128 archives and 200,000 members).
A cache hit and every member read check the path policy, compare the open handle's
device, file ID and size and re-hash the header and index region, which is
equivalent to re-parsing the index; file IDs alone are not trusted, and a
modification-time change alone keeps a verified index. A changed index is parsed
again. Concurrent in-place rewrites of member data are caught by the probe's
whole-container hashes before and after reading, not by member reads.

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

`renpy-text-v2` is a descriptor rule: dialogue records keep `renpy-text-v1`, and
string-key records (`original_key` beginning `string/`) also protect Python printf
conversions such as `%d`, `%(name)s` and `%.2f`, because game code may apply `%` to
them. The space flag is excluded so prose such as `100% done` stays text, mapping keys
must be identifiers, and `str.format` braces remain unsupported Ren'Py tags. v1 tokens
and printf conversions each keep their own order, so `%%` may move around a conversion
(Turkish `%50`). In a format template a bare `%` may not be added or removed. Known false positive: `50%off`
contains the conversion `%o`. Every v2 acceptance is also a v1 acceptance. New projects
start with v2. Existing projects keep their persisted rule; only an explicit
re-extraction with `--format-rules renpy-text-v2` (or the session's `format_rules`)
upgrades every Ren'Py descriptor, refuses while any job is unfinished, invalidates only
string translations, retired ones included, that fail the new rule, records a
`format_rules_upgrade`
snapshot. Downgrades are refused. Newer rules join the pilot identity, so an upgrade
needs a new reviewed pilot; v1 projects keep their existing pilots. Approval rechecks
the current rule. Native export records the rule; v2 recipient packages declare
`format_rules`, and the recipient refuses unknown values and enforces printf tokens in
string blocks. Shared vectors in `tests/fixtures/renpy-format-v1.json` and
`renpy-format-v2.json` run against the Python validator and the recipient tokenizer.
The recipient deliberately stays stricter for ruby brackets anywhere and for UTF-16
length limits on astral characters; these pinned cases fail closed at review time.

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
The additive installer guarantees no original-file overwrite during installation
or removal. User-launched gameplay can update normal saves, caches and bytecode;
there is no promise of a write-free game session or rollback of gameplay data.
The recipient's reviewed-plan/identity service surrounds the shared native exporter;
it does not reuse Unity loaders. If unowned compiled translation sidecars exist,
removal stops before deleting any patch files, since orphaned `.rpyc` files could
keep translations active. Users must separately review those exact sidecars.

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

#### Desktop design foundation

The desktop is a local translation workbench: source preparation, candidate
generation, human review and approved delivery are separate activities. Navigation
must expose that sequence without implying that generation approves a translation
or that extraction establishes installation support. Existing session commands,
draft flushing, pilot gates and explicit confirmation dialogs remain authoritative.

Version 0.7.0 uses a persistent grouped workflow sidebar, a compact
project summary and a page heading with one next-step shortcut. Reusable shell,
section, disclosure, action-menu and editor components live under `ui/`; presentation
components own no project state or backend policy. Secondary tools use labelled
menus and expandable sections, not a wall of equally prominent buttons. Menus
must track the enabled state of the underlying action. Review prioritizes a
resizable record list and labelled source/translation editors, with reference and
check details in an alternate inspector tab. Check notices remain visible below
the workspace; the inspector and tooltips retain their complete plain text.
The supported minimum window is 900 × 740; narrow tables prioritize source and
translation, retaining the full selected key and category filter. Saving, approval
and draft status remain distinct. Whole-project operations retain their preview and confirmation flows.

Use a restrained warm charcoal palette, off-white text and a muted sage accent;
no gradients. Semantic warning/error colors supplement explicit text. Shared
spacing, borders, focus indicators and typography belong to one theme module.
Long action labels wrap and forms scroll vertically when space is limited;
review panes resize without hiding primary
actions. Keyboard navigation, eight offline catalogs, plain-text rendering of
untrusted content and existing UI-language/project-language separation are required.
Validate synthetic populated and empty screens, long localized labels, smaller
windows, draft/history/approval workflows and a fresh standalone Windows package.

| Surface | Implemented behavior and remaining limits |
| --- | --- |
| Project | Independent source/target tags; Texts chooses an inspection engine and Export requires an explicit native target identifier |
| Texts / discovery | Desktop engine/template candidates; reports retain input/container evidence and coverage/exclusions with independent capability results |
| Review | File/block/speaker context, source keys and format diagnostics; existing drafts/history/pilot/approval; template text is read-only provenance |
| Export | Project JSON, Unity payload/runtime, native Ren'Py and additive ZIP actions; native actions flush drafts and require current approvals |
| Apply to game | Desktop session installation remains Unity-only; Ren'Py uses the ZIP's own reviewed recipient plan, with no Unity fallback |
| CLI | Shared scan/probe/extract plus `export-renpy` and `export-renpy-zip` with explicit `--language <identifier>`; old commands/options/report keys remain supported |

Keep advanced engine details out of the ordinary translation flow unless they explain
a choice or blocker. Add all new UI messages to the eight catalogs and update guides
when the feature exists; do not present planned controls as already available.

### Native installation ZIP

`renpy_package.py` wraps the same authoritative native exporter. For the pinned
8.1.2 build with one root game EXE, it inventories required immutable build files,
checks the target namespace in loose files and archives, freezes current approvals
and revalidates inputs, drafts and staged ZIP bytes before publishing a fresh file.
The ZIP ships approved text, fixed installer/launcher source and its MIT notice;
no game assets, binaries, model, project, save data or absolute sender path is included.
Unapproved source string text is omitted from package evidence.

New UI/CLI exports call `export_install_package`. Format 3 declares
`unitytranslator-renpy-additive`; the fixed `renpy-copy.ps1` dispatches only to the
hash-checked bundled `renpy-additive.ps1`, sharing its path/identity/native-grammar
checks. The recipient selects the original game once. A concrete plan lists only
native payloads, `Play-Translated.cmd` and per-package records under
`.unitytranslator/renpy-additive/<id>`. No game assets are copied and no existing
file is backed up or replaced: collisions refuse installation. Root/directory
identity, source hashes, script/archive membership, payload grammar, approval
snapshots and the reviewed plan are rechecked. Create-new handles, held parent
directories and a flushed identity journal protect additions. Incomplete installs
retain their markers; they cannot be adopted as completed installs.

Build verification explicitly omits ordinary saves, caches, logs, receipt metadata
and paired Python bytecode; source `.py` files and source-less `.pyc` modules stay
verified. These are the new package's verification scope, not changes to an existing
original-file inventory. `Play-Translated.cmd` selects `RENPY_LANGUAGE` only when
explicitly invoked, using normal saves without startup Python injection. Gameplay
may update runtime files as usual; the installer never starts the game.

Removal validates the receipt, directory identities and immutable start/plan proof.
Only unchanged receipt-owned text and the launcher are removed, with identity,
single-link and hash checks on the deletion handle. Unknown compiled translation
sidecars block removal before any deletion. Modified/linked additions are preserved
with a partial-removal report; saves and runtime caches are never restored or
deleted. An empty owned language directory may be removed by identity on its handle;
unknown contents prevent that removal. Small audit/support records remain. A new
package can be exported after the old namespace/launcher have been removed.

Formats 1/2 and `export_copy_package` retain the legacy independent-copy route,
including its separate saves/logs and ownership-checked removal. Existing ZIPs are
not rewritten or reinterpreted as additive installations. Native export remains
formats 1/2; the format-3 ZIP records that version in `native_format_version`.
Synthetic Windows tests cover the additive route; actual original-root gameplay
and generated-sidecar cleanup remain unverified. Copy pilot evidence does not prove
those behaviors or broader engine compatibility.

## Development roadmap

Observations below come from a 0.7.0 source review and synthetic 100,000-record
measurements; recheck each before implementing it. Everything in this section is
**planned** unless an item says it is implemented in source. It grants no capability
and changes no compatibility claim.

Phase F comes first. Phase C, contract-based coverage, is next: its Ren'Py items
run inside the [broader Ren'Py support](#broader-renpy-support-planned) gates, and
its Unity items then resume [deferred engine expansion](#deferred-engine-expansion).
Phase M and T items may land in slices alongside that coverage work.
Phase D follows the Ren'Py milestone and may proceed alongside the Unity items
of Phase C. Items inside a phase are independent unless
noted. Every item ships with targeted synthetic tests, the shared checks and updates
to this document, Compatibility or Installation. Identities, approvals, drafts,
receipts, legacy payloads, persisted confirmation values and historical metadata are
preserved. Storage changes use the next numbered transactional migration with a
consistent backup; new metadata reads as absent on legacy rows.

### Phase F: foundation

Scale and reliability defects affect every engine and the large Ren'Py sets targeted
by the coverage milestone.

| Item | Observed in 0.7.0 | Planned change and acceptance |
| --- | --- | --- |
| F1 Schema 7 and set-based queries | Only four explicit secondary indexes exist besides key autoindexes; none covers `source_revisions.unit_id` or `translation_revisions.source_revision`. Portable history export issues two scanning queries per unit, about 0.2 s per unit at 100,000 units, and every review page sorts the full inventory. | **Implemented in source.** An additive schema 7 adds those indexes and a review-order index. Portable history export reads two ordered sets with unchanged output, and candidate-only job results are found by their content-addressed revision ID. One migration table and `LATEST_SCHEMA` replace the repeated version tuples. A synthetic 100,000-record test with generous budgets covers ingest, paging, search, history, export and whole-project approval, and reopened schema-6 projects keep all work. Selective search and impact pages and whole-project reads keep their schema-6 scan-and-sort plans, because walking the review-order index for few matches is slower. In repeated synthetic runs, history export fell from a projected several hours to under 2 s and unfiltered early review pages from about 0.4 s to 0.01 s; index maintenance made first ingest about 15-40% and candidate writes about 10-20% slower. Deep pages still pay `OFFSET`. |
| F2 Job resilience | HTTP 429 and 5xx replies whose body matches no specific reason (including 503 while a model loads) fall through to `http_error`, which fails the item permanently and neither retries nor pauses the job. Items are requeued before the backoff sleep, so parallel workers can spend all attempts at once. Closing the app cancels a running job. | **Implemented in source.** Unmatched 429/5xx replies become retryable `server_unavailable`. Outage failures keep history and refund the attempt budget. A record whose own latest five runs are outages, counted across resumes, is failed and left Pending; otherwise consecutive outages spanning more than one record pause the job once they reach four plus the parallel request count, so one concurrent loading wave does not pause it. Records in an outage are claimed last without a queue sort, and retries hold their claim during jittered backoff. Closing or switching projects pauses a running job, keeps an earlier automatic reason, never starts a late prepared job and never cancels a previously selected job; reopening never resumes automatically, and resume keeps the saved-profile and source-context checks. Jobs cancelled by earlier versions stay cancelled. Timeouts still spend attempts. Fake-provider tests cover model loading, rate limits, outage/recovery, a single failing record at one and two parallel requests, a concurrent loading wave, interleaved outages, bounded resumes, claim order and plan, backoff claims, pause reasons, report counts and shutdown. |
| F3 Text-safety gaps | `renpy-text-v1` treats `%%` as its only percent token, so `%s` and `%(name)s` in `_()` string keys are unprotected. `extend` dialogue is skipped without a count. Excluded say statements reserve no native serial, so a later identical statement can receive the wrong native ID. Editing an inactive unit can clear its approval without a version bump. | **Implemented in source.** A `renpy-text-v2` descriptor rule protects printf conversions in string keys only; `str.format` braces stay unsupported tags. New projects use it; existing projects upgrade only through explicit re-extraction, which invalidates only failing string approvals, records the change and needs a new pilot. Descriptor validation, portable format 3, the native exporter and the recipient accept it explicitly. `extend` is counted as `extend_say` and reserves its native serial when its code is computable; other excluded say statements that may share a later statement's base refuse reading with a reason, keeping the previous snapshot; statements in a voice/nvl group are not suspects, because the engine hashes the whole group's code. The rule is recorded as `native_id_allocation` in new snapshot metadata without changing the parser version or dialogue-context evidence. Truncated-digest collisions between non-computable codes remain for C2. Inactive-unit edits are rejected before any state change. Shared v1/v2 vector fixtures run against Python and the recipient, whose multi-name tag acceptance was fixed. |
| F4 Worker boundary | The I2 worker uses `subprocess.run`, post-hoc size checks, plain `json.loads` and no cancellation. The Ren'Py script worker transfers its full report only for hashing. Every RPA member read re-parses the whole index to detect archive changes. | **Implemented in source.** The I2 reader uses `run_json_worker` with strict JSON, the extraction's cancellation, the shared timeout and the 32 MiB IPC limit, and accepts only the Unity worker's own report fields with their types: units need exactly the record fields, 64-bit source objects and string texts. Strict JSON at every worker boundary reports excessive nesting as a value error. Worker failures report the worker's bounded fatal record and the last stderr line, at most 300 printable characters each, with control, format and lone surrogate characters removed; a fatal record after other output lines is still found, and the Unity and TextAsset workers' fatal records now carry a message of at most 1,024 characters. The Ren'Py script worker returns a strict `reader-digest-v1` digest-and-counts result instead of its full report; parent re-verification is unchanged. Parsed RPA indexes are cached per verified archive identity for a whole probe, and each member read checks the path policy, the open handle's identity and size, and the index-region hash. In a synthetic 15,000-member archive, reading every member took about 15 s instead of a projected 36 minutes of per-read index parsing; the per-read path policy check is most of that remaining time. |

### Phase M: maintainability

| Item | Observed in 0.7.0 | Planned change and acceptance |
| --- | --- | --- |
| M1 Structured diagnostics | About 350 backend exception messages are Turkish literals; only a few match catalog entries, so other interface languages show Turkish errors. The bridge sends only `str(exc)`. | **Implemented in source.** All 339 Turkish exception messages, and the installation status and discovery uncertainty texts, are English; parameterized and formerly concatenated messages are `Diagnostic` templates, and `PolicyError`, `ProviderError`, `OperationCancelled` and `GameNotClosedError` are diagnostics. Every exception message is now a reason code catalogued in all eight languages: 841 new catalog keys. Turkish keeps the previous wording where one existed. The first 387 other-language translations were produced and independently reviewed by assistant agents; the remaining 450 keys in all seven languages were translated through the app's own llama.cpp request path with the adaptive reasoning budget (T5) and a user-run local model, checked automatically for placeholders and technical names, and corrected by hand where review found meaning errors. These local-model translations have no full human review. Failures cross the bridge with code, parameters, request token and project ID and are localized by code; stored plain English text with parameters is recognized by bounded template matching. A legacy table of 386 aliases keeps messages stored by earlier versions localizable, with tests that every alias matches its old text and localizes in every language. AST tests reject non-English source text outside documented exemptions, dynamic or uncatalogued exception messages and hidden template parameters. Persisted confirmation values, generated Turkish pilot reports and their issue labels are unchanged. |
| M2 Session and UI structure | `ApplicationSession.dispatch` is one chain of about 50 string commands with repeated guards. `MainWindow.completed` (about 720 lines) handles every page, and `ui.*` is excluded from mypy. | **Implemented in source.** `commands.py` declares each of the 50 unchanged command names with a typed payload (`TypedDict`) and a declarative guard: open project, payload project identity and idle scope (extraction, job or either), checked in that order with the previous messages. Handlers are `command_*` session methods registered by name; unknown `deployment_*` and `editor_draft_*` commands keep their family guard and message. Two commands whose previous checks had a different order (`use_pilot_profile`, `run_job`) keep them in the handler. `MainWindow.completed` dispatches to seven page controllers under `ui/pages/`, which hold the former branch bodies in their previous order; a review compared every branch with the previous method. `Page` names the eight workflow tabs and `REVIEW_PAGE_SIZE` the shared 200-record page. mypy now checks `ui.*`: new UI modules are strict, and `bridge`, `components`, `drafts`, `verify` and `window` have their function bodies type-checked without annotation requirements yet. This found and fixed a `MainWindow.style` attribute that shadowed Qt's `style()` and an `addTab` overload that broke icon tabs. Remaining: annotate those five modules and remove them from the relaxed override. |
| M3 One installer contract | Ownership, process and path checks exist in Python and two PowerShell installers and have drifted. Some deployment activation and preview paths have no production caller. | **Implemented in source.** `resources/recipient-core.ps1` holds the file-identity and process C# types and the path, digest, create-new, journal and game-process helpers once; `recipient_scripts.py` inlines it at one marker line when a package is exported, so every shipped script stays self-contained and its hash pins cover the generated bytes. The Unity patch and Ren'Py copy/additive installers use it. The recipient process check now has Python's semantics: any image under the game root refuses, an unreadable or unmatched image whose name matches an EXE under the root is uncertain, and a game tree that cannot be inspected (links, reserved names, unreadable folders, more than 100,000 entries) fails closed with its own message in both; a folder without any EXE gets a select-the-game-folder message. Per-file checks reuse a closed result for at most one second and never across a typed confirmation, after which every current installer checks all planned destinations again before its first write. Device names match in ASCII only, as on Windows. Python and the core share path and process vectors (`tests/fixtures/recipient-*.json`); Python's name rule was tightened to the core's, and the three remaining differences are documented in the fixtures. Frozen installers built by their own revisions' exporters (Unity patch rc.6, rc.7 and 0.5.0; Ren'Py copy formats 1-2 from 0.5.0; additive format 3 from the 0.6-0.7 line) and the current Python and PowerShell implementations run one ownership scenario suite: exact plans and receipts, conflicts before and after review, clean and partial removal, tampered or relocated receipts, a process under the root during install and removal, a retry after restoring a preserved file and interrupted installs. Legacy behaviour that differs is asserted as recorded behaviour. The unused `prepare_i2_deployment_preview` and `DeploymentService.activate` were removed after receipt and plan searches; the loader-support staging tools and the documented `DeploymentAdapter` protocol stay. Remaining: an interrupted Ren'Py copy or additive install has no receipt yet, so its own Remove refuses and recovery is manual from the journal; the frozen 0.6-0.7 additive installer can leave unreceipted additions when a destination appears during its confirmation prompt. |
| M4 Test and release hygiene | Unity worker parsing has no synthetic end-to-end test, migration tests rebuild old schemas by dropping objects, and privacy and version rules are duplicated across tools. | **Implemented in source.** `tests/fixtures/unity-serialized/` holds small format-17 serialized files and a metadata-only .NET image written by its own deterministic builder from UnityPy's bundled Unity 2017.4 class layouts; the real worker subprocess reads them through the I2 type-tree path and the managed-metadata fallback with the same unit IDs, and truncated or trailing payloads, assemblies and script files fail closed. A strict xfail records the C5 type-tree naming gap. `tests/fixtures/legacy-projects/` holds 11 frozen projects built by the released revisions' own code (schemas 4-6) and by the oldest revision's stepwise SQL (schemas 1-3), pinned by SHA-256 with recorded expectations; copies migrate to the latest schema with consistent backups, unchanged rows, pages, history, drafts and jobs, and injected failures roll back. Migration tests no longer rebuild old schemas by dropping objects. CI runs separate Python and C# jobs (`tools/check.py --python-only`/`--dotnet-only`), a stdlib per-test watchdog (120 s, `@pytest.mark.test_timeout`, `UNITYTRANSLATOR_TEST_TIMEOUT`), step timeouts, a uv cache keyed on `uv.lock` with a SHA-pinned `actions/cache`, and a concurrency group that cancels superseded branch runs but keeps every main run. `tools/release_rules.py` is the one privacy, label, language and version rule module for every packaging tool; source archives accept only the three synthetic fixture trees by path and type, and an sdist entry outside its root folder is refused. `src/unitytranslator/__init__.py` is the one version source (`pyproject.toml` reads it dynamically) and the package description names Ren'Py; `uv.lock` records the project version as dynamic. Remaining: the workflow has not run on GitHub yet. |

### Phase T: throughput and translation quality

| Item | Planned change and acceptance |
| --- | --- |
| T1 Project translation memory | **Implemented in source.** Review > Bulk actions > Reuse translation memory runs `translation_memory_preview`, which reports candidates, matching keys, approved and model donors, conflicts and skips by reason (approved, draft, queued in an unfinished job, already translated, same text, already offered, format check), and `translation_memory_apply`, which requires `user_action` and the unchanged preview token, recomputes the plan in one transaction and refuses any change. Both commands use the project-identity and extraction/translation idle guards. A key is the exact source text (byte-exact, as its source hash) with the effective format rules, category, context, target language and a digest of the record's current verified dialogue window (speaker and neighbouring speakers and source text, not record IDs) when it has one; model donors add their generation-profile fingerprint (the profile without policy versions) and glossary/style versions, which must equal the selected model settings and the active policies. Donors are other records' approved translations of the current source, except approvals awaiting glossary/style re-review, and, only when the user opts in, warning-free unapproved model translations without a draft. Approved donors win over model donors; a key whose winning donors disagree reuses nothing and is reported as a conflict. A record is never its own donor, and a memory candidate, approved or imported, is never a donor. Targets are records without approval, draft, queued job item or (by default) current translation: the candidate becomes the current unapproved translation and the work version increases. An option also adds a history-only candidate to records with an unapproved translation without changing their current text, status or version; the reviewer selects it explicitly. Candidates are stored with origin `import` and metadata `origin_detail: translation_memory`, the key digest, the donor record, key and revision and, for model donors, the profile fingerprint and policy versions; no schema change was needed. Re-applying adds no duplicates: a stored candidate counts as already offered, or is reused as the current translation, only when its text, complete provenance, format rules and review checks version are identical; otherwise a fresh candidate with current provenance and issues is added and older ones stay in history. Review rows, the record details and history label them as translation memory with their donor and say whether a reviewer approved that revision. The action's tooltip and options dialog state that it covers the whole project. Approved-only exports and packages ignore them, portable export marks them unapproved, and job reports do not count them as model output or corrections. Remaining: matching ignores the review filters and covers the whole project; Ren'Py dialogue contexts name their block, so equal Ren'Py lines in different blocks never share a key; there is no command-line command. |
| T2 Prompt registry | Prompt files and the profile's `prompt_version` already exist, but jobs accept only `translate-v1` and the provider uses a fixed allowlist. A validated registry admits bundled, read-only prompt versions; profiles and imports select only bundled IDs, never prompt text, and a missing ID means `translate-v1`. A new version may add language names and fixed-template corrective feedback on retries. Isolated pilots compare failures, retries and human judgment between versions. |
| T3 Request efficiency | **Implemented in source.** A successful record now costs two write transactions instead of four: the claim and its attempt start commit together, and the result, its revision, the record state and the run record commit together; a failed attempt records its run with any outage refund, and a final failure also releases the claim, in one commit. Recovery is unchanged: a crash inside either transaction leaves the record as before it, and a crash between them requeues it with that attempt charged and the run marked interrupted, as a crash after the former separate attempt commit did. Live progress is kept from each commit with at most one index lookup per record and one job scan at the first report, instead of a full scan at every report. A job owns one HTTP client, shared by its workers, sized for the parallel requests and closed on completion, pause, cancel, error and shutdown; model lists and connection tests keep short-lived clients. With more than one parallel request, a llama.cpp job asks `/props` (`total_slots`), then `/slots`, once through that client with a 3 s limit; size-bounded, type-checked slot counts are kept in run metadata, and when the parallel requests exceed them the run result, live progress, job report and translation page carry an English-template warning without blocking; the job report uses the latest run's settings. LM Studio is not probed, and unknown or malformed slot reports give no warning. Synthetic tests count two transactions per record and no writes outside them, compare live progress with full scans, kill a worker process inside and between the two commits, check pause, cancel and shutdown with a request in flight, and show one pooled client opening at most one connection per parallel request (ten without it for nine records at three parallel requests). Optional micro-batching of short context-free records remains planned: it uses its own prompt version, joins pilot identity, needs a matching reviewed pilot and keeps exact-ID per-record validation. The job report counts a manual edit as a correction only when its revision follows the generated one, not by timestamp. Remaining: the command line has no job command, so command-line users see the warning only in saved job reports; on the user's llama.cpp server writes fell from 4.29 to 2.29 per record and the slot warning appeared at 16 parallel requests against 12 slots (see Compatibility). |
| T5 Reasoning control | **Implemented in source.** With a local Gemma model on llama.cpp every request reasoned for about 300-850 tokens, even for a seven-word message, so one-line records took about 40 s each at 12 parallel requests and some failed as `output_truncated`; the app could only switch reasoning off, and only for LM Studio. The profile now offers server default, off (LM Studio and llama.cpp) and an adaptive llama.cpp thinking budget that grows with record length and dialogue references and is reserved on top of the output budget. Job reports summarize budgets and reasoning size so the effect can be compared on the user's own records. Effort levels (`low`/`medium`/`high`) are not offered: the measured template ignored them. |
| T4 Review QA | **Deterministic checks implemented in source** as `review-multilingual-v6`. Glossary rules are compiled once per content-addressed glossary version and language pair (`PolicyStore.compiled`, a small in-process cache) and reused by every job attempt and the quality audit. Source terms match with word boundaries, or as substrings in Chinese, Japanese, Korean, Thai, Lao, Khmer and Burmese, which also fixes rules whose Chinese or Japanese source term sits inside a longer phrase. Target terms of a preferred translation accept a closed list of endings per language, documented in `glossary_match.py`: the Turkish plural/possessive/case/-ki/copula chain with an optional apostrophe and final-consonant softening (last word only), Finnish case, possessive and clitic endings, German case/plural endings, Russian and Ukrainian case endings after dropping a final vowel or adjective ending, French, Spanish, Portuguese and English plurals and Italian final-vowel changes; a remainder outside the list is a different word (okul is not ok, Demirci is not demir), and umlaut plurals, consonant gradation, fleeting vowels and compounds are not tolerated. A preserved name must appear verbatim, as written in the rule or exactly as it occurs in the source (an all-caps title), with the same endings allowed; a case-sensitive rule keeps its case and its endings follow the text. The issue code stays `glossary_violation:<source term>`. Negation and condition cues are tables per target language (`tr`, `de`, `fr`, `es`, `pt`, `ru`, `zh`) for English sources: broad target cues, look-alike phrases removed first (Russian не менее, Chinese 非常), and the added-negation check off for Chinese; German, French, Spanish, Portuguese and Russian sources to English get strict negation cues only; other pairs skip both checks. `length_ratio_review` flags a translation whose visible length (protected tokens, tags and combining or format characters excluded, whitespace runs counted once, East Asian wide characters counted twice) exceeds source length x category ratio (1.6 for UI/menu/button/label/interface categories, 2.5 for dialogue/description/subtitle/journal-like categories, 2.0 otherwise) x target/source expansion factor (for example German 1.35, Russian 1.3, French 1.25, Turkish 1.15) + 3, when the source has at least 6, 20 or 10 visible units; the thresholds are named constants in `validation.py`. Version change: stored revisions keep their recorded issues and `review_checks_version`, statuses and approvals are not changed or revoked, and nothing is rechecked automatically. New model, manual, import and translation-memory candidates record v6 issues; translation memory therefore treats an older v5 candidate as not yet offered and adds a fresh one. The quality audit (an explicit user action) rechecks current translations with v6 and the active glossary version, reports findings the stored issues lack as new, and changes no revision. **Local reviewer pass implemented in source.** Review > Bulk actions > Run local reviewer calls `local_review_preview`, which validates the selected model settings, counts current translations in the review filters (or an explicit unit list) and checks that the already running server lists the model, then, after a confirmation naming the server and model, `local_review_run`, which needs `user_action` and the preview token; both use the project-identity and extraction/translation idle guards, `local_review_cancel` stops a run, and a running review holds translation jobs and other model requests. Prompt `review-v1` sends one record's source, translation, category and context as JSON data. The reply must be one strict JSON object with the requested ID, unique codes from the closed set `meaning_review`, `omission_review`, `addition_review`, `terminology_review`, `tone_review` and `grammar_review`, and an optional plain note of at most 300 characters; unknown codes, extra fields, other IDs, duplicate keys, tool calls or a truncated reply write nothing. Requests reuse the local-address check, the T5 reasoning options with the adaptive budget, structured output and one pooled client per run with bounded parallel requests. A run covers at most 500 records and commits each review on its own, so a cancelled run keeps completed reviews and a rerun skips revisions already reviewed with the same settings. An unreachable server or a missing model fails the preview with nothing written; a connection or server failure stops a run. Schema 8 stores one `local_reviews` row per translation revision and reviewer (prompt version, provider, model, reasoning mode, temperature and structured output; the address is recorded too); text, revisions, stored issues, statuses and approvals never change. Review rows, record details and history show the codes as Local reviewer: meaning and so on, with the model and prompt version, only for the revision that was reviewed, so an edit leaves them behind. Job reports and the quality audit count them under `local_review`, apart from `issue_counts`. Remaining: glossary rules are not sent to the reviewer; codes neither filter records nor block approval; portable export, shareable packages and the command line ignore them; one small synthetic run on the user's llama.cpp server (see Compatibility) is the only real-model evidence. |

### Phase C: contract-based coverage

Support is defined per mechanism, such as an I2 layout family, Unity text components
or the Ren'Py translation framework, not per game. For new support, author-side
allowlists (build hashes, exact version strings, company/product profiles) give way
to checks on the user's own files: the app checks statically that the files carry
the structure a reader depends on and that runtime entry points match a verified
family contract, or it refuses and names the missing contract. A static match is
not runtime proof. A contract-matched build without runtime observation gets no
compatibility claim and at most an experimental installation route; installation
always needs current approved revisions, a concrete reviewed create-new plan and
owned-removal checks. Engine families are verified with synthetic games built from
official tooling rather than a growing list of commercial titles; real games remain
private regression references. Reports distinguish verified families,
contract-matched builds and unsupported inputs with reasons. Where a format proves
that a failed record cannot change other records' identities, serials, grouping or
order, that record is excluded and counted; otherwise the whole set is refused as
before. Existing pins stay valid for the projects and packages created under them,
and existing projects keep their recorded reader, profile and legacy report keys.
Game-specific support such as the bundled Krypta reader and runtime, with its
validated data profile, stays optional and is not the basis of support.

Items are in priority order; C1 runs alongside the others.

| Item | Planned change and acceptance |
| --- | --- |
| C1 Engine family matrix | A developer-side step outside the app, after explicit user authorization for each download, license activation, SDK or Editor run and synthetic-game launch: build small synthetic games with pinned official Ren'Py SDKs across 7.x and 8.x and with Unity Editor LTS versions under the user's own license (Mono first). The app itself never runs a Ren'Py launcher, compiler or translation generator. Contract digests per release become validated data with provenance, summarized in Compatibility. Only derived vectors, fingerprints and minimal synthetic data whose license permits redistribution enter the repository, with notices; engine or player binaries and Unity built-in resources never do. CI never downloads SDKs or uses real games. Acceptance: at least one pinned release per claimed family. |
| C2 Ren'Py compiled-ID cross-check | For sources with a paired `.rpyc`, a data-only opcode scan, never unpickling, confirms that each computed dialogue ID occurs exactly once in the compiled file, using the slot and string forms C1 records per family. This is additional evidence for dialogue identity; it does not replace engine-source contracts for string keys, escapes, block grouping or source order. Sources without a paired `.rpyc` keep the current checks. Ren'Py 7 dialogue becomes readable only after C1 establishes its family, and Python 2 string semantics stay unsupported until separately verified. The persisted `renpy-script-8.1.2-v1` parser label stays unchanged as source identity, and a separate versioned dialect record names the verified family. Acceptance: synthetic vectors with a shifted serial fail. |
| C3 Ren'Py runtime family gate | A new recipient ZIP format binds to the script-bearing files whose IDs were computed and to a runtime family whose translation loading, language selection and `.rpyc` sidecar/cache behavior C1 verified with synthetic and separately authorized pilot evidence, instead of one build string and every build file. Recipient checks still require a clean target namespace and refuse conflicts across loose files and archives. Builds that only match the static contract are reported without an installation route. Formats 1-3 keep their checks. Installation still needs the package's frozen current approvals and a reviewed create-new plan. Acceptance: synthetic recipients with the same runtime contract and unchanged script files pass; a changed loader function or script file is refused with a reason. |
| C4 Ren'Py input breadth | Template input reports unsupported blocks such as `extend`, `voice` and `nvl clear` as counted exclusions and is never presented as complete. A new text-rule version may protect balanced unknown source tags as opaque tokens with a per-tag review diagnostic; allowlisted tags keep their pairing rules, and self-closing or unbalanced custom tags stay excluded. As in F3, existing units keep their rule until explicit re-extraction, which invalidates only affected approvals. Voice/nvl groups and say suffixes follow verified vectors. Discovery budgets count only relevant files. New snapshots store source bytes in content-addressed storage through a numbered migration; existing snapshots move only with verified byte and hash equality or stay as they are. Last, a data-only `.rpyc` reader for compiled-only games maps an allowlist of class names to plain records and never constructs objects. Acceptance: each unsupported block is counted, and tag vectors pass in the exporter and recipient validators. |
| C5 Unity content-based selection | Each bundled reader exposes a cheap static detector, and a bounded scan of serialized candidates, including StreamingAssets bundles, reports detected content without extracting it. For new selections, reader choice follows that content; company/product profiles remain hints. A different detected reader for an existing project is reported and needs explicit re-selection that preserves history. Detection never grants extraction or installation. Acceptance: a synthetic I2 object read through the type-tree path reports the same GameObject name as the managed fallback; the suspected empty-name failure, found by code reading only, is confirmed by that test first. |
| C6 Unity static type-tree generator | `managed_schema` replaces its Unity 2017-only gate with explicit Unity version dialects. It resolves inheritance and type references across `Managed/*.dll`, Unity built-in structs, more primitives, non-int32 enums, object references, serialized references and generic fields beyond `List<T>`. It reads both I2 layout families, ScriptableObject sources and text fields of `UI.Text`, TextMeshPro and `TextMesh` in scenes and prefabs without executing game code. Exact byte consumption remains the per-object contract; unknown layouts fail with reasons. Acceptance: synthetic stub assemblies and serialized vectors per dialect, including rejected layouts. |
| C7 Unity ABI-checked runtime | The I2 plugin's compatibility check moves from author-side game hashes to an install-time static check that every type, field and method the shipped plugin references exists in the user's assemblies with matching signatures, together with Mono x64 and loader-family checks. Payloads keep binding to the assembly hash and per-entry source hashes of the build they were extracted from. A second compiled variant covers the `LanguageSourceData` layout family. Installation rules are unchanged. Acceptance: stub assemblies that differ by one member or signature are refused with a reason. |
| C8 Generic Unity text runtime | A bundled plugin with compiled hooks on Unity-owned text APIs (`UI.Text`, `TMP_Text`, `TextMesh`) replaces reviewed, statically extracted source strings, keyed by source-text hash and limited to the component, scene/prefab or asset contexts they were extracted from; matching text elsewhere is left unchanged. Payload data selects strings, never hook targets. Equal source text with different approved translations is reported and excluded. The plugin neither captures nor transmits text, and runtime-composed strings stay out of scope. It targets Mono builds that pass C7-style checks; installation needs current approvals and a reviewed create-new plan, and removal follows owned-addition receipts. Acceptance: stub-based C# tests cover replacement, out-of-context text, conflicts and rollback. |
| C9 Interop export | A fixed bundled writer exports current approved revisions to a named, versioned community runtime text format, such as XUnity.AutoTranslator translation files. It escapes separators and refuses entries the format would interpret as regex, substitution or configuration directives. Equal source text with different approved translations is reported and excluded. It writes no configuration, enables no capture or online translation and makes no compatibility or installation claim. No third-party runtime is bundled, downloaded or installed. Acceptance: a synthetic export reparses under the format's rules and round-trips every exported pair. |

IL2CPP reading and runtime, Godot and Unreal stay outside Phase C; see
[deferred engine expansion](#deferred-engine-expansion).

### Phase D: delivery

| Item | Planned change and acceptance |
| --- | --- |
| D1 Payload refresh | Replaces only unchanged receipt-owned additions with current approved revisions after identity, single-link and hash checks under a concrete reviewed plan, writes a new receipt and never touches original game files. Synthetic tests cover a tampered owned file, a stale receipt and rollback. |
| D2 Loader allowlist | The protected preloader loads only catalog-pinned plugin files by name and hash, as a registered upstream change with matching source and notices. |
| D3 Faster game checks | Single-pass hashing per operation. A stat cache may speed discovery reports but never replaces hash checks at installation or removal. |
| D4 Worker limits | Reader workers run in a Windows Job Object with a memory limit and a minimal environment; the documented boundary remains crash isolation, not an OS sandbox. |
| D5 Package authenticity | Shareable packages carry a signature or a published hash shown before installation. |
| D6 Headless CLI | Pilot, translation and report commands reuse session commands; approval stays an explicit human step in the desktop. |

Capturing text from running games remains outside this plan.

## Ren'Py roadmap

Implementation must also extend source/package privacy checks for Ren'Py inputs,
keeping real scripts/archives/compiled data private while allowing identified synthetic
fixtures. Dependency additions need pinned provenance and matching notices/sources.

R0-R2 implement the initial template-based, export-only increment with synthetic
verification. R4 includes the audited original-source behavior family, `_ren.py`,
large sets and disjoint containers; overlapping load order and compiled-only input
remain planned. R3 has an experimental additive ZIP with synthetic recipient checks;
original-folder gameplay evidence and automatic sidecar ownership remain open.
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
| R3: additive installation | New matching-build ZIPs add only text and fixed helpers, with one folder selection, reviewed create-new plans, build/input checks and ownership-checked removal. Compiled sidecars block automatic removal. Additive Windows checks are synthetic; actual original-folder gameplay remains unverified. Legacy copy pilots retain their separate evidence. Explicit install/launch actions stay separate. |
| R4: wider Ren'Py input | Implemented audited static source behavior, symbolic attributes, `_ren.py`, bounded large sets, disjoint loose/archive unions and sharded output. Unknown contracts, overlapping containers, multiline dialogue and compiled-only games remain unsupported. Never deserialize executable objects to read scripts. |

R0-R2 define the first export-capable increment. R3 evidence must describe the
actual copy/original installation route. A synthetic template test is not evidence
for a particular commercial game, engine release, font or all scenes. No game input
is needed to implement synthetic infrastructure; missing real-game evidence blocks
only the corresponding compatibility/installation claim.

### Broader Ren'Py support (planned)

This is the next coverage milestone, after [roadmap phase F](#phase-f-foundation):
reusable support across games and verified engine families, not another exact-build
exception. Keep one extraction/review/export pipeline and
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
when it differs. Version overrides permit inspection only. Package formats 1-3
bind each recipient ZIP to its author's exact source build; the planned format of
roadmap item C3 binds to verified script files and a verified runtime family, never
to a version string alone. Broader reader compatibility alone never makes a patch
interchangeable between game builds.

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
Extend the native installation ZIP by tested runtime behavior families. Include source
dialect/feature evidence in the manifest and verify it at export and recipient time.
Inspect development/mod folders for private repository, tooling and user data before
defining a copy scope; proposed omissions must be explicit in the new-copy plan,
never silently broaden existing inventories. The additive ZIP has synthetic
recipient checks; original-folder gameplay and automatic sidecar ownership remain
unverified. Game launch and runtime pilots require applicable explicit user action.

Items C1-C4 of [roadmap phase C](#phase-c-contract-based-coverage) order the
contract-based part of these gates; overlapping/mod source resolution and multiline
literals remain as described above.

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

The planned contract-based Unity work is listed as items C1 and C5-C9 of
[roadmap phase C](#phase-c-contract-based-coverage). It precedes the other Unity
methods above; a further I2 profile or TextAsset layout is added as validated data
on top of C5 detection and the C6 generator. C5 only detects bundled content;
AssetBundle/Addressables resolution remains the item above.

Unreal Engine and Godot testing and implementation are planned after broader Unity
and Ren'Py support. Establish supported engine versions, localization resources,
packaging and safe export/installation behavior before enabling each capability;
neither engine is currently supported. OCR, voices, model training,
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
python tools/check.py --dotnet-only
uv run python tools/check_documentation.py
uv build
uv run python tools/check_distribution.py
```

Use targeted synthetic fixtures first, then Ruff/mypy/pytest and relevant C# checks
for shared changes. C# projects require their compatible .NET SDK. `tools/check.py`
allocates a new `.cache/` test directory; never use a running application's directory
as pytest `--basetemp`. Do not repeat broad tests without new changes/failures.
Each test has a 120 s watchdog; raise it per test with
`@pytest.mark.test_timeout(seconds)` or per run with `UNITYTRANSLATOR_TEST_TIMEOUT`
(0 turns it off). The version lives only in `src/unitytranslator/__init__.py`;
packaging privacy rules live only in `tools/release_rules.py`.
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

Backend errors are English. A `Diagnostic` (a `ValueError`) carries its English
template as the reason code and its `{p0}`-style parameters separately; a plain
message that is a catalog key is its own code. The bridge sends a `Failure` with code,
parameters, English text, command, request token and project ID, and the interface
localizes it by code, falling back to the English text for uncatalogued details such
as OS or server messages. Stored plain text is matched against current templates with at
most two parameters and against legacy aliases, only up to 2,048 characters. Renaming a template requires a
`resources/locales/legacy-messages.json` alias. That table maps messages written by
earlier versions, which stored data keeps verbatim, to current templates, including
patterned parameters; it never rewrites stored data. Source-rule tests reject
non-English source text outside documented exemptions, and any exception message that
is dynamic, uncatalogued or passes its template parameters indirectly. Generated Turkish pilot reports, their issue labels,
linguistic patterns and the persisted approve-all confirmation phrase are not
interface diagnostics and stay as they are.
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
