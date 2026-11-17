from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from bandit.mobile_cameras.application.media import MediaSettings
from bandit.mobile_cameras.application.use_cases import MediaRequest
from bandit.mobile_cameras.domain.models import (
    DeviceStatus,
    EndReason,
    MobileDevice,
    MobileSessionChanged,
    Platform,
    SessionLimits,
    SessionStatus,
)
from bandit.mobile_cameras.infrastructure.fernet_tickets import FernetTicketSigner
from bandit.mobile_cameras.infrastructure.push import DisabledDevicePush
from bandit.mobile_cameras.module import MobileCamerasModule
from bandit.shared.errors import (
    AuthenticationError,
    ConflictError,
    RateLimitedError,
    UnavailableError,
)
from bandit.shared.events import InMemoryEventBus

INTERNAL_PASSWORD = "lectura-interna"


class FakeSources:
    def __init__(self) -> None:
        self.created: list[tuple[UUID, str, str]] = []
        self.enabled: dict[UUID, bool] = {}
        self.removed: list[UUID] = []

    async def create(self, establishment_id: UUID, name: str, url: str) -> UUID:
        camera_id = uuid4()
        self.created.append((establishment_id, name, url))
        self.enabled[camera_id] = False
        return camera_id

    async def set_enabled(self, camera_id: UUID, enabled: bool) -> None:
        self.enabled[camera_id] = enabled

    async def remove(self, camera_id: UUID) -> None:
        self.removed.append(camera_id)


def media(configured: bool = True) -> MediaSettings:
    return MediaSettings(
        public_webrtc_url="https://bandit.example/media" if configured else "",
        internal_rtsp_url="rtsp://mediamtx:8554",
        internal_user="bandit-interno",
        internal_password=INTERNAL_PASSWORD,
    )


@pytest.fixture
def sources() -> FakeSources:
    return FakeSources()


@pytest.fixture
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def module(sessions, clock, sources, bus) -> MobileCamerasModule:
    return MobileCamerasModule(
        sessions,
        sources,
        FernetTicketSigner(),
        DisabledDevicePush(),
        media(),
        bus,
        clock,
        limits=SessionLimits(
            answer_window=timedelta(seconds=90), max_duration=timedelta(minutes=15)
        ),
    )


ESTABLISHMENT = uuid4()
OWNER = uuid4()


async def paired(module: MobileCamerasModule) -> tuple[MobileDevice, str]:
    pairing, code = await module.create_pairing.execute(OWNER, ESTABLISHMENT)
    return await module.complete_pairing.execute(
        pairing.id, code, "Teléfono sala", Platform.ANDROID, "10.0.0.5"
    )


async def available(module: MobileCamerasModule) -> MobileDevice:
    device, _ = await paired(module)
    return await module.set_availability.execute(device, True)


async def live_session(module: MobileCamerasModule, device: MobileDevice):
    session = await module.request_session.execute(device, OWNER, "duena@example.com", True)
    session, grant = await module.answer.accept(device, session.id, True, True)
    assert await module.authorize_media.execute(
        MediaRequest("publish", session.media_path, "webrtc", "", "", grant.token)
    )
    return await module.report.execute(device, session.id, "live")


async def test_pairing_registers_the_device_once(module) -> None:
    pairing, code = await module.create_pairing.execute(OWNER, ESTABLISHMENT)
    device, token = await module.complete_pairing.execute(
        pairing.id, code, "Teléfono sala", Platform.IOS, "10.0.0.5"
    )

    assert device.establishment_id == ESTABLISHMENT
    assert device.token_hash != token
    assert (await module.authenticate.execute(token)).id == device.id
    with pytest.raises(AuthenticationError):
        await module.complete_pairing.execute(pairing.id, code, "Otro", Platform.IOS, "10.0.0.6")


async def test_expired_or_wrong_codes_are_rejected(module, clock) -> None:
    pairing, code = await module.create_pairing.execute(OWNER, ESTABLISHMENT)
    with pytest.raises(AuthenticationError):
        await module.complete_pairing.execute(pairing.id, code + "x", "Tel", Platform.ANDROID, "ip")
    clock.advance(minutes=6)
    with pytest.raises(AuthenticationError):
        await module.complete_pairing.execute(pairing.id, code, "Tel", Platform.ANDROID, "ip")


async def test_repeated_failed_pairings_are_throttled(module) -> None:
    pairing, _ = await module.create_pairing.execute(OWNER, ESTABLISHMENT)
    for _ in range(10):
        with pytest.raises(AuthenticationError):
            await module.complete_pairing.execute(
                pairing.id, "x" * 32, "Tel", Platform.ANDROID, "1.2.3.4"
            )
    with pytest.raises(RateLimitedError):
        await module.complete_pairing.execute(
            pairing.id, "x" * 32, "Tel", Platform.ANDROID, "1.2.3.4"
        )


async def test_rotated_tokens_replace_the_old_one(module) -> None:
    device, old = await paired(module)
    new = await module.rotate_token.execute(device)
    assert (await module.authenticate.execute(new)).id == device.id
    with pytest.raises(AuthenticationError):
        await module.authenticate.execute(old)


async def test_requests_need_an_available_device(module) -> None:
    device, _ = await paired(module)
    with pytest.raises(ConflictError):
        await module.request_session.execute(device, OWNER, "duena", True)


async def test_request_reaches_a_connected_phone(module) -> None:
    device = await available(module)
    subscription = module.hub.connect(device.id)

    session = await module.request_session.execute(device, OWNER, "duena@example.com", True)

    assert session.status is SessionStatus.AWAITING_DEVICE
    message = await anext(aiter(subscription))
    assert message["type"] == "mobile_camera.session_requested"
    assert message["requested_by"] == "duena@example.com"
    view = await module.describe.one(device)
    assert view.status is DeviceStatus.NEEDS_USER_ACTION


async def test_offline_phone_receives_the_request_when_it_connects(module) -> None:
    device = await available(module)
    session = await module.request_session.execute(device, OWNER, "duena", False)
    assert session.status is SessionStatus.REQUESTED

    subscription = module.hub.connect(device.id)
    await module.deliver_pending.execute(device)

    message = await anext(aiter(subscription))
    assert message["session_id"] == str(session.id)
    assert (await module.get_session.execute(session.id)).status is SessionStatus.AWAITING_DEVICE


async def test_only_one_open_session_per_device(module) -> None:
    device = await available(module)
    await module.request_session.execute(device, OWNER, "duena", True)
    with pytest.raises(ConflictError):
        await module.request_session.execute(device, OWNER, "duena", True)


async def test_phone_can_refuse_audio_but_not_add_it(module) -> None:
    device = await available(module)
    no_audio = await module.request_session.execute(device, OWNER, "duena", False)
    session, _ = await module.answer.accept(device, no_audio.id, True, True)
    assert session.audio_enabled is False


async def test_full_session_goes_live_and_feeds_analysis_when_enabled(module, sources) -> None:
    device = await available(module)
    await module.set_analysis.execute(device, True)

    session = await live_session(module, device)

    assert session.status is SessionStatus.LIVE
    assert len(sources.created) == 1
    _, name, url = sources.created[0]
    assert name == "Móvil · Teléfono sala"
    assert url.endswith(f"@mediamtx:8554/{device.media_path}")
    assert list(sources.enabled.values()) == [True]

    stopped = await module.stop.by_user(session)
    assert stopped.status is SessionStatus.ENDED
    assert stopped.end_reason is EndReason.USER_STOPPED
    assert list(sources.enabled.values()) == [False]


async def test_analysis_stays_off_by_default(module, sources) -> None:
    device = await available(module)
    await live_session(module, device)
    assert sources.created == []


async def test_phone_cannot_claim_live_before_media_server_accepts(module) -> None:
    device = await available(module)
    session = await module.request_session.execute(device, OWNER, "duena", True)
    await module.answer.accept(device, session.id, True, True)
    with pytest.raises(ConflictError):
        await module.report.execute(device, session.id, "live")


async def test_media_auth_checks_kind_path_and_state(module) -> None:
    device = await available(module)
    session = await module.request_session.execute(device, OWNER, "duena", True)
    _, grant = await module.answer.accept(device, session.id, True, True)
    path = session.media_path
    authorize = module.authorize_media.execute

    assert not await authorize(MediaRequest("read", path, "webrtc", "", "", grant.token))
    assert not await authorize(
        MediaRequest("publish", "mobile/otro", "webrtc", "", "", grant.token)
    )
    assert not await authorize(MediaRequest("publish", "lente1", "webrtc", "", "", grant.token))
    assert not await authorize(MediaRequest("publish", path, "webrtc", "", "", "basura"))
    assert await authorize(MediaRequest("publish", path, "webrtc", "", "", grant.token))
    assert (await module.get_session.execute(session.id)).status is SessionStatus.CONNECTING

    view = module.session_media.view_grant(await module.get_session.execute(session.id))
    assert await authorize(MediaRequest("read", path, "webrtc", "", "", view.token))

    await module.stop.by_user(await module.get_session.execute(session.id))
    assert not await authorize(MediaRequest("read", path, "webrtc", "", "", view.token))


async def test_internal_reader_uses_its_own_credentials(module) -> None:
    authorize = module.authorize_media.execute
    path = f"mobile/{uuid4().hex}"
    assert await authorize(
        MediaRequest("read", path, "rtsp", "bandit-interno", INTERNAL_PASSWORD, "")
    )
    assert not await authorize(MediaRequest("read", path, "rtsp", "bandit-interno", "otra", ""))
    assert not await authorize(
        MediaRequest("publish", path, "rtsp", "bandit-interno", INTERNAL_PASSWORD, "")
    )


async def test_rejection_closes_the_request(module) -> None:
    device = await available(module)
    session = await module.request_session.execute(device, OWNER, "duena", True)
    rejected = await module.answer.reject(device, session.id)
    assert rejected.status is SessionStatus.REJECTED
    with pytest.raises(ConflictError):
        await module.answer.accept(device, session.id, True, True)


async def test_unanswered_requests_expire(module, clock) -> None:
    device = await available(module)
    subscription = module.hub.connect(device.id)
    session = await module.request_session.execute(device, OWNER, "duena", True)
    clock.advance(seconds=91)

    assert await module.expire.execute() == 1

    expired = await module.get_session.execute(session.id)
    assert expired.status is SessionStatus.EXPIRED
    assert expired.end_reason is EndReason.NOT_ANSWERED
    iterator = aiter(subscription)
    await anext(iterator)
    assert (await anext(iterator))["type"] == "mobile_camera.session_ended"


async def test_live_sessions_expire_at_max_duration(module, clock, sources) -> None:
    device = await available(module)
    await module.set_analysis.execute(device, True)
    session = await live_session(module, device)
    clock.advance(minutes=16)

    await module.expire.execute()

    closed = await module.get_session.execute(session.id)
    assert closed.end_reason is EndReason.MAX_DURATION
    assert list(sources.enabled.values()) == [False]


async def test_turning_availability_off_cancels_waiting_requests(module) -> None:
    device = await available(module)
    session = await module.request_session.execute(device, OWNER, "duena", True)
    await module.set_availability.execute(device, False)
    closed = await module.get_session.execute(session.id)
    assert closed.end_reason is EndReason.DEVICE_UNAVAILABLE


async def test_revocation_ends_everything(module, sources) -> None:
    device = await available(module)
    await module.set_analysis.execute(device, True)
    session = await live_session(module, device)
    subscription = module.hub.connect(device.id)

    await module.revoke.execute(device)

    assert (await module.get_session.execute(session.id)).end_reason is EndReason.DEVICE_REVOKED
    assert len(sources.removed) == 1
    assert not module.hub.is_online(device.id)
    messages = [message["type"] async for message in subscription]
    assert messages[-1] == "mobile_camera.device_revoked"
    assert await module.describe.for_establishment(ESTABLISHMENT) == []


async def test_revoked_tokens_stop_working(module) -> None:
    device, token = await paired(module)
    await module.revoke.execute(device)
    with pytest.raises(AuthenticationError):
        await module.authenticate.execute(token)


async def test_session_changes_are_published(module, bus) -> None:
    seen: list[SessionStatus] = []

    async def record(event: MobileSessionChanged) -> None:
        seen.append(event.session.status)

    bus.subscribe(MobileSessionChanged, record)
    device = await available(module)
    await live_session(module, device)

    # Sin WebSocket abierto la solicitud queda "requested" hasta que el teléfono se conecte.
    assert seen == [
        SessionStatus.REQUESTED,
        SessionStatus.ACCEPTED,
        SessionStatus.CONNECTING,
        SessionStatus.LIVE,
    ]


async def test_media_server_must_be_configured(sessions, clock, sources, bus) -> None:
    module = MobileCamerasModule(
        sessions, sources, FernetTicketSigner(), DisabledDevicePush(), media(False), bus, clock
    )
    device = await available(module)
    session = await module.request_session.execute(device, OWNER, "duena", True)
    with pytest.raises(UnavailableError):
        await module.answer.accept(device, session.id, True, True)
    # El teléfono no estaba conectado y la solicitud sigue esperando.
    assert (await module.get_session.execute(session.id)).status is SessionStatus.REQUESTED
