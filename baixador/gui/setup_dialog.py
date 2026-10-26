"""Janela da primeira execução, que baixa os componentes necessários."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .. import tools
from ..downloader import human_size
from . import theme
from .widgets import SlimProgress, badge_circle_pixmap
from .workers import SetupWorker


class SetupDialog(QDialog):
    def __init__(self, missing: list[str], parent=None):
        super().__init__(parent)
        self._missing = missing
        self._worker: SetupWorker | None = None
        self._done: set[str] = set()
        self._current: str | None = None
        self.setWindowTitle("Preparando o Baixador")
        self.setModal(True)
        self.setMinimumWidth(480)

        art = QLabel()
        art.setPixmap(badge_circle_pixmap("download", 52))
        title = QLabel("Só mais um passo")
        title.setFont(theme.font(1.35, QFont.Weight.Bold))

        names = ", ".join(dict.fromkeys(tools.TOOL_LABELS[k] for k in missing))
        intro = QLabel(
            "Na primeira vez, o app precisa baixar os componentes que fazem o "
            f"download e a conversão dos vídeos ({names}). Isso só acontece uma vez."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")

        self.step_label = QLabel("Iniciando…")
        self.step_label.setFont(theme.font(1.0, QFont.Weight.Medium))
        self.bar = SlimProgress(8)
        self.detail_label = QLabel(" ")
        self.detail_label.setObjectName("Muted")
        self.error_label = QLabel()
        self.error_label.setObjectName("Error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self._cancel)
        self.retry_btn = QPushButton("Tentar de novo")
        self.retry_btn.setObjectName("Primary")
        self.retry_btn.clicked.connect(self.start)
        self.retry_btn.hide()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.retry_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(10)
        layout.addWidget(art)
        layout.addSpacing(4)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addSpacing(8)
        layout.addWidget(self.step_label)
        layout.addWidget(self.bar)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.error_label)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    def start(self) -> None:
        pending = [k for k in self._missing if k not in self._done]
        self.error_label.hide()
        self.retry_btn.hide()
        self.bar.set_state("")
        self.cancel_btn.setText("Cancelar")
        self.cancel_btn.setEnabled(True)
        worker = SetupWorker(pending, parent=self)
        worker.step.connect(self._on_step)
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.cancelled.connect(self.reject)
        self._worker = worker
        worker.start()

    def exec(self) -> int:  # noqa: A003 - mesmo nome da API do Qt
        self.start()
        return super().exec()

    # -- sinais do worker ----------------------------------------------------

    def _on_step(self, key: str, position: int, total: int) -> None:
        if position > 1:
            self._done.add(self._current)
        self._current = key
        self.step_label.setText(f"Baixando {tools.TOOL_LABELS[key]} ({position} de {total})…")
        self.bar.set_fraction(0, animate=False)
        self.bar.set_busy(True)
        self.detail_label.setText(" ")

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.bar.set_fraction(done / total, animate=False)
            self.detail_label.setText(f"{human_size(done)} de {human_size(total)}")
        else:
            self.detail_label.setText(human_size(done))

    def _on_success(self) -> None:
        self.accept()

    def _on_failure(self, message: str) -> None:
        self.step_label.setText("Não foi possível baixar os componentes.")
        self.bar.set_fraction(0, animate=False)
        self.bar.set_state("error")
        self.detail_label.setText("Verifique sua conexão com a internet e tente de novo.")
        self.error_label.setText(message)
        self.error_label.show()
        self.cancel_btn.setText("Fechar")
        self.retry_btn.show()

    # -- fechar --------------------------------------------------------------

    def _cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.cancel_btn.setEnabled(False)
            self.step_label.setText("Cancelando…")
            self._worker.cancel()
        else:
            self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Esc passa pelo mesmo caminho do botão Cancelar.
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)
