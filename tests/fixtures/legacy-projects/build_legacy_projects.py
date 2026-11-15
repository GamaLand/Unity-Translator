"""Rebuild the frozen legacy project databases from earlier release sources.

Synthetic data only. Each revision's ``src`` and ``tests`` trees are extracted with
``git archive`` into a new work directory, and a generated pytest module populates a
project through that revision's own repository, job, policy, draft and extraction code.
Schemas 1-3, which no release left as final, are built by the oldest revision with its
own migrations stopped at that schema. No game, installer, model or download is started.
"""

import argparse
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tomllib
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = "<synthetic-game>"
# (revision, recipe, schema the build must leave, migration cap for stepwise builds)
FIXTURES = (
    ("9ba9495", "unity", 1, 1),
    ("9ba9495", "unity", 2, 2),
    ("9ba9495", "unity", 3, 3),
    ("9ba9495", "unity", 4, None),
    ("0b83e59", "unity", 4, None),
    ("e8d768c", "unity", 5, None),
    ("556bf5e", "renpy", 5, None),
    ("1e1dfc3", "renpy", 5, None),
    ("41ea1da", "renpy", 6, None),
    ("9088210", "unity", 6, None),
    ("bcfa3e2", "renpy", 6, None),
)

RECIPE = '''"""Generated legacy project builder; synthetic data only; starts no game or model."""

import gc
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, fields
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from test_repository import draft

import unitytranslator
import unitytranslator.repository as repository_module
from unitytranslator.domain import GenerationProfile
from unitytranslator.editor_drafts import EditorDraftStore
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.jobs import JobStore
from unitytranslator.policy import GlossaryRule, PolicyStore
from unitytranslator.repository import ProjectRepository, canonical, now

OUT = Path(os.environ["UT_LEGACY_OUT"])
SOURCE = Path(os.environ["UT_LEGACY_SOURCE"]).resolve()
SPECS = json.loads(os.environ["UT_LEGACY_SPECS"])

UNITY_FIRST = {"UI/start": "Start", "UI/options": "Options", "UI/quit": "Quit",
               "UI/credits": "Credits"}
UNITY_SECOND = {"UI/start": "Start", "UI/options": "Settings", "UI/quit": "Quit"}
RENPY_FIRST = (
    'define e = Character(_("Example"))\\n\\n'
    'screen preferences():\\n    label _("Display")\\n\\n'
    'label start:\\n    e "Hello there."\\n    e "How are you?"\\n    "Narration."\\n'
    '    return\\n'
)
RENPY_SECOND = RENPY_FIRST.replace("How are you?", "How are you today?")
TEXTS = {
    "Start": "Başla", "Options": "Seçenekler", "Quit": "Çık", "Credits": "Emeği geçenler",
    "Settings": "Ayarlar", "Example": "Örnek", "Display": "Ekran", "Hello there.": "Merhaba.",
    "How are you?": "Nasılsın?", "How are you today?": "Bugün nasılsın?",
    "Narration.": "Anlatım.",
}


def test_extracted_revision_is_imported():
    assert Path(unitytranslator.__file__).resolve().is_relative_to(SOURCE)


def tables(repo):
    return {row[0] for row in repo.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(repo, table):
    return {row[1] for row in repo.db.execute(f"PRAGMA table_info({table})")}


def row(repo, unit):
    return next(r for r in repo.page() if r["unit_id"] == unit)


def by_source(repo, text):
    return next(r for r in repo.page() if r["source_text"] == text)


def profile(context):
    names = {field.name for field in fields(GenerationProfile)}
    enabled = context and "dialogue_context" in names
    extra = {"dialogue_context": "source-window-v1"} if enabled else {}
    return GenerationProfile("lm-studio", "http://127.0.0.1:1234", "synthetic-model", 8192, **extra)


def api_job(repo, units, prof, *, fail=False):
    store = JobStore(repo)
    job = store.create(units, prof)
    store.start(job)
    while (item := store.claim(job)) is not None:
        run = store.attempt(item, {"synthetic": True})
        if fail:
            store.record_attempt(run, "timeout", 2.5, {})
            store.fail(item, "timeout", retry=True)
            store.pause(job)
            break
        store.record_attempt(run, "accepted", 1.25, {})
        result = {"translation": TEXTS[item["source_text"]], "issues": []}
        assert store.finish(item, result, run)
    store.settle(job)
    return job


def mirrored_job(repo, units, prof, *, fail=False):
    """SQL-level mirror of the revision's JobStore for schema 2 (no candidate_only yet)."""
    job = uuid4().hex
    with repo.transaction() as db:
        db.execute(
            "INSERT INTO jobs(id,kind,status,profile_json,source_fingerprint,created_at,"
            "updated_at) VALUES(?,'prototype','running',?,?,?,?)",
            (job, canonical(asdict(prof)), JobStore(repo).fingerprint(), now(), now()),
        )
        for unit in units:
            current = row(repo, unit)
            db.execute(
                "INSERT INTO job_items(job_id,unit_id,source_revision,work_version,status) "
                "VALUES(?,?,?,?,'queued')",
                (job, unit, current["source_revision"], current["version"]),
            )
    for unit in units:
        current = row(repo, unit)
        version = current["version"] + 1
        run = uuid4().hex
        with repo.transaction() as db:
            db.execute("UPDATE work_items SET status='processing',version=? WHERE unit_id=?",
                       (version, unit))
            db.execute(
                "UPDATE job_items SET status='processing',work_version=?,claim_id=?,"
                "attempts=attempts+1 WHERE job_id=? AND unit_id=?",
                (version, uuid4().hex, job, unit),
            )
            db.execute(
                "INSERT INTO translation_runs(id,job_id,unit_id,source_revision,attempt,"
                "metadata_json,status,elapsed_seconds,created_at) VALUES(?,?,?,?,1,?,?,?,?)",
                (run, job, unit, current["source_revision"], canonical({}),
                 "timeout" if fail else "accepted", 2.5 if fail else 1.25, now()),
            )
        if fail:
            with repo.transaction() as db:
                db.execute(
                    "UPDATE job_items SET status='queued',claim_id=NULL,error_code='timeout',"
                    "work_version=work_version+1 WHERE job_id=? AND unit_id=?", (job, unit),
                )
                db.execute("UPDATE work_items SET status='pending',version=version+1 "
                           "WHERE unit_id=?", (unit,))
                db.execute("UPDATE jobs SET status='paused',pause_requested=1,updated_at=? "
                           "WHERE id=?", (now(), job))
            return job
        assert repo.candidate(unit, current["source_revision"], version,
                              TEXTS[current["source_text"]], "model",
                              {"issues": [], "run_id": run}, [])
        with repo.transaction() as db:
            db.execute(
                "UPDATE job_items SET status='completed',claim_id=NULL,result_revision="
                "(SELECT translation_revision FROM work_items WHERE unit_id=?) "
                "WHERE job_id=? AND unit_id=?", (unit, job, unit),
            )
    with repo.transaction() as db:
        db.execute("UPDATE jobs SET status='completed',updated_at=? WHERE id=?", (now(), job))
    return job


def job(repo, units, prof, *, fail=False):
    if "jobs" not in tables(repo):
        if not fail:  # Schema 1 has no job queue: model candidates are stored directly.
            for unit in units:
                current = row(repo, unit)
                assert repo.candidate(unit, current["source_revision"], current["version"],
                                      TEXTS[current["source_text"]], "model",
                                      {"model": "synthetic-model"}, [])
        return None
    if "candidate_only" in columns(repo, "job_items"):
        return api_job(repo, units, prof, fail=fail)
    return mirrored_job(repo, units, prof, fail=fail)


def approve(repo, unit):
    current = row(repo, unit)
    if "policy_impacts" in tables(repo):
        repo.approve(unit, current["version"])
        return
    with repo.transaction() as db:  # Schema 1 mirror of the revision's approve().
        db.execute(
            "UPDATE work_items SET status='approved',approved_source=?,"
            "approved_translation=translation_revision,version=version+1 WHERE unit_id=?",
            (current["source_revision"], unit),
        )


def edit_and_approve(repo, unit, text):
    assert repo.edit(unit, row(repo, unit)["version"], text)
    approve(repo, unit)


def glossary(repo, source, target):
    rule = GlossaryRule(source=source, target=target, kind="preferred_translation")
    if "policy_impacts" in tables(repo):
        PolicyStore(repo).set_glossary([rule])
    elif "glossary_versions" in tables(repo):  # Schema 2 mirror; impacts start in schema 3.
        encoded = canonical([rule.model_dump()])
        identifier = sha256(encoded.encode("utf-8")).hexdigest()
        with repo.transaction() as db:
            db.execute("INSERT INTO glossary_versions VALUES(?,?,?)", (identifier, encoded, now()))
            db.execute("INSERT INTO project_settings VALUES('glossary',?)", (identifier,))


def editor_draft(repo, unit, text):
    if "editor_drafts" in tables(repo):
        current = row(repo, unit)
        EditorDraftStore(repo).put(unit, current["source_revision"], current["version"], text, 0)


def observe(repo):
    units = [r[0] for r in repo.db.execute("SELECT unit_id FROM text_units ORDER BY unit_id")]
    drafts = {}
    if "editor_drafts" in tables(repo):
        for unit in units:
            value = EditorDraftStore(repo).get(unit)
            if value is not None:
                drafts[unit] = {key: value[key] for key in (
                    "source_revision", "base_version", "revision", "text")}
    return {
        "project_id": repo.project_id,
        "source_language": repo.source_language,
        "target_language": repo.target_language,
        "page": [
            {key: r[key] for key in (
                "unit_id", "source_revision", "status", "version", "translation_revision",
                "translation",
            )} for r in repo.page()
        ],
        "history": {
            unit: [r["id"] for r in repo.history(unit)["revisions"]] for unit in units
        },
        "drafts": drafts,
        "jobs": {
            r["id"]: {"kind": r["kind"], "status": r["status"]}
            for r in repo.db.execute("SELECT * FROM jobs ORDER BY created_at,rowid")
        } if "jobs" in tables(repo) else {},
    }


def unity(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    paths = ProjectPaths(game, tmp_path / "project")
    with ProjectRepository(paths) as repo:
        repo.ingest([draft(k, v) for k, v in UNITY_FIRST.items()], {"pass": 1})
        job(repo, list(UNITY_FIRST), profile(False))
        approve(repo, "UI/start")
        edit_and_approve(repo, "UI/options", "Ayarlar")
        glossary(repo, "Quit", "Çıkış")
    with ProjectRepository(paths) as repo:  # A later session sees a changed source.
        repo.ingest([draft(k, v) for k, v in UNITY_SECOND.items()], {"pass": 2})
        job(repo, ["UI/options"], profile(False), fail=True)
        editor_draft(repo, "UI/quit", "Çıkış")
        observed = observe(repo)
    return paths, observed


def renpy(tmp_path):
    from test_renpy_scripts import fixture

    from unitytranslator.discovery import extract_to_project

    paths, script = fixture(tmp_path, RENPY_FIRST)
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        job(repo, [r["unit_id"] for r in repo.page()], profile(True))
        approve(repo, by_source(repo, "Display")["unit_id"])
        edit_and_approve(repo, by_source(repo, "Hello there.")["unit_id"], "Selam.")
        glossary(repo, "Example", "Örnek")
    script.write_text(RENPY_SECOND, encoding="utf-8")
    extract_to_project(paths, "game/script.rpy")
    with ProjectRepository(paths) as repo:
        job(repo, [by_source(repo, "How are you today?")["unit_id"]], profile(True), fail=True)
        editor_draft(repo, by_source(repo, "Narration.")["unit_id"], "Anlatı.")
        observed = observe(repo)
    return paths, observed


@pytest.mark.parametrize("spec", SPECS, ids=[spec["name"] for spec in SPECS])
def test_build_legacy_project(spec, tmp_path, monkeypatch):
    if spec["cap"] is not None:
        original = ProjectRepository.migrate

        def capped(self, old_version, new_version):
            if new_version <= spec["cap"]:
                original(self, old_version, new_version)

        monkeypatch.setattr(repository_module.ProjectRepository, "migrate", capped)
        recover = ProjectRepository.recover_interrupted

        def recover_existing(self):
            # The revision's recovery assumes the schema-2 job tables; schema 1 has no jobs.
            if "job_items" in tables(self):
                recover(self)

        monkeypatch.setattr(
            repository_module.ProjectRepository, "recover_interrupted", recover_existing
        )
    paths, observed = {"unity": unity, "renpy": renpy}[spec["recipe"]](tmp_path)
    gc.collect()  # Close read-only preflight connections the revision left to the collector.
    database = paths.project / "project.sqlite3"
    if (paths.project / "project.sqlite3-wal").exists():
        last = sqlite3.connect(database)  # The last connection folds the WAL into the file.
        last.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        last.close()
    assert not (paths.project / "project.sqlite3-wal").exists()
    target = OUT / spec["name"]
    target.mkdir()
    shutil.copyfile(paths.project / "project.sqlite3", target / "project.sqlite3")
    shutil.copyfile(paths.project / "project.json", target / "project.json")
    (target / "observed.json").write_text(json.dumps(observed), encoding="utf-8")
'''


def git(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments], capture_output=True, check=True
    ).stdout


def extract(repository: Path, revision: str, target: Path) -> None:
    archive = git(repository, "archive", "--format=tar", revision, "src", "tests")
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(target, filter="data")


def name(revision: str, recipe: str, schema: int) -> str:
    return f"schema{schema}-{revision}-{recipe}"


def build(
    repository: Path, revision: str, specs: list[dict[str, object]], work: Path, staging: Path
) -> None:
    root = work / revision
    root.mkdir()
    extract(repository, revision, root)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    module = root / "tests" / "test_zz_legacy_project_build.py"
    module.write_text(RECIPE, encoding="utf-8")
    environment = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "UT_LEGACY_OUT": str(staging),
        "UT_LEGACY_SOURCE": str(root / "src"),
        "UT_LEGACY_SPECS": json.dumps(specs),
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "-c",
            str(root / "pytest.ini"),
            "--rootdir",
            str(root),
            "--basetemp",
            str(root / "basetemp"),
            str(module),
        ],
        cwd=root,
        env=environment,
        check=True,
    )


def anonymize(database: Path, forbidden: list[bytes]) -> None:
    """Replace the build's game folder; secure_delete zeroes the freed old value."""
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA secure_delete=ON")
        db.execute("UPDATE project SET game_path=?", (PLACEHOLDER,))
    db.close()
    if database.with_name(database.name + "-wal").exists():
        raise RuntimeError("The rewritten database kept a WAL file.")
    raw = database.read_bytes().lower()
    for value in forbidden:
        if value.lower() in raw:
            raise RuntimeError(f"{database} still contains a local build path.")


def stored(database: Path) -> dict[str, object]:
    """Concrete records read back from the frozen bytes at build time."""
    with sqlite3.connect(database.as_uri() + "?immutable=1", uri=True) as db:
        names = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result: dict[str, object] = {
            "user_version": db.execute("PRAGMA user_version").fetchone()[0],
            "migrations": [
                row[0]
                for row in db.execute("SELECT version FROM schema_migrations ORDER BY version")
            ],
            "counts": {
                table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in names
            },
            "text_units": {
                row[0]: [row[1], row[2]]
                for row in db.execute(
                    "SELECT unit_id,source_revision,active FROM text_units ORDER BY unit_id"
                )
            },
            "work_items": {
                row[0]: list(row[1:])
                for row in db.execute(
                    "SELECT unit_id,status,version,translation_revision,approved_source,"
                    "approved_translation FROM work_items ORDER BY unit_id"
                )
            },
            "glossary_versions": [
                row[0] for row in db.execute("SELECT id FROM glossary_versions ORDER BY id")
            ]
            if "glossary_versions" in names
            else [],
            "source_descriptors": [
                row[0] for row in db.execute("SELECT id FROM source_descriptors ORDER BY id")
            ]
            if "source_descriptors" in names
            else [],
            "job_context_sources": [
                list(row)
                for row in db.execute(
                    "SELECT job_id,source_id FROM job_context_sources ORDER BY job_id,source_id"
                )
            ]
            if "job_context_sources" in names
            else [],
        }
    db.close()
    return result


def describe(repository: Path, revision: str) -> dict[str, object]:
    project = tomllib.loads(git(repository, "show", f"{revision}:pyproject.toml").decode())
    tags = git(repository, "tag", "--points-at", revision).decode().split()
    return {"package_version": project["project"]["version"], "tags": sorted(tags)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work",
        type=Path,
        required=True,
        help="New directory under .cache/tests/ for extracted revisions.",
    )
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--repository", type=Path, default=HERE.parents[2])
    args = parser.parse_args()
    repository = args.repository.resolve()
    work = args.work.resolve()
    work.mkdir(parents=True)  # Refuses an existing work directory.
    staging = work / "staging"
    staging.mkdir()
    revisions: dict[str, list[dict[str, object]]] = {}
    for revision, recipe, schema, cap in FIXTURES:
        revisions.setdefault(revision, []).append(
            {"name": name(revision, recipe, schema), "recipe": recipe, "cap": cap}
        )
    for revision, specs in revisions.items():
        build(repository, revision, specs, work, staging)
    forbidden = sorted(
        {
            variant.encode("utf-8")
            for path in (work, repository, Path.home())
            for variant in (str(path), path.as_posix(), json.dumps(str(path))[1:-1])
        }
    )
    fixtures = []
    for revision, recipe, schema, cap in FIXTURES:
        label = name(revision, recipe, schema)
        folder = staging / label
        database = folder / "project.sqlite3"
        anonymize(database, forbidden)
        manifest = folder / "project.json"
        if any(value.lower() in manifest.read_bytes().lower() for value in forbidden):
            raise RuntimeError(f"{manifest} contains a local build path.")
        expect = {
            **json.loads((folder / "observed.json").read_text(encoding="utf-8")),
            **stored(database),
        }
        if expect["user_version"] != schema:
            raise RuntimeError(f"{label} left schema {expect['user_version']}, not {schema}.")
        fixtures.append(
            {
                "name": label,
                "revision": revision,
                **describe(repository, revision),
                "recipe": recipe,
                "build": "stepwise" if cap is not None else "release",
                "schema": schema,
                "database": label + ".sqlite3",
                "database_sha256": sha256(database.read_bytes()).hexdigest(),
                "manifest": label + ".project.json",
                "manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
                "expect": expect,
            }
        )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for item in fixtures:  # Create-new copies; an existing fixture is never replaced.
        folder = staging / str(item["name"])
        for source, target in (
            ("project.sqlite3", item["database"]),
            ("project.json", item["manifest"]),
        ):
            with (folder / source).open("rb") as stream, (output / str(target)).open("xb") as out:
                shutil.copyfileobj(stream, out)
    index = {
        "format_version": 1,
        "synthetic_only": True,
        "game_path_placeholder": PLACEHOLDER,
        "fixtures": fixtures,
    }
    with (output / "index.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
