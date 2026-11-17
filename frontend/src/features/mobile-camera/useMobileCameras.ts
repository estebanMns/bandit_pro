"use client";

import { useCallback, useEffect, useState } from "react";
import type { ServerEvent } from "@/features/live/protocol";
import { useLiveEvents } from "@/features/live/useLiveEvents";
import { listMobileCameras, mobileCameraConfig } from "./api";
import type { MobileCameraConfig, MobileDevice } from "./types";

/** Lista de teléfonos del local, al día con los eventos del backend. */
export function useMobileCameras(establishmentId: string | undefined) {
  const [config, setConfig] = useState<MobileCameraConfig | null>(null);
  const [devices, setDevices] = useState<MobileDevice[]>([]);

  const reload = useCallback(async () => {
    if (!establishmentId) return;
    try {
      setDevices(await listMobileCameras(establishmentId));
    } catch {
      // Se conserva la última lista; el próximo evento la vuelve a pedir.
    }
  }, [establishmentId]);

  useEffect(() => {
    mobileCameraConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  const onEvent = useCallback(
    (event: ServerEvent) => {
      if (event.type === "sync" || event.type === "mobile_camera" || event.type === "mobile_camera_session") {
        void reload();
      }
    },
    [reload],
  );

  useLiveEvents(config?.enabled ? establishmentId : undefined, onEvent);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (config?.enabled) void reload();
  }, [config, reload]);

  return { config, devices, reload };
}
