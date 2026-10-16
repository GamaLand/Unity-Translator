"""Hash envanterini doğrulayarak yeni standalone ZIP ve SHA-256 üretir."""

import argparse
import json
import os
import re
import tempfile
import tomllib
import zipfile
from hashlib import sha256
from pathlib import Path, PurePosixPath

from unitytranslator.filesystem import checked_path, hash_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Örneğin preview.3")
    label = parser.parse_args().label
    if not re.fullmatch(r"[a-z][a-z0-9.-]{0,39}", label):
        raise ValueError("Geçersiz paket etiketi.")
    root = Path(__file__).resolve().parents[1]
    output = checked_path(root / "dist/windows")
    package = checked_path(output / "UnityTranslator.dist")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    destination = checked_path(output / f"UnityTranslator-{version}-{label}-win-x64.zip")
    digest_path = checked_path(Path(str(destination) + ".sha256"))
    if destination.exists() or digest_path.exists():
        raise ValueError("Mevcut önizleme paketi üzerine yazılmaz; yeni etiket seçin.")
    entries = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    paths = {}
    for entry in entries:
        name = entry["path"]
        relative = PurePosixPath(name)
        if (
            name in paths
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or ":" in name
            or any(
                part.casefold() in {".local", ".cache", ".python", ".venv", "deployment"}
                for part in relative.parts
            )
            or relative.suffix.casefold() in {".gguf", ".assets", ".sqlite3", ".ress"}
            or name == "PACKAGE-MANIFEST.json"
        ):
            raise ValueError("Paket envanteri güvenli değil.")
        path = checked_path(package / name)
        if not path.is_relative_to(package) or not path.is_file():
            raise ValueError("Envanter dosyası eksik veya paket dışında.")
        if path.stat().st_size != entry["bytes"] or hash_file(path) != entry["sha256"]:
            raise ValueError("Dosya lisans/hash envanterinden sonra değişti.")
        paths[name] = path
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()}
    if actual != set(paths):
        raise ValueError("Dağıtım dosyaları envanterle eşleşmiyor.")
    prefix = "UnityTranslator.dist/"
    with tempfile.NamedTemporaryFile(
        dir=output, prefix="package-", suffix=".zip", delete=False
    ) as stream:
        temporary = checked_path(Path(stream.name))
    # Başarısız üretim geçici çıktıyı bırakır; final adı yalnızca doğrulama sonrası oluşur.
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in paths.items():
            archive.write(path, prefix + name)
        archive.writestr(prefix + "PACKAGE-MANIFEST.json", json.dumps(entries, indent=2))
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC doğrulaması başarısız.")
        expected = {prefix + name for name in paths} | {prefix + "PACKAGE-MANIFEST.json"}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError("ZIP girdileri envanterle eşleşmiyor.")
        for entry in entries:
            digest = sha256()
            with archive.open(prefix + entry["path"]) as member:
                for block in iter(lambda: member.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != entry["sha256"]:
                raise ValueError("ZIP dosya içeriği envanterle eşleşmiyor.")
    # Windows rename var olan hedefi değiştirmez; POSIX'te create-new link kullanılır.
    if os.name == "nt":
        temporary.rename(destination)
    else:
        os.link(temporary, destination)
        temporary.unlink()
    digest = hash_file(destination)
    with digest_path.open("x", encoding="ascii") as stream:
        stream.write(f"{digest}  {destination.name}\n")
    print(
        json.dumps(
            {
                "file": destination.name,
                "bytes": destination.stat().st_size,
                "sha256": digest,
                "zip_entries": len(expected),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
