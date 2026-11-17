"""Teléfonos vinculados, códigos de vinculación y sesiones de transmisión."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from bandit.shared.errors import ConflictError, InvalidDataError
from bandit.shared.events import DomainEvent

MEDIA_PATH_PREFIX = "mobile"
MAX_DEVICE_NAME = 120


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"


class DeviceStatus(StrEnum):
    """Estado visible del teléfono. Se calcula: no se guarda."""

    OFFLINE = "offline"
    REGISTERED = "registered"
    AVAILABLE = "available"
    BUSY = "busy"
    NEEDS_USER_ACTION = "needs_user_action"
    REVOKED = "revoked"


class SessionStatus(StrEnum):
    REQUESTED = "requested"
    AWAITING_DEVICE = "awaiting_device"
    ACCEPTED = "accepted"
    CONNECTING = "connecting"
    LIVE = "live"
    RECONNECTING = "reconnecting"
    REJECTED = "rejected"
    ENDED = "ended"
    FAILED = "failed"
    EXPIRED = "expired"


class EndReason(StrEnum):
    USER_STOPPED = "user_stopped"
    DEVICE_STOPPED = "device_stopped"
    REJECTED = "rejected"
    NOT_ANSWERED = "not_answered"
    MAX_DURATION = "max_duration"
    DEVICE_REVOKED = "device_revoked"
    DEVICE_UNAVAILABLE = "device_unavailable"
    MEDIA_FAILED = "media_failed"


TERMINAL = frozenset(
    {SessionStatus.REJECTED, SessionStatus.ENDED, SessionStatus.FAILED, SessionStatus.EXPIRED}
)
WAITING_FOR_ANSWER = frozenset({SessionStatus.REQUESTED, SessionStatus.AWAITING_DEVICE})
MEDIA_ACTIVE = frozenset(
    {
        SessionStatus.ACCEPTED,
        SessionStatus.CONNECTING,
        SessionStatus.LIVE,
        SessionStatus.RECONNECTING,
    }
)

_CLOSING = frozenset({SessionStatus.ENDED, SessionStatus.FAILED, SessionStatus.EXPIRED})

# Toda transición pasa por aquí: ni el dashboard ni el teléfono pueden saltarse un paso.
TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.REQUESTED: frozenset(
        {SessionStatus.AWAITING_DEVICE, SessionStatus.ACCEPTED, SessionStatus.REJECTED} | _CLOSING
    ),
    SessionStatus.AWAITING_DEVICE: frozenset(
        {SessionStatus.ACCEPTED, SessionStatus.REJECTED} | _CLOSING
    ),
    SessionStatus.ACCEPTED: frozenset({SessionStatus.CONNECTING} | _CLOSING),
    SessionStatus.CONNECTING: frozenset({SessionStatus.LIVE} | _CLOSING),
    SessionStatus.LIVE: frozenset({SessionStatus.RECONNECTING} | _CLOSING),
    SessionStatus.RECONNECTING: frozenset(
        {SessionStatus.CONNECTING, SessionStatus.LIVE} | _CLOSING
    ),
    SessionStatus.REJECTED: frozenset(),
    SessionStatus.ENDED: frozenset(),
    SessionStatus.FAILED: frozenset(),
    SessionStatus.EXPIRED: frozenset(),
}


def clean_device_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidDataError("El teléfono necesita un nombre")
    if len(cleaned) > MAX_DEVICE_NAME:
        raise InvalidDataError(f"El nombre admite hasta {MAX_DEVICE_NAME} caracteres")
    return cleaned


def media_path_for(device_id: UUID) -> str:
    """La ruta la decide el servidor: nunca se acepta una enviada por el cliente."""
    return f"{MEDIA_PATH_PREFIX}/{device_id.hex}"


@dataclass(slots=True)
class MobileDevice:
    id: UUID
    establishment_id: UUID
    user_id: UUID
    name: str
    platform: Platform
    token_hash: str
    created_at: datetime
    updated_at: datetime
    is_available: bool = False
    analysis_enabled: bool = False
    camera_id: UUID | None = None
    last_seen: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def media_path(self) -> str:
        return media_path_for(self.id)

    def ensure_active(self) -> None:
        if self.revoked:
            raise ConflictError("Este teléfono fue desvinculado")


@dataclass(slots=True)
class Pairing:
    id: UUID
    establishment_id: UUID
    user_id: UUID
    code_hash: str
    expires_at: datetime
    created_at: datetime
    used_at: datetime | None = None

    def is_usable(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at


@dataclass(slots=True)
class StreamSession:
    id: UUID
    device_id: UUID
    establishment_id: UUID
    requested_by: UUID
    requested_by_label: str
    status: SessionStatus
    audio_enabled: bool
    video_enabled: bool
    media_path: str
    created_at: datetime
    answer_by: datetime
    expires_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    end_reason: EndReason | None = None

    @property
    def is_open(self) -> bool:
        return self.status not in TERMINAL

    def can_move_to(self, target: SessionStatus) -> bool:
        return target in TRANSITIONS[self.status]

    def move_to(self, target: SessionStatus, now: datetime) -> None:
        if not self.can_move_to(target):
            raise ConflictError(f"La sesión no puede pasar de {self.status.value} a {target.value}")
        self.status = target
        if target is SessionStatus.LIVE and self.started_at is None:
            self.started_at = now

    def close(self, target: SessionStatus, reason: EndReason, now: datetime) -> None:
        if target not in TERMINAL:
            raise InvalidDataError("Solo se cierra con un estado final")
        self.move_to(target, now)
        self.ended_at = now
        self.end_reason = reason

    def overdue(self, now: datetime) -> EndReason | None:
        """Motivo por el que la sesión debe vencer ahora, si lo hay."""
        if not self.is_open:
            return None
        if self.status in WAITING_FOR_ANSWER and now >= self.answer_by:
            return EndReason.NOT_ANSWERED
        if now >= self.expires_at:
            return EndReason.MAX_DURATION
        return None


@dataclass(frozen=True, slots=True)
class SessionLimits:
    answer_window: timedelta
    max_duration: timedelta


def device_status(
    device: MobileDevice, online: bool, open_session: StreamSession | None
) -> DeviceStatus:
    if device.revoked:
        return DeviceStatus.REVOKED
    if open_session is not None:
        if open_session.status in WAITING_FOR_ANSWER:
            return DeviceStatus.NEEDS_USER_ACTION
        return DeviceStatus.BUSY
    if not online:
        return DeviceStatus.OFFLINE
    return DeviceStatus.AVAILABLE if device.is_available else DeviceStatus.REGISTERED


@dataclass(frozen=True, slots=True, kw_only=True)
class MobileDeviceChanged(DomainEvent):
    device_id: UUID
    establishment_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class MobileSessionChanged(DomainEvent):
    session: StreamSession
