"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import {
  createPairing,
  requestMobileSession,
  revokeMobileCamera,
  setMobileAnalysis,
  setMobileAvailability,
} from "./api";
import { deviceStatusLabel, platformLabel } from "./labels";
import { PairingQr } from "./PairingQr";
import type { MobileDevice, Pairing } from "./types";
import { useMobileCameras } from "./useMobileCameras";
import styles from "./mobile-camera.module.css";

/** Sección "Cámaras móviles" dentro de Ajustes > Cámaras. */
export function MobileCamerasPanel({ establishmentId }: { establishmentId: string }) {
  const router = useRouter();
  const { config, devices, reload } = useMobileCameras(establishmentId);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audio, setAudio] = useState(true);
  const clearPairing = useCallback(() => setPairing(null), []);

  if (!config?.enabled) return null;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "No hay conexión con el servidor.");
    }
  }

  async function startSession(device: MobileDevice) {
    setError(null);
    try {
      const session = await requestMobileSession(device.id, audio);
      router.push(`/ajustes/camaras/movil/${session.id}`);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "No hay conexión con el servidor.");
    }
  }

  return (
    <section className={`vidrio ${styles.panel}`} aria-labelledby="camaras-moviles">
      <h2 id="camaras-moviles">Cámaras móviles</h2>
      <p className={styles.ayuda}>
        Usa un Android o iPhone como cámara bajo demanda. El teléfono solo transmite cuando alguien
        lo autoriza en su pantalla, muestra que la cámara y el micrófono están activos y nada se
        graba.
      </p>
      {!config.media_configured && (
        <p className={styles.aviso}>
          El servidor de video (MediaMTX) aún no está configurado: puedes vincular teléfonos, pero
          no transmitir.
        </p>
      )}

      {pairing ? (
        <div className={styles.vinculacion}>
          <PairingQr pairing={pairing} onExpired={clearPairing} />
          <Button variant="secundario" onClick={() => setPairing(null)}>
            Listo
          </Button>
        </div>
      ) : (
        <Button onClick={() => void run(async () => setPairing(await createPairing(establishmentId)))}>
          Vincular un teléfono
        </Button>
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {devices.length === 0 ? (
        <p className={styles.ayuda}>Todavía no hay teléfonos vinculados.</p>
      ) : (
        <>
          <label className={styles.opcion}>
            <input type="checkbox" checked={audio} onChange={(e) => setAudio(e.target.checked)} />
            Pedir también el audio
          </label>
          <ul className={styles.dispositivos}>
            {devices.map((device) => (
              <li key={device.id} className={styles.dispositivo}>
                <div className={styles.identidad}>
                  <strong>{device.name}</strong>
                  <span className={styles.tenue}>
                    {platformLabel(device.platform)}
                    {device.last_seen &&
                      ` · visto ${new Date(device.last_seen).toLocaleString("es-CO")}`}
                  </span>
                </div>
                <span className={styles.estado} data-estado={device.status}>
                  {deviceStatusLabel(device.status)}
                </span>
                <div className={styles.acciones}>
                  {device.session ? (
                    <Link
                      className={styles.enlace}
                      href={`/ajustes/camaras/movil/${device.session.id}`}
                    >
                      Ver sesión
                    </Link>
                  ) : (
                    <Button
                      disabled={!device.is_available || !config.media_configured}
                      onClick={() => void startSession(device)}
                      title={
                        device.is_available
                          ? undefined
                          : "Actívalo como disponible en la app o aquí"
                      }
                    >
                      Solicitar transmisión
                    </Button>
                  )}
                  <Button
                    variant="secundario"
                    onClick={() =>
                      void run(() => setMobileAvailability(device.id, !device.is_available))
                    }
                  >
                    {device.is_available ? "Marcar no disponible" : "Marcar disponible"}
                  </Button>
                  <Button
                    variant="secundario"
                    onClick={() =>
                      void run(() => setMobileAnalysis(device.id, !device.analysis_enabled))
                    }
                    aria-pressed={device.analysis_enabled}
                  >
                    {device.analysis_enabled ? "Análisis activado" : "Analizar con Bandit"}
                  </Button>
                  <Button
                    variant="peligro"
                    onClick={() => {
                      if (window.confirm(`¿Desvincular ${device.name}? Tendrás que escanear otro QR.`)) {
                        void run(() => revokeMobileCamera(device.id));
                      }
                    }}
                  >
                    Desvincular
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
