"""Repositorios SQL de cámaras móviles."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update

from bandit.mobile_cameras.domain.models import (
    TERMINAL,
    EndReason,
    MobileDevice,
    Pairing,
    Platform,
    SessionStatus,
    StreamSession,
)
from bandit.mobile_cameras.infrastructure.tables import (
    MobileCameraDeviceRow,
    MobileCameraPairingRow,
    MobileCameraSessionRow,
)
from bandit.shared.db import SessionFactory

_TERMINAL_VALUES = [status.value for status in TERMINAL]


def _device(row: MobileCameraDeviceRow) -> MobileDevice:
    return MobileDevice(
        id=row.id,
        establishment_id=row.establishment_id,
        user_id=row.user_id,
        name=row.device_name,
        platform=Platform(row.platform),
        token_hash=row.device_token_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_available=row.is_available,
        analysis_enabled=row.analysis_enabled,
        camera_id=row.camera_id,
        last_seen=row.last_seen,
        revoked_at=row.revoked_at,
    )


def _copy_device(device: MobileDevice, row: MobileCameraDeviceRow) -> None:
    row.device_name = device.name
    row.device_token_hash = device.token_hash
    row.is_available = device.is_available
    row.analysis_enabled = device.analysis_enabled
    row.camera_id = device.camera_id
    row.last_seen = device.last_seen
    row.updated_at = device.updated_at
    row.revoked_at = device.revoked_at


class SqlDeviceRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def add(self, device: MobileDevice) -> None:
        async with self._sessions.begin() as session:
            row = MobileCameraDeviceRow(
                id=device.id,
                establishment_id=device.establishment_id,
                user_id=device.user_id,
                platform=device.platform.value,
                created_at=device.created_at,
            )
            _copy_device(device, row)
            session.add(row)

    async def save(self, device: MobileDevice) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(MobileCameraDeviceRow, device.id)
            if row is not None:
                _copy_device(device, row)

    async def get(self, device_id: UUID) -> MobileDevice | None:
        async with self._sessions() as session:
            row = await session.get(MobileCameraDeviceRow, device_id)
            return _device(row) if row else None

    async def by_token_hash(self, token_hash: str) -> MobileDevice | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(MobileCameraDeviceRow).where(
                    MobileCameraDeviceRow.device_token_hash == token_hash
                )
            )
            return _device(row) if row else None

    async def list_for(self, establishment_id: UUID) -> list[MobileDevice]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(MobileCameraDeviceRow)
                .where(MobileCameraDeviceRow.establishment_id == establishment_id)
                .order_by(MobileCameraDeviceRow.created_at)
            )
            return [_device(row) for row in rows]


def _pairing(row: MobileCameraPairingRow) -> Pairing:
    return Pairing(
        id=row.id,
        establishment_id=row.establishment_id,
        user_id=row.user_id,
        code_hash=row.pairing_code_hash,
        expires_at=row.expires_at,
        created_at=row.created_at,
        used_at=row.used_at,
    )


class SqlPairingRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def add(self, pairing: Pairing) -> None:
        async with self._sessions.begin() as session:
            session.add(
                MobileCameraPairingRow(
                    id=pairing.id,
                    establishment_id=pairing.establishment_id,
                    user_id=pairing.user_id,
                    pairing_code_hash=pairing.code_hash,
                    expires_at=pairing.expires_at,
                    used_at=pairing.used_at,
                    created_at=pairing.created_at,
                )
            )

    async def get(self, pairing_id: UUID) -> Pairing | None:
        async with self._sessions() as session:
            row = await session.get(MobileCameraPairingRow, pairing_id)
            return _pairing(row) if row else None

    async def mark_used(self, pairing_id: UUID, used_at: datetime) -> bool:
        # Un solo UPDATE condicional: dos teléfonos con el mismo QR no pueden ganar los dos.
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(MobileCameraPairingRow)
                .where(
                    MobileCameraPairingRow.id == pairing_id,
                    MobileCameraPairingRow.used_at.is_(None),
                )
                .values(used_at=used_at)
            )
            return bool(getattr(result, "rowcount", 0))


def _session(row: MobileCameraSessionRow) -> StreamSession:
    return StreamSession(
        id=row.id,
        device_id=row.device_id,
        establishment_id=row.establishment_id,
        requested_by=row.requested_by,
        requested_by_label=row.requested_by_label,
        status=SessionStatus(row.status),
        audio_enabled=row.audio_enabled,
        video_enabled=row.video_enabled,
        media_path=row.media_path,
        created_at=row.created_at,
        answer_by=row.answer_by,
        expires_at=row.expires_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        end_reason=EndReason(row.end_reason) if row.end_reason else None,
    )


def _copy_session(stream: StreamSession, row: MobileCameraSessionRow) -> None:
    row.status = stream.status.value
    row.audio_enabled = stream.audio_enabled
    row.video_enabled = stream.video_enabled
    row.started_at = stream.started_at
    row.ended_at = stream.ended_at
    row.end_reason = stream.end_reason.value if stream.end_reason else None


class SqlSessionRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def add(self, stream: StreamSession) -> None:
        async with self._sessions.begin() as session:
            row = MobileCameraSessionRow(
                id=stream.id,
                device_id=stream.device_id,
                establishment_id=stream.establishment_id,
                requested_by=stream.requested_by,
                requested_by_label=stream.requested_by_label,
                media_path=stream.media_path,
                created_at=stream.created_at,
                answer_by=stream.answer_by,
                expires_at=stream.expires_at,
            )
            _copy_session(stream, row)
            session.add(row)

    async def save(self, stream: StreamSession) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(MobileCameraSessionRow, stream.id)
            if row is not None:
                _copy_session(stream, row)

    async def get(self, session_id: UUID) -> StreamSession | None:
        async with self._sessions() as session:
            row = await session.get(MobileCameraSessionRow, session_id)
            return _session(row) if row else None

    async def open_for_device(self, device_id: UUID) -> StreamSession | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(MobileCameraSessionRow)
                .where(
                    MobileCameraSessionRow.device_id == device_id,
                    MobileCameraSessionRow.status.not_in(_TERMINAL_VALUES),
                )
                .order_by(MobileCameraSessionRow.created_at.desc())
                .limit(1)
            )
            return _session(row) if row else None

    async def list_open(self) -> list[StreamSession]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(MobileCameraSessionRow).where(
                    MobileCameraSessionRow.status.not_in(_TERMINAL_VALUES)
                )
            )
            return [_session(row) for row in rows]

    async def recent_for(self, establishment_id: UUID, limit: int) -> list[StreamSession]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(MobileCameraSessionRow)
                .where(MobileCameraSessionRow.establishment_id == establishment_id)
                .order_by(MobileCameraSessionRow.created_at.desc())
                .limit(limit)
            )
            return [_session(row) for row in rows]
