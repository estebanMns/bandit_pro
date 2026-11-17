"""Casos de uso: vinculación, disponibilidad, sesiones bajo demanda y autorización de medios."""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from bandit.identity.public import AttemptThrottle
from bandit.mobile_cameras.application.device_hub import DeviceHub
from bandit.mobile_cameras.application.media import MediaSettings
from bandit.mobile_cameras.domain.models import (
    MEDIA_ACTIVE,
    MEDIA_PATH_PREFIX,
    WAITING_FOR_ANSWER,
    DeviceStatus,
    EndReason,
    MobileDevice,
    MobileDeviceChanged,
    MobileSessionChanged,
    Pairing,
    Platform,
    SessionLimits,
    SessionStatus,
    StreamSession,
    clean_device_name,
    device_status,
    media_path_for,
)
from bandit.mobile_cameras.domain.ports import (
    CameraSources,
    DevicePush,
    DeviceRepository,
    MediaTicket,
    PairingRepository,
    SessionRepository,
    TicketKind,
    TicketSigner,
)
from bandit.shared.clock import Clock
from bandit.shared.errors import (
    AuthenticationError,
    ConflictError,
    InvalidDataError,
    NotFoundError,
    RateLimitedError,
    UnavailableError,
)
from bandit.shared.events import EventBus

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "bmc_"  # noqa: S105  Prefijo público, no un secreto.
_LAST_SEEN_GAP = timedelta(seconds=30)


def digest(secret: str) -> str:
    """Huella de un código o token: la base nunca guarda el valor en claro."""
    return hashlib.sha256(secret.encode()).hexdigest()


@dataclass(slots=True)
class Deps:
    devices: DeviceRepository
    pairings: PairingRepository
    sessions: SessionRepository
    hub: DeviceHub
    bus: EventBus
    clock: Clock


@dataclass(frozen=True, slots=True)
class DeviceView:
    device: MobileDevice
    status: DeviceStatus
    online: bool
    open_session: StreamSession | None


@dataclass(frozen=True, slots=True)
class MediaGrant:
    """Lo necesario para publicar (WHIP) o ver (WHEP) una sesión. Caduca pronto."""

    url: str
    token: str
    expires_in: int
    ice_servers: list[dict[str, Any]]


def session_message(session: StreamSession, event_type: str) -> dict[str, Any]:
    return {
        "type": event_type,
        "session_id": str(session.id),
        "device_id": str(session.device_id),
        "status": session.status.value,
        "requested_by": session.requested_by_label,
        "audio_requested": session.audio_enabled,
        "video_requested": session.video_enabled,
        "answer_by": session.answer_by.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "reason": session.end_reason.value if session.end_reason else None,
    }


class _Base:
    def __init__(self, deps: Deps) -> None:
        self._deps = deps

    async def _device(self, device_id: UUID) -> MobileDevice:
        device = await self._deps.devices.get(device_id)
        if device is None:
            raise NotFoundError("El teléfono no existe")
        return device

    async def _session(self, session_id: UUID) -> StreamSession:
        session = await self._deps.sessions.get(session_id)
        if session is None:
            raise NotFoundError("La sesión no existe")
        return session

    async def _changed_device(self, device: MobileDevice) -> None:
        await self._deps.bus.publish(
            MobileDeviceChanged(device_id=device.id, establishment_id=device.establishment_id)
        )

    async def _changed_session(self, session: StreamSession) -> None:
        await self._deps.sessions.save(session)
        await self._deps.bus.publish(MobileSessionChanged(session=session))


class CameraLink:
    """Mete el teléfono en el flujo de cámaras (y de análisis) solo mientras transmite."""

    def __init__(self, devices: DeviceRepository, sources: CameraSources, media: MediaSettings):
        self._devices = devices
        self._sources = sources
        self._media = media

    async def start(self, device: MobileDevice) -> None:
        if not device.analysis_enabled or not self._media.configured:
            return
        try:
            if device.camera_id is None:
                device.camera_id = await self._sources.create(
                    device.establishment_id,
                    f"Móvil · {device.name}"[:200],
                    self._media.internal_rtsp_for(device.media_path),
                )
                await self._devices.save(device)
            await self._sources.set_enabled(device.camera_id, True)
        except Exception:
            # El video en vivo sigue aunque el análisis no arranque.
            logger.exception("No se pudo conectar el teléfono %s al análisis", device.id)

    async def stop(self, device: MobileDevice) -> None:
        if device.camera_id is None:
            return
        try:
            await self._sources.set_enabled(device.camera_id, False)
        except Exception:
            logger.exception("No se pudo pausar la fuente del teléfono %s", device.id)

    async def remove(self, device: MobileDevice) -> None:
        if device.camera_id is None:
            return
        try:
            await self._sources.remove(device.camera_id)
        except Exception:
            logger.exception("No se pudo quitar la fuente del teléfono %s", device.id)
        device.camera_id = None


class SessionCloser(_Base):
    def __init__(self, deps: Deps, link: CameraLink) -> None:
        super().__init__(deps)
        self._link = link

    async def close(
        self,
        session: StreamSession,
        status: SessionStatus,
        reason: EndReason,
        *,
        notify_device: bool = True,
        device: MobileDevice | None = None,
    ) -> StreamSession:
        if not session.is_open:
            return session
        was_streaming = session.status in MEDIA_ACTIVE
        session.close(status, reason, self._deps.clock.now())
        await self._changed_session(session)
        if notify_device:
            self._deps.hub.send(
                session.device_id, session_message(session, "mobile_camera.session_ended")
            )
        if was_streaming:
            owner = device or await self._deps.devices.get(session.device_id)
            if owner is not None:
                await self._link.stop(owner)
        logger.info("Sesión móvil %s cerrada: %s (%s)", session.id, status.value, reason.value)
        return session


# --- Vinculación ---------------------------------------------------------------------------


class CreatePairing(_Base):
    def __init__(self, deps: Deps, ttl: timedelta, throttle: AttemptThrottle) -> None:
        super().__init__(deps)
        self._ttl = ttl
        self._throttle = throttle

    async def execute(self, user_id: UUID, establishment_id: UUID) -> tuple[Pairing, str]:
        now = self._deps.clock.now()
        key = f"pairing:{user_id}"
        if self._throttle.is_blocked(key, now):
            raise RateLimitedError("Generaste demasiados códigos. Espera unos minutos.")
        self._throttle.record(key, now)
        code = secrets.token_urlsafe(24)
        pairing = Pairing(
            id=uuid4(),
            establishment_id=establishment_id,
            user_id=user_id,
            code_hash=digest(code),
            expires_at=now + self._ttl,
            created_at=now,
        )
        await self._deps.pairings.add(pairing)
        logger.info("Código de vinculación creado para el local %s", establishment_id)
        return pairing, code


class CompletePairing(_Base):
    """El QR prueba que lo generó una sesión autenticada del local, hace pocos minutos."""

    def __init__(self, deps: Deps, throttle: AttemptThrottle) -> None:
        super().__init__(deps)
        self._throttle = throttle

    async def execute(
        self, pairing_id: UUID, code: str, name: str, platform: Platform, client: str
    ) -> tuple[MobileDevice, str]:
        now = self._deps.clock.now()
        key = f"register:{client}"
        if self._throttle.is_blocked(key, now):
            raise RateLimitedError("Demasiados intentos de vinculación. Espera unos minutos.")
        pairing = await self._deps.pairings.get(pairing_id)
        if (
            pairing is None
            or not hmac.compare_digest(pairing.code_hash, digest(code))
            or not pairing.is_usable(now)
        ):
            self._throttle.record(key, now)
            raise AuthenticationError("El código QR venció o ya se usó. Genera uno nuevo.")
        if not await self._deps.pairings.mark_used(pairing.id, now):
            raise AuthenticationError("El código QR venció o ya se usó. Genera uno nuevo.")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        device = MobileDevice(
            id=uuid4(),
            establishment_id=pairing.establishment_id,
            user_id=pairing.user_id,
            name=clean_device_name(name),
            platform=platform,
            token_hash=digest(token),
            created_at=now,
            updated_at=now,
            last_seen=now,
        )
        await self._deps.devices.add(device)
        self._throttle.reset(key)
        await self._changed_device(device)
        logger.info("Teléfono %s vinculado al local %s", device.id, device.establishment_id)
        return device, token


class AuthenticateDevice(_Base):
    async def execute(self, token: str) -> MobileDevice:
        if not token.startswith(TOKEN_PREFIX):
            raise AuthenticationError("Credencial del teléfono no válida")
        device = await self._deps.devices.by_token_hash(digest(token))
        if device is None or device.revoked:
            raise AuthenticationError("Credencial del teléfono no válida")
        return device


class RotateDeviceToken(_Base):
    async def execute(self, device: MobileDevice) -> str:
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        device.token_hash = digest(token)
        device.updated_at = self._deps.clock.now()
        await self._deps.devices.save(device)
        return token


class TouchDevice(_Base):
    async def execute(self, device: MobileDevice) -> None:
        now = self._deps.clock.now()
        if device.last_seen is None or now - device.last_seen >= _LAST_SEEN_GAP:
            device.last_seen = now
            await self._deps.devices.save(device)


class AnnouncePresence(_Base):
    """Avisa al dashboard que el teléfono se conectó o se desconectó."""

    async def execute(self, device: MobileDevice) -> None:
        await self._changed_device(device)


# --- Dispositivos --------------------------------------------------------------------------


class DescribeDevices(_Base):
    async def one(self, device: MobileDevice) -> DeviceView:
        open_session = await self._deps.sessions.open_for_device(device.id)
        online = self._deps.hub.is_online(device.id)
        return DeviceView(device, device_status(device, online, open_session), online, open_session)

    async def for_establishment(self, establishment_id: UUID) -> list[DeviceView]:
        devices = await self._deps.devices.list_for(establishment_id)
        return [await self.one(device) for device in devices if not device.revoked]

    async def get(self, device_id: UUID) -> MobileDevice:
        return await self._device(device_id)


class SetAvailability(_Base):
    def __init__(self, deps: Deps, closer: SessionCloser) -> None:
        super().__init__(deps)
        self._closer = closer

    async def execute(self, device: MobileDevice, available: bool) -> MobileDevice:
        device.ensure_active()
        device.is_available = available
        device.updated_at = self._deps.clock.now()
        await self._deps.devices.save(device)
        if not available:
            session = await self._deps.sessions.open_for_device(device.id)
            if session is not None and session.status in WAITING_FOR_ANSWER:
                await self._closer.close(
                    session, SessionStatus.ENDED, EndReason.DEVICE_UNAVAILABLE, device=device
                )
        self._deps.hub.send(
            device.id, {"type": "mobile_camera.availability_changed", "available": available}
        )
        await self._changed_device(device)
        return device


class SetAnalysis(_Base):
    def __init__(self, deps: Deps, link: CameraLink) -> None:
        super().__init__(deps)
        self._link = link

    async def execute(self, device: MobileDevice, enabled: bool) -> MobileDevice:
        device.ensure_active()
        device.analysis_enabled = enabled
        device.updated_at = self._deps.clock.now()
        await self._deps.devices.save(device)
        session = await self._deps.sessions.open_for_device(device.id)
        if session is not None and session.status is SessionStatus.LIVE:
            await (self._link.start(device) if enabled else self._link.stop(device))
        await self._changed_device(device)
        return device


class RevokeDevice(_Base):
    def __init__(self, deps: Deps, closer: SessionCloser, link: CameraLink) -> None:
        super().__init__(deps)
        self._closer = closer
        self._link = link

    async def execute(self, device: MobileDevice) -> None:
        if device.revoked:
            return
        session = await self._deps.sessions.open_for_device(device.id)
        if session is not None:
            await self._closer.close(
                session, SessionStatus.ENDED, EndReason.DEVICE_REVOKED, device=device
            )
        now = self._deps.clock.now()
        device.revoked_at = now
        device.updated_at = now
        device.is_available = False
        await self._link.remove(device)
        await self._deps.devices.save(device)
        self._deps.hub.kick(device.id)
        await self._changed_device(device)
        logger.info("Teléfono %s desvinculado", device.id)


# --- Sesiones ------------------------------------------------------------------------------


class RequestSession(_Base):
    def __init__(self, deps: Deps, limits: SessionLimits, push: DevicePush) -> None:
        super().__init__(deps)
        self._limits = limits
        self._push = push

    async def execute(
        self, device: MobileDevice, requested_by: UUID, requester_label: str, audio: bool
    ) -> StreamSession:
        device.ensure_active()
        if not device.is_available:
            raise ConflictError("El teléfono no está disponible para solicitudes")
        if await self._deps.sessions.open_for_device(device.id) is not None:
            raise ConflictError("El teléfono ya tiene una sesión abierta")
        now = self._deps.clock.now()
        session = StreamSession(
            id=uuid4(),
            device_id=device.id,
            establishment_id=device.establishment_id,
            requested_by=requested_by,
            requested_by_label=requester_label[:200],
            status=SessionStatus.REQUESTED,
            audio_enabled=audio,
            video_enabled=True,
            media_path=media_path_for(device.id),
            created_at=now,
            answer_by=now + self._limits.answer_window,
            expires_at=now + self._limits.max_duration,
        )
        await self._deps.sessions.add(session)
        message = session_message(session, "mobile_camera.session_requested")
        delivered = self._deps.hub.send(device.id, message)
        if not delivered:
            delivered = await self._push.notify(device, message)
        if delivered:
            session.move_to(SessionStatus.AWAITING_DEVICE, now)
        await self._changed_session(session)
        logger.info("Sesión móvil %s solicitada para el teléfono %s", session.id, device.id)
        return session


class DeliverPending(_Base):
    """Al reconectar, el teléfono recibe la solicitud que esperaba o la sesión en curso."""

    async def execute(self, device: MobileDevice) -> None:
        session = await self._deps.sessions.open_for_device(device.id)
        if session is None:
            return
        if session.status in WAITING_FOR_ANSWER:
            self._deps.hub.send(
                device.id, session_message(session, "mobile_camera.session_requested")
            )
            if session.status is SessionStatus.REQUESTED:
                session.move_to(SessionStatus.AWAITING_DEVICE, self._deps.clock.now())
                await self._changed_session(session)
        else:
            self._deps.hub.send(device.id, session_message(session, "mobile_camera.session_active"))


class SessionMedia:
    def __init__(self, signer: TicketSigner, media: MediaSettings, clock: Clock) -> None:
        self._signer = signer
        self._media = media
        self._clock = clock

    def _require_media(self) -> None:
        if not self._media.configured:
            raise UnavailableError("El servidor multimedia no está configurado")

    def publish_grant(self, session: StreamSession) -> MediaGrant:
        self._require_media()
        ttl = self._media.publish_ticket_ttl
        token = self._signer.issue(MediaTicket(TicketKind.PUBLISH, session.id, session.media_path))
        return MediaGrant(
            url=self._media.whip_url(session.media_path),
            token=token,
            expires_in=int(ttl.total_seconds()),
            ice_servers=self._media.ice_servers(session.id, self._clock.now()),
        )

    def view_grant(self, session: StreamSession) -> MediaGrant:
        self._require_media()
        ttl = self._media.view_ticket_ttl
        token = self._signer.issue(MediaTicket(TicketKind.VIEW, session.id, session.media_path))
        return MediaGrant(
            url=self._media.whep_url(session.media_path),
            token=token,
            expires_in=int(ttl.total_seconds()),
            ice_servers=self._media.ice_servers(session.id, self._clock.now()),
        )


def _owned(device: MobileDevice, session: StreamSession) -> None:
    if session.device_id != device.id:
        raise NotFoundError("La sesión no existe")


class AnswerSession(_Base):
    def __init__(
        self, deps: Deps, closer: SessionCloser, media: SessionMedia, expire: "ExpireSessions"
    ) -> None:
        super().__init__(deps)
        self._closer = closer
        self._media = media
        self._expire = expire

    async def accept(
        self, device: MobileDevice, session_id: UUID, audio: bool, video: bool
    ) -> tuple[StreamSession, MediaGrant]:
        device.ensure_active()
        session = await self._expire.check(await self._session(session_id))
        _owned(device, session)
        if not video:
            raise InvalidDataError("La primera versión transmite siempre video")
        if session.status not in WAITING_FOR_ANSWER:
            raise ConflictError("La solicitud ya no está esperando respuesta")
        grant = self._media.publish_grant(session)
        # El teléfono puede negar el audio aunque el dashboard lo haya pedido, nunca al revés.
        session.audio_enabled = session.audio_enabled and audio
        session.move_to(SessionStatus.ACCEPTED, self._deps.clock.now())
        await self._changed_session(session)
        logger.info("Sesión móvil %s aceptada en el teléfono", session.id)
        return session, grant

    async def reject(self, device: MobileDevice, session_id: UUID) -> StreamSession:
        session = await self._expire.check(await self._session(session_id))
        _owned(device, session)
        if session.status not in WAITING_FOR_ANSWER:
            raise ConflictError("La solicitud ya no está esperando respuesta")
        return await self._closer.close(
            session, SessionStatus.REJECTED, EndReason.REJECTED, notify_device=False
        )

    async def renew_publish(self, device: MobileDevice, session_id: UUID) -> MediaGrant:
        """Para reconectar sin volver a pedir permiso, mientras la sesión siga abierta."""
        session = await self._expire.check(await self._session(session_id))
        _owned(device, session)
        if session.status not in MEDIA_ACTIVE:
            raise ConflictError("La sesión no está transmitiendo")
        return self._media.publish_grant(session)


class ReportSession(_Base):
    """El teléfono informa cómo va su conexión WebRTC."""

    def __init__(
        self, deps: Deps, closer: SessionCloser, link: CameraLink, expire: "ExpireSessions"
    ) -> None:
        super().__init__(deps)
        self._closer = closer
        self._link = link
        self._expire = expire

    async def execute(self, device: MobileDevice, session_id: UUID, state: str) -> StreamSession:
        session = await self._expire.check(await self._session(session_id))
        _owned(device, session)
        now = self._deps.clock.now()
        if state == "live":
            # Solo pasa a "live" si MediaMTX ya autorizó la publicación (estado connecting).
            if session.status is SessionStatus.LIVE:
                return session
            if session.status not in (SessionStatus.CONNECTING, SessionStatus.RECONNECTING):
                raise ConflictError("El servidor multimedia aún no recibe el video")
            session.move_to(SessionStatus.LIVE, now)
            await self._changed_session(session)
            await self._link.start(device)
            return session
        if state == "reconnecting":
            if session.status is SessionStatus.LIVE:
                session.move_to(SessionStatus.RECONNECTING, now)
                await self._changed_session(session)
            return session
        if state == "failed":
            return await self._closer.close(
                session, SessionStatus.FAILED, EndReason.MEDIA_FAILED, notify_device=False
            )
        raise InvalidDataError("Estado no reconocido")


class StopSession(_Base):
    def __init__(self, deps: Deps, closer: SessionCloser) -> None:
        super().__init__(deps)
        self._closer = closer

    async def by_user(self, session: StreamSession) -> StreamSession:
        return await self._closer.close(session, SessionStatus.ENDED, EndReason.USER_STOPPED)

    async def by_device(self, device: MobileDevice, session_id: UUID) -> StreamSession:
        session = await self._session(session_id)
        _owned(device, session)
        return await self._closer.close(
            session,
            SessionStatus.ENDED,
            EndReason.DEVICE_STOPPED,
            notify_device=False,
            device=device,
        )


class GetSession(_Base):
    def __init__(self, deps: Deps, expire: "ExpireSessions") -> None:
        super().__init__(deps)
        self._expire = expire

    async def execute(self, session_id: UUID) -> StreamSession:
        return await self._expire.check(await self._session(session_id))

    async def recent(self, establishment_id: UUID, limit: int = 20) -> list[StreamSession]:
        return await self._deps.sessions.recent_for(establishment_id, limit)


class ExpireSessions(_Base):
    def __init__(self, deps: Deps, closer: SessionCloser) -> None:
        super().__init__(deps)
        self._closer = closer

    async def check(self, session: StreamSession) -> StreamSession:
        reason = session.overdue(self._deps.clock.now())
        if reason is None:
            return session
        return await self._closer.close(session, SessionStatus.EXPIRED, reason)

    async def execute(self) -> int:
        expired = 0
        for session in await self._deps.sessions.list_open():
            if session.overdue(self._deps.clock.now()) is not None:
                await self.check(session)
                expired += 1
        return expired


# --- Autorización de MediaMTX --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MediaRequest:
    action: str
    path: str
    protocol: str
    user: str
    password: str
    token: str


class AuthorizeMedia(_Base):
    """MediaMTX pregunta antes de cada publicación o lectura. Solo responde sí o no."""

    def __init__(self, deps: Deps, signer: TicketSigner, media: MediaSettings) -> None:
        super().__init__(deps)
        self._signer = signer
        self._media = media

    async def execute(self, request: MediaRequest) -> bool:
        path = request.path.strip("/")
        if not path.startswith(f"{MEDIA_PATH_PREFIX}/"):
            return False
        if request.action == "read" and self._is_internal_reader(request):
            return True
        if not request.token or request.action not in ("publish", "read"):
            return False
        kind = TicketKind.PUBLISH if request.action == "publish" else TicketKind.VIEW
        ttl = (
            self._media.publish_ticket_ttl
            if kind is TicketKind.PUBLISH
            else self._media.view_ticket_ttl
        )
        ticket = self._signer.verify(request.token, int(ttl.total_seconds()))
        if ticket is None or ticket.kind is not kind or ticket.path != path:
            return False
        session = await self._deps.sessions.get(ticket.session_id)
        if session is None or session.media_path != path or session.status not in MEDIA_ACTIVE:
            return False
        if session.overdue(self._deps.clock.now()) is not None:
            return False
        if kind is TicketKind.PUBLISH and session.status in (
            SessionStatus.ACCEPTED,
            SessionStatus.RECONNECTING,
        ):
            session.move_to(SessionStatus.CONNECTING, self._deps.clock.now())
            await self._changed_session(session)
        return True

    def _is_internal_reader(self, request: MediaRequest) -> bool:
        expected_user = self._media.internal_user
        expected_password = self._media.internal_password
        if not expected_user or not expected_password:
            return False
        return hmac.compare_digest(
            request.user.encode(), expected_user.encode()
        ) and hmac.compare_digest(request.password.encode(), expected_password.encode())
