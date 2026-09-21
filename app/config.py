from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def as_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/automation.db")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", "./data")).resolve()
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    webhook_verify_token: str = os.getenv("WEBHOOK_VERIFY_TOKEN", "")
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    instagram_access_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    instagram_user_id: str = os.getenv("INSTAGRAM_USER_ID", "")
    meta_graph_version: str = os.getenv("META_GRAPH_VERSION", "v23.0")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    auto_process_video: bool = as_bool("AUTO_PROCESS_VIDEO", True)
    auto_generate_subtitles: bool = as_bool("AUTO_GENERATE_SUBTITLES", True)
    auto_generate_caption: bool = as_bool("AUTO_GENERATE_CAPTION", True)
    auto_publish: bool = as_bool("AUTO_PUBLISH", False)
    auto_reply_comments: bool = as_bool("AUTO_REPLY_COMMENTS", False)
    auto_analytics: bool = as_bool("AUTO_ANALYTICS", True)
    auto_content_planning: bool = as_bool("AUTO_CONTENT_PLANNING", True)
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "500"))
    timezone: str = os.getenv("TIMEZONE", "Asia/Tashkent")

    @property
    def meta_ready(self) -> bool:
        return bool(self.instagram_access_token and self.instagram_user_id and self.public_base_url)

    def ensure_dirs(self) -> None:
        for name in ("incoming", "processing", "ready", "published", "failed", "archive"):
            (self.storage_root / name).mkdir(parents=True, exist_ok=True)


settings = Settings()

