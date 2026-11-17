"""Avisos push a los teléfonos.

FCM y APNs necesitan credenciales del proyecto (cuenta de servicio de Firebase y llave .p8 de
Apple) y el token push de cada teléfono. Mientras no estén configurados, el aviso se entrega
solo por el WebSocket del teléfono y la solicitud espera a que la aplicación se abra.
"""

from typing import Any

from bandit.mobile_cameras.domain.models import MobileDevice


class DisabledDevicePush:
    async def notify(self, device: MobileDevice, payload: dict[str, Any]) -> bool:
        return False
