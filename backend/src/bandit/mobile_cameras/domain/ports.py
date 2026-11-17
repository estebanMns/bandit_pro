"""Puertos del módulo de cámaras móviles."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from bandit.mobile_cameras.domain.models import MobileDevice, Pairing, StreamSession


class DeviceRepository(Protocol):
    async def add(self, device: MobileDevice) -> None: ...

    async def save(self, device: MobileDevice) -> None: ...

    async def get(self, device_id: UUID) -> MobileDevice | None: ...

    async def by_token_hash(self, token_hash: str) -> MobileDevice | None: ...

    async def list_for(self, establishment_id: UUID) -> list[MobileDevice]: ...


class PairingRepository(Protocol):
    async def add(self, pairing: Pairing) -> None: ...

    async def get(self, pairing_id: UUID) -> Pairing | None: ...

    async def mark_used(self, pairing_id: UUID, used_at: datetime) -> bool:
        """Marca el código como usado solo si nadie lo usó antes. Devuelve si lo logró."""
        ...


class SessionRepository(Protocol):
    async def add(self, session: StreamSession) -> None: ...

    async def save(self, session: StreamSession) -> None: ...

    async def get(self, session_id: UUID) -> StreamSession | None: ...

    async def open_for_device(self, device_id: UUID) -> StreamSession | None: ...

    async def list_open(self) -> list[StreamSession]: ...

    async def recent_for(self, establishment_id: UUID, limit: int) -> list[StreamSession]: ...


class CameraSources(Protocol):
    """Conecta el teléfono con el flujo de cámaras existente, sin conocer sus clases."""

    async def create(self, establishment_id: UUID, name: str, url: str) -> UUID: ...

    async def set_enabled(self, camera_id: UUID, enabled: bool) -> None: ...

    async def remove(self, camera_id: UUID) -> None: ...


class TicketKind(StrEnum):
    PUBLISH = "publish"
    VIEW = "view"


@dataclass(frozen=True, slots=True)
class MediaTicket:
    kind: TicketKind
    session_id: UUID
    path: str


class TicketSigner(Protocol):
    def issue(self, ticket: MediaTicket) -> str: ...

    def verify(self, token: str, ttl_seconds: int) -> MediaTicket | None: ...


class DevicePush(Protocol):
    """Aviso por FCM o APNs cuando el teléfono no tiene el WebSocket abierto."""

    async def notify(self, device: MobileDevice, payload: dict[str, Any]) -> bool: ...
