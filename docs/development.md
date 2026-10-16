# Development

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
| `deployment.py`, `installation.py`, `runtime_*.py`, `shareable.py` | Additive install plans, runtime data and ownership |
| `editor_drafts.py`, `review_selection.py`, `portable.py`, `reports.py` | Review, drafts, history interchange and reports |
| `ui/`, `resources/locales/` | Qt views, bridge and eight offline interface catalogs |
| `guide/` | Eight localized user guides |
| `adapters/` | I2/protected-loader C# sources, synthetic tests and original notices |
| `tools/` | Verification, source tracing and packaging utilities |

The current reader and deployment implementation is an identified Mono/I2 integration.
The generic adapter registry and JSON/CSV readers are [planned work](roadmap.md).
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

Schema 4, old project interchange, I2 record identities and v1/v2 runtime payloads are
compatibility inputs. Keep numbered migrations and fixtures; an old file is not
obsolete simply because a newer format exists. Imports preserve existing approvals
and treat archived approvals as history. Protect user drafts and optimistic versions.
The source set must become scoped before independently ingesting several files.

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
