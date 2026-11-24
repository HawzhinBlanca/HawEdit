"""Resolve a single YouTube podcast into the local episode source library."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def youtube_video_id(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    video_id = ""
    if parsed.scheme == "https":
        if host == "youtu.be":
            video_id = parsed.path.removeprefix("/")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                ids = parse_qs(parsed.query).get("v", [])
                video_id = ids[0] if len(ids) == 1 else ""
            elif parsed.path.startswith(("/shorts/", "/live/")):
                video_id = parsed.path.split("/", 2)[-1]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
        raise ValueError("Enter an HTTPS YouTube video URL for one episode")
    return video_id


def _archived_movie(info: Path, video_id: str) -> Path | None:
    try:
        metadata = json.loads(info.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(metadata, dict) or metadata.get("id") != video_id:
        return None
    if str(metadata.get("extractor_key") or metadata.get("extractor")).lower() != "youtube":
        return None
    movie = info.with_name(info.name.removesuffix(".info.json") + ".mp4")
    return movie if movie.is_file() and movie.stat().st_size else None


def resolve_youtube_source(url: str, library: Path) -> Path:
    """Reuse a matching local download, or fetch the canonical video into an isolated directory."""
    video_id = youtube_video_id(url)
    library.mkdir(parents=True, exist_ok=True)
    cached = library / video_id
    info_name = video_id + ".info.json"
    for info in [cached / info_name, *sorted(library.glob("*.info.json"))]:
        movie = _archived_movie(info, video_id)
        if movie is not None:
            return movie
    executable = shutil.which("yt-dlp")
    if executable is None:
        uv_tool = Path.home() / ".local" / "bin" / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")
        executable = str(uv_tool) if uv_tool.is_file() else None
    if executable is None:
        raise ValueError("Install yt-dlp for new downloads or select an existing source library")
    with tempfile.TemporaryDirectory(dir=library) as staging:
        bundle = Path(staging) / video_id
        bundle.mkdir()
        cmd = [
            executable,
            "--ignore-config",
            "--no-playlist",
            "--no-progress",
            "--write-info-json",
            "-f",
            "bv[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            "--merge-output-format",
            "mp4",
            "-o",
            "%(id)s.%(ext)s",
            "--",
            "https://www.youtube.com/watch?v=" + video_id,
        ]
        result = subprocess.run(cmd, cwd=bundle, check=False)
        if result.returncode or _archived_movie(bundle / info_name, video_id) is None:
            raise ValueError("YouTube download failed to produce a matching MP4")
        try:
            bundle.rename(cached)
        except OSError:
            if _archived_movie(cached / info_name, video_id) is None:
                raise
    return cached / (video_id + ".mp4")
