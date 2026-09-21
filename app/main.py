from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select

from .comments import classify_comment, may_auto_reply
from .config import settings
from .database import Job, Video, WebhookEvent, init_db, session_scope
from .pipeline import ingest, process
from .security import verify_admin_key, verify_meta_signature

app = FastAPI(title="Instagram Automation", version="0.1.0")


def require_admin(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.admin_api_key:
        raise HTTPException(503, "ADMIN_API_KEY is not configured")
    if not verify_admin_key(x_api_key, settings.admin_api_key):
        raise HTTPException(401, "Invalid API key")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return {
        "status": "ready",
        "meta": "configured" if settings.meta_ready else "not_configured",
        "auto_publish": settings.auto_publish,
        "auto_reply_comments": settings.auto_reply_comments,
    }


@app.get("/status", dependencies=[Depends(require_admin)])
def status() -> dict:
    with session_scope() as session:
        counts = dict(session.execute(select(Job.state, func.count()).group_by(Job.state)).all())
    return {"jobs": counts, "meta": settings.meta_ready, "dry_run_default": not settings.auto_publish}


@app.post("/videos", dependencies=[Depends(require_admin)])
async def upload_video(file: UploadFile, dry_run: bool = True) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v"}:
        raise HTTPException(415, "Unsupported video type")
    temporary = settings.storage_root / "processing" / f"upload-{hashlib.sha256((file.filename or '').encode()).hexdigest()[:12]}{suffix}"
    size = 0
    with temporary.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                temporary.unlink(missing_ok=True)
                raise HTTPException(413, "File too large")
            handle.write(chunk)
    try:
        job_id, created = ingest(temporary, dry_run=dry_run)
    finally:
        temporary.unlink(missing_ok=True)
    if created and settings.auto_process_video:
        process(job_id)
    return {"job_id": job_id, "created": created}


@app.post("/jobs/{job_id}/process", dependencies=[Depends(require_admin)])
def process_job(job_id: str) -> dict:
    try:
        return {"job_id": job_id, "state": process(job_id)}
    except KeyError:
        raise HTTPException(404, "Job not found")


@app.get("/webhooks/instagram")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and settings.webhook_verify_token and hub_verify_token == settings.webhook_verify_token:
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
    raise HTTPException(403, "Webhook verification failed")


@app.post("/webhooks/instagram")
async def instagram_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)) -> dict:
    body = await request.body()
    if not verify_meta_signature(body, x_hub_signature_256, settings.meta_app_secret):
        raise HTTPException(401, "Invalid signature")
    payload = json.loads(body)
    event_key = hashlib.sha256(body).hexdigest()
    with session_scope() as session:
        if session.scalar(select(WebhookEvent).where(WebhookEvent.event_key == event_key)):
            return {"accepted": True, "duplicate": True}
        session.add(WebhookEvent(event_key=event_key, payload_json=json.dumps(payload)))
    return {"accepted": True, "duplicate": False}


@app.post("/comments/classify", dependencies=[Depends(require_admin)])
async def classify(request: Request) -> dict:
    body = await request.json()
    category = classify_comment(str(body.get("text", "")))
    return {"category": category, "eligible_for_auto_reply": settings.auto_reply_comments and may_auto_reply(category)}
