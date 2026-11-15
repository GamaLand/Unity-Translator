# Legacy recipient fixtures

Frozen packages built by earlier releases' exporters, so that
`tests/test_recipient_scenarios.py` runs each frozen installer against its own receipts.
All content is synthetic: synthetic games, text stand-ins for executables and runtime
DLLs, and synthetic translations. The two release-candidate game ZIPs instead contain a
128-byte `Synthetic.exe` header stub (`MZ`/`PE` x64 fields, otherwise zero bytes, no
code) written by those revisions' own test recipe. There is no real game data and no
third-party binary.

| Fixture | Source revision | Format | Installer in the ZIP |
| --- | --- | --- | --- |
| `unity-shareable-9ba9495` | `9ba9495` (tag `v0.1.0-rc.6`) | shareable patch format 1 (I2 path), no review phase | `patch.ps1` |
| `unity-shareable-0b83e59` | `0b83e59` (tag `v0.1.0-rc.7`) | shareable patch format 1 (I2 path), no review phase | `patch.ps1` |
| `unity-shareable-556bf5e` | `556bf5e` (0.5.0) | shareable patch format 1 (Krypta path) | `patch.ps1` |
| `renpy-copy-format1-556bf5e` | `556bf5e` (0.5.0) | Ren'Py translated copy, format 1 | `renpy-copy.ps1` |
| `renpy-copy-format2-556bf5e` | `556bf5e` (0.5.0) | Ren'Py translated copy, format 2 (sharded) | `renpy-copy.ps1` |
| `renpy-additive-1e1dfc3` | `1e1dfc3` (tag `v0.7.0`) | Ren'Py additive, format 3 | `renpy-copy.ps1` + `renpy-additive.ps1` |

Each fixture has two files. `<name>.zip` is the exporter's ZIP, byte for byte.
`<name>-game.zip` is the synthetic game folder the package was built for, stored with
fixed timestamps. `index.json` records the SHA-256 of every ZIP, and the tests check
those hashes before they extract anything. `.gitattributes` marks the ZIPs as binary.

## Rebuilding

From the repository root, pick a new work directory:

```
.venv/Scripts/python tests/fixtures/legacy-recipients/build_legacy_recipients.py --work .cache/tests/legacy-build-<new-id>
```

For each revision, the script does the following:

1. Extracts the revision's `src` and `tests` trees with `git archive <rev> src tests`
   into `<work>/<rev>`. It creates no worktree and checks nothing out.
2. Writes a generated pytest module into that revision's `tests` folder. The module uses
   the revision's own fixtures as recipes: `fixture`/`approve` from
   `test_renpy_scripts.py`, `krypta_project` from `test_shareable.py` with its
   synthetic runtime kits (0.5.0), and the release candidates' `shareable` fixture
   (`install_project` from `test_installation.py` with a synthetic I2 runtime kit).
3. Runs it with `PYTHONPATH=<work>/<rev>/src`. The module checks that it imported the
   extracted sources.

The revision's exporters write the ZIPs, and the script copies them here in create-new
mode. It refuses to overwrite an existing fixture, so pass `--output <new directory>`
(created if needed) to compare a rebuild with the stored files. `--revision <rev>` (once
per revision) builds only those fixtures, keeps the other index entries and replaces only
`index.json`. To add a new revision, first add it to `REVISIONS` (and its recipe to
`SNIPPETS`) in the script. Package IDs are random, so a rebuild never matches the stored
hashes byte for byte. The script never starts an installer, a game
or a model.
