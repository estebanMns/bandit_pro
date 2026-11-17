export type MobilePlatform = "android" | "ios";

export type MobileDeviceStatus =
  | "offline"
  | "registered"
  | "available"
  | "busy"
  | "needs_user_action"
  | "revoked";

export type MobileSessionStatus =
  | "requested"
  | "awaiting_device"
  | "accepted"
  | "connecting"
  | "live"
  | "reconnecting"
  | "rejected"
  | "ended"
  | "failed"
  | "expired";

export interface MobileSession {
  id: string;
  device_id: string;
  establishment_id: string;
  status: MobileSessionStatus;
  requested_by: string;
  audio_enabled: boolean;
  video_enabled: boolean;
  created_at: string;
  answer_by: string;
  expires_at: string;
  started_at: string | null;
  ended_at: string | null;
  end_reason: string | null;
}

export interface MobileDevice {
  id: string;
  establishment_id: string;
  name: string;
  platform: MobilePlatform;
  status: MobileDeviceStatus;
  online: boolean;
  is_available: boolean;
  analysis_enabled: boolean;
  last_seen: string | null;
  created_at: string;
  session: MobileSession | null;
}

export interface Pairing {
  pairing_id: string;
  expires_at: string;
  qr_payload: string;
}

export interface MediaGrant {
  url: string;
  token: string;
  expires_in: number;
  ice_servers: RTCIceServer[];
}

export interface MobileCameraConfig {
  enabled: boolean;
  media_configured: boolean;
  answer_window_seconds: number;
  max_duration_seconds: number;
}
