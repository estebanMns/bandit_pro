"""Flujo HTTP y WebSocket completo: vinculación, solicitud, MediaMTX y cierre."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from bandit.main import create_app
from bandit.shared.config import Settings
from tests.test_api import PASSWORD, _create_schema, create_local, login, register

AUTH_SECRET = "secreto-de-mediamtx"
INTERNAL_PASSWORD = "lectura-interna"


def _settings(tmp_path: Path, url: str, **changes: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "database_url": url,
        "camera_encryption_key": Fernet.generate_key().decode(),
        "bootstrap_admin_email": "admin@example.com",
        "bootstrap_admin_password": PASSWORD,
        "ffmpeg_path": "ffmpeg-inexistente",
        "media_root": str(tmp_path),
        "directory_scrape_enabled": False,
        "camera_capture_enabled": False,
        "mobile_camera_enabled": True,
        "mediamtx_public_webrtc_url": "https://bandit.example/media",
        "mediamtx_internal_password": INTERNAL_PASSWORD,
        "mediamtx_auth_secret": AUTH_SECRET,
        "webrtc_stun_urls": "stun:stun.example:3478",
    }
    values.update(changes)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'movil.db'}"
    app = create_app(_settings(tmp_path, url))
    asyncio.run(_create_schema(url))
    with TestClient(app) as test_client:
        yield test_client


def pair_phone(client: TestClient, headers: dict[str, str], local: str) -> dict[str, str]:
    created = client.post(f"/api/establishments/{local}/mobile-cameras/pairing", headers=headers)
    assert created.status_code == 201, created.text
    qr = json.loads(created.json()["qr_payload"])
    assert qr["type"] == "bandit-mobile-camera"
    registered = client.post(
        "/api/mobile-cameras/register",
        json={
            "pairing_id": qr["pairing_id"],
            "code": qr["code"],
            "device_name": "Teléfono sala",
            "platform": "android",
        },
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    return {"id": body["device_id"], "token": body["device_token"]}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def media_auth(client: TestClient, key: str = AUTH_SECRET, **body: str) -> int:
    return client.post(f"/api/mobile-cameras/media-auth?key={key}", json=body).status_code


def test_complete_on_demand_session(client: TestClient) -> None:
    headers = login(client)
    local = create_local(client, headers)
    phone = pair_phone(client, headers, local)

    listed = client.get(f"/api/establishments/{local}/mobile-cameras").json()
    assert [device["status"] for device in listed] == ["offline"]
    assert "token" not in json.dumps(listed)

    switched = client.patch(
        "/api/mobile-device/availability", json={"available": True}, headers=bearer(phone["token"])
    )
    assert switched.json()["is_available"] is True
    analysis = client.patch(
        f"/api/mobile-cameras/{phone['id']}/analysis", json={"enabled": True}, headers=headers
    )
    assert analysis.json()["analysis_enabled"] is True

    with client.websocket_connect(
        "/ws/mobile-cameras/device", headers=bearer(phone["token"])
    ) as socket:
        assert socket.receive_json()["type"] == "hello"
        assert client.get(f"/api/mobile-cameras/{phone['id']}").json()["status"] == "available"

        requested = client.post(
            f"/api/mobile-cameras/{phone['id']}/sessions", json={"audio": True}, headers=headers
        )
        assert requested.status_code == 201, requested.text
        session_id = requested.json()["id"]
        assert requested.json()["status"] == "awaiting_device"

        incoming = socket.receive_json()
        assert incoming["type"] == "mobile_camera.session_requested"
        assert incoming["requested_by"] == "admin@example.com"

        # Todavía no hay video: el dashboard no puede pedir un ticket de lectura.
        early = client.post(
            f"/api/mobile-camera-sessions/{session_id}/stream-ticket", headers=headers
        )
        assert early.status_code == 403

        accepted = client.post(
            f"/api/mobile-camera-sessions/{session_id}/accept",
            json={"audio": True, "video": True},
            headers=bearer(phone["token"]),
        ).json()
        publish = accepted["publish"]
        path = publish["url"].removeprefix("https://bandit.example/media/").removesuffix("/whip")
        assert path == f"mobile/{phone['id'].replace('-', '')}"
        assert publish["ice_servers"] == [{"urls": ["stun:stun.example:3478"]}]

        assert (
            media_auth(client, key="mala", action="publish", path=path, token=publish["token"])
            == 401
        )
        assert (
            media_auth(
                client, action="publish", path=path, protocol="webrtc", token=publish["token"]
            )
            == 200
        )
        live = client.post(
            f"/api/mobile-camera-sessions/{session_id}/state",
            json={"state": "live"},
            headers=bearer(phone["token"]),
        )
        assert live.json()["status"] == "live"

        view = client.post(
            f"/api/mobile-camera-sessions/{session_id}/stream-ticket", headers=headers
        ).json()
        assert view["url"].endswith("/whep")
        assert (
            media_auth(client, action="read", path=path, protocol="webrtc", token=view["token"])
            == 200
        )
        assert (
            media_auth(
                client,
                action="read",
                path=path,
                protocol="rtsp",
                user="bandit-interno",
                password=INTERNAL_PASSWORD,
            )
            == 200
        )

        # Mientras transmite, el teléfono es una cámara más para el supervisor y el análisis.
        cameras = client.get(f"/api/establishments/{local}/cameras").json()
        assert [(c["name"], c["enabled"]) for c in cameras] == [("Móvil · Teléfono sala", True)]

        stopped = client.post(f"/api/mobile-camera-sessions/{session_id}/stop", headers=headers)
        assert stopped.json()["status"] == "ended"
        ended = socket.receive_json()
        assert ended["type"] == "mobile_camera.session_ended"
        assert ended["reason"] == "user_stopped"

    assert (
        media_auth(client, action="read", path=path, protocol="webrtc", token=view["token"]) == 401
    )


def test_other_locals_cannot_see_or_use_the_phone(client: TestClient) -> None:
    headers = login(client)
    local = create_local(client, headers)
    phone = pair_phone(client, headers, local)

    other = register(client, "otra@example.com", "Otro bar")
    assert client.get(f"/api/establishments/{local}/mobile-cameras").status_code == 403
    assert client.get(f"/api/mobile-cameras/{phone['id']}").status_code == 403
    assert (
        client.post(
            f"/api/mobile-cameras/{phone['id']}/sessions", json={}, headers=other
        ).status_code
        == 403
    )


def test_pairing_requires_a_manager_session_and_csrf(client: TestClient) -> None:
    headers = login(client)
    local = create_local(client, headers)
    assert client.post(f"/api/establishments/{local}/mobile-cameras/pairing").status_code == 403
    client.cookies.clear()
    anonymous = client.post(f"/api/establishments/{local}/mobile-cameras/pairing", headers=headers)
    assert anonymous.status_code in (401, 403)


def test_qr_codes_are_single_use(client: TestClient) -> None:
    headers = login(client)
    local = create_local(client, headers)
    qr = json.loads(
        client.post(f"/api/establishments/{local}/mobile-cameras/pairing", headers=headers).json()[
            "qr_payload"
        ]
    )
    body = {
        "pairing_id": qr["pairing_id"],
        "code": qr["code"],
        "device_name": "Tel",
        "platform": "ios",
    }
    assert client.post("/api/mobile-cameras/register", json=body).status_code == 201
    assert client.post("/api/mobile-cameras/register", json=body).status_code == 401


def test_revoked_phone_loses_access_and_its_socket(client: TestClient) -> None:
    headers = login(client)
    local = create_local(client, headers)
    phone = pair_phone(client, headers, local)

    with client.websocket_connect(
        "/ws/mobile-cameras/device", headers=bearer(phone["token"])
    ) as socket:
        socket.receive_json()
        deleted = client.delete(f"/api/mobile-cameras/{phone['id']}", headers=headers)
        assert deleted.status_code == 204
        assert socket.receive_json()["type"] == "mobile_camera.device_revoked"

    assert client.get("/api/mobile-device/me", headers=bearer(phone["token"])).status_code == 401
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/mobile-cameras/device", headers=bearer(phone["token"])),
    ):
        pass


def test_device_endpoints_need_a_device_token(client: TestClient) -> None:
    assert client.get("/api/mobile-device/me").status_code == 401
    assert client.get("/api/mobile-device/me", headers=bearer("bmc_inventado")).status_code == 401
    assert (
        client.post(
            f"/api/mobile-camera-sessions/{uuid4()}/accept", json={"audio": True}
        ).status_code
        == 401
    )


def test_module_can_be_turned_off(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'apagado.db'}"
    app = create_app(_settings(tmp_path, url, mobile_camera_enabled=False))
    asyncio.run(_create_schema(url))
    with TestClient(app) as client:
        headers = login(client)
        local = create_local(client, headers)
        assert client.get("/api/mobile-cameras/config").json()["enabled"] is False
        assert (
            client.post(
                f"/api/establishments/{local}/mobile-cameras/pairing", headers=headers
            ).status_code
            == 404
        )
