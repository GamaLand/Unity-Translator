# UnityTranslator for Windows

Extract the complete application ZIP into its own folder and run `UnityTranslator.exe`.
Keep the included DLLs, runtime kits, notices and guides together. You do not need Python
or a compiler to run this standalone package.

The default interface language is English. Select **Language**, beside **Help**, to
choose English, Turkish, German, French, Spanish, Brazilian Portuguese, Russian or
Simplified Chinese. The saved preference takes effect the next time you open the app;
it does not interrupt an active job or change the project's language pair.

1. Select a game folder and a separate project folder, then create the project.
2. Scan compatibility and extract text from a supported source.
3. Start your own local LM Studio/llama.cpp server, load a model and enter its address/ID.
4. Optionally set glossary and style rules. Translate and review a representative pilot.
   Saved rule changes apply to new requests without repeating the pilot; active
   requests and existing translations retain their original rules and text.
5. Start the remaining translation, then edit and approve results in Review.
   **Retranslate records on this page** queues up to 200 visible filtered records
   using a matching reviewed pilot. Drafts are excluded and approved text is preserved.
6. Export a backup/JSON or prepare and review a supported installation while the game is closed.

Use **Open existing project** to continue. Ctrl+O opens a project; Ctrl+F searches Review;
Ctrl+S saves the current edit. Minimized translation continues. Select 1–36 parallel
requests according to your server's capacity. Pause waits for active requests; cancellation
stops client tasks. A generation request may wait up to 30 minutes including the server queue.

Whole-project approval requires acknowledging scope/warnings and then typing the displayed
phrase before pressing the final confirmation button. Drafts and format failures are excluded.
The operation aborts without partial approval if the reviewed candidate set changes.

For complete instructions, open **Help → User guide** or choose a file in `guide/`:
`en.md` (English), `tr.md` (Türkçe), `de.md` (Deutsch), `fr.md` (Français),
`es.md` (Español), `pt.md` (Português), `ru.md` (Русский), `zh.md` (简体中文).

Conflicting loader files must not be overwritten or blindly removed. See `development.md`
in the Windows package, or [the developer guide](development.md) in the source repository.
Remove unchanged owned additions through the project that installed them. Never reset the
original inventory to bypass a conflict.

Game application is experimental and not universal Unity support. Launch the game yourself
to check the result. Keep project runtime files in place while a normal installation is
active; use the shareable ZIP for distribution to recipients without the app/model.
Some technical diagnostics retain original wording. Automatic checks do not guarantee quality.

The application's own code is MIT licensed. See `SOURCE-ACCESS.md`, `NATIVE-NOTICES.md`,
`LICENSES`, the dependency-source archives and the runtime-kit notices before redistribution.


Game translation languages are separate from the interface. Source/target boxes
suggest 32 codes and accept custom tags: ja = Japanese, it = Italian, pt-BR = Brazilian
Portuguese. The source must exist in the game and the model must support the pair.
Existing project settings and styles are preserved. Check fonts, RTL layout and
plural forms before distributing a patch. Shareable ZIPs include Install.cmd and
Uninstall.cmd; the recipient does not need this application or a model.

In Review, **Bulk actions** works across all pages matching the current filters.
Preview and confirm exact-source approval or return empty translations to Pending;
the latter preserves history and leaves starting a translation job to you.

New Ren'Py installation ZIPs select the original game folder once and add only
approved text, a launcher and ownership records; the game is not copied. Normal
saves are used. See the ZIP's README and [installation guide](installation.md)
for collision checks, removal and generated `.rpyc` sidecar limits.
