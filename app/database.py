from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(Text)
    rendered_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    probe_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Job(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    content_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(40), index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ContentPackage(Base):
    __tablename__ = "content_packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    caption: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="uz")
    transcript_status: Mapped[str] = mapped_column(String(40), default="not_configured")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    settings.ensure_dirs()
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

