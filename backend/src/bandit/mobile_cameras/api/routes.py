"""Rutas de cámaras móviles: dashboard (cookie), teléfono (token) y MediaMTX (secreto)."""

import asyncio
import contextlib
import hmac
import json
import logging
from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect, status

from bandit.identity.public import CurrentUser, ManagerUser, User, require_csrf
from bandit.mobile_cameras.api.schemas import (
    AcceptRequest,
    AcceptResponse,
    AnalysisRequest,
    AvailabilityRequest,
    ConfigResponse,
    DeviceResponse,
    DeviceSelfResponse,
    MediaAuthRequest,
    MediaGrantResponse,
    PairingResponse,
    RegisterRequest,
    RegisterResponse,
    SessionRequest,
    SessionResponse,
    StateRequest,
    TokenResponse,
)
from bandit.mobile_cameras.application.device_hub import DeviceMessage
from bandit.mobile_cameras.application.use_cases import MediaRequest
from bandit.mobile_cameras.domain.models import MobileDevice, StreamSession
from bandit.mobile_cameras.module import MobileCamerasModule
from bandit.shared.errors import (
    AuthenticationError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["mobile-cameras"])
ws_router = APIRouter()

QR_VERSION = 1
QR_TYPE = "bandit-mobile-camera"
_WS_RECEIVE_TIMEOUT_SECONDS = 75


def _raw_module(request: Request) -> MobileCamerasModule:
    module: MobileCamerasModule = request.app.state.mobile_cameras
    return module


def _module(request: Request) -> MobileCamerasModule:
    module = _raw_module(request)
    if not module.enabled:
        raise NotFoundError("Las cámaras móviles no están activadas en este servidor")
    return module


Module = Annotated[MobileCamerasModule, Depends(_module)]


def _bearer(value: str | None) -> str:
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def current_device(request: Request, module: Module) -> MobileDevice:
    token = _bearer(request.headers.get("authorization"))
    if not token:
        raise AuthenticationError("Falta la credencial del teléfono")
    device = await module.authenticate.execute(token)
    await module.touch.execute(device)
    return device


CurrentDevice = Annotated[MobileDevice, Depends(current_device)]


def _ensure_access(user: User, establishment_id: UUID) -> None:
    if not user.can_access(establishment_id):
        raise PermissionDeniedError("No tienes acceso a este local")


async def _device_for(user: User, device_id: UUID, module: MobileCamerasModule) -> MobileDevice:
    device = await module.describe.get(device_id)
    _ensure_access(user, device.establishment_id)
    if device.revoked:
        raise NotFoundError("El teléfono no existe")
    return device


async def _session_for(user: User, session_id: UUID, module: MobileCamerasModule) -> StreamSession:
    session = await module.get_session.execute(session_id)
    _ensure_access(user, session.establishment_id)
    return session


def _client(request: Request) -> str:
    return request.client.host if request.client else "desconocido"


# --- Dashboard -----------------------------------------------------------------------------


@router.get("/mobile-cameras/config")
async def config(request: Request) -> ConfigResponse:
    module = _raw_module(request)
    return ConfigResponse(
        enabled=module.enabled,
        media_configured=module.media.configured,
        answer_window_seconds=int(module.limits.answer_window.total_seconds()),
        max_duration_seconds=int(module.limits.max_duration.total_seconds()),
    )


@router.post(
    "/establishments/{establishment_id}/mobile-cameras/pairing",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_pairing(
    establishment_id: UUID, request: Request, user: ManagerUser, module: Module
) -> PairingResponse:
    _ensure_access(user, establishment_id)
    pairing, code = await module.create_pairing.execute(user.id, establishment_id)
    api_url = getattr(request.app.state, "public_backend_url", "") or str(request.base_url).rstrip(
        "/"
    )
    payload = {
        "v": QR_VERSION,
        "type": QR_TYPE,
        "api": api_url.rstrip("/"),
        "pairing_id": str(pairing.id),
        "code": code,
        "expires_at": pairing.expires_at.isoformat(),
    }
    return PairingResponse(
        pairing_id=pairing.id,
        expires_at=pairing.expires_at,
        qr_payload=json.dumps(payload, separators=(",", ":")),
    )


@router.get("/establishments/{establishment_id}/mobile-cameras")
async def list_devices(
    establishment_id: UUID, user: CurrentUser, module: Module
) -> list[DeviceResponse]:
    _ensure_access(user, establishment_id)
    views = await module.describe.for_establishment(establishment_id)
    return [DeviceResponse.of(view) for view in views]


@router.get("/establishments/{establishment_id}/mobile-camera-sessions")
async def recent_sessions(
    establishment_id: UUID, user: CurrentUser, module: Module
) -> list[SessionResponse]:
    _ensure_access(user, establishment_id)
    return [SessionResponse.of(s) for s in await module.get_session.recent(establishment_id)]


@router.get("/mobile-cameras/{device_id}")
async def get_device(device_id: UUID, user: CurrentUser, module: Module) -> DeviceResponse:
    device = await _device_for(user, device_id, module)
    return DeviceResponse.of(await module.describe.one(device))


@router.patch("/mobile-cameras/{device_id}/availability", dependencies=[Depends(require_csrf)])
async def set_availability(
    device_id: UUID, body: AvailabilityRequest, user: ManagerUser, module: Module
) -> DeviceResponse:
    device = await _device_for(user, device_id, module)
    await module.set_availability.execute(device, body.available)
    return DeviceResponse.of(await module.describe.one(device))


@router.patch("/mobile-cameras/{device_id}/analysis", dependencies=[Depends(require_csrf)])
async def set_analysis(
    device_id: UUID, body: AnalysisRequest, user: ManagerUser, module: Module
) -> DeviceResponse:
    device = await _device_for(user, device_id, module)
    await module.set_analysis.execute(device, body.enabled)
    return DeviceResponse.of(await module.describe.one(device))


@router.delete(
    "/mobile-cameras/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def revoke_device(device_id: UUID, user: ManagerUser, module: Module) -> None:
    device = await _device_for(user, device_id, module)
    await module.revoke.execute(device)


@router.post(
    "/mobile-cameras/{device_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def request_session(
    device_id: UUID, body: SessionRequest, user: CurrentUser, module: Module
) -> SessionResponse:
    device = await _device_for(user, device_id, module)
    session = await module.request_session.execute(device, user.id, user.email, body.audio)
    return SessionResponse.of(session)


@router.get("/mobile-camera-sessions/{session_id}")
async def get_session(session_id: UUID, user: CurrentUser, module: Module) -> SessionResponse:
    return SessionResponse.of(await _session_for(user, session_id, module))


@router.post("/mobile-camera-sessions/{session_id}/stop", dependencies=[Depends(require_csrf)])
async def stop_session(session_id: UUID, user: CurrentUser, module: Module) -> SessionResponse:
    session = await _session_for(user, session_id, module)
    return SessionResponse.of(await module.stop.by_user(session))


@router.post(
    "/mobile-camera-sessions/{session_id}/stream-ticket", dependencies=[Depends(require_csrf)]
)
async def stream_ticket(session_id: UUID, user: CurrentUser, module: Module) -> MediaGrantResponse:
    session = await _session_for(user, session_id, module)
    if not session.is_open or session.status.value in ("requested", "awaiting_device"):
        raise PermissionDeniedError("La sesión no está transmitiendo")
    return MediaGrantResponse.of(module.session_media.view_grant(session))


# --- Teléfono ------------------------------------------------------------------------------


@router.post("/mobile-cameras/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, module: Module) -> RegisterResponse:
    device, token = await module.complete_pairing.execute(
        body.pairing_id, body.code, body.device_name, body.platform, _client(request)
    )
    return RegisterResponse(
        device_id=device.id, establishment_id=device.establishment_id, device_token=token
    )


@router.get("/mobile-device/me")
async def device_me(device: CurrentDevice, module: Module) -> DeviceSelfResponse:
    return DeviceSelfResponse.of(device, await module.describe.one(device))


@router.patch("/mobile-device/availability")
async def device_availability(
    body: AvailabilityRequest, device: CurrentDevice, module: Module
) -> DeviceSelfResponse:
    await module.set_availability.execute(device, body.available)
    return DeviceSelfResponse.of(device, await module.describe.one(device))


@router.post("/mobile-device/token")
async def rotate_token(device: CurrentDevice, module: Module) -> TokenResponse:
    return TokenResponse(device_token=await module.rotate_token.execute(device))


@router.delete("/mobile-device", status_code=status.HTTP_204_NO_CONTENT)
async def unpair_self(device: CurrentDevice, module: Module) -> None:
    await module.revoke.execute(device)


@router.post("/mobile-camera-sessions/{session_id}/accept")
async def accept_session(
    session_id: UUID, body: AcceptRequest, device: CurrentDevice, module: Module
) -> AcceptResponse:
    session, grant = await module.answer.accept(device, session_id, body.audio, body.video)
    return AcceptResponse(session=SessionResponse.of(session), publish=MediaGrantResponse.of(grant))


@router.post("/mobile-camera-sessions/{session_id}/reject")
async def reject_session(
    session_id: UUID, device: CurrentDevice, module: Module
) -> SessionResponse:
    return SessionResponse.of(await module.answer.reject(device, session_id))


@router.post("/mobile-camera-sessions/{session_id}/publish-ticket")
async def publish_ticket(
    session_id: UUID, device: CurrentDevice, module: Module
) -> MediaGrantResponse:
    return MediaGrantResponse.of(await module.answer.renew_publish(device, session_id))


@router.post("/mobile-camera-sessions/{session_id}/state")
async def report_state(
    session_id: UUID, body: StateRequest, device: CurrentDevice, module: Module
) -> SessionResponse:
    return SessionResponse.of(await module.report.execute(device, session_id, body.state))


@router.post("/mobile-device/sessions/{session_id}/stop")
async def device_stop(session_id: UUID, device: CurrentDevice, module: Module) -> SessionResponse:
    return SessionResponse.of(await module.stop.by_device(device, session_id))


# --- MediaMTX ------------------------------------------------------------------------------


@router.post("/mobile-cameras/media-auth", include_in_schema=False)
async def media_auth(body: MediaAuthRequest, request: Request, module: Module) -> Response:
    """MediaMTX (authMethod: http) pregunta aquí antes de publicar o leer una ruta."""
    secret: str = getattr(request.app.state, "mediamtx_auth_secret", "")
    given = request.query_params.get("key", "")
    if not secret or not hmac.compare_digest(given.encode(), secret.encode()):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    token = body.token or parse_qs(body.query).get("token", [""])[0]
    allowed = await module.authorize_media.execute(
        MediaRequest(
            action=body.action,
            path=body.path,
            protocol=body.protocol,
            user=body.user,
            password=body.password,
            token=token,
        )
    )
    if not allowed:
        logger.info("MediaMTX: %s denegado en %s (%s)", body.action, body.path, body.protocol)
    return Response(status_code=status.HTTP_200_OK if allowed else status.HTTP_401_UNAUTHORIZED)


# --- WebSocket del teléfono ----------------------------------------------------------------


@ws_router.websocket("/ws/mobile-cameras/device")
async def device_socket(websocket: WebSocket) -> None:
    module: MobileCamerasModule = websocket.app.state.mobile_cameras
    try:
        if not module.enabled:
            raise NotFoundError("Las cámaras móviles no están activadas")
        token = _bearer(websocket.headers.get("authorization"))
        device = await module.authenticate.execute(token)
    except DomainError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    subscription = module.hub.connect(device.id)
    await module.touch.execute(device)
    await module.announce.execute(device)
    await websocket.send_json({"type": "hello", "device_id": str(device.id)})
    await module.deliver_pending.execute(device)

    async def forward() -> None:
        async for message in subscription:
            await websocket.send_json(message)
            if message.get("type") == "mobile_camera.device_revoked":
                return

    async def receive() -> None:
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                # Sin latidos en 75 s se da por perdido: la app envía uno cada 25 s.
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_WS_RECEIVE_TIMEOUT_SECONDS
                )
                await _on_device_message(raw, device, module, websocket)

    tasks = {asyncio.create_task(forward()), asyncio.create_task(receive())}
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        module.hub.disconnect(device.id, subscription)
        with contextlib.suppress(Exception):
            await module.announce.execute(device)
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await websocket.close()


async def _on_device_message(
    raw: str, device: MobileDevice, module: MobileCamerasModule, websocket: WebSocket
) -> None:
    try:
        message: DeviceMessage = json.loads(raw)
    except ValueError:
        return
    if not isinstance(message, dict):
        return
    if message.get("type") == "ping":
        await module.touch.execute(device)
        await websocket.send_json({"type": "pong"})
