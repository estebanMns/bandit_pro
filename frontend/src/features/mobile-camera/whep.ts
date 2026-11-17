/**
 * Cliente WHEP mínimo: pide a MediaMTX el audio y video de una sesión con un ticket temporal.
 * La negociación espera a reunir los candidatos ICE (sin trickle) para simplificar.
 */

const ICE_GATHERING_TIMEOUT_MS = 3_000;

export interface WhepConnection {
  stream: MediaStream;
  peer: RTCPeerConnection;
  close: () => Promise<void>;
}

function waitForIce(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(done, ICE_GATHERING_TIMEOUT_MS);
    function done() {
      clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", check);
      resolve();
    }
    function check() {
      if (peer.iceGatheringState === "complete") done();
    }
    peer.addEventListener("icegatheringstatechange", check);
  });
}

export function resolveUrl(base: string, location: string | null): string | null {
  if (!location) return null;
  try {
    return new URL(location, base).toString();
  } catch {
    return null;
  }
}

export async function connectWhep(
  url: string,
  token: string,
  iceServers: RTCIceServer[],
): Promise<WhepConnection> {
  const peer = new RTCPeerConnection({ iceServers });
  const stream = new MediaStream();
  peer.addTransceiver("video", { direction: "recvonly" });
  peer.addTransceiver("audio", { direction: "recvonly" });
  peer.ontrack = (event) => stream.addTrack(event.track);

  try {
    await peer.setLocalDescription(await peer.createOffer());
    await waitForIce(peer);
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${token}` },
      body: peer.localDescription?.sdp ?? "",
    });
    if (response.status !== 201) {
      throw new Error(
        response.status === 401 || response.status === 403
          ? "El servidor de video rechazó el acceso."
          : "El teléfono todavía no envía video.",
      );
    }
    const answer = await response.text();
    await peer.setRemoteDescription({ type: "answer", sdp: answer });
    const resource = resolveUrl(url, response.headers.get("Location"));

    return {
      stream,
      peer,
      close: async () => {
        stream.getTracks().forEach((track) => track.stop());
        peer.close();
        if (resource) {
          await fetch(resource, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          }).catch(() => undefined);
        }
      },
    };
  } catch (failure) {
    peer.close();
    throw failure;
  }
}
