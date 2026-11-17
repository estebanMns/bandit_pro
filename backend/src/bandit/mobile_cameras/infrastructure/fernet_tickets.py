"""Tickets multimedia cifrados con Fernet: una sesión, una ruta y una acción."""

import json
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from bandit.mobile_cameras.domain.ports import MediaTicket, TicketKind


class FernetTicketSigner:
    def __init__(self, key: str | bytes | None = None) -> None:
        # Sin clave configurada se usa una por proceso: los tickets duran un par de minutos.
        self._fernet = Fernet(key or Fernet.generate_key())

    def issue(self, ticket: MediaTicket) -> str:
        payload = {"k": ticket.kind.value, "s": ticket.session_id.hex, "p": ticket.path}
        return self._fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()

    def verify(self, token: str, ttl_seconds: int) -> MediaTicket | None:
        try:
            raw = self._fernet.decrypt(token.encode(), ttl=ttl_seconds)
            payload = json.loads(raw)
            return MediaTicket(TicketKind(payload["k"]), UUID(hex=payload["s"]), str(payload["p"]))
        except (InvalidToken, ValueError, KeyError, TypeError):
            return None
