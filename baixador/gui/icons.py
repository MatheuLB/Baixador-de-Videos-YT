"""Ícones vetoriais desenhados para o app (traço simples, 24×24, cor configurável)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "link": '<path d="M10 14a4.2 4.2 0 0 0 6 0l3-3a4.2 4.2 0 0 0-6-6l-1.2 1.2"/>'
            '<path d="M14 10a4.2 4.2 0 0 0-6 0l-3 3a4.2 4.2 0 0 0 6 6l1.2-1.2"/>',
    "paste": '<rect x="6" y="4" width="12" height="17" rx="2.5"/>'
             '<rect x="9" y="2.5" width="6" height="3.5" rx="1.2"/>'
             '<path d="M9.5 12h5M9.5 15.5h5"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="3"/>'
             '<path d="M10.5 9.3v5.4l4.5-2.7z" fill="currentColor"/>',
    "music": '<path d="M9 17.5V5.5l10-2v12"/><circle cx="6.5" cy="17.5" r="2.5"/>'
             '<circle cx="16.5" cy="15.5" r="2.5"/>',
    "headphones": '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/>'
                  '<rect x="3" y="14" width="4.5" height="6.5" rx="1.8"/>'
                  '<rect x="16.5" y="14" width="4.5" height="6.5" rx="1.8"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.2h7a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "folder-open": '<path d="M3.5 18V7.5a2 2 0 0 1 2-2h4l2 2.2h6a2 2 0 0 1 2 2v1"/>'
                   '<path d="M3.5 18l2.6-6.2a1.6 1.6 0 0 1 1.5-1h12.2a1 1 0 0 1 .9 1.4L18.4 17a1.6 1.6 0 0 1-1.5 1z"/>',
    "download": '<path d="M12 3.5v11"/><path d="M7.5 10.5L12 15l4.5-4.5"/>'
                '<path d="M4.5 16.5v1.5a2.5 2.5 0 0 0 2.5 2.5h10a2.5 2.5 0 0 0 2.5-2.5v-1.5"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z"/>',
    "x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "alert": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.8v5"/>'
             '<circle cx="12" cy="16.2" r=".6" fill="currentColor"/>',
    "retry": '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
    "trash": '<path d="M4.5 7h15"/><path d="M9.5 7V5h5v2"/>'
             '<path d="M6.5 7l.8 12a1.8 1.8 0 0 0 1.8 1.6h5.8a1.8 1.8 0 0 0 1.8-1.6l.8-12"/>',
    "sun": '<circle cx="12" cy="12" r="4"/>'
           '<path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4'
           'M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "moon": '<path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z"/>',
    "monitor": '<rect x="3" y="4.5" width="18" height="12" rx="2.5"/><path d="M9 20.5h6M12 16.5v4"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.2"/>'
            '<circle cx="12" cy="7.8" r=".6" fill="currentColor"/>',
    "chevron-down": '<path d="M7 10l5 5 5-5"/>',
}


def svg(name: str, color: str, stroke: float = 1.8) -> str:
    body = _PATHS[name].replace("currentColor", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def pixmap(name: str, color: str, size: int = 18, stroke: float = 1.8) -> QPixmap:
    ratio = 2.0
    image = QPixmap(int(size * ratio), int(size * ratio))
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color, stroke).encode()))
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, image.width(), image.height()))
    painter.end()
    image.setDevicePixelRatio(ratio)
    return image


def icon(name: str, color: str, size: int = 18, disabled_color: str | None = None) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    if disabled_color:
        result.addPixmap(pixmap(name, disabled_color, size), QIcon.Mode.Disabled)
    return result


def icon_size(size: int = 18) -> QSize:
    return QSize(size, size)
