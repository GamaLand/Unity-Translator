"""Package official Qt/PySide source archives with pinned source hashes."""

import argparse
import json
import tomllib
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx

from unitytranslator.filesystem import checked_path, hash_file
from unitytranslator.json_boundary import strict_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=root / "dist/windows")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download missing official sources; never uploads game or model data",
    )
    args = parser.parse_args()
    output = checked_path(args.output_root)
    if not output.is_relative_to(root / "dist"):
        raise ValueError("Source package output must be under the workspace dist folder.")
    output.mkdir(parents=True, exist_ok=True)
    catalog = strict_json((root / "adapters/qt-source-catalog.json").read_bytes())
    cache = checked_path(root / ".cache/dependency-sources")
    cache.mkdir(parents=True, exist_ok=True)
    paths = {}
    for item in catalog["archives"]:
        if Path(item["file"]).name != item["file"] or not item["url"].startswith(
            "https://download.qt.io/"
        ):
            raise ValueError("Kaynak katalog yolu geçersiz.")
        target = checked_path(cache / item["file"])
        if not target.exists():
            if not args.download:
                raise ValueError("Eksik kaynak arşivi; geliştirici --download seçebilir.")
            temporary = checked_path(cache / ("download-" + uuid4().hex))
            with httpx.Client(follow_redirects=True, trust_env=False, timeout=60) as client:
                with client.stream("GET", item["url"]) as response:
                    response.raise_for_status()
                    received = 0
                    with temporary.open("xb") as stream:
                        for block in response.iter_bytes(1024 * 1024):
                            received += len(block)
                            if received > item["bytes"]:
                                raise ValueError("Kaynak arşivi boyut sınırını aştı.")
                            stream.write(block)
            if temporary.stat().st_size != item["bytes"] or hash_file(temporary) != item["sha256"]:
                raise ValueError("İndirilen kaynak resmî hash ile eşleşmiyor.")
            temporary.rename(target)
        if target.stat().st_size != item["bytes"] or hash_file(target) != item["sha256"]:
            raise ValueError("Kaynak önbelleği değişmiş.")
        paths[item["file"]] = target
        print(json.dumps({"verified_source": item["file"], "bytes": item["bytes"]}), flush=True)
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    destination = checked_path(
        output / f"UnityTranslator-{version}-dependency-sources.zip"
    )
    if destination.exists():
        raise ValueError("Mevcut kaynak teslimi üzerine yazılmaz.")
    temporary = destination.parent / ("sources-" + uuid4().hex + ".zip")
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, source in paths.items():
            archive.write(source, name)
        archive.writestr("SOURCE-MANIFEST.json", json.dumps(catalog, indent=2))
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(paths) + 1:
            raise ValueError("Kaynak ZIP doğrulaması başarısız.")
    temporary.rename(destination)
    print(
        json.dumps(
            {
                "file": destination.name,
                "bytes": destination.stat().st_size,
                "sha256": hash_file(destination),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
