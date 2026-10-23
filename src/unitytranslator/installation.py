"""End-user installation through the shared inventory and ownership gates."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.deployment import DeploymentService, VolatileFile
from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.i2_activation import install_reviewed_trial, prepare_activation_review
from unitytranslator.i2_trial import prepare_i2_trial
from unitytranslator.krypta_profile import load_profile
from unitytranslator.krypta_runtime import KryptaRuntimeKit
from unitytranslator.krypta_trial import install_krypta_review, prepare_krypta_review
from unitytranslator.language import language_name
from unitytranslator.repository import ProjectRepository
from unitytranslator.runtime_export import export_selected_runtime
from unitytranslator.runtime_kit import RuntimeKit


class InstallationSession:
    def __init__(self, repo: ProjectRepository):
        self.repo = repo
        self.pending: dict[str, Any] | None = None

    def adapter_kind(self) -> str:
        adapters = {
            row[0]
            for row in self.repo.db.execute(
                "SELECT DISTINCT d.adapter_id FROM text_units u "
                "JOIN source_descriptors d ON d.id=u.logical_source_id WHERE u.active=1"
            )
        }
        if not adapters or adapters == {"i2"}:
            return "i2"
        if adapters == {"krypta-textassets"}:
            return "krypta"
        return "unsupported"

    def require_installation_adapter(self) -> None:
        kind = self.adapter_kind()
        if kind == "unsupported" or (
            kind == "krypta" and KryptaRuntimeKit().catalog.get("ui_trial_enabled") is not True
        ):
            raise ValueError(
                "This source adapter supports staged text exports only; game installation "
                "is not implemented."
            )

    def status(self) -> dict[str, Any]:
        service = DeploymentService(self.repo)
        baseline, manifest = service.read_baseline(), service.read_manifest()
        count = self.repo.db.execute(
            "SELECT count(*) FROM work_items w JOIN text_units u USING(unit_id) "
            "WHERE u.active=1 AND w.status='approved' AND w.approved_source=u.source_revision "
            "AND w.approved_translation=w.translation_revision"
        ).fetchone()[0]
        try:
            self.require_installation_adapter()
            kit: RuntimeKit = (
                KryptaRuntimeKit() if self.adapter_kind() == "krypta" else RuntimeKit()
            )
            available, reason = kit.root.is_dir(), ""
            if not available:
                reason = "Bu pakette runtime dosyaları eksik. Tam Windows paketini kullanın."
            else:
                if self.adapter_kind() == "krypta":
                    assembly_relative = load_profile()["assembly"]["path"]
                else:
                    candidates = list(
                        self.repo.paths.game.glob("*_Data/Managed/Assembly-CSharp.dll")
                    )
                    if len(candidates) != 1:
                        raise ValueError("Bu oyun yapısıyla eşleşen uygulama adaptörü bulunmuyor.")
                    assembly_relative = candidates[0].relative_to(self.repo.paths.game).as_posix()
                kit.check_game(self.repo, assembly_relative)
        except ValueError as exc:
            available, reason = False, str(exc)
        except OSError:
            available, reason = (
                False,
                "Oyunun çalışma dosyaları okunamadı veya adaptörle eşleşmiyor.",
            )
        return {
            "project_id": self.repo.project_id,
            "approved": count,
            "kit_available": available,
            "kit_reason": reason,
            "baseline_exists": baseline is not None,
            "exclusions": service.exclusion_rules(),
            "deployment": manifest,
            "application_verified": False,
        }

    def prepare(
        self,
        *,
        log_file: str = "",
        log_reviewed: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        self.pending = None
        self.require_installation_adapter()

        def notify(message: str) -> None:
            if progress:
                progress(message)

        notify("Onaylı çeviriler ve uygulama bileşenleri kontrol ediliyor…")
        service = DeploymentService(self.repo)
        if service.read_baseline() is None and log_file:
            service = DeploymentService(
                self.repo,
                exclusions=(
                    VolatileFile(
                        path=log_file,
                        kind="log",
                        reason="Kullanıcı bu günlük dosyasını ayrı izlemeyi seçti.",
                    ),
                ),
                exclusions_reviewed=log_reviewed,
            )
        elif log_file:
            raise ValueError("Önceki özgün envanter korunur; yeni dışlama eklenemez.")
        service.require_game_closed()
        manifest = service.read_manifest()
        if manifest and manifest["status"] != "removed":
            raise ValueError("Önce mevcut ekleri kaldırın veya yarım kurulumu kurtarın.")
        # Check before staging or capturing the original inventory: another project's
        # loader must never become an 'original game file' in this project.
        conflicts = [
            name
            for name in ("winhttp.dll", "doorstop_config.ini")
            if checked_path(self.repo.paths.game / name).exists()
        ]
        if conflicts:
            raise ValueError(
                "Oyun klasöründe mevcut yükleyici dosyaları var: "
                + ", ".join(conflicts)
                + ". Üzerlerine yazılmaz. Önce bu kurulumu oluşturan projeyi açıp "
                "Oyuna uygula bölümünden sahiplik kontrolüyle kaldırın. Dosyalar başka "
                "bir moda aitse o modun kaldırma yöntemini kullanın."
            )
        records = [
            dict(row)
            for row in self.repo.db.execute(
                "SELECT u.unit_id,u.source_revision,w.translation_revision,w.version "
                "FROM text_units u JOIN work_items w USING(unit_id) WHERE u.active=1 "
                "AND w.status='approved' ORDER BY u.unit_id LIMIT 100001"
            )
        ]
        if self.adapter_kind() == "krypta":
            kit_krypta = KryptaRuntimeKit()
            kit_krypta.validate()
            kit_krypta.check_game(self.repo, load_profile()["assembly"]["path"])
            review_krypta = prepare_krypta_review(
                self.repo,
                kit_krypta,
                records,
                service=service,
            )
            self.pending = {
                "review_id": uuid4().hex,
                "adapter_kind": "krypta",
                "review_relative": review_krypta["review_relative"],
                "review_sha256": review_krypta["review_sha256"],
            }
            baseline_krypta = service.read_baseline()
            assert baseline_krypta is not None
            return {
                "project_id": self.repo.project_id,
                **self.pending,
                "records": len(records),
                "original_files": len(baseline_krypta["files"]),
                "exclusions": service.exclusion_rules(),
                "files": review_krypta["plan"]["files"],
                "game": str(self.repo.paths.game),
                "application_verified": False,
            }
        context = export_selected_runtime(self.repo, records, record_limit=100_000)
        self.check_sources(context["source_fingerprints"])
        kit = RuntimeKit()
        staged = kit.stage(self.repo, context["assembly_relative"])
        notify("Özgün dosyaların SHA-256 envanteri kontrol ediliyor. Büyük oyunlarda bu sürebilir…")
        baseline = service.baseline()
        trial = prepare_i2_trial(
            self.repo,
            **staged,
            source_set=context["source_set"],
            unity_version=context["unity_version"],
            assembly_relative=context["assembly_relative"],
            target_name=language_name(self.repo.target_language),
            selected_unit_ids={row["unit_id"] for row in records},
            record_limit=100_000,
        )
        trial_relative = Path(trial["manifest"]).relative_to(self.repo.paths.project).as_posix()
        review = prepare_activation_review(self.repo, trial_relative, service)
        self.pending = {
            "review_id": uuid4().hex,
            "review_relative": review["review_relative"],
            "review_sha256": hash_file(self.repo.paths.output(review["review_relative"])),
            "assembly_relative": context["assembly_relative"],
            "source_fingerprints": context["source_fingerprints"],
        }
        return {
            "project_id": self.repo.project_id,
            **self.pending,
            "records": len(records),
            "original_files": len(baseline["files"]),
            "exclusions": service.exclusion_rules(),
            "files": review["plan"]["files"],
            "game": str(self.repo.paths.game),
            "application_verified": False,
        }

    def install(
        self, review_id: str, *, user_action: bool, experimental_reviewed: bool
    ) -> dict[str, Any]:
        if user_action is not True or experimental_reviewed is not True:
            raise ValueError(
                "Kurulum açık kullanıcı seçimi ve deneysel kapsam incelemesi gerektirir."
            )
        pending = self.pending
        if (
            not pending
            or review_id != pending["review_id"]
            or hash_file(self.repo.paths.output(pending["review_relative"]))
            != pending["review_sha256"]
        ):
            raise ValueError("Kurulum incelemesi eski veya değişmiş; yeniden hazırlayın.")
        if pending.get("adapter_kind") == "krypta":
            self.require_installation_adapter()
            result_krypta = install_krypta_review(
                self.repo,
                KryptaRuntimeKit(),
                pending["review_relative"],
                pending["review_sha256"],
                user_action=user_action,
                experimental_reviewed=experimental_reviewed,
                service=DeploymentService(self.repo),
            )
            self.pending = None
            return result_krypta
        RuntimeKit().check_game(self.repo, pending["assembly_relative"])
        self.check_sources(pending["source_fingerprints"])
        result = install_reviewed_trial(
            self.repo,
            pending["review_relative"],
            DeploymentService(self.repo),
            user_action=user_action,
            experimental_trial_reviewed=experimental_reviewed,
        )
        self.pending = None
        return result

    def check_sources(self, fingerprints: dict[str, str | None]) -> None:
        if not fingerprints:
            raise ValueError("Kaynak doğrulaması eksik; metinleri yeniden çıkarın.")
        for relative, expected in fingerprints.items():
            source = checked_path(self.repo.paths.game / relative)
            if (
                not expected
                or not source.is_relative_to(self.repo.paths.game)
                or hash_file(source) != expected
            ):
                raise ValueError("Oyun kaynağı değişmiş veya eski; metinleri yeniden çıkarın.")

    def remove(self, plan_id: str, *, user_action: bool) -> dict[str, Any]:
        if user_action is not True:
            raise ValueError("Kaldırma açık kullanıcı işlemi gerektirir.")
        service = DeploymentService(self.repo)
        manifest = service.read_manifest()
        if not manifest or manifest["plan_id"] != plan_id:
            raise ValueError("Kaldırma planı değişmiş; durumu yenileyin.")
        result = service.uninstall(user_action=True)
        self.pending = None
        return result
