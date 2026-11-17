"""Convierte eventos de dominio en mensajes para el navegador."""

from bandit.analysis.public import ActivityEntryResponse, AnalysisActivity
from bandit.cameras.public import CameraStatusChanged
from bandit.faces.public import FaceCheckDone, FaceCheckResponse
from bandit.incidents.public import IncidentChanged, IncidentResponse
from bandit.mobile_cameras.public import MobileDeviceChanged, MobileSessionChanged, SessionResponse
from bandit.realtime.application.event_hub import EventHub


class LiveEventPublisher:
    def __init__(self, hub: EventHub) -> None:
        self._hub = hub

    async def on_incident_changed(self, event: IncidentChanged) -> None:
        incident = IncidentResponse.of(event.incident)
        self._hub.publish(
            event.incident.establishment_id,
            {"type": "incident", "incident": incident.model_dump(mode="json")},
        )

    async def on_camera_status(self, event: CameraStatusChanged) -> None:
        self._hub.publish(
            event.establishment_id,
            {"type": "camera", "cameraId": str(event.camera_id), "status": event.status.value},
        )

    async def on_analysis_activity(self, event: AnalysisActivity) -> None:
        entry = ActivityEntryResponse.of(event.camera_id, event)
        self._hub.publish(
            event.establishment_id,
            {
                "type": "analysis",
                "cameraName": event.camera_name,
                "entry": entry.model_dump(mode="json"),
            },
        )

    async def on_face_check(self, event: FaceCheckDone) -> None:
        check = FaceCheckResponse.of(event.check)
        self._hub.publish(
            event.check.establishment_id,
            {"type": "face", "check": check.model_dump(mode="json")},
        )

    async def on_mobile_device(self, event: MobileDeviceChanged) -> None:
        self._hub.publish(
            event.establishment_id, {"type": "mobile_camera", "deviceId": str(event.device_id)}
        )

    async def on_mobile_session(self, event: MobileSessionChanged) -> None:
        session = SessionResponse.of(event.session)
        self._hub.publish(
            event.session.establishment_id,
            {"type": "mobile_camera_session", "session": session.model_dump(mode="json")},
        )
