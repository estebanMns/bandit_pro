import type { ActivityEntry } from "@/features/activity/types";
import type { FaceCheck } from "@/features/faces/types";
import type { Incident } from "@/features/incidents/types";
import type { MobileSession } from "@/features/mobile-camera/types";

/** Mensajes del backend por /ws/events. */
export type ServerEvent =
  | { type: "sync" }
  | { type: "incident"; incident: Incident }
  | { type: "camera"; cameraId: string; status: string }
  | { type: "analysis"; cameraName: string; entry: ActivityEntry }
  | { type: "face"; check: FaceCheck }
  | { type: "mobile_camera"; deviceId: string }
  | { type: "mobile_camera_session"; session: MobileSession };

export type ToSharedWorker =
  | { type: "join"; establishmentId: string }
  | { type: "leave" };

export type FromSharedWorker =
  | ServerEvent
  | { type: "connection"; connected: boolean; tabs: number };
