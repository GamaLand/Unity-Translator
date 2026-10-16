# UnityTranslator

A Windows desktop app for translating supported Unity game text with a local AI model.
Extract text, translate it, review the results and prepare a translation patch in one workspace.

## Features

- Local translation through an existing **LM Studio** or **llama.cpp** server.
- Up to **16 parallel requests**, progress tracking, pause, resume and cancellation.
- Glossary and style rules, placeholder/tag checks and plural-aware review.
- Side-by-side editing, saved drafts, translation history and explicit human approval.
- JSON import/export, project backups and shareable patches for supported installations.
- Eight interface languages: **English** (default), Turkish, German, French, Spanish,
  Brazilian Portuguese, Russian and Simplified Chinese.

Game files are read without modification. Supported patch installation adds only new,
non-conflicting files and tracks ownership for removal. Translation projects stay outside
the game folder. The app does not start a game, model or server automatically.

## Game translation languages

Source and target languages are independent of the interface language. The editable
selectors suggest 32 language codes, including `ja` (Japanese), `it` (Italian),
`pt-BR` (Brazilian Portuguese), `zh-CN`, `ru` and `ar`. You can enter other language
tags; `jp` is normalized to `ja`. Choose a source language actually present in the
game. Missing or ambiguous language columns are rejected rather than replaced with
English. The loaded model must support the chosen language pair.

Translation prompts and the default style follow the selected target language.
Existing projects keep their saved languages, approvals and custom style rules;
review any old Turkish-specific style before translating into another language.
The experimental I2 runtime and shareable patches carry both language codes and
verify source text hashes against the selected source column. English can also be
a target. Existing target font/asset references are preserved.

Game compatibility still depends on the supported adapter and matching game build.
Language codes do not add missing fonts or guarantee Arabic shaping, right-to-left
layout or correct language-specific plural forms. Existing plural branches are
preserved and flagged for human review. Specialized negation/condition heuristics
currently cover English-to-Turkish; other pairs still receive format, number,
percentage, unchanged-text and glossary checks. Test a small patch before sharing.

## Install

**Windows package:** if a packaged release is available, download its Windows x64 ZIP,
extract the whole archive into a separate folder and run **UnityTranslator.exe**.
Python is not required for the packaged app. Keep all files from the archive together.

**From source:** install Python 3.12 and [uv](https://docs.astral.sh/uv/), then run in this folder:

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

Start your local model server and load a text model yourself before translating.
Enter its local address and model ID in the app; no cloud account is required.

## Use

1. **Project:** choose the game folder and a separate project folder.
2. **Texts:** scan compatibility, select a supported source and extract text.
3. **Model:** connect to your local server; optionally configure the glossary.
4. **Translate:** run a representative pilot, review it, then translate the remaining text.
5. **Review:** edit and approve translations. Whole-project approval requires two confirmations.
6. **Export / Apply to game:** export your work or review and install a supported patch
   while the game is closed. Launch the game yourself to check the result.

Use **Open existing project** to resume work. Select the interface language from
**Language**, beside **Help**; the selection takes effect on the next app launch and
does not change the project's source or target language.

## Guides

[English](rehber/en.md) · [Türkçe](rehber/tr.md) · [Deutsch](rehber/de.md) ·
[Français](rehber/fr.md) · [Español](rehber/es.md) · [Português](rehber/pt.md) ·
[Русский](rehber/ru.md) · [简体中文](rehber/zh.md)

## Compatibility

This is not a universal Unity patcher. Extraction and installation support depend on the
game's engine version, runtime and localization system. The reference adapter targets
an identified Mono/I2 installation of *Warhammer 40,000: Mechanicus*. In-game application
remains experimental; the reference menu and Turkish glyphs were user-verified, not every
scene or game version. IL2CPP and Unreal installation are not currently supported.

Automated checks cannot guarantee translation meaning. Clean Windows validation remains
pending. Some technical diagnostics retain their original wording. Interface translations
have automated resource checks; native-speaker review is welcome.

## Development and troubleshooting

See [development and safe installation recovery](docs/development.md) for architecture,
checks and loader conflicts. Real game files, models, user projects, local AI instructions
and build outputs are excluded from the public source package.

## License

UnityTranslator's own code is licensed under the [MIT License](LICENSE).
Third-party components retain their own licenses; game assets and models are not included.
See [dependencies](docs/dependencies.md), [native notices](docs/NATIVE-NOTICES.md) and
[source access](docs/SOURCE-ACCESS.md) before redistributing a packaged build.
