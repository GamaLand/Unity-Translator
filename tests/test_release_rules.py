"""Packaging tools share one private-data rule module and one version source."""

import importlib
import io
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest

import unitytranslator

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
RELEASE_TOOLS = (
    "build_windows",
    "check_distribution",
    "check_documentation",
    "package_dependency_sources",
    "package_notices",
    "package_source",
    "package_windows",
)

# Rule sets each tool carried before tools/release_rules.py; every one stays enforced.
FORMER_DISTRIBUTION = {
    "folders": {
        ".local",
        ".cache",
        ".python",
        ".venv",
        "deployment",
        "obj",
        "bin",
        ".agents",
        ".codex",
        ".claude",
        ".cursor",
    },
    "names": {
        "agents.md",
        "claude.md",
        "gemini.md",
        "goal.md",
        "technical_design.md",
        "technical.design.md",
        ".cursorrules",
        ".windsurfrules",
        "copilot-instructions.md",
        ".env",
        ".env.local",
    },
    "suffixes": {
        ".gguf",
        ".assets",
        ".sqlite3",
        ".ress",
        ".dll",
        ".rpa",
        ".rpyc",
        ".rpy",
        "_ren.py",
    },
}
FORMER_SOURCE_ZIP = {
    "folders": FORMER_DISTRIBUTION["folders"],
    "names": {
        "agents.md",
        "goal.md",
        "technical_design.md",
        "technical.design.md",
        "claude.md",
        "gemini.md",
        ".env",
    },
    "suffixes": {
        ".dll",
        ".exe",
        ".gguf",
        ".assets",
        ".sqlite3",
        ".rpa",
        ".rpyc",
        ".rpy",
        "_ren.py",
    },
}
FORMER_STANDALONE = {
    # package_windows.py and package_notices.py (whose ".resS" check never matched).
    "folders": {".local", ".cache", ".python", ".venv", "deployment"},
    "names": set(),
    "suffixes": {".gguf", ".assets", ".sqlite3", ".ress"},
}


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    # Release tools run as scripts, so their folder is on sys.path; mirror that here.
    monkeypatch.syspath_prepend(str(TOOLS))
    return importlib.import_module("release_rules")


def samples(rules: dict[str, set[str]]) -> list[str]:
    paths = []
    for folder in rules["folders"]:
        paths += [f"{folder}/file.txt", f"docs/{folder.upper()}/nested/file.txt"]
    for name in rules["names"]:
        paths += [name, f"docs/{name.upper()}"]
    for suffix in rules["suffixes"]:
        stem = "script" if suffix.startswith("_") else "data"
        paths += [f"{stem}{suffix}", f"src/deep/{stem}{suffix.upper()}"]
    return paths


@pytest.mark.parametrize(
    ("rules", "profiles"),
    [
        (FORMER_DISTRIBUTION, ("WHEEL", "SOURCE")),
        (FORMER_SOURCE_ZIP, ("SOURCE",)),
        (FORMER_STANDALONE, ("STANDALONE", "WHEEL", "SOURCE")),
    ],
)
def test_every_former_rule_set_is_still_enforced(
    tools: ModuleType, rules: dict[str, set[str]], profiles: tuple[str, ...]
) -> None:
    for profile in profiles:
        allowed = [
            path
            for path in samples(rules)
            if tools.private_reason(path, getattr(tools, profile)) is None
        ]
        assert allowed == [], profile
    for name in ("C:/x/data.txt", "/abs/data.txt", "a/../b.txt", "a\\b.txt", ""):
        assert tools.unsafe_path(name), name


def test_standalone_keeps_native_runtime_files(tools: ModuleType) -> None:
    for name in (
        "UnityTranslator.exe",
        "PySide6/Qt6Core.dll",
        "certifi/cacert.pem",
        "UnityPy/x.tpk",
        "LICENSES/httpx/httpx-0.28.1.dist-info_licenses_LICENSE.md",
        "runtime-kit/a.zip",
    ):
        assert tools.private_reason(name, tools.STANDALONE) is None, name
    for name in ("game/script.rpy", "data/model.safetensors", "x/.venv-old/a.txt"):
        assert tools.private_reason(name, tools.STANDALONE) is not None, name


def test_fixture_trees_are_exact_paths_and_types(tools: ModuleType) -> None:
    accepted = (
        "tests/fixtures/legacy-recipients/.gitattributes",
        "tests/fixtures/legacy-recipients/renpy-additive-1e1dfc3.zip",
        "tests/fixtures/legacy-recipients/build_legacy_recipients.py",
        "tests/fixtures/legacy-projects/schema-1.sqlite3",
        "tests/fixtures/legacy-projects/nested/schema-6.SQLITE3",
        "tests/fixtures/legacy-projects/index.json",
        "tests/fixtures/unity-serialized/typetree.bin",
        "tests/fixtures/unity-serialized/README.md",
    )
    for name in accepted:
        assert tools.private_reason(name, tools.SOURCE) is None, name
    rejected = (
        "tests/fixtures/legacy-projects/schema-1.sqlite3-wal",
        "tests/fixtures/legacy-projects/model.gguf",
        "tests/fixtures/legacy-projects/runner.exe",
        "tests/fixtures/legacy-projects/script_ren.py",
        "tests/fixtures/legacy-projects/__pycache__/x.json",
        "tests/fixtures/legacy-projects/AGENTS.md",
        "tests/fixtures/legacy-projects/notes.txt",
        "tests/fixtures/legacy-projects/schema",
        "tests/fixtures/legacy-projects-copy/schema-1.sqlite3",
        "tests/fixtures/legacy-recipients/game.sqlite3",
        "tests/fixtures/legacy-recipients/script.rpy",
        "tests/fixtures/unity-serialized/resources.assets",
        "tests/fixtures/unity-serialized/Synthetic.I2.dll",
        "tests/fixtures/schema-1.sqlite3",
        "src/tests/fixtures/legacy-projects/schema-1.sqlite3",
    )
    for name in rejected:
        assert tools.private_reason(name, tools.SOURCE) is not None, name
    # The installable wheel never carries test fixtures' private file types.
    assert tools.private_reason(accepted[3], tools.WHEEL) is not None


def test_present_fixture_files_match_their_tree(tools: ModuleType) -> None:
    for tree in tools.SOURCE_FIXTURE_TREES:
        folder = ROOT / tree.prefix
        if not folder.is_dir():
            continue  # A tree may land after this rule; its allowlist still applies.
        for path in folder.rglob("*"):
            relative = PurePosixPath(path.relative_to(ROOT).as_posix())
            if path.is_file() and "__pycache__" not in relative.parts:
                assert tools.private_reason(str(relative), tools.SOURCE) is None, relative


def test_sdist_reincludes_only_reviewed_fixture_types(tools: ModuleType) -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excludes = config["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    trees = {tree.prefix.as_posix(): tree for tree in tools.SOURCE_FIXTURE_TREES}
    for pattern in (item for item in excludes if item.startswith("!")):
        match = re.fullmatch(r"!/(tests/fixtures/[a-z-]+)/\*\*/\*(\.[a-z0-9]+)", pattern)
        assert match, pattern
        assert match[2] in trees[match[1]].suffixes
    # Global source exclusions still cover the private suffixes the audit rejects.
    for suffix in (".gguf", ".dll", ".exe", ".rpa", ".rpyc", ".rpy", ".pem", ".key", ".pfx"):
        assert any(item.endswith("*" + suffix) for item in excludes), suffix


def test_distribution_audit_accepts_fixtures_and_rejects_private_data(
    tools: ModuleType, tmp_path: Path
) -> None:
    audit = importlib.import_module("check_distribution").audit
    root = "unitytranslator-0.0.0/"
    required = [
        "src/unitytranslator/resources/renpy-source-NOTICE.txt",
        "src/unitytranslator/resources/renpy-additive.ps1",
        "src/unitytranslator/resources/recipient-core.ps1",
        "src/unitytranslator/resources/locales/legacy-messages.json",
        *(f"src/unitytranslator/resources/locales/{code}.json" for code in tools.LANGUAGES),
        *(f"guide/{code}.md" for code in tools.LANGUAGES),
        "tests/fixtures/legacy-projects/schema-1.sqlite3",
        "tests/fixtures/unity-serialized/typetree.bin",
    ]

    def sdist(name: str, entries: list[str]) -> Path:
        path = tmp_path / name / "unitytranslator-0.0.0.tar.gz"
        path.parent.mkdir()
        with tarfile.open(path, "w:gz") as archive:
            for entry in entries:
                info = tarfile.TarInfo(root + entry)
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))
        return path

    assert len(audit(sdist("clean", required))) == len(required)
    private = ("tests/fixtures/game.sqlite3", ".claude/settings.json", "game/a.rpy")
    for index, entry in enumerate(private):
        with pytest.raises(ValueError, match="private"):
            audit(sdist(f"private-{index}", [*required, entry]))
    outside = tmp_path / "outside" / "unitytranslator-0.0.0.tar.gz"
    outside.parent.mkdir()
    with tarfile.open(outside, "w:gz") as archive:
        for entry in [*(root + item for item in required), "model.gguf", "AGENTS.md"]:
            info = tarfile.TarInfo(entry)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="exactly one top-level folder"):
        audit(outside)
    wheel =tmp_path / "unitytranslator-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for entry in required[:-2]:
            archive.writestr(entry.replace("src/", ""), b"x")
        archive.writestr("unitytranslator/tests/fixtures/legacy-projects/a.sqlite3", b"x")
    with pytest.raises(ValueError, match="private"):
        audit(wheel)


@pytest.mark.parametrize("name", RELEASE_TOOLS)
def test_release_tools_import_the_shared_rules(tools: ModuleType, name: str) -> None:
    importlib.import_module(name)
    source = (TOOLS / (name + ".py")).read_text(encoding="utf-8")
    assert "tomllib" not in source and '"pyproject.toml"' not in source
    assert '".sqlite3"' not in source and '".gguf"' not in source
    assert '"agents.md"' not in source and '("en", "tr"' not in source
    assert "[a-z][a-z0-9.-]" not in source


def test_release_label_rule(tools: ModuleType) -> None:
    assert tools.check_release_label("rc.8") == "rc.8"
    for label in ("RC8", "8rc", "rc/8", "a" * 41, ""):
        with pytest.raises(ValueError):
            tools.check_release_label(label)


def test_one_version_source(tools: ModuleType) -> None:
    version = tools.project_version()
    assert version == unitytranslator.__version__
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in project["project"]
    assert project["project"]["dynamic"] == ["version"]
    assert project["tool"]["hatch"]["version"]["path"] == tools.VERSION_FILE.as_posix()
    description = project["project"]["description"]
    assert "supported Unity and Ren'Py games" in description
    copy = re.compile(rb"(?<![0-9.])" + re.escape(version.encode()) + rb"(?![0-9])")
    generated = {"__pycache__", "deployment", "obj", "bin"}
    copies = []
    for folder in ("src", "tools"):
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if (
                path.is_file()
                and not generated.intersection(relative.parts)
                and relative.as_posix() != tools.VERSION_FILE.as_posix()
                and copy.search(path.read_bytes())
            ):
                copies.append(relative.as_posix())
    assert copies == []
    assert copy.search((ROOT / "pysidedeploy.spec").read_bytes()) is None


def test_project_version_reads_only_a_plain_literal(tools: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / tools.VERSION_FILE
    target.parent.mkdir(parents=True)
    target.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    assert tools.project_version(tmp_path) == "1.2.3"
    for text in ("__version__ = get()\n", '__version__ = "../x"\n', 'VERSION = "1.0"\n'):
        target.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            tools.project_version(tmp_path)
