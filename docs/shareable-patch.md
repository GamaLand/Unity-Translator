# Shareable translation patches

Use **Export -> Create a shareable translation ZIP** to package current approved
translations for a supported, fingerprint-matched installation. The recipient does
not need UnityTranslator, Python, LM Studio or the model used for translation.

## Recipient use

1. Extract the entire ZIP into a separate directory.
2. Close the game, run `Install.cmd` and select its installation directory.
3. Review the result and launch the game normally yourself.
4. To remove the patch, close the game and run `Uninstall.cmd`.

`Kur.cmd` and `Kaldir.cmd` are retained as legacy aliases. The installer uses built-in
Windows PowerShell/.NET, does not download code and never starts the game.

## Layout and ownership

The package adds `UnityTranslatorPatch/`, `winhttp.dll` and `doorstop_config.ini`.
The runtime and approved `translation.json` live below
`UnityTranslatorPatch/BepInEx/`. The INI is generated on the recipient's computer and
points to that owned runtime, not to the author's project path. Component licenses,
sources and notices accompany the bundle.

Installation refuses existing targets, wrong game hashes, unsafe paths and a running
or uncertain game process. It never overwrites an original language asset. Removal
checks recorded ownership, file identity, single-link status and hashes; modified
files are preserved. A prior project-managed trial must be removed through its owning
project before testing a shareable installation on the same game.

The normal **Apply to game** action uses an external project runtime instead; see
[installation.md](installation.md). Copying its two root files alone does not create a
portable patch. Moving a game requires removing and reinstalling its owned patch.

## Compatibility limits

The portable preloader is separately built/cataloged. Current game compatibility is
experimental and fingerprint-specific. Synthetic install/remove checks are not proof
of every in-game font, language, scene or callback behavior. Check a representative
screen and dynamic text before distributing a patch. No model, project database,
proprietary game DLL or original game asset belongs in the distribution.
