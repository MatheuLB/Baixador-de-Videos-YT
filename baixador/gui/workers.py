"""Threads que fazem o trabalho demorado sem travar a interface."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

from .. import tools
from ..downloader import DownloadOptions, DownloadResult, DownloadRunner


class FunctionThread(QThread):
    """Roda uma função qualquer em segundo plano e devolve o resultado."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, *args, parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self) -> None:
        try:
            result = self._fn(*self._args)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira mensagem
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.succeeded.emit(result)


def run_in_background(
    owner: QObject,
    fn: Callable,
    *args,
    on_success: Callable | None = None,
    on_failure: Callable | None = None,
) -> FunctionThread:
    thread = FunctionThread(fn, *args, parent=owner)
    if on_success:
        thread.succeeded.connect(on_success)
    if on_failure:
        thread.failed.connect(on_failure)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


class DownloadWorker(QThread):
    event = Signal(object)  # dict vindo do OutputParser
    result = Signal(object)  # DownloadResult

    def __init__(self, opts: DownloadOptions, paths: tools.ToolPaths, parent: QObject | None = None):
        super().__init__(parent)
        self._runner = DownloadRunner(opts, paths, self.event.emit)

    def cancel(self) -> None:
        self._runner.cancel()

    def run(self) -> None:
        try:
            outcome = self._runner.run()
        except Exception as exc:  # noqa: BLE001
            outcome = DownloadResult("error", [], "Erro inesperado.", str(exc), str(exc))
        self.result.emit(outcome)


class SetupWorker(QThread):
    """Baixa os componentes que estiverem faltando, um de cada vez."""

    step = Signal(str, int, int)  # componente, posição (1..n), total
    progress = Signal(int, int)  # bytes baixados, total
    succeeded = Signal()
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, keys: list[str], parent: QObject | None = None):
        super().__init__(parent)
        self._keys = keys
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            for position, key in enumerate(self._keys, start=1):
                self.step.emit(key, position, len(self._keys))
                tools.install_tool(key, progress=self.progress.emit, cancelled=lambda: self._cancel)
        except tools.InstallCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.succeeded.emit()
