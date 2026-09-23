from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from .config import settings
from .database import ApprovalRequest, session_scope


ALLOWED_ACTIONS = {"dm_reply", "comment_reply", "publish_post", "publish_reel"}


def pending_input_ids(limit: int = 2) -> list[int]:
    """Return the newest requests that are still waiting for owner-written text."""
    with session_scope() as session:
        rows = session.scalars(
            select(ApprovalRequest.id)
            .where(ApprovalRequest.status == "PENDING_INPUT")
            .order_by(ApprovalRequest.id.desc())
            .limit(limit)
        ).all()
        return list(rows)


def create_approval(action_type: str, source_ref: str, context: dict[str, Any]) -> ApprovalRequest | None:
    if action_type not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported approval action: {action_type}")
    with session_scope() as session:
        if session.scalar(select(ApprovalRequest).where(ApprovalRequest.source_ref == source_ref)):
            return None
        request = ApprovalRequest(
            action_type=action_type,
            source_ref=source_ref[:255],
            context_json=json.dumps(context, ensure_ascii=False),
        )
        session.add(request)
        session.flush()
        return request


def set_proposed_text(request_id: int, text: str) -> ApprovalRequest:
    clean = text.strip()
    if not clean:
        raise ValueError("Reply/caption cannot be empty")
    with session_scope() as session:
        request = session.get(ApprovalRequest, request_id)
        if not request or request.status in {"APPROVED", "REJECTED", "EXECUTED"}:
            raise KeyError(request_id)
        request.proposed_text = clean
        request.status = "AWAITING_CONFIRMATION"
        request.updated_at = datetime.now(timezone.utc)
        session.flush()
        return request


def decide(request_id: int, approved: bool) -> ApprovalRequest:
    with session_scope() as session:
        request = session.get(ApprovalRequest, request_id)
        if not request:
            raise KeyError(request_id)
        if approved and not request.proposed_text:
            raise ValueError("Write the reply/caption before approval")
        request.status = "APPROVED" if approved else "REJECTED"
        request.updated_at = datetime.now(timezone.utc)
        session.flush()
        return request


def queue_from_instagram(payload: dict[str, Any]) -> list[ApprovalRequest]:
    queued: list[ApprovalRequest] = []
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            message = event.get("message") or {}
            if message.get("is_echo"):
                continue
            text = message.get("text")
            sender_id = str((event.get("sender") or {}).get("id") or "")
            message_id = str(message.get("mid") or event.get("timestamp") or "")
            if text and sender_id and message_id:
                request = create_approval(
                    "dm_reply",
                    f"dm:{message_id}",
                    {"sender_id": sender_id, "incoming_text": str(text)[:2000]},
                )
                if request:
                    queued.append(request)
        for change in entry.get("changes", []):
            if change.get("field") not in {"comments", "live_comments"}:
                continue
            value = change.get("value") or {}
            comment_id = str(value.get("id") or value.get("comment_id") or "")
            text = value.get("text")
            if comment_id and text:
                author_id = str((value.get("from") or {}).get("id") or "")
                if author_id and author_id == settings.instagram_user_id:
                    continue
                request = create_approval(
                    "comment_reply",
                    f"comment:{comment_id}",
                    {
                        "comment_id": comment_id,
                        "author_id": author_id,
                        "username": str((value.get("from") or {}).get("username") or ""),
                        "incoming_text": str(text)[:2000],
                    },
                )
                if request:
                    queued.append(request)
    return queued
