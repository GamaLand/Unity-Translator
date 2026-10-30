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
   Select 1–36 parallel requests according to server capacity. Minimized translation continues.
   Pause stops new requests and waits for active ones; cancel stops client tasks.
6. **Review:** compare source and translation, save edits, then approve. Draft autosave
   does not grant approval. Page approval affects selected eligible records on that page.
   **Approve all translations** covers the project: review the count/warnings, acknowledge,
   then type the exact displayed phrase and press the final button. Either step can be
   cancelled. Drafts and format failures are excluded; a changed preview aborts the operation.

## Back up, install and share

For the pinned Krypta FM build, use source `en` and target `tr`. Profile 2 covers 449 fields from 34 TextAssets and one journal grid; two sources and other UI/image text remain outside the profile. Existing identities and approvals are preserved.

After review and approval, close the game and use **Apply to game** to prepare and review the two-file plan (`winhttp.dll`, `doorstop_config.ini`). The experimental runtime stays in the separate project; original game files are not replaced. Remove additions through the same project. Text-payload export is data only, and shareable installation ZIPs also support the pinned Krypta en-to-tr build. Recipients run Install.cmd, review the file plan and type INSTALL; Uninstall.cmd removes unchanged owned additions. Portable install/remove has synthetic checks; a separate in-game check of this portable combination is deferred. Startup/menu, options, transition into gameplay, pause and subtitles were observed. Other screens, language switching and text layout need manual review; a long settings label can overlap its explanation.

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

In advanced model settings, you can optionally disable model reasoning for LM Studio requests. This may leave more output budget for the translation. Support depends on the loaded model/server; an unsupported option can stop the job. Defaults and server-wide settings are preserved.

## Engine inspection and Ren'Py translation

In Texts, select the engine, scan and choose an input. Native templates under
`game/tl/<language>/*.rpy` are read as a complete language folder. Original `.rpy`,
verified `_ren.py` and script-bearing RPA-3.0 inputs use audited source behavior
contracts, compared against Ren'Py 8.1.2 and 8.3.6. Version evidence alone does not
grant support. Large sets and disjoint loose/archive containers are supported;
overlapping paths or source basenames are refused. The static reader covers single-line
dialogue with character and temporary `@` attributes, `nointeract`, explicit literal
`_()` keys and menu choices/captions. Menu dialogue must precede choices and cannot
mix with captions. Voice/nvl groups, multiline dialogue, dynamic text, compiled-only
input and image labels remain outside scope. Check reported exclusions. Game code
is never executed during extraction. Large exports can contain multiple numbered
files; keep the complete exported tree together.

Installation ZIP support remains limited to Ren'Py `8.1.2.23090503`; private repository, AI-tooling or credential metadata blocks copy packaging.

Use the existing model connection, pilot, drafts and human review. Old template
translations appear read-only in history and are never approved automatically.
Review context includes the member file, line, native block and speaker. Source and
target languages are independent of the interface language.

After human approval, enter an explicit Ren'Py target identifier, for example
`turkish` for a `tr` project. Finish or discard drafts first. Native-file export
stages approved files and a coverage manifest in the project; it does not install.
Unapproved keys are omitted and conflicting approved global string mappings block
export.

**Create a Ren'Py installation ZIP** supports the pinned build with a single root
game executable. The ZIP contains reviewed translations and a fixed Windows
installer, not game assets. Extract it outside the original game, run `Install.cmd`,
select the matching original game and a separate output parent, and review the
exact create-new file plan. Installation prepares a full separate translated copy
and needs additional disk space. It never starts the game or replaces original files.

Use `Play-Translated.cmd` in the new copy to select the package language and play.
Original saves, logs and caches are not copied; the copy starts with separate saves.
The recipient needs neither Python nor a model nor UnityTranslator.
Keep the ZIP for `Remove.cmd`: it removes only unchanged owned copy files.
Changed or runtime-created files, sidecars, saves and the removal receipt are
preserved. Removal does not promise an empty copy directory.

The CLI uses the same checks:

```powershell
unitytranslator extract --game C:\Game --project C:\Translations --source game/archive.rpa --engine renpy
unitytranslator export-renpy --game C:\Game --project C:\Translations --language turkish
unitytranslator export-renpy-zip --game C:\Game --project C:\Translations --language turkish
```

Installation into the original game folder remains unsupported. A staged file or
successful model response does not prove font coverage, layout or every game scene.

If a pilot report still shows a running job, refresh the report after it stops. A cancelled pilot can be reviewed when the full required sample was attempted and completed results exist. Saving the evaluation unlocks bulk work for matching settings and sources; it does not approve translations.

After pilot review, saved glossary/style changes apply to new requests without another pilot. Active requests finish with their original rules; existing translations are unchanged. Review affected records and regenerate them explicitly if needed. Use reviewed pilot settings restores the model/generation settings while keeping the current saved glossary/style.

In Review, Retranslate records on this page sends up to 200 records from the visible filtered page through the shared translation queue using the current model settings and saved glossary/style. A matching reviewed pilot is required. Drafts and active records are excluded. Approved text stays selected; new candidates appear in history. The Translation tab opens to show progress.

In Review, **Bulk actions** can approve nonempty translations exactly identical to their source or return empty translations to Pending. Both actions cover all pages matching the current filters, with a count and examples before confirmation. Clear filters to include the whole project. Drafts, queued/processing records and existing approvals are excluded. Exact copies may still be untranslated sentences: approval is your explicit decision. Returning empty translations preserves history and sends no model requests; start a bulk job from Translate afterward, using the usual reviewed-pilot gate.
