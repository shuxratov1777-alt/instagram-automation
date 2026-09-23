from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from .comments import classify_comment, may_auto_reply
from .config import settings
from .approvals import create_approval, queue_from_instagram
from .database import ApprovalRequest, Job, Video, WebhookEvent, init_db, session_scope
from .pipeline import ingest, process
from .security import verify_admin_key, verify_meta_signature
from .telegram_bot import notify_approval, start_telegram_bot
from .executor import start_approval_executor

app = FastAPI(title="Instagram Automation", version="0.1.0")


def require_admin(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.admin_api_key:
        raise HTTPException(503, "ADMIN_API_KEY is not configured")
    if not verify_admin_key(x_api_key, settings.admin_api_key):
        raise HTTPException(401, "Invalid API key")


@app.on_event("startup")
def startup() -> None:
    init_db()
    start_telegram_bot()
    start_approval_executor()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SocialFlow Automation Privacy Policy</title></head><body style="font-family:system-ui;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.6">
<h1>SocialFlow Automation Privacy Policy</h1><p><strong>Effective date:</strong> September 23, 2026</p>
<p>SocialFlow Automation is a private tool used by the owner of the Instagram professional account @shukhratov.e to review and approve replies and content publishing.</p>
<h2>Data processed</h2><p>The service may process Instagram-scoped user identifiers, message or comment text, event identifiers, approval decisions, captions, and publishing results. It does not request Instagram passwords.</p>
<h2>Purpose and sharing</h2><p>Data is used only to show the account owner an approval request and to perform the exact reply or publishing action the owner confirms. Approval notifications are sent to the owner's private Telegram bot. Data is not sold or used for advertising.</p>
<h2>Storage and security</h2><p>Operational records are stored in the service database with access restricted to the owner and service administrators. Access tokens are stored as protected deployment variables and are not displayed publicly.</p>
<h2>Retention and deletion</h2><p>Records are retained only while needed for operation, troubleshooting, and duplicate prevention. To request deletion, follow the instructions on the <a href="/data-deletion">Data Deletion</a> page.</p>
<h2>Contact</h2><p>Contact the account owner through the Instagram profile <a href="https://www.instagram.com/shukhratov.e/">@shukhratov.e</a>.</p>
</body></html>"""


@app.get("/data-deletion", response_class=HTMLResponse)
def data_deletion() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SocialFlow Automation Data Deletion</title></head><body style="font-family:system-ui;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.6">
<h1>Data Deletion Instructions</h1>
<p>To request deletion of data processed by SocialFlow Automation:</p>
<ol><li>Send a direct message to <a href="https://www.instagram.com/shukhratov.e/">@shukhratov.e</a>.</li><li>Write “Data deletion request” and include the Instagram username whose data should be deleted.</li><li>The account owner will verify the request and remove associated operational records within 30 days.</li></ol>
<p>Deleting records does not remove messages or comments already sent through Instagram; those can be managed directly in Instagram.</p>
</body></html>"""


@app.get("/ready")
def ready() -> dict:
    return {
        "status": "ready",
        "meta": "configured" if settings.meta_ready else "not_configured",
        "auto_publish": settings.auto_publish,
        "auto_reply_comments": settings.auto_reply_comments,
        "human_approval_required": True,
        "telegram_approval": "configured" if settings.telegram_ready else "not_configured",
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
    approvals = queue_from_instagram(payload)
    for approval in approvals:
        notify_approval(approval)
    return {"accepted": True, "duplicate": False, "approvals_queued": len(approvals)}


@app.get("/approvals", dependencies=[Depends(require_admin)])
def list_approvals(status: str = "PENDING_INPUT") -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(ApprovalRequest).where(ApprovalRequest.status == status).order_by(ApprovalRequest.id.desc()).limit(100)
        ).all()
        return [
            {"id": row.id, "action_type": row.action_type, "status": row.status, "created_at": row.created_at}
            for row in rows
        ]


@app.post("/approvals/content", dependencies=[Depends(require_admin)])
async def request_content_approval(request: Request) -> dict:
    body = await request.json()
    content_type = str(body.get("content_type", "")).lower()
    if content_type not in {"post", "reel"}:
        raise HTTPException(422, "content_type must be post or reel")
    media_url = str(body.get("media_url") or body.get("image_url") or body.get("video_url") or "")
    if not media_url.startswith("https://"):
        raise HTTPException(422, "A public HTTPS media_url is required")
    source_ref = str(body.get("source_ref") or f"content:{content_type}:{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}")
    approval = create_approval(f"publish_{content_type}", source_ref, body)
    if approval:
        notify_approval(approval)
    return {"queued": bool(approval), "approval_id": approval.id if approval else None}


@app.post("/comments/classify", dependencies=[Depends(require_admin)])
async def classify(request: Request) -> dict:
    body = await request.json()
    category = classify_comment(str(body.get("text", "")))
    return {"category": category, "eligible_for_auto_reply": settings.auto_reply_comments and may_auto_reply(category)}
