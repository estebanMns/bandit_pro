import { api } from "@/lib/api";
import type {
  MediaGrant,
  MobileCameraConfig,
  MobileDevice,
  MobileSession,
  Pairing,
} from "./types";

export function mobileCameraConfig(): Promise<MobileCameraConfig> {
  return api("/api/mobile-cameras/config");
}

export function listMobileCameras(establishmentId: string): Promise<MobileDevice[]> {
  return api(`/api/establishments/${establishmentId}/mobile-cameras`);
}

export function createPairing(establishmentId: string): Promise<Pairing> {
  return api(`/api/establishments/${establishmentId}/mobile-cameras/pairing`, { method: "POST" });
}

export function setMobileAvailability(deviceId: string, available: boolean): Promise<MobileDevice> {
  return api(`/api/mobile-cameras/${deviceId}/availability`, {
    method: "PATCH",
    body: JSON.stringify({ available }),
  });
}

export function setMobileAnalysis(deviceId: string, enabled: boolean): Promise<MobileDevice> {
  return api(`/api/mobile-cameras/${deviceId}/analysis`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export function revokeMobileCamera(deviceId: string): Promise<void> {
  return api(`/api/mobile-cameras/${deviceId}`, { method: "DELETE" });
}

export function requestMobileSession(deviceId: string, audio: boolean): Promise<MobileSession> {
  return api(`/api/mobile-cameras/${deviceId}/sessions`, {
    method: "POST",
    body: JSON.stringify({ audio }),
  });
}

export function getMobileSession(sessionId: string): Promise<MobileSession> {
  return api(`/api/mobile-camera-sessions/${sessionId}`);
}

export function stopMobileSession(sessionId: string): Promise<MobileSession> {
  return api(`/api/mobile-camera-sessions/${sessionId}/stop`, { method: "POST" });
}

/** Ticket de lectura de un minuto: el navegador nunca recibe una URL permanente. */
export function streamTicket(sessionId: string): Promise<MediaGrant> {
  return api(`/api/mobile-camera-sessions/${sessionId}/stream-ticket`, { method: "POST" });
}
