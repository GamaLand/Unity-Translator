# Experimental I2 Mono adapter

This is the C# runtime for an identified, fingerprint-matched Mono/I2 game build.
It is not a generic Unity or IL2CPP loader. Current evidence and limitations are in
[compatibility.md](../../docs/compatibility.md).

## Runtime contract

Payload schema v2 carries the source and target language tags. Legacy v1 data retains
an implicit English source. The fixed JSON parser rejects unknown/duplicate fields,
invalid structure and excessive sizes. Source terms must match their hashes in the
selected unique language column before any memory change. Only current human-approved
revisions are exported by the Python application.

The plugin preserves source columns and existing target font/asset references, fills
untranslated text from the selected source, and changes I2 language/culture/RTL state
in memory. It does not save language preferences, download fonts or import translations
from a server. Partial term/localization failures restore language lists, arrays,
touch data, flags and prior language state; failed rollback is reported explicitly.
New scene source objects are rechecked; the same source is not rewritten repeatedly.

Fonts, shaping, overflow, plural rules and additional game builds need their own
verification. The existing plural branch structure is retained, not converted to the
target language's full plural categories.

## Build and verify

Game DLLs are statically read as compiler/metadata references, never executed or
redistributed. Supply paths explicitly; no machine-specific game path is hardcoded.

```powershell
uv run python tools/build_i2mono.py --managed <game-Managed> --bepinex-core <local-BepInEx-core> --csc <Roslyn-csc.dll>
dotnet run --project adapters/i2mono/tests/CoreTests.csproj
```

The C# checks use synthetic I2/Unity stubs and shared protected-format fixtures. They
are not in-game rendering tests. A successful plugin change requires matching rebuilt
binary, source ZIP, notices and runtime catalogs before a new Windows release.

## Loader provenance and ownership

The pinned loader inputs are BepInEx 5.4.23.5 x64 and the components recorded in
[loader-components.json](loader-components.json). The normal and portable preloader
variants have separate protection/build evidence and source archives. The stock
preloader's persistent shim/log paths are not accepted as the protected runtime.
Do not install stock components merely because their package version matches.

See the [runtime component design](../../docs/runtime-components.md),
[component audit](../../docs/loader-component-audit.md),
[protected source trace](../../docs/protected-source-trace.md) and
[source-access requirements](../../docs/SOURCE-ACCESS.md). Original upstream license
texts remain in `third_party_licenses/`; their owners and contents are unchanged.
The application never overwrites original game files. Installation/removal uses the
separate [inventory and ownership service](../../docs/installation.md).
