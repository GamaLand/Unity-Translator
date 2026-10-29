"""Built-in reader contracts and source-scoped identity, independent of backend libraries."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol

from unitytranslator.domain import TextUnitDraft


def validate_relative_source(value: str) -> None:
    windows, posix = PureWindowsPath(value), PurePosixPath(value)
    if (
        not value
        or len(value) > 2048
        or "\x00" in value
        or ":" in value
        or windows.drive
        or windows.root
        or posix.is_absolute()
        or ".." in windows.parts
        or ".." in posix.parts
    ):
        raise ValueError("Source paths must be safe relative game paths.")


@dataclass(frozen=True)
class SourceDescriptor:
    logical_id: str
    adapter_id: str
    profile_id: str
    schema_version: str
    source_file: str
    source_object: int
    source_language: str
    fingerprint: str = ""
    format_rules: str = "protected-i2-v4"
    asset_name: str = ""
    payload_fingerprint: str = ""

    def __post_init__(self) -> None:
        validate_relative_source(self.source_file)
        if self.format_rules not in ("protected-i2-v4", "literal-lines-v1", "renpy-text-v1"):
            raise ValueError("Unknown built-in source format rules.")
        for value in (
            self.logical_id,
            self.adapter_id,
            self.profile_id,
            self.schema_version,
            self.source_language,
            self.format_rules,
        ):
            if not value or len(value) > 4096 or "\x00" in value:
                raise ValueError("Invalid source descriptor identity or version.")
        for fingerprint in (self.fingerprint, self.payload_fingerprint):
            if fingerprint and (
                len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint)
            ):
                raise ValueError("Source fingerprints must be lowercase SHA-256 values.")

    @classmethod
    def legacy(cls, source_file: str, language: str) -> "SourceDescriptor":
        # A metadata namespace only: existing I2 unit/revision identities never change.
        return cls(
            "legacy-file-v1:" + source_file,
            "i2",
            "legacy-i2",
            "i2-v1",
            source_file,
            -1,
            language,
        )


@dataclass(frozen=True)
class SourceSnapshot:
    source: SourceDescriptor
    units: tuple[TextUnitDraft, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReaderContext:
    game: Path
    project: Path
    source_language: str
    timeout: float = 120
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False, compare=False)


@dataclass(frozen=True)
class ReaderProbe:
    sources: tuple[SourceDescriptor, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()
    report: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReaderResult:
    snapshots: tuple[SourceSnapshot, ...]
    complete: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    replace_source_set: bool = True


class SourceReader(Protocol):
    id: str
    version: str

    def probe(self, context: ReaderContext, relative: str) -> ReaderProbe: ...

    def extract(
        self, context: ReaderContext, relative: str, cancellation: Callable[[], bool]
    ) -> ReaderResult: ...


class DeploymentAdapter(Protocol):
    id: str
    version: str

    def probe(self) -> dict[str, Any]: ...

    def prepare(self, **options: Any) -> dict[str, Any]: ...
