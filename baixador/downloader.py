"""Monta a linha de comando do yt-dlp, roda o processo e interpreta a saída.

Este módulo não depende do Qt, para poder ser testado sozinho.

O yt-dlp é instruído a imprimir linhas com o prefixo "BXD:" seguidas de
JSON, assim não precisamos adivinhar nada a partir do texto em inglês:

    BXD:INFO {...}   dados do vídeo (título, canal, duração, miniatura...)
    BXD:FMTS [...]   partes que serão baixadas (vídeo e áudio separados)
    BXD:PROG {...} {...}  progresso do download e a parte atual
    BXD:PP {...}     etapa de pós-processamento (juntar, converter...)
    BXD:FILE "..."   arquivo final salvo
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from . import tools

MODE_VIDEO = "video"
MODE_MP3 = "mp3"
MODE_M4A = "m4a"

MODES = [
    (MODE_VIDEO, "Vídeo (MP4)"),
    (MODE_MP3, "Áudio (MP3)"),
    (MODE_M4A, "Áudio (M4A)"),
]

QUALITIES = {
    MODE_VIDEO: [
        ("best", "Melhor disponível"),
        ("2160", "4K (2160p)"),
        ("1440", "2K (1440p)"),
        ("1080", "Full HD (1080p)"),
        ("720", "HD (720p)"),
        ("480", "480p"),
        ("360", "360p"),
    ],
    MODE_MP3: [
        ("320", "320 kbps"),
        ("192", "192 kbps"),
        ("128", "128 kbps"),
    ],
    MODE_M4A: [
        ("best", "Original (sem conversão)"),
    ],
}

DEFAULT_QUALITY = {MODE_VIDEO: "1080", MODE_MP3: "192", MODE_M4A: "best"}

MARK = "BXD:"
INFO_FIELDS = (
    "id,title,uploader,channel,duration,thumbnail,extractor_key,"
    "playlist_title,playlist_index,n_entries,playlist_count"
)
PROGRESS_FIELDS = (
    "status,downloaded_bytes,total_bytes,total_bytes_estimate,speed,eta,"
    "fragment_index,fragment_count,filename,tmpfilename"
)

PP_LABELS = {
    "Merger": "Juntando vídeo e áudio…",
    "ExtractAudio": "Convertendo o áudio…",
    "EmbedThumbnail": "Adicionando a capa…",
    "ThumbnailsConvertor": "Preparando a capa…",
    "Metadata": "Gravando informações…",
    "VideoRemuxer": "Convertendo o vídeo…",
    "VideoConvertor": "Convertendo o vídeo…",
    "MoveFiles": "Finalizando…",
}


@dataclass
class DownloadOptions:
    url: str
    output_dir: str
    mode: str = MODE_VIDEO
    quality: str = "1080"
    compatible: bool = False  # prefere H.264, que abre em qualquer player
    playlist: bool = False

    def describe(self) -> str:
        mode_label = dict(MODES).get(self.mode, self.mode)
        quality_label = dict(QUALITIES.get(self.mode, [])).get(self.quality, self.quality)
        return f"{mode_label} · {quality_label}"


# --------------------------------------------------------------------------
# Link e linha de comando
# --------------------------------------------------------------------------

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def normalize_url(text: str) -> str | None:
    """Limpa o texto colado pelo usuário; devolve None se não for um link."""
    if not text:
        return None
    candidates = text.split()
    if not candidates:
        return None
    url = next((c for c in candidates if "://" in c), candidates[0])
    url = url.strip("\"'<>()[]")
    if not _SCHEME_RE.match(url):
        host = url.split("/", 1)[0]
        if "." not in host:
            return None
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return None
    return url


def output_template(opts: DownloadOptions) -> str:
    # O ".150B" limita o nome a 150 bytes, evitando caminhos longos demais no Windows.
    if opts.playlist:
        return (
            "%(playlist_title,playlist_id|Playlist).80B/"
            "%(playlist_index|0)03d - %(title).120B.%(ext)s"
        )
    return "%(title).150B.%(ext)s"


def format_args(opts: DownloadOptions) -> list[str]:
    if opts.mode == MODE_MP3:
        quality = opts.quality if opts.quality.isdigit() else "192"
        return ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", f"{quality}K"]
    if opts.mode == MODE_M4A:
        return ["-f", "ba[ext=m4a]/ba/b", "-x", "--audio-format", "m4a"]

    res = "res" if opts.quality == "best" else f"res:{opts.quality}"
    if opts.compatible:
        # H.264 primeiro (abre em qualquer player, mas no YouTube vai só até 1080p).
        sort = f"vcodec:h264,{res},ext:mp4:m4a"
    else:
        # Resolução primeiro; entre iguais, prefere MP4 + áudio M4A.
        sort = f"{res},ext:mp4:m4a"
    return ["-f", "bv*+ba/b", "-S", sort, "--merge-output-format", "mp4"]


def build_args(opts: DownloadOptions, paths: tools.ToolPaths) -> list[str]:
    args = [
        paths.ytdlp,
        "--ignore-config",
        "--newline",
        "--progress",
        "--no-simulate",
        "--color", "never",
        "--progress-delta", "0.4",
        "--print", f"video:{MARK}INFO %(.{{{INFO_FIELDS}}})j",
        "--print", f"video:{MARK}FMTS %(requested_formats.:.{{format_id,filesize,filesize_approx,vcodec}})j",
        "--print", f"after_move:{MARK}FILE %(filepath)j",
        "--progress-template", f"download:{MARK}PROG %(progress.{{{PROGRESS_FIELDS}}})j %(info.{{format_id,vcodec}})j",
        "--progress-template", f"postprocess:{MARK}PP %(progress.{{postprocessor,status}})j",
        "--windows-filenames",
        "--no-mtime",
        "--concurrent-fragments", "4",
        "--embed-metadata",
        "--embed-thumbnail",
        "--convert-thumbnails", "jpg",
        "-P", opts.output_dir,
        "-o", output_template(opts),
    ]
    if paths.ffmpeg_dir:
        args += ["--ffmpeg-location", paths.ffmpeg_dir]
    if paths.deno:
        args += ["--js-runtimes", f"deno:{paths.deno}"]
    if opts.playlist:
        # Um vídeo indisponível não deve interromper a playlist inteira.
        args += ["--yes-playlist", "--ignore-errors"]
    else:
        args += ["--no-playlist"]
    args += format_args(opts)
    args += ["--", opts.url]
    return args


# --------------------------------------------------------------------------
# Mensagens de erro
# --------------------------------------------------------------------------

ERROR_HINTS = [
    ("Private video", "Este vídeo é privado."),
    ("members-only", "Este vídeo é exclusivo para membros do canal."),
    ("Join this channel", "Este vídeo é exclusivo para membros do canal."),
    ("Sign in to confirm your age", "Este vídeo tem restrição de idade e exige login no YouTube."),
    ("not a bot", "O YouTube pediu uma verificação anti-robô. Aguarde alguns minutos e tente de novo, ou atualize o yt-dlp."),
    ("Video unavailable", "Este vídeo está indisponível."),
    ("This video is unavailable", "Este vídeo está indisponível."),
    ("This video has been removed", "Este vídeo foi removido."),
    ("not available in your country", "Este vídeo não está disponível no seu país."),
    ("Premieres in", "Este vídeo ainda não estreou."),
    ("live event will begin", "Esta transmissão ao vivo ainda não começou."),
    ("Unsupported URL", "Este link não é suportado."),
    ("is not a valid URL", "Este link não é válido."),
    ("Requested format is not available", "A qualidade escolhida não está disponível para este vídeo."),
    ("HTTP Error 403", "O servidor recusou o download (erro 403). Tente atualizar o yt-dlp."),
    ("HTTP Error 429", "Muitos downloads em pouco tempo (erro 429). Aguarde alguns minutos e tente de novo."),
    ("HTTP Error 404", "Conteúdo não encontrado (erro 404)."),
    ("getaddrinfo failed", "Sem conexão com a internet."),
    ("Name or service not known", "Sem conexão com a internet."),
    ("Temporary failure in name resolution", "Sem conexão com a internet."),
    ("nodename nor servname", "Sem conexão com a internet."),
    ("timed out", "A conexão demorou demais para responder. Verifique sua internet."),
    ("Unable to download webpage", "Não foi possível acessar o site. Verifique sua conexão com a internet."),
    ("No space left on device", "Não há espaço suficiente no disco."),
    ("Permission denied", "Sem permissão para salvar na pasta escolhida."),
    ("ffmpeg not found", "O FFmpeg não foi encontrado. Reinstale os componentes."),
    ("ffprobe and ffmpeg not found", "O FFmpeg não foi encontrado. Reinstale os componentes."),
    ("JavaScript runtime", "O Deno não foi encontrado. Reinstale os componentes."),
]

_ERROR_PREFIX_RE = re.compile(r"^(ERROR:\s*)?(\[[^\]]+\]\s*)?([\w-]{6,}:\s+)?")


def friendly_error(message: str) -> str:
    for needle, hint in ERROR_HINTS:
        if needle.lower() in message.lower():
            return hint
    cleaned = _ERROR_PREFIX_RE.sub("", message.strip(), count=1).strip()
    return cleaned or "Ocorreu um erro desconhecido."


# --------------------------------------------------------------------------
# Leitura da saída
# --------------------------------------------------------------------------


def _decode_json_values(text: str) -> list:
    decoder = json.JSONDecoder()
    values, pos = [], 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        try:
            value, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            # O yt-dlp imprime "NA" quando um campo não existe.
            break
        values.append(value)
    return values


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value >= 0 else None


@dataclass
class OutputParser:
    """Transforma as linhas do yt-dlp em eventos (dicionários) para a interface."""

    parts: list[dict] = field(default_factory=list)
    part_sizes: dict[str, float] = field(default_factory=dict)
    finished_parts: set[str] = field(default_factory=set)
    files: list[str] = field(default_factory=list)
    partial_files: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    log: deque = field(default_factory=lambda: deque(maxlen=400))
    playlist_index: int | None = None
    playlist_count: int | None = None

    def feed(self, line: str) -> list[dict]:
        line = line.rstrip("\r\n")
        if not line.strip():
            return []
        if not line.startswith(MARK):
            self.log.append(line)
            if line.startswith("ERROR:"):
                self.errors.append(line)
                return [{"type": "error", "message": line}]
            return []

        kind, _, payload = line[len(MARK):].partition(" ")
        values = _decode_json_values(payload)
        if kind != "PROG":
            self.log.append(line)
        if kind == "INFO" and values and isinstance(values[0], dict):
            return [self._on_info(values[0])]
        if kind == "FMTS":
            self._on_formats(values[0] if values and isinstance(values[0], list) else [])
            return []
        if kind == "PROG" and values and isinstance(values[0], dict):
            part = values[1] if len(values) > 1 and isinstance(values[1], dict) else {}
            return [self._on_progress(values[0], part)]
        if kind == "PP" and values and isinstance(values[0], dict):
            event = self._on_postprocess(values[0])
            return [event] if event else []
        if kind == "FILE" and values and isinstance(values[0], str):
            self.files.append(values[0])
            return [{"type": "file", "path": values[0]}]
        return []

    # -- handlers ---------------------------------------------------------

    def _on_info(self, info: dict) -> dict:
        self.parts = []
        self.part_sizes = {}
        self.finished_parts = set()
        self.playlist_index = info.get("playlist_index")
        self.playlist_count = info.get("n_entries") or info.get("playlist_count")
        thumbnail = info.get("thumbnail")
        if info.get("extractor_key") == "Youtube" and info.get("id"):
            # Miniatura em JPG e num tamanho pequeno, em vez do WebP gigante.
            thumbnail = f"https://i.ytimg.com/vi/{info['id']}/mqdefault.jpg"
        return {
            "type": "info",
            "title": info.get("title") or "",
            "uploader": info.get("uploader") or info.get("channel") or "",
            "duration": _number(info.get("duration")),
            "thumbnail": thumbnail,
            "playlist_title": info.get("playlist_title"),
            "playlist_index": self.playlist_index,
            "playlist_count": self.playlist_count,
        }

    def _on_formats(self, formats: list) -> None:
        self.parts = [f for f in formats if isinstance(f, dict)]
        for fmt in self.parts:
            size = _number(fmt.get("filesize")) or _number(fmt.get("filesize_approx"))
            if size:
                self.part_sizes[str(fmt.get("format_id"))] = size

    def _on_progress(self, prog: dict, part: dict) -> dict:
        format_id = str(part.get("format_id", ""))
        for key in ("filename", "tmpfilename"):
            if isinstance(prog.get(key), str):
                self.partial_files.add(prog[key])
        downloaded = _number(prog.get("downloaded_bytes")) or 0.0
        total = _number(prog.get("total_bytes")) or _number(prog.get("total_bytes_estimate"))
        if total and format_id:
            self.part_sizes[format_id] = total

        fraction = None
        if total:
            fraction = min(downloaded / total, 1.0)
        elif prog.get("fragment_count"):
            fraction = min((prog.get("fragment_index") or 0) / prog["fragment_count"], 1.0)
        if prog.get("status") == "finished":
            fraction = 1.0
            self.finished_parts.add(format_id)

        percent = self._overall_percent(format_id, fraction)
        ids = [str(p.get("format_id")) for p in self.parts]
        if len(ids) > 1:
            index = ids.index(format_id) if format_id in ids else 0
            is_video = (part.get("vcodec") or "none") != "none"
            stage = f"Baixando {'vídeo' if is_video else 'áudio'} ({index + 1}/{len(ids)})"
        else:
            stage = "Baixando"

        return {
            "type": "progress",
            "percent": percent,
            "downloaded": downloaded,
            "total": total,
            "speed": _number(prog.get("speed")),
            "eta": _number(prog.get("eta")),
            "stage": stage,
        }

    def _overall_percent(self, format_id: str, fraction: float | None) -> float | None:
        """Junta o progresso das partes (vídeo + áudio) numa porcentagem só."""
        if fraction is None:
            return None
        ids = [str(p.get("format_id")) for p in self.parts]
        if len(ids) <= 1 or format_id not in ids:
            return fraction * 100
        index = ids.index(format_id)
        sizes = [self.part_sizes.get(i) for i in ids]
        if all(sizes):
            done = sum(sizes[:index]) + sizes[index] * fraction
            return min(done / sum(sizes) * 100, 100.0)
        return (index + fraction) / len(ids) * 100

    def _on_postprocess(self, pp: dict) -> dict | None:
        if pp.get("status") != "started":
            return None
        name = str(pp.get("postprocessor") or "")
        label = PP_LABELS.get(name)
        if label is None:
            label = "Ajustando o arquivo…" if name.startswith("Fixup") else "Processando…"
        return {"type": "postprocess", "stage": label}


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------

STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


@dataclass
class DownloadResult:
    status: str
    files: list[str]
    error: str | None = None
    raw_error: str | None = None
    log: str = ""


class DownloadRunner:
    """Roda um download do yt-dlp (bloqueante) e repassa os eventos."""

    def __init__(
        self,
        opts: DownloadOptions,
        paths: tools.ToolPaths,
        on_event: Callable[[dict], None],
    ):
        self.opts = opts
        self.paths = paths
        self.on_event = on_event
        self._proc: subprocess.Popen | None = None
        self._cancelled = threading.Event()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            tools.kill_process_tree(proc)

    def run(self) -> DownloadResult:
        parser = OutputParser()
        args = build_args(self.opts, self.paths)
        try:
            with self._lock:
                if self._cancelled.is_set():
                    return DownloadResult(STATUS_CANCELLED, [])
                self._proc = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **tools.popen_kwargs()
                )
            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace")
                for event in parser.feed(line):
                    self.on_event(event)
            code = self._proc.wait()
        except OSError as exc:
            return DownloadResult(
                STATUS_ERROR, [], "Não foi possível iniciar o yt-dlp.", str(exc), str(exc)
            )

        log = "\n".join(parser.log)
        if self._cancelled.is_set():
            remove_partial_files(parser.partial_files, keep=parser.files)
            return DownloadResult(STATUS_CANCELLED, parser.files, log=log)
        if code == 0 or (self.opts.playlist and parser.files):
            # Em playlists, alguns vídeos podem falhar sem estragar o resto.
            raw = parser.errors[-1] if parser.errors else None
            return DownloadResult(STATUS_DONE, parser.files, raw_error=raw, log=log)
        raw = parser.errors[-1] if parser.errors else (parser.log[-1] if parser.log else "")
        return DownloadResult(STATUS_ERROR, parser.files, friendly_error(raw), raw, log)


def remove_partial_files(paths: set[str], keep: list[str]) -> None:
    """Apaga o que sobrou de um download cancelado (.part, fragmentos, partes soltas)."""
    keep_set = {os.path.abspath(k) for k in keep}
    for path in paths:
        candidates = [path, path + ".part", path + ".ytdl"]
        candidates += glob.glob(glob.escape(path) + "-Frag*")
        for candidate in candidates:
            if os.path.abspath(candidate) in keep_set:
                continue
            try:
                if os.path.isfile(candidate):
                    os.remove(candidate)
            except OSError:
                pass  # arquivo ainda preso pelo sistema; não é grave


# --------------------------------------------------------------------------
# Formatação
# --------------------------------------------------------------------------


def _decimal(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def human_size(num: float | None) -> str:
    if num is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{int(num)} {unit}" if unit == "B" else f"{_decimal(num)} {unit}"
        num /= 1024
    return f"{_decimal(num)} TB"


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
