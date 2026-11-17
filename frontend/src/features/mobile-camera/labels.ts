import type { MobileDeviceStatus, MobileSessionStatus } from "./types";

const DEVICE: Record<MobileDeviceStatus, string> = {
  offline: "Sin conexión",
  registered: "Registrado, no disponible",
  available: "Disponible",
  busy: "Transmitiendo",
  needs_user_action: "Esperando autorización en el teléfono",
  revoked: "Desvinculado",
};

const SESSION: Record<MobileSessionStatus, string> = {
  requested: "Solicitud enviada; el teléfono aún no la recibe",
  awaiting_device: "Esperando autorización en el teléfono",
  accepted: "Autorizada, preparando el video",
  connecting: "Conectando",
  live: "Transmisión activa",
  reconnecting: "Reconectando",
  rejected: "La solicitud fue rechazada en el teléfono",
  ended: "Sesión finalizada",
  failed: "No se pudo establecer la conexión",
  expired: "La sesión venció",
};

const END_REASON: Record<string, string> = {
  user_stopped: "Se detuvo desde el dashboard.",
  device_stopped: "Se detuvo desde el teléfono.",
  rejected: "Rechazada en el teléfono.",
  not_answered: "Nadie respondió en el teléfono a tiempo.",
  max_duration: "Se alcanzó la duración máxima.",
  device_revoked: "El teléfono fue desvinculado.",
  device_unavailable: "El teléfono dejó de estar disponible.",
  media_failed: "Falló la conexión de video.",
};

export function deviceStatusLabel(status: MobileDeviceStatus): string {
  return DEVICE[status];
}

export function sessionStatusLabel(status: MobileSessionStatus): string {
  return SESSION[status];
}

export function endReasonLabel(reason: string | null): string | null {
  return reason ? (END_REASON[reason] ?? null) : null;
}

const OPEN: ReadonlySet<MobileSessionStatus> = new Set([
  "requested",
  "awaiting_device",
  "accepted",
  "connecting",
  "live",
  "reconnecting",
]);

export function isOpen(status: MobileSessionStatus): boolean {
  return OPEN.has(status);
}

/** Hay video que pedir a MediaMTX solo cuando el teléfono ya publica. */
export function canWatch(status: MobileSessionStatus): boolean {
  return status === "connecting" || status === "live" || status === "reconnecting";
}

export function platformLabel(platform: string): string {
  return platform === "ios" ? "iPhone" : "Android";
}
