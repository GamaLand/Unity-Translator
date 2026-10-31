# Source code access

UnityTranslator's own project code is MIT licensed. The accompanying
`unitytranslator-0.6.1.tar.gz` source distribution contains the application and build
tools. `uv.lock` pins dependency versions. `tools/build_windows.py` and
`docs/windows-package.md` describe the standalone build.

Qt/PySide6 6.12.0 sources are provided separately in the accompanying
`UnityTranslator-0.6.1-dependency-sources.zip`. That archive preserves the official
PySide/Shiboken, QtBase, QtSvg and QtImageFormats source archives without modification.
`SOURCE-MANIFEST.json` records their official URLs, sizes and SHA-256 hashes. Users do
not need to download source archives merely to run the program.

Qt libraries are shared DLLs. The application does not impose a runtime hash lock that
prevents replacing those libraries. You can run the source application or rebuild the
standalone package with your own compatible Qt/PySide build. Make modifications in a
separate copy. No additional product restriction is imposed on inspection or debugging.
The components' own notices are preserved in `LICENSES` and `THIRD_PARTY_NOTICES.json`.

Experimental loader sources and licenses are also provided in `runtime-kit/SOURCES`,
`runtime-kit/LICENSES` and `runtime-kit/RUNTIME-NOTICES.json`. The modified preloader's
complete source tree and change evidence are included in `protected-preloader.zip`.
The portable variant has its corresponding notices and sources in `portable-runtime-kit`.
The separate experimental Krypta components, when bundled, retain their own notices
and corresponding sources in `krypta-runtime-kit`. Their fingerprints and evidence
are independent of the I2 kits; staged export support does not establish runtime support.
Original game DLLs and model files are not included.

When redistributing a binary release, provide its corresponding application and dependency
source archives through the same distribution channel; do not distribute only an isolated
application ZIP. Retain the component notices, license texts and source manifests.
The program does not publish releases automatically. The source repository alone is not
the complete dependency-source delivery for a packaged Windows release.

Official references: [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations),
[PySide6 6.12.0 sources](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/),
[Qt 6.12.0 sources](https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/).
