# Development and safe installation recovery

## Architecture

The Python core owns the SQLite project store, revision history, model requests and
installation receipts. PySide6 Widgets is the desktop interface. An independent asyncio
thread performs network work; window minimization does not pause translation. Unity
extraction runs in a separate worker process. Readers, translation and application adapters
are separate, so extraction support never implies installation support.

The current application adapter is an experimental, fingerprint-matched Mono/I2 adapter.
It never rewrites original game assets. A separate portable runtime variant supports
shareable packages without requiring UnityTranslator or a model on the recipient's machine.
Runtime components are not part of the source repository; their build/preparation tools,
hash catalogs and license/source handling live in `tools/` and `adapters/`.

## Develop and check

```powershell
uv sync --locked --extra ui
uv run --extra ui python tools/check.py
uv run --extra ui python tools/check.py --with-dotnet
uv build
uv run python tools/check_distribution.py
```

The C# checks require the compatible .NET SDK indicated by the test projects. Tests use
synthetic fixtures, not installed games or real translation projects. The check script
allocates a new temporary directory inside `.cache/`. Never point pytest's `--basetemp`
at a folder containing work you want to keep. A local pass is not a claim that remote CI
or a clean Windows installation has been tested.

## Existing loader files block installation

An installation may be owned by an older project even if the current project shows no
installed patch. `winhttp.dll` and `doorstop_config.ini` are shared game-root targets;
their presence must block a second installation. Never overwrite or blindly delete them.

1. Close the game and the application that owns the affected project.
2. Read the older project's `artifacts/deployment.json`, original inventory and recorded
   plan. The INI's runtime path is a clue to the old workspace, **not ownership proof**.
3. Verify game identity, the saved plan, each file's SHA-256, device/file identity and
   single-link status. Verify the original game hashes and that the game is closed.
4. Use that project's **Apply to game → Disable translation and remove added files**.
   The underlying `DeploymentService.uninstall(user_action=True)` removes only owned,
   unchanged additions. Modified/replaced files are preserved and require investigation.
5. Reopen the new project and prepare a fresh plan; the user reviews installation separately.

If the files belong to another mod, use that mod's removal procedure. Missing ownership
records are not permission to claim or delete the files.

### A failed attempt already captured the old loader in its original inventory

Do not delete `original-inventory.json` and rescan blindly: that would redefine originals
and could hide real game changes. Preserve the complete old inventory as a separate backup.
If a prior trusted, game-matched inventory exists, verify every original hash and the exact
set difference. Only proven program-owned additions may be separated out. Carry over only
the specific variable-file rules already approved by the user; never exclude a whole Logs
folder or reset hashes for changed game assets. Explain the exact repair and obtain explicit
approval before changing this protection boundary.

Hold the project lock during repair, remove the old additions through their original receipt,
restore the verified inventory atomically and record the backup path and before/after hashes.
Keep translation tables, drafts, revisions and approvals untouched. Compare logical database
table contents against a consistent snapshot; SQLite may create or remove empty WAL/SHM
sidecars without changing those records. Finally verify originals again and test preparation
against an isolated project copy. Do not launch the game or install the new patch as part of
inventory repair.

`InstallationSession.prepare()` now checks conflicting loader targets **before** staging
runtime files or capturing an original inventory. Regression tests ensure foreign files
remain unchanged and no baseline is created on conflict.

## Interface translations

English source messages are wrapped in `tr(...)`. Eight UTF-8 JSON catalogs live in
`src/unitytranslator/resources/locales/`; placeholders such as `{p1}` and Qt progress
tokens must remain exact. Catalogs are bundled and work offline. Do not translate game
text, model IDs, paths, language codes or persisted approval protocol values as interface
labels. Whole-project approval displays a localized phrase but submits an invariant internal
confirmation. The UI preference is stored outside the project in the user's app settings.

Use `UNITYTRANSLATOR_UI_LANGUAGE=en` (or another supported code) for an isolated language
test. `UNITYTRANSLATOR_CONFIG_HOME` can direct preference storage to a test directory.
Legacy UI regression fixtures explicitly select Turkish; separate tests verify the English
default and all eight catalogs. Language changes take effect after reopening the app.

## Publishing source

Keep `.local/`, `.cache/`, game/model files, generated binaries and secrets out of commits.
Local AI instruction/specification files remain available in the workspace but are ignored
and excluded from source distributions. `.gitignore` does not untrack files already committed:
review the Git index before pushing and remove accidentally tracked private files from it.
Do not publish an old Git history containing private data. Review the source archive with
`tools/check_distribution.py`; the repository-ready ZIP is source only, not a Windows release.
