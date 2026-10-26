"""Cores, fonte e estilo da interface, com tema claro e escuro."""

from __future__ import annotations

import atexit
import shutil
import tempfile
import weakref
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from .. import tools
from . import icons

DARK = {
    "bg": "#0E0F13",
    "surface": "#16171E",
    "surface_alt": "#1D1F28",
    "hover": "#242733",
    "border": "#252836",
    "border_strong": "#343849",
    "text": "#F2F3F7",
    "muted": "#9095A9",
    "subtle": "#5E6378",
    "accent": "#8B7CFF",
    "grad_start": "#7C5CFF",
    "grad_end": "#3D8BFF",
    "on_accent": "#FFFFFF",
    "track": "#252733",
    "success": "#34D399",
    "danger": "#F87171",
    "warning": "#FBBF24",
}

LIGHT = {
    "bg": "#F4F5F9",
    "surface": "#FFFFFF",
    "surface_alt": "#F1F2F7",
    "hover": "#E9EBF2",
    "border": "#E3E5ED",
    "border_strong": "#D2D5E0",
    "text": "#15161C",
    "muted": "#666B7F",
    "subtle": "#A0A4B4",
    "accent": "#6246FF",
    "grad_start": "#6A4DFF",
    "grad_end": "#2F7BFF",
    "on_accent": "#FFFFFF",
    "track": "#E7E8F0",
    "success": "#16A34A",
    "danger": "#DC2626",
    "warning": "#D97706",
}

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"

FONT_FAMILY = "Inter"
_asset_dir: Path | None = None
_preference = THEME_SYSTEM


def is_dark() -> bool:
    if _preference == THEME_DARK:
        return True
    if _preference == THEME_LIGHT:
        return False
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def colors() -> dict[str, str]:
    return DARK if is_dark() else LIGHT


def rgba(hex_color: str, alpha: float) -> str:
    color = QColor(hex_color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {int(alpha * 255)})"


def gradient(c: dict[str, str], lighten: int = 100) -> str:
    start = QColor(c["grad_start"]).lighter(lighten).name()
    end = QColor(c["grad_end"]).lighter(lighten).name()
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {start}, stop:1 {end})"


def set_preference(app: QApplication, preference: str) -> None:
    """Força o tema claro/escuro ou volta a seguir o sistema."""
    global _preference
    _preference = preference if preference in (THEME_LIGHT, THEME_DARK) else THEME_SYSTEM
    # No Qt 6.8+ isso também deixa a barra de título do Windows/macOS no tema certo.
    scheme = {
        THEME_LIGHT: Qt.ColorScheme.Light,
        THEME_DARK: Qt.ColorScheme.Dark,
    }.get(preference, Qt.ColorScheme.Unknown)
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(scheme)
    apply(app)


# --------------------------------------------------------------------------
# Fonte
# --------------------------------------------------------------------------


def load_fonts(app: QApplication) -> None:
    global FONT_FAMILY
    loaded = False
    for weight in ("Regular", "Medium", "SemiBold", "Bold"):
        path = tools.resource_path(f"assets/fonts/Inter-{weight}.ttf")
        if path.is_file() and QFontDatabase.addApplicationFont(str(path)) >= 0:
            loaded = True
    if not loaded:
        FONT_FAMILY = app.font().family()
        return
    size = app.font().pointSizeF()
    if tools.current_os() == "windows":
        size = max(size, 10.0)  # o padrão do Windows (9pt) fica pequeno com a Inter
    font = QFont(FONT_FAMILY)
    font.setPointSizeF(size if size > 0 else 10.0)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)


def font(scale: float = 1.0, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    result = QFont(QApplication.font())
    result.setPointSizeF(result.pointSizeF() * scale)
    result.setWeight(weight)
    return result


# --------------------------------------------------------------------------
# Imagens usadas pelo QSS (setas, interruptores)
# --------------------------------------------------------------------------


def _assets() -> Path:
    global _asset_dir
    if _asset_dir is None:
        _asset_dir = Path(tempfile.mkdtemp(prefix="baixador-theme-"))
        atexit.register(shutil.rmtree, _asset_dir, True)
    return _asset_dir


def _write_asset(name: str, content: str) -> str:
    path = _assets() / name
    path.write_text(content, encoding="utf-8")
    return path.as_posix()


def _switch_svg(track: str, knob: str, on: bool) -> str:
    cx = 23 if on else 11
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="34" height="20" viewBox="0 0 34 20">'
        f'<rect x="0.5" y="0.5" width="33" height="19" rx="9.5" fill="{track}"/>'
        f'<circle cx="{cx}" cy="10" r="7" fill="{knob}"/></svg>'
    )


def _theme_assets(c: dict[str, str]) -> dict[str, str]:
    suffix = "dark" if c is DARK else "light"
    return {
        "chevron": _write_asset(f"chevron-{suffix}.svg", icons.svg("chevron-down", c["muted"], 2)),
        "switch_off": _write_asset(
            f"switch-off-{suffix}.svg", _switch_svg(c["border_strong"], "#FFFFFF", False)
        ),
        "switch_on": _write_asset(
            f"switch-on-{suffix}.svg", _switch_svg(c["accent"], "#FFFFFF", True)
        ),
    }


# --------------------------------------------------------------------------
# Paleta e folha de estilo
# --------------------------------------------------------------------------


def _palette(c: dict[str, str]) -> QPalette:
    palette = QPalette()
    role = QPalette.ColorRole
    palette.setColor(role.Window, QColor(c["bg"]))
    palette.setColor(role.WindowText, QColor(c["text"]))
    palette.setColor(role.Base, QColor(c["surface"]))
    palette.setColor(role.AlternateBase, QColor(c["surface_alt"]))
    palette.setColor(role.Text, QColor(c["text"]))
    palette.setColor(role.PlaceholderText, QColor(c["subtle"]))
    palette.setColor(role.Button, QColor(c["surface_alt"]))
    palette.setColor(role.ButtonText, QColor(c["text"]))
    palette.setColor(role.Highlight, QColor(c["accent"]))
    palette.setColor(role.HighlightedText, QColor(c["on_accent"]))
    palette.setColor(role.ToolTipBase, QColor(c["surface_alt"]))
    palette.setColor(role.ToolTipText, QColor(c["text"]))
    palette.setColor(role.Link, QColor(c["accent"]))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(disabled, r, QColor(c["subtle"]))
    return palette


def _stylesheet(c: dict[str, str], a: dict[str, str]) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    QLabel {{ background: transparent; }}
    QLabel#Muted {{ color: {c['muted']}; }}
    QLabel#Subtle {{ color: {c['subtle']}; }}
    QLabel#Error {{ color: {c['danger']}; }}
    QLabel#SectionTitle {{ font-weight: 600; }}
    QLabel#Badge {{
        background: {rgba(c['accent'], 0.16)};
        color: {c['accent']};
        border-radius: 9px;
        padding: 1px 8px;
        font-weight: 600;
    }}

    QFrame#Hero {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 18px;
    }}
    QFrame#Hero[dragging="true"] {{ border: 1px solid {c['accent']}; }}
    QFrame#Card {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 14px;
    }}
    QFrame#Card:hover {{ border: 1px solid {c['border_strong']}; }}
    QFrame#Field {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}

    QLineEdit {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 12px;
        padding: 0 12px;
        min-height: 46px;
        selection-background-color: {c['accent']};
        selection-color: {c['on_accent']};
    }}
    QLineEdit:hover {{ border: 1px solid {c['border_strong']}; }}
    QLineEdit:focus {{ border: 1px solid {c['accent']}; background: {c['surface']}; }}

    QComboBox {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 0 30px 0 12px;
        min-height: 36px;
    }}
    QComboBox:hover {{ border: 1px solid {c['border_strong']}; }}
    QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QComboBox:disabled {{ color: {c['subtle']}; }}
    QComboBox::drop-down {{ border: none; width: 28px; subcontrol-position: center right; }}
    QComboBox::down-arrow {{ image: url("{a['chevron']}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{
        background: {c['surface_alt']};
        border: 1px solid {c['border_strong']};
        border-radius: 10px;
        padding: 4px;
        outline: 0;
        selection-background-color: {rgba(c['accent'], 0.22)};
        selection-color: {c['text']};
    }}

    QPushButton {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 0 14px;
        min-height: 36px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {c['hover']}; border-color: {c['border_strong']}; }}
    QPushButton:pressed {{ background: {c['border']}; }}
    QPushButton:disabled {{ color: {c['subtle']}; }}
    QPushButton#Secondary {{ min-height: 46px; border-radius: 12px; }}

    QPushButton#Primary {{
        background: {gradient(c)};
        color: {c['on_accent']};
        border: none;
        border-radius: 13px;
        min-height: 50px;
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background: {gradient(c, 112)}; }}
    QPushButton#Primary:pressed {{ background: {gradient(c, 92)}; }}
    QPushButton#Primary:disabled {{ background: {c['track']}; color: {c['subtle']}; }}

    QPushButton#Link {{
        background: transparent;
        border: none;
        color: {c['accent']};
        padding: 0 4px;
        min-height: 24px;
    }}
    QPushButton#Link:hover {{ text-decoration: underline; }}
    QPushButton#Link:disabled {{ color: {c['subtle']}; }}

    QFrame#Segment {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 12px;
    }}
    QPushButton#SegmentButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 0 14px;
        min-height: 32px;
        color: {c['muted']};
    }}
    QPushButton#SegmentButton:hover {{ color: {c['text']}; }}
    QPushButton#SegmentButton:checked {{
        background: {c['surface']};
        border: 1px solid {c['border_strong']};
        color: {c['text']};
        font-weight: 600;
    }}

    QToolButton#IconButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 6px;
    }}
    QToolButton#IconButton:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
    QToolButton#IconButton:pressed {{ background: {c['border']}; }}
    QToolButton#IconButton::menu-indicator {{ image: none; width: 0; }}

    QCheckBox {{ spacing: 8px; color: {c['text']}; }}
    QCheckBox::indicator {{ width: 34px; height: 20px; }}
    QCheckBox::indicator:unchecked {{ image: url("{a['switch_off']}"); }}
    QCheckBox::indicator:checked {{ image: url("{a['switch_on']}"); }}

    QMenu {{
        background: {c['surface_alt']};
        border: 1px solid {c['border_strong']};
        border-radius: 10px;
        padding: 5px;
    }}
    QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {rgba(c['accent'], 0.18)}; }}
    QMenu::indicator {{ width: 0; }}

    QScrollArea, QWidget#ListContainer {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['subtle']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QToolTip {{
        background: {c['surface_alt']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        border-radius: 6px;
        padding: 5px 8px;
    }}
    QMessageBox QLabel {{ color: {c['text']}; }}
    QTextEdit {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}
    """


_listeners: list = []


def on_change(callback) -> None:
    """Registra uma função chamada sempre que o tema muda.

    Métodos são guardados por referência fraca, para não manter vivos
    widgets que já saíram da tela.
    """
    ref = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else (lambda: callback)
    _listeners.append(ref)


def apply(app: QApplication) -> None:
    c = colors()
    app.setStyle("Fusion")
    app.setPalette(_palette(c))
    app.setStyleSheet(_stylesheet(c, _theme_assets(c)))
    for ref in list(_listeners):
        callback = ref()
        try:
            if callback is None:
                raise RuntimeError
            callback()
        except RuntimeError:
            _listeners.remove(ref)  # o widget já foi destruído


def repolish(widget) -> None:
    """Reaplica o estilo depois de mudar uma propriedade usada no QSS."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
