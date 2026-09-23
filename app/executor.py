from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .config import settings
from .database import ApprovalRequest, session_scope
from .instagram import InstagramClient


logger = logging.getLogger(__name__)
_started = False


def _load_context(raw: str) -> dict:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _scheduled_time(context: dict) -> datetime | None:
    raw = str(context.get("scheduled_at") or "").strip()
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(settings.timezone))
    return parsed.astimezone(timezone.utc)


def is_due(context: dict, now: datetime | None = None) -> bool:
    scheduled = _scheduled_time(context)
    return scheduled is None or scheduled <= (now or datetime.now(timezone.utc))


def _https_url(value: object, label: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be a public HTTPS URL")
    return url


def execute_approval(request_id: int) -> dict:
    with session_scope() as session:
        request = session.get(ApprovalRequest, request_id)
        if not request:
            raise KeyError(request_id)
        if request.status == "EXECUTED":
            return {"status": "EXECUTED", "result": _load_context(request.context_json).get("result_ref")}
        if request.status != "APPROVED":
            raise ValueError(f"Approval {request_id} is not approved")
        context = _load_context(request.context_json)
        if not is_due(context):
            return {"status": "SCHEDULED", "scheduled_at": context.get("scheduled_at")}
        request.status = "EXECUTING"
        request.updated_at = datetime.now(timezone.utc)
        session.flush()
        action_type = request.action_type
        proposed_text = str(request.proposed_text or "")

    client = InstagramClient()
    try:
        if action_type == "dm_reply":
            result_ref = client.send_message(str(context["sender_id"]), proposed_text)
        elif action_type == "comment_reply":
            result_ref = client.reply_to_comment(str(context["comment_id"]), proposed_text)
        elif action_type == "publish_post":
            media_url = _https_url(context.get("image_url") or context.get("media_url"), "image_url")
            creation_id = client.create_image_container(media_url, proposed_text)
            client.wait_until_ready(creation_id)
            result_ref = client.publish(creation_id)
        elif action_type == "publish_reel":
            media_url = _https_url(context.get("video_url") or context.get("media_url"), "video_url")
            creation_id = client.create_reel_container(media_url, proposed_text)
            client.wait_until_ready(creation_id)
            result_ref = client.publish(creation_id)
        else:
            raise ValueError(f"Unsupported action: {action_type}")
    except Exception as exc:
        with session_scope() as session:
            request = session.get(ApprovalRequest, request_id)
            if request:
                failure_context = _load_context(request.context_json)
                failure_context["execution_error"] = str(exc)[:1000]
                request.context_json = json.dumps(failure_context, ensure_ascii=False)
                request.status = "FAILED"
                request.updated_at = datetime.now(timezone.utc)
        raise

    with session_scope() as session:
        request = session.get(ApprovalRequest, request_id)
        if not request:
            raise KeyError(request_id)
        success_context = _load_context(request.context_json)
        success_context["result_ref"] = result_ref
        success_context["executed_at"] = datetime.now(timezone.utc).isoformat()
        request.context_json = json.dumps(success_context, ensure_ascii=False)
        request.status = "EXECUTED"
        request.updated_at = datetime.now(timezone.utc)
    return {"status": "EXECUTED", "result": result_ref}


def _scheduled_loop() -> None:
    while True:
        try:
            with session_scope() as session:
                ids = list(session.scalars(select(ApprovalRequest.id).where(ApprovalRequest.status == "APPROVED")).all())
            for request_id in ids:
                try:
                    execute_approval(request_id)
                except Exception:
                    logger.exception("Approved Instagram action %s failed", request_id)
        except Exception:
            logger.exception("Approval executor loop failed")
        time.sleep(15)


def start_approval_executor() -> bool:
    global _started
    if _started or not settings.meta_ready:
        return False
    _started = True
    threading.Thread(target=_scheduled_loop, name="instagram-approval-executor", daemon=True).start()
    return True
