# Bandit Mobile Camera

## Especificación técnica y plan de implementación

**Proyecto:** Bandit\
**Módulo:** Bandit Mobile Camera\
**Versión del documento:** 1.0\
**Estado:** Diseño técnico / pendiente de implementación y validación\
**Plataformas:** Android e iOS\
**Modalidad:** Transmisión bajo demanda\
**Medios:** Vídeo y audio, con autorización explícita

------------------------------------------------------------------------

## 1. Objetivo

Bandit Mobile Camera permitirá registrar teléfonos Android y iPhone como
fuentes de vídeo del sistema Bandit. El usuario podrá dejar un teléfono
en una ubicación ---por ejemplo, su casa--- y solicitar desde el
dashboard una transmisión en directo cuando la necesite.

La aplicación móvil capturará vídeo y, si el usuario lo autoriza, audio.
La transmisión se realizará mediante una conexión multimedia segura. El
vídeo podrá integrarse con el flujo de cámaras y análisis que ya utilice
Bandit.

Este módulo amplía las fuentes de vídeo de Bandit: además de cámaras IP
tradicionales, podrá admitir teléfonos móviles autorizados.

### 1.1 Alcance funcional

-   Registrar y vincular teléfonos a una cuenta de Bandit.
-   Admitir Android e iOS desde una aplicación Flutter.
-   Mostrar los dispositivos registrados y su estado.
-   Permitir que el usuario habilite o deshabilite la disponibilidad del
    teléfono.
-   Solicitar una sesión de transmisión desde el dashboard.
-   Solicitar autorización visible en el teléfono antes de activar
    cámara y micrófono.
-   Transmitir vídeo y audio en directo.
-   Visualizar la transmisión desde el dashboard web.
-   Finalizar una sesión y liberar cámara, micrófono y recursos de red.
-   Integrar la fuente móvil con el flujo de cámaras existente.
-   Permitir que el sistema de análisis de Bandit procese fotogramas, si
    el usuario tiene habilitada esa función.

### 1.2 Fuera del alcance inicial

La primera versión no debe prometer:

-   Activar de forma oculta la cámara o el micrófono.
-   Iniciar de forma garantizada la cámara de un iPhone cuando la
    aplicación está suspendida o cerrada.
-   Grabar audio o vídeo permanentemente.
-   Evitar las restricciones de segundo plano impuestas por Android o
    iOS.
-   Acceder a teléfonos que no hayan sido vinculados y autorizados.

------------------------------------------------------------------------

## 2. Experiencia esperada

El escenario principal será:

1.  El usuario instala Bandit Mobile Camera en su Android o iPhone.
2.  Desde Bandit web genera un código QR temporal.
3.  El usuario escanea el QR con el teléfono y confirma la vinculación.
4.  El teléfono aparece en el dashboard como dispositivo registrado.
5.  El usuario abre la aplicación móvil y habilita manualmente el estado
    **Disponible para solicitudes**.
6.  Desde otra red ---por ejemplo, la universidad--- el usuario
    selecciona el teléfono en Bandit y solicita una transmisión.
7.  El teléfono recibe una solicitud visible y pide autorización para
    iniciar cámara y micrófono.
8.  Una vez autorizada, se establece la conexión multimedia.
9.  El usuario visualiza el vídeo y escucha el audio desde el dashboard.
10. Al detener la sesión, la aplicación apaga las pistas de cámara y
    micrófono y Bandit actualiza el estado.

**Importante:** estar registrado no significa que la cámara esté
transmitiendo. El dispositivo solo transmite durante una sesión
autorizada.

------------------------------------------------------------------------

## 3. Arquitectura propuesta

La arquitectura debe reutilizar los servicios y módulos existentes de
Bandit. No se debe crear un segundo motor de videovigilancia ni duplicar
innecesariamente el procesamiento de cámaras.

### 3.1 Componentes

  -----------------------------------------------------------------------
  Componente              Tecnología propuesta    Responsabilidad
  ----------------------- ----------------------- -----------------------
  Aplicación móvil        Flutter                 Interfaz, vinculación,
                                                  permisos y control de
                                                  sesión

  Captura Android         CameraX / APIs          Acceso a cámara y
                          compatibles             micrófono

  Captura iOS             AVFoundation            Acceso a cámara y
                                                  micrófono

  Transporte multimedia   WebRTC                  Transmisión de audio y
                                                  vídeo

  Señalización            WebSocket               Negociación y eventos
                                                  de sesión

  Backend                 FastAPI, si es el       Autenticación,
                          backend actual          dispositivos, permisos
                                                  y sesiones

  Base de datos           PostgreSQL / Supabase,  Persistencia
                          según la configuración  
                          actual                  

  Servidor multimedia     MediaMTX, si ya está    Recepción y
                          desplegado              distribución del flujo

  Dashboard               Next.js                 Gestión de dispositivos
                                                  y reproducción

  Análisis                Motor actual de Bandit  Procesamiento de
                          / Gemini                fotogramas, cuando
                                                  corresponda

  Notificaciones          FCM y APNs, según       Avisos de solicitudes y
                          plataforma              cambios de estado
  -----------------------------------------------------------------------

Las tecnologías de esta tabla son la arquitectura objetivo. Antes de
programar, se debe comprobar la versión, configuración y disponibilidad
real de cada componente en el repositorio y el despliegue.

### 3.2 Diagrama lógico

``` text
┌────────────────────────────────────┐
│       Bandit Mobile Camera         │
│           Flutter                  │
│                                    │
│  Cámara + micrófono + WebRTC       │
└──────────────────┬─────────────────┘
                   │
                   │ WebRTC / WHIP*
                   │
┌──────────────────▼─────────────────┐
│             MediaMTX               │
│       Recepción / distribución     │
└──────────────┬─────────────┬───────┘
               │             │
          RTSP u otro     WebRTC
          protocolo          │
               │             │
┌──────────────▼──────┐  ┌───▼────────────────┐
│ Flujo de cámaras    │  │ Dashboard Next.js  │
│ existente de Bandit│  │ Reproductor en vivo│
└──────────────┬──────┘  └────────────────────┘
               │
┌──────────────▼─────────────────────┐
│ Análisis / supervisor / Gemini    │
│ (si está habilitado en Bandit)     │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│ Backend Bandit                     │
│ FastAPI + WebSocket                │
│                                    │
│ Usuarios, dispositivos, permisos,  │
│ vinculación y sesiones             │
└────────────────────────────────────┘
```

`*` WHIP es una opción de publicación que debe validarse con la versión
de MediaMTX y el cliente WebRTC elegido. Si el cliente Flutter no ofrece
una integración WHIP directa compatible, se implementará un adaptador de
señalización HTTP/WebRTC. No se debe asumir que instalar
`flutter_webrtc` resuelve automáticamente la publicación WHIP.

### 3.3 Separación de responsabilidades

-   **Backend:** controla identidad, propiedad, permisos, estados y
    ciclo de vida de sesiones.
-   **WebSocket:** transporta eventos de señalización y estado; no debe
    transportar el vídeo.
-   **WebRTC:** transporta audio y vídeo.
-   **STUN/TURN:** ayuda a establecer conectividad entre redes
    diferentes. TURN será necesario en redes donde la conexión directa
    no sea posible.
-   **MediaMTX:** recibe y distribuye medios si se utiliza como servidor
    multimedia.
-   **Dashboard:** solicita sesiones y presenta la reproducción.
-   **Análisis:** recibe fotogramas mediante la integración con el flujo
    de cámaras existente.

La transmisión podrá ser directa cuando la conectividad lo permita o
pasar por un servidor TURN/relé multimedia cuando sea necesario. La
arquitectura debe evitar exponer las cámaras o credenciales de medios
directamente a Internet.

------------------------------------------------------------------------

## 4. Integración con Bandit existente

El módulo debe adaptarse a la estructura real del repositorio. La
siguiente estructura es una propuesta de organización, no una afirmación
de que todas estas carpetas ya existan.

``` text
Bandit/
├── backend/
│   └── src/
│       └── bandit/
│           ├── cameras/
│           ├── realtime/
│           └── mobile_cameras/       # Nuevo módulo
│               ├── routes.py
│               ├── service.py
│               ├── models.py
│               ├── schemas.py
│               ├── repository.py
│               ├── pairing.py
│               ├── sessions.py
│               ├── signaling.py
│               └── security.py
│
├── frontend/
│   └── src/
│       └── features/
│           └── mobile-camera/        # Nueva funcionalidad
│               ├── components/
│               ├── hooks/
│               ├── services/
│               ├── types/
│               └── pages/            # Ajustar al router existente
│
├── mobile/                            # Nueva aplicación Flutter
│   └── bandit_mobile_camera/
│       ├── lib/
│       │   ├── app/
│       │   ├── features/
│       │   │   ├── pairing/
│       │   │   ├── camera/
│       │   │   ├── sessions/
│       │   │   └── settings/
│       │   └── services/
│       ├── android/
│       └── ios/
│
└── deploy/
    └── mediamtx/                       # Solo si coincide con despliegue actual
```

### 4.1 Reutilización obligatoria

Antes de crear código nuevo, revisar y reutilizar:

-   Servicio de autenticación y autorización.
-   Modelo y repositorio de cámaras.
-   Supervisor o gestor de fuentes de vídeo.
-   Servicio de WebSocket y eventos en tiempo real.
-   Configuración de MediaMTX.
-   Reproductor de vídeo del dashboard.
-   Sistema de análisis y envío de fotogramas a Gemini.
-   Configuración de PostgreSQL/Supabase y migraciones.
-   Convenciones de API, errores, logs y pruebas.

No se deben duplicar usuarios, permisos, cámaras, reproductores ni
motores de análisis si ya existen equivalentes.

### 4.2 Integración como fuente de cámara

Una cámara móvil debe registrarse como un tipo de fuente distinto, por
ejemplo:

``` json
{
  "source_type": "mobile",
  "device_id": "uuid-del-dispositivo",
  "display_name": "Teléfono sala",
  "transport": "webrtc",
  "status": "available"
}
```

El modelo de cámara existente debe ampliarse de manera compatible. No se
debe romper el registro de cámaras RTSP, ONVIF o de fabricantes ya
soportados.

------------------------------------------------------------------------

## 5. Aplicación móvil Flutter

### 5.1 Responsabilidades

La aplicación móvil debe:

-   Vincular el dispositivo con Bandit.
-   Autenticar al usuario o dispositivo.
-   Solicitar permisos de cámara y micrófono.
-   Mostrar el estado de disponibilidad.
-   Recibir solicitudes de sesión.
-   Presentar una confirmación clara antes de transmitir.
-   Capturar vídeo y audio.
-   Establecer y mantener la conexión WebRTC.
-   Mostrar indicadores visibles de cámara y micrófono activos.
-   Permitir detener la transmisión inmediatamente.
-   Liberar todos los recursos al finalizar.
-   Informar al backend cuando cambie su estado.

### 5.2 Paquetes y APIs

  -----------------------------------------------------------------------
  Tecnología                          Uso
  ----------------------------------- -----------------------------------
  Flutter                             Aplicación multiplataforma

  `flutter_webrtc`                    PeerConnection, pistas y
                                      negociación WebRTC

  CameraX / APIs Android              Captura nativa en Android cuando
                                      sea necesaria

  AVFoundation                        Captura nativa en iOS cuando sea
                                      necesaria

  WebSocket                           Señalización y eventos

  FCM / APNs                          Notificaciones de solicitudes,
                                      sujeto a permisos

  Almacenamiento seguro del sistema   Guardar tokens de dispositivo
  -----------------------------------------------------------------------

Las dependencias deben fijarse a versiones compatibles y mantenerse
actualizadas. Los permisos y la captura nativa deben probarse en
dispositivos físicos de ambas plataformas.

### 5.3 Pantallas móviles

1.  **Inicio / vinculación:** escaneo de QR y confirmación de cuenta.
2.  **Dispositivo:** nombre, plataforma, estado y última conexión.
3.  **Disponibilidad:** activar o desactivar la recepción de
    solicitudes.
4.  **Solicitud entrante:** quién solicita la sesión y qué permisos
    necesita.
5.  **Transmisión activa:** vista previa e indicadores visibles de
    cámara y micrófono.
6.  **Privacidad y ajustes:** permisos, audio, cámara seleccionada y
    desvinculación.

------------------------------------------------------------------------

## 6. Comportamiento por plataforma

### 6.1 Android

Android ofrece opciones de servicio en primer plano, pero el acceso a
cámara y micrófono está sujeto a las reglas de la versión del sistema,
permisos y restricciones de inicio de servicios.

Requisitos:

-   Solicitar permisos de cámara y micrófono.
-   Si se utiliza un servicio en primer plano, implementar el tipo y
    permisos correspondientes a la versión objetivo de Android.
-   Mostrar notificación persistente cuando el servicio esté activo.
-   Iniciar la captura como resultado de una acción explícita del
    usuario y respetar las restricciones del sistema.
-   Gestionar optimización de batería sin prometer que pueda
    deshabilitarse en todos los fabricantes.
-   Detener cámara y micrófono al terminar la sesión.

No se debe garantizar que Android permita iniciar la cámara remotamente
en cualquier estado del teléfono. Debe probarse en distintas versiones y
fabricantes.

### 6.2 iOS

iOS limita la ejecución en segundo plano y el acceso a cámara/micrófono.
No se debe diseñar el producto suponiendo que una notificación push
puede activar la cámara de forma silenciosa.

Requisitos:

-   Solicitar permisos de cámara y micrófono.
-   La aplicación debe estar en un estado que permita iniciar captura.
-   Una notificación puede avisar de una solicitud, pero el usuario
    deberá abrir la aplicación y autorizar la sesión cuando iOS no
    permita iniciar la captura desde segundo plano.
-   Mostrar claramente cuándo cámara y micrófono están activos.
-   Liberar las sesiones y recursos al terminar o al perder permisos.

**Comportamiento esperado:** en iPhone, la disponibilidad puede
significar que el dispositivo está registrado y puede recibir avisos; no
garantiza que pueda empezar a transmitir con la aplicación suspendida.

------------------------------------------------------------------------

## 7. Vinculación mediante QR

### 7.1 Flujo

1.  El usuario autenticado abre la sección de cámaras móviles en Bandit
    web.
2.  El backend crea un código de vinculación aleatorio, de un solo uso y
    con vencimiento corto.
3.  El frontend muestra el QR con un identificador y el secreto temporal
    necesario para completar la vinculación.
4.  La aplicación Flutter escanea el QR.
5.  La aplicación confirma la identidad del usuario y solicita completar
    la vinculación.
6.  El backend valida vencimiento, uso, usuario y permisos.
7.  Se registra el dispositivo y se invalida el código.
8.  La aplicación recibe credenciales de dispositivo de corta duración o
    un mecanismo de renovación seguro.

### 7.2 Seguridad del QR

-   No incluir contraseñas ni tokens permanentes.
-   No registrar el contenido sensible del QR en logs.
-   Guardar en la base de datos el hash del código, no el código en
    texto plano.
-   Usar vencimiento breve y un solo uso.
-   Limitar intentos y solicitudes de vinculación.
-   Permitir revocar y desvincular el dispositivo.
-   Exigir autenticación para generar y completar la vinculación.

------------------------------------------------------------------------

## 8. Flujo de sesión bajo demanda

### 8.1 Estados

Estados sugeridos del dispositivo:

-   `unpaired`
-   `offline`
-   `registered`
-   `available`
-   `busy`
-   `needs_user_action`
-   `revoked`

Estados sugeridos de una sesión:

-   `requested`
-   `awaiting_device`
-   `accepted`
-   `connecting`
-   `live`
-   `reconnecting`
-   `rejected`
-   `ended`
-   `failed`
-   `expired`

Las transiciones deben validarse en el backend. El frontend no puede
cambiar por sí solo una sesión a `live`.

### 8.2 Secuencia

1.  El usuario solicita transmisión desde Bandit web.
2.  El backend comprueba que el usuario puede acceder al dispositivo.
3.  Se crea una sesión con vencimiento.
4.  El backend notifica al móvil mediante WebSocket si está conectado y,
    cuando proceda, mediante push.
5.  El móvil presenta una solicitud visible.
6.  El usuario acepta o rechaza.
7.  Si acepta, la aplicación solicita o verifica los permisos del
    sistema.
8.  Se negocia WebRTC mediante el mecanismo de señalización configurado.
9.  Se inicia el flujo de audio y vídeo.
10. El backend actualiza la sesión y el dashboard comienza la
    reproducción.
11. Al finalizar, cualquiera de los participantes autorizados puede
    detener la sesión.
12. Se cierran pistas, PeerConnection, rutas temporales y credenciales
    de sesión.

### 8.3 Eventos WebSocket sugeridos

Solicitud:

``` json
{
  "type": "mobile_camera.session_requested",
  "session_id": "uuid",
  "device_id": "uuid",
  "expires_at": "2026-11-16T23:59:00Z"
}
```

Aceptación:

``` json
{
  "type": "mobile_camera.session_accepted",
  "session_id": "uuid",
  "audio_enabled": true,
  "video_enabled": true
}
```

Rechazo:

``` json
{
  "type": "mobile_camera.session_rejected",
  "session_id": "uuid"
}
```

Fin:

``` json
{
  "type": "mobile_camera.session_ended",
  "session_id": "uuid",
  "reason": "user_stopped"
}
```

Los mensajes reales deben validarse con esquemas estrictos,
autenticación y autorización. No confiar en el `user_id`, `device_id` o
permisos enviados por el cliente sin comprobarlos en el backend.

------------------------------------------------------------------------

## 9. WebRTC, STUN, TURN y MediaMTX

### 9.1 WebRTC

WebRTC será el transporte de audio y vídeo. La señalización es
responsabilidad de Bandit o del mecanismo de publicación compatible con
MediaMTX.

### 9.2 STUN y TURN

-   STUN ayuda a descubrir cómo puede alcanzarse un dispositivo detrás
    de NAT.
-   TURN retransmite medios cuando no es posible una conexión directa.
-   Debe desplegarse y probarse un servicio TURN confiable para redes
    restrictivas.
-   Las credenciales TURN deben ser temporales y generadas de forma
    segura.
-   No publicar credenciales permanentes en el frontend ni en la
    aplicación móvil.

### 9.3 MediaMTX

MediaMTX puede funcionar como servidor de recepción y distribución
multimedia si la versión desplegada admite el flujo elegido.

Diseño objetivo:

1.  La aplicación móvil publica una sesión WebRTC.
2.  MediaMTX recibe el flujo en una ruta temporal asociada a la sesión.
3.  MediaMTX distribuye el flujo al dashboard mediante WebRTC.
4.  Si el supervisor actual de Bandit necesita RTSP, se utiliza la
    salida RTSP de MediaMTX o el adaptador apropiado.
5.  Al terminar, se invalida la ruta temporal y se detiene la
    publicación.

### 9.4 WHIP

WHIP puede simplificar la publicación WebRTC hacia un servidor
compatible. Antes de implementarlo:

-   Verificar que la versión concreta de MediaMTX soporte la modalidad
    requerida.
-   Verificar compatibilidad del cliente Flutter con WHIP.
-   Si no existe compatibilidad directa, desarrollar el adaptador
    necesario para HTTP/SDP e ICE.
-   Probar audio, vídeo, renegociación, desconexión y reconexión.
-   No mezclar la señalización de Bandit con la publicación WHIP sin
    definir quién es responsable de cada etapa.

### 9.5 Audio y vídeo

-   Audio y vídeo se habilitan explícitamente.
-   El audio no debe grabarse ni persistirse por defecto.
-   La visualización en vivo puede incluir audio cuando esté autorizado.
-   El análisis de Gemini puede trabajar con fotogramas, sin requerir
    almacenamiento de audio.
-   Debe existir una opción visible para desactivar el audio.
-   Los permisos del sistema operativo prevalecen sobre las preferencias
    de Bandit.

------------------------------------------------------------------------

## 10. API propuesta

Los endpoints siguientes son una propuesta y deben adaptarse a las
convenciones existentes del backend.

  --------------------------------------------------------------------------------------------------
  Método                  Endpoint                                           Descripción
  ----------------------- -------------------------------------------------- -----------------------
  `POST`                  `/api/mobile-cameras/pairing`                      Generar vinculación
                                                                             temporal

  `POST`                  `/api/mobile-cameras/register`                     Completar registro del
                                                                             móvil

  `GET`                   `/api/mobile-cameras`                              Listar dispositivos del
                                                                             usuario

  `GET`                   `/api/mobile-cameras/{id}`                         Consultar un
                                                                             dispositivo

  `PATCH`                 `/api/mobile-cameras/{id}/availability`            Cambiar disponibilidad

  `DELETE`                `/api/mobile-cameras/{id}`                         Revocar o desvincular

  `POST`                  `/api/mobile-cameras/{id}/sessions`                Solicitar sesión

  `POST`                  `/api/mobile-camera-sessions/{id}/accept`          Aceptar sesión

  `POST`                  `/api/mobile-camera-sessions/{id}/reject`          Rechazar sesión

  `POST`                  `/api/mobile-camera-sessions/{id}/stop`            Detener sesión

  `GET`                   `/api/mobile-camera-sessions/{id}`                 Consultar estado

  `POST`                  `/api/mobile-camera-sessions/{id}/stream-ticket`   Obtener autorización
                                                                             multimedia temporal
  --------------------------------------------------------------------------------------------------

### 10.1 Reglas de API

-   Todas las rutas privadas requieren autenticación.
-   Comprobar propiedad del dispositivo y acceso al establecimiento o
    espacio correspondiente.
-   Comprobar permisos en cada operación sensible.
-   Usar UUID no predecibles como identificadores, sin tratarlos como
    sustituto de autorización.
-   Los tickets multimedia deben ser temporales, de alcance limitado y
    de un solo uso cuando sea posible.
-   Aplicar rate limiting en vinculación, solicitudes y autenticación.
-   Validar tamaños, formatos y estados.
-   No aceptar rutas de medios arbitrarias enviadas por el cliente.
-   No devolver secretos de MediaMTX, TURN o del proveedor de
    almacenamiento.
-   Registrar eventos de auditoría sin almacenar audio o vídeo.

------------------------------------------------------------------------

## 11. Modelo de datos propuesto

Los nombres y tipos deben adaptarse al esquema actual de
PostgreSQL/Supabase. Las migraciones deben ser compatibles con los datos
existentes.

### 11.1 `mobile_camera_devices`

  -----------------------------------------------------------------------
  Campo                   Tipo sugerido           Descripción
  ----------------------- ----------------------- -----------------------
  `id`                    UUID                    Identificador

  `user_id`               UUID                    Propietario

  `establishment_id`      UUID nullable           Espacio o
                                                  establecimiento, si
                                                  aplica

  `device_name`           VARCHAR                 Nombre visible

  `platform`              VARCHAR / ENUM          `android` o `ios`

  `device_token_hash`     VARCHAR                 Referencia/hash de
                                                  credencial, según
                                                  estrategia

  `push_token`            VARCHAR nullable        Token push cifrado o
                                                  protegido, si se
                                                  necesita

  `status`                VARCHAR / ENUM          Estado actual

  `is_available`          BOOLEAN                 Disponibilidad
                                                  solicitada

  `last_seen`             TIMESTAMP nullable      Última comunicación

  `created_at`            TIMESTAMP               Creación

  `updated_at`            TIMESTAMP               Actualización

  `revoked_at`            TIMESTAMP nullable      Revocación
  -----------------------------------------------------------------------

No almacenar tokens de autenticación en texto plano. Los tokens push son
datos sensibles y deben protegerse y poder rotarse.

### 11.2 `mobile_camera_sessions`

  -----------------------------------------------------------------------
  Campo                   Tipo sugerido           Descripción
  ----------------------- ----------------------- -----------------------
  `id`                    UUID                    Identificador

  `device_id`             UUID                    Dispositivo

  `requested_by`          UUID                    Usuario solicitante

  `status`                VARCHAR / ENUM          Estado de sesión

  `audio_enabled`         BOOLEAN                 Audio autorizado

  `video_enabled`         BOOLEAN                 Vídeo autorizado

  `media_path`            VARCHAR nullable        Ruta temporal, no
                                                  secreto permanente

  `started_at`            TIMESTAMP nullable      Inicio

  `ended_at`              TIMESTAMP nullable      Finalización

  `expires_at`            TIMESTAMP               Vencimiento

  `created_at`            TIMESTAMP               Creación

  `end_reason`            VARCHAR nullable        Motivo de cierre
  -----------------------------------------------------------------------

### 11.3 `mobile_camera_pairings`

  Campo                 Tipo sugerido        Descripción
  --------------------- -------------------- ---------------------
  `id`                  UUID                 Identificador
  `user_id`             UUID                 Usuario que vincula
  `pairing_code_hash`   VARCHAR              Hash del código
  `expires_at`          TIMESTAMP            Vencimiento
  `used_at`             TIMESTAMP nullable   Fecha de uso
  `created_at`          TIMESTAMP            Creación

### 11.4 Índices y restricciones

-   Índice por `user_id` en dispositivos.
-   Índice por `device_id` y `status` en sesiones.
-   Índice por `expires_at` para limpiar sesiones vencidas.
-   Restricción para evitar códigos de vinculación duplicados.
-   Política de unicidad del dispositivo según la identidad estable que
    permita cada plataforma.
-   Foreign keys y reglas de borrado coherentes con el modelo de
    usuarios actual.
-   Políticas RLS si se usa Supabase directamente desde clientes; las
    operaciones privilegiadas deben permanecer en backend seguro.

------------------------------------------------------------------------

## 12. Dashboard Next.js

Agregar una sección **Cámaras móviles** dentro del módulo de cámaras
existente, no un dashboard separado.

### 12.1 Vista de dispositivos

Debe mostrar:

-   Nombre del teléfono.
-   Plataforma: Android o iOS.
-   Estado: desconectado, registrado, disponible, ocupado o requiere
    acción.
-   Última conexión.
-   Indicador de disponibilidad.
-   Acción para solicitar transmisión.
-   Acción para revocar o desvincular.
-   Acción para generar QR de vinculación.

### 12.2 Vista de sesión

Debe mostrar:

-   Reproductor de vídeo.
-   Estado de conexión.
-   Indicador visible de audio.
-   Controles para silenciar o activar el audio de reproducción, si la
    sesión lo permite.
-   Botón para detener la sesión.
-   Mensajes claros de espera, rechazo, vencimiento, reconexión o error.

El navegador debe obtener acceso multimedia mediante un ticket temporal
y no mediante una URL permanente o credenciales estáticas.

### 12.3 Estados de interfaz

-   Sin dispositivos vinculados.
-   Dispositivo sin conexión.
-   Dispositivo registrado pero no disponible.
-   Esperando autorización en el teléfono.
-   Conectando.
-   Transmisión activa.
-   Reconectando.
-   Sesión finalizada.
-   Error de permisos.
-   Dispositivo revocado.

------------------------------------------------------------------------

## 13. Integración con el análisis de Bandit y Gemini

La fuente móvil debe entrar en el mismo flujo de procesamiento de
cámaras que ya utiliza Bandit.

Flujo esperado:

1.  MediaMTX recibe el flujo móvil.
2.  El adaptador de cámaras registra la fuente como `mobile`.
3.  El supervisor existente obtiene fotogramas.
4.  El sistema de análisis procesa los fotogramas según la configuración
    del usuario.
5.  Los eventos detectados continúan por el pipeline actual.
6.  El dashboard presenta eventos asociados a la cámara móvil.

No se debe enviar cada fotograma a Gemini sin control. Reutilizar la
estrategia actual de muestreo, límites, colas y tratamiento de errores
para controlar costos y latencia.

El audio se mantiene separado del análisis visual inicial. No
implementar reconocimiento, almacenamiento o análisis de audio sin un
requisito explícito y una autorización adicional.

------------------------------------------------------------------------

## 14. Seguridad y privacidad

La seguridad es requisito de diseño, no una fase opcional.

### 14.1 Controles obligatorios

-   Autenticación de usuarios y dispositivos.
-   Autorización por propietario y ámbito de acceso.
-   Vinculación QR temporal, de un solo uso.
-   Revocación de dispositivos.
-   TLS para HTTPS y WSS.
-   WebRTC con cifrado de medios según el protocolo.
-   Tickets multimedia temporales y de alcance limitado.
-   Credenciales TURN temporales.
-   Separación de señalización y medios.
-   Rate limiting y protección contra abuso.
-   Validación de cada transición de sesión en el backend.
-   Logs de auditoría sin contenido multimedia.
-   Protección de tokens y secretos.
-   Cierre de sesiones vencidas.
-   Indicadores visibles de cámara y micrófono activos.
-   Acción inmediata para detener la transmisión.

### 14.2 Privacidad

-   No iniciar captura sin autorización visible del usuario.
-   No activar cámara o micrófono de forma oculta.
-   No guardar audio o vídeo por defecto.
-   Informar quién solicita la sesión.
-   Permitir rechazar la solicitud.
-   Permitir detener la transmisión en cualquier momento.
-   Mostrar el estado de los permisos.
-   Permitir desvincular el dispositivo.
-   Definir retención y borrado de metadatos de sesión.

------------------------------------------------------------------------

## 15. Reconexión y tratamiento de errores

La aplicación y el backend deben manejar:

-   Pérdida de Wi-Fi o datos móviles.
-   Cambio entre Wi-Fi y red móvil.
-   Caída de WebSocket.
-   Fallo de negociación WebRTC.
-   Fallo de ICE.
-   TURN no disponible.
-   MediaMTX no disponible.
-   Permiso de cámara revocado.
-   Permiso de micrófono revocado.
-   Aplicación suspendida o cerrada.
-   Sesión vencida.
-   Solicitud rechazada.
-   Usuario que detiene la sesión desde el dashboard.

La reconexión debe respetar el vencimiento de la sesión y volver a
comprobar la autorización. No debe reactivar cámara o micrófono
silenciosamente después de que el sistema operativo haya suspendido o
terminado la aplicación.

------------------------------------------------------------------------

## 16. Configuración y despliegue

Las variables siguientes son nombres ilustrativos. Deben alinearse con
el sistema de configuración y secretos que ya tenga Bandit.

``` env
# Backend
MOBILE_CAMERA_ENABLED=true
MOBILE_CAMERA_PAIRING_TTL_SECONDS=300
MOBILE_CAMERA_SESSION_TTL_SECONDS=900

# WebRTC / ICE
WEBRTC_STUN_URL=stun:stun.example.com:3478
WEBRTC_TURN_URL=turn:turn.example.com:3478
WEBRTC_TURN_USERNAME=
WEBRTC_TURN_CREDENTIAL=

# MediaMTX
MEDIAMTX_WEBRTC_ENABLED=true
MEDIAMTX_WHIP_ENABLED=true
MEDIAMTX_INTERNAL_URL=
MEDIAMTX_PUBLIC_URL=

# Notificaciones
FCM_PROJECT_ID=
APNS_CONFIGURATION=
```

**No guardar secretos reales en `.env.example`, Git ni documentación.**
Los valores sensibles deben configurarse en el gestor de secretos del
entorno de despliegue.

### 16.1 Requisitos de infraestructura

-   HTTPS y WSS con certificados válidos.
-   MediaMTX accesible solo por los puertos y rutas necesarios.
-   STUN/TURN desplegado y probado.
-   Reglas de firewall documentadas.
-   Límites de conexiones y ancho de banda.
-   Monitorización de sesiones y recursos.
-   Limpieza de sesiones y rutas multimedia vencidas.
-   Entornos separados para desarrollo, pruebas y producción.

No exponer interfaces administrativas de MediaMTX a Internet. Las rutas
de medios deben ser temporales y estar protegidas.

------------------------------------------------------------------------

## 17. Plan de implementación por fases

### Fase 0 --- Auditoría del repositorio

Antes de modificar:

-   Revisar la estructura real de Bandit.
-   Identificar modelos y endpoints de cámaras.
-   Identificar autenticación y autorización.
-   Revisar WebSocket y eventos actuales.
-   Revisar configuración y versión de MediaMTX.
-   Revisar supervisor y pipeline de análisis.
-   Revisar dashboard y reproductor.
-   Revisar migraciones y políticas de base de datos.
-   Documentar puntos de integración y pruebas existentes.

**Entregable:** mapa de integración aprobado y lista de archivos que se
modificarán.

### Fase 1 --- Backend, base de datos y vinculación

-   Crear migraciones de dispositivos, sesiones y códigos QR.
-   Crear modelos, esquemas, repositorios y servicios.
-   Implementar creación y consumo de códigos QR.
-   Implementar registro, listado, disponibilidad y revocación.
-   Implementar autorización por usuario.
-   Implementar estados y vencimiento de sesiones.
-   Crear endpoints y pruebas.

**Entregable:** teléfonos registrables y administrables desde la API,
todavía sin vídeo.

### Fase 2 --- Aplicación Flutter

-   Crear proyecto Flutter.
-   Implementar escaneo de QR.
-   Implementar autenticación y registro.
-   Implementar permisos de cámara y micrófono.
-   Implementar disponibilidad y estado.
-   Implementar solicitud entrante y confirmación visible.
-   Implementar captura local y vista previa.
-   Implementar cierre y liberación de recursos.

**Entregable:** aplicación Android/iOS vinculada y con captura local
autorizada.

### Fase 3 --- WebRTC y MediaMTX

-   Definir mecanismo de señalización.
-   Configurar STUN/TURN.
-   Validar WHIP o implementar adaptador.
-   Publicar flujo de prueba desde Android.
-   Publicar flujo de prueba desde iOS.
-   Recibir flujo en MediaMTX.
-   Validar vídeo y audio.
-   Validar redes diferentes.
-   Validar reconexión y cierre.
-   Proteger rutas y credenciales.

**Entregable:** flujo móvil de audio y vídeo recibido de forma segura
por la infraestructura multimedia.

### Fase 4 --- Dashboard

-   Crear sección de cámaras móviles.
-   Implementar QR.
-   Mostrar dispositivos y estados.
-   Solicitar, aceptar y detener sesiones.
-   Implementar reproductor WebRTC.
-   Mostrar errores y estados de conexión.
-   Integrar controles de audio.

**Entregable:** transmisión solicitada y visualizada desde el dashboard.

### Fase 5 --- Integración con cámaras y Gemini

-   Adaptar el modelo de fuentes de cámara.
-   Incorporar la fuente móvil al supervisor existente.
-   Adaptar MediaMTX/RTSP al consumidor actual.
-   Reutilizar muestreo y colas de fotogramas.
-   Integrar el análisis existente.
-   Asociar eventos a la cámara y sesión correctas.
-   Probar que las cámaras tradicionales siguen funcionando.

**Entregable:** cámara móvil tratada como fuente del ecosistema actual
de Bandit.

### Fase 6 --- Seguridad, estabilidad y pruebas finales

-   Probar autorización y revocación.
-   Probar permisos revocados.
-   Probar Android e iOS físicos.
-   Probar redes domésticas, universitarias y móviles.
-   Probar TURN.
-   Probar desconexiones y reconexiones.
-   Probar múltiples dispositivos y sesiones.
-   Probar carga, ancho de banda y latencia.
-   Revisar logs, secretos y exposición de puertos.
-   Documentar instalación, operación y recuperación.

**Entregable:** módulo listo para despliegue controlado.

------------------------------------------------------------------------

## 18. Criterios de aceptación

### Vinculación y administración

-   [ ] Generar QR temporal desde Bandit web.
-   [ ] Vincular Android.
-   [ ] Vincular iPhone.
-   [ ] Rechazar QR vencido o ya utilizado.
-   [ ] Listar dispositivos vinculados.
-   [ ] Cambiar disponibilidad.
-   [ ] Revocar o desvincular dispositivo.

### Sesiones

-   [ ] Solicitar una sesión desde otra red.
-   [ ] Mostrar solicitud visible en el teléfono.
-   [ ] Aceptar y rechazar solicitudes.
-   [ ] Impedir sesiones de usuarios no autorizados.
-   [ ] Manejar vencimiento.
-   [ ] Detener desde el móvil.
-   [ ] Detener desde el dashboard.

### Multimedia

-   [ ] Transmitir vídeo desde Android.
-   [ ] Transmitir vídeo desde iOS.
-   [ ] Transmitir audio con autorización.
-   [ ] Reproducir audio y vídeo desde el dashboard.
-   [ ] Probar conexión directa.
-   [ ] Probar conexión mediante TURN.
-   [ ] Probar redes diferentes.
-   [ ] Cerrar pistas y recursos al finalizar.

### Integración

-   [ ] Registrar móvil como fuente de cámara.
-   [ ] Integrar con el supervisor existente.
-   [ ] Procesar fotogramas mediante el pipeline actual.
-   [ ] Mantener funcionando las cámaras IP existentes.
-   [ ] Asociar eventos a la fuente correcta.

### Privacidad y seguridad

-   [ ] Indicador visible de cámara y micrófono.
-   [ ] Autorización explícita para cada sesión.
-   [ ] No almacenar audio/vídeo por defecto.
-   [ ] Tickets y credenciales temporales.
-   [ ] Revocación efectiva.
-   [ ] Sin secretos en el repositorio.
-   [ ] Auditoría de solicitudes y sesiones.

------------------------------------------------------------------------

## 19. Estrategia de pruebas

### Backend

-   Pruebas unitarias de vinculación y vencimiento.
-   Pruebas de autorización por propietario.
-   Pruebas de transición de estados.
-   Pruebas de revocación.
-   Pruebas de sesiones concurrentes.
-   Pruebas de endpoints y WebSocket.

### Flutter

-   Pruebas de permisos.
-   Pruebas de captura y liberación.
-   Pruebas de aceptación y rechazo.
-   Pruebas en Android físico.
-   Pruebas en iPhone físico.
-   Pruebas de suspensión, reanudación y cierre.

### WebRTC / MediaMTX

-   Prueba LAN.
-   Prueba entre redes distintas.
-   Prueba con TURN obligatorio.
-   Prueba de audio y vídeo.
-   Prueba de desconexión.
-   Prueba de reconexión.
-   Prueba de cierre y expiración.

### Dashboard

-   Pruebas de estados.
-   Pruebas de autorización.
-   Pruebas de reproducción.
-   Pruebas de detención.
-   Pruebas de errores y reconexión.

------------------------------------------------------------------------

## 20. Riesgos técnicos y decisiones pendientes

  -----------------------------------------------------------------------
  Riesgo o decisión                   Tratamiento
  ----------------------------------- -----------------------------------
  iOS suspende la aplicación          Exigir apertura/acción del usuario
                                      para iniciar captura cuando sea
                                      necesario

  Android limita servicios de cámara  Cumplir las reglas de foreground
                                      service y probar por versión

  NAT impide conexión directa         Desplegar TURN

  Flutter no publica WHIP             Validar cliente o desarrollar
  directamente                        adaptador

  Supervisor consume RTSP             Usar salida RTSP de MediaMTX o
                                      adaptador

  Ancho de banda elevado              Ajustar resolución, FPS y bitrate

  Varios móviles simultáneos          Definir límites por usuario y
                                      capacidad de infraestructura

  Pérdida de conexión                 Estados, vencimientos y reconexión
                                      autorizada

  Costos de análisis                  Reutilizar muestreo y límites
                                      existentes

  Privacidad de audio                 No grabar ni persistir por defecto
  -----------------------------------------------------------------------

### Decisiones que deben confirmarse durante la auditoría

1.  Versión real de MediaMTX y protocolos habilitados.
2.  Si el dashboard ya tiene reproductor WebRTC reutilizable.
3.  Cómo consume vídeo el supervisor actual.
4.  Si el backend ya dispone de un sistema de notificaciones.
5.  Qué mecanismo de autenticación y permisos utiliza Bandit.
6.  Cómo se aplican las políticas RLS de Supabase.
7.  Cuántas transmisiones simultáneas debe soportar la primera versión.
8.  Resolución, FPS y bitrate iniciales.

------------------------------------------------------------------------

## 21. Orden recomendado de desarrollo

No comenzar implementando todas las pantallas a la vez. El orden que
reduce riesgos es:

1.  Auditar y documentar los puntos de integración.
2.  Implementar registro y vinculación.
3.  Implementar una prueba Flutter de captura local.
4.  Establecer una sesión WebRTC entre redes distintas.
5.  Recibir el flujo en MediaMTX.
6.  Reproducirlo en un navegador.
7.  Conectar el flujo al supervisor de Bandit.
8.  Integrar Gemini.
9.  Completar controles, notificaciones y estados.
10. Ejecutar pruebas de seguridad, privacidad y estabilidad.

**Prueba vertical mínima:** un Android o iPhone vinculado, una solicitud
autorizada, vídeo y audio en directo desde otra red, reproducción en el
dashboard y cierre completo de la sesión.

------------------------------------------------------------------------

## 22. Resultado esperado

Al completar el módulo, Bandit tendrá dos grandes tipos de fuentes:

1.  **Cámaras IP:** cámaras de red conectadas mediante los protocolos
    que soporte el sistema actual.
2.  **Cámaras móviles:** teléfonos Android y iPhone vinculados, que
    transmiten audio y vídeo bajo demanda y con autorización visible.

Ambas fuentes deberán integrarse en el mismo dashboard, sistema de
eventos y pipeline de análisis, siempre que los protocolos y capacidades
de la infraestructura lo permitan.

El módulo debe construirse de forma incremental, reutilizando la
arquitectura actual de Bandit, preservando las cámaras existentes y
manteniendo la privacidad del usuario como requisito obligatorio.

------------------------------------------------------------------------

## 23. Referencias técnicas

-   Flutter: https://docs.flutter.dev/
-   flutter_webrtc: https://pub.dev/packages/flutter_webrtc
-   WebRTC: https://webrtc.org/
-   MediaMTX: https://github.com/bluenviron/mediamtx
-   Documentación MediaMTX: https://mediamtx.org/docs/
-   Android CameraX: https://developer.android.com/media/camera/camerax
-   Android foreground services:
    https://developer.android.com/develop/background-work/services/foreground-services
-   Apple AVFoundation:
    https://developer.apple.com/documentation/avfoundation
-   Apple Background Execution:
    https://developer.apple.com/documentation/backgroundtasks
-   Firebase Cloud Messaging:
    https://firebase.google.com/docs/cloud-messaging
-   Apple Push Notification service:
    https://developer.apple.com/documentation/usernotifications
