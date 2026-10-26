"""Inicialização do Qt."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTimer, QTranslator
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__, tools
from . import theme
from .main_window import MainWindow, window_icon


def run() -> int:
    app = QApplication(sys.argv)
    # Nome e organização definem onde o QSettings guarda as preferências.
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(window_icon())
    if tools.current_os() == "linux":
        app.setDesktopFileName("baixador")  # liga a janela ao ícone do .desktop

    # Traduz os textos do próprio Qt ("Sim", "Não", "Mostrar detalhes…", diálogos de pasta).
    translator = QTranslator(app)
    translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil), "qtbase", "_", translations):
        app.installTranslator(translator)

    theme.load_fonts(app)
    theme.set_preference(app, str(QSettings().value("theme", theme.THEME_SYSTEM)))
    app.styleHints().colorSchemeChanged.connect(lambda *_: theme.apply(app))

    args = app.arguments()[1:]
    smoke_args = args[args.index("--smoke-test") + 1:] if "--smoke-test" in args else None

    window = MainWindow(check_tools=smoke_args is None or bool(smoke_args))
    window.show()
    if smoke_args is not None:
        _smoke_test(app, window, smoke_args)
    return app.exec()


def _smoke_test(app: QApplication, window: MainWindow, args: list[str]) -> None:
    """Diagnóstico: `Baixador --smoke-test [LINK [PASTA]]`.

    Sem link, só confere se a janela abre (usado no GitHub Actions). Com link,
    baixa o vídeo pela interface e sai com código 0 se tudo deu certo.
    """
    def finish(code: int, message: str) -> None:
        print(message, flush=True)
        app.exit(code)

    if not args:
        QTimer.singleShot(1500, lambda: finish(0, "smoke-test: janela aberta com sucesso"))
        return

    url, folder = args[0], (args[1] if len(args) > 1 else None)
    state = {"submitted": False}

    def poll() -> None:
        if not state["submitted"]:
            if window.is_ready():
                if folder:
                    window._set_output_dir(folder)
                window.url_edit.setText(url)
                window.download_btn.click()
                state["submitted"] = True
        elif window.manager.jobs and all(j.finished for j in window.manager.jobs):
            job = window.manager.jobs[-1]
            detail = job.files or job.error or job.status_text
            finish(0 if job.state == "done" else 1, f"smoke-test: {job.state} {detail}")
            return
        QTimer.singleShot(300, poll)

    QTimer.singleShot(300, poll)
    QTimer.singleShot(300_000, lambda: finish(2, "smoke-test: tempo esgotado"))
