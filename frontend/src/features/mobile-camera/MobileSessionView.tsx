"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import type { ServerEvent } from "@/features/live/protocol";
import { useLiveEvents } from "@/features/live/useLiveEvents";
import { ApiError } from "@/lib/api";
import { getMobileSession, stopMobileSession, streamTicket } from "./api";
import { canWatch, endReasonLabel, isOpen, sessionStatusLabel } from "./labels";
import type { MobileSession } from "./types";
import { connectWhep, type WhepConnection } from "./whep";
import styles from "./mobile-camera.module.css";

const RETRY_MS = 3_000;

export function MobileSessionView({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<MobileSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(true);
  const [playing, setPlaying] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const connection = useRef<WhepConnection | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSession(await getMobileSession(sessionId));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "No hay conexión con el servidor.");
    }
  }, [sessionId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const onEvent = useCallback(
    (event: ServerEvent) => {
      if (event.type === "mobile_camera_session" && event.session.id === sessionId) {
        setSession(event.session);
      } else if (event.type === "sync") {
        void refresh();
      }
    },
    [sessionId, refresh],
  );
  useLiveEvents(session?.establishment_id, onEvent);

  const watchable = session ? canWatch(session.status) : false;

  // Conecta el reproductor cuando hay video y lo cierra al terminar la sesión.
  useEffect(() => {
    if (!watchable) return;
    const element = video.current;
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    async function attach() {
      try {
        const grant = await streamTicket(sessionId);
        const opened = await connectWhep(grant.url, grant.token, grant.ice_servers);
        if (cancelled) {
          await opened.close();
          return;
        }
        connection.current = opened;
        if (element) element.srcObject = opened.stream;
        setPlaying(true);
        setError(null);
        opened.peer.addEventListener("connectionstatechange", () => {
          const state = opened.peer.connectionState;
          if ((state === "failed" || state === "disconnected") && !cancelled) {
            setPlaying(false);
            void opened.close();
            connection.current = null;
            retry = setTimeout(() => void attach(), RETRY_MS);
          }
        });
      } catch (failure) {
        if (cancelled) return;
        setPlaying(false);
        setError(failure instanceof Error ? failure.message : "No se pudo abrir el video.");
        retry = setTimeout(() => void attach(), RETRY_MS);
      }
    }

    void attach();
    return () => {
      cancelled = true;
      clearTimeout(retry);
      setPlaying(false);
      void connection.current?.close();
      connection.current = null;
      if (element) element.srcObject = null;
    };
  }, [watchable, sessionId]);

  async function stop() {
    try {
      setSession(await stopMobileSession(sessionId));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "No se pudo detener la sesión.");
    }
  }

  const open = session ? isOpen(session.status) : false;
  const reason = session ? endReasonLabel(session.end_reason) : null;

  return (
    <div className={styles.sesion}>
      <Link href="/ajustes/camaras">Volver a cámaras</Link>
      <div className={`vidrio ${styles.reproductor}`}>
        <video
          ref={video}
          autoPlay
          playsInline
          muted={muted}
          className={styles.video}
          aria-label="Video en vivo del teléfono"
          data-activo={playing}
        />
        {!playing && (
          <p className={styles.superpuesto} role="status">
            {session ? sessionStatusLabel(session.status) : "Cargando la sesión…"}
          </p>
        )}
      </div>

      {session && (
        <div className={styles.barra}>
          <span className={styles.estado} data-estado={session.status}>
            {sessionStatusLabel(session.status)}
          </span>
          <span className={styles.indicador} data-activo={session.audio_enabled && playing}>
            {session.audio_enabled ? "Audio autorizado" : "Sin audio"}
          </span>
          <span className={styles.tenue}>Solicitada por {session.requested_by}</span>
          {session.audio_enabled && (
            <Button variant="secundario" onClick={() => setMuted((value) => !value)}>
              {muted ? "Activar sonido" : "Silenciar"}
            </Button>
          )}
          {open && (
            <Button variant="peligro" onClick={() => void stop()}>
              Detener transmisión
            </Button>
          )}
        </div>
      )}
      {reason && <p className={styles.ayuda}>{reason}</p>}
      {error && open && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
