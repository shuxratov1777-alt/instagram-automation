from __future__ import annotations

import json
import subprocess
from pathlib import Path


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v"}


class VideoError(RuntimeError):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=900)


def probe(path: Path) -> dict:
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise VideoError("Unsupported file extension")
    result = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if result.returncode != 0:
        raise VideoError("Video cannot be read by ffprobe")
    data = json.loads(result.stdout)
    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise VideoError("No video stream found")
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    if duration <= 0:
        raise VideoError("Invalid video duration")
    stream = video_streams[0]
    return {
        "duration": duration,
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "codec": stream.get("codec_name"),
        "audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
        "size": int(data.get("format", {}).get("size", 0) or 0),
    }


def render_reel(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    result = _run([
        "ffmpeg", "-y", "-i", str(source), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(destination),
    ])
    if result.returncode != 0:
        raise VideoError("FFmpeg rendering failed")

