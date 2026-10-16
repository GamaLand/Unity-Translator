"""pyside6-deploy ile standalone; yalnızca özel üretilmiş spec değiştirilebilir."""

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

from unitytranslator.filesystem import checked_path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = checked_path(root / "dist" / "windows" / "UnityTranslator.dist")
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Derleme hedefi çalışma alanı dışında.")
    if target.exists():
        for entry in target.rglob("*"):
            checked_path(entry)
        shutil.rmtree(target)
    config = configparser.ConfigParser()
    config.read(root / "pysidedeploy.spec", encoding="utf-8")
    for name in ("project_dir", "input_file", "exec_directory"):
        config["app"][name] = str(root / config["app"][name])
    config["app"]["icon"] = ""
    private = root / ".cache" / "pysidedeploy.local.spec"
    private.parent.mkdir(exist_ok=True)
    with private.open("w", encoding="utf-8") as stream:
        config.write(stream)
    environment = os.environ.copy()
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    environment["NUITKA_CACHE_DIR"] = str(root / ".cache" / "nuitka")
    environment["TEMP"] = environment["TMP"] = str(root / ".cache")
    command = [
        str(Path(sys.executable).parent / "pyside6-deploy.exe"),
        "--config-file",
        str(private),
        "--mode",
        "standalone",
        "--no-install",
        "--force",
        "--keep-deployment-files",
    ]
    result = subprocess.run(command, cwd=root, env=environment, check=False)
    if result.returncode:
        return result.returncode
    # Qt'nin otomatik gelen PDF image plugin'i bu uygulamada kullanılmaz.
    # Yalnızca yeni üretilmiş paket içindeki bu iki dosya kaldırılır.
    for entry in target.rglob("*"):
        if entry.name.casefold() in {"qpdf.dll", "qt6pdf.dll"}:
            path = checked_path(entry)
            if not path.is_relative_to(target) or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError("Üretilmiş PDF bileşeni güvenle ayrılamadı.")
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
