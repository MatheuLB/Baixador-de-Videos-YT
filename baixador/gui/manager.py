"""Fila de downloads: guarda o estado de cada item e controla quantos rodam juntos."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal

from .. import tools
from ..downloader import (
    STATUS_CANCELLED,
    STATUS_DONE,
    DownloadOptions,
    DownloadResult,
    human_duration,
    human_size,
)
from .workers import DownloadWorker

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
ERROR = "error"
CANCELLED = "cancelled"

MAX_CONCURRENT = 2


class Job(QObject):
    """Um item da lista de downloads."""

    changed = Signal()

    def __init__(self, opts: DownloadOptions):
        super().__init__()
        self.opts = opts
        self.state = QUEUED
        self.title = opts.url
        self.uploader = ""
        self.duration: float | None = None
        self.thumbnail_url: str | None = None
        self.playlist_title: str | None = None
        self.playlist_position = ""
        self.percent: float | None = 0.0
        self.badge = "Na fila"  # texto curto do selo colorido
        self.status_text = "Aguardando a vez…"
        self.files: list[str] = []
        self.error: str | None = None
        self.log = ""
        self.worker: DownloadWorker | None = None

    @property
    def finished(self) -> bool:
        return self.state in (DONE, ERROR, CANCELLED)

    @property
    def meta_text(self) -> str:
        parts = []
        if self.playlist_position:
            parts.append(self.playlist_position)
        if self.uploader:
            parts.append(self.uploader)
        if self.duration:
            parts.append(human_duration(self.duration))
        parts.append(self.opts.describe())
        return " · ".join(parts)

    @property
    def display_title(self) -> str:
        if self.opts.playlist and self.playlist_title:
            return self.playlist_title
        return self.title

    # -- eventos do yt-dlp ------------------------------------------------

    def apply_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "info":
            self.title = event["title"] or self.title
            self.uploader = event["uploader"]
            self.duration = event["duration"]
            self.thumbnail_url = self.thumbnail_url or event["thumbnail"]
            self.playlist_title = event.get("playlist_title") or self.playlist_title
            index, count = event.get("playlist_index"), event.get("playlist_count")
            if self.opts.playlist and index and count:
                self.playlist_position = f"Vídeo {index} de {count}: {self.title}"
            self.badge = "Preparando"
            self.status_text = "Escolhendo a melhor versão…"
        elif kind == "progress":
            self.percent = event["percent"]
            self.badge = f"{event['percent']:.0f}%" if event["percent"] is not None else "Baixando"
            self.status_text = _progress_text(event)
        elif kind == "postprocess":
            self.percent = None
            self.badge = "Processando"
            self.status_text = event["stage"]
        elif kind == "file":
            self.files.append(event["path"])
        else:
            return
        self.changed.emit()

    def mark_running(self) -> None:
        self.state = RUNNING
        self.percent = None
        self.error = None
        self.badge = "Iniciando"
        self.status_text = "Buscando informações do vídeo…"
        self.changed.emit()

    def finish(self, result: DownloadResult) -> None:
        self.worker = None
        self.log = result.log
        self.files = result.files or self.files
        if result.status == STATUS_DONE:
            self.state = DONE
            self.percent = 100.0
            self.badge = "Concluído"
            self.status_text = _done_text(self.files, result)
        elif result.status == STATUS_CANCELLED:
            self.state = CANCELLED
            self.badge = "Cancelado"
            self.status_text = "Você cancelou este download."
        else:
            self.state = ERROR
            self.error = result.error
            self.log = result.log or (result.raw_error or "")
            self.badge = "Erro"
            self.status_text = result.error or "O download falhou."
        self.changed.emit()


def _progress_text(event: dict) -> str:
    pieces = [event["stage"]]
    if event["percent"] is None and event["downloaded"]:
        pieces.append(human_size(event["downloaded"]))
    if event["speed"]:
        pieces.append(f"{human_size(event['speed'])}/s")
    if event["eta"] is not None and event["percent"] is not None and event["percent"] < 100:
        pieces.append(f"faltam {human_duration(event['eta'])}")
    return " · ".join(pieces)


def _done_text(files: list[str], result: DownloadResult) -> str:
    sizes = [os.path.getsize(f) for f in files if os.path.isfile(f)]
    if len(files) > 1:
        text = f"{len(files)} arquivos · {human_size(sum(sizes))}"
    elif files:
        name = os.path.basename(files[0])
        text = f"{human_size(sizes[0])} · {name}" if sizes else name
    else:
        text = "Arquivo salvo"
    if result.raw_error:
        text += " · alguns vídeos falharam"
    return text


class DownloadManager(QObject):
    job_added = Signal(object)
    job_removed = Signal(object)
    active_changed = Signal(int)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.jobs: list[Job] = []
        self._paused = False

    # -- API ---------------------------------------------------------------

    def add(self, opts: DownloadOptions) -> Job:
        job = Job(opts)
        self.jobs.append(job)
        self.job_added.emit(job)
        self._pump()
        return job

    def retry(self, job: Job) -> None:
        if job.finished:
            job.state = QUEUED
            job.percent = 0.0
            job.badge = "Na fila"
            job.status_text = "Aguardando a vez…"
            job.changed.emit()
            self._pump()

    def cancel(self, job: Job) -> None:
        if job.state == QUEUED:
            job.state = CANCELLED
            job.badge = "Cancelado"
            job.status_text = "Você cancelou este download."
            job.changed.emit()
            self._pump()
        elif job.state == RUNNING and job.worker is not None:
            job.badge = "Cancelando"
            job.status_text = "Encerrando o download…"
            job.changed.emit()
            job.worker.cancel()

    def remove(self, job: Job) -> None:
        if job.finished and job in self.jobs:
            self.jobs.remove(job)
            self.job_removed.emit(job)

    def clear_finished(self) -> None:
        for job in [j for j in self.jobs if j.finished]:
            self.remove(job)

    def set_paused(self, paused: bool) -> None:
        """Segura a fila (por exemplo, enquanto o yt-dlp se atualiza)."""
        self._paused = paused
        if not paused:
            self._pump()

    def active_count(self) -> int:
        return sum(1 for j in self.jobs if j.state in (QUEUED, RUNNING))

    def shutdown(self, timeout_ms: int = 5000) -> None:
        self._paused = True
        running = [j for j in self.jobs if j.state == RUNNING and j.worker]
        for job in running:
            job.worker.cancel()
        for job in running:
            if job.worker:
                job.worker.wait(timeout_ms)

    # -- interno -------------------------------------------------------------

    def _pump(self) -> None:
        if not self._paused:
            running = sum(1 for j in self.jobs if j.state == RUNNING)
            for job in self.jobs:
                if running >= MAX_CONCURRENT:
                    break
                if job.state == QUEUED:
                    self._start(job)
                    running += 1
        self.active_changed.emit(self.active_count())

    def _start(self, job: Job) -> None:
        paths = tools.resolve()
        if paths is None:
            job.finish(
                DownloadResult(
                    "error", [], "O yt-dlp não está instalado. Use “Instalar componentes”."
                )
            )
            return
        worker = DownloadWorker(job.opts, paths, parent=self)
        job.worker = worker
        worker.event.connect(job.apply_event)
        worker.result.connect(lambda result, j=job: self._on_finished(j, result))
        worker.finished.connect(worker.deleteLater)
        job.mark_running()
        worker.start()

    def _on_finished(self, job: Job, result: DownloadResult) -> None:
        job.finish(result)
        self._pump()
