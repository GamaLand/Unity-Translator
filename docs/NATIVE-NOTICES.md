# Native runtime components

The MIT license covering UnityTranslator's own code does not replace the licenses of
its dependencies. `PACKAGE-MANIFEST.json` provides the packaged file/hash inventory.

- Python and Python package notices are in `LICENSES` and `THIRD_PARTY_NOTICES.json`.
  The full CPython license text is retained.
- Qt/PySide source archives and replacement/rebuild information are described in
  `SOURCE-ACCESS.md`. The unused Qt PDF plugin and DLL are omitted.
- Microsoft C/C++ runtime DLLs (`msvcp140` and `vcruntime140` families) are Microsoft
  components subject to their own terms; they are not relicensed under MIT. Debug
  runtime files are not packaged. References:
  [Visual Studio 2026 redistribution](https://learn.microsoft.com/en-us/visualstudio/releases/2026/redistribution),
  [Visual C++ runtime terms](https://visualstudio.microsoft.com/license-terms/vs2026-ga-visualcpp-v14-redist-runtime/).
- Python SSL dependencies (`libssl`/`libcrypto`) are OpenSSL components. OpenSSL and
  libffi license texts are in `LICENSES/NativeRuntime`; `catalog.json` in that folder
  records source URLs and hashes. The local PE metadata did not identify an exact
  libffi version, so no exact version is asserted. The application's loopback-only
  network policy is independent of these libraries' licenses.
- The experimental loader's separate component/source inventory is in
  `runtime-kit/RUNTIME-NOTICES.json`, `runtime-kit/LICENSES` and `runtime-kit/SOURCES`.
  The portable loader variant has equivalent records in `portable-runtime-kit`.

Redistribution must preserve component notices and corresponding source access.
The program does not publish this package automatically. See `SOURCE-ACCESS.md` and
the original, unchanged component license texts for the delivered materials.
