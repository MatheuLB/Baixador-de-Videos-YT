# -*- mode: python ; coding: utf-8 -*-
# Receita do PyInstaller para Windows, macOS e Linux.
# Uso: pyinstaller --noconfirm --clean baixador.spec

import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)
from baixador import APP_DISPLAY_NAME, APP_NAME, __version__  # noqa: E402

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "assets" / "icon.png"), "assets"),
    (str(ROOT / "assets" / "fonts"), "assets/fonts"),
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore"],
    noarchive=False,
)
if sys.platform.startswith("linux"):
    # O app tem tema próprio, então o plugin de tema GTK3 do Qt é dispensável.
    # Sem ele, não embutimos o GTK inteiro (que pode brigar com o do sistema).
    gtk_only = (
        "libqgtk3", "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk-1", "libatk-bridge",
        "libatspi", "libcairo", "libpango", "libepoxy",
    )
    a.binaries = [b for b in a.binaries if not any(name in b[0] for name in gtk_only)]

pyz = PYZ(a.pure)

if sys.platform == "win32":
    icon = str(ROOT / "assets" / "icon.ico")
elif sys.platform == "darwin":
    icon = str(ROOT / "assets" / "icon.icns")
else:
    icon = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=icon,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="io.github.baixador",
        version=__version__,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_DISPLAY_NAME,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
