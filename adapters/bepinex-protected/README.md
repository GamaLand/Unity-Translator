# Experimental protected preloader

This directory contains UnityTranslator's own MIT-licensed protection helpers and
synthetic tests. Upstream BepInEx source is supplied from a verified local cache,
not copied into the public repository. Original upstream notices and modification
records are retained in the generated source tree and corresponding-source ZIP.

## Normal external runtime

`tools/prepare_protected_preloader.py` applies only registered changes to the pinned
BepInEx 5.4.23.5 source: remove the persistent Harmony interop/shim paths, redirect
bounded error diagnostics away from the game tree, and check runtime/game separation.
`ProtectedRuntimeDiagnostics` uses unique create-new files in the external runtime;
it never falls back to game-root or current-directory logs. Messages are bounded to
8,192 characters. Relative/network/device/ADS and observed reparse paths are rejected.

## Portable runtime

The separately built portable variant accepts only the owned `UnityTranslatorPatch`
subtree and marker. It does not authorize an arbitrary runtime inside the game tree.
The normal and portable guards must not be interchanged by editing a catalog or INI.

## Build and audit

```powershell
uv run python tools/prepare_protected_preloader.py --source-archive <official-source.zip> --managed <game-Managed> --loader <local-loader> --csc <Roslyn-csc.dll>
uv run python tools/audit_protected_preloader.py --assembly <built-Preloader.dll> --output <local-report.json>
uv run python tools/stage_protected_source.py --game <game> --project <separate-project> --build <protected-build> --archive <official-source.zip>
```

Compile/reference evidence and static CIL checks do not execute game assemblies. The
synthetic .NET tests check path separation, Unicode, create-new logging, message bounds,
identity failures and no game-root fallback. These are not legacy-Mono or complete
native-side-effect proofs. Preserve reference hashes and do not distribute game DLLs.

[Runtime components](../../docs/runtime-components.md) explains the complete build and
provenance chain. [Installation](../../docs/installation.md) adds original inventories,
source/runtime checks, concrete review and ownership-based removal. A prepared loader
or source manifest alone is neither installation permission nor game compatibility.
