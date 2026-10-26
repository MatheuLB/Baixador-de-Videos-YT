import gzip
import io
import zipfile

import pytest

from baixador import tools


@pytest.mark.parametrize(
    "os_name,arch,expected",
    [
        ("windows", "x64", "yt-dlp.exe"),
        ("windows", "arm64", "yt-dlp.exe"),
        ("macos", "arm64", "yt-dlp_macos"),
        ("linux", "x64", "yt-dlp_linux"),
        ("linux", "arm64", "yt-dlp_linux_aarch64"),
    ],
)
def test_ytdlp_urls(os_name, arch, expected):
    url, kind = tools.download_url(tools.YTDLP, os_name, arch)
    assert url.endswith("/" + expected) and kind == "raw"


def test_ffmpeg_and_deno_urls():
    assert tools.download_url(tools.FFMPEG, "macos", "arm64")[0].endswith("/ffmpeg-darwin-arm64.gz")
    assert tools.download_url(tools.FFPROBE, "windows", "arm64")[0].endswith("/ffprobe-win32-x64.gz")
    url, kind = tools.download_url(tools.DENO, "linux", "x64")
    assert url.endswith("/deno-x86_64-unknown-linux-gnu.zip") and kind == "zip"
    assert tools.download_url(tools.DENO, "macos", "arm64")[0].endswith("/deno-aarch64-apple-darwin.zip")


def test_child_env_strips_pyinstaller_vars(monkeypatch):
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/x")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/custom")
    env = tools.child_env()
    assert "_PYI_APPLICATION_HOME_DIR" not in env
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/custom"
    assert "LD_LIBRARY_PATH_ORIG" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"


class _FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.mark.parametrize("kind", ["raw", "gz", "zip"])
def test_install_tool_extracts_each_archive_kind(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("BAIXADOR_DATA_DIR", str(tmp_path))
    payload = b"#!/bin/sh\necho ok\n"
    name = tools.exe_name("deno")
    if kind == "gz":
        data = gzip.compress(payload)
    elif kind == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"pasta/{name}", payload)
        data = buf.getvalue()
    else:
        data = payload
    monkeypatch.setattr(tools, "download_url", lambda key: ("https://example.invalid/x", kind))
    monkeypatch.setattr(tools, "open_url", lambda url, timeout=0: _FakeResponse(data))

    seen = []
    path = tools.install_tool("deno", progress=lambda done, total: seen.append((done, total)))
    assert path == tmp_path / "bin" / name
    assert path.read_bytes() == payload
    assert seen[-1] == (len(data), len(data))
    assert [p.name for p in tmp_path.iterdir()] == ["bin"]  # nada de lixo temporário


def test_install_tool_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIXADOR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(tools, "download_url", lambda key: ("https://example.invalid/x", "raw"))
    monkeypatch.setattr(tools, "open_url", lambda url, timeout=0: _FakeResponse(b"x" * 10))
    with pytest.raises(tools.InstallCancelled):
        tools.install_tool("deno", cancelled=lambda: True)
    assert not (tmp_path / "bin" / tools.exe_name("deno")).exists()
