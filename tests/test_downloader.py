from baixador import downloader as dl
from baixador.tools import ToolPaths

PATHS = ToolPaths(ytdlp="/bin/yt-dlp", ffmpeg_dir="/opt/ffmpeg", deno="/opt/deno")


def _opts(**kwargs):
    base = dict(url="https://youtu.be/abc", output_dir="/tmp/out")
    base.update(kwargs)
    return dl.DownloadOptions(**base)


def _value_after(args, flag):
    return args[args.index(flag) + 1]


# -- normalize_url -----------------------------------------------------------


def test_normalize_url_accepts_common_inputs():
    assert dl.normalize_url("https://www.youtube.com/watch?v=x") == "https://www.youtube.com/watch?v=x"
    assert dl.normalize_url("  youtu.be/abc123  ") == "https://youtu.be/abc123"
    assert dl.normalize_url("Olha isso: https://youtu.be/abc") == "https://youtu.be/abc"
    assert dl.normalize_url("<https://youtu.be/abc>") == "https://youtu.be/abc"


def test_normalize_url_rejects_garbage():
    assert dl.normalize_url("") is None
    assert dl.normalize_url("   ") is None
    assert dl.normalize_url("não é um link") is None
    assert dl.normalize_url("ftp://example.com/file") is None


# -- build_args --------------------------------------------------------------


def test_video_args():
    args = dl.build_args(_opts(mode=dl.MODE_VIDEO, quality="1080"), PATHS)
    assert args[0] == "/bin/yt-dlp"
    assert args[-2:] == ["--", "https://youtu.be/abc"]
    assert _value_after(args, "-S") == "res:1080,ext:mp4:m4a"
    assert _value_after(args, "--merge-output-format") == "mp4"
    assert _value_after(args, "--ffmpeg-location") == "/opt/ffmpeg"
    assert _value_after(args, "--js-runtimes") == "deno:/opt/deno"
    assert _value_after(args, "-P") == "/tmp/out"
    assert "--no-playlist" in args


def test_video_best_and_compatible():
    best = dl.build_args(_opts(quality="best"), PATHS)
    assert _value_after(best, "-S") == "res,ext:mp4:m4a"
    compat = dl.build_args(_opts(quality="720", compatible=True), PATHS)
    assert _value_after(compat, "-S") == "vcodec:h264,res:720,ext:mp4:m4a"


def test_audio_args():
    mp3 = dl.build_args(_opts(mode=dl.MODE_MP3, quality="320"), PATHS)
    assert _value_after(mp3, "--audio-format") == "mp3"
    assert _value_after(mp3, "--audio-quality") == "320K"
    m4a = dl.build_args(_opts(mode=dl.MODE_M4A, quality="best"), PATHS)
    assert _value_after(m4a, "--audio-format") == "m4a"
    assert "--merge-output-format" not in m4a


def test_playlist_args_and_template():
    args = dl.build_args(_opts(playlist=True), PATHS)
    assert "--yes-playlist" in args and "--ignore-errors" in args
    assert "/" in _value_after(args, "-o")


def test_optional_tools_are_omitted():
    args = dl.build_args(_opts(), ToolPaths(ytdlp="yt-dlp", ffmpeg_dir=None, deno=None))
    assert "--ffmpeg-location" not in args
    assert "--js-runtimes" not in args


# -- OutputParser --------------------------------------------------------------
# Linhas reais capturadas do yt-dlp 2026.10.21 com os templates do app.

MERGE_OUTPUT = """\
WARNING: [generic] Falling back on generic information extractor
BXD:INFO {"id": "manifest", "title": "manifest", "extractor_key": "Generic"}
BXD:FMTS [{"format_id": "0", "vcodec": "avc1.f4001f", "acodec": "none"}, {"format_id": "1", "vcodec": "none", "acodec": "mp4a.40.2"}]
BXD:PROG {"status": "downloading", "downloaded_bytes": 107889, "total_bytes": 215778, "speed": 1000.5, "eta": 3} {"format_id": "0", "vcodec": "avc1.f4001f"}
BXD:PROG {"status": "finished", "downloaded_bytes": 215778, "total_bytes": 215778, "speed": 11651606.4} {"format_id": "0", "vcodec": "avc1.f4001f"}
BXD:PROG {"status": "downloading", "downloaded_bytes": 765, "total_bytes_estimate": 3825.0, "speed": 0, "fragment_index": 0, "fragment_count": 5} {"format_id": "1", "vcodec": "none"}
BXD:PROG {"status": "finished", "downloaded_bytes": 72745, "total_bytes": 72745, "speed": 3212612.3} {"format_id": "1", "vcodec": "none"}
BXD:PP {"postprocessor": "Merger", "status": "started"}
BXD:PP {"postprocessor": "Merger", "status": "finished"}
BXD:PP {"postprocessor": "MoveFiles", "status": "started"}
BXD:FILE "/tmp/out/manifest.mp4"
"""


def _feed_all(text):
    parser = dl.OutputParser()
    events = [e for line in text.splitlines() for e in parser.feed(line)]
    return parser, events


def test_parser_merge_flow():
    parser, events = _feed_all(MERGE_OUTPUT)
    kinds = [e["type"] for e in events]
    assert kinds == ["info", "progress", "progress", "progress", "progress", "postprocess", "postprocess", "file"]

    info = events[0]
    assert info["title"] == "manifest"

    first, video_done, audio_start, audio_done = events[1:5]
    assert first["stage"] == "Baixando vídeo (1/2)"
    assert 0 < first["percent"] < 50
    assert first["speed"] == 1000.5 and first["eta"] == 3
    assert audio_start["stage"] == "Baixando áudio (2/2)"
    assert video_done["percent"] <= audio_start["percent"] <= audio_done["percent"]
    assert audio_done["percent"] == 100

    assert events[5]["stage"] == "Juntando vídeo e áudio…"
    assert events[6]["stage"] == "Finalizando…"
    assert parser.files == ["/tmp/out/manifest.mp4"]
    assert parser.errors == []


def test_parser_single_part_and_youtube_thumbnail():
    parser = dl.OutputParser()
    info = parser.feed('BXD:INFO {"id": "dQw4w9WgXcQ", "title": "Música", "uploader": "Canal", "duration": 212, "extractor_key": "Youtube", "thumbnail": "https://i.ytimg.com/x.webp"}')[0]
    assert info["thumbnail"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"
    assert info["uploader"] == "Canal" and info["duration"] == 212
    parser.feed("BXD:FMTS []")
    prog = parser.feed('BXD:PROG {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200} {"format_id": "18"}')[0]
    assert prog["stage"] == "Baixando" and prog["percent"] == 25


def test_parser_handles_missing_fields():
    parser = dl.OutputParser()
    assert parser.feed("BXD:FMTS NA") == []
    prog = parser.feed('BXD:PROG {"status": "downloading", "downloaded_bytes": 10} {"format_id": "x"}')[0]
    assert prog["percent"] is None
    assert parser.feed("") == []
    assert parser.feed("[download] qualquer coisa") == []


def test_parser_reports_errors():
    parser = dl.OutputParser()
    events = parser.feed("ERROR: [youtube] abc: Private video. Sign in if you've been granted access")
    assert events[0]["type"] == "error"
    assert dl.friendly_error(parser.errors[-1]) == "Este vídeo é privado."


def test_friendly_error_fallback_strips_prefixes():
    assert dl.friendly_error("ERROR: [generic] Something odd happened") == "Something odd happened"
    assert dl.friendly_error("ERROR: Unable to download webpage: HTTP Error 404: Not Found") == "Conteúdo não encontrado (erro 404)."


def test_human_formatting():
    assert dl.human_size(512) == "512 B"
    assert dl.human_size(1536) == "1,5 KB"
    assert dl.human_size(5 * 1024 * 1024) == "5,0 MB"
    assert dl.human_duration(65) == "1:05"
    assert dl.human_duration(3725) == "1:02:05"
    assert dl.human_duration(None) == ""


def test_parser_tracks_partial_files_and_cleanup(tmp_path):
    parser = dl.OutputParser()
    part = tmp_path / "video.f137.mp4.part"
    parser.feed(
        'BXD:PROG {"status": "downloading", "downloaded_bytes": 1, "total_bytes": 9, '
        f'"filename": "{(tmp_path / "video.f137.mp4").as_posix()}", "tmpfilename": "{part.as_posix()}"}} '
        '{"format_id": "137"}'
    )
    assert part.as_posix() in parser.partial_files
    part.write_bytes(b"x")
    (tmp_path / "video.f137.mp4.ytdl").write_bytes(b"x")
    (tmp_path / "video.f137.mp4.part-Frag3").write_bytes(b"x")
    keep = tmp_path / "outro.mp4"
    keep.write_bytes(b"x")
    dl.remove_partial_files(parser.partial_files | {keep.as_posix()}, keep=[keep.as_posix()])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["outro.mp4"]
