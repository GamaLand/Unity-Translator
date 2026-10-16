# Windows packaging

Current published baseline: 0.1.0 RC7. The repository's guide-directory cleanup is
source maintenance after RC7; it does not silently replace published release ZIPs.

## Prerequisites

Use Python 3.12 x64, the locked UI/build dependencies and a compatible native compiler
for PySide6/Nuitka. Use the .NET SDK required by the C# test projects for their checks.
Build and validate the normal/portable runtime kits separately from explicitly selected,
verified local component caches. Proprietary game DLLs are reference inputs only and
must not be distributed. See [runtime-components.md](runtime-components.md).

```powershell
uv sync --locked --extra ui --group build
uv run --locked --extra ui python tools/check.py --with-dotnet
uv build
uv run python tools/check_distribution.py
```

## Create a new Windows candidate

Build into a new directory under `dist/` while keeping earlier running applications
separate. The build refuses an existing application output directory.

```powershell
uv run --extra ui --group build python tools/build_windows.py --output-root dist/windows-next
uv run --extra ui python tools/package_notices.py --output-root dist/windows-next
powershell -NoProfile -ExecutionPolicy Bypass -File tools/standalone_smoke.ps1 -PackageRoot dist/windows-next/UnityTranslator.dist -OutputRoot .cache
uv run python tools/package_windows.py --output-root dist/windows-next --label rc.next
```

The notice tool bundles the eight `guide/` documents, current documentation,
license texts, corresponding-source notices and the two validated runtime kits.
The ZIP tool checks the complete file/hash manifest and refuses an existing archive.
Never copy only the EXE, omit a runtime source archive or bypass an invalid catalog.
Do not delete an output directory used by a running application.

The synthetic smoke script checks Qt review/edit/approval, Unicode, drafts, paging,
installation/export and worker behavior with an isolated PATH. It runs on the current
machine; it is not a clean-Windows VM test. Record its exit status and limitations.

## Release assets

Publish the Windows ZIP and its `.sha256`, matching application `.tar.gz`, matching
dependency-source ZIP and a delivery inventory. A wheel or repository-ready source ZIP
can be optional developer downloads. Preserve matching component sources/notices as
explained in [SOURCE-ACCESS.md](SOURCE-ACCESS.md). Build a source-only repository ZIP
with `tools/package_source.py` after building/auditing the matching sdist.

Git stores reviewed source changes, not `dist/`, game files, models, user projects or
local AI working documents. Publishing/retagging a GitHub release is a separate action.
A source refactor, passing CI or a loaded local model never proves new game compatibility.
