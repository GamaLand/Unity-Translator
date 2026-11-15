"""Shared private-data, release-label and version rules for the packaging tools.

The release tools import this module by name because Python puts the running script's
folder on ``sys.path``. It deliberately imports nothing from ``unitytranslator`` so the
audits read this checkout, never an installed copy.
"""

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PurePosixPath("src/unitytranslator/__init__.py")
LANGUAGES = ("en", "tr", "de", "fr", "es", "pt", "ru", "zh")
RELEASE_LABEL = re.compile(r"[a-z][a-z0-9.-]{0,39}")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:[a-z][a-z0-9]*(?:\.[0-9]+)?)?")

# Local environments, caches, build output and assistant state, matched per path part.
PRIVATE_DIRECTORIES = frozenset(
    {
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
        ".git",
        "__pycache__",
    }
)
PRIVATE_DIRECTORY_PREFIXES = (".venv-",)
# Local AI instructions and secrets, matched by file name.
PRIVATE_NAMES = frozenset(
    {
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
    }
)
PRIVATE_NAME_PREFIXES = (".env.", ".aider")
# Game and model data never belong in any delivery.
GAME_MODEL_SUFFIXES = frozenset(
    {".gguf", ".ggml", ".safetensors", ".assets", ".ress", ".sqlite3", ".unitypackage"}
)
# Ren'Py game scripts/archives are game data; executables and secrets are binary/private.
SOURCE_ONLY_SUFFIXES = frozenset(
    {
        ".rpa",
        ".rpyc",
        ".rpy",
        ".dll",
        ".exe",
        ".pdb",
        ".pem",
        ".key",
        ".pfx",
        ".log",
        ".bundle",
    }
)
SOURCE_ONLY_NAME_SUFFIXES = ("_ren.py",)


@dataclass(frozen=True)
class FixtureTree:
    """A reviewed synthetic test tree that may carry otherwise private file types."""

    prefix: PurePosixPath
    suffixes: frozenset[str]
    names: frozenset[str] = frozenset()

    def contains(self, relative: PurePosixPath) -> bool:
        return relative.parts[: len(self.prefix.parts)] == self.prefix.parts and len(
            relative.parts
        ) > len(self.prefix.parts)

    def accepts(self, relative: PurePosixPath) -> bool:
        name = relative.name.casefold()
        return name in self.names or (
            "." in name.lstrip(".") and relative.suffix.casefold() in self.suffixes
        )


# Exact synthetic fixture trees; everything inside them must use one of these file types.
SOURCE_FIXTURE_TREES = (
    FixtureTree(
        PurePosixPath("tests/fixtures/legacy-recipients"),
        frozenset({".zip", ".json", ".md", ".py"}),
        frozenset({".gitattributes"}),
    ),
    FixtureTree(
        PurePosixPath("tests/fixtures/legacy-projects"),
        frozenset({".sqlite3", ".json", ".md", ".py"}),
    ),
    FixtureTree(
        # Synthetic serialized files are committed as .bin, never as game-named .assets.
        PurePosixPath("tests/fixtures/unity-serialized"),
        frozenset({".bin", ".json", ".md", ".py"}),
    ),
)


@dataclass(frozen=True)
class Profile:
    """Which private-data rules apply to one kind of delivery."""

    name: str
    suffixes: frozenset[str]
    name_suffixes: tuple[str, ...]
    fixture_trees: tuple[FixtureTree, ...] = ()


# Wheel: installable package only. Source: sdist and the source ZIP built from it.
WHEEL = Profile("wheel", GAME_MODEL_SUFFIXES | SOURCE_ONLY_SUFFIXES, SOURCE_ONLY_NAME_SUFFIXES)
SOURCE = Profile(
    "source",
    GAME_MODEL_SUFFIXES | SOURCE_ONLY_SUFFIXES,
    SOURCE_ONLY_NAME_SUFFIXES,
    SOURCE_FIXTURE_TREES,
)
# Standalone builds legitimately carry native runtime DLLs, the EXE and CA bundles.
STANDALONE = Profile(
    "standalone",
    GAME_MODEL_SUFFIXES | {".rpa", ".rpyc", ".rpy"},
    SOURCE_ONLY_NAME_SUFFIXES,
)


def unsafe_path(name: str) -> bool:
    """Return whether an archive/manifest name is not a plain relative POSIX path."""
    relative = PurePosixPath(name)
    return (
        not name
        or "\\" in name
        or ":" in name
        or relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
    )


def private_reason(name: str, profile: Profile) -> str | None:
    """Return why a relative delivery path is private, or None when it is allowed."""
    relative = PurePosixPath(name.replace("\\", "/"))
    for part in relative.parts:
        folded = part.casefold()
        if folded in PRIVATE_DIRECTORIES or folded.startswith(PRIVATE_DIRECTORY_PREFIXES):
            return "private folder"
    filename = relative.name.casefold()
    if filename in PRIVATE_NAMES or filename.startswith(PRIVATE_NAME_PREFIXES):
        return "private file name"
    tree = next((item for item in profile.fixture_trees if item.contains(relative)), None)
    if tree is not None and not tree.accepts(relative):
        return "unreviewed fixture file type"
    # A fixture tree waives only its own listed suffixes; name suffixes are never waived.
    waived = tree.suffixes if tree is not None else frozenset()
    if filename.endswith(profile.name_suffixes) or any(
        filename.endswith(suffix) and suffix not in waived for suffix in profile.suffixes
    ):
        return "game, model or binary data"
    return None


def private_entries(names: Iterable[str], profile: Profile) -> list[str]:
    """Return the names a delivery must not contain, in input order."""
    return [name for name in names if private_reason(name, profile) is not None]


def strip_archive_root(name: str) -> str:
    """Remove the single top folder that sdists put around every entry."""
    parts = PurePosixPath(name).parts
    return PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else ""


def check_release_label(label: str) -> str:
    if not RELEASE_LABEL.fullmatch(label):
        raise ValueError("Invalid release label.")
    return label


def project_version(root: Path = ROOT) -> str:
    """Read the authoritative ``__version__`` literal without importing the package."""
    tree = ast.parse((root / VERSION_FILE).read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and [getattr(target, "id", None) for target in node.targets] == ["__version__"]
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and VERSION.fullmatch(node.value.value)
        ):
            return node.value.value
    raise ValueError("The package version literal is missing or invalid.")
