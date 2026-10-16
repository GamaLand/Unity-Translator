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
in [shareable-patch.md](shareable-patch.md).

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

## Limits

Static loader audits and synthetic rollback tests cannot prove every native or game
callback side effect. The fingerprint-matched adapter remains experimental. Never
infer installation support from extraction support or from a successful model response.
