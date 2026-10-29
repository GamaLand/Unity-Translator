"""Read-only discovery services shared by the CLI and desktop application."""

import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from unitytranslator.capabilities import discovery_capabilities
from unitytranslator.engines import engine_evidence, renpy_inputs
from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.profiles import match_profile
from unitytranslator.repository import ProjectRepository


def scan(paths: ProjectPaths, *, engine: str = "auto") -> dict[str, Any]:
    engines = engine_evidence(paths.game, engine)
    evidence = []
    candidates = []
    runtimes: set[str] = set()
    recommendations = []
    for data in sorted(paths.game.glob("*_Data")):
        checked_path(data)
        if not data.is_dir():
            continue
        info = data / "app.info"
        if info.is_file() and info.stat().st_size <= 4096:
            lines = checked_path(info).read_text(encoding="utf-8-sig").splitlines()
            if len(lines) >= 2:
                profile = match_profile(lines[0], lines[1])
                if profile is not None and (data / profile.source_hint).is_file():
                    recommendations.append(
                        {
                            "profile": profile.id,
                            "source": (data / profile.source_hint)
                            .relative_to(paths.game)
                            .as_posix(),
                            "status": "unverified_hint",
                        }
                    )
        for name in (
            "app.info",
            "Managed/Assembly-CSharp.dll",
            "Managed/Assembly-CSharp-firstpass.dll",
            "il2cpp_data/Metadata/global-metadata.dat",
        ):
            file = checked_path(data / name)
            if file.is_file():
                evidence.append(
                    {
                        "path": file.relative_to(paths.game).as_posix(),
                        "size": file.stat().st_size,
                        "sha256": hash_file(file),
                    }
                )
                if name.startswith("Managed/"):
                    runtimes.add("Mono")
                if name.startswith("il2cpp_data/"):
                    runtimes.add("IL2CPP")
        for file in sorted(data.iterdir()):
            checked_path(file)
            if file.is_file() and (
                file.suffix == ".assets"
                or file.name == "globalgamemanagers"
                or re.fullmatch(r"level\d+", file.name)
            ):
                candidates.append(
                    {"path": file.relative_to(paths.game).as_posix(), "size": file.stat().st_size}
                )
    report = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "runtime_indicators": sorted(runtimes),
        "evidence": evidence,
        "source_candidates": candidates,
        "extraction": "unknown",
        "application": "unknown",
        "uncertainties": [
            "Dosya adayları metin kaynağı olduğunu kanıtlamaz.",
            "Runtime göstergeleri kesin çalışma uyumluluğu değildir.",
            "Haricî dil/mod ve font desteği henüz doğrulanmadı.",
        ],
        "recommendations": recommendations,
        "engine_report": engines,
    }
    if "renpy" in engines["detected"] or engines["engine"] == "renpy":
        inputs = renpy_inputs(paths.game)
        report["renpy_inputs"] = inputs
        report["container_indicators"] = inputs["container_indicators"] + (
            ["serialized_asset_candidate"] if candidates else []
        )
    report["capabilities"] = discovery_capabilities(report).to_dict()
    return report


def _probe_i2_source(
    paths: ProjectPaths, relative: str, timeout: float = 120, *, source_language: str = "en"
) -> dict[str, Any]:
    part = Path(relative)
    if part.is_absolute() or part.drive:
        raise ValueError("Kaynak yolu oyun köküne göreli olmalı.")
    source = checked_path(paths.game / part)
    if not source.is_relative_to(paths.game) or not source.is_file():
        raise ValueError("Kaynak oyun klasöründe bir dosya olmalı.")
    before = hash_file(source)
    worker = (
        [sys.executable, "--unity-worker"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "unitytranslator.workers.unity_probe"]
    )
    completed = subprocess.run(
        [
            *worker,
            str(source),
            source.relative_to(paths.game).as_posix(),
            str(paths.game),
            source_language,
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=timeout,
        check=False,
    )
    if hash_file(source) != before:
        raise ValueError("Kaynak hash'i inceleme sırasında değişti; sonuç kabul edilmedi.")
    if completed.returncode:
        raise ValueError(f"Unity okuma alt süreci başarısız: {completed.returncode}")
    if len(completed.stdout) > 32 * 1024 * 1024:
        raise ValueError("Keşif IPC boyut sınırı aşıldı.")
    result: dict[str, Any] = json.loads(completed.stdout)
    ids = [unit["unit_id"] for unit in result["units"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Belirsiz kaynak kümesi: yinelenen mantıksal kimlik.")
    result.update(
        {
            "format_version": 1,
            "source": relative,
            "sha256_before": before,
            "sha256_after": before,
            "application": "unknown",
            "extraction": "supported" if result["units"] and not result["errors"] else "unknown",
        }
    )
    result["counts"] = {
        "records": len(ids),
        "unique_texts": len({u["source_text"] for u in result["units"]}),
        "characters": sum(len(u["source_text"]) for u in result["units"]),
        "errors": len(result["errors"]),
        "diagnostics": dict(Counter(item["code"] for item in result.get("diagnostics", []))),
    }
    result["capabilities"] = discovery_capabilities(result, inspected=True).to_dict()
    return result


def probe_source(
    paths: ProjectPaths, relative: str, timeout: float = 120, *, source_language: str = "en",
    cancellation: Callable[[], bool] | None = None,
    engine: str = "auto",
) -> dict[str, Any]:
    from unitytranslator.reader_adapters import BUILTIN_READERS
    from unitytranslator.source_contracts import ReaderContext, validate_relative_source

    validate_relative_source(relative)
    source = checked_path(paths.game / relative)
    if not source.is_relative_to(paths.game) or not source.is_file():
        raise ValueError("Source must be an existing file inside the game directory.")
    engines = engine_evidence(paths.game, engine)
    if engines["engine"] == "ambiguous":
        raise ValueError("Ambiguous engine evidence; select an explicit inspection engine.")
    if (
        engines["engine"] == "renpy" and source.suffix.lower() == ".rpy"
        and Path(relative).parts[:2] == ("game", "tl")
    ):
        return BUILTIN_READERS.select(("renpy-templates",)).probe(
            ReaderContext(
                paths.game, paths.project, source_language, timeout, cancellation or (lambda: False)
            ), relative,
        ).report
    if (
        engines["engine"] == "renpy" and (
            source.suffix.lower() in (".rpy", ".rpa") or source.name.endswith("_ren.py")
        )
        and Path(relative).parts[0] == "game"
    ):
        return BUILTIN_READERS.select(("renpy-scripts",)).probe(
            ReaderContext(
                paths.game, paths.project, source_language, timeout, cancellation or (lambda: False)
            ), relative,
        ).report
    if source.name.lower().endswith("_ren.py"):
        raise ValueError(
            "Ren'Py input detected: _ren.py is a separate unsupported source dialect; "
            "native text mapping has not been verified. No Python file is executed."
        )
    if engines["engine"] == "renpy" or source.suffix.lower() in (".rpy", ".rpyc", ".rpa"):
        raise ValueError(
            "Ren'Py input detected. Select a supported loose game/tl/<language>/*.rpy template; "
            "or a supported original .rpy/RPA-3.0 source. Compiled-only reading is unsupported."
        )
    if engines["engine"] == "unknown" and not (
        source.suffix.lower() == ".assets"
        or source.name == "globalgamemanagers"
        or re.fullmatch(r"level\d+", source.name)
    ):
        raise ValueError("No engine or built-in reader matches this source; select an engine.")
    reader_id = "i2"
    info = checked_path(paths.game / Path(relative).parts[0] / "app.info")
    if info.is_file() and info.stat().st_size <= 4096:
        lines = info.read_text(encoding="utf-8-sig").splitlines()
        if len(lines) >= 2 and (profile := match_profile(lines[0], lines[1])) is not None:
            reader_id = profile.reader_id
    reader = BUILTIN_READERS.select((reader_id,))
    return reader.probe(
        ReaderContext(
            paths.game, paths.project, source_language, timeout, cancellation or (lambda: False)
        ),
        relative,
    ).report


def save_report(paths: ProjectPaths, kind: str, report: dict[str, Any]) -> Path:
    return paths.write_json(f"snapshots/{kind}-{uuid4().hex}.json", report)


def validate_source_selection(repository: ProjectRepository, report: dict[str, Any]) -> None:
    """Missing Ren'Py templates require a separate decision, never silent retirement."""
    if report.get("adapter_id") not in ("renpy-templates", "renpy-scripts"):
        return
    profiles = {source["profile_id"] for source in report["source_descriptors"]}
    active_profiles = {
        row[0] for row in repository.db.execute(
            "SELECT DISTINCT profile_id FROM source_descriptors "
            "WHERE adapter_id IN ('renpy-templates','renpy-scripts') AND active=1"
        )
    }
    if active_profiles - profiles:
        raise ValueError("This project already has another active Ren'Py template language set.")
    incoming = {source["logical_id"] for source in report["source_descriptors"]}
    existing = {
        row["id"] for row in repository.db.execute(
            "SELECT id,profile_id FROM source_descriptors "
            "WHERE adapter_id IN ('renpy-templates','renpy-scripts') AND active=1"
        ) if row["profile_id"] in profiles
    }
    if missing := existing - incoming:
        raise ValueError(
            "Previously active Ren'Py templates are missing: " + ", ".join(sorted(missing))
        )
    if report["adapter_id"] == "renpy-scripts":
        payloads = {payload["logical_id"]: payload for payload in report["payloads"]}
        for logical in existing & incoming:
            previous = repository.db.execute(
                "SELECT ss.metadata_json FROM snapshot_sources s "
                "JOIN source_snapshots ss ON ss.id=s.snapshot_id WHERE s.source_id=? "
                "ORDER BY ss.created_at DESC,ss.rowid DESC LIMIT 1", (logical,),
            ).fetchone()
            if previous is None:
                continue
            old = {member["name"] for member in json.loads(previous[0]).get("original_members", ())}
            new = {member["name"] for member in payloads[logical]["original_members"]}
            if old - new:
                raise ValueError("Previously active Ren'Py original-source members are missing.")


def extract_to_project(
    paths: ProjectPaths, relative: str, *, engine: str = "auto"
) -> dict[str, Any]:
    # Hold the writer lock during extraction, but no transaction while the worker runs.
    with ProjectRepository(paths) as repository:
        report = probe_source(
            paths, relative, source_language=repository.source_language, engine=engine
        )
        output = save_report(paths, "extract", report)
        if report["extraction"] != "supported":
            raise ValueError(f"Çıkarma tamamlanamadı; tanı raporu: {output}")
        from unitytranslator.reader_adapters import result_from_report

        validate_source_selection(repository, report)
        snapshot = repository.ingest_reader_result(result_from_report(
            report, replace_source_set=report.get("complete_source_set") is True
        ))[0]
        return {
            "snapshot": snapshot,
            "report": str(output),
            "counts": report["counts"],
            "extraction": report["extraction"],
            "application": report["application"],
            "capabilities": report["capabilities"],
        }
