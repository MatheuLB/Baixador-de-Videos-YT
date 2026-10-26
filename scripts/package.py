"""Empacota o resultado do PyInstaller (pasta dist/) no formato de cada sistema.

- Windows: instalador .exe (Inno Setup) + .zip portátil
- macOS:   .dmg com atalho para a pasta Aplicativos
- Linux:   AppImage + .tar.gz com script de instalação

Uso (depois de `pyinstaller --noconfirm --clean baixador.spec`):
    python scripts/package.py
Os arquivos finais ficam em dist/release/.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from baixador import APP_DISPLAY_NAME, APP_NAME, __version__  # noqa: E402

DIST = ROOT / "dist"
OUT = DIST / "release"
PACKAGING = ROOT / "packaging"


def arch_label() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def run(cmd: list, **kwargs) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------


def find_iscc() -> str | None:
    found = shutil.which("iscc")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def package_windows() -> None:
    source = DIST / APP_NAME
    portable = OUT / f"{APP_NAME}-{__version__}-windows-x64-portatil"
    shutil.make_archive(str(portable), "zip", DIST, APP_NAME)

    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup não encontrado: gerei só a versão portátil (.zip).")
        return
    run([
        iscc,
        f"/DAppVersion={__version__}",
        f"/DSourceDir={source}",
        f"/DOutputDir={OUT}",
        f"/DIconFile={ROOT / 'assets' / 'icon.ico'}",
        PACKAGING / "windows" / "installer.iss",
    ])


# --------------------------------------------------------------------------
# macOS
# --------------------------------------------------------------------------


def package_macos() -> None:
    app = DIST / f"{APP_NAME}.app"
    # Assinatura "ad-hoc": não substitui a da Apple, mas é obrigatória no Apple Silicon.
    run(["codesign", "--force", "--deep", "--sign", "-", app])

    staging = DIST / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    shutil.copytree(app, staging / app.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")

    dmg = OUT / f"{APP_NAME}-{__version__}-macos-{arch_label()}.dmg"
    run([
        "hdiutil", "create",
        "-volname", APP_DISPLAY_NAME,
        "-srcfolder", staging,
        "-ov", "-format", "UDZO",
        dmg,
    ])


# --------------------------------------------------------------------------
# Linux
# --------------------------------------------------------------------------


def package_linux() -> None:
    arch = arch_label()
    linux = PACKAGING / "linux"

    # .tar.gz: o app + script que instala no menu do usuário.
    folder_name = f"{APP_NAME}-{__version__}"
    staging = DIST / "linux" / folder_name
    shutil.rmtree(staging.parent, ignore_errors=True)
    shutil.copytree(DIST / APP_NAME, staging, symlinks=True)
    shutil.copy(linux / "baixador.desktop", staging / "baixador.desktop")
    shutil.copy(ROOT / "assets" / "icon.png", staging / "baixador.png")
    shutil.copy(linux / "install.sh", staging / "install.sh")
    make_executable(staging / "install.sh")
    tar_path = OUT / f"{APP_NAME}-{__version__}-linux-{arch}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(staging, arcname=folder_name)
    print("Gerado", tar_path)

    # AppImage: um arquivo só, que roda na maioria das distribuições.
    appdir = DIST / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(DIST / APP_NAME, appdir / "usr" / "lib" / "baixador", symlinks=True)
    apprun = appdir / "AppRun"
    apprun.write_text(
        '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
        f'exec "$HERE/usr/lib/baixador/{APP_NAME}" "$@"\n'
    )
    make_executable(apprun)
    shutil.copy(linux / "baixador.desktop", appdir / "baixador.desktop")
    shutil.copy(ROOT / "assets" / "icon.png", appdir / "baixador.png")
    shutil.copy(ROOT / "assets" / "icon.png", appdir / ".DirIcon")

    tool_arch = "aarch64" if arch == "arm64" else "x86_64"
    tool = DIST / f"appimagetool-{tool_arch}.AppImage"
    if not tool.exists():
        url = (
            "https://github.com/AppImage/appimagetool/releases/download/continuous/"
            f"appimagetool-{tool_arch}.AppImage"
        )
        print("Baixando", url)
        urllib.request.urlretrieve(url, tool)
        make_executable(tool)
    appimage = OUT / f"{APP_NAME}-{__version__}-linux-{arch}.AppImage"
    env = dict(os.environ, ARCH=tool_arch)
    # --appimage-extract-and-run dispensa FUSE (útil em CI e containers).
    run([tool, "--appimage-extract-and-run", "--no-appstream", appdir, appimage], env=env)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        package_windows()
    elif sys.platform == "darwin":
        package_macos()
    else:
        package_linux()
    print("\nPacotes prontos em", OUT)
    for item in sorted(OUT.iterdir()):
        print(f"  {item.name}  ({item.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
