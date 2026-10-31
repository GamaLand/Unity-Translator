# Installation and original-file protection

## Separate preparation from installation

Extraction reads game files. Translation, reports, drafts, exports and runtime staging
write into a separate local project directory. Project and game roots must not overlap.
Preparing a patch is not permission to install it or proof of in-game compatibility.
The model never receives filesystem access and its output is always treated as data.

The application never launches a game. Before installation/removal it queries the
selected game's process state; an inaccessible or uncertain identity is not a positive
closed-game result. A prior observation is not permanent authorization.

## Project-managed runtime

The normal installation flow stages an external runtime under the translation project,
including `BepInEx/core/BepInEx.Preloader.dll` and
`BepInEx/plugins/UnityTranslator/translation.json`. Two new, non-conflicting game-root
files (`winhttp.dll` and `doorstop_config.ini`) point to that runtime. The project runtime
must stay at its recorded location. A shareable patch uses a separate layout described
in [Shareable translation patches](#shareable-translation-patches).

Only current, explicitly approved translation revisions can be packaged. Preparation
checks source revisions, source fingerprints, runtime-kit hashes, matching game
references and the immutable original-file inventory. A changed record, runtime or file
plan invalidates the review. The UI requires the concrete plan and experimental scope
to be reviewed before writing any game-root addition.

## File ownership and removal

Original game files are never overwritten, renamed or deleted. Installation uses
create-new writes and a durable plan/receipt. Removal checks the receipt, file identity,
single-link status and content hash, and deletes only the unchanged additions it owns.
Modified/replaced additions are preserved for investigation. Missing receipts do not
prove ownership. A backup does not authorize replacing an original file.

Original hashes are verified before/after activation and removal. A user may select
one explicit mutable log path for separate tracking; there are no automatic wildcard
or directory-wide exclusions. Never hide a changed asset by expanding exclusions or
resetting the baseline. Reparse/network/path-escape checks remain part of the boundary.

## Existing loader conflicts

Another project or another mod may already own the shared loader targets. Preparation
checks these targets before staging runtime files or capturing an original inventory.
Never overwrite them, delete them blindly or treat them as original files in a new
baseline. The INI's path is a clue to the owning project, not ownership proof.

1. Close the game and inspect the original project's deployment receipt and inventory.
2. Verify the game identity, recorded paths, content hashes and file identities.
3. Remove the old installation through its owning project's removal action.
4. Preserve files belonging to a different mod and use that mod's removal procedure.
5. Prepare and review the new installation separately.

If an earlier failed attempt captured an old loader as original, do not delete the
inventory and rescan. Preserve it as a backup, compare with a prior trusted inventory,
verify every original hash and the exact difference, and repair only proven ownership
mistakes with explicit authorization. Hold the project lock and preserve all translation
revisions, drafts and approvals. Compare logical SQLite table contents; empty WAL/SHM
sidecars are not proof that translation data changed.

## Krypta FM experimental installation

For the pinned English-to-Turkish build, approve current revisions, close the game and
use **Apply to game** to prepare an exact plan. Review the two new root files,
`winhttp.dll` and `doorstop_config.ini`, then approve installation. Runtime, translation,
license and source files remain in the separate project. Launch the game yourself.
Use the same project to remove only unchanged owned additions. Never replace a conflicting loader.

Startup/menu, options, transition into gameplay, pause and subtitles were observed with
449 approved translations. The user accepted this limited scope; journal/forum display,
language switching, reload, all scenes and translation quality remain manual checks.
Known limits include an overlapping long settings label and English control-help text
outside the profile. Shareable recipient ZIPs are available for this pinned en→tr
build through **Export**; see [Shareable translation patches](#shareable-translation-patches). The portable
loader/plugin combination has synthetic checks, without a separate game launch.
A staged text export
does not itself install anything or authorize installation.

## Limits

Static loader audits and synthetic rollback tests cannot prove every native or game
callback side effect. The fingerprint-matched adapter remains experimental. Never
infer installation support from extraction support or from a successful model response.

## Shareable translation patches

Use **Export -> Create a shareable translation ZIP** to package current approved
translations for a supported, fingerprint-matched installation. The recipient does
not need UnityTranslator, Python, LM Studio or the model used for translation.

### Recipient use

1. Extract the entire ZIP into a separate directory.
2. Close the game, run `Install.cmd` and select its installation directory.
3. Review the exact new-file plan and hashes, then type `INSTALL` to approve it.
4. Launch the game normally yourself.
5. To remove the patch, close the game and run `Uninstall.cmd`.

`Kur.cmd` and `Kaldir.cmd` are retained as legacy aliases. The installer uses built-in
Windows PowerShell/.NET, does not download code and never starts the game.

### Layout and ownership

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
[Project-managed runtime](#project-managed-runtime). Copying its two root files alone does not create a
portable patch. Moving a game requires removing and reinstalling its owned patch.

### Compatibility limits

Both the identified I2 build and the pinned Krypta FM English-to-Turkish build are
supported by the exporter. Other source adapters/profiles and mixed source sets are
rejected. Export freezes current approved revisions without drafts, validates source
fingerprints and kits, then rechecks them before publishing the ZIP. It does not
install anything into the author's game and does not change approval history.

Krypta packages combine the unchanged scoped plugin and shared core with the
separately built portable preloader. Shared component hashes must agree. Both kits'
matching licenses and source archives accompany the package in `support/krypta/`
and `support/portable/`; `support/RUNTIME-COMPOSITION.json` identifies the actual
plugin/loader combination. The I2 plugin is not installed in a Krypta package.
This combination is covered by synthetic recipient checks, without a separate
in-game observation. Earlier Krypta gameplay observation used the same plugin with
the external preloader. Remaining display/lifecycle checks are manual.

For noninteractive local verification, `patch.ps1 -ReviewOnly -GameFolder ...`
returns the concrete plan without game writes. Installation with
`-ReviewedPlanSha256 <sha256>` accepts only that exact current plan for that game path.
The normal CMD launchers show the plan and request interactive approval.

The portable preloader is separately built/cataloged. Current game compatibility is
experimental and fingerprint-specific. Synthetic install/remove checks are not proof
of every in-game font, language, scene or callback behavior. Check a representative
screen and dynamic text before distributing a patch. No model, project database,
proprietary game DLL or original game asset belongs in the distribution.

## Ren'Py native output and installation ZIP

**Export approved Ren'Py files** stages approved text and coverage in a new project
folder. It does not install anything. **Create a Ren'Py installation ZIP**, or
`export-renpy-zip --game ... --project ... --language turkish`, packages the same
current approved revisions for additive installation. Finish or discard drafts
first. The ZIP remains limited to the matching pinned 8.1.2.23090503 build with one
root game EXE and an unused target language namespace. Readable sources alone do
not establish installation support for other builds.

### Install without copying the game

1. Close the game and extract the ZIP outside its folder.
2. Run `Install.cmd` and select the original game folder once.
3. Review the exact create-new file plan and type `INSTALL`.
4. Explicitly launch `Play-Translated.cmd` in the game folder to select the package language.

Only approved `game/tl/<language>/*.rpy`, a small launcher and per-package ownership
records are added. No game assets are copied or distributed. No existing file is
replaced, so no original-file backup is needed; an occupied path or language
namespace refuses installation. Package/source hashes, native grammar and token
structure, build fingerprints and script/archive membership are checked again at
installation. The plan binds the game directory identity, manifest and every new
payload/helper/generated-record path. `-ReviewOnly -GameFolder ...` prints it;
`-ReviewedPlanSha256 <sha256>` accepts only that unchanged plan.

Writes use create-new handles, held parent directories, an immutable start marker,
a flushed identity journal and a final receipt. Incomplete additions are retained
for recovery; neither installation nor removal starts the game. There is no second
output-folder prompt and no full-game disk-space requirement.

### Gameplay and removal

The launcher sets `RENPY_LANGUAGE` for that process and uses normal game saves.
The original language remains available; no startup Python is injected. Playing
may update saves, caches, logs, paired Python bytecode and compiled translation
sidecars normally. These runtime changes are not backed up or rolled back by the
patch. Do not restore old saves/caches as an uninstall operation.

Keep the extracted ZIP. Close the game, run `Remove.cmd`, select that same game
folder, review the removal plan and type `REMOVE`. Only unchanged receipt-owned
translation files and the launcher are removed, with directory identity, single-link
and file identity/hash checks. Modified, linked or unknown files are preserved;
partial removal is reported as such. Small audit/support records remain under
`.unitytranslator/renpy-additive/<package-id>`.

**Compiled sidecars:** Ren'Py may create `.rpyc` files beside installed translations.
A same-name file or matching source footer is not sufficient ownership evidence.
If those unowned sidecars exist, automatic removal stops before deleting any patch
files, because orphaned `.rpyc` files can keep translations active. The reviewed
plan names the exact blockers. Review/remove only those generated translation
sidecars manually, then rerun removal; never delete unrelated game `.rpyc` files.
An empty owned language directory can be removed by identity; unknown contents
are retained. Existing files are never adopted or overwritten during updates.

New format-3 packages use this additive route. Existing format-1/2 ZIPs keep their
original separate-copy behavior and must be removed with their own installer.
The legacy Python `export_copy_package` API is retained. Additive recipient checks
are synthetic Windows tests; actual original-folder gameplay and sidecar cleanup
have not been verified on a real game. Fonts, layout and full-game text coverage
remain separate compatibility limits.

### Historical copy-pilot observations

The selected Invulnerable reference uses image assets for its active main-menu
labels; a string-table pilot must target a confirmed text consumer, such as the
preferences screen. Initial runtime experiments require a separate full copy with
isolated saves/logs and a reviewed exact addition plan. Ren'Py may compile sidecars
and update existing cache files, so an experiment on a copy does not authorize
installation into the original build or establish removable sidecar ownership.

The reviewed Invulnerable one-label experiment confirmed loading and user-observed
rendering on its isolated copy. Its post-exit audit found a new compiled sidecar and
changes to existing copied script/screen caches, local persistent data and engine
Python bytecode. `--savedir` did not prevent the game's local persistent mirror.
The original build's complete 1,347-file inventory remained unchanged. Preserve
the trial, reviewed plan and receipt; that earlier manual experiment did not verify
the new ZIP installer and did not pass the original-root no-write gate.
