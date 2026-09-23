from __future__ import annotations

import time

import httpx

from .config import settings


class InstagramNotConfigured(RuntimeError):
    pass


class InstagramClient:
    def __init__(self) -> None:
        self.base = f"https://graph.instagram.com/{settings.meta_graph_version}"

    def require_ready(self) -> None:
        if not settings.meta_ready:
            raise InstagramNotConfigured("Meta publishing is not configured")

    def _post(self, path: str, *, data: dict | None = None, json: dict | None = None) -> dict:
        self.require_ready()
        response = httpx.post(
            f"{self.base}/{path.lstrip('/')}",
            data=data,
            json=json,
            params={"access_token": settings.instagram_access_token},
            timeout=35,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(str(payload["error"]))
        return payload

    def send_message(self, recipient_id: str, text: str) -> str:
        payload = self._post(
            f"{settings.instagram_user_id}/messages",
            json={"recipient": {"id": recipient_id}, "message": {"text": text}},
        )
        return str(payload.get("message_id") or payload.get("id") or "sent")

    def reply_to_comment(self, comment_id: str, text: str) -> str:
        payload = self._post(f"{comment_id}/replies", data={"message": text})
        return str(payload.get("id") or "sent")

    def create_image_container(self, image_url: str, caption: str) -> str:
        payload = self._post(
            f"{settings.instagram_user_id}/media",
            data={"image_url": image_url, "caption": caption},
        )
        return str(payload["id"])

    def create_reel_container(self, video_url: str, caption: str) -> str:
        payload = self._post(
            f"{settings.instagram_user_id}/media",
            data={"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"},
        )
        return str(payload["id"])

    def wait_until_ready(self, creation_id: str, attempts: int = 24, delay: float = 5) -> None:
        for _ in range(attempts):
            response = httpx.get(
                f"{self.base}/{creation_id}",
                params={"fields": "status_code", "access_token": settings.instagram_access_token},
                timeout=30,
            )
            response.raise_for_status()
            status = str(response.json().get("status_code") or "").upper()
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram media container status: {status}")
            time.sleep(delay)
        raise TimeoutError("Instagram media container did not become ready in time")

    def publish(self, creation_id: str) -> str:
        payload = self._post(
            f"{settings.instagram_user_id}/media_publish",
            data={"creation_id": creation_id},
        )
        return str(payload["id"])
