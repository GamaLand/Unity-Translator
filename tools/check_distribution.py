"""Wheel/sdist içerik denetimi. Standalone DLL'leri bu denetimin konusu değildir."""

import tarfile
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    archives = [*root.glob("dist/*.whl"), *root.glob("dist/*.tar.gz")]
    if not archives:
        raise ValueError("Önce uv build ile wheel/sdist üretin.")
    private = {
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
    }
    private_names = {
        "agents.md",
        "claude.md",
        "gemini.md",
        "goal.md",
        "technical_design.md",
        ".cursorrules",
        ".windsurfrules",
        "copilot-instructions.md",
        ".env",
    }
    extensions = (".gguf", ".assets", ".sqlite3", ".ress", ".dll")
    for archive in archives:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as stream:
                names = stream.namelist()
        else:
            with tarfile.open(archive, "r:gz") as tar:
                names = tar.getnames()
                if any(item.issym() or item.islnk() for item in tar.getmembers()):
                    raise ValueError("Kaynak arşivinde bağlantı girdisi bulundu.")
        forbidden = [
            name
            for name in names
            if (
                any(part.casefold() in private for part in name.replace("\\", "/").split("/"))
                or Path(name).name.casefold() in private_names
                or Path(name).name.casefold().startswith(".env.")
                or name.casefold().endswith(extensions)
            )
        ]
        if forbidden:
            raise ValueError(f"{archive.name} içinde özel/binary veri bulundu: {forbidden[:5]}")
        for code in ("en", "tr", "de", "fr", "es", "pt", "ru", "zh"):
            if not any(name.endswith("/locales/" + code + ".json") for name in names):
                raise ValueError("Missing interface language: " + code)
            if archive.suffix != ".whl" and not any(
                name.endswith("/rehber/" + code + ".md") for name in names
            ):
                raise ValueError("Missing user guide: " + code)
        print(f"{archive.name}: {len(names)} girdi; özel oyun/model/önbellek dosyası yok.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
