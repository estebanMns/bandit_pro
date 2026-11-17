"""Tablas de cámaras móviles. Nunca guardan códigos ni tokens en claro, ni audio ni video."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from bandit.shared.db import Base, UtcDateTime


class MobileCameraDeviceRow(Base):
    __tablename__ = "mobile_camera_devices"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    establishment_id: Mapped[UUID] = mapped_column(
        ForeignKey("establishments.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(16))
    device_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fuente en el módulo de cámaras, creada la primera vez que se analiza el teléfono.
    camera_id: Mapped[UUID | None] = mapped_column(nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(UtcDateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime(timezone=True), nullable=True)


class MobileCameraPairingRow(Base):
    __tablename__ = "mobile_camera_pairings"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    establishment_id: Mapped[UUID] = mapped_column(
        ForeignKey("establishments.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pairing_code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True))


class MobileCameraSessionRow(Base):
    __tablename__ = "mobile_camera_sessions"
    __table_args__ = (Index("ix_mobile_camera_sessions_device_status", "device_id", "status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    device_id: Mapped[UUID] = mapped_column(
        ForeignKey("mobile_camera_devices.id", ondelete="CASCADE")
    )
    establishment_id: Mapped[UUID] = mapped_column(
        ForeignKey("establishments.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    requested_by_label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32))
    audio_enabled: Mapped[bool] = mapped_column(Boolean)
    video_enabled: Mapped[bool] = mapped_column(Boolean)
    media_path: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True))
    answer_by: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
