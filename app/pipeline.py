from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .content import generate_fallback
from .database import ContentPackage, Job, Video, session_scope
from .state import transition
from .video import VideoError, probe, render_reel


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ingest(source: Path, dry_run: bool = True) -> tuple[str, bool]:
    source = source.resolve()
    digest = file_hash(source)
    with session_scope() as session:
        existing = session.scalar(select(Video).where(Video.sha256 == digest))
        if existing:
            job = session.scalar(select(Job).where(Job.content_id == existing.content_id).order_by(Job.id.desc()))
            return job.job_id, False
        content_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        safe_name = f"{content_id}{source.suffix.lower()}"
        stored = settings.storage_root / "incoming" / safe_name
        shutil.copy2(source, stored)
        session.add(Video(content_id=content_id, sha256=digest, original_name=source.name[:255], source_path=str(stored)))
        session.add(Job(job_id=job_id, content_id=content_id, state="UPLOADED", dry_run=dry_run))
        return job_id, True


def process(job_id: str) -> str:
    with session_scope() as session:
        job = session.scalar(select(Job).where(Job.job_id == job_id))
        if not job:
            raise KeyError(job_id)
        video = session.scalar(select(Video).where(Video.content_id == job.content_id))
        source = Path(video.source_path)
        try:
            transition(session, job, "VALIDATING")
            metadata = probe(source)
            if metadata["size"] > settings.max_upload_mb * 1024 * 1024:
                raise VideoError("Video exceeds configured size limit")
            video.probe_json = json.dumps(metadata)
            transition(session, job, "VALIDATED")

            transition(session, job, "TRANSCRIBING")
            transcript_status = "provider_not_configured" if not settings.openai_api_key else "adapter_pending_live_credentials"
            transition(session, job, "TRANSCRIBED", transcript_status)

            transition(session, job, "EDITING")
            destination = settings.storage_root / "ready" / f"{video.content_id}.mp4"
            render_reel(source, destination)
            video.rendered_path = str(destination)

            transition(session, job, "GENERATING_CONTENT")
            package = generate_fallback(source, transcript_status)
            session.add(ContentPackage(content_id=video.content_id, **package))
            transition(session, job, "READY", "dry_run_ready" if job.dry_run else "ready")
            return job.state
        except Exception as exc:
            job.error = str(exc)[:1000]
            if job.state != "FAILED" and "FAILED" in __import__("app.state", fromlist=["TRANSITIONS"]).TRANSITIONS.get(job.state, set()):
                transition(session, job, "FAILED", job.error)
            raise

