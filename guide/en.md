# UnityTranslator user guide

## Install and choose a language

On Windows x64, extract the **entire** application ZIP to a separate folder and run
`UnityTranslator.exe`. The packaged app needs no Python installation. For source setup:

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

The interface starts in English. **Language**, next to **Help**, offers eight languages;
your choice applies when you reopen the app. It does not change the game's translation language.

## Translate

1. **Project:** select the game folder and a separate project folder. Choose source and
   target language codes. Use **Open existing project** to resume an existing workspace.
2. **Texts:** run the read-only compatibility scan, choose a supported source and extract text.
   Extraction and game installation have separate support checks.
3. **Model:** start LM Studio or llama-server and load your model yourself. Enter the
   local server address and model ID, then test the connection. The app does not start them.
4. **Glossary:** optionally enter preserved names, preferred terms and category styles.
5. **Translate:** run and review the representative pilot before starting the bulk job.
   Select 1–16 parallel requests according to server capacity. Minimized translation continues.
   Pause stops new requests and waits for active ones; cancel stops client tasks.
6. **Review:** compare source and translation, save edits, then approve. Draft autosave
   does not grant approval. Page approval affects selected eligible records on that page.
   **Approve all translations** covers the project: review the count/warnings, acknowledge,
   then type the exact displayed phrase and press the final button. Either step can be
   cancelled. Drafts and format failures are excluded; a changed preview aborts the operation.

## Back up, install and share

**Export** offers JSON exchange and a project data backup. Keep backups outside the game.
For a supported installation, close the game, open **Apply to game**, prepare a plan,
review the new files and approve installation separately. Launch the game yourself to
check glyphs, layout and meaning. Installation remains experimental.

Remove additions through the same project and screen. Never overwrite conflicting
`winhttp.dll`/`doorstop_config.ini` files or delete the original inventory. Open the
owning old project to remove its unchanged additions; see [developer recovery](../docs/installation.md).

A shareable ZIP contains approved translations and the required runtime. Its recipient
extracts the ZIP and runs `Kur.cmd` to select the matching game folder; `Kaldir.cmd`
removes owned, unchanged additions. The recipient needs no model or UnityTranslator.
Keep the included license/source materials. Not every Unity game is supported; automated
checks do not guarantee translation quality. Some technical diagnostics retain original wording.


Game translation languages: source and target are separate from the interface language. Enter ja for Japanese, it for Italian or pt-BR for Brazilian Portuguese; other language codes can also be entered. The source must exist in the game. Missing or ambiguous source columns are rejected. The model must support the pair. Existing project languages, approvals and custom styles are preserved; review old language-specific styles. Check fonts, RTL layout and plural forms in a small patch before sharing. English can also be a target.
