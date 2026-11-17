"""Composición del módulo de cámaras móviles."""

from datetime import timedelta

from bandit.identity.public import AttemptThrottle
from bandit.mobile_cameras.application.device_hub import DeviceHub
from bandit.mobile_cameras.application.media import MediaSettings
from bandit.mobile_cameras.application.use_cases import (
    AnnouncePresence,
    AnswerSession,
    AuthenticateDevice,
    AuthorizeMedia,
    CameraLink,
    CompletePairing,
    CreatePairing,
    DeliverPending,
    Deps,
    DescribeDevices,
    ExpireSessions,
    GetSession,
    ReportSession,
    RequestSession,
    RevokeDevice,
    RotateDeviceToken,
    SessionCloser,
    SessionMedia,
    SetAnalysis,
    SetAvailability,
    StopSession,
    TouchDevice,
)
from bandit.mobile_cameras.domain.models import SessionLimits
from bandit.mobile_cameras.domain.ports import CameraSources, DevicePush, TicketSigner
from bandit.mobile_cameras.infrastructure.repositories import (
    SqlDeviceRepository,
    SqlPairingRepository,
    SqlSessionRepository,
)
from bandit.shared.clock import Clock
from bandit.shared.db import SessionFactory
from bandit.shared.events import EventBus


class MobileCamerasModule:
    def __init__(
        self,
        sessions: SessionFactory,
        sources: CameraSources,
        signer: TicketSigner,
        push: DevicePush,
        media: MediaSettings,
        bus: EventBus,
        clock: Clock,
        *,
        enabled: bool = True,
        pairing_ttl: timedelta = timedelta(minutes=5),
        limits: SessionLimits | None = None,
    ) -> None:
        self.enabled = enabled
        self.media = media
        self.hub = DeviceHub()
        devices = SqlDeviceRepository(sessions)
        deps = Deps(
            devices=devices,
            pairings=SqlPairingRepository(sessions),
            sessions=SqlSessionRepository(sessions),
            hub=self.hub,
            bus=bus,
            clock=clock,
        )
        self.limits = limits or SessionLimits(
            answer_window=timedelta(seconds=90), max_duration=timedelta(minutes=15)
        )
        link = CameraLink(devices, sources, media)
        closer = SessionCloser(deps, link)
        session_media = SessionMedia(signer, media, clock)
        self.expire = ExpireSessions(deps, closer)
        self.create_pairing = CreatePairing(
            deps, pairing_ttl, AttemptThrottle(10, timedelta(minutes=5))
        )
        self.complete_pairing = CompletePairing(deps, AttemptThrottle(10, timedelta(minutes=5)))
        self.authenticate = AuthenticateDevice(deps)
        self.rotate_token = RotateDeviceToken(deps)
        self.touch = TouchDevice(deps)
        self.announce = AnnouncePresence(deps)
        self.describe = DescribeDevices(deps)
        self.set_availability = SetAvailability(deps, closer)
        self.set_analysis = SetAnalysis(deps, link)
        self.revoke = RevokeDevice(deps, closer, link)
        self.request_session = RequestSession(deps, self.limits, push)
        self.deliver_pending = DeliverPending(deps)
        self.answer = AnswerSession(deps, closer, session_media, self.expire)
        self.report = ReportSession(deps, closer, link, self.expire)
        self.stop = StopSession(deps, closer)
        self.get_session = GetSession(deps, self.expire)
        self.session_media = session_media
        self.authorize_media = AuthorizeMedia(deps, signer, media)
