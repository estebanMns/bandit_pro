"""Conexiones WebSocket abiertas por los teléfonos.

La presencia vive en memoria del proceso, igual que el EventHub del dashboard: con varios
backends, cada uno solo conoce los teléfonos conectados a él.
"""

from typing import Any
from uuid import UUID

from bandit.shared.fanout import Overflow, Subscription

_QUEUE_CAPACITY = 32

DeviceMessage = dict[str, Any]


class DeviceHub:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[Subscription[DeviceMessage]]] = {}

    def connect(self, device_id: UUID) -> Subscription[DeviceMessage]:
        subscription: Subscription[DeviceMessage] = Subscription(
            _QUEUE_CAPACITY, Overflow.DISCONNECT
        )
        self._connections.setdefault(device_id, set()).add(subscription)
        return subscription

    def disconnect(self, device_id: UUID, subscription: Subscription[DeviceMessage]) -> None:
        subscription.close()
        connections = self._connections.get(device_id)
        if connections is None:
            return
        connections.discard(subscription)
        if not connections:
            self._connections.pop(device_id, None)

    def is_online(self, device_id: UUID) -> bool:
        return any(not s.closed for s in self._connections.get(device_id, ()))

    def send(self, device_id: UUID, message: DeviceMessage) -> bool:
        """Devuelve si había al menos una conexión para recibirlo."""
        delivered = False
        for subscription in tuple(self._connections.get(device_id, ())):
            subscription.offer(message)
            if subscription.closed:
                self.disconnect(device_id, subscription)
            else:
                delivered = True
        return delivered

    def kick(self, device_id: UUID) -> None:
        """Avisa y cierra las conexiones del teléfono, por ejemplo al desvincularlo."""
        for subscription in self._connections.pop(device_id, set()):
            subscription.offer({"type": "mobile_camera.device_revoked"})
            subscription.close()
