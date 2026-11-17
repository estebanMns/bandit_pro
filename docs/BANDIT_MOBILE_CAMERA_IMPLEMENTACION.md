# Bandit Mobile Camera: implementación en bandit_pro

Este documento acompaña la especificación [`BANDIT_MOBILE_CAMERA.md`](BANDIT_MOBILE_CAMERA.md).
Recoge la auditoría del repositorio (Fase 0), las decisiones tomadas, lo que quedó construido y
lo que falta validar en dispositivos y en el despliegue real.

## 1. Auditoría del repositorio (Fase 0)

| Pregunta de la especificación (§20) | Respuesta en el código actual |
|---|---|
| Versión de MediaMTX y protocolos | Solo existía como **puente RTSP** (`relay/`, v1.12.2, WebRTC apagado). No estaba en `docker-compose.yml`. Se agrega un servicio nuevo con WebRTC (WHIP/WHEP) y autorización HTTP. |
| ¿Reproductor WebRTC reutilizable? | No. El dashboard recibe JPEG por `/ws/video/{camera_id}` (Web Worker + SharedArrayBuffer). Se agrega un cliente **WHEP** pequeño para las sesiones móviles. |
| ¿Cómo consume video el supervisor? | `cameras/application/supervisor.py` lee **RTSP con ffmpeg** a partir de la URL cifrada de cada cámara. El análisis arranca solo cuando una cámara pasa a `live` (`CameraStatusChanged`). |
| ¿Sistema de notificaciones? | WhatsApp Cloud y Web Push (VAPID) para operadores. **No hay FCM ni APNs.** |
| Autenticación y permisos | Cookie de sesión + CSRF; roles `admin`, `owner`, `operator`; todo recurso pertenece a un **local** (`establishment_id`) y se valida con `user.can_access(...)`. |
| RLS de Supabase | Todas las tablas nacen con RLS activado y sin políticas: los clientes nunca hablan con Supabase directo; todo pasa por el backend. `tests/test_migrations.py` lo exige. |
| Transmisiones simultáneas | Una sesión abierta por teléfono. El límite global depende del servidor (ver §6). |
| Resolución, FPS y bitrate | Captura en el teléfono: ideal 1280×720 a 20 fps (máx. 25). El análisis sigue usando `VIDEO_FPS` y `VIDEO_WIDTH` del supervisor. |

### Puntos de integración

| Pieza existente | Cómo se reutiliza |
|---|---|
| `identity` | `CurrentUser`, `ManagerUser`, `require_csrf`, `can_access` y `AttemptThrottle` (exportado ahora en `identity.public`). |
| `cameras` | El teléfono se registra **como una cámara más** (URL RTSP interna de MediaMTX, cifrada con la misma clave). Se activa solo mientras hay sesión en vivo y análisis habilitado. El módulo móvil no importa `cameras`: `bootstrap.py` lo conecta por el puerto `CameraSources`. |
| `analysis` / Gemini | Sin cambios: el muestreo, los límites diarios, la cola y el filtro de movimiento son los mismos para la fuente móvil. El audio nunca entra al análisis. |
| `realtime` | `LiveEventPublisher` difunde `mobile_camera` y `mobile_camera_session` por el WebSocket de eventos existente (SharedWorker del frontend). |
| `shared/fanout.py` | Colas por teléfono para el WebSocket del dispositivo. |
| Migraciones Alembic | `0010_camaras_moviles.py`, con RLS. |
| Frontend | Sección dentro de **Ajustes › Cámaras** (no un dashboard aparte) y vista de sesión en `/ajustes/camaras/movil/[sessionId]`. |

## 2. Arquitectura implementada

```text
 Teléfono (Flutter)                       Backend FastAPI                    Dashboard Next.js
 ──────────────────                       ───────────────                    ─────────────────
 QR ─► POST /api/mobile-cameras/register ─► código hash, un uso, 5 min
 WSS /ws/mobile-cameras/device ◄──────────► DeviceHub (eventos, latidos)
                                           ◄── POST /mobile-cameras/{id}/sessions ◄── "Solicitar"
 pantalla "¿Aceptar?" ◄─ session_requested
 POST /sessions/{id}/accept ─────────────► ticket WHIP (2 min) + ICE/TURN temporales
 WHIP ──► MediaMTX ──(authMethod http)──► POST /api/mobile-cameras/media-auth?key=…
                                           accepted → connecting
 POST /sessions/{id}/state live ────────► connecting → live ─► cámara habilitada (si análisis)
                    MediaMTX ─RTSP interno─► supervisor ffmpeg ─► análisis Gemini
                    MediaMTX ─WHEP───────────────────────────────────────────► <video>
                                           ◄── POST /sessions/{id}/stream-ticket (1 min)
 session_ended ◄────────────────────────── POST /sessions/{id}/stop ◄──────── "Detener"
```

### Estados

Teléfono (calculado, no guardado): `offline`, `registered`, `available`, `busy`,
`needs_user_action`, `revoked`. La presencia viene del WebSocket del teléfono.

Sesión: `requested → awaiting_device → accepted → connecting → live ⇄ reconnecting`, y los
finales `rejected`, `ended`, `failed`, `expired`. `StreamSession.move_to` valida cada transición
(`domain/models.py`). Nadie puede marcar `live` si MediaMTX no autorizó antes la publicación.

Vencimientos: 90 s para responder en el teléfono y 15 min de duración máxima (configurables).
Un trabajo de APScheduler cierra cada 30 s lo vencido; además se revisa en cada lectura.

### API

| Método | Ruta | Quién | Nota |
|---|---|---|---|
| GET | `/api/mobile-cameras/config` | público | ¿Módulo y MediaMTX activos? |
| POST | `/api/establishments/{id}/mobile-cameras/pairing` | dueño + CSRF | Devuelve el texto del QR. *La especificación proponía `/api/mobile-cameras/pairing`; se ancla al local como el resto de la API.* |
| GET | `/api/establishments/{id}/mobile-cameras` | usuario del local | |
| GET | `/api/establishments/{id}/mobile-camera-sessions` | usuario del local | Últimas 20 (auditoría) |
| GET | `/api/mobile-cameras/{id}` | usuario del local | |
| PATCH | `/api/mobile-cameras/{id}/availability` | dueño + CSRF | |
| PATCH | `/api/mobile-cameras/{id}/analysis` | dueño + CSRF | Análisis apagado por defecto |
| DELETE | `/api/mobile-cameras/{id}` | dueño + CSRF | Revoca, cierra sesión, quita la fuente y expulsa el WebSocket |
| POST | `/api/mobile-cameras/{id}/sessions` | usuario del local + CSRF | `{ "audio": true }` |
| GET | `/api/mobile-camera-sessions/{id}` | usuario del local | |
| POST | `/api/mobile-camera-sessions/{id}/stop` | usuario del local + CSRF | |
| POST | `/api/mobile-camera-sessions/{id}/stream-ticket` | usuario del local + CSRF | Ticket WHEP de 1 min |
| POST | `/api/mobile-cameras/register` | QR | Limitado por IP |
| GET | `/api/mobile-device/me` | token del teléfono | |
| PATCH | `/api/mobile-device/availability` | token | |
| POST | `/api/mobile-device/token` | token | Rota el token |
| DELETE | `/api/mobile-device` | token | El teléfono se desvincula |
| POST | `/api/mobile-camera-sessions/{id}/accept` | token | `{ "audio", "video" }` → ticket WHIP |
| POST | `/api/mobile-camera-sessions/{id}/reject` | token | |
| POST | `/api/mobile-camera-sessions/{id}/publish-ticket` | token | Para reconectar sin pedir permiso de nuevo |
| POST | `/api/mobile-camera-sessions/{id}/state` | token | `live`, `reconnecting`, `failed` |
| POST | `/api/mobile-device/sessions/{id}/stop` | token | |
| POST | `/api/mobile-cameras/media-auth?key=…` | MediaMTX | Responde solo 200/401 |
| WS | `/ws/mobile-cameras/device` | `Authorization: Bearer` | Eventos y latidos (`ping`/`pong`) |

### Datos

`mobile_camera_devices`, `mobile_camera_pairings` y `mobile_camera_sessions`, como en la
especificación, con estos ajustes:

- `establishment_id` es obligatorio: en Bandit todo pertenece a un local.
- `status` del teléfono no se guarda: se calcula (evita estados viejos tras un reinicio).
- Se agregan `analysis_enabled` y `camera_id` (fuente en el módulo de cámaras) al teléfono, y
  `requested_by_label` y `answer_by` a la sesión.
- `push_token` queda fuera hasta implementar FCM/APNs.
- Solo se guardan huellas SHA-256 de códigos QR y tokens. Ni audio, ni video, ni tickets.

### Decisiones

1. **Ruta de medios por teléfono, permiso por sesión.** La ruta es `mobile/<id del teléfono>`
   porque la fuente de cámara guarda una URL fija. Lo temporal es la autorización: cada ticket
   nombra la sesión, la ruta y la acción, caduca en 1–2 min, y `media-auth` comprueba además que
   la sesión siga abierta. Al cerrar la sesión, ningún ticket vuelve a servir.
2. **Tickets reutilizables dentro de su vigencia.** MediaMTX autentica cada petición HTTP de
   WHIP/WHEP (POST, PATCH de ICE, DELETE), así que un ticket de un solo uso rompería la
   negociación. Se compensa con vigencia muy corta y alcance mínimo.
3. **WHIP directo desde Flutter.** `flutter_webrtc` no trae WHIP, pero el protocolo es un POST
   con SDP: se implementó en `whip_publisher.dart` sin negociación por trickle ICE.
4. **Sin servicio en primer plano ni push en v1.** El teléfono recibe solicitudes con la app
   abierta; al pasar a segundo plano la transmisión se detiene. Es lo que permiten iOS y
   Android sin prometer de más (§1.2 y §6 de la especificación).
5. **El teléfono puede quitar el audio, nunca agregarlo.** `audio_enabled` final =
   pedido por el dashboard ∧ aceptado en el teléfono ∧ permiso del sistema.

## 3. Despliegue

```bash
# .env
MOBILE_CAMERA_ENABLED=true
MOBILE_CAMERA_TICKET_KEY=<Fernet>
MEDIAMTX_PUBLIC_WEBRTC_URL=https://tu-dominio/media
MEDIAMTX_INTERNAL_PASSWORD=<aleatorio>
MEDIAMTX_AUTH_SECRET=<aleatorio>
MEDIAMTX_PUBLIC_HOST=<IP o dominio público>
WEBRTC_STUN_URLS=stun:stun.l.google.com:19302
WEBRTC_TURN_URLS=turn:turn.tu-dominio:3478?transport=udp,turns:turn.tu-dominio:5349
WEBRTC_TURN_SHARED_SECRET=<mismo secreto de coturn>

docker compose --profile mobile up -d
```

- `deploy/mediamtx/mediamtx.yml`: solo rutas `mobile/<32 hex>`, sin API, métricas, grabación ni
  reproducción. RTSP (8554) y HTTP (8889) quedan dentro de la red de Docker; Caddy publica WHIP
  y WHEP bajo `/media`. En el host solo se abre **8189 UDP/TCP** para los medios.
- `deploy/coturn/turnserver.conf.example`: TURN con `use-auth-secret` (credenciales que
  caducan) y sin relevo hacia redes privadas.
- MediaMTX también necesita los servidores ICE del lado del servidor si está detrás de NAT:
  `MTX_WEBRTCICESERVERS2_0_URL`, `…_USERNAME`, `…_PASSWORD` (credenciales TURN propias del
  servidor).
- Con frontend en Vercel y backend en Render, MediaMTX debe vivir en un equipo con IP pública y
  UDP abierto (Render no expone UDP). `MEDIAMTX_PUBLIC_WEBRTC_URL` apunta allí y el
  Allow-Origin de WebRTC de MediaMTX debe permitir el dominio del frontend.

## 4. Estado por fase

| Fase | Estado |
|---|---|
| 0. Auditoría | Hecha (este documento). |
| 1. Backend, base de datos y vinculación | Hecha, con pruebas. |
| 2. Aplicación Flutter | Código completo en `mobile/bandit_mobile_camera`. **Sin compilar ni probar en dispositivos**: el entorno donde se escribió no tenía Flutter. |
| 3. WebRTC y MediaMTX | Backend, configuración y publicador WHIP hechos. Falta la prueba real entre redes y con TURN obligatorio. |
| 4. Dashboard | Hecho: QR, listado, estados, disponibilidad, análisis, solicitar, ver (WHEP), silenciar y detener. |
| 5. Integración con cámaras y Gemini | Hecha por el puerto `CameraSources`; probada con el módulo real de cámaras. Falta verificar ffmpeg leyendo el RTSP de MediaMTX con un teléfono real. |
| 6. Seguridad y pruebas finales | Pruebas automáticas de autorización, revocación, vencimiento y tickets. Pendiente la parte física (§18 de la especificación). |

### Pendiente

- Compilar la app (`mobile/bandit_mobile_camera/setup.sh`) y probarla en Android e iPhone
  físicos; fijar versiones en `pubspec.lock`.
- Prueba vertical mínima: un teléfono, otra red, TURN, reproducción en el dashboard y cierre.
- Confirmar el códec que negocia cada teléfono (H.264 es el más compatible con el RTSP que lee
  ffmpeg; si llega VP8 y ffmpeg no lo procesa bien, forzar H.264 en el SDP).
- FCM y APNs (`DevicePush` ya es un puerto con un adaptador desactivado).
- Límite global de sesiones simultáneas y de ancho de banda según la capacidad del servidor.
- Presencia de teléfonos en memoria: con varios backends, enrutar el WebSocket del teléfono
  al mismo backend que atiende el dashboard, o mover `DeviceHub` a un bus compartido.
- Política de retención de metadatos de sesión (hoy se conservan; no contienen medios).

## 5. Pruebas

```bash
cd backend && PYTHONPATH=src pytest tests/mobile_cameras   # 47 pruebas
cd frontend && npm test                                    # incluye labels.test.ts
cd mobile/bandit_mobile_camera && flutter test             # tras ./setup.sh
```
