"""Synthetic Unity serialized files through the real Unity worker subprocess.

The fixtures come from tests/fixtures/unity-serialized/build_fixtures.py. They cover
the I2 type-tree path and the Unity 2017 managed-metadata fallback; no game is started
and the synthetic assembly is only read as metadata.
"""

import importlib.util
import shutil
from hashlib import sha256
from pathlib import Path
from types import ModuleType

import pytest

from unitytranslator.discovery import _probe_i2_source, extract_to_project
from unitytranslator.filesystem import ProjectPaths, hash_file
from unitytranslator.repository import ProjectRepository

FIXTURES = Path(__file__).parent / "fixtures" / "unity-serialized"
DATA = "Synthetic_Data"
TYPE_TREE = DATA + "/sharedassets0.assets"
MANAGED = DATA + "/resources.assets"
SOURCE_SET = "SyntheticLanguages"
# Extraction order, category, context and the English and Turkish source texts.
EXPECTED = [
    ("Menu/Start", "Menu", "Main menu button", "Start", "Başlat"),
    ("Dialog/Intro", "Dialog", "", "Hello, {[PLAYER]}!\nWelcome.", "Merhaba, {[PLAYER]}!"),
    ("Menu/Empty", "Menu", "Not written yet", "", "Boş"),
    ("Credits", "unknown", "", "Thanks: Iıİi çğöşü", "Teşekkürler"),
]


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "unity_serialized_fixtures", FIXTURES / "build_fixtures.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install(tmp_path: Path, builder: ModuleType, **replace: bytes) -> ProjectPaths:
    """Copy the committed fixtures into a new synthetic game; never edit the originals."""
    game = tmp_path / "game"
    for fixture, installed in builder.LAYOUT.items():
        target = game / DATA / installed
        target.parent.mkdir(parents=True, exist_ok=True)
        if fixture in replace:
            target.write_bytes(replace[fixture])
        else:
            shutil.copyfile(FIXTURES / fixture, target)
    return ProjectPaths(game, tmp_path / "project")


def fingerprints(paths: ProjectPaths) -> dict[str, str]:
    return {
        path.relative_to(paths.game).as_posix(): hash_file(path)
        for path in sorted(paths.game.rglob("*"))
        if path.is_file()
    }


def unit_id(key: str) -> str:
    return sha256("\0".join(("i2-v1", SOURCE_SET, key)).encode("utf-8")).hexdigest()


def expected_units(source: str, source_object: int, language: str = "en") -> list[dict]:
    column = 3 if language == "en" else 4
    return [
        {
            "unit_id": unit_id(key),
            "original_key": key,
            "source_file": source,
            "source_object": source_object,
            "source_language": language,
            "source_text": item[column],
            "source_hash": sha256(item[column].encode("utf-8")).hexdigest(),
            "category": category,
            "context": context,
        }
        for item in EXPECTED
        for key, category, context in [item[:3]]
        if item[column]
    ]


def test_committed_fixtures_match_the_builder_and_stay_small(builder, tmp_path):
    built = builder.fixtures()
    assert set(built) == set(builder.LAYOUT)
    committed = {path.name for path in FIXTURES.iterdir() if path.suffix == ".bin"}
    assert committed == set(built)
    for name, data in built.items():
        assert (FIXTURES / name).read_bytes() == data, f"Regenerate {name} with the builder."
    assert sum(len(data) for data in built.values()) < 200 * 1024
    # Source packages reject these suffixes; the committed names must avoid them.
    assert not any(Path(name).suffix in (".assets", ".dll") for name in built)
    output = tmp_path / "check"
    output.mkdir()
    assert builder.main(["--check", "--output", str(output)]) == 1
    assert not any(output.iterdir())


def test_type_tree_path_extracts_ordered_units_with_stable_identities(builder, tmp_path):
    paths = install(tmp_path, builder)
    before = fingerprints(paths)
    report = _probe_i2_source(paths, TYPE_TREE)
    assert report["extraction"] == "supported"
    assert report["capabilities"]["extraction"]["status"] == "supported"
    assert report["unity_versions"] == ["2017.4.40f1"]
    assert report["objects"] == {"GameObject": 1, "MonoScript": 1, "MonoBehaviour": 1}
    assert report["i2_scripts"] == [
        {
            "object": 2,
            "class": "LanguageSource",
            "namespace": "I2.Loc",
            "assembly": "Synthetic.I2.dll",
        }
    ]
    [candidate] = report["i2_candidates"]
    assert candidate["object"] == 3 and candidate["source_set"] == SOURCE_SET
    assert candidate["term_count"] == 5 and candidate["schema_evidence"] is None
    assert [language["Code"] for language in candidate["languages"]] == ["en", "tr", "ja"]
    assert report["units"] == expected_units(TYPE_TREE, 3)
    assert report["errors"] == []
    assert report["diagnostics"] == [
        {"object": 3, "key": "Menu/Empty", "code": "empty_source_excluded"}
    ]
    assert report["counts"]["records"] == 3
    assert report["sha256_before"] == report["sha256_after"] == before[TYPE_TREE]
    assert fingerprints(paths) == before


def test_managed_fallback_reads_synthetic_metadata_with_the_same_identities(builder, tmp_path):
    paths = install(tmp_path, builder)
    before = fingerprints(paths)
    report = _probe_i2_source(paths, MANAGED)
    assert report["extraction"] == "supported"
    assert report["objects"] == {"GameObject": 2, "MonoBehaviour": 2}
    assert report["i2_scripts"] == []  # The MonoScripts are in the external file.
    [candidate] = report["i2_candidates"]
    # The component name is empty; the source set comes from the GameObject.
    assert candidate["object"] == 2 and candidate["source_set"] == SOURCE_SET
    # Public and [SerializeField] fields are read; the unmarked private field is not.
    assert candidate["fields"] == [
        "Assets",
        "CaseInsensitiveTerms",
        "mLanguages",
        "mTerms",
        "mUpdateDelay",
    ]
    source_bytes = builder.payload(
        builder.language_source("", 1, 1), builder.build_node(builder.language_source_nodes())
    )
    assert candidate["schema_evidence"] == {
        "assembly_sha256": before[DATA + "/Managed/Synthetic.I2.dll"],
        # Static, [NonSerialized] and unmarked private LanguageSource fields are skipped.
        "fields": ["mSource"],
        "consumed_bytes": len(source_bytes),
        "schema_reader": "dnfile-unity2017-v1",
    }
    # Unit IDs match the type-tree path: identity does not depend on the reader path.
    assert report["units"] == expected_units(MANAGED, 2)
    assert report["errors"] == []
    # The non-I2 MonoBehaviour (object 4) is identified by its script and skipped.
    assert report["diagnostics"] == [
        {"object": 2, "code": "type_tree_unavailable", "exception": "ValueError"},
        {"object": 2, "key": "Menu/Empty", "code": "empty_source_excluded"},
        {"object": 4, "code": "type_tree_unavailable", "exception": "ValueError"},
    ]
    turkish = _probe_i2_source(paths, MANAGED, source_language="tr")
    assert turkish["units"] == expected_units(MANAGED, 2, "tr")
    assert [unit["unit_id"] for unit in turkish["units"]] == [unit_id(key) for key, *_ in EXPECTED]
    assert fingerprints(paths) == before


def test_fallback_units_enter_the_shared_project_pipeline(builder, tmp_path):
    paths = install(tmp_path, builder)
    before = fingerprints(paths)
    extracted = extract_to_project(paths, MANAGED)
    assert extracted["extraction"] == "supported"
    assert extracted["counts"]["records"] == 3
    with ProjectRepository(paths) as repository:
        rows = repository.page()
    # The review page orders I2 records by term key; the worker kept the I2 term order.
    assert [
        (row["unit_id"], row["original_key"], row["source_text"], row["status"]) for row in rows
    ] == sorted(
        (
            (unit["unit_id"], unit["original_key"], unit["source_text"], "pending")
            for unit in expected_units(MANAGED, 2)
        ),
        key=lambda row: (row[1], row[0]),
    )
    assert fingerprints(paths) == before


@pytest.mark.parametrize(
    "variant,message",
    [
        ("trailing", "The serialized object was not fully consumed; the schema was not accepted."),
        ("truncated", "Truncated Unity serialized object."),
        ("assembly", "Managed assembly metadata was not found."),
        ("scripts", "The script metadata file is not a Unity serialized file."),
    ],
)
def test_corrupted_fallback_inputs_fail_closed(builder, tmp_path, variant, message):
    replace = {
        "trailing": {"managed.bin": builder.managed_source(source_suffix=b"\0" * 4)},
        "truncated": {"managed.bin": builder.managed_source(source_trim=4)},
        "assembly": {"assembly.bin": builder.assembly()[:600]},
        "scripts": {"scripts.bin": builder.scripts_file()[:-50]},
    }[variant]
    paths = install(tmp_path, builder, **replace)
    before = fingerprints(paths)
    report = _probe_i2_source(paths, MANAGED)
    assert report["units"] == []
    assert report["extraction"] == "unknown"
    assert report["capabilities"]["extraction"]["reason"] == "source_read_failed"
    assert report["errors"][0]["object"] == 2
    assert {error["code"] for error in report["errors"]} == {"managed_i2_error"}
    # Without readable script metadata the non-I2 MonoBehaviour cannot be told apart either.
    objects = [2, 4] if variant == "scripts" else [2]
    assert report["errors"] == [
        {"object": item, "code": "managed_i2_error", "message": message} for item in objects
    ]
    with pytest.raises(ValueError, match="Extraction could not be completed"):
        extract_to_project(paths, MANAGED)
    with ProjectRepository(paths) as repository:
        assert repository.page() == []
    assert fingerprints(paths) == before


@pytest.mark.parametrize(
    "fixture,relative",
    [
        ("managed.bin", MANAGED),
        ("typetree.bin", TYPE_TREE),
    ],
)
def test_truncated_serialized_files_are_not_read_as_sources(builder, tmp_path, fixture, relative):
    data = (FIXTURES / fixture).read_bytes()
    paths = install(tmp_path, builder, **{fixture: data[: len(data) - 100]})
    report = _probe_i2_source(paths, relative)
    # UnityPy does not recognize a serialized file whose header size exceeds the file.
    assert report["objects"] == {} and report["units"] == [] and report["errors"] == []
    assert report["extraction"] == "unknown"
    assert report["capabilities"]["extraction"]["reason"] == "no_matching_reader"
    with pytest.raises(ValueError, match="Extraction could not be completed"):
        extract_to_project(paths, relative)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Development C5: the type-tree path ignores the GameObject name that the "
    "managed fallback uses when the component name is empty.",
)
def test_type_tree_path_names_an_empty_component_like_the_fallback(builder, tmp_path):
    paths = install(tmp_path, builder, **{"typetree.bin": builder.typetree_source(name="")})
    report = _probe_i2_source(paths, TYPE_TREE)
    # Today: [{"object": 3, "code": "i2_schema_error",
    #          "message": "A stable source set name was not found."}]
    assert report["errors"] == []
    assert report["units"] == expected_units(TYPE_TREE, 3)
