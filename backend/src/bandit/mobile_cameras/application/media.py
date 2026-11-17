"""Direcciones de MediaMTX y servidores ICE (STUN/TURN) para cada sesión."""

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MediaSettings:
    # URL pública de MediaMTX para WebRTC (WHIP/WHEP), por ejemplo https://bandit.example/media.
    public_webrtc_url: str
    # Base RTSP interna de MediaMTX que lee el supervisor de cámaras: rtsp://mediamtx:8554.
    internal_rtsp_url: str
    # Usuario interno con permiso de solo lectura; MediaMTX lo valida contra este backend.
    internal_user: str
    internal_password: str
    stun_urls: tuple[str, ...] = ()
    turn_urls: tuple[str, ...] = ()
    # Secreto compartido con coturn (use-auth-secret): genera credenciales que caducan.
    turn_shared_secret: str = ""
    turn_ttl: timedelta = timedelta(hours=1)
    publish_ticket_ttl: timedelta = timedelta(minutes=2)
    view_ticket_ttl: timedelta = timedelta(minutes=1)

    @property
    def configured(self) -> bool:
        return bool(self.public_webrtc_url)

    def whip_url(self, path: str) -> str:
        return f"{self.public_webrtc_url.rstrip('/')}/{path}/whip"

    def whep_url(self, path: str) -> str:
        return f"{self.public_webrtc_url.rstrip('/')}/{path}/whep"

    def internal_rtsp_for(self, path: str) -> str:
        """URL que guarda el módulo de cámaras (cifrada) para analizar el teléfono."""
        base = self.internal_rtsp_url.rstrip("/")
        scheme, _, rest = base.partition("://")
        credentials = (
            f"{quote(self.internal_user, safe='')}:{quote(self.internal_password, safe='')}"
        )
        return f"{scheme}://{credentials}@{rest}/{path}"

    def ice_servers(self, session_id: UUID, now: datetime) -> list[dict[str, Any]]:
        servers: list[dict[str, Any]] = []
        if self.stun_urls:
            servers.append({"urls": list(self.stun_urls)})
        if self.turn_urls and self.turn_shared_secret:
            username, credential = turn_credentials(
                self.turn_shared_secret, session_id, now + self.turn_ttl
            )
            servers.append(
                {"urls": list(self.turn_urls), "username": username, "credential": credential}
            )
        return servers


def turn_credentials(secret: str, session_id: UUID, expires_at: datetime) -> tuple[str, str]:
    """Credenciales temporales de la API REST de TURN (coturn `use-auth-secret`)."""
    username = f"{int(expires_at.timestamp())}:{session_id.hex}"
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return username, base64.b64encode(digest).decode()
