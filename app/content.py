from __future__ import annotations

import re
from pathlib import Path


def generate_fallback(source: Path, transcript_status: str) -> dict[str, str]:
    topic = re.sub(r"[_-]+", " ", source.stem).strip() or "Yangi video"
    topic = topic[:80]
    return {
        "title": topic.capitalize(),
        "caption": f"{topic.capitalize()} haqida qisqa video. Fikringizni izohlarda yozing.",
        "hashtags": "#uzbekistan #video",
        "language": "uz",
        "transcript_status": transcript_status,
    }

