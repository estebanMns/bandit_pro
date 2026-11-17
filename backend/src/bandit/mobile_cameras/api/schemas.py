"""Esquemas HTTP de cámaras móviles. Ninguna respuesta incluye hashes ni secretos de medios."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from bandit.mobile_cameras.application.use_cases import DeviceView, MediaGrant
from bandit.mobile_cameras.domain.models import (
    DeviceStatus,
    MobileDevice,
    Platform,
    SessionStatus,
    StreamSession,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionResponse(BaseModel):
    id: UUID
    device_id: UUID
    establishment_id: UUID
    status: SessionStatus
    requested_by: str
    audio_enabled: bool
    video_enabled: bool
    created_at: datetime
    answer_by: datetime
    expires_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None

    @classmethod
    def of(cls, session: StreamSession) -> "SessionResponse":
        return cls(
            id=session.id,
            device_id=session.device_id,
            establishment_id=session.establishment_id,
            status=session.status,
            requested_by=session.requested_by_label,
            audio_enabled=session.audio_enabled,
            video_enabled=session.video_enabled,
            created_at=session.created_at,
            answer_by=session.answer_by,
            expires_at=session.expires_at,
            started_at=session.started_at,
            ended_at=session.ended_at,
            end_reason=session.end_reason.value if session.end_reason else None,
        )


class DeviceResponse(BaseModel):
    id: UUID
    establishment_id: UUID
    name: str
    platform: Platform
    status: DeviceStatus
    online: bool
    is_available: bool
    analysis_enabled: bool
    last_seen: datetime | None
    created_at: datetime
    session: SessionResponse | None

    @classmethod
    def of(cls, view: DeviceView) -> "DeviceResponse":
        device = view.device
        return cls(
            id=device.id,
            establishment_id=device.establishment_id,
            name=device.name,
            platform=device.platform,
            status=view.status,
            online=view.online,
            is_available=device.is_available,
            analysis_enabled=device.analysis_enabled,
            last_seen=device.last_seen,
            created_at=device.created_at,
            session=SessionResponse.of(view.open_session) if view.open_session else None,
        )


class PairingResponse(BaseModel):
    pairing_id: UUID
    expires_at: datetime
    # Texto que el frontend convierte en QR. Contiene el código temporal: no se registra.
    qr_payload: str


class RegisterRequest(_Strict):
    pairing_id: UUID
    code: str = Field(min_length=16, max_length=128)
    device_name: str = Field(min_length=1, max_length=120)
    platform: Platform


class RegisterResponse(BaseModel):
    device_id: UUID
    establishment_id: UUID
    device_token: str


class TokenResponse(BaseModel):
    device_token: str


class AvailabilityRequest(_Strict):
    available: bool


class AnalysisRequest(_Strict):
    enabled: bool


class SessionRequest(_Strict):
    audio: bool = True


class AcceptRequest(_Strict):
    audio: bool
    video: bool = True


class StateRequest(_Strict):
    state: Literal["live", "reconnecting", "failed"]


class MediaGrantResponse(BaseModel):
    url: str
    token: str
    expires_in: int
    ice_servers: list[dict[str, Any]]

    @classmethod
    def of(cls, grant: MediaGrant) -> "MediaGrantResponse":
        return cls(
            url=grant.url,
            token=grant.token,
            expires_in=grant.expires_in,
            ice_servers=grant.ice_servers,
        )


class AcceptResponse(BaseModel):
    session: SessionResponse
    publish: MediaGrantResponse


class DeviceSelfResponse(BaseModel):
    id: UUID
    establishment_id: UUID
    name: str
    platform: Platform
    is_available: bool
    status: DeviceStatus
    session: SessionResponse | None

    @classmethod
    def of(cls, device: MobileDevice, view: DeviceView) -> "DeviceSelfResponse":
        return cls(
            id=device.id,
            establishment_id=device.establishment_id,
            name=device.name,
            platform=device.platform,
            is_available=device.is_available,
            status=view.status,
            session=SessionResponse.of(view.open_session) if view.open_session else None,
        )


class MediaAuthRequest(BaseModel):
    """Cuerpo que envía MediaMTX con `authMethod: http`."""

    model_config = ConfigDict(extra="ignore")

    user: str = ""
    password: str = ""
    token: str = ""
    ip: str = ""
    action: str = ""
    path: str = ""
    protocol: str = ""
    id: str | None = None
    query: str = ""


class ConfigResponse(BaseModel):
    enabled: bool
    media_configured: bool
    answer_window_seconds: int
    max_duration_seconds: int
