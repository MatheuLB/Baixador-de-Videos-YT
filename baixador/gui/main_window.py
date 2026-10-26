"""Janela principal do app."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFont, QGuiApplication, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_DISPLAY_NAME, __version__, tools
from ..downloader import (
    DEFAULT_QUALITY,
    MODE_M4A,
    MODE_MP3,
    MODE_VIDEO,
    QUALITIES,
    DownloadOptions,
    normalize_url,
)
from . import icons, system, theme
from .manager import DownloadManager, Job
from .setup_dialog import SetupDialog
from .widgets import DownloadCard, ElidedLabel, EmptyState, IconButton, SegmentedControl
from .workers import run_in_background

UPDATE_INTERVAL = 24 * 3600  # verifica atualizações do yt-dlp uma vez por dia

FORMAT_OPTIONS = [
    (MODE_VIDEO, "Vídeo MP4", "video"),
    (MODE_MP3, "Áudio MP3", "music"),
    (MODE_M4A, "Áudio M4A", "headphones"),
]

THEME_OPTIONS = [
    (theme.THEME_SYSTEM, "Seguir o sistema", "monitor"),
    (theme.THEME_LIGHT, "Tema claro", "sun"),
    (theme.THEME_DARK, "Tema escuro", "moon"),
]


def default_download_dir() -> str:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return location or str(Path.home())


class MainWindow(QMainWindow):
    def __init__(self, check_tools: bool = True):
        super().__init__()
        self.settings = QSettings()
        self.manager = DownloadManager(self)
        self.cards: dict[Job, DownloadCard] = {}
        self._tools_ready = False
        self._updating = False

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setMinimumSize(660, 600)
        self.resize(820, 760)
        self.setAcceptDrops(True)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(26, 22, 26, 16)
        root.setSpacing(16)
        root.addLayout(self._build_header())
        root.addWidget(self._build_hero())
        root.addSpacing(4)
        root.addLayout(self._build_list_header())
        root.addWidget(self._build_list(), 1)
        root.addLayout(self._build_footer())
        self.setCentralWidget(central)

        self.manager.job_added.connect(self._on_job_added)
        self.manager.job_removed.connect(self._on_job_removed)
        self.manager.active_changed.connect(lambda _: self._update_list_state())

        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self._paste_shortcut)
        theme.on_change(self._refresh_icons)

        self._restore_settings()
        self._refresh_icons()
        self._update_list_state()
        self._set_tools_ready(False, "Verificando componentes…")
        if check_tools:
            QTimer.singleShot(0, self._check_tools)

    # ----------------------------------------------------------------------
    # Construção da interface
    # ----------------------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        logo = QLabel()
        pixmap = QPixmap(str(tools.resource_path("assets/icon.png")))
        if not pixmap.isNull():
            ratio = 2.0
            pixmap = pixmap.scaled(
                int(46 * ratio), int(46 * ratio),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            pixmap.setDevicePixelRatio(ratio)
            logo.setPixmap(pixmap)

        title = QLabel(APP_DISPLAY_NAME)
        title.setFont(theme.font(1.6, QFont.Weight.Bold))
        subtitle = QLabel("Vídeos e músicas do YouTube a partir de um link.")
        subtitle.setObjectName("Muted")
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(title)
        texts.addWidget(subtitle)

        self.theme_btn = IconButton("monitor", "Tema da interface", size=19)
        self.theme_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.theme_btn)
        group = QActionGroup(menu)
        self._theme_actions: dict[str, QAction] = {}
        for value, label, _icon in THEME_OPTIONS:
            action = QAction(label, menu, checkable=True)
            action.triggered.connect(lambda _=False, v=value: self._set_theme(v))
            group.addAction(action)
            menu.addAction(action)
            self._theme_actions[value] = action
        self.theme_btn.setMenu(menu)

        about_btn = IconButton("info", "Sobre o app", size=19)
        about_btn.clicked.connect(self._show_about)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(logo)
        row.addLayout(texts, 1)
        row.addWidget(self.theme_btn, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(about_btn, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _build_hero(self) -> QFrame:
        self.hero = QFrame()
        self.hero.setObjectName("Hero")
        layout = QVBoxLayout(self.hero)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Link
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Cole aqui o link do vídeo ou da playlist")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self._start_download)
        self.url_edit.textChanged.connect(lambda _: self.form_error.hide())
        self._link_action = self.url_edit.addAction(QIcon(), QLineEdit.ActionPosition.LeadingPosition)
        self.paste_btn = QPushButton("Colar")
        self.paste_btn.setObjectName("Secondary")
        self.paste_btn.setIconSize(icons.icon_size(17))
        self.paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_btn.setToolTip("Colar o link copiado (Ctrl+V)")
        self.paste_btn.clicked.connect(self._paste)
        url_row = QHBoxLayout()
        url_row.setSpacing(10)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.paste_btn)

        # Formato e qualidade
        self.format_control = SegmentedControl(FORMAT_OPTIONS)
        self.format_control.changed.connect(self._on_mode_changed)
        self.quality_combo = QComboBox()
        self.quality_combo.setMinimumContentsLength(15)
        self.quality_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        options_row = QHBoxLayout()
        options_row.setSpacing(10)
        options_row.addWidget(self.format_control)
        options_row.addStretch(1)
        options_row.addWidget(self._label("Qualidade", "Muted"))
        options_row.addWidget(self.quality_combo)

        # Opções extras
        self.compat_check = QCheckBox("Máxima compatibilidade")
        self.compat_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compat_check.setToolTip(
            "Prefere vídeo H.264, que abre em qualquer player e editor\n"
            "(no YouTube, o H.264 vai só até 1080p)."
        )
        self.playlist_check = QCheckBox("Baixar a playlist inteira")
        self.playlist_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_check.setToolTip(
            "Se o link for de uma playlist, baixa todos os vídeos dela\n"
            "numa subpasta com o nome da playlist."
        )
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(22)
        toggles_row.addWidget(self.compat_check)
        toggles_row.addWidget(self.playlist_check)
        toggles_row.addStretch(1)

        # Pasta de destino
        folder_field = QFrame()
        folder_field.setObjectName("Field")
        self.folder_icon = QLabel()
        self.folder_label = ElidedLabel()
        change_btn = QPushButton("Alterar")
        change_btn.setObjectName("Link")
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.clicked.connect(self._choose_folder)
        open_btn = QPushButton("Abrir")
        open_btn.setObjectName("Link")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: system.open_path(self.output_dir))
        folder_layout = QHBoxLayout(folder_field)
        folder_layout.setContentsMargins(12, 8, 10, 8)
        folder_layout.setSpacing(10)
        folder_layout.addWidget(self.folder_icon)
        folder_layout.addWidget(self._label("Salvar em", "Muted"))
        folder_layout.addWidget(self.folder_label, 1)
        folder_layout.addWidget(change_btn)
        folder_layout.addWidget(open_btn)

        self.form_error = QLabel()
        self.form_error.setObjectName("Error")
        self.form_error.hide()

        self.download_btn = QPushButton("Baixar agora")
        self.download_btn.setObjectName("Primary")
        self.download_btn.setIconSize(icons.icon_size(20))
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.clicked.connect(self._start_download)

        layout.addLayout(url_row)
        layout.addLayout(options_row)
        layout.addLayout(toggles_row)
        layout.addWidget(folder_field)
        layout.addWidget(self.form_error)
        layout.addWidget(self.download_btn)
        return self.hero

    def _build_list_header(self) -> QHBoxLayout:
        title = self._label("Downloads", "SectionTitle")
        title.setFont(theme.font(1.12, QFont.Weight.DemiBold))
        self.count_badge = self._label("0", "Badge")
        self.clear_btn = QPushButton("Limpar concluídos")
        self.clear_btn.setObjectName("Link")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self.manager.clear_finished)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(title)
        row.addWidget(self.count_badge)
        row.addStretch(1)
        row.addWidget(self.clear_btn)
        return row

    def _build_list(self) -> QScrollArea:
        self.list_container = QWidget()
        self.list_container.setObjectName("ListContainer")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(10)
        self.empty_state = EmptyState()
        self.list_layout.addWidget(self.empty_state)
        self.list_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.list_container)
        return scroll

    def _build_footer(self) -> QHBoxLayout:
        self.tools_label = ElidedLabel()
        self.tools_label.setObjectName("Subtle")
        self.tools_btn = QPushButton()
        self.tools_btn.setObjectName("Link")
        self.tools_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tools_btn.clicked.connect(self._on_tools_button)
        legal = self._label("Baixe apenas conteúdo que você tem direito de baixar.", "Subtle")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.tools_label, 1)
        row.addWidget(self.tools_btn)
        row.addSpacing(10)
        row.addWidget(legal)
        return row

    @staticmethod
    def _label(text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        return label

    def _refresh_icons(self) -> None:
        c = theme.colors()
        self._link_action.setIcon(icons.icon("link", c["subtle"], 18))
        self.paste_btn.setIcon(icons.icon("paste", c["text"], 17))
        self.download_btn.setIcon(icons.icon("download", c["on_accent"], 20, c["subtle"]))
        self.folder_icon.setPixmap(icons.pixmap("folder", c["accent"], 18))
        preference = self._theme_preference()
        icon_name = dict((v, i) for v, _l, i in THEME_OPTIONS).get(preference, "monitor")
        self.theme_btn.set_icon(icon_name)

    # ----------------------------------------------------------------------
    # Tema
    # ----------------------------------------------------------------------

    def _theme_preference(self) -> str:
        return str(self.settings.value("theme", theme.THEME_SYSTEM))

    def _set_theme(self, preference: str) -> None:
        self.settings.setValue("theme", preference)
        self._theme_actions[preference].setChecked(True)
        theme.set_preference(QApplication.instance(), preference)

    # ----------------------------------------------------------------------
    # Configurações
    # ----------------------------------------------------------------------

    @property
    def output_dir(self) -> str:
        return self.folder_label.full_text()

    def _set_output_dir(self, path: str) -> None:
        self.folder_label.setText(path)
        self.folder_label.setToolTip(path)

    def _restore_settings(self) -> None:
        preference = self._theme_preference()
        if preference in self._theme_actions:
            self._theme_actions[preference].setChecked(True)
        folder = str(self.settings.value("output_dir", "") or "")
        self._set_output_dir(folder if folder and os.path.isdir(folder) else default_download_dir())
        self.format_control.set_value(str(self.settings.value("mode", MODE_VIDEO)))
        self._on_mode_changed()
        self.compat_check.setChecked(self.settings.value("compatible", False, type=bool))
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _save_settings(self) -> None:
        self.settings.setValue("output_dir", self.output_dir)
        self.settings.setValue("mode", self.current_mode)
        self.settings.setValue(f"quality_{self.current_mode}", self.quality_combo.currentData())
        self.settings.setValue("compatible", self.compat_check.isChecked())
        self.settings.setValue("geometry", self.saveGeometry())

    @property
    def current_mode(self) -> str:
        return self.format_control.value()

    def _on_mode_changed(self, *_args) -> None:
        mode = self.current_mode
        saved = str(self.settings.value(f"quality_{mode}", DEFAULT_QUALITY[mode]))
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        for value, label in QUALITIES[mode]:
            self.quality_combo.addItem(label, value)
        index = self.quality_combo.findData(saved)
        self.quality_combo.setCurrentIndex(index if index >= 0 else 0)
        self.quality_combo.blockSignals(False)
        self.quality_combo.setEnabled(len(QUALITIES[mode]) > 1)
        self.compat_check.setVisible(mode == MODE_VIDEO)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Escolha onde salvar", self.output_dir)
        if folder:
            self._set_output_dir(folder)
            self._save_settings()

    # ----------------------------------------------------------------------
    # Link e download
    # ----------------------------------------------------------------------

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)
            self.url_edit.setFocus()

    def _paste_shortcut(self) -> None:
        # Ctrl+V com o foco fora do campo também cola o link nele.
        if self.url_edit.hasFocus():
            self.url_edit.paste()
        else:
            self._paste()

    def _show_form_error(self, message: str) -> None:
        self.form_error.setText(message)
        self.form_error.show()

    def _start_download(self) -> None:
        if not self._tools_ready:
            self._show_form_error("Os componentes ainda não estão instalados.")
            return
        url = normalize_url(self.url_edit.text())
        if url is None:
            self._show_form_error("Cole um link válido, por exemplo https://youtu.be/…")
            self.url_edit.setFocus()
            return
        output_dir = self.output_dir
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError:
            self._show_form_error("Não foi possível usar a pasta de destino. Escolha outra.")
            return
        if not os.access(output_dir, os.W_OK):
            self._show_form_error("Sem permissão para salvar nessa pasta. Escolha outra.")
            return

        opts = DownloadOptions(
            url=url,
            output_dir=output_dir,
            mode=self.current_mode,
            quality=self.quality_combo.currentData() or DEFAULT_QUALITY[self.current_mode],
            compatible=self.current_mode == MODE_VIDEO and self.compat_check.isChecked(),
            playlist=self.playlist_check.isChecked(),
        )
        self._save_settings()
        self.manager.add(opts)
        self.url_edit.clear()
        self.url_edit.setFocus()

    def _on_job_added(self, job: Job) -> None:
        card = DownloadCard(job)
        card.cancel_requested.connect(self.manager.cancel)
        card.retry_requested.connect(self.manager.retry)
        card.remove_requested.connect(self.manager.remove)
        self.cards[job] = card
        self.list_layout.insertWidget(0, card)  # mais recente no topo
        self._update_list_state()

    def _on_job_removed(self, job: Job) -> None:
        card = self.cards.pop(job, None)
        if card is not None:
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self._update_list_state()

    def _update_list_state(self) -> None:
        self.empty_state.setVisible(not self.cards)
        self.count_badge.setText(str(len(self.cards)))
        self.count_badge.setVisible(bool(self.cards))
        self.clear_btn.setVisible(any(j.finished for j in self.manager.jobs))

    # ----------------------------------------------------------------------
    # Componentes (yt-dlp, FFmpeg, Deno)
    # ----------------------------------------------------------------------

    def is_ready(self) -> bool:
        return self._tools_ready and not self._updating

    def _set_tools_ready(self, ready: bool, text: str) -> None:
        self._tools_ready = ready
        self.download_btn.setEnabled(ready)
        self.tools_label.setText(text)
        self.tools_btn.setText("Atualizar yt-dlp" if ready else "Instalar componentes")
        self.tools_btn.setEnabled(not self._updating)

    def _check_tools(self) -> None:
        missing = tools.missing_tools()
        if missing:
            dialog = SetupDialog(missing, self)
            dialog.exec()
        if tools.resolve() is None:
            self._set_tools_ready(False, "Componentes não instalados.")
            return
        self._set_tools_ready(True, "Componentes prontos.")
        self._refresh_tools_label()
        last = float(self.settings.value("last_update_check", 0) or 0)
        if time.time() - last > UPDATE_INTERVAL:
            self._update_ytdlp(silent=True)

    def _refresh_tools_label(self) -> None:
        def describe(version):
            paths = tools.resolve()
            parts = [f"yt-dlp {version}" if version else "yt-dlp"]
            parts.append("FFmpeg ✓" if paths and paths.ffmpeg_dir else "FFmpeg ausente")
            parts.append("Deno ✓" if paths and paths.deno else "Deno ausente")
            self.tools_label.setText(" · ".join(parts))

        run_in_background(self, tools.ytdlp_version, on_success=describe)

    def _on_tools_button(self) -> None:
        if self._tools_ready:
            self._update_ytdlp(silent=False)
        else:
            self._check_tools()

    def _update_ytdlp(self, silent: bool) -> None:
        if self._updating:
            return
        self._updating = True
        self.tools_btn.setEnabled(False)
        self.tools_label.setText("Procurando atualizações do yt-dlp…")
        self.manager.set_paused(True)

        def finished(result):
            ok, output = result
            self._updating = False
            self.tools_btn.setEnabled(True)
            self.manager.set_paused(False)
            if ok:
                self.settings.setValue("last_update_check", time.time())
            self._refresh_tools_label()
            if not silent:
                box = QMessageBox(self)
                box.setWindowTitle("Atualização do yt-dlp")
                if ok:
                    box.setIcon(QMessageBox.Icon.Information)
                    box.setText("O yt-dlp está na versão mais recente.")
                else:
                    box.setIcon(QMessageBox.Icon.Warning)
                    box.setText("Não foi possível atualizar o yt-dlp agora.")
                box.setDetailedText(output or "")
                box.exec()

        run_in_background(
            self,
            tools.update_ytdlp,
            on_success=finished,
            on_failure=lambda message: finished((False, message)),
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"Sobre o {APP_DISPLAY_NAME}",
            f"<h3>{APP_DISPLAY_NAME} {__version__}</h3>"
            "<p>Baixa vídeos e músicas a partir de um link.</p>"
            "<p>Feito com <a href='https://github.com/yt-dlp/yt-dlp'>yt-dlp</a>, "
            "<a href='https://ffmpeg.org'>FFmpeg</a>, <a href='https://deno.com'>Deno</a>, "
            "<a href='https://www.qt.io/qt-for-python'>Qt for Python</a> e a fonte "
            "<a href='https://rsms.me/inter/'>Inter</a>.</p>"
            "<p>Respeite os direitos autorais e os Termos de Serviço dos sites: "
            "baixe apenas conteúdo seu, de domínio público, com licença livre "
            "ou com autorização de quem tem os direitos.</p>"
            f"<p>Componentes instalados em:<br><code>{tools.bin_dir()}</code></p>",
        )

    # ----------------------------------------------------------------------
    # Eventos da janela
    # ----------------------------------------------------------------------

    def _set_dragging(self, dragging: bool) -> None:
        self.hero.setProperty("dragging", dragging)
        theme.repolish(self.hero)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()
            self._set_dragging(True)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_dragging(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_dragging(False)
        mime = event.mimeData()
        text = mime.urls()[0].toString() if mime.hasUrls() else mime.text()
        if text:
            self.url_edit.setText(text.strip())
            self.url_edit.setFocus()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.manager.active_count():
            answer = QMessageBox.question(
                self,
                "Sair do Baixador?",
                "Ainda há downloads em andamento. Se sair agora, eles serão cancelados.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._save_settings()
        self.manager.shutdown()
        super().closeEvent(event)


def window_icon() -> QIcon:
    return QIcon(str(tools.resource_path("assets/icon.png")))
