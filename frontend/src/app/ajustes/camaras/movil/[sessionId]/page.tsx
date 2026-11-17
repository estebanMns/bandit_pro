import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { MobileSessionView } from "@/features/mobile-camera/MobileSessionView";
import styles from "../../../ajustes.module.css";

export const metadata: Metadata = { title: "Cámara móvil en vivo" };

export default async function MobileSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return (
    <AppShell>
      <main className={styles.pagina}>
        <h1 className={styles.titulo}>Cámara móvil</h1>
        <MobileSessionView sessionId={sessionId} />
      </main>
    </AppShell>
  );
}
