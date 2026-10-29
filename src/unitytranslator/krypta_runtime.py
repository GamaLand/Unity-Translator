"""Pinned Krypta runtime components and binary-bound experimental installation evidence."""

from importlib.resources import files
from pathlib import Path

from unitytranslator.filesystem import checked_path
from unitytranslator.json_boundary import strict_json
from unitytranslator.krypta_profile import load_profile, verify_profile_evidence
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_kit import CORE_NAMES, RuntimeKit, bundled_kit_root

RUNTIME_SCHEMAS = frozenset(
    {"menu-lines-v1", "forum-lines-v1", "keypost-lines-v1", "subtitle-lines-v1", "journal-lines-v1"}
)
LEGACY_RUNTIME_SCHEMAS = RUNTIME_SCHEMAS - {"journal-lines-v1"}


class KryptaRuntimeKit(RuntimeKit):
    plugin_name = "UnityTranslator.KryptaFM.dll"
    runtime_names = {"core/" + name for name in CORE_NAMES} | {
        "winhttp.dll",
        "plugin/" + plugin_name,
    }

    def __init__(self, root: Path | None = None):
        self.root = checked_path(root or bundled_kit_root().parent / "krypta-runtime-kit")
        raw = files("unitytranslator.resources").joinpath("krypta-runtime-kit-catalog.json")
        if not raw.is_file():
            raise ValueError("The experimental Krypta runtime has not been built.")
        data = raw.read_bytes()
        if len(data) > 1024 * 1024:
            raise ValueError("Krypta runtime catalog size limit exceeded.")
        self.catalog = strict_json(data)
        if (
            self.catalog.get("format_version") != 1
            or self.catalog.get("purpose") != "experimental-krypta-textassets-runtime"
            or set(self.catalog["runtime_files"]) != self.runtime_names
            or self.catalog.get("application_verified") is not False
            or not set(self.catalog.get("supported_schemas", LEGACY_RUNTIME_SCHEMAS))
            <= RUNTIME_SCHEMAS
        ):
            raise ValueError("Invalid experimental Krypta runtime catalog.")
        if self.catalog.get("ui_trial_enabled") is True:
            self.require_trial_evidence()

    def require_trial_evidence(self) -> None:
        """A rebuilt binary cannot inherit another binary's observed readiness."""
        evidence = self.catalog.get("ui_trial_evidence")
        if (
            not isinstance(evidence, dict)
            or evidence.get("format_version") != 1
            or evidence.get("scope") != "limited-user-accepted"
            or evidence.get("plugin_sha256")
            != self.catalog["runtime_files"]["plugin/" + self.plugin_name]
            or evidence.get("observed") != [
                "startup", "menu", "options", "menu-to-game", "pause", "subtitles"
            ]
        ):
            raise ValueError(
                "The experimental Krypta runtime readiness evidence is missing or stale."
            )

    def require_payload(self, payload: Path) -> None:
        path = checked_path(payload)
        with path.open("rb") as stream:
            data = stream.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Krypta runtime payload size limit exceeded.")
        value = strict_json(data)
        if not isinstance(value, dict):
            raise ValueError("Krypta runtime payload must be an object.")
        entries = value.get("entries")
        supported = set(self.catalog.get("supported_schemas", LEGACY_RUNTIME_SCHEMAS))
        if (
            not isinstance(entries, list)
            or not 1 <= len(entries) <= 256
            or any(
                not isinstance(entry, dict)
                or not isinstance(entry.get("schema"), str)
                or entry["schema"] not in supported
                for entry in entries
            )
        ):
            raise ValueError(
                "The pinned runtime does not support this source schema; rebuild the kit."
            )

    def check_game(self, repo: ProjectRepository, assembly_relative: str) -> None:
        profile = load_profile()
        if assembly_relative != profile["assembly"]["path"]:
            raise ValueError("Unexpected Krypta game assembly path.")
        super().check_game(repo, assembly_relative)
        verify_profile_evidence(repo.paths.game, profile)
