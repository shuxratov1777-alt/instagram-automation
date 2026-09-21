from __future__ import annotations

from datetime import datetime, timezone

from .database import Job, SystemEvent


TRANSITIONS = {
    "UPLOADED": {"VALIDATING", "FAILED"},
    "VALIDATING": {"VALIDATED", "FAILED"},
    "VALIDATED": {"TRANSCRIBING", "FAILED"},
    "TRANSCRIBING": {"TRANSCRIBED", "FAILED"},
    "TRANSCRIBED": {"EDITING", "FAILED"},
    "EDITING": {"GENERATING_CONTENT", "FAILED"},
    "GENERATING_CONTENT": {"READY", "FAILED"},
    "READY": {"PUBLISHING", "FAILED"},
    "PUBLISHING": {"INSTAGRAM_PROCESSING", "FAILED"},
    "INSTAGRAM_PROCESSING": {"PUBLISHED", "FAILED"},
    "PUBLISHED": set(),
    "FAILED": {"VALIDATING", "TRANSCRIBING", "EDITING", "GENERATING_CONTENT", "PUBLISHING"},
}


def transition(session, job: Job, target: str, details: str = "") -> None:
    if target not in TRANSITIONS.get(job.state, set()):
        raise ValueError(f"Invalid transition: {job.state} -> {target}")
    job.state = target
    job.updated_at = datetime.now(timezone.utc)
    session.add(SystemEvent(job_id=job.job_id, event=target, details=details))

