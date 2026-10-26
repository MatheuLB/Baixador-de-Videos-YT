"""Componentes visuais: barra de progresso animada, seletor em pílulas,
botões com ícone e o cartão de cada download."""

from __future__ import annotations

import os

from PySide6.QtCore import (
    QEasingCurve,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import tools
from . import icons, system, theme
from .manager import CANCELLED, DONE, ERROR, QUEUED, RUNNING, Job
from .workers import run_in_background

THUMB_SIZE = QSize(144, 81)


class ElidedLabel(QLabel):
    """QLabel de uma linha que corta o texto com "…" quando não cabe."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - API do Qt
        self._full_text = text
        self.setToolTip(text if len(text) > 40 else "")
        self._update_elision()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_elision()

    def _update_elision(self) -> None:
        width = max(self.width(), 10)
        elided = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        super().setText(elided)


class SlimProgress(QWidget):
    """Barra de progresso fina, com gradiente e animação suave."""

    def __init__(self, height: int = 6, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._value = 0.0
        self._phase = 0.0
        self._busy = False
        self._state = ""

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)

        self._busy_anim = QVariantAnimation(self)
        self._busy_anim.setStartValue(0.0)
        self._busy_anim.setEndValue(1.0)
        self._busy_anim.setDuration(1300)
        self._busy_anim.setLoopCount(-1)
        self._busy_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._busy_anim.valueChanged.connect(self._on_phase)

    def set_fraction(self, fraction: float, animate: bool = True) -> None:
        self.set_busy(False)
        fraction = max(0.0, min(1.0, fraction))
        self._anim.stop()
        if animate and abs(fraction - self._value) > 0.001 and fraction > self._value:
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(fraction)
            self._anim.start()
        else:
            self._value = fraction
            self.update()

    def set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            self._anim.stop()
            self._busy_anim.start()
        else:
            self._busy_anim.stop()
        self.update()

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.update()

    def _on_value(self, value) -> None:
        self._value = float(value)
        self.update()

    def _on_phase(self, value) -> None:
        self._phase = float(value)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        c = theme.colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        radius = rect.height() / 2
        track = QPainterPath()
        track.addRoundedRect(rect, radius, radius)
        painter.fillPath(track, QColor(c["track"]))
        painter.setClipPath(track)

        if self._busy:
            width = rect.width() * 0.32
            x = -width + (rect.width() + width) * self._phase
            fill = QRectF(x, 0, width, rect.height())
        else:
            fill = QRectF(0, 0, rect.width() * self._value, rect.height())
        if fill.width() <= 0:
            return

        if self._state == "done":
            brush = QColor(c["success"])
        elif self._state == "error":
            brush = QColor(c["danger"])
        else:
            brush = QLinearGradient(0, 0, rect.width(), 0)
            brush.setColorAt(0, QColor(c["grad_start"]))
            brush.setColorAt(1, QColor(c["grad_end"]))
        path = QPainterPath()
        path.addRoundedRect(fill, radius, radius)
        painter.fillPath(path, brush)


class IconButton(QToolButton):
    """Botão só com ícone, que se recolore quando o tema muda."""

    def __init__(self, icon_name: str, tooltip: str, tone: str = "muted", size: int = 18, parent=None):
        super().__init__(parent)
        self.setObjectName("IconButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setIconSize(icons.icon_size(size))
        self._icon_name = icon_name
        self._tone = tone
        self._size = size
        theme.on_change(self._refresh_icon)
        self._refresh_icon()

    def set_icon(self, icon_name: str, tone: str | None = None) -> None:
        self._icon_name = icon_name
        if tone:
            self._tone = tone
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        c = theme.colors()
        self.setIcon(icons.icon(self._icon_name, c[self._tone], self._size, c["subtle"]))


class SegmentedControl(QFrame):
    """Grupo de opções em formato de pílula (como um seletor do iOS)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Segment")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        self._icon_names: dict[str, str] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        for value, label, icon_name in options:
            button = QPushButton(label)
            button.setObjectName("SegmentButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(icons.icon_size(16))
            button.toggled.connect(self._refresh_icons)
            button.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            self._group.addButton(button)
            self._buttons[value] = button
            self._icon_names[value] = icon_name
            layout.addWidget(button)
        theme.on_change(self._refresh_icons)

    def value(self) -> str:
        for value, button in self._buttons.items():
            if button.isChecked():
                return value
        return next(iter(self._buttons))

    def set_value(self, value: str) -> None:
        button = self._buttons.get(value) or next(iter(self._buttons.values()))
        button.setChecked(True)
        self._refresh_icons()

    def _refresh_icons(self, *_args) -> None:
        c = theme.colors()
        for value, button in self._buttons.items():
            color = c["accent"] if button.isChecked() else c["muted"]
            button.setIcon(icons.icon(self._icon_names[value], color, 16))


class Pill(QLabel):
    """Selo colorido com o estado do download."""

    TONES = {"neutral": "muted", "accent": "accent", "success": "success", "danger": "danger"}

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tone = "neutral"
        self.setFont(theme.font(0.86, QFont.Weight.DemiBold))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setContentsMargins(9, 2, 9, 2)
        theme.on_change(self._restyle)
        self._restyle()

    def set(self, text: str, tone: str) -> None:
        self.setText(text)
        if tone != self._tone:
            self._tone = tone
            self._restyle()

    def _color(self) -> QColor:
        return QColor(theme.colors()[self.TONES[self._tone]])

    def _restyle(self) -> None:
        self.setStyleSheet(f"color: {self._color().name()}; background: transparent;")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        # O fundo arredondado é pintado aqui: o QSS não arredonda fundo de QLabel.
        background = self._color()
        background.setAlphaF(0.15)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        rect = QRectF(self.rect())
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.end()
        super().paintEvent(event)


# --------------------------------------------------------------------------
# Imagens
# --------------------------------------------------------------------------


def rounded_pixmap(image: QImage, size: QSize, radius: float = 10) -> QPixmap:
    """Recorta a imagem no tamanho pedido (preenchendo) e arredonda os cantos."""
    ratio = 2.0  # desenha em alta resolução para telas Retina/HiDPI
    target = QPixmap(int(size.width() * ratio), int(size.height() * ratio))
    target.fill(Qt.GlobalColor.transparent)
    scaled = image.scaled(
        target.size(),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(target.rect()), radius * ratio, radius * ratio)
    painter.setClipPath(path)
    x = (scaled.width() - target.width()) // 2
    y = (scaled.height() - target.height()) // 2
    painter.drawImage(0, 0, scaled, x, y, target.width(), target.height())
    painter.end()
    target.setDevicePixelRatio(ratio)
    return target


def _draw_centered(painter: QPainter, glyph: QPixmap, width: int, height: int) -> None:
    # Pinta em pixels físicos: o destino ainda não tem devicePixelRatio aplicado.
    w, h = glyph.width(), glyph.height()
    painter.drawPixmap(QRectF((width - w) / 2, (height - h) / 2, w, h), glyph, QRectF(glyph.rect()))


def placeholder_pixmap(size: QSize, icon_name: str, radius: float = 10) -> QPixmap:
    """Fundo em gradiente suave com um ícone, enquanto a miniatura não chega."""
    c = theme.colors()
    ratio = 2.0
    target = QPixmap(int(size.width() * ratio), int(size.height() * ratio))
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, target.width(), target.height())
    start, end = QColor(c["grad_start"]), QColor(c["grad_end"])
    start.setAlphaF(0.22)
    end.setAlphaF(0.10)
    gradient.setColorAt(0, start)
    gradient.setColorAt(1, end)
    path = QPainterPath()
    path.addRoundedRect(QRectF(target.rect()), radius * ratio, radius * ratio)
    painter.fillPath(path, QColor(c["surface_alt"]))
    painter.fillPath(path, gradient)
    _draw_centered(painter, icons.pixmap(icon_name, c["accent"], 28), target.width(), target.height())
    painter.end()
    target.setDevicePixelRatio(ratio)
    return target


def badge_circle_pixmap(icon_name: str, diameter: int = 64) -> QPixmap:
    """Ícone grande dentro de um círculo translúcido (usado no estado vazio)."""
    c = theme.colors()
    ratio = 2.0
    side = int(diameter * ratio)
    target = QPixmap(side, side)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, side, side)
    start, end = QColor(c["grad_start"]), QColor(c["grad_end"])
    start.setAlphaF(0.20)
    end.setAlphaF(0.08)
    gradient.setColorAt(0, start)
    gradient.setColorAt(1, end)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(0, 0, side, side)
    _draw_centered(painter, icons.pixmap(icon_name, c["accent"], int(diameter * 0.45)), side, side)
    painter.end()
    target.setDevicePixelRatio(ratio)
    return target


class EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.art = QLabel()
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Nenhum download ainda")
        title.setFont(theme.font(1.1, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Cole um link acima, ou arraste o link para esta janela.")
        subtitle.setObjectName("Muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 28, 0, 28)
        layout.setSpacing(6)
        layout.addWidget(self.art)
        layout.addSpacing(6)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        theme.on_change(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self.art.setPixmap(badge_circle_pixmap("download", 68))


# --------------------------------------------------------------------------
# Cartão de download
# --------------------------------------------------------------------------


class DownloadCard(QFrame):
    """Cartão de um download na lista, sempre refletindo o estado do Job."""

    retry_requested = Signal(object)
    cancel_requested = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, job: Job, parent: QWidget | None = None):
        super().__init__(parent)
        self.job = job
        self._thumb_loaded_for: str | None = None
        self._thumb_image: QImage | None = None
        self.setObjectName("Card")

        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_SIZE)

        self.title = ElidedLabel()
        self.title.setFont(theme.font(1.02, QFont.Weight.DemiBold))
        self.meta = ElidedLabel()
        self.meta.setObjectName("Muted")
        self.bar = SlimProgress(6)
        self.pill = Pill()
        self.status = ElidedLabel()
        self.status.setObjectName("Muted")

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self.pill)
        status_row.addWidget(self.status, 1)

        info = QVBoxLayout()
        info.setSpacing(5)
        info.addWidget(self.title)
        info.addWidget(self.meta)
        info.addSpacing(4)
        info.addWidget(self.bar)
        info.addSpacing(2)
        info.addLayout(status_row)

        self.cancel_btn = IconButton("x", "Cancelar download")
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job))
        self.open_btn = IconButton("play", "Abrir o arquivo", tone="accent")
        self.open_btn.clicked.connect(self._open_file)
        self.folder_btn = IconButton("folder-open", "Mostrar na pasta")
        self.folder_btn.clicked.connect(self._reveal)
        self.retry_btn = IconButton("retry", "Tentar de novo", tone="accent")
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.job))
        self.details_btn = IconButton("alert", "Ver detalhes do erro", tone="danger")
        self.details_btn.clicked.connect(self._show_details)
        self.remove_btn = IconButton("trash", "Remover da lista")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.job))

        actions = QHBoxLayout()
        actions.setSpacing(2)
        for button in (
            self.open_btn, self.folder_btn, self.retry_btn,
            self.details_btn, self.cancel_btn, self.remove_btn,
        ):
            actions.addWidget(button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 10, 12)
        layout.setSpacing(16)
        layout.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(info, 1)
        layout.addLayout(actions)

        job.changed.connect(self.refresh)
        theme.on_change(self._refresh_thumb)
        self._refresh_thumb()
        self.refresh()

    # -- atualização visual ------------------------------------------------

    def refresh(self) -> None:
        job = self.job
        self.title.setText(job.display_title)
        self.meta.setText(job.meta_text)
        self.status.setText(job.status_text)
        self.status.setObjectName("Error" if job.state == ERROR else "Muted")
        theme.repolish(self.status)

        tone = {
            RUNNING: "accent",
            DONE: "success",
            ERROR: "danger",
        }.get(job.state, "neutral")
        self.pill.set(job.badge, tone)

        if job.state == RUNNING and job.percent is None:
            self.bar.set_busy(True)
        elif job.state == ERROR or job.state == CANCELLED:
            self.bar.set_fraction((job.percent or 0) / 100, animate=False)
        else:
            self.bar.set_fraction((job.percent or 0) / 100)
        self.bar.set_state({DONE: "done", ERROR: "error"}.get(job.state, ""))

        active = job.state in (QUEUED, RUNNING)
        self.cancel_btn.setVisible(active)
        self.open_btn.setVisible(job.state == DONE and bool(job.files))
        self.folder_btn.setVisible(job.state == DONE)
        self.retry_btn.setVisible(job.state in (ERROR, CANCELLED))
        self.details_btn.setVisible(job.state == ERROR)
        self.remove_btn.setVisible(job.finished)

        if job.thumbnail_url and job.thumbnail_url != self._thumb_loaded_for:
            self._thumb_loaded_for = job.thumbnail_url
            # A thread pertence ao app, não ao cartão: o cartão pode ser
            # removido da lista antes de a miniatura terminar de baixar.
            run_in_background(
                QApplication.instance(),
                tools.fetch_bytes,
                job.thumbnail_url,
                on_success=self._set_thumbnail,
            )

    def _refresh_thumb(self) -> None:
        if self._thumb_image is not None:
            self.thumb.setPixmap(rounded_pixmap(self._thumb_image, THUMB_SIZE))
        else:
            name = "video" if self.job.opts.mode == "video" else "music"
            self.thumb.setPixmap(placeholder_pixmap(THUMB_SIZE, name))

    def _set_thumbnail(self, data: bytes) -> None:
        image = QImage()
        if not image.loadFromData(data):
            return
        try:
            self._thumb_image = image
            self._refresh_thumb()
        except RuntimeError:
            pass  # o cartão já foi removido

    # -- ações ---------------------------------------------------------------

    def _target_file(self) -> str | None:
        return self.job.files[-1] if self.job.files else None

    def _open_file(self) -> None:
        path = self._target_file()
        if path:
            # Numa playlist, "Abrir" abre a pasta da playlist.
            system.open_path(os.path.dirname(path) if len(self.job.files) > 1 else path)

    def _reveal(self) -> None:
        path = self._target_file()
        if path:
            system.reveal_file(path)
        else:
            system.open_path(self.job.opts.output_dir)

    def _show_details(self) -> None:
        job = self.job
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Detalhes do erro")
        box.setText(job.error or "O download falhou.")
        box.setInformativeText(f"Link: {job.opts.url}")
        if job.log:
            box.setDetailedText(job.log)
        box.exec()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.job.state == DONE:
            self._open_file()
        super().mouseDoubleClickEvent(event)
