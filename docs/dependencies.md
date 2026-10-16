# Dependency inventory

The versions below describe the recorded Windows x64 / CPython 3.12.14 development
environment. `uv.lock` contains the exact resolution and package hashes. License labels
were read from installed package metadata; full original notices and native component
licenses are collected for the binary distribution. The project's MIT license does not
cover game content, model files or third-party components.

| Direct dependency | Recorded version | Metadata license | Purpose |
| --- | --- | --- | --- |
| UnityPy | 1.25.4 | MIT | Read Unity/I2 assets; limited static type-tree fallback |
| HTTPX | 0.28.1 | BSD-3-Clause | Async requests to existing local model servers |
| Pydantic | 2.14.1 | MIT | Strict data boundaries |
| dnfile | 0.17.0 | MIT | Read assembly type/field/attribute metadata without executing it |
| PySide6 | 6.12.0 | LGPL/GPL/commercial options | Qt Widgets UI and standalone packaging |

The UnityPy MIT text is included in the installed package; see the
[official project](https://github.com/K0lb3/UnityPy).
Qt/PySide licensing and corresponding source access are documented separately in
[SOURCE-ACCESS.md](SOURCE-ACCESS.md) and the [official Qt for Python documentation](https://doc.qt.io/qtforpython-6/).
Standalone tests on the development machine do not establish clean Windows compatibility.

| Other installed package | Recorded version | Metadata license |
| --- | --- | --- |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| archspec | 0.2.6 | Apache-2.0 OR MIT |
| astc-encoder-py | 0.1.12 | MIT |
| attrs | 26.1.0 | MIT |
| brotli | 1.2.0 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| colorama | 0.4.6 | BSD; consult the packaged notice for the exact variant |
| etcpak | 0.9.15 | MIT |
| fmod_toolkit | 0.1.3 | MIT |
| fsspec | 2026.9.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| librt | 0.16.0 | MIT |
| lz4 | 4.4.5 | BSD; consult the packaged notice for the exact variant |
| mypy | 1.20.2 | MIT |
| mypy_extensions | 1.1.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pathspec | 1.1.1 | MPL-2.0 |
| pefile | 2024.8.26 | MIT |
| pillow | 12.3.0 | MIT-CMU |
| pluggy | 1.6.0 | MIT |
| pydantic_core | 2.50.1 | MIT |
| pyfmodex | 0.7.2 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| ruff | 0.17.0 | MIT |
| texture2ddecoder | 1.0.6 | MIT |
| tpk_ar | 0.2.4 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |

Audio/texture packages are transitive UnityPy dependencies. The application does not
load an audio/image model or export game audio or textures. Hatchling runs in the
isolated source-build environment and is not an application runtime dependency.
`uv build` produces a wheel/sdist, not a Python-free Windows executable.

Nuitka 4.1.1 is pinned as the Windows build compiler. Its compiler is AGPLv3; its
[Runtime Library Exception](https://github.com/Nuitka/Nuitka/blob/develop/LICENSE-RUNTIME.txt)
allows generated programs to use a different license. The compiler license, exception
and NOTICE text are collected separately. UnityTranslator's MIT license is unchanged.
See [Nuitka's official license explanation](https://nuitka.net/pages/overview.html).

Development-only dependencies include [dncil](https://github.com/mandiant/dncil)
1.0.2 (Apache-2.0), used for static CIL inspection, and
[fontTools](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html) 4.66.1 (MIT),
used to inspect font coverage in memory. They do not execute game assemblies, export
game fonts or become desktop runtime dependencies. Consult `uv.lock` for the pinned build.
