# Development

The optional generation-profile field `reasoning_effort="none"` sends a
request-scoped LM Studio Chat Completions option; it does not change server defaults.
The desktop advanced settings expose this opt-in. Other providers reject this option.
Default profiles omit the new field when serialized, preserving existing job and
pilot identities. Requested settings and actual usage remain distinct: an ignored
server option does not establish that reasoning was disabled. A local loaded-model
synthetic probe returned zero reasoning tokens with this request option; model/server
support must be checked independently. No model is downloaded or started automatically.

## Architecture and source map

Python 3.12 owns project state, translation jobs, validation and deployment plans.
PySide6 Widgets is a presentation layer. `ApplicationSession` dispatches work through
the Qt bridge to an independent asyncio/SQLite-owner thread; minimization does not
pause translation. Unity parsing runs in a separate process to contain reader crashes.
No game assembly is executed for extraction.

| Location | Responsibility |
| --- | --- |
| `src/unitytranslator/application.py` | Shared application session/commands |
| `domain.py`, `repository.py`, `resources/schema-v*.sql` | Data contracts, revisions and migrations |
| `jobs.py`, `providers.py`, `policy.py`, `validation.py` | Durable queue, local HTTP, policies and checks |
| `discovery.py`, `profiles.py`, `i2*.py`, `managed_schema.py`, `workers/` | Read-only discovery and current I2 extraction |
| `capabilities.py` | Independent discovery capabilities and structured reasons |
| `source_contracts.py`, `reader_adapters.py` | Bundled reader/deployment contracts and deterministic reader selection |
| `krypta_profile.py`, `textasset_layouts.py`, `textasset_export.py` | Reviewed TextAsset profile, explicit line layouts and staged payload exports |
| `worker_process.py`, `workers/textasset_probe.py` | Bounded, cancellable TextAsset worker IPC |
| `deployment.py`, `installation.py`, `runtime_*.py`, `shareable.py` | Additive install plans, runtime data and ownership |
| `editor_drafts.py`, `review_selection.py`, `portable.py`, `reports.py` | Review, drafts, history interchange and reports |
| `ui/`, `resources/locales/` | Qt views, bridge and eight offline interface catalogs |
| `guide/` | Eight localized user guides |
| `adapters/` | I2/protected-loader C# sources, synthetic tests and original notices |
| `tools/` | Verification, source tracing and packaging utilities |

The built-in registry wraps the existing I2 reader and the fingerprint-bound Krypta FM
TextAsset reader. Profiles are validated bundled data and cannot select imports,
commands or reflection targets. JSON/CSV readers remain [planned work](roadmap.md).
The current installation adapter is still the identified Mono/I2 integration.
`capabilities.py` defines independent discovery capability DTOs with stable reason
codes and English fallback messages. Shared scan/probe services attach the versioned
report without changing legacy report keys. CLI summaries and the desktop discovery
view consume it; export and installation require their own current approval/build
checks. Runtime, container and localization indicators are separate and may be empty.
A translation-project JSON import/export is not a game JSON reader. See the independent
support results in [compatibility.md](compatibility.md).

## Setup and checks

```powershell
uv sync --locked --extra ui
uv run --locked --extra ui unitytranslator gui
uv run --locked --extra ui python tools/check.py
uv run --locked --extra ui python tools/check.py --with-dotnet
uv build
uv run python tools/check_distribution.py
uv run python tools/check_documentation.py
```

C# checks require the compatible .NET SDK indicated by their projects. Tests use
synthetic fixtures, not installed games or user projects. `tools/check.py` allocates a
new directory under `.cache/`; never point pytest's `--basetemp` at work to preserve.
Use targeted checks first. Repeat broad tests only after new changes or unresolved
failures. CI success does not prove a clean Windows installation or new game support.

## Compatibility and persistence

Schema 4 inputs, old project interchange, I2 record identities and v1/v2 runtime payloads are
compatibility inputs. Keep numbered migrations and fixtures; an old file is not
obsolete simply because a newer format exists. Imports preserve existing approvals
and treat archived approvals as history. Protect user drafts and optimistic versions.
Schema 5 adds logical-source descriptors and immutable snapshot-to-source metadata;
legacy I2 IDs and revision hashes remain unchanged. Migration takes a consistent
SQLite backup before transactional changes. A source update affects only its own
records; complete multi-source activation either commits in full or rolls back.
Historical snapshot metadata stays verbatim rather than inventing past source paths.
TextAsset positional IDs include the complete payload fingerprint: insertions,
reordering or edits create new records and keep old approvals/drafts as inactive history.
Imports retain legacy payload schemas and never grant local approvals or deployment
authority. A restored TextAsset project must re-extract local sources before staging.

TextAsset records explicitly select `literal-lines-v1`; the shared provider, review,
draft and approval pipeline does not impose I2 tag/plural parsing on these strings.
Staged exports reconstruct verified payload snapshots using current approved revisions,
retain unapproved source text, reject stale sources/drafts/revisions and preserve all
non-text fields, encoding/BOM and newline sequences. No Unity asset is rewritten.

Original-file inventories and ownership receipts form a separate protection boundary.
Never reset them to work around a conflict. [Installation](installation.md) explains
safe conflict handling and recovery. [Runtime components](runtime-components.md)
describes the source/binary provenance chain; keep its build/audit tools and notices.

## English-first source and localization

Use English for source identifiers, CLI help, new diagnostics, comments and public docs.
Keep localized UI text in the eight UTF-8 catalogs and guides in `guide/{code}.md`.
Source labels use `tr(...)`; preserve placeholders such as `{p1}` and Qt progress tokens.
Do not translate game content, IDs, paths, model names or persisted protocol values as
interface labels. Legacy diagnostic/protocol strings are compatibility data and must
not be mass-rewritten without dedicated tests and a migration plan.

The UI language defaults to English and changes on restart. The project language pair
is independent. `UNITYTRANSLATOR_UI_LANGUAGE` selects an isolated test locale;
`UNITYTRANSLATOR_CONFIG_HOME` redirects preference storage during tests. Language
normalization/default style live in `language.py`; old custom policies remain user data.

Source checkouts open help from `guide/`; wheels use bundled `resources/guides/`;
new Windows builds ship `guide/`. Published RC7 archives retain their original layout.
All three delivery modes must resolve a guide without a network request.

## Packaging and publishing

Keep `.local/`, `.cache/`, environments, real games/models, user projects, secrets and
build outputs out of Git. Local AI instructions/specifications remain ignored and
excluded from source distributions, including case/name variants. The public roadmap
and architecture above are intentionally available to every contributor.

Review the Git index before committing. `.gitignore` does not untrack previously
committed files. Audit wheel/sdist contents with `tools/check_distribution.py` and
Markdown links/layout with `tools/check_documentation.py`. Build new Windows candidates
in new output folders as described in [windows-package.md](windows-package.md).
Keep the matching dependency sources and original license notices with every release.
A cleanup task does not authorize a push, release or game installation.
