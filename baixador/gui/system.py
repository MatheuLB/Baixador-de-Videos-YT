"""Integração com o sistema: abrir arquivos e pastas no gerenciador de arquivos."""

from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from .. import tools


def open_path(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def reveal_file(path: str) -> None:
    """Mostra o arquivo selecionado no Explorer/Finder (no Linux, abre a pasta)."""
    if not os.path.exists(path):
        open_path(os.path.dirname(path))
        return
    os_name = tools.current_os()
    try:
        if os_name == "windows":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return
        if os_name == "macos":
            subprocess.Popen(["open", "-R", path])
            return
    except OSError:
        pass
    open_path(os.path.dirname(path))
