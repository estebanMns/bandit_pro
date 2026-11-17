import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from bandit.mobile_cameras.application.media import MediaSettings, turn_credentials
from bandit.mobile_cameras.domain.models import (
    DeviceStatus,
    EndReason,
    MobileDevice,
    Platform,
    SessionStatus,
    StreamSession,
    clean_device_name,
    device_status,
    media_path_for,
)
from bandit.mobile_cameras.domain.ports import MediaTicket, TicketKind
from bandit.mobile_cameras.infrastructure.fernet_tickets import FernetTicketSigner
from bandit.shared.errors import ConflictError, InvalidDataError

NOW = datetime(2026, 11, 16, 23, 0, tzinfo=UTC)


def make_session(status: SessionStatus = SessionStatus.REQUESTED) -> StreamSession:
    device_id = uuid4()
    return StreamSession(
        id=uuid4(),
        device_id=device_id,
        establishment_id=uuid4(),
        requested_by=uuid4(),
        requested_by_label="duena@example.com",
        status=status,
        audio_enabled=True,
        video_enabled=True,
        media_path=media_path_for(device_id),
        created_at=NOW,
        answer_by=NOW + timedelta(seconds=90),
        expires_at=NOW + timedelta(minutes=15),
    )


def make_device(**changes: object) -> MobileDevice:
    device = MobileDevice(
        id=uuid4(),
        establishment_id=uuid4(),
        user_id=uuid4(),
        name="Teléfono sala",
        platform=Platform.ANDROID,
        token_hash="x" * 64,
        created_at=NOW,
        updated_at=NOW,
    )
    for key, value in changes.items():
        setattr(device, key, value)
    return device


def test_happy_path_transitions() -> None:
    session = make_session()
    for target in (
        SessionStatus.AWAITING_DEVICE,
        SessionStatus.ACCEPTED,
        SessionStatus.CONNECTING,
        SessionStatus.LIVE,
    ):
        session.move_to(target, NOW)
    assert session.started_at == NOW
    session.close(SessionStatus.ENDED, EndReason.USER_STOPPED, NOW)
    assert not session.is_open
    assert session.end_reason is EndReason.USER_STOPPED


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (SessionStatus.REQUESTED, SessionStatus.LIVE),
        (SessionStatus.AWAITING_DEVICE, SessionStatus.CONNECTING),
        (SessionStatus.ACCEPTED, SessionStatus.LIVE),
        (SessionStatus.ENDED, SessionStatus.LIVE),
        (SessionStatus.REJECTED, SessionStatus.ACCEPTED),
    ],
)
def test_cannot_skip_steps(start: SessionStatus, target: SessionStatus) -> None:
    with pytest.raises(ConflictError):
        make_session(start).move_to(target, NOW)


def test_close_requires_a_final_state() -> None:
    with pytest.raises(InvalidDataError):
        make_session().close(SessionStatus.LIVE, EndReason.USER_STOPPED, NOW)


def test_unanswered_requests_expire_before_the_session_limit() -> None:
    session = make_session(SessionStatus.AWAITING_DEVICE)
    assert session.overdue(NOW + timedelta(seconds=89)) is None
    assert session.overdue(NOW + timedelta(seconds=90)) is EndReason.NOT_ANSWERED


def test_live_sessions_expire_at_their_maximum_duration() -> None:
    session = make_session(SessionStatus.LIVE)
    assert session.overdue(NOW + timedelta(minutes=5)) is None
    assert session.overdue(NOW + timedelta(minutes=15)) is EndReason.MAX_DURATION


def test_device_status_is_derived() -> None:
    device = make_device()
    assert device_status(device, False, None) is DeviceStatus.OFFLINE
    assert device_status(device, True, None) is DeviceStatus.REGISTERED
    device.is_available = True
    assert device_status(device, True, None) is DeviceStatus.AVAILABLE
    waiting = make_session(SessionStatus.AWAITING_DEVICE)
    assert device_status(device, False, waiting) is DeviceStatus.NEEDS_USER_ACTION
    assert device_status(device, True, make_session(SessionStatus.LIVE)) is DeviceStatus.BUSY
    device.revoked_at = NOW
    assert device_status(device, True, None) is DeviceStatus.REVOKED


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_device_names_are_validated(name: str) -> None:
    with pytest.raises(InvalidDataError):
        clean_device_name(name)


def test_device_names_are_normalized() -> None:
    assert clean_device_name("  Teléfono   sala ") == "Teléfono sala"


def test_media_path_comes_from_the_device_id() -> None:
    device_id = uuid4()
    assert media_path_for(device_id) == f"mobile/{device_id.hex}"


def test_turn_credentials_follow_the_coturn_rest_scheme() -> None:
    session_id = uuid4()
    expires = NOW + timedelta(hours=1)
    username, credential = turn_credentials("secreto", session_id, expires)
    assert username == f"{int(expires.timestamp())}:{session_id.hex}"
    expected = hmac.new(b"secreto", username.encode(), hashlib.sha1).digest()
    assert credential == base64.b64encode(expected).decode()


def test_media_settings_build_urls_without_leaking_secrets_to_clients() -> None:
    media = MediaSettings(
        public_webrtc_url="https://bandit.example/media/",
        internal_rtsp_url="rtsp://mediamtx:8554",
        internal_user="bandit-interno",
        internal_password="cl@ve",
        stun_urls=("stun:stun.example:3478",),
        turn_urls=("turn:turn.example:3478",),
        turn_shared_secret="s",
    )
    assert media.whip_url("mobile/a") == "https://bandit.example/media/mobile/a/whip"
    assert media.whep_url("mobile/a") == "https://bandit.example/media/mobile/a/whep"
    assert media.internal_rtsp_for("mobile/a") == (
        "rtsp://bandit-interno:cl%40ve@mediamtx:8554/mobile/a"
    )
    servers = media.ice_servers(uuid4(), NOW)
    assert servers[0] == {"urls": ["stun:stun.example:3478"]}
    assert servers[1]["urls"] == ["turn:turn.example:3478"]
    assert "s" not in servers[1]["credential"].split()


def test_tickets_round_trip_and_reject_tampering() -> None:
    signer = FernetTicketSigner()
    ticket = MediaTicket(TicketKind.PUBLISH, uuid4(), "mobile/abc")
    token = signer.issue(ticket)
    assert signer.verify(token, 60) == ticket
    assert signer.verify(token[:-2] + "xx", 60) is None
    assert FernetTicketSigner().verify(token, 60) is None
