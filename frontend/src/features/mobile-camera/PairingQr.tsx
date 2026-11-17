"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { Pairing } from "./types";
import styles from "./mobile-camera.module.css";

/** El QR contiene un código de un solo uso; caduca en minutos y nunca se guarda en el navegador. */
export function PairingQr({ pairing, onExpired }: { pairing: Pairing; onExpired: () => void }) {
  const [image, setImage] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(() => remaining(pairing.expires_at));

  useEffect(() => {
    let active = true;
    QRCode.toDataURL(pairing.qr_payload, { margin: 1, width: 260, errorCorrectionLevel: "M" })
      .then((url) => {
        if (active) setImage(url);
      })
      .catch(() => setImage(null));
    return () => {
      active = false;
    };
  }, [pairing]);

  useEffect(() => {
    const timer = setInterval(() => {
      const left = remaining(pairing.expires_at);
      setSecondsLeft(left);
      if (left <= 0) {
        clearInterval(timer);
        onExpired();
      }
    }, 1_000);
    return () => clearInterval(timer);
  }, [pairing, onExpired]);

  return (
    <figure className={styles.qr}>
      {image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image} width={260} height={260} alt="Código QR para vincular el teléfono" />
      ) : (
        <div className={styles.qrVacio} aria-hidden="true" />
      )}
      <figcaption>
        Escanéalo con la app Bandit Mobile Camera. Vence en{" "}
        <strong>
          {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
        </strong>{" "}
        y sirve una sola vez.
      </figcaption>
    </figure>
  );
}

function remaining(expiresAt: string): number {
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - Date.now()) / 1_000));
}
