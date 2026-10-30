# UnityTranslator

A Windows desktop app for translating supported **Unity and Ren’Py** game text
with a local AI model. Extract text, translate it through **LM Studio** or
**llama.cpp**, review the results and export approved translations from one project.

Support depends on the game and input format; extraction, export and installation
have separate compatibility limits. See [current compatibility](docs/compatibility.md).

## Install

**Windows package:** download an available Windows x64 ZIP from
[Releases](https://github.com/GamaLand/Unity-Translator/releases), extract the entire
archive into a separate folder and run `UnityTranslator.exe`. Python is not required.

**From source:** install Python 3.12 and [uv](https://docs.astral.sh/uv/), then run
these commands in the project folder:

```powershell
uv sync --locked --extra ui
uv run --locked --extra ui unitytranslator gui
```

Start LM Studio or llama-server and load a model yourself before translating.
The app does not start games, model servers or downloads automatically.

## How to use

1. Choose the game folder, a separate translation project folder and your languages.
2. Scan compatibility and extract a supported text source.
3. Connect your local model; optionally add glossary and style rules.
4. Translate a small pilot and review it before starting bulk translation.
5. Edit and approve the results, then export them or prepare a supported installation.

Keep original game files intact. Installation requires a reviewed file plan;
automatic checks do not replace human translation review.

## Guides and documentation

[English](guide/en.md) · [Türkçe](guide/tr.md) · [Deutsch](guide/de.md) ·
[Français](guide/fr.md) · [Español](guide/es.md) · [Português](guide/pt.md) ·
[Русский](guide/ru.md) · [简体中文](guide/zh.md)

For more detail, see the [documentation index](docs/README.md),
[installation guide](docs/installation.md) and [development guide](docs/development.md).

## Future plans

Expand **Unity and Ren’Py** support, and test and implement support for
**Unreal Engine and Godot**. These are planned additions, not current compatibility
claims. See the [roadmap](docs/development.md#deferred-engine-expansion).

## License

UnityTranslator’s own code is licensed under the [MIT License](LICENSE).
Third-party components retain their own licenses; game assets and models are not
included. For redistribution notices and corresponding sources, see
[dependencies](docs/dependencies.md), [native notices](docs/NATIVE-NOTICES.md) and
[source access](docs/SOURCE-ACCESS.md).
