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

## Ren'Py native output and translated-copy ZIP

The flows above describe Unity runtimes. Ren'Py uses native files and an explicit
language identifier. **Export approved Ren'Py files** stages approved revisions and
coverage in a new project folder; it performs no game installation.
**Create a Ren'Py installation ZIP**, or `export-renpy-zip --game ... --project ...
--language turkish`, packages the same current approved revisions for a separate
translated-copy installation. Both flush/check drafts and revalidate local sources.
The ZIP is experimental and requires the pinned 8.1.2.23090503 build with one root
game EXE and an unused language namespace. It contains no original game assets,
binaries, model, project data or sender paths.

Native output and the recipient validator preserve symbolic character attributes,
temporary `@` attributes and `nointeract` as fixed source structure. A changed
speaker, attribute or interaction mode rejects the payload. This syntax extension
does not broaden the ZIP's engine/build gate or authorize a new installation.

This exact-version gate describes ZIP runtime installation. The
[broader Ren'Py plan](development.md#broader-renpy-support-planned) separates reader
compatibility from runtime installation evidence. Audited source reading and
native staging can cover other matching behavior contracts; they authorize no new
runtime or installation. Future multi-version installation support must
retain exact recipient build fingerprints, current approvals and reviewed plans.

Large native output uses complete-block shards with fixed numbered names. The
ZIP validates all payloads together, including cross-file ID/string conflicts,
and retains its exact recipient build check. Private repository, AI-tooling or
credential metadata in a development/mod build refuses copy packaging. A clean
reviewed build is required; no new omission is silently added to an original inventory.

The recipient extracts outside the original game and runs `Install.cmd`, selects
the matching original and a separate output parent, then reviews the exact new-file
plan and types `INSTALL`. The plan binds both paths, package hash and every required
build/payload/helper file. Noninteractive `-ReviewOnly -GameFolder ... -OutputParent ...`
prints it; `-ReviewedPlanSha256 <sha256>` accepts only the unchanged plan. An existing
target, changed build, live game, reparse path or malformed native payload blocks
installation. No game is started. The new `UnityTranslatorRenpy-<package-id>` folder
is independent; the original game and original-file inventory are never changed.

Required build files are copied locally with create-new handles, hash/identity/link
checks and a durable write journal. The new-copy scope explicitly omits original
`game/saves`, `game/cache`, root runtime logs and `__pycache__` bytecode. Flat
source-less `.pyc` modules remain required inputs. These omissions do not broaden
any existing original-file inventory exclusions. Allow space for a full game copy;
the inspected Invulnerable build needs about 1.05 GB for 1,204 required build files.

The installed copy's `Play-Translated.cmd` is an explicit user launch action. It
checks the copy, selects the package language through `RENPY_LANGUAGE` and places
new saves/logs inside the copy. Original progress is preserved in the original and
is not imported automatically. Native compilation and the game-local persistent
mirror remain confined to the copy. The installer injects no startup Python.

Keep the extracted package for `Remove.cmd`. Its separate reviewed plan removes
only receipt-bound copy files whose current identity, single-link status and hash
match, using checks on the deletion handle. Modified files, unknown runtime data,
compiled sidecars and receipts are retained; the result reports that runtime data
remains. It never promises an empty directory or deletes original game files.
Interrupted installations retain a start marker and flushed journal for recovery;
they cannot be relaunched or overwritten as completed installations. New package
revisions create a new independent copy; existing-copy updates and save migration
are not implemented. See the [Ren'Py design](development.md#renpy-native-template-integration).

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
