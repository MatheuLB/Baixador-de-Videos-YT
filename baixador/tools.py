"""Localiza, instala e atualiza os programas externos usados pelo app.

O Baixador é só a interface. O trabalho pesado é feito por programas
externos, que o app baixa na primeira execução para a pasta de dados do
usuário. Assim o instalador fica pequeno e o yt-dlp pode se atualizar
sozinho sempre que o YouTube mudar alguma coisa:

- yt-dlp: extrai e baixa os vídeos
- ffmpeg / ffprobe: juntam vídeo + áudio e convertem para MP3
- deno: runtime JavaScript que o yt-dlp exige para o YouTube
"""

from __future__ import annotations

import gzip
import os
import platform
import shutil
import signal
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import APP_NAME, __version__

YTDLP = "yt-dlp"
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
DENO = "deno"

TOOL_LABELS = {YTDLP: "yt-dlp", FFMPEG: "FFmpeg", FFPROBE: "FFprobe", DENO: "Deno"}

GITHUB = "https://github.com"
# Builds estáticos do FFmpeg para Windows, macOS e Linux (os mesmos do pacote
# npm "ffmpeg-static"). A versão fica fixa para o app não quebrar se o
# projeto mudar o nome dos arquivos numa versão futura.
FFMPEG_RELEASE = f"{GITHUB}/eugeneware/ffmpeg-static/releases/download/b6.1.1"

ProgressCallback = Callable[[int, int], None]  # (bytes baixados, total ou 0)
CancelCheck = Callable[[], bool]


class InstallCancelled(Exception):
    pass


class InstallError(Exception):
    pass


# --------------------------------------------------------------------------
# Plataforma e pastas
# --------------------------------------------------------------------------


def current_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def current_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64", "armv8l", "armv8b"):
        return "arm64"
    return "x64"


def exe_name(key: str, os_name: str | None = None) -> str:
    return key + ".exe" if (os_name or current_os()) == "windows" else key


def data_dir() -> Path:
    """Pasta onde o app guarda os componentes baixados."""
    override = os.environ.get("BAIXADOR_DATA_DIR")
    if override:
        return Path(override)
    os_name = current_os()
    if os_name == "windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if os_name == "macos":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME.lower()


def bin_dir() -> Path:
    return data_dir() / "bin"


def resource_path(relative: str) -> Path:
    """Caminho de um arquivo de `assets/`, rodando do código-fonte ou empacotado."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative


# --------------------------------------------------------------------------
# Localização
# --------------------------------------------------------------------------


def _is_executable(path: Path) -> bool:
    return path.is_file() and (current_os() == "windows" or os.access(path, os.X_OK))


def _extra_search_dirs() -> list[Path]:
    # Apps abertos pelo Finder/menu não herdam o PATH do terminal, então
    # procuramos também nos lugares onde Homebrew, Deno etc. costumam instalar.
    home = Path.home()
    dirs = [home / ".deno" / "bin", home / ".local" / "bin"]
    if current_os() == "macos":
        dirs += [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    elif current_os() == "linux":
        dirs += [Path("/usr/local/bin"), Path("/usr/bin"), Path("/snap/bin")]
    return dirs


def own_tool_path(key: str) -> Path:
    return bin_dir() / exe_name(key)


def find_tool(key: str) -> Path | None:
    """Procura primeiro a cópia do app, depois o PATH e pastas comuns."""
    own = own_tool_path(key)
    if _is_executable(own):
        return own
    found = shutil.which(key)
    if found:
        return Path(found)
    for directory in _extra_search_dirs():
        candidate = directory / exe_name(key)
        if _is_executable(candidate):
            return candidate
    return None


def find_ffmpeg_dir() -> Path | None:
    """Pasta que contém ffmpeg *e* ffprobe (o yt-dlp procura os dois juntos)."""
    candidates = [bin_dir()]
    found = shutil.which(FFMPEG)
    if found:
        candidates.append(Path(found).parent)
    candidates += _extra_search_dirs()
    for directory in candidates:
        if _is_executable(directory / exe_name(FFMPEG)) and _is_executable(
            directory / exe_name(FFPROBE)
        ):
            return directory
    return None


def missing_tools() -> list[str]:
    """Componentes que precisam ser baixados antes de usar o app."""
    missing = []
    # Do yt-dlp usamos sempre uma cópia própria, que o app consegue atualizar.
    if not _is_executable(own_tool_path(YTDLP)):
        missing.append(YTDLP)
    if find_ffmpeg_dir() is None:
        missing += [FFMPEG, FFPROBE]
    if find_tool(DENO) is None:
        missing.append(DENO)
    return missing


@dataclass(frozen=True)
class ToolPaths:
    ytdlp: str
    ffmpeg_dir: str | None
    deno: str | None


def resolve() -> ToolPaths | None:
    ytdlp = find_tool(YTDLP)
    if ytdlp is None:
        return None
    ffmpeg_dir = find_ffmpeg_dir()
    deno = find_tool(DENO)
    return ToolPaths(
        ytdlp=str(ytdlp),
        ffmpeg_dir=str(ffmpeg_dir) if ffmpeg_dir else None,
        deno=str(deno) if deno else None,
    )


# --------------------------------------------------------------------------
# Instalação
# --------------------------------------------------------------------------


def download_url(key: str, os_name: str | None = None, arch: str | None = None) -> tuple[str, str]:
    """Retorna (url, tipo) do componente; tipo é "raw", "gz" ou "zip"."""
    os_name = os_name or current_os()
    arch = arch or current_arch()
    if os_name == "windows":
        # Os executáveis x64 também rodam no Windows ARM (por emulação).
        arch = "x64"

    if key == YTDLP:
        base = f"{GITHUB}/yt-dlp/yt-dlp/releases/latest/download"
        if os_name == "windows":
            return f"{base}/yt-dlp.exe", "raw"
        if os_name == "macos":
            return f"{base}/yt-dlp_macos", "raw"  # binário universal (Intel + Apple Silicon)
        suffix = "_aarch64" if arch == "arm64" else ""
        return f"{base}/yt-dlp_linux{suffix}", "raw"

    if key in (FFMPEG, FFPROBE):
        platform_name = {"windows": "win32", "macos": "darwin", "linux": "linux"}[os_name]
        return f"{FFMPEG_RELEASE}/{key}-{platform_name}-{arch}.gz", "gz"

    if key == DENO:
        cpu = "aarch64" if arch == "arm64" else "x86_64"
        target = {
            "windows": "pc-windows-msvc",
            "macos": "apple-darwin",
            "linux": "unknown-linux-gnu",
        }[os_name]
        return f"{GITHUB}/denoland/deno/releases/latest/download/deno-{cpu}-{target}.zip", "zip"

    raise ValueError(f"componente desconhecido: {key}")


def ssl_context() -> ssl.SSLContext:
    # Certificados do sistema + os do certifi: o Python empacotado no macOS
    # não enxerga os certificados do sistema, e no Windows/Linux os do sistema
    # são necessários atrás de proxies corporativos.
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(certifi.where())
    except Exception:
        pass
    return context


def open_url(url: str, timeout: float = 30):
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context()))
    return opener.open(request, timeout=timeout)


def fetch_bytes(url: str, timeout: float = 15, limit: int = 5_000_000) -> bytes:
    with open_url(url, timeout=timeout) as response:
        return response.read(limit)


def _download_file(
    url: str, dest: Path, progress: ProgressCallback | None, cancelled: CancelCheck | None
) -> None:
    with open_url(url, timeout=60) as response, open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                raise InstallCancelled()
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if total and done < total:
        raise InstallError(f"download incompleto ({done} de {total} bytes)")


def _extract_from_zip(archive: Path, name: str, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        member = next((m for m in zf.namelist() if Path(m).name == name), None)
        if member is None:
            raise InstallError(f"{name} não encontrado dentro do arquivo baixado")
        with zf.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)


def install_tool(
    key: str,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> Path:
    """Baixa um componente para a pasta do app e devolve o caminho dele."""
    url, kind = download_url(key)
    name = exe_name(key)
    target = bin_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)

    # A pasta temporária fica no mesmo disco do destino para o os.replace
    # final ser atômico: nunca deixamos um executável pela metade.
    with tempfile.TemporaryDirectory(prefix="download-", dir=data_dir()) as tmp:
        downloaded = Path(tmp) / "download"
        ready = Path(tmp) / name
        _download_file(url, downloaded, progress, cancelled)
        if kind == "raw":
            downloaded.replace(ready)
        elif kind == "gz":
            with gzip.open(downloaded, "rb") as src, open(ready, "wb") as out:
                shutil.copyfileobj(src, out)
        else:
            _extract_from_zip(downloaded, name, ready)
        if current_os() != "windows":
            ready.chmod(ready.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(ready, target)
    return target


# --------------------------------------------------------------------------
# Execução de processos
# --------------------------------------------------------------------------


def child_env() -> dict[str, str]:
    """Ambiente para os programas filhos, sem as variáveis do PyInstaller.

    O yt-dlp também é um executável do PyInstaller; se ele herdar as
    variáveis do nosso processo, pode tentar usar as bibliotecas erradas.
    """
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("_PYI", "_MEI")):
            del env[name]
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        original = env.pop(var + "_ORIG", None)
        if original is not None:
            env[var] = original
        elif getattr(sys, "frozen", False):
            env.pop(var, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def popen_kwargs() -> dict:
    kwargs: dict = {"env": child_env(), "stdin": subprocess.DEVNULL}
    if current_os() == "windows":
        # Sem isso, cada execução do yt-dlp abriria uma janela de terminal.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        # Grupo de processos próprio: assim conseguimos encerrar o yt-dlp
        # junto com o ffmpeg que ele tiver aberto.
        kwargs["start_new_session"] = True
    return kwargs


def kill_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if current_os() == "windows":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_tool(args: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    kwargs = popen_kwargs()
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


def ytdlp_version() -> str | None:
    ytdlp = find_tool(YTDLP)
    if ytdlp is None:
        return None
    try:
        result = run_tool([str(ytdlp), "--version"], timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = result.stdout.strip().splitlines()
    return lines[-1].strip() if result.returncode == 0 and lines else None


def update_ytdlp() -> tuple[bool, str]:
    """Atualiza a cópia do yt-dlp do app. Retorna (sucesso, saída do yt-dlp)."""
    own = own_tool_path(YTDLP)
    if not _is_executable(own):
        return False, "O yt-dlp ainda não foi instalado."
    try:
        result = run_tool([str(own), "-U"], timeout=180)
    except subprocess.TimeoutExpired:
        return False, "A atualização demorou demais e foi interrompida."
    except OSError as exc:
        return False, str(exc)
    output = result.stdout.strip()
    # O yt-dlp usa o código 100 para "atualizado, reinicie o programa", e em
    # algumas falhas de rede ele imprime "ERROR:" mas ainda sai com 0.
    ok = result.returncode in (0, 100) and "ERROR:" not in output
    return ok, output
