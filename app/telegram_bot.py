from __future__ import annotations

import json
import logging
import threading
import time
from uuid import uuid4

import httpx

from .approvals import create_approval, decide, set_proposed_text
from .config import settings
from .database import ApprovalRequest
from .executor import execute_approval


logger = logging.getLogger(__name__)
_started = False


def _api(method: str, payload: dict | None = None) -> dict:
    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}",
        json=payload or {},
        timeout=35,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API rejected {method}")
    return data


def _context(request: ApprovalRequest) -> dict:
    try:
        return json.loads(request.context_json)
    except json.JSONDecodeError:
        return {}


def notify_approval(request: ApprovalRequest) -> bool:
    if not settings.telegram_ready:
        return False
    context = _context(request)
    incoming = str(context.get("incoming_text") or "")[:1000]
    labels = {
        "dm_reply": "Yangi Instagram DM",
        "comment_reply": "Yangi Instagram komment",
        "publish_post": "Post nashri uchun so‘rov",
        "publish_reel": "Reels nashri uchun so‘rov",
    }
    command = "caption" if request.action_type.startswith("publish_") else "reply"
    text = (
        f"{labels.get(request.action_type, request.action_type)}\n"
        f"ID: {request.id}\n"
        f"Matn: {incoming or 'Kontent tafsilotlari tayyor'}\n\n"
        f"Taklifingizni yuboring:\n/{command} {request.id} MATN"
    )
    _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": text})
    return True


def _send_confirmation(request: ApprovalRequest) -> None:
    label = "Caption" if request.action_type.startswith("publish_") else "Javob"
    _api(
        "sendMessage",
        {
            "chat_id": settings.telegram_owner_chat_id,
            "text": f"{label} tasdiqlansinmi?\nID: {request.id}\n\n{request.proposed_text}",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "✅ Tasdiqlash", "callback_data": f"approve:{request.id}"},
                    {"text": "❌ Rad etish", "callback_data": f"reject:{request.id}"},
                ]]
            },
        },
    )


def _handle_message(message: dict) -> None:
    if str((message.get("chat") or {}).get("id")) != settings.telegram_owner_chat_id:
        return
    text = str(message.get("text") or "").strip()
    if text == "/start":
        _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": (
            "SocialFlow tasdiqlash boti ulandi. Hech bir javob yoki nashr sizning tasdig‘ingizsiz bajarilmaydi.\n\n"
            "Kontent tayyorlash:\n"
            "/post HTTPS_RASM_URL | YYYY-MM-DD HH:MM\n"
            "/reel HTTPS_VIDEO_URL | YYYY-MM-DD HH:MM\n"
            "Vaqt ixtiyoriy; ko‘rsatilmasa tasdiqdan keyin darhol nashr qilinadi."
        )})
        return
    if text == "/help":
        _handle_message({"chat": {"id": settings.telegram_owner_chat_id}, "text": "/start"})
        return
    if text.startswith("/post ") or text.startswith("/reel "):
        command, raw = text.split(maxsplit=1)
        pieces = [piece.strip() for piece in raw.split("|", 1)]
        media_url = pieces[0]
        scheduled_at = pieces[1] if len(pieces) == 2 else ""
        if not media_url.startswith("https://"):
            _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": "Media uchun ochiq HTTPS URL yuboring."})
            return
        kind = "post" if command == "/post" else "reel"
        context = {
            "media_url": media_url,
            "scheduled_at": scheduled_at,
            "incoming_text": f"{kind.upper()} media: {media_url}" + (f"\nVaqt: {scheduled_at}" if scheduled_at else "\nVaqt: tasdiqdan keyin darhol"),
        }
        request = create_approval(f"publish_{kind}", f"telegram:{kind}:{uuid4()}", context)
        if request:
            notify_approval(request)
        return
    if not (text.startswith("/reply ") or text.startswith("/caption ")):
        return
    parts = text.split(maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit():
        _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": "Format: /reply ID MATN yoki /caption ID MATN"})
        return
    try:
        request = set_proposed_text(int(parts[1]), parts[2])
        _send_confirmation(request)
    except (KeyError, ValueError):
        _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": "Bu ID topilmadi yoki allaqachon yopilgan."})


def _handle_callback(callback: dict) -> None:
    message = callback.get("message") or {}
    if str((message.get("chat") or {}).get("id")) != settings.telegram_owner_chat_id:
        return
    data = str(callback.get("data") or "")
    if ":" not in data:
        return
    action, raw_id = data.split(":", 1)
    if action not in {"approve", "reject"} or not raw_id.isdigit():
        return
    try:
        request = decide(int(raw_id), action == "approve")
        result = "Tasdiqlandi. Bajarish navbatiga qo‘yildi." if action == "approve" else "Rad etildi. Hech narsa yuborilmadi."
        _api("answerCallbackQuery", {"callback_query_id": callback.get("id"), "text": result})
        _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": f"ID {request.id}: {result}"})
        if action == "approve":
            threading.Thread(target=_execute_and_report, args=(request.id,), daemon=True).start()
    except (KeyError, ValueError) as exc:
        _api("answerCallbackQuery", {"callback_query_id": callback.get("id"), "text": str(exc)[:180], "show_alert": True})


def _execute_and_report(request_id: int) -> None:
    try:
        result = execute_approval(request_id)
        if result["status"] == "SCHEDULED":
            text = f"ID {request_id}: rejalashtirildi — {result.get('scheduled_at')}."
        else:
            text = f"ID {request_id}: Instagram amali muvaffaqiyatli bajarildi."
    except Exception as exc:
        logger.exception("Approved Instagram action %s failed", request_id)
        text = f"ID {request_id}: bajarishda xato. Hech narsa takroran yuborilmadi. Xato: {str(exc)[:300]}"
    try:
        _api("sendMessage", {"chat_id": settings.telegram_owner_chat_id, "text": text})
    except Exception:
        logger.exception("Could not report approval result to Telegram")


def _poll() -> None:
    offset = 0
    while True:
        try:
            data = _api("getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]})
            for update in data.get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)
                if "message" in update:
                    _handle_message(update["message"])
                elif "callback_query" in update:
                    _handle_callback(update["callback_query"])
        except Exception:
            logger.exception("Telegram approval polling failed")
            time.sleep(5)


def start_telegram_bot() -> bool:
    global _started
    if _started or not settings.telegram_ready:
        return False
    _started = True
    threading.Thread(target=_poll, name="telegram-approval", daemon=True).start()
    return True
