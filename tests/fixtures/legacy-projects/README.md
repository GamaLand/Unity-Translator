# Legacy project fixtures

Frozen project databases written by earlier revisions' own code, so that
`tests/test_frozen_projects.py` and `tests/test_migrations.py` open real old schemas with
the current `ProjectRepository`. All content is synthetic: synthetic Unity-style records
(`UI/start`, `UI/options`, ...) or a short synthetic Ren'Py script, Turkish test
translations and a local model address that is never contacted. There is no real game
data, user path or third-party binary.

| Fixture | Source revision | Schema | Build | Recipe |
| --- | --- | --- | --- | --- |
| `schema1-9ba9495-unity` | `9ba9495` (tag `v0.1.0-rc.6`) | 1 | stepwise | Unity-style records |
| `schema2-9ba9495-unity` | `9ba9495` (tag `v0.1.0-rc.6`) | 2 | stepwise | Unity-style records |
| `schema3-9ba9495-unity` | `9ba9495` (tag `v0.1.0-rc.6`) | 3 | stepwise | Unity-style records |
| `schema4-9ba9495-unity` | `9ba9495` (tag `v0.1.0-rc.6`) | 4 | release | Unity-style records |
| `schema4-0b83e59-unity` | `0b83e59` (tag `v0.1.0-rc.7`) | 4 | release | Unity-style records |
| `schema5-e8d768c-unity` | `e8d768c` (0.4.0) | 5 | release | Unity-style records |
| `schema5-556bf5e-renpy` | `556bf5e` (0.5.0, tag `Beta`) | 5 | release | Ren'Py script |
| `schema5-1e1dfc3-renpy` | `1e1dfc3` (tag `v0.7.0`, package 0.5.0) | 5 | release | Ren'Py script |
| `schema6-41ea1da-renpy` | `41ea1da` (0.6.0) | 6 | release | Ren'Py script |
| `schema6-9088210-unity` | `9088210` (0.6.1) | 6 | release | Unity-style records |
| `schema6-bcfa3e2-renpy` | `bcfa3e2` (0.7.0) | 6 | release | Ren'Py script |

Each fixture has two files. `<name>.sqlite3` is the revision's `project.sqlite3` and
`<name>.project.json` is its `project.json` manifest. `index.json` records the SHA-256 of
both, the revision's package version and tags, and the values to expect after migration:
project identity, every unit's source revision, work status, version, current and
approved revisions, translation history, editor drafts, jobs, glossary versions, source
descriptors and job context bindings. The tests check the hashes, copy the files to a new
temporary directory and only then open them.

## Content

The Unity-style recipe ingests four records, translates them through a prototype job,
approves one model translation, edits and approves a second record manually, and saves a
glossary. A later session ingests a changed source (one record changed, one removed),
leaves a second job paused after a failed attempt and saves an editor draft.

The Ren'Py recipe extracts a synthetic `game/script.rpy` through the revision's own
`extract_to_project`, runs a prototype job (with the `source-window-v1` dialogue context
where the revision has it, which fills `job_context_sources`), approves a model and a
manual translation and saves a glossary. A later extraction changes one line, then a
paused job and an editor draft follow, as above.

Each step uses only what that schema has. Installation receipts are files under
`artifacts/`, not database rows, so these fixtures have none; the legacy recipient
fixtures cover receipts.

## Schemas 1-3

No release left a project at schemas 1, 2 or 3; every release migrates to at least 4 on
open. These three are built by the oldest revision, `9ba9495`, with its own
`ProjectRepository`: `schema-v1.sql` is applied by its constructor and its own
`migrate()` applies the numbered scripts up to the target schema, after which further
migrations are skipped. They are populated through its repository's SQL-level API,
where the schema allows it:

- Schema 1 has no job, policy or settings tables. Model translations are stored with
  `candidate()` directly, approvals use the same `UPDATE` as the revision's `approve()`,
  and the revision's `recover_interrupted()`, which needs the schema-2 job tables, is
  skipped.
- Schema 2 has jobs but no `candidate_only` column or policy impacts. Jobs are written
  with SQL that mirrors the revision's `JobStore` queue steps, and the glossary version
  is written without impacts.
- Schema 3 uses the revision's `JobStore`, `PolicyStore` and `approve()`.

These databases therefore contain metadata of `9ba9495` (for example its review-check
version) at an earlier schema.

## Normalization

The only change after the revision closes its project is that `project.game_path` is set
to `<synthetic-game>`, with `secure_delete` on, so that no build path remains. Before
that, the build folds a remaining WAL file into the database as its last connection. The
databases stay in WAL journal mode, as the application leaves them. The build fails if a
database or manifest still contains the work directory, the repository path or the home
directory.

## Rebuilding

From the repository root, pick a new work directory:

```
.venv/Scripts/python tests/fixtures/legacy-projects/build_legacy_projects.py --work .cache/tests/legacy-projects-build-<new-id> --output .cache/tests/legacy-projects-out-<new-id>
```

For each revision, the script extracts `git archive <rev> src tests` into
`<work>/<rev>`, writes a generated pytest module into that revision's `tests` folder and
runs it with `PYTHONPATH=<work>/<rev>/src`. The module checks that it imported the
extracted sources and uses the revision's own `draft` and Ren'Py `fixture` test helpers.
It creates no worktree and checks nothing out. The script writes in create-new mode, so
`--output` must not already hold fixtures. Project and record IDs and timestamps are new
on every run, so a rebuild never matches the stored hashes; replace all fixtures and
`index.json` together. The script never starts a game, an installer, a model server or a
download.
