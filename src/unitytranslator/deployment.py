"""Additive file plans and ownership-checked removal, independent of readers.

Normal and explicitly reviewed experimental installation paths share the same
original-file inventory, create-new write and ownership protections."""

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.game_process import GameProcessStatus, inspect_game_processes
from unitytranslator.json_boundary import strict_json
from unitytranslator.repository import ProjectRepository, canonical


@dataclass(frozen=True)
class PayloadFile:
    source: str
    target: str
    sha256: str


@dataclass(frozen=True)
class DeploymentPlan:
    id: str
    adapter: str
    adapter_version: str
    fingerprint: str
    files: tuple[PayloadFile, ...]


Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class OriginalInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format_version: Literal[1, 2]
    game: str
    files: dict[str, Digest] = Field(max_length=100_000)
    fingerprint: Digest
    exclusions: list["VolatileFile"] = Field(default_factory=list, max_length=1000)


class VolatileFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    kind: Literal["log", "save", "cache"]
    reason: str = Field(min_length=1, max_length=1000)


class FileReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str
    target: str
    sha256: Digest
    state: Literal["planned", "created", "installed", "removed", "missing"]
    device: int | None = None
    inode: int | None = None


class DeploymentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format_version: Literal[1]
    plan_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    adapter: str
    adapter_version: str
    fingerprint: Digest
    status: Literal["installing", "installed", "removed", "recovery_required"]
    files: list[FileReceipt] = Field(min_length=1, max_length=1000)


class GameNotClosedError(ValueError):
    pass


class DeploymentService:
    def __init__(
        self,
        repository: ProjectRepository,
        process_probe: Callable[[Path], GameProcessStatus] = inspect_game_processes,
        *,
        exclusions: tuple[VolatileFile, ...] = (),
        exclusions_reviewed: bool = False,
    ):
        self.paths = repository.paths
        self.repository = repository
        self.process_probe = process_probe
        if exclusions and exclusions_reviewed is not True:
            raise ValueError("Değişken veri dışlamaları açık kullanıcı seçimi gerektirir.")
        self.requested_exclusions = [rule.model_dump() for rule in exclusions]
        self.validate_exclusions(self.requested_exclusions)

    def validate_exclusions(self, rules: list[dict[str, Any]]) -> None:
        if len(rules) > 1000:
            raise ValueError("Dışlama dosyası sınırı aşıldı.")
        sources = {
            self.target(row[0]).as_posix().casefold()
            for row in self.repository.db.execute("SELECT DISTINCT source_file FROM text_units")
        }
        names = set()
        folders = {"log": "logs", "save": "saves", "cache": "cache"}
        extensions = {"log": {".log", ".txt"}, "save": {".sav"}, "cache": {".cache"}}
        for value in rules:
            rule = VolatileFile.model_validate(value)
            path = self.target(rule.path)
            if path.as_posix().casefold() in sources:
                raise ValueError("Çıkarılmış oyun kaynağı dışlanamaz.")
            relative = path.relative_to(self.paths.game)
            # Only narrow single-file rules; no wildcard/directory or Unity/loader exclusions.
            if (
                len(relative.parts) != 2
                or relative.parts[0].casefold() != folders[rule.kind]
                or relative.suffix.casefold() not in extensions[rule.kind]
                or not rule.reason.strip()
                or any(char in rule.path for char in "*?[]")
                or (path.exists() and not path.is_file())
            ):
                raise ValueError("Dışlama yalnızca tanımlı log/save/cache dosyası olabilir.")
            key = relative.as_posix().casefold()
            if key in names:
                raise ValueError("Dışlama yolu yineleniyor.")
            names.add(key)

    def read_baseline(self) -> dict[str, Any] | None:
        path = self.paths.output("artifacts/original-inventory.json")
        if not path.exists():
            return None
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Özgün envanter boyut sınırını aşıyor.")
        value = OriginalInventory.model_validate(strict_json(path.read_bytes())).model_dump()
        rules = value["exclusions"]
        self.validate_exclusions(rules)
        if (
            value["game"] != str(self.paths.game)
            or (value["format_version"] == 1 and rules)
            or value["fingerprint"] != self.fingerprint(value["files"], rules)
            or (self.requested_exclusions and self.requested_exclusions != rules)
        ):
            raise ValueError("Özgün envanter proje/oyun/dışlama bağlantısı geçersiz.")
        protected = {self.target(rule["path"]).as_posix().casefold() for rule in rules}
        for name in value["files"]:
            if self.target(name).as_posix().casefold() in protected:
                raise ValueError("Özgün dosya ve dışlama aynı yolu içeremez.")
        return value

    def exclusion_rules(self) -> list[dict[str, Any]]:
        baseline = self.read_baseline()
        return baseline["exclusions"] if baseline else self.requested_exclusions

    def excluded_observations(self) -> list[dict[str, Any]]:
        result = []
        for rule in self.exclusion_rules():
            path = self.target(rule["path"])
            result.append(
                {
                    **rule,
                    "state": "present" if path.exists() else "missing",
                    "bytes": path.stat().st_size if path.exists() else None,
                }
            )
        return result

    def protected_originals(self, baseline: dict[str, Any]) -> set[Path]:
        return {self.target(name) for name in baseline["files"]} | {
            self.target(rule["path"]) for rule in baseline["exclusions"]
        }

    def require_game_closed(self, manifest: dict[str, Any] | None = None) -> None:
        status = self.process_probe(self.paths.game)
        if status.status != "closed":
            if manifest is not None:
                manifest["status"] = "recovery_required"
                self.save_manifest(manifest)
            raise GameNotClosedError(
                "Oyun çalışıyor veya kapalı olduğu doğrulanamadı; dosya işlemi durdu. "
                "Oyunu kapatıp yeniden kontrol edin."
            )

    def target(self, relative: str) -> Path:
        part = Path(relative)
        if not relative or part.is_absolute() or part.drive or ".." in part.parts:
            raise ValueError("Uygulama hedefi güvenli ve göreli olmalı.")
        path = checked_path(self.paths.game / part)
        if not path.is_relative_to(self.paths.game) or path == self.paths.game:
            raise ValueError("Uygulama hedefi oyun kökü dışında.")
        return path

    def inventory(self) -> dict[str, str]:
        """Report mutable data separately; never silently exclude installation assets."""
        self.require_game_closed()
        excluded = {
            self.target(rule["path"]).as_posix().casefold() for rule in self.exclusion_rules()
        }
        result = {}
        for directory, subdirs, files in os.walk(self.paths.game, followlinks=False):
            for name in [*subdirs, *files]:
                checked_path(Path(directory) / name)
            for name in files:
                path = checked_path(Path(directory) / name)
                if path.as_posix().casefold() in excluded:
                    continue
                before = path.stat()
                digest = hash_file(path)
                after = path.stat()
                if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
                    after.st_ino,
                    after.st_dev,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    raise ValueError("Oyun dosyası envanter sırasında değişti; işlem durdu.")
                result[path.relative_to(self.paths.game).as_posix()] = digest
        self.require_game_closed()
        observations = self.excluded_observations()
        self.require_game_closed()
        self.paths.write_json("artifacts/volatile-data-observations.json", observations)
        return result

    def baseline(self) -> dict[str, Any]:
        value = self.read_baseline()
        if value is not None:
            return value
        files = self.inventory()
        value = {
            "format_version": 2 if self.requested_exclusions else 1,
            "game": str(self.paths.game),
            "files": files,
            "fingerprint": self.fingerprint(files, self.requested_exclusions),
            "exclusions": self.requested_exclusions,
        }
        OriginalInventory.model_validate(value)
        self.paths.write_json("artifacts/original-inventory.json", value)
        return value

    @staticmethod
    def fingerprint(files: dict[str, str], exclusions: list[dict[str, Any]] | None = None) -> str:
        content = {"files": files, "exclusions": exclusions} if exclusions else files
        return sha256(canonical(content).encode()).hexdigest()

    def original_changes(self) -> list[str]:
        baseline = self.baseline()
        changed = []
        for name, expected in baseline["files"].items():
            path = self.target(name)
            if not path.is_file() or hash_file(path) != expected:
                changed.append(name)
        self.require_game_closed()
        return changed

    def prepare(self, adapter: str, version: str, files: list[tuple[str, str]]) -> DeploymentPlan:
        if not adapter or not version or not 1 <= len(files) <= 1000:
            raise ValueError("Adaptör sürümü ve dosya listesi gerekli.")
        baseline = self.baseline()
        current = self.inventory()
        if current != baseline["files"]:
            raise ValueError("Oyun envanteri değişti; eski paket yeniden uygulanamaz.")
        payload = []
        names: set[str] = set()
        for source, target in files:
            path = self.target(target)
            if path in self.protected_originals(baseline):
                raise ValueError(
                    "Uygulama hedefi özgün veya dışlanan kullanıcı verisiyle çakışıyor."
                )
            normalized = path.relative_to(self.paths.game).as_posix().casefold()
            if normalized in names or path.exists():
                raise ValueError("Uygulama hedefi yineleniyor veya mevcut dosyayla çakışıyor.")
            names.add(normalized)
            source_path = self.paths.output(source)
            if not source_path.is_file():
                raise ValueError("Paket dosyası proje içinde bulunamadı.")
            for parent in path.parents:
                if parent == self.paths.game:
                    break
                if parent.exists() and not parent.is_dir():
                    raise ValueError("Uygulama hedefinin üst yolu dosyayla çakışıyor.")
            payload.append(PayloadFile(source, target, hash_file(source_path)))
        if any(a.startswith(b + "/") for a in names for b in names if a != b):
            raise ValueError("Dosya/dizin uygulama hedefleri çakışıyor.")
        plan = DeploymentPlan(
            uuid4().hex, adapter, version, baseline["fingerprint"], tuple(payload)
        )
        self.require_game_closed()
        self.paths.write_json(f"artifacts/plans/{plan.id}.json", asdict(plan))
        return plan

    def read_manifest(self) -> dict[str, Any] | None:
        path = self.paths.output("artifacts/deployment.json")
        if not path.exists():
            return None
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Uygulama manifesti boyut sınırını aşıyor.")
        manifest = DeploymentManifest.model_validate(strict_json(path.read_bytes())).model_dump()
        baseline = self.baseline()
        if manifest["fingerprint"] != baseline["fingerprint"]:
            raise ValueError("Uygulama manifesti özgün envanterle eşleşmiyor.")
        originals = self.protected_originals(baseline)
        recorded = strict_json(
            self.paths.output(f"artifacts/plans/{manifest['plan_id']}.json").read_bytes()
        )
        if (
            recorded["fingerprint"] != manifest["fingerprint"]
            or recorded["adapter"] != manifest["adapter"]
            or recorded["adapter_version"] != manifest["adapter_version"]
            or recorded["files"]
            != [
                {key: file[key] for key in ("source", "target", "sha256")}
                for file in manifest["files"]
            ]
        ):
            raise ValueError("Uygulama manifesti hazırlanan dosya planıyla eşleşmiyor.")
        for file in manifest["files"]:
            self.target(file["target"])
            if self.target(file["target"]) in originals:
                raise ValueError("Uygulama manifesti özgün dosyayı sahiplenemez.")
        return manifest

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        DeploymentManifest.model_validate(manifest)
        self.paths.write_json("artifacts/deployment.json", manifest)

    def activate(
        self, plan: DeploymentPlan, *, user_action: bool, adapter_verified: bool
    ) -> dict[str, Any]:
        if plan.adapter == "i2mono-experimental-trial":
            raise ValueError("Deneysel plan normal doğrulanmış adaptör yolundan kurulamaz.")
        if user_action is not True or adapter_verified is not True:
            raise ValueError(
                "Etkinleştirme açık kullanıcı eylemi ve doğrulanmış adaptör gerektirir."
            )
        return self._activate_checked(plan)

    def install_experimental_trial(
        self, plan: DeploymentPlan, *, user_action: bool, experimental_trial_reviewed: bool
    ) -> dict[str, Any]:
        """Explicit reviewed trial; does not establish normal adapter support or approval."""
        if user_action is not True or experimental_trial_reviewed is not True:
            raise ValueError("Deneysel kurulum ayrı, açık kullanıcı deneme seçimi gerektirir.")
        if (
            plan.adapter != "i2mono-experimental-trial"
            or plan.adapter_version != "1"
            or len(plan.files) != 2
            or {file.target for file in plan.files} != {"winhttp.dll", "doorstop_config.ini"}
        ):
            raise ValueError("Deneysel kurulum yalnızca sınırlı I2 deneme planını kabul eder.")
        return {
            **self._activate_checked(plan),
            "experimental": True,
            "application_verified": False,
        }

    def _activate_checked(self, plan: DeploymentPlan) -> dict[str, Any]:
        self.require_game_closed()
        old = self.read_manifest()
        if old is not None and old["status"] != "removed":
            raise ValueError("Önce eski uygulama eklerini kaldırın veya kurtarın.")
        # Compare the exact locally prepared plan; imported JSON is not installation authority.
        recorded = strict_json(self.paths.output(f"artifacts/plans/{plan.id}.json").read_bytes())
        if canonical(recorded) != canonical(asdict(plan)):
            raise ValueError("Plan hazırlamadan sonra değişti.")
        if self.fingerprint(self.inventory(), self.baseline()["exclusions"]) != plan.fingerprint:
            raise ValueError("Oyun hazırlamadan sonra değişti.")
        for file in plan.files:
            if (
                self.target(file.target).exists()
                or hash_file(self.paths.output(file.source)) != file.sha256
            ):
                raise ValueError("Paket veya hedef hazırlamadan sonra değişti.")
        manifest: dict[str, Any] = {
            "format_version": 1,
            "plan_id": plan.id,
            "adapter": plan.adapter,
            "adapter_version": plan.adapter_version,
            "fingerprint": plan.fingerprint,
            "status": "installing",
            "files": [asdict(f) | {"state": "planned"} for f in plan.files],
        }
        self.save_manifest(manifest)  # Persist the receipt before creating a game-root file.
        try:
            for item in manifest["files"]:
                self.require_game_closed(manifest)
                path = self.target(item["target"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path = self.target(item["target"])
                with path.open("xb") as output:
                    info = os.fstat(output.fileno())
                    item.update(state="created", device=info.st_dev, inode=info.st_ino)
                    self.save_manifest(
                        manifest
                    )  # Record file ownership before writing its contents.
                    with self.paths.output(item["source"]).open("rb") as source:
                        for block in iter(lambda: source.read(1024 * 1024), b""):
                            output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                if hash_file(path) != item["sha256"]:
                    raise ValueError("Eklenen dosya hash kontrolünü geçmedi.")
                item["state"] = "installed"
                self.save_manifest(manifest)
            changed = self.original_changes()
            if changed:
                raise ValueError("Özgün dosya değişikliği saptandı; etkinleştirme doğrulanmadı.")
            self.require_game_closed(manifest)
            manifest["status"] = "installed"
            self.save_manifest(manifest)
            return {
                "status": "installed",
                "original_changes": [],
                "excluded_observations": self.excluded_observations(),
            }
        except Exception:
            # Report partial file/hash/receipt failures; never restore over an original file.
            try:
                self._remove_owned(manifest)
            except GameNotClosedError:
                manifest["status"] = "recovery_required"
                self.save_manifest(manifest)
            raise

    def _remove_owned(self, manifest: dict[str, Any]) -> dict[str, Any]:
        DeploymentManifest.model_validate(manifest)
        self.require_game_closed(manifest)
        originals = self.protected_originals(self.baseline())
        if any(self.target(item["target"]) in originals for item in manifest["files"]):
            raise ValueError("Kaldırma manifesti özgün dosyayı sahiplenemez.")
        removed = []
        preserved = []
        for item in reversed(manifest["files"]):
            self.require_game_closed(manifest)
            path = self.target(item["target"])
            if not path.exists():
                item["state"] = "missing"
                continue
            info = path.stat()
            if (
                item["state"] not in ("created", "installed")
                or not path.is_file()
                or info.st_nlink != 1
                or info.st_dev != item.get("device")
                or info.st_ino != item.get("inode")
                or hash_file(path) != item["sha256"]
            ):
                preserved.append(item["target"])
                continue
            self.require_game_closed(manifest)
            path.unlink()
            item["state"] = "removed"
            removed.append(item["target"])
            self.save_manifest(manifest)
        try:
            changed = self.original_changes()
            self.require_game_closed(manifest)
        except GameNotClosedError:
            manifest["status"] = "recovery_required"
            self.save_manifest(manifest)
            raise
        manifest["status"] = "recovery_required" if preserved or changed else "removed"
        self.save_manifest(manifest)
        return {
            "status": manifest["status"],
            "removed": removed,
            "preserved": preserved,
            "original_changes": changed,
            "excluded_observations": self.excluded_observations(),
        }

    def uninstall(self, *, user_action: bool) -> dict[str, Any]:
        if not user_action:
            raise ValueError("Kaldırma/kurtarma açık kullanıcı eylemi gerektirir.")
        self.require_game_closed()
        manifest = self.read_manifest()
        if manifest is None:
            raise ValueError("Kaldırılacak sahiplik manifesti bulunamadı.")
        return self._remove_owned(manifest)
