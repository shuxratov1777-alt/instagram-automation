from __future__ import annotations

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

    def create_reel_container(self, video_url: str, caption: str) -> str:
        self.require_ready()
        response = httpx.post(
            f"{self.base}/{settings.instagram_user_id}/media",
            data={"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": settings.instagram_access_token},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["id"]

    def publish(self, creation_id: str) -> str:
        self.require_ready()
        response = httpx.post(
            f"{self.base}/{settings.instagram_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": settings.instagram_access_token},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["id"]

